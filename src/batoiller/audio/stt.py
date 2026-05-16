"""Async wrapper around `mlx-whisper` for speech-to-text.

The ONLY module in batoiller that imports `mlx_whisper`. Apple-Silicon only.
Callers talk to `STTService` and the types in `batoiller.audio.models`.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import mlx_whisper

_DEFAULT_MODEL = "mlx-community/whisper-turbo"


class STTService:
    """Transcribe audio to text using a local Whisper model on Apple Silicon.

    Sequential calls only. Concurrent calls are not supported and may corrupt
    Metal state (mlx-whisper internals). Brick 8 (Gradio) will need a lock
    when multiple users could hit the service at once.
    """

    def __init__(self, model: str | None = None, language: str | None = None) -> None:
        self._model = (
            model if model is not None else os.environ.get("BATOILLER_STT_MODEL", _DEFAULT_MODEL)
        )
        self._language = (
            language if language is not None else os.environ.get("BATOILLER_STT_LANGUAGE")
        )

    @property
    def model(self) -> str:
        return self._model

    async def transcribe(self, audio: str | Path | bytes) -> str:
        """Transcribe audio to text.

        Args:
            audio: path-like (str or Path), OR encoded audio file bytes
                (wav/mp3/m4a/... — decoded by ffmpeg). NOT raw PCM samples.

        Returns:
            Recognized text, stripped of leading/trailing whitespace.

        Raises:
            ValueError: if audio bytes are empty.
            FileNotFoundError, RuntimeError, etc.: from the backend on failure.
        """
        if isinstance(audio, bytes):
            if not audio:
                raise ValueError("audio bytes must not be empty")
            # Suffix .audio (not .wav) — ffmpeg sniffs format from content,
            # so a .wav suffix would lie if the caller passed mp3/m4a bytes.
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                tmp.write(audio)
                tmp_path = tmp.name
            try:
                result = await self._invoke(tmp_path)
            finally:
                # Cleanup MUST run on exception paths too.
                Path(tmp_path).unlink(missing_ok=True)
        else:
            result = await self._invoke(str(audio))

        text = result.get("text", "")
        return text.strip() if isinstance(text, str) else ""

    async def _invoke(self, audio_path: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"path_or_hf_repo": self._model}
        # Only pass language= when set; whisper auto-detects when the kwarg is absent.
        if self._language is not None:
            kwargs["language"] = self._language
        return await asyncio.to_thread(mlx_whisper.transcribe, audio_path, **kwargs)
