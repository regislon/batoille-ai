"""Audio adapters — STT (brick 2 ✅), TTS (brick 4). Apple Silicon only.

VAD lives in post-v0.4.0 exploration: push-to-talk in Gradio (brick 7)
is the chosen turn-taking strategy.
"""

from batoiller.audio.models import STTError
from batoiller.audio.stt import STTService

__all__ = ["STTError", "STTService"]
