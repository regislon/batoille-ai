"""Live smoke test for STTService against the real Whisper model + real mic.

Run with:
    uv run python scripts/check_stt.py

Requires:
    - Apple Silicon Mac
    - ffmpeg in PATH (`brew install ffmpeg`)
    - Microphone permission granted to the terminal
    - First run will auto-download the Whisper model (~1.5 GB for turbo)
    - Optional: Ollama daemon running with mistral-small pulled, to chain
      the transcript into a German tutor reply

Press Enter to start recording. Speak in German. Press Enter again to stop.
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
from batoiller.llm import LLMConnectionError, LLMModelNotFoundError, Message, OllamaClient

SAMPLE_RATE = 16000
MIN_RECORDING_SECONDS = 0.5
SILENCE_THRESHOLD = 1e-4

SYSTEM_PROMPT = (
    "Du bist ein freundlicher Deutschlehrer für französischsprachige Lerner. "
    "Antworte immer auf Deutsch, mit einfachen Sätzen."
)


def probe_ffmpeg() -> int:
    print("=== Step 1: ffmpeg ===")
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH.", file=sys.stderr)
        print("Hint: `brew install ffmpeg`", file=sys.stderr)
        return 1
    print("OK\n")
    return 0


def probe_microphone() -> int:
    print("=== Step 2: Microphone ===")
    try:
        devices = sd.query_devices(kind="input")
    except sd.PortAudioError as exc:
        print(f"No usable input device: {exc}", file=sys.stderr)
        print(
            "Hint: check System Settings → Privacy & Security → Microphone, "
            "and grant access to your terminal.",
            file=sys.stderr,
        )
        return 1
    print(f"Default input: {devices['name']}\n")
    return 0


def record_press_to_stop() -> np.ndarray:
    """Press Enter to start, press Enter again to stop. Returns float32 mono @ 16 kHz."""
    input("Press Enter to start recording...")
    print("🎙️  Recording — press Enter again to stop.")

    chunks: list[np.ndarray] = []

    def _cb(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        # blocking; ok in scripts, must be to_thread'd from async handlers
        chunks.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=_cb)
    with stream:
        input()  # blocks the main thread until user presses Enter again

    if not chunks:
        return np.empty((0,), dtype=np.float32)
    return np.concatenate(chunks, axis=0).flatten()


async def main() -> int:
    if probe_ffmpeg() != 0:
        return 1
    if probe_microphone() != 0:
        return 1

    print("=== Step 3: Record + transcribe ===")
    print("Loading Whisper model (first call may take 10-30s on cold start)...")
    rec = record_press_to_stop()

    duration_s = len(rec) / SAMPLE_RATE
    print(f"✓ Recorded {duration_s:.1f}s")

    if duration_s < MIN_RECORDING_SECONDS:
        print(
            f"Recording too short ({duration_s:.1f}s). "
            "Speak for at least a sentence and try again.",
            file=sys.stderr,
        )
        return 1

    if np.abs(rec).max() < SILENCE_THRESHOLD:
        print(
            "Recording is silent. macOS may have returned zeros because the "
            "terminal doesn't have mic permission. Check System Settings → "
            "Privacy & Security → Microphone.",
            file=sys.stderr,
        )
        return 1

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sf.write(str(tmp_path), rec, SAMPLE_RATE, subtype="PCM_16")
        print("Transcribing...")
        stt = STTService()
        transcript = await stt.transcribe(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    print(f"\nTranscript: {transcript!r}\n")

    if not transcript:
        print("Empty transcript — skipping LLM chat.")
        return 0

    print("=== Step 4: Optional — send transcript to Mistral ===")
    try:
        async with OllamaClient() as llm:
            response = await llm.chat(
                [
                    Message(role="system", content=SYSTEM_PROMPT),
                    Message(role="user", content=transcript),
                ]
            )
            print(f"Mistral: {response.content}")
    except LLMConnectionError as exc:
        print(f"Skipped LLM chat: {exc}", file=sys.stderr)
        print("Hint: is the Ollama daemon running? Try `ollama serve`.", file=sys.stderr)
        return 0  # STT itself worked; LLM is optional here
    except LLMModelNotFoundError as exc:
        print(f"Skipped LLM chat: {exc}", file=sys.stderr)
        return 0

    print("\nAll checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
