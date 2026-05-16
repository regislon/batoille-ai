"""The Tutor: orchestrates a multi-turn conversation with the LLM.

Holds the conversation history in memory for the lifetime of the instance,
adds a configurable system prompt to every call. UI-agnostic — usable from
a CLI, a Gradio app, or a future FastAPI backend.
"""

from collections.abc import AsyncIterator

from batoiller.llm import Message, OllamaClient


class Tutor:
    """Multi-turn conversation orchestrator.

    Not safe for concurrent calls on the same instance — one conversation
    per Tutor. If you want fan-out (e.g. several users in Gradio), give
    each user their own Tutor.
    """

    def __init__(self, client: OllamaClient, system_prompt: str) -> None:
        self._client = client
        self._system_prompt = system_prompt
        self._history: list[Message] = []

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def history(self) -> list[Message]:
        """Defensive copy of the running history (excluding the system message)."""
        return list(self._history)

    def reset(self) -> None:
        """Clear conversation history. The system prompt stays."""
        self._history = []

    async def respond(self, user_message: str) -> str:
        self._history.append(Message(role="user", content=user_message))
        try:
            response = await self._client.chat(self._messages())
        except Exception:
            # Don't leave an orphan user message in history on failure.
            self._history.pop()
            raise
        text = response.content
        self._history.append(Message(role="assistant", content=text))
        return text

    async def respond_stream(self, user_message: str) -> AsyncIterator[str]:
        """Stream the assistant reply token-by-token.

        On successful completion, the full exchange is appended to history.
        If the stream is interrupted (consumer breaks, or the backend errors),
        both the user message and any partial assistant text are dropped —
        history stays as it was before this call.
        """
        self._history.append(Message(role="user", content=user_message))
        chunks: list[str] = []
        completed = False
        try:
            async for chunk in self._client.chat_stream(self._messages()):
                chunks.append(chunk)
                yield chunk
            completed = True
        finally:
            if completed and chunks:
                self._history.append(Message(role="assistant", content="".join(chunks)))
            elif self._history and self._history[-1].role == "user":
                # Stream was interrupted OR returned zero content — drop the
                # orphan user message so history stays consistent.
                self._history.pop()

    def _messages(self) -> list[Message]:
        return [Message(role="system", content=self._system_prompt), *self._history]
