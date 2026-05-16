# Roadmap — Batoiller

> Incremental development plan organized as bricks, with working method
> and prompt templates for Claude Code.

This document is the **source of truth** for the project's evolution.
Every brick is designed to be delivered in a few hours to 2 days max,
leave `main` in a usable state, and move the project toward a complete
language tutor.

---

## Development philosophy

### The principle: short iteration loops

Each brick follows these rules:

- **Duration**: half a day to 2 days maximum.
- **Deliverable**: something end-to-end usable after merge.
- **Scope**: explicitly defined, with an equally explicit "scope out".
- **Plan first, code second**: Claude Code proposes a plan, you
  validate, then it implements.
- **Documentation as you go**: `CLAUDE.md` and `docs/` updated with
  every brick.

### The cycle for each brick

```
1. Define the scope (in / out)
2. Open a GitHub issue
3. Decide whether an ADR is needed
4. Create the branch feat/brick-name
5. Ask Claude Code for a plan (template below)
6. Validate and adjust the plan
7. Implement step by step
8. Test manually with an ad-hoc script
9. Run the automated tests
10. Update the documentation
11. Commit, merge, tag if it's a milestone
```

### Cross-cutting rules

- `main` must always be usable. If `uv run python -m batoiller.cli`
  breaks after a merge, that's a bug to fix immediately.
- No WIP on `main`. Half-finished code stays on its branch.
- One brick = one "mental PR" (even without using the GitHub PR UI).
- Conventional Commits everywhere (`feat:`, `fix:`, `docs:`,
  `refactor:`, `chore:`, `test:`).
- Continuous refactoring, never big-bang.
- Any out-of-scope idea goes into `IDEAS.md`, never into the current
  code.

---

## Bricks overview

| #  | Brick                                  | Duration | Version          | Status  |
| -- | -------------------------------------- | -------- | ---------------- | ------- |
| 0  | Project foundations                    | ½ day   | v0.0.1           | ✅ Done |
| 1  | Async OllamaClient                     | ½ day   | v0.0.2           | ✅ Done |
| 2  | STT (speech-to-text)                   | 1 day    | v0.0.3           | ✅ Done |
| 3  | Minimal Tutor + voice REPL             | ½ day   | v0.0.4           | ✅ Done |
| 4  | TTS (text-to-speech) — spoken replies  | 1 day    | v0.0.5           | TODO    |
| 5  | Conversational CLI                     | ½ day   | v0.0.6           | TODO    |
| 6  | SQLite persistence (base)              | 1 day    | v0.0.7           | TODO    |
| 7  | Gradio interface (push-to-talk + TTS)  | 1 day    | **v0.1.0** | TODO    |
| 8  | Lesson loader                          | 1-2 days | v0.1.1           | TODO    |
| 9  | Long-term memory                       | 2-3 days | v0.1.2           | TODO    |
| 10 | Grammar tracking & corrections         | 1-2 days | **v0.2.0** | TODO    |
| 11 | Vocabulary & SRS                       | 2 days   | v0.2.1           | TODO    |
| 12 | Semantic search                        | 2 days   | **v0.3.0** | TODO    |
| 13 | Multi-language support                 | 1-2 days | v0.3.1           | TODO    |
| 14 | Assisted lesson generation             | 1-2 days | **v0.4.0** | TODO    |

**Major milestones**:

- **v0.1.0**: end-to-end usable demo — web UI with push-to-talk voice
  in, spoken voice out, persistence, and multi-turn German conversation.
- **v0.2.0**: pedagogical tutor with lessons, memory and corrections.
- **v0.3.0**: tutor with long-term semantic recall (remembers what you
  said weeks ago by topic, not just by chronology).
- **v0.4.0**: self-evolving tutor (generates its own lessons).

Note: VAD (automatic turn-taking) was considered for the path to v0.1.0
and ultimately dropped — push-to-talk in the Gradio UI is simpler and
more controllable than auto-VAD for a tutoring use case. VAD now lives
in "Beyond v0.4.0" as exploration for always-listening device-style
experiences.

---

## Bricks in detail

