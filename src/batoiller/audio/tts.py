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
import subprocess
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice

from batoiller.audio.models import TTSError

_DEFAULT_VOICE = "de_DE-thorsten-high"


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
        await asyncio.to_thread(self._play_sync, audio_bytes, sample_rate)

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
