"""Unit tests for TTSService. Piper and audio playback are mocked — no
voice download, no real audio, no real synthesis. Live verification
lives in scripts/check_tts.py.
"""

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from batoiller.audio import TTSError, TTSService
from batoiller.audio.tts import _pop_sentence


async def _async_iter(*chunks: str) -> AsyncIterator[str]:
    for c in chunks:
        yield c


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


@pytest.fixture
def mock_output_stream(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock `sd.OutputStream` as a class. All instances created during a test
    share the returned MagicMock, so `instance.write.call_count` reflects
    every write across the consumer's lifetime.
    """
    instance = MagicMock()
    instance.samplerate = 22050
    factory = MagicMock(return_value=instance)
    monkeypatch.setattr("batoiller.audio.tts.sd.OutputStream", factory)
    return instance


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


# ---------------------------------------------------------------------------
# Sentence-buffer unit tests
# ---------------------------------------------------------------------------


def test_pop_sentence_happy_path() -> None:
    sentence, remainder = _pop_sentence("Das ist die erste Sentenz. Wie geht es dir heute?")
    assert sentence == "Das ist die erste Sentenz. "
    sentence2, remainder2 = _pop_sentence(remainder)
    assert sentence2 == "Wie geht es dir heute?"
    assert remainder2 == ""


def test_pop_sentence_skips_too_short_dot_prefix() -> None:
    # "Kurz." is only 5 chars — does NOT qualify on length. The function
    # should return None rather than emit a short fragment.
    sentence, remainder = _pop_sentence("Kurz.")
    assert sentence is None
    assert remainder == "Kurz."


def test_pop_sentence_short_prefix_dodges_abbreviation() -> None:
    # First period after "z.B." is followed by space, but the prefix is too
    # short to qualify; the function should find the LATER period instead.
    sentence, remainder = _pop_sentence("Das ist z.B. wichtig. Klar?")
    assert sentence == "Das ist z.B. wichtig. "
    assert remainder == "Klar?"


def test_pop_sentence_question_mark_qualifies_regardless_of_length() -> None:
    # `?` is unambiguous — qualify even for a 2-char prefix.
    sentence, remainder = _pop_sentence("Ja? Mehr Text.")
    assert sentence == "Ja? "
    assert remainder == "Mehr Text."


def test_pop_sentence_no_boundary() -> None:
    sentence, remainder = _pop_sentence("unterminated text")
    assert sentence is None
    assert remainder == "unterminated text"


# ---------------------------------------------------------------------------
# speak_stream tests
# ---------------------------------------------------------------------------


async def test_speak_stream_three_sentences_three_writes(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """Three qualifying sentences → three OutputStream.write calls on a
    single, persistent OutputStream (no per-sentence device open/close)."""
    tts = TTSService(voice_dir=voice_dir)
    full = await tts.speak_stream(
        _async_iter(
            "Erste Sentenz hier. ",
            "Zweite Sentenz hier! ",
            "Dritte Sentenz hier?",
        )
    )
    assert full == "Erste Sentenz hier. Zweite Sentenz hier! Dritte Sentenz hier?"
    assert mock_output_stream.write.call_count == 3
    # Single stream opened, started, stopped, closed — this is the click fix.
    mock_output_stream.start.assert_called_once()
    mock_output_stream.stop.assert_called_once()
    mock_output_stream.close.assert_called_once()


async def test_speak_stream_unterminated_single_chunk_flushes(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """A stream that ends without a sentence boundary still writes once."""
    tts = TTSService(voice_dir=voice_dir)
    full = await tts.speak_stream(_async_iter("unterminated fragment"))
    assert full == "unterminated fragment"
    mock_output_stream.write.assert_called_once()


async def test_speak_stream_empty_stream_makes_no_calls(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    _, mock_voice = mock_piper
    tts = TTSService(voice_dir=voice_dir)
    full = await tts.speak_stream(_async_iter())
    assert full == ""
    mock_output_stream.write.assert_not_called()
    # No audio means we never opened the device either.
    mock_output_stream.start.assert_not_called()
    mock_voice.synthesize.assert_not_called()


async def test_speak_stream_on_text_called_per_chunk(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    received: list[str] = []
    tts = TTSService(voice_dir=voice_dir)
    await tts.speak_stream(
        _async_iter("Ha", "llo", " Welt."),
        on_text=lambda c: received.append(c),
    )
    assert received == ["Ha", "llo", " Welt."]


async def test_speak_stream_abbreviation_regression(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """'z.B.' inside a sentence must not split it. Two real sentences → two writes."""
    tts = TTSService(voice_dir=voice_dir)
    await tts.speak_stream(_async_iter("Das ist z.B. wichtig. Wirklich!"))
    assert mock_output_stream.write.call_count == 2


async def test_speak_stream_prepends_silence_to_each_chunk(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """Each written buffer starts with silence — covers device warmup for the
    first chunk, adds natural inter-sentence pause for the rest. Without this,
    OutputStream's back-to-back writes sound rushed and clip the first phoneme.
    """
    tts = TTSService(voice_dir=voice_dir)
    await tts.speak_stream(_async_iter("Eine ganz lange Sentenz hier."))

    # mock_piper's _fake_chunk produces 4 bytes of "audio" = 2 int16 frames.
    written = mock_output_stream.write.call_args_list[0].args[0]
    assert written[0] == 0, "Each chunk must start with silence (device warmup)"
    assert len(written) > 2, (
        f"Expected silence-padded array longer than the 2-frame raw audio, "
        f"got len={len(written)}"
    )


async def test_speak_stream_first_chunk_silence_is_shorter(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """First chunk gets only a brief warmup; subsequent chunks get the full
    inter-sentence pause. This is the trade-off that minimises time-to-first-
    audio while still giving natural breathing room between sentences."""
    tts = TTSService(voice_dir=voice_dir)
    await tts.speak_stream(
        _async_iter("Erste Sentenz hier lang. ", "Zweite Sentenz hier lang!")
    )

    def leading_zero_count(arr: Any) -> int:
        n = 0
        for v in arr:
            if v != 0:
                break
            n += 1
        return n

    first_silence = leading_zero_count(mock_output_stream.write.call_args_list[0].args[0])
    second_silence = leading_zero_count(mock_output_stream.write.call_args_list[1].args[0])
    # Both have leading silence; the second has strictly more.
    assert 0 < first_silence < second_silence, (
        f"Expected first ({first_silence}) < second ({second_silence}) silence frames"
    )


async def test_play_cancellable_calls_sd_stop_on_cancellation(
    voice_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The _play_cancellable wrapper calls sd.stop() when its await is
    cancelled mid-playback. Without this, sd.wait() would block the
    worker thread indefinitely after a Ctrl+C.

    Tested as a focused unit — going through a full speak_stream task
    with real cancellation timing is flaky in CI.
    """
    stop = MagicMock()
    monkeypatch.setattr("batoiller.audio.tts.sd.stop", stop)

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        # Simulate cancellation arriving while the worker is "playing".
        raise asyncio.CancelledError("simulated mid-playback cancel")

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    tts = TTSService(voice_dir=voice_dir)
    with pytest.raises(asyncio.CancelledError):
        await tts._play_cancellable(b"audio", 22050)

    stop.assert_called_once()


async def test_speak_stream_producer_exception_cancels_consumer(
    voice_dir: Path,
    mock_piper: tuple[MagicMock, MagicMock],
    mock_output_stream: MagicMock,
) -> None:
    """If synthesis raises on the second sentence, the whole speak_stream
    raises and the second write is never invoked."""
    _, mock_voice = mock_piper
    call_count = {"n": 0}

    def _synth(text: str, *a: Any, **kw: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("piper exploded mid-stream")
        chunk = MagicMock()
        # b"\x01\x02" — 2 bytes, evenly divisible into one int16 frame.
        chunk.audio_int16_bytes = b"\x01\x02"
        chunk.sample_rate = 22050
        return iter([chunk])

    mock_voice.synthesize.side_effect = _synth

    tts = TTSService(voice_dir=voice_dir)
    with pytest.raises(ExceptionGroup) as exc_info:
        await tts.speak_stream(_async_iter("Das ist die erste Sentenz. Das ist die zweite!"))
    flat = exc_info.value.exceptions
    assert any(isinstance(e, RuntimeError) for e in flat)

    # Only the first sentence's audio reached the consumer before the
    # producer's RuntimeError cancelled it.
    assert mock_output_stream.write.call_count <= 1


async def test_stream_write_cancellable_calls_abort_on_cancellation(
    voice_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The _stream_write_cancellable wrapper calls stream.abort() when
    its await is cancelled mid-write — the OutputStream-side analogue
    of _play_cancellable / sd.stop()."""
    mock_stream = MagicMock()

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        raise asyncio.CancelledError("simulated mid-write cancel")

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    tts = TTSService(voice_dir=voice_dir)
    import numpy as np

    with pytest.raises(asyncio.CancelledError):
        await tts._stream_write_cancellable(mock_stream, np.array([0], dtype=np.int16))

    mock_stream.abort.assert_called_once()