### Brick 0 — Project foundations ✅

**Goal**: clean repo structure, configured dependencies, working Ollama
smoke test.

**Delivered**: directory tree, `pyproject.toml`, `CLAUDE.md`,
`README.md`, pre-commit, ADR 001, `scripts/hello.py` that speaks German.

---

### Brick 1 — Async OllamaClient ✅

**Goal**: clean async Python wrapper around Ollama. All subsequent
bricks depend on it.

**Scope (in)**:

- `OllamaClient` class with `chat(messages) -> ChatResponse` method
- `chat_stream(messages) -> AsyncIterator[str]` method for streaming
- Pydantic v2 models for `Message`, `ChatResponse`
- Configuration: model, host, timeout (via constructor or environment
  variables)
- Basic error handling (connection refused, model not found)
- Unit tests (happy path + network errors, mocked)

**Scope (out)**:

- Embeddings (separate brick later)
- Function calling / tool use
- Complex retry logic, circuit breakers
- Multi-model load balancing

**Files**:

- `src/batoiller/llm/ollama_client.py`
- `src/batoiller/llm/models.py` (Pydantic)
- `src/batoiller/llm/__init__.py` (public exports)
- `tests/llm/test_ollama_client.py`
- `scripts/check_ollama_client.py` (live smoke against real Ollama)

**Acceptance criteria**:

- An async script can call `client.chat([...])` and get a German
  response from Mistral ✅
- Streaming prints tokens progressively ✅
- Tests green, mypy strict OK, ruff OK ✅

---

### Brick 2 — STT (speech-to-text) ✅

**Goal**: validate the voice path on your hardware as early as
possible. You can speak German, get a clean transcript, and feed it to
the LLM via the wrapper from brick 1.

This brick is intentionally pulled forward (originally planned at
brick 10) to de-risk mlx-whisper install, German transcription
quality, audio capture, and model-download size before investing in
the rest of the stack.

**Scope (in)**:

- `STTService` wrapping `mlx-whisper`
- `whisper-turbo` model by default (~1.5 GB, distilled from large-v3, near-equivalent German WER; swap to `mlx-community/whisper-large-v3-mlx` via constructor or `BATOILLER_STT_MODEL` env var)
- Audio input from file path or raw bytes
- Public API: `await stt.transcribe(audio) -> str` and a sync helper if
  trivial to expose
- `scripts/check_stt.py`: record N seconds from the mic (or read a
  fixture wav), print the transcript
- Optional one-shot wiring to `OllamaClient`: transcribe → `chat()` →
  print reply, to smoke-test the full speak-to-LLM path (single-turn,
  no `Tutor` yet)
- Unit tests for the service with a tiny fixture wav

**Scope (out)**:

- Gradio integration (deferred to brick 7 when the UI lands)
- Multi-turn voice conversation (waits for `Tutor` at brick 3)
- Real-time streaming STT (explore later)
- Automatic end-of-sentence / VAD detection — push-to-talk in brick 7
  is the chosen path; VAD is post-v0.4.0
- TTS (brick 4 closes the loop)

**Files**:

- `src/batoiller/audio/__init__.py`
- `src/batoiller/audio/stt.py`
- `scripts/check_stt.py`
- `tests/audio/test_stt.py`
- Test fixture: `tests/audio/fixtures/de_short.wav` (a few seconds of
  clean German speech)

**Acceptance criteria**:

- Record ~10 s of German into the mic and get a clean transcript
- Fixture-based test passes deterministically (no mic needed in CI)
- Optional: speak a German question, see Mistral's reply on stdout
- Tests green, mypy strict OK, ruff OK

---

### Brick 3 — Minimal Tutor + voice REPL ✅

**Goal**: a business class that orchestrates a conversation, plus a
small script that lets you have a real multi-turn German conversation
through the mic *today*, without waiting for Gradio at brick 7.

**Scope (in)**:

- `Tutor` class with `respond(user_message) -> str` method
- `respond_stream(user_message) -> AsyncIterator[str]` method
- Configurable system prompt (constructor parameter)
- Conversation history kept in memory during instance lifetime
- `reset()` method to clear history
- Tests with mocked OllamaClient
- **`scripts/voice_chat.py`**: multi-turn voice REPL that wires
  `STTService` (brick 2) + `Tutor` + `OllamaClient` (brick 1). Press
  Enter to start a turn, press Enter again to stop speaking, hear /
  read the streamed German reply, repeat. Empty recording or Ctrl+C
  exits. Press-Enter UX is permanent for this script — the Gradio UI
  at brick 7 supersedes it with push-to-talk for daily use.

**Scope (out)**:

- Persistence (Brick 6)
- Long-term memory (Brick 9)
- Lessons (Brick 8)
- Structured corrections (Brick 10)
- TTS — the tutor's reply is text-only here; brick 4 adds spoken
  playback to this same script

**Files**:

- `src/batoiller/core/tutor.py`
- `src/batoiller/core/__init__.py`
- `tests/core/test_tutor.py`
- `scripts/voice_chat.py`

**Acceptance criteria**:

- A tutor can be instantiated with a German system prompt ✅
- Multiple successive calls maintain context ✅
- `reset()` starts fresh ✅
- `core/` modules import **nothing** from UI ✅
- `uv run python scripts/voice_chat.py` opens a multi-turn voice
  conversation: you speak, the tutor remembers what you said two
  turns ago, the script keeps running until you exit ✅

---

### Brick 4 — TTS (text-to-speech) — spoken replies

**Goal**: the tutor speaks to you. With STT in place since brick 2,
this brick closes the audio output side of the voice loop: you press
Enter to talk (via `voice_chat.py`), tutor responds in streamed text
**and** spoken German. The full conversational tutor experience in the
CLI; the web UI follows at brick 7.

**Scope (in)**:

- `TTSService` wrapping `piper-tts` (local, CPU-based ONNX inference)
- Default voice: `de_DE-thorsten-high` (~70 MB, clear male German
  voice, auto-downloads on first use). Overridable via constructor
  or `BATOILLER_TTS_VOICE` env var.
- Public API: `await tts.synthesize(text) -> bytes` (PCM/wav bytes)
  and `await tts.speak(text) -> None` (plays via `sounddevice` from
  brick 2's dep stack)
- `scripts/voice_chat.py` upgraded: after `tutor.respond_stream` prints
  the full reply, `await tts.speak(reply)` plays it back. Sequential
  (synthesize-then-play) — streaming TTS sentence-by-sentence is a
  later polish item.
- `scripts/check_tts.py`: live smoke that synthesizes "Hallo, ich bin
  dein Deutschlehrer." and plays it; ffmpeg/audio probes mirror the
  STT smoke
- Unit tests: mocked `piper.PiperVoice.synthesize`, assert wrapper
  returns bytes / triggers playback / handles voice-not-found error
- **`TTSService.speak_stream(text_chunks, on_text)`**: sentence-pipelined
  playback (added in a follow-up perf commit). Buffers LLM text chunks
  into sentences; synthesizes each on a worker thread while the LLM
  keeps streaming; plays through a single persistent `sd.OutputStream`
  to avoid open/close clicks. Time-to-first-audio drops from "full
  LLM latency + full synthesis" to "first-sentence latency + first-
  sentence synthesis". Asymmetric silence padding (80 ms warmup on the
  first chunk, 200 ms breathing pause between subsequent sentences)
  for clean device startup and natural rhythm.

**Scope (out)**:

- Dynamic voice choice from the UI (post-MVP)
- Configurable speed / pitch / volume
- Barge-in (interrupting playback when the user starts speaking) —
  post-v0.4.0; needs either VAD or a mic-level threshold check
  during playback

**Files**:

- `src/batoiller/audio/tts.py`
- `src/batoiller/audio/models.py` (add `TTSError`)
- `scripts/check_tts.py`
- `scripts/voice_chat.py` (upgraded with TTS playback)
- `tests/audio/test_tts.py`

**Dependency to add**:

- `piper-tts>=1.2` (Apple-Silicon compatible via ONNX Runtime; one
  voice model auto-downloads on first synth)

**Acceptance criteria**:

- `uv run python scripts/check_tts.py` produces audible German speech
  through the default output device
- `voice_chat.py` reads each tutor reply aloud after streaming the
  text — sequential, no overlap, mic capture pauses while playback
  is in progress so the tutor doesn't transcribe its own voice
- Tests green, mypy strict OK, ruff OK

---

### Brick 5 — Conversational CLI

**Goal**: a text-only daily-driver REPL for situations where you'd
rather type than talk (on the bus, in a quiet office, when you don't
want to disturb others). Complements `voice_chat.py` from bricks 3-4.

**Scope (in)**:

- Executable module `python -m batoiller.cli`
- Interactive loop: user prompt, tutor streaming response
- Special commands: `/reset` (clear history), `/quit` (exit)
- Clear display (separators, role indicators)
- Clean Ctrl+C handling

**Scope (out)**:

- Persistence between sessions (Brick 6)
- Multi-session history
- Advanced commands (lessons, vocab, etc.)
- Voice input/output through the CLI (already covered by
  `scripts/voice_chat.py` from bricks 3-4)

**Files**:

- `src/batoiller/cli.py`
- `src/batoiller/__main__.py` (for `python -m batoiller`)

**Acceptance criteria**:

- `uv run python -m batoiller.cli` opens the loop
- Smooth conversation with visible streaming
- Ctrl+C doesn't crash, exits cleanly

---

### Brick 6 — SQLite persistence (base)

**Goal**: your tutor remembers conversations across sessions.

**Scope (in)**:

- SQLModel models: `Learner`, `Session`, `Message`
- `MemoryService` with methods: `create_session`, `save_message`,
  `get_session_messages`, `get_last_session`, `end_session`
- Alembic migrations configured (`alembic init`, first migration)
- DB stored at `~/.batoiller/data.db` (configurable path)
- Integration in `Tutor`: new session on startup, messages saved on the
  fly
- CLI automatically loads the last 2-3 messages from previous session as
  context
- Tests with in-memory SQLite

**Scope (out)**:

- Long-term facts (`learner_fact`) — Brick 9
- Summaries — Brick 9
- Vocabulary — Brick 11
- Lessons — Brick 8

**Files**:

- `src/batoiller/memory/models.py`
- `src/batoiller/memory/service.py`
- `src/batoiller/memory/__init__.py`
- `alembic.ini`, `alembic/versions/001_initial.py`
- `tests/memory/test_service.py`

**Acceptance criteria**:

- Quit the CLI, relaunch: the tutor remembers the previous conversation
- `~/.batoiller/data.db` contains the right tables
- Migrations replayable on empty DB

---

### Brick 7 — Gradio interface (push-to-talk + TTS) 🎯 v0.1.0

**Goal**: first demoable release. A polished web UI where you click
the mic, speak in German, click again to stop, see the transcript,
hear the spoken reply, and the conversation persists across sessions.

**Scope (in)**:

