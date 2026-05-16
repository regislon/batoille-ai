# CLAUDE.md — batoiller

This file is loaded into every Claude Code session in this repo. Read it first.

## What this project is

**batoiller** — local-first AI language tutor. The user converses with a local LLM (Ollama) that behaves like a real teacher: structured lessons, persistent memory across sessions, grammar corrections, vocabulary tracking, CEFR-level adaptation.

The name is Vaudois patois for *"to chatter, discuss"* — Suisse romande identity. Primary target language is **German**, but the architecture must NOT hardcode it.

## Philosophy

- **Local-first.** LLM, STT, and TTS all run on the user's machine. No cloud dependency.
- **Strict separation of concerns.** Core business logic is UI-agnostic. The same `Tutor`, `LessonLoader`, `MemoryService` must be callable from a CLI, a future FastAPI backend, or a Gradio app. **Core never imports UI.**
- **Read by humans first.** Clear naming over cleverness. Comments explain *why*, not *what*.
- **Keep files short and focused.** Prefer composition over deep hierarchies.

## Stack (locked — don't propose alternatives)

| Layer        | Choice                                                              |
|--------------|---------------------------------------------------------------------|
| Language     | Python 3.12+                                                        |
| Pkg manager  | uv                                                                  |
| LLM runtime  | Ollama (default model: `mistral-small`)                             |
| STT          | mlx-whisper (default model: `mlx-community/whisper-turbo`)          |
| TTS (later)  | Piper                                                               |
| DB           | SQLite via SQLModel                                                 |
| Lesson fmt   | YAML front-matter + Markdown body                                   |
| UI (MVP)     | Gradio (added in a later step)                                      |
| License      | MIT                                                                 |

**Platform / runtime prereqs:**
- Apple Silicon Mac is required for the audio bricks (mlx-whisper, eventually Piper).
- `ffmpeg` must be in PATH (`brew install ffmpeg`) — Whisper shells out to it for audio decoding.

## Repository layout

```
batoiller/
├── src/batoiller/
│   ├── core/      # Tutor, conversation orchestration (no I/O specifics)
│   ├── llm/       # Ollama client adapter
│   ├── audio/     # STT (mlx-whisper) — and later TTS (Piper)
│   ├── memory/    # SQLModel models + MemoryService
│   └── lessons/   # LessonLoader, lesson schema
├── tests/
├── docs/
│   ├── architecture.md
│   ├── ROADMAP.md
│   └── decisions/   # ADRs, numbered 001-, 002-, ...
├── lessons/         # Lesson content (YAML front-matter + Markdown)
└── scripts/         # Smoke tests, dev utilities
```

## Coding conventions

- **Type hints on every public function/method/return.** `from __future__ import annotations` is unnecessary on 3.12.
- **Pydantic v2** syntax — `model_config = ConfigDict(...)`, `Field(...)`, `@field_validator`. No v1 patterns.
- **Async I/O** for LLM calls and DB I/O. CPU-bound code stays sync.
- **`match` statements** for closed sets of cases (lesson types, message roles, etc.).
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`. Scope optional.
- **Imports**: ruff (isort) handles ordering. Don't fight it.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for module constants.

## Things to NOT do

- ❌ Don't import Gradio (or any UI lib) inside `src/batoiller/core/`, `llm/`, `memory/`, `lessons/`, or `audio/`.
- ❌ Don't hardcode "German" anywhere — language is configuration.
- ❌ Don't add a dependency without proposing it first.
- ❌ Don't introduce a new build tool, web framework, or LLM runtime.
- ❌ Don't write speculative abstractions for hypothetical needs.
- ❌ Don't write multi-paragraph docstrings or comment blocks. One short line max for non-obvious *why*.
- ❌ Don't catch broad exceptions to "be safe" — let them propagate unless there's a real recovery.
- ❌ Don't call `STTService.transcribe` concurrently — mlx/Metal isn't safe for it. When multi-user surfaces appear (brick 7 Gradio), wrap with an `asyncio.Lock` or a queue.

## Audio notes (brick 2+)

- **Whisper hallucinates on silence.** A typical German artifact is `Untertitel von Stephanie Geiges`. Push-to-talk in Gradio (brick 7) limits this in practice (the user controls timing), but the UI MUST still filter empty / near-silent recordings before sending to Whisper — accidental "press start, hesitate, press stop" gives a silent buffer. Brick 10 (corrections) also needs this filter at its input boundary, otherwise the correction pipeline will treat the hallucination as a real learner mistake.
- Default STT model is `whisper-turbo` (~1.5 GB). Swap to `mlx-community/whisper-large-v3-mlx` (~2.9 GB, slightly better quality) by setting `BATOILLER_STT_MODEL`.

## Useful commands

```bash
# Install / sync deps (runtime + dev group)
uv sync

# Run the smoke test (requires Ollama running + mistral-small pulled)
uv run python scripts/hello.py

# Lint & format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy

# Tests
uv run pytest

# Install pre-commit hooks (once per clone)
uv run pre-commit install
```

## When in doubt

- If a design choice is non-obvious, write a short ADR in `docs/decisions/NNN-title.md` *before* implementing.
- If a piece of business logic could live in either core or UI, **it goes in core**.
