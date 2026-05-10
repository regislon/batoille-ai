# 001 — Stack choices

- **Status:** Accepted
- **Date:** 2026-05-10

## Context

batoiller is a local-first language tutor. The first technical decisions shape everything that follows: inference runtime, persistence, UI, lesson format.

## Decision

### LLM runtime — Ollama (default model: `mistral-small`)

- One-command install on macOS / Linux / Windows.
- Stable HTTP API and an official Python client.
- Manages model lifecycle (pull, quantization, GPU detection) so we don't reinvent it.
- `mistral-small` gives a reasonable quality/latency tradeoff on consumer hardware; users can swap any tag.

Alternatives considered:
- `llama.cpp` directly — more control, more moving parts (model paths, server flags, custom client).
- Cloud APIs — violates the local-first goal.

### Persistence — SQLite via SQLModel

- Zero-config, single-file, ubiquitous. Ideal for local-first.
- SQLModel = Pydantic + SQLAlchemy in one declaration; DRY for our domain.
- Trivially backed up, inspected, or migrated.

Alternatives considered:
- DuckDB — overkill for OLTP-style usage; we don't need columnar.
- Flat JSON store — fast to start, painful once we want vocab queries and session joins.

### UI (MVP) — Gradio

- Fastest path from "I have a Python function" to "I have a chat UI".
- Streaming, audio I/O, and transcript components come for free.
- Decoupled from core (see [architecture.md](../architecture.md)) so it can be replaced later.

Alternatives considered:
- FastAPI + a custom frontend — better long-term, way too much UI plumbing for an MVP.
- Streamlit — weaker chat-streaming story, less suited to audio.

### Lesson format — YAML front-matter + Markdown body

- Authors write lessons as Markdown; metadata (CEFR level, prerequisites, vocabulary, drills) lives in front-matter.
- Diffable, human-readable, easy to lint, trivially convertible to other surfaces (e.g. exporting to a static site).
- `python-frontmatter` parses both halves in two lines.

Alternatives considered:
- JSON/YAML-only — content authoring is awful in a pure structured format.
- DB-backed CMS — premature; lessons are version-controlled content.

## Consequences

- Users must install Ollama separately. Acceptable: it's a one-time, well-documented step.
- We accept SQLite's single-writer limitation. For a single-user local app, that's a non-issue.
- Switching UI in the future requires a UI rewrite, but no core changes (by design).
- Lesson authoring is a Markdown-with-front-matter workflow. Standard, learnable in minutes.
