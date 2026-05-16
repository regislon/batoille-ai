"""Public exceptions for the audio adapters (STT, TTS).

Exceptions live here so `core/` can `from batoiller.audio.models import STTError`
without transitively importing `mlx_whisper` / `piper` (heavy at import time).
"""


class STTError(Exception):
    """Base class for any error raised by the STT adapter."""


class TTSError(Exception):
    """Base class for any error raised by the TTS adapter."""
