"""Public types and exceptions for the LLM adapter.

Anything that wants to talk to the model imports from here. The `ollama`
package is intentionally NOT imported in this module — the architecture rule
is that the runtime (Ollama) only leaks into `ollama_client.py`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    message: Message
    eval_count: int | None = None
    total_duration_ns: int | None = None

    @property
    def content(self) -> str:
        return self.message.content


class LLMError(Exception):
    """Base class for any error raised by the LLM adapter."""


class LLMConnectionError(LLMError):
    """The LLM runtime (Ollama daemon) could not be reached."""


class LLMModelNotFoundError(LLMError):
    """The configured model is not available on the Ollama daemon (HTTP 404)."""

    def __init__(self, model: str) -> None:
        super().__init__(f"Model {model!r} not found. Run `ollama pull {model}`.")
        self.model = model


class LLMResponseError(LLMError):
    """Ollama responded with a non-404 error."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Ollama responded {status_code}: {message}")
        self.status_code = status_code
        self.message = message
