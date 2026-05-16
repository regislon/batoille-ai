"""Multi-turn voice REPL with the German tutor.

Run with:
    uv run python scripts/voice_chat.py

Requires:
    - Apple Silicon Mac
    - ffmpeg in PATH (`brew install ffmpeg`)
    - Microphone permission granted to the terminal
    - Ollama daemon running with mistral-small pulled
    - Whisper turbo model downloaded (auto on first run, ~1.5 GB)

Press Enter to start a turn, press Enter again to stop speaking, hear the
tutor's German reply, repeat. Empty recording or Ctrl+C exits.

Note: this is the press-Enter UX. Brick 4 (VAD) upgrades it to hands-free
turn-taking.
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from batoiller.audio import STTService
from batoiller.core import Tutor
from batoiller.llm import LLMConnectionError, LLMModelNotFoundError, OllamaClient

SAMPLE_RATE = 16000
MIN_RECORDING_SECONDS = 0.5
SILENCE_THRESHOLD = 1e-4

SYSTEM_PROMPT = (
    "Du bist ein freundlicher Deutschlehrer für französischsprachige Lerner. "
    "Antworte immer auf Deutsch, mit einfachen Sätzen. Du behältst den Kontext "
    "der ganzen Unterhaltung im Gedächtnis und kannst auf frühere Aussagen "
    "Bezug nehmen."
)


def probe_ffmpeg() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH.", file=sys.stderr)
        print("Hint: `brew install ffmpeg`", file=sys.stderr)
        return 1
    return 0


def probe_microphone() -> int:
    try:
        sd.query_devices(kind="input")
    except sd.PortAudioError as exc:
        print(f"No usable input device: {exc}", file=sys.stderr)
        print(
            "Hint: check System Settings → Privacy & Security → Microphone.",
            file=sys.stderr,
        )
        return 1
    return 0


def record_press_to_stop() -> np.ndarray:
    """Press Enter to start, press Enter again to stop. Returns float32 mono @ 16 kHz."""
    print()
    input("Press Enter to start your turn (empty recording = exit)...")
    print("🎙️  Recording — press Enter again to stop.")

    chunks: list[np.ndarray] = []

    def _cb(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        chunks.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=_cb)
    with stream:
        input()  # blocks the main thread until user presses Enter again

    if not chunks:
        return np.empty((0,), dtype=np.float32)
    return np.concatenate(chunks, axis=0).flatten()


async def transcribe_recording(stt: STTService, rec: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sf.write(str(tmp_path), rec, SAMPLE_RATE, subtype="PCM_16")
        return await stt.transcribe(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


async def conversation_loop(llm: OllamaClient) -> int:
    stt = STTService()
    tutor = Tutor(llm, system_prompt=SYSTEM_PROMPT)

    print("=== Voice chat with German tutor ===")
    print("Hold a multi-turn conversation. Empty recording or Ctrl+C exits.")

    while True:
        rec = record_press_to_stop()
        duration_s = len(rec) / SAMPLE_RATE

        if duration_s < MIN_RECORDING_SECONDS:
            print("\nAuf Wiedersehen!")
            return 0

        if np.abs(rec).max() < SILENCE_THRESHOLD:
            print(
                "Silent recording (~0). macOS may have denied mic permission to "
                "the terminal. Check System Settings → Privacy & Security → "
                "Microphone, then try again."
            )
            continue

        print(f"  (recorded {duration_s:.1f}s)  Transcribing...")
        transcript = await transcribe_recording(stt, rec)

        if not transcript:
            print("  Empty transcript — try again.")
            continue

        print(f"\nYou: {transcript}")
        print("Tutor: ", end="", flush=True)
        async for chunk in tutor.respond_stream(transcript):
            print(chunk, end="", flush=True)
        print()


async def main() -> int:
    if probe_ffmpeg() != 0:
        return 1
    if probe_microphone() != 0:
        return 1

    print("Loading Whisper model (first call may take 10-30s on cold start)...")

    try:
        async with OllamaClient() as llm:
            return await conversation_loop(llm)
    except LLMConnectionError as exc:
        print(f"\nCould not reach Ollama: {exc}", file=sys.stderr)
        print("Hint: is the Ollama daemon running? Try `ollama serve`.", file=sys.stderr)
        return 1
    except LLMModelNotFoundError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAuf Wiedersehen!")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
