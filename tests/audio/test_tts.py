"""Unit tests for TTSService. Piper and audio playback are mocked — no
voice download, no real audio, no real synthesis. Live verification
lives in scripts/check_tts.py.
"""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from batoiller.audio import TTSError, TTSService


def _fake_chunk(audio: bytes = b"\x01\x02\x03\x04", sample_rate: int = 22050) -> MagicMock:
    chunk = MagicMock()
    chunk.audio_int16_bytes = audio
    chunk.sample_rate = sample_rate
    return chunk


@pytest.fixture
def voice_dir(tmp_path: Path) -> Path:
    """A directory where the voice files already 'exist' (empty placeholders)."""
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    (voice_dir / "de_DE-thorsten-high.onnx").write_bytes(b"\x00")
    (voice_dir / "de_DE-thorsten-high.onnx.json").write_text("{}")
    return voice_dir


@pytest.fixture
def mock_piper(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    """Patch PiperVoice.load to return a mock voice; mock voice.synthesize yields chunks."""
    mock_voice = MagicMock()
    mock_voice.synthesize.side_effect = lambda text, *a, **kw: iter([_fake_chunk()])
    mock_load = MagicMock(return_value=mock_voice)
    monkeypatch.setattr("batoiller.audio.tts.PiperVoice.load", mock_load)
    return mock_load, mock_voice


@pytest.fixture
def mock_play(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    play = MagicMock()
    wait = MagicMock()
    monkeypatch.setattr("batoiller.audio.tts.sd.play", play)
    monkeypatch.setattr("batoiller.audio.tts.sd.wait", wait)
    return play, wait


async def test_synthesize_returns_bytes_and_sample_rate(
    voice_dir: Path, mock_piper: tuple[MagicMock, MagicMock]
) -> None:
    tts = TTSService(voice_dir=voice_dir)
    audio, sr = await tts.synthesize("Hallo Welt")
    assert isinstance(audio, bytes)
    assert audio == b"\x01\x02\x03\x04"
    assert sr == 22050


async def test_synthesize_concatenates_multiple_chunks(
    voice_dir: Path, mock_piper: tuple[MagicMock, MagicMock]
) -> None:
    _, mock_voice = mock_piper
    mock_voice.synthesize.side_effect = lambda text, *a, **kw: iter(
        [_fake_chunk(b"AB"), _fake_chunk(b"CD"), _fake_chunk(b"EF")]
    )
    tts = TTSService(voice_dir=voice_dir)
    audio, _ = await tts.synthesize("multi-sentence text")
    assert audio == b"ABCDEF"


async def test_speak_plays_audio(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_play: tuple[MagicMock, MagicMock],
) -> None:
    tts = TTSService(voice_dir=voice_dir)
    await tts.speak("Hallo")
    play, wait = mock_play
    play.assert_called_once()
    wait.assert_called_once()
    call_kwargs = play.call_args.kwargs
    assert call_kwargs["samplerate"] == 22050


async def test_voice_loaded_once_across_calls(
    voice_dir: Path, mock_piper: tuple[MagicMock, MagicMock]
) -> None:
    tts = TTSService(voice_dir=voice_dir)
    await tts.synthesize("First")
    await tts.synthesize("Second")
    mock_load, _ = mock_piper
    assert mock_load.call_count == 1


async def test_empty_text_raises_value_error(
    voice_dir: Path, mock_piper: tuple[MagicMock, MagicMock]
) -> None:
    tts = TTSService(voice_dir=voice_dir)
    with pytest.raises(ValueError, match="must not be empty"):
        await tts.synthesize("   \n")


async def test_default_voice_from_env(
    voice_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_piper: tuple[MagicMock, MagicMock],
) -> None:
    monkeypatch.setenv("BATOILLER_TTS_VOICE", "de_DE-something-else")
    # Make the env-named voice file also exist
    (voice_dir / "de_DE-something-else.onnx").write_bytes(b"\x00")
    (voice_dir / "de_DE-something-else.onnx.json").write_text("{}")
    tts = TTSService(voice_dir=voice_dir)
    assert tts.voice == "de_DE-something-else"
    await tts.synthesize("Hi")


async def test_missing_voice_triggers_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_piper: tuple[MagicMock, MagicMock],
) -> None:
    voice_dir = tmp_path / "empty"
    download_calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        download_calls.append(cmd)
        # Pretend the download worked by creating the files
        voice_dir.mkdir(parents=True, exist_ok=True)
        (voice_dir / "de_DE-thorsten-high.onnx").write_bytes(b"\x00")
        (voice_dir / "de_DE-thorsten-high.onnx.json").write_text("{}")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("batoiller.audio.tts.subprocess.run", fake_run)

    tts = TTSService(voice_dir=voice_dir)
    await tts.synthesize("Hi")

    assert len(download_calls) == 1
    cmd = download_calls[0]
    assert "piper.download_voices" in " ".join(cmd)
    assert "de_DE-thorsten-high" in cmd
    assert str(voice_dir) in cmd


async def test_download_failure_raises_tts_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_piper: tuple[MagicMock, MagicMock],
) -> None:
    voice_dir = tmp_path / "empty"

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="404 Not Found")

    monkeypatch.setattr("batoiller.audio.tts.subprocess.run", fake_run)

    tts = TTSService(voice_dir=voice_dir)
    with pytest.raises(TTSError, match="Voice download failed"):
        await tts.synthesize("Hi")


async def test_zero_chunks_raises_tts_error(
    voice_dir: Path, mock_piper: tuple[MagicMock, MagicMock]
) -> None:
    _, mock_voice = mock_piper
    mock_voice.synthesize.side_effect = lambda text, *a, **kw: iter([])
    tts = TTSService(voice_dir=voice_dir)
    with pytest.raises(TTSError, match="produced no audio"):
        await tts.synthesize("Hello")


async def test_preload_loads_voice_without_synthesizing(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
) -> None:
    tts = TTSService(voice_dir=voice_dir)
    await tts.preload()
    mock_load, mock_voice = mock_piper
    mock_load.assert_called_once()
    mock_voice.synthesize.assert_not_called()
