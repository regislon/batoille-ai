"""Async wrapper around `piper-tts` for German text-to-speech.

The ONLY module in batoiller that imports `piper`. Apple-Silicon-compatible
via ONNX Runtime; no Metal, so concurrent calls are safe (unlike STT).

Voice files are auto-downloaded into `~/.batoiller/voices/` on first use
via piper's own `python -m piper.download_voices` CLI. Subsequent runs
reuse the cached files.

Note: piper-tts is GPLv3. Using it as a runtime dependency in this MIT
project means batoiller as a whole acts as a "combined work" under
GPLv3 when distributed. Acceptable for a personal language tutor; if
you ever ship this commercially, revisit.
"""

import asyncio
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice

from batoiller.audio.models import TTSError

_DEFAULT_VOICE = "de_DE-thorsten-high"

# Sentence-streaming knobs (used by speak_stream / _pop_sentence).
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|\n|$)")
_MIN_SENTENCE_CHARS = 15  # avoid splitting on "z.B.", "Dr.", ordinals like "1."
_AUDIO_QUEUE_MAXSIZE = 2  # one playing, one ready — backpressure on synthesis
# Silence prepended to chunks written to the OutputStream. Asymmetric:
#  - First chunk: just enough to cover the audio device's warmup so the
#    first phoneme isn't clipped on macOS CoreAudio. Anything more is
#    pure latency on time-to-first-audio.
#  - Subsequent chunks: a longer pause so consecutive sentences don't
#    run together. Without this, OutputStream concatenates back-to-back
#    and speech sounds rushed (no comma-like break between "Hallo." and
#    "Wie geht's?").
_DEVICE_WARMUP_SILENCE_MS = 80
_INTER_SENTENCE_SILENCE_MS = 200


def _pop_sentence(buffer: str) -> tuple[str | None, str]:
    """Find the first qualifying sentence boundary in `buffer`.

    A boundary qualifies if either (a) the punctuation is `!` or `?`, or
    (b) the candidate sentence is at least `_MIN_SENTENCE_CHARS` long after
    stripping whitespace. Kills the common German false positives ("z.B.",
    "Dr.", "Nr.", "d.h.", ordinals like "1.") without a hand-maintained
    abbreviation list.

    Returns (sentence_with_trailing_punct_and_space, remainder), or
    (None, buffer) if no qualifying boundary is in the buffer yet.
    """
    for match in _SENTENCE_END_RE.finditer(buffer):
        end = match.end()
        sentence = buffer[:end]
        punct = match.group()[0]
        if punct in "!?" or len(sentence.strip()) >= _MIN_SENTENCE_CHARS:
            return sentence, buffer[end:]
    return None, buffer


def _default_voice_dir() -> Path:
    """Where we cache voice models — alongside the future SQLite DB."""
    return Path.home() / ".batoiller" / "voices"


