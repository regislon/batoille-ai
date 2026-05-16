"""Public exceptions for the audio adapters (STT now; TTS in a later brick).

Exceptions live here so `core/` can `from batoiller.audio.models import STTError`
without transitively importing `mlx_whisper` (which is Apple-Silicon-only and
heavy at import time).
"""


class STTError(Exception):
    """Base class for any error raised by the STT adapter."""
