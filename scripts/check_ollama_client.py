"""Live smoke test for OllamaClient against a running Ollama daemon.

Run with:
    uv run python scripts/check_ollama_client.py

Requires:
    - Ollama daemon running (`ollama serve` or the Mac/Win/Linux app)
    - mistral-small pulled (`ollama pull mistral-small`)

Three checks: basic chat, streaming, multi-turn context. Exits non-zero on
any failure with a hint pointing at the likely cause.
"""

import asyncio
import sys

from batoiller.llm import (
    LLMConnectionError,
    LLMModelNotFoundError,
    Message,
    OllamaClient,
)

SYSTEM_PROMPT = (
    "Du bist ein freundlicher Deutschlehrer für französischsprachige Lerner. "
    "Antworte immer auf Deutsch, mit einfachen Sätzen."
)


async def check_basic_chat(client: OllamaClient) -> None:
    print("=== Test 1: Basic chat ===")
    response = await client.chat(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content="Sag Hallo auf Deutsch."),
        ]
    )
    print(f"Response: {response.content}")
    assert response.content, "Empty response"
    assert len(response.content) > 5, "Response too short"
    print("OK\n")


async def check_streaming(client: OllamaClient) -> None:
    print("=== Test 2: Streaming ===")
    print("Stream: ", end="", flush=True)
    chunks: list[str] = []
    async for chunk in client.chat_stream(
        [Message(role="user", content="Zähle von 1 bis 5 auf Deutsch.")]
    ):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    print()
    assert len(chunks) > 3, f"Expected > 3 chunks for a real stream, got {len(chunks)}"
    print("OK\n")


async def check_multi_turn_context(client: OllamaClient) -> None:
    print("=== Test 3: Multi-turn context ===")
    history: list[Message] = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content="Mein Name ist Régis."),
    ]
    first = await client.chat(history)
    print(f"Turn 1: {first.content}")

    history.append(Message(role="assistant", content=first.content))
    history.append(Message(role="user", content="Wie ist mein Name?"))
    second = await client.chat(history)
    print(f"Turn 2: {second.content}")

    lower = second.content.lower()
    assert "régis" in lower or "regis" in lower, (
        f"Tutor should remember the name 'Régis', got: {second.content}"
    )
    print("Context preserved\n")


async def main() -> int:
    try:
        async with OllamaClient() as client:
            await check_basic_chat(client)
            await check_streaming(client)
            await check_multi_turn_context(client)
    except LLMConnectionError as exc:
        print(f"Could not reach Ollama: {exc}", file=sys.stderr)
        print("Hint: is the Ollama daemon running? Try `ollama serve`.", file=sys.stderr)
        return 1
    except LLMModelNotFoundError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
