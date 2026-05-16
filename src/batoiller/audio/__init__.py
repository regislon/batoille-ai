"""Audio adapters — STT now (brick 2), TTS later (brick 11). Apple Silicon only."""

from batoiller.audio.models import STTError
from batoiller.audio.stt import STTService

__all__ = ["STTError", "STTService"]
