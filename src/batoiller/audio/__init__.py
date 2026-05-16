"""Audio adapters — STT (brick 2 ✅), VAD (brick 4), TTS (brick 5). Apple Silicon only."""

from batoiller.audio.models import STTError
from batoiller.audio.stt import STTService

__all__ = ["STTError", "STTService"]
