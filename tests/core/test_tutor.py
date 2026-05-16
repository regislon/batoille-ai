"""Unit tests for Tutor. OllamaClient is mocked — no Ollama daemon needed."""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from batoiller.core import Tutor
from batoiller.llm import ChatResponse, Message


def _response(text: str = "Hallo!") -> ChatResponse:
    return ChatResponse(
        model="mistral-small",
        message=Message(role="assistant", content=text),
        eval_count=10,
        total_duration_ns=1_000_000,
    )


async def _stream(*chunks: str) -> AsyncIterator[str]:
    for c in chunks:
        yield c


def _mock_client_with_chat(*responses: ChatResponse) -> MagicMock:
    client = MagicMock()
    if len(responses) == 1:
        client.chat = AsyncMock(return_value=responses[0])
    else:
        client.chat = AsyncMock(side_effect=list(responses))
    return client


async def test_respond_returns_assistant_text() -> None:
    client = _mock_client_with_chat(_response("Guten Tag!"))
    tutor = Tutor(client, system_prompt="Du bist ein Lehrer.")

    result = await tutor.respond("Hallo!")

    assert result == "Guten Tag!"
    client.chat.assert_awaited_once()


async def test_first_call_sends_system_plus_user() -> None:
    client = _mock_client_with_chat(_response())
    tutor = Tutor(client, system_prompt="Du bist ein Lehrer.")

    await tutor.respond("Hallo!")

    sent: list[Message] = client.chat.call_args.args[0]
    assert [m.role for m in sent] == ["system", "user"]
    assert sent[0].content == "Du bist ein Lehrer."
    assert sent[1].content == "Hallo!"


async def test_history_grows_across_turns() -> None:
    client = _mock_client_with_chat(_response("Erste Antwort"), _response("Zweite Antwort"))
    tutor = Tutor(client, system_prompt="Sys")

    await tutor.respond("Erste Frage")
    await tutor.respond("Zweite Frage")

    second_call: list[Message] = client.chat.call_args_list[1].args[0]
    assert [m.role for m in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[2].content == "Erste Antwort"
    assert second_call[3].content == "Zweite Frage"


async def test_reset_clears_history_keeps_system() -> None:
    client = _mock_client_with_chat(_response("OK"), _response("Fresh"))
    tutor = Tutor(client, system_prompt="Sys")

    await tutor.respond("First")
    tutor.reset()
    await tutor.respond("After reset")

    last_call: list[Message] = client.chat.call_args_list[-1].args[0]
    assert [m.role for m in last_call] == ["system", "user"]
    assert last_call[1].content == "After reset"


async def test_respond_failure_drops_orphan_user_message() -> None:
    client = MagicMock()
    client.chat = AsyncMock(side_effect=RuntimeError("boom"))
    tutor = Tutor(client, system_prompt="Sys")

    with pytest.raises(RuntimeError, match="boom"):
        await tutor.respond("Will fail")

    assert tutor.history == []


async def test_respond_stream_yields_and_records() -> None:
    client = MagicMock()
    client.chat_stream = MagicMock(return_value=_stream("Hal", "lo", "!"))
    tutor = Tutor(client, system_prompt="Sys")

    output: list[str] = []
    async for chunk in tutor.respond_stream("Hi"):
        output.append(chunk)

    assert output == ["Hal", "lo", "!"]
    assert tutor.history[-2].content == "Hi"
    assert tutor.history[-1].content == "Hallo!"
    assert tutor.history[-1].role == "assistant"


async def test_respond_stream_interrupted_clears_user_message() -> None:
    """Interrupted streams leave history clean: both user msg and partial
    assistant text are dropped. Consumer must explicitly close the generator
    (or fully consume it) for cleanup to be deterministic."""
    client = MagicMock()
    client.chat_stream = MagicMock(return_value=_stream("Hal", "lo", "!"))
    tutor = Tutor(client, system_prompt="Sys")

    gen = cast(AsyncGenerator[str, None], tutor.respond_stream("Hi"))
    first_chunk = await gen.__anext__()
    await gen.aclose()

    assert first_chunk == "Hal"
    assert tutor.history == []


async def test_respond_stream_no_chunks_drops_orphan_user_message() -> None:
    client = MagicMock()
    client.chat_stream = MagicMock(return_value=_stream())
    tutor = Tutor(client, system_prompt="Sys")

    async for _ in tutor.respond_stream("Will get nothing"):
        pass

    assert tutor.history == []


def test_history_property_returns_a_copy() -> None:
    client = _mock_client_with_chat(_response())
    tutor = Tutor(client, system_prompt="Sys")

    snapshot = tutor.history
    snapshot.append(Message(role="user", content="injected"))

    assert tutor.history == []


async def test_core_does_not_import_ui() -> None:
    """Architecture rule: core never imports UI."""
    import sys

    import batoiller.core  # noqa: F401

    for module in ("gradio", "streamlit", "fastapi", "flask"):
        assert module not in sys.modules, f"core unexpectedly imports {module}"
