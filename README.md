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
- **Apple Silicon Mac** — required for on-device STT/TTS (brick 2+ uses `mlx-whisper`)
- **ffmpeg** in PATH — `brew install ffmpeg` (used by Whisper to decode audio)

## Quick start

```bash
git clone <this-repo> batoiller
cd batoiller
uv sync
ollama pull mistral-small
uv run python scripts/hello.py
```

If the smoke test prints a German greeting, you're set.

## Run Ollama & chat with Mistral

**Start the daemon.** Install the [Ollama Mac app](https://ollama.com/download) (auto-starts on login), or from a terminal:

```bash
ollama serve &
# Verify it's reachable:
curl http://localhost:11434/api/tags
```

**Chat with Mistral** from the CLI — multi-turn, keeps context until you type `/bye`:

```bash
ollama run mistral-small
```

Inside the REPL, give it a tutor persona for the session:

```
/set system "Du bist ein freundlicher Deutschlehrer für französischsprachige Lerner."
```

**Test batoiller's own async wrapper** end-to-end (basic chat, streaming, multi-turn context):

```bash
uv run python scripts/check_ollama_client.py
```

## Going further

- 📐 [Architecture overview](docs/architecture.md)
- 📜 [Architectural decisions](docs/decisions/)
- 🤖 [Working with Claude Code on this project](CLAUDE.md)

## License

MIT — see [LICENSE](LICENSE).
