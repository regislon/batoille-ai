"""Unit tests for STTService. mlx_whisper.transcribe is mocked — the fixture
file path only needs to exist (its contents are never read).
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from batoiller.audio import STTService


@pytest.fixture
def fake_audio_path(tmp_path: Path) -> Path:
    p = tmp_path / "x.wav"
    p.write_bytes(b"\x00")
    return p


@pytest.fixture
def mock_transcribe(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value={"text": "Hallo Welt", "segments": [], "language": "de"})
    monkeypatch.setattr("batoiller.audio.stt.mlx_whisper.transcribe", mock)
    return mock


async def test_transcribe_str_path(fake_audio_path: Path, mock_transcribe: MagicMock) -> None:
    stt = STTService(model="custom-model")
    result = await stt.transcribe(str(fake_audio_path))
    assert result == "Hallo Welt"
    args, kwargs = mock_transcribe.call_args
    assert args[0] == str(fake_audio_path)
    assert kwargs["path_or_hf_repo"] == "custom-model"


async def test_transcribe_pathlib_path(fake_audio_path: Path, mock_transcribe: MagicMock) -> None:
    stt = STTService()
    result = await stt.transcribe(fake_audio_path)
    assert result == "Hallo Welt"
    # os.PathLike must be normalized to str before passing to whisper
    args, _ = mock_transcribe.call_args
    assert args[0] == str(fake_audio_path)
    assert isinstance(args[0], str)


async def test_transcribe_bytes_writes_and_cleans_temp(mock_transcribe: MagicMock) -> None:
    captured_path: dict[str, str] = {}

    def _capture_then_check(audio_path: str, **_: Any) -> dict[str, Any]:
        # During the call, the temp file must exist with our bytes.
        captured_path["path"] = audio_path
        assert Path(audio_path).exists()
        assert Path(audio_path).read_bytes() == b"FAKE-AUDIO"
        return {"text": "from bytes", "segments": [], "language": "de"}

    mock_transcribe.side_effect = _capture_then_check
    stt = STTService()
    result = await stt.transcribe(b"FAKE-AUDIO")

    assert result == "from bytes"
    # After the call, the temp file must be gone.
    assert not Path(captured_path["path"]).exists()


async def test_temp_file_cleaned_up_on_exception(mock_transcribe: MagicMock) -> None:
    captured_path: dict[str, str] = {}

    def _capture_then_raise(audio_path: str, **_: Any) -> dict[str, Any]:
        captured_path["path"] = audio_path
        raise RuntimeError("whisper exploded")

    mock_transcribe.side_effect = _capture_then_raise
    stt = STTService()
    with pytest.raises(RuntimeError, match="whisper exploded"):
        await stt.transcribe(b"AUDIO")
    assert not Path(captured_path["path"]).exists()


async def test_empty_bytes_raises_value_error(mock_transcribe: MagicMock) -> None:
    stt = STTService()
    with pytest.raises(ValueError, match="must not be empty"):
        await stt.transcribe(b"")
    mock_transcribe.assert_not_called()


async def test_whitespace_stripped(fake_audio_path: Path, mock_transcribe: MagicMock) -> None:
    mock_transcribe.return_value = {"text": "  spaced \n", "segments": [], "language": "de"}
    stt = STTService()
    result = await stt.transcribe(fake_audio_path)
    assert result == "spaced"


async def test_default_model_from_env(
    fake_audio_path: Path,
    mock_transcribe: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BATOILLER_STT_MODEL", "from-env-model")
    stt = STTService()
    assert stt.model == "from-env-model"
    await stt.transcribe(fake_audio_path)
    _, kwargs = mock_transcribe.call_args
    assert kwargs["path_or_hf_repo"] == "from-env-model"


async def test_language_none_omits_kwarg(fake_audio_path: Path, mock_transcribe: MagicMock) -> None:
    stt = STTService()
    await stt.transcribe(fake_audio_path)
    _, kwargs = mock_transcribe.call_args
    # Critical: omit the kwarg entirely, don't pass language=None.
    assert "language" not in kwargs


async def test_language_set_is_forwarded(fake_audio_path: Path, mock_transcribe: MagicMock) -> None:
    stt = STTService(language="de")
    await stt.transcribe(fake_audio_path)
    _, kwargs = mock_transcribe.call_args
    assert kwargs["language"] == "de"
