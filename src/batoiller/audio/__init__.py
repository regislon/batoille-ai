"""Audio adapters — STT (brick 2 ✅), TTS (brick 4 ✅). Apple Silicon.

VAD lives in post-v0.4.0 exploration: push-to-talk in Gradio (brick 7)
is the chosen turn-taking strategy.
"""

from batoiller.audio.models import STTError, TTSError
from batoiller.audio.stt import STTService
from batoiller.audio.tts import TTSService

__all__ = ["STTError", "STTService", "TTSError", "TTSService"]
