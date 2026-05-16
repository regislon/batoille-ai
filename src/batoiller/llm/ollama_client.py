"""Async wrapper around the official `ollama` Python client.

The ONLY module in batoiller that imports the `ollama` package. Callers talk
to `OllamaClient` and the types in `batoiller.llm.models`; if you find
yourself reaching for `ollama.*` outside this file, fix the wrapper instead.
"""

import os
from collections.abc import AsyncIterator
from types import TracebackType
from typing import cast

import ollama

from batoiller.llm.models import (
    ChatResponse,
    LLMConnectionError,
    LLMError,
    LLMModelNotFoundError,
    LLMResponseError,
    Message,
    Role,
)

_DEFAULT_MODEL = "mistral-small"
_DEFAULT_TIMEOUT = 120.0


class OllamaClient:
    """Async client for an Ollama daemon. Safe for concurrent in-flight calls."""

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._model = (
            model if model is not None else os.environ.get("BATOILLER_LLM_MODEL", _DEFAULT_MODEL)
        )
        resolved_timeout = timeout if timeout is not None else _read_timeout_env()
        # ollama.AsyncClient itself reads OLLAMA_HOST when host is None.
        self._client = ollama.AsyncClient(host=host, timeout=resolved_timeout)
        self._closed = False

    @property
    def model(self) -> str:
        return self._model

    async def chat(self, messages: list[Message]) -> ChatResponse:
        if not messages:
            raise ValueError("messages must not be empty")
        try:
            raw = await self._chat_once(messages)
        except ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except ollama.ResponseError as exc:
            raise self._translate_response_error(exc) from exc
        return _to_public_response(raw)

    async def chat_stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if not messages:
            raise ValueError("messages must not be empty")
        try:
            stream = await self._chat_stream_raw(messages)
        except ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except ollama.ResponseError as exc:
            raise self._translate_response_error(exc) from exc

        try:
            async for chunk in stream:
                # Brick 1: yield only the delta. Brick 2 may want richer chunks.
                yield chunk.message.content or ""
        except ConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc
        except ollama.ResponseError as exc:
            raise self._translate_response_error(exc) from exc

    async def _chat_once(self, messages: list[Message]) -> ollama.ChatResponse:
        return await self._client.chat(
            model=self._model,
            messages=[m.model_dump() for m in messages],
            stream=False,
        )

    async def _chat_stream_raw(self, messages: list[Message]) -> AsyncIterator[ollama.ChatResponse]:
        return await self._client.chat(
            model=self._model,
            messages=[m.model_dump() for m in messages],
            stream=True,
        )

    def _translate_response_error(self, exc: ollama.ResponseError) -> LLMError:
        if exc.status_code == 404:
            return LLMModelNotFoundError(self._model)
        return LLMResponseError(exc.status_code, exc.error)

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        await self._client.close()  # type: ignore[no-untyped-call]
        self._closed = True


def _to_public_response(raw: ollama.ChatResponse) -> ChatResponse:
    role: str = raw.message.role
    if role not in ("system", "user", "assistant"):
        # Defensive: ollama can return roles we don't yet model (e.g. "tool").
        raise LLMResponseError(0, f"Unexpected message role from Ollama: {role!r}")
    return ChatResponse(
        model=raw.model or "",
        message=Message(role=cast(Role, role), content=raw.message.content or ""),
        eval_count=raw.eval_count,
        total_duration_ns=raw.total_duration,
    )


def _read_timeout_env() -> float:
    raw = os.environ.get("BATOILLER_LLM_TIMEOUT")
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT
