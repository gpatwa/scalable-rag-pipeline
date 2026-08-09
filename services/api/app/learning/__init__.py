# services/api/app/learning/__init__.py
"""
Self-improvement loop.

`evaluator_node` grades an answer and can retry it once — a loop closed inside
one request. This package closes the loop *across* requests: graded outcomes are
persisted, recalled by semantic similarity on later runs, and injected into the
responder prompt so the system's behaviour changes as evidence accumulates.

  store.py   — ExperienceMemory: record graded outcomes, recall relevant ones
  recall.py  — the graph node that loads experience into AgentState
"""
from app.learning.store import (  # noqa: F401
    EXPERIENCE_COLLECTION,
    Experience,
    ExperienceMemory,
    experience_memory,
    set_vectordb_client,
)
