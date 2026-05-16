"""Unit tests for OllamaClient. Network calls are mocked — these tests do not
require an Ollama daemon. Live verification lives in scripts/check_ollama_client.py.
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import ollama
import pytest

from batoiller.llm import (
    ChatResponse,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMResponseError,
    Message,
    OllamaClient,
)


def _ollama_response(content: str = "Hallo!", model: str = "mistral-small") -> ollama.ChatResponse:
    return ollama.ChatResponse(
        model=model,
        message=ollama.Message(role="assistant", content=content),
        done=True,
        done_reason="stop",
        eval_count=42,
        total_duration=123_000_000,
    )


async def _async_chunks(*chunks: ollama.ChatResponse) -> AsyncIterator[ollama.ChatResponse]:
    for c in chunks:
        yield c


class _MockAsyncClient:
    def __init__(self, host: str | None = None, timeout: float | None = None) -> None:
        self.host = host
        self.timeout = timeout
        self.chat = AsyncMock()
        self.close = AsyncMock()


@pytest.fixture
def mock_async_client(monkeypatch: pytest.MonkeyPatch) -> list[_MockAsyncClient]:
    instances: list[_MockAsyncClient] = []

    def factory(
        host: str | None = None, timeout: float | None = None, **_: Any
    ) -> _MockAsyncClient:
        inst = _MockAsyncClient(host=host, timeout=timeout)
        instances.append(inst)
        return inst

    monkeypatch.setattr("batoiller.llm.ollama_client.ollama.AsyncClient", factory)
    return instances


async def test_chat_happy_path(mock_async_client: list[_MockAsyncClient]) -> None:
    client = OllamaClient(model="mistral-small")
    mock = mock_async_client[0]
    mock.chat.return_value = _ollama_response("Guten Tag!")

    response = await client.chat([Message(role="user", content="Hallo")])

    assert isinstance(response, ChatResponse)
    assert response.message.role == "assistant"
    assert response.message.content == "Guten Tag!"
    assert response.content == "Guten Tag!"
    assert response.model == "mistral-small"
    assert response.eval_count == 42
    assert response.total_duration_ns == 123_000_000

    mock.chat.assert_awaited_once()
    call_kwargs = mock.chat.call_args.kwargs
    assert call_kwargs["model"] == "mistral-small"
    assert call_kwargs["stream"] is False
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hallo"}]


async def test_chat_stream_happy_path(mock_async_client: list[_MockAsyncClient]) -> None:
    client = OllamaClient(model="mistral-small")
    mock = mock_async_client[0]
    mock.chat.return_value = _async_chunks(
        _ollama_response("Hal"),
        _ollama_response("lo"),
        _ollama_response("!"),
    )

    output: list[str] = []
    async for piece in client.chat_stream([Message(role="user", content="Hi")]):
        output.append(piece)

    assert output == ["Hal", "lo", "!"]
    call_kwargs = mock.chat.call_args.kwargs
    assert call_kwargs["stream"] is True


async def test_chat_translates_connection_error(mock_async_client: list[_MockAsyncClient]) -> None:
    client = OllamaClient()
    mock = mock_async_client[0]
    mock.chat.side_effect = ConnectionError("connection refused")

    with pytest.raises(LLMConnectionError) as exc_info:
        await client.chat([Message(role="user", content="Hallo")])

    assert isinstance(exc_info.value.__cause__, ConnectionError)


async def test_chat_translates_model_not_found(mock_async_client: list[_MockAsyncClient]) -> None:
    client = OllamaClient(model="nonexistent")
    mock = mock_async_client[0]
    mock.chat.side_effect = ollama.ResponseError("model not found", 404)

    with pytest.raises(LLMModelNotFoundError) as exc_info:
        await client.chat([Message(role="user", content="Hallo")])

    assert exc_info.value.model == "nonexistent"


async def test_chat_translates_other_response_error(
    mock_async_client: list[_MockAsyncClient],
) -> None:
    client = OllamaClient()
    mock = mock_async_client[0]
    mock.chat.side_effect = ollama.ResponseError("server error", 500)

    with pytest.raises(LLMResponseError) as exc_info:
        await client.chat([Message(role="user", content="Hallo")])

    assert exc_info.value.status_code == 500


async def test_chat_stream_propagates_mid_iteration(
    mock_async_client: list[_MockAsyncClient],
) -> None:
    client = OllamaClient(model="mistral-small")
    mock = mock_async_client[0]

    async def stream_then_fail() -> AsyncIterator[ollama.ChatResponse]:
        yield _ollama_response("first")
        raise ollama.ResponseError("model gone", 404)

    mock.chat.return_value = stream_then_fail()

    output: list[str] = []
    with pytest.raises(LLMModelNotFoundError):
        async for piece in client.chat_stream([Message(role="user", content="Hi")]):
            output.append(piece)

    assert output == ["first"]


async def test_chat_empty_messages_raises_no_call(
    mock_async_client: list[_MockAsyncClient],
) -> None:
    client = OllamaClient()
    mock = mock_async_client[0]

    with pytest.raises(ValueError):
        await client.chat([])

    mock.chat.assert_not_awaited()


async def test_aclose_idempotent(mock_async_client: list[_MockAsyncClient]) -> None:
    client = OllamaClient()
    mock = mock_async_client[0]

    await client.aclose()
    await client.aclose()

    mock.close.assert_awaited_once()
