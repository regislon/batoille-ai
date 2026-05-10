"""Smoke test: verify Ollama is reachable and mistral-small can roleplay a German tutor.

Run with:
    uv run python scripts/hello.py
"""

import sys

import ollama

MODEL = "mistral-small"

SYSTEM_PROMPT = (
    "You are a friendly, patient German language tutor. "
    "Greet the student warmly in German (one or two short sentences), "
    "then add a single line in English inviting them to start their first lesson. "
    "Keep it concise."
)


def main() -> int:
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Hallo!"},
            ],
        )
    except ollama.ResponseError as exc:
        print(f"Ollama returned an error: {exc}", file=sys.stderr)
        print(f"Hint: have you run `ollama pull {MODEL}`?", file=sys.stderr)
        return 1
    except ConnectionError as exc:
        print(f"Could not reach Ollama: {exc}", file=sys.stderr)
        print("Hint: is the Ollama daemon running?", file=sys.stderr)
        return 1

    print(response["message"]["content"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
