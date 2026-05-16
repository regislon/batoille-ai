"""Core business logic — UI-agnostic conversation orchestration.

Core never imports UI libraries. It may depend on `llm/`, `memory/`,
`lessons/`, `audio/` via narrow interfaces.
"""

from batoiller.core.tutor import Tutor

__all__ = ["Tutor"]
