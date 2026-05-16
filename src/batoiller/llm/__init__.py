"""LLM adapter — the only module that imports `ollama`."""

from batoiller.llm.models import (
    ChatResponse,
    LLMConnectionError,
    LLMError,
    LLMModelNotFoundError,
    LLMResponseError,
    Message,
)
from batoiller.llm.ollama_client import OllamaClient

__all__ = [
    "ChatResponse",
    "LLMConnectionError",
    "LLMError",
    "LLMModelNotFoundError",
    "LLMResponseError",
    "Message",
    "OllamaClient",
]
