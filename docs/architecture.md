# Architecture

batoiller follows a layered architecture with one hard rule: **core never imports UI**. Inference and persistence are local; everything composes around plain Python objects.

## Layers

```
┌─────────────────────────────────────────────────────────────┐
│  UI layer  (Gradio MVP, future FastAPI, future CLI)         │
│  - Owns presentation, user input, session lifecycle.        │
│  - Calls into core. Never the other way around.             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Core  (src/batoiller/core)                                 │
│  - Tutor: orchestrates a conversation turn.                 │
│  - Domain types (CEFR level, message role, lesson plan).    │
│  - No I/O specifics — depends on llm/memory/lessons via     │
│    intent-level interfaces.                                 │
└──────────┬─────────────────────────┬────────────────────────┘
           │                         │
┌──────────▼──────────┐   ┌──────────▼──────────────────────┐
│  llm/               │   │  memory/                        │
│  - Ollama adapter.  │   │  - SQLModel models.             │
│  - Sync + async.    │   │  - MemoryService (record turn,  │
│  - Streaming.       │   │    track vocab, recall topics). │
└─────────────────────┘   └─────────────────────────────────┘

         ┌─────────────────────────────┐
         │  lessons/                   │
         │  - LessonLoader             │
         │  - Lesson schema (Pydantic) │
         │  - Parses YAML front-matter │
         │    + Markdown body          │
         └─────────────────────────────┘
```

## Rules

1. **Core never imports UI.** `core` may depend on `llm/`, `memory/`, `lessons/` through narrow interfaces; UI depends on `core`.
2. **One LLM runtime, abstracted.** `llm/` wraps Ollama. If we ever swap (e.g. `llama.cpp`), only `llm/` changes.
3. **Persistence is replaceable.** `memory/` exposes a service with intent-level methods (`record_turn`, `mark_word_seen`, `recall_recent_topics`), not raw SQL.
4. **Lessons are content, not code.** Files in top-level `lessons/` are authored by humans; the `lessons/` Python module only parses and validates them.
5. **Async at the edges.** LLM and DB calls are async; pure data transformations stay sync.

## What lives where

| Concern                    | Location                  |
|----------------------------|---------------------------|
| Ollama HTTP/streaming      | `src/batoiller/llm/`      |
| Conversation orchestration | `src/batoiller/core/`     |
| SQLite schema + CRUD       | `src/batoiller/memory/`   |
| Lesson parsing & schema    | `src/batoiller/lessons/`  |
| Gradio app                 | (future) `app/` or `ui/`  |
| Lesson content (`.md`)     | top-level `lessons/`      |
| Smoke tests, dev scripts   | `scripts/`                |
