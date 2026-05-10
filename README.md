# batoiller

> _Batoiller_ — vaudois patois for *"to chatter, to discuss"*.
>
> 🇫🇷 Bavarder avec une IA locale pour apprendre une langue.
> 🇬🇧 Chat with a local AI to learn a language.

A local-first language tutor. You converse with a local LLM (via [Ollama](https://ollama.com/)) that behaves like a real teacher: structured lessons, persistent memory across sessions, grammar corrections, vocabulary tracking, CEFR-level adaptation.

Default target language is **German**, but the architecture does not hardcode it. Born in Suisse romande.

## Status

🚧 **Early — work in progress.** Foundations only. APIs, schemas, and folder layout will change.

## Prerequisites

- **Python 3.12+**
- [**uv**](https://docs.astral.sh/uv/) for dependency management
- [**Ollama**](https://ollama.com/) running locally

## Quick start

```bash
git clone <this-repo> batoiller
cd batoiller
uv sync
ollama pull mistral-small
uv run python scripts/hello.py
```

If the smoke test prints a German greeting, you're set.

## Going further

- 📐 [Architecture overview](docs/architecture.md)
- 📜 [Architectural decisions](docs/decisions/)
- 🤖 [Working with Claude Code on this project](CLAUDE.md)

## License

MIT — see [LICENSE](LICENSE).