class TTSService:
    """Synthesize German speech from text via a local Piper voice.

    Voice is lazy-loaded on first call to `synthesize` or `speak`. If the
    voice files are missing, the service auto-invokes piper's downloader
    (a one-time ~114 MB fetch from Hugging Face).
    """

    def __init__(
        self,
        voice: str | None = None,
        voice_dir: Path | None = None,
    ) -> None:
        self._voice_name = (
            voice if voice is not None else os.environ.get("BATOILLER_TTS_VOICE", _DEFAULT_VOICE)
        )
        self._voice_dir = Path(voice_dir) if voice_dir is not None else _default_voice_dir()
        self._voice: PiperVoice | None = None

    @property
    def voice(self) -> str:
        return self._voice_name

    @property
    def voice_dir(self) -> Path:
        return self._voice_dir

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        """Synthesize `text` to raw int16 PCM bytes + the sample rate.

        Returns:
            (audio_bytes, sample_rate). audio_bytes is mono int16 PCM,
            ready to feed to `sounddevice.play(np.frombuffer(...), samplerate=...)`.

        Raises:
            ValueError: if text is empty or whitespace-only.
            TTSError: if voice download fails or synthesis yields no audio.
        """
        if not text.strip():
            raise ValueError("text must not be empty")
        voice = await self._ensure_loaded()
        return await asyncio.to_thread(self._synth_sync, voice, text)

    async def speak(self, text: str) -> None:
        """Synthesize `text` and play through the default audio output.

        Blocks until playback completes. Mic capture won't pick up the
        audio because this awaits playback before returning.
        """
        audio_bytes, sample_rate = await self.synthesize(text)
        await self._play_cancellable(audio_bytes, sample_rate)

    async def speak_stream(
        self,
        text_chunks: AsyncIterator[str],
        on_text: Callable[[str], None] | None = None,
    ) -> str:
        """Stream-synthesize and play audio as text chunks arrive.

        For each complete sentence found in the buffered text, synthesize on
        a worker thread and enqueue for playback. A consumer plays sentences
        in order; synthesis of sentence N+1 can overlap with playback of
        sentence N. Time-to-first-audio drops from "full LLM latency + full
        synthesis" to "first sentence latency + first sentence synthesis".

        Args:
            text_chunks: async iterator of text fragments (e.g. from
                `Tutor.respond_stream`).
            on_text: optional per-chunk callback invoked as each fragment
                arrives — typically used to print the text live.

        Returns:
            The accumulated full text (useful for logging / history).

        Cancellation:
            If the surrounding task is cancelled mid-playback, the audio
            output device is stopped via `sd.stop()` so the worker thread
            returns promptly. `CancelledError` then propagates out.
        """
        voice = await self._ensure_loaded()
        audio_queue: asyncio.Queue[tuple[bytes, int] | None] = asyncio.Queue(
            maxsize=_AUDIO_QUEUE_MAXSIZE
        )
        parts: list[str] = []

        async def producer() -> None:
            buffer = ""
            try:
                async for chunk in text_chunks:
                    if on_text is not None:
                        on_text(chunk)
                    parts.append(chunk)
                    buffer += chunk
                    while True:
                        sentence, buffer = _pop_sentence(buffer)
                        if sentence is None:
                            break
                        audio = await asyncio.to_thread(self._synth_sync, voice, sentence)
                        await audio_queue.put(audio)
                if buffer.strip():
                    audio = await asyncio.to_thread(self._synth_sync, voice, buffer)
                    await audio_queue.put(audio)
            finally:
                # Sentinel pushed on clean exit AND on exception so the
                # consumer always wakes from queue.get(). TaskGroup
                # cancels the consumer on exception, this is belt + braces.
                await audio_queue.put(None)

        async def consumer() -> None:
            # Keep the audio device open across all sentences. Calling
            # sd.play()/sd.wait() per sentence (the old code) produced a
            # click at every boundary because the device closed and
            # re-opened. OutputStream stays initialised; we just write
            # each sentence's PCM into its ring buffer.
            output_stream: sd.OutputStream | None = None
            try:
                while True:
                    item = await audio_queue.get()
                    if item is None:
                        return
                    audio_bytes, sample_rate = item
                    audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
                    if output_stream is None:
                        output_stream = sd.OutputStream(
                            samplerate=sample_rate,
                            channels=1,
                            dtype="int16",
                        )
                        output_stream.start()
                        # First chunk gets just enough silence to cover
                        # the device's warmup transient (otherwise the
                        # first phoneme can clip on macOS).
                        silence_ms = _DEVICE_WARMUP_SILENCE_MS
                    else:
                        # Subsequent chunks get the longer inter-sentence
                        # breathing pause.
                        silence_ms = _INTER_SENTENCE_SILENCE_MS
                    silence_frames = int(sample_rate * silence_ms / 1000)
                    padded = np.concatenate(
                        [np.zeros(silence_frames, dtype=np.int16), audio_np]
                    )
                    await self._stream_write_cancellable(output_stream, padded)
            finally:
                if output_stream is not None:
                    # Synchronous cleanup so cancellation propagation
                    # can't kill the close mid-call. stop() drains the
                    # remaining ring buffer on the happy path; after a
                    # prior abort() it's a no-op.
                    try:
                        output_stream.stop()
                    finally:
                        output_stream.close()

        async with asyncio.TaskGroup() as tg:
            tg.create_task(producer())
            tg.create_task(consumer())

        return "".join(parts)

    async def preload(self) -> None:
        """Force the voice to be loaded (and downloaded if needed) ahead of time.

        Useful at app startup so the user sees the 'downloading…' message
        once, not buried inside the first synthesize call.
        """
        await self._ensure_loaded()

    async def _ensure_loaded(self) -> PiperVoice:
        if self._voice is not None:
            return self._voice
        await self._ensure_voice_files()
        model_path = self._voice_dir / f"{self._voice_name}.onnx"
        self._voice = await asyncio.to_thread(PiperVoice.load, str(model_path))
        return self._voice

    async def _ensure_voice_files(self) -> None:
        model_path = self._voice_dir / f"{self._voice_name}.onnx"
        config_path = self._voice_dir / f"{self._voice_name}.onnx.json"
        if model_path.exists() and config_path.exists():
            return
        print(
            f"Downloading TTS voice {self._voice_name!r} to {self._voice_dir} "
            "(~114 MB, one-time)..."
        )
        self._voice_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    sys.executable,
                    "-m",
                    "piper.download_voices",
                    self._voice_name,
                    "--download-dir",
                    str(self._voice_dir),
                ],
                check=False,
            )
        except FileNotFoundError as exc:
            raise TTSError(f"Could not invoke piper.download_voices: {exc}") from exc
        if result.returncode != 0:
            raise TTSError(
                f"Voice download failed for {self._voice_name!r} "
                f"(exit code {result.returncode}). Try running manually:\n"
                f"  uv run python -m piper.download_voices {self._voice_name} "
                f"--download-dir {self._voice_dir}"
            )
        if not model_path.exists():
            raise TTSError(f"Voice download appeared to succeed but {model_path} is still missing.")

    def _synth_sync(self, voice: PiperVoice, text: str) -> tuple[bytes, int]:
        buffer = bytearray()
        sample_rate = 0
        for chunk in voice.synthesize(text):
            buffer.extend(chunk.audio_int16_bytes)
            if sample_rate == 0:
                sample_rate = chunk.sample_rate
        if not buffer:
            raise TTSError(f"Voice {self._voice_name!r} produced no audio for the given text.")
        return bytes(buffer), sample_rate

    def _play_sync(self, audio_bytes: bytes, sample_rate: int) -> None:
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        sd.play(audio_np, samplerate=sample_rate)
        sd.wait()

    async def _play_cancellable(self, audio_bytes: bytes, sample_rate: int) -> None:
        """Play audio in a worker thread, but actually stop the device on cancel.

        `asyncio.to_thread` does NOT cancel the underlying thread — a
        `CancelledError` only fires once the thread returns. With `sd.wait()`
        blocking for the full duration of an audio chunk, Ctrl+C would feel
        broken. Calling `sd.stop()` from the event-loop side breaks the wait.
        """
        try:
            await asyncio.to_thread(self._play_sync, audio_bytes, sample_rate)
        except asyncio.CancelledError:
            sd.stop()
            raise

    async def _stream_write_cancellable(
        self, stream: sd.OutputStream, audio: np.ndarray
    ) -> None:
        """Write `audio` into an open OutputStream; abort on cancellation.

        Same cancellation pattern as _play_cancellable: stream.write blocks
        in a worker thread; on cancel we call stream.abort() from the loop
        thread, which causes the worker's write to return immediately so
        the thread can be reaped.
        """
        try:
            await asyncio.to_thread(stream.write, audio)
        except asyncio.CancelledError:
            stream.abort()
            raise
