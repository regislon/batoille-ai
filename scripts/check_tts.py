"""Live smoke test for TTSService against the real Piper voice.

Run with:
    uv run python scripts/check_tts.py

Requires:
    - Apple Silicon Mac
    - No ffmpeg required (unlike STT)
    - First run will auto-download `de_DE-thorsten-high` (~114 MB)
      into ~/.batoiller/voices/

Synthesizes one German sentence, plays it through the default audio
output, exits.
"""

import asyncio
import sys

import sounddevice as sd

from batoiller.audio import TTSError, TTSService

GREETING = (
    "Hallo! Ich bin dein Deutschlehrer und ich werde dir helfen, die deutsche Sprache zu lernen."
)


def probe_output_device() -> int:
    print("=== Step 1: Audio output device ===")
    try:
        devices = sd.query_devices(kind="output")
    except sd.PortAudioError as exc:
        print(f"No usable output device: {exc}", file=sys.stderr)
        return 1
    print(f"Default output: {devices['name']}\n")
    return 0


async def main() -> int:
    if probe_output_device() != 0:
        return 1

    print("=== Step 2: Synthesize + play ===")
    tts = TTSService()
    print(f"Voice: {tts.voice}")

    try:
        print(f"Speaking: {GREETING!r}")
        await tts.speak(GREETING)
    except TTSError as exc:
        print(f"TTS failed: {exc}", file=sys.stderr)
        return 1

    print("\nAll checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