- `app.py` module with `gr.ChatInterface`
- Response streaming
- Soft theme, title and description in German + English
- Tutor shared across sessions (application singleton)
- "Reset conversation" button
- **Push-to-talk mic input** wired to `STTService` from brick 2. The
  user clicks the mic button to start recording, clicks again (or
  releases, depending on Gradio's primitive) to stop. Empty / silent
  recordings are filtered before transcription to avoid Whisper's
  silence-hallucination ("Untertitel von…").
- **Spoken output** wired to `TTSService` from brick 4 — toggleable
  via a UI checkbox in case the user is in a quiet room
- Launch: `uv run python -m batoiller.app`

**Scope (out)**:

- Multiple tabs
- Lesson selector (Brick 8)
- Progress dashboard
- VAD / automatic turn-taking — push-to-talk by design (more
  predictable, no false stops on hesitations)

**Files**:

- `src/batoiller/app.py`
- Screenshot at `docs/screenshots/v0.1.0.png` for the README

**Acceptance criteria**:

- App launches and is accessible at `localhost:7860`
- A full conversation works, with persistence across sessions
- Push-to-talk transcribes a German utterance and submits it
- Tutor's reply is both displayed AND (when the checkbox is on)
  spoken aloud
- README updated with screenshot and instructions

**Tag: `v0.1.0`** 🎉

---

### Brick 8 — Lesson loader

**Goal**: structure courses via declarative files editable by hand.
This is what makes the project a real tutor.

**Scope (in)**:

- Format documented in `docs/lessons-format.md`
- Loader: `LessonLoader.load(lesson_id) -> Lesson`
- YAML front-matter + Markdown body parsing via `python-frontmatter`
- Optional `vocabulary.yaml` file per lesson
- Pydantic models: `Lesson`, `LessonMetadata`, `VocabItem`
- `lesson` table in DB (filesystem ↔ DB sync via hash)
- Tutor accepts a lesson as parameter: enriches the system prompt
- 2 complete example lessons (`construction_basics` and
  `home_renovation`)
- Selector in Gradio (dropdown of available lessons)

**Scope (out)**:

- Phased scenarios (post-MVP, integrate later)
- Automatic lesson generation (Brick 14)
- Per-lesson progression (Brick 10 or 11)

**Files**:

- `src/batoiller/lessons/loader.py`
- `src/batoiller/lessons/models.py`
- `src/batoiller/lessons/sync.py`
- `docs/lessons-format.md`
- `lessons/construction_basics/LESSON.md`
- `lessons/construction_basics/vocabulary.yaml`
- `lessons/home_renovation/LESSON.md`
- `tests/lessons/test_loader.py`

**Acceptance criteria**:

- You can create a new lesson in pure text without touching the code
- The app detects the new lesson on next startup
- The tutor respects the persona and objectives defined in the lesson

---

### Brick 9 — Long-term memory

**Goal**: the tutor remembers who you are, what you said a week ago,
your interests. **This is the brick that creates the illusion of human
continuity.**

**Scope (in)**:

- Tables: `learner_fact`, `summary`
- Extraction via second LLM pass with structured JSON output
- Post-message pipeline: analysis + facts persistence
- End-of-session summary generation
- Enriched system prompt construction (facts + last session summary)
- ADR 002: "Conversational memory strategy"

**Scope (out)**:

- Embeddings and semantic search (Brick 12)
- Grammar skills (Brick 10)
- Multi-level summaries (weekly, monthly) — can come later

**Files**:

- `src/batoiller/memory/facts.py`
- `src/batoiller/memory/summaries.py`
- `src/batoiller/memory/extraction.py`
- `src/batoiller/core/prompts.py` (enriched construction)
- Alembic migration
- `docs/decisions/002-memory-strategy.md`

**Acceptance criteria**:

- You say "I live in Lausanne" in session 1
- In session 2 (the next day), the tutor can refer to your city without
  you re-mentioning it
- Session summaries are inspectable in DB

---

### Brick 10 — Grammar tracking & corrections 🎯 v0.2.0

**Goal**: the tutor identifies your mistakes, categorizes them, and
adapts its corrections to your recurring weaknesses.

**Scope (in)**:

- Tables: `grammar_skill`, `correction`
- Structured outputs for corrections (Pydantic + Ollama JSON Schema)
- Pre-defined grammar skills catalog for German (dative, accusative,
  genders, etc.)
- `mastery` update per skill on each error or success
- Injection of weak skills into the system prompt
- Display of corrections in Gradio (side panel or collapse)
- "My recurring mistakes" view at end of session

**Scope (out)**:

- Generated targeted exercises (post-MVP)
- Vocabulary (Brick 11)

**Files**:

- `src/batoiller/core/corrections.py`
- `src/batoiller/data/grammar_skills_de.yaml` (catalog)
- Alembic migration
- Gradio app update

**Acceptance criteria**:

- A faulty German sentence generates a structured correction in DB
- Weak skills appear in the prompt sent to the LLM
- A recap view shows the most frequent error types

**Tag: `v0.2.0`** 🎉

---

### Brick 11 — Vocabulary & SRS

**Goal**: track vocabulary encountered, Anki-style spaced repetition
integrated into the conversation.

**Scope (in)**:

- `vocab_item` table with SM-2 fields (ease_factor, interval_days,
  repetitions, next_review_at)
- Extraction of used / introduced words in the second LLM pass
- SRS service: `get_due_for_review()`, `record_review_result()`
- Injection of vocab due for review into the system prompt
- Gradio view: list of words seen, due for review, mastered

**Scope (out)**:

- Dedicated Anki-style review mode (post-MVP)
- Automatic example sentence generation

**Files**:

- `src/batoiller/core/vocabulary.py`
- `src/batoiller/core/srs.py`
- Alembic migration
- Gradio app update

**Acceptance criteria**:

- German words used are automatically recorded
- Words due for review are naturally mentioned by the tutor in
  conversation

---

### Brick 12 — Semantic search 🎯 v0.3.0

**Goal**: retrieve relevant "memories" as the conversation history
grows. The tutor finds what you said *about a topic* weeks ago, not
just the most recent chronological turns.

**Scope (in)**:

- `sqlite-vec` extension installed and configured
- Embeddings via Ollama (`nomic-embed-text`)
- Automatic embedding of summaries and important facts
- `MemoryService.search_relevant(query) -> list[Memory]`
- Injection of relevant memories into the system prompt

**Scope (out)**:

- Individual message embedding (too much volume)
- Classic full-text search (overkill for now)

**Files**:

- `src/batoiller/memory/embeddings.py`
- Update `MemoryService`
- ADR 003: "Semantic vs SQL for memory search"

**Acceptance criteria**:

- You ask "what did we talk about regarding the house the other day" →
  the tutor retrieves the relevant memories

**Tag: `v0.3.0`** 🎉

---

### Brick 13 — Multi-language support

**Goal**: generalization beyond German (Italian, English, Spanish, etc.).

**Scope (in)**:

- `target_language` parameter on `Learner`
- Per-language grammar_skills catalogs in `data/`
- Templated system prompts per language
- Language selector in Gradio

**Scope (out)**:

- Voice in each language (depends on Piper availability — most major
  languages have a thorsten-tier voice)

**Files**:

- `src/batoiller/data/grammar_skills_it.yaml`, `_en.yaml`, etc.
- `src/batoiller/core/i18n.py`

**Acceptance criteria**:

- You can learn Italian by simply switching the target language

---

### Brick 14 — Assisted lesson generation 🎯 v0.4.0

**Goal**: you describe a topic, the tutor generates the skeleton of a
lesson you can then edit. Complete loop.

**Scope (in)**:

- CLI command `batoiller create-lesson "bathroom renovation"`
- Generation of `LESSON.md` and `vocabulary.yaml` via LLM call
- Mandatory manual validation before integration
- `_draft_` prefix until validated

**Scope (out)**:

- Auto-improvement of existing lessons (post-v1.0)

**Files**:

- `src/batoiller/cli_commands/create_lesson.py`

**Acceptance criteria**:

- In 2 minutes, you can generate a new lesson on any topic and run it

**Tag: `v0.4.0`** 🎉

---

## Beyond v0.4.0

Some directions to explore once the base is solid:

- **VAD (Voice Activity Detection)**: automatic turn-taking via
  `silero-vad`. Mainly interesting for non-UI use cases — an
  always-listening device, accessibility scenarios, hands-busy
  practice (cooking, walking). Push-to-talk in Gradio is the better
  default for desktop usage; this is opt-in polish.
- **Barge-in**: detect when the user starts speaking during tutor
  playback (via VAD or mic-level threshold), stop playback, start
  listening.
- **Dedicated exercise mode**: targeted exercises on weak skills,
  outside of free conversation.
- **Progress export**: markdown / PDF reports of progress.
- **Mobile**: PWA interface or Capacitor app for on-the-go use.
- **Multi-user**: family (Arlette when she's old enough?).
- **Alternative models**: test DiscoLM, SauerkrautLM for German
  specifically.
- **Anki plugin**: export vocab to Anki if useful.
- **Distribution**: .dmg / .deb / brew tap packaging to simplify
  installation.

These ideas live in `IDEAS.md`, not in this roadmap, until they get
planned.

---

## Prompt template for starting a brick

Copy-paste this template into Claude Code at the start of each brick,
replacing the sections in brackets.

````
Read CLAUDE.md, docs/architecture.md, and any other doc in docs/ that's
relevant to this brick.

## Brick

[Number and name — e.g., "Brick 1 — Async OllamaClient"]

## Issue reference

[Link or copy of the GitHub issue]

## Goal

[1-2 sentences — what we're trying to achieve]

## Scope (in)

- [Precise bullet]
- [Precise bullet]
- [Precise bullet]

## Scope (out)

- [What we're NOT doing in this brick — be explicit]
- [And why: "later", "overkill", "not needed"]

## Acceptance criteria

- [ ] [Verifiable criterion]
- [ ] [Verifiable criterion]
- [ ] Tests pass, mypy strict OK, ruff OK
- [ ] Documentation updated (CLAUDE.md, docs/ if needed)

## Instructions

Before writing any code, propose your implementation plan with:

1. **Files to create or modify** (full paths)
2. **Public API**: class names, method signatures, with type hints
3. **Pydantic models** needed, with their fields
4. **Tests** to write, with what they cover
5. **Implementation order**: break it into 3-5 steps I can validate
   one by one
6. **Open questions** or ambiguities you need me to clarify before
   starting

Do NOT write code yet. I'll review the plan, ask questions, possibly
adjust the scope, then approve. Only then you start coding, step by
step, waiting for my validation between each step.

## Convention reminders

- Python 3.12+, type hints on public API
- Pydantic v2 (not v1)
- async for I/O
- No UI imports in core modules
- Conventional Commits
- Don't add dependencies I didn't approve
````

### Prompt variants

Depending on the situation, adapt the prompt:

**For a very small brick (targeted refactor, bug fix)**:

````
Read CLAUDE.md.

[Describe the change in 2 sentences]

Affected files: [precise list]

Propose a minimal patch. Show the diff before applying.
````

**For an exploration / technical spike**:

````
Read CLAUDE.md.

I want to explore [topic] before committing to an approach. Don't write
production code. Instead:

1. Read the docs of [library/concept]
2. Propose 2-3 possible approaches with pros/cons
3. Suggest a minimal proof-of-concept script we could run in scripts/

I'll pick the approach, then we'll start a proper brick.
````

**For pure documentation updates**:

````
Read CLAUDE.md and [relevant file(s)].

Update [file] to reflect [change]. Keep the existing structure and
tone. Show me the diff.
````

---

## How to use this document

This file is yours. A few good habits:

- **Check off completed bricks** in the overview table (move from
  `TODO` to `✅ Done`).
- **Adjust durations** if you find you're going faster or slower than
  estimated.
- **Reorder bricks** if your usage suggests another priority. Examples
  from this project: STT was originally planned at brick 10 and pulled
  forward to brick 2 to de-risk voice early; TTS was originally at
  brick 12 and pulled to brick 4 so the voice loop closes well before
  the web UI; VAD was briefly in the path between Tutor and TTS, then
  dropped in favour of push-to-talk once the target was clearly a
  web UI rather than a script. The same kind of move stays available.
- **Add bricks** when new needs emerge.
- **Remove bricks** if you decide they're not useful.

This roadmap is not a contract, it's a compass. The project gains
coherence when it exists, and stays agile because it evolves with you.

---

## Appendix — Commit and tag conventions

### Conventional Commits

- `feat:` new feature (bumps minor in SemVer)
- `fix:` bug fix (bumps patch)
- `docs:` documentation only
- `refactor:` refactor without functional change
- `test:` add / modify tests
- `chore:` maintenance (deps, config, etc.)
- `perf:` performance improvement

With optional scope: `feat(llm): add streaming support`.

### Tags

- `v0.0.x`: foundation bricks, not yet usable
- `v0.1.0`: first demoable milestone
- `v0.x.0`: functional milestones (lessons, voice, etc.)
- `v1.0.0`: project considered mature and stable

Tag each milestone with a message:

```bash
git tag -a v0.1.0 -m "First demoable release: chat + DB + Gradio"
git push --tags
```
