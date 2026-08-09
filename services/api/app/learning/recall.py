# services/api/app/learning/recall.py
"""
The graph node that loads prior experience into state.

Placed immediately after the planner and before retrieval, so recalled guidance
is available to the responder without adding a round trip to the critical path
for requests that the semantic cache already short-circuits.
"""
from __future__ import annotations

import logging

from app.agents.state import AgentState
from app.config import settings
from app.learning.store import DEFAULT_TENANT_ID, experience_memory

logger = logging.getLogger(__name__)


async def experience_recall_node(state: AgentState) -> dict:
    """Populate `exemplars` / `antipatterns` for the responder to use.

    Returns empty lists rather than raising when the feature is off or the
    store is unreachable — the graph must run identically with learning
    disabled.
    """
    if not settings.EXPERIENCE_MEMORY_ENABLED:
        return {"exemplars": [], "antipatterns": []}

    query = state.get("current_query", "")
    if not query.strip():
        return {"exemplars": [], "antipatterns": []}

    exemplars, antipatterns = await experience_memory.recall(
        query=query,
        tenant_id=state.get("tenant_id") or DEFAULT_TENANT_ID,
        # Reuse the vector the semantic-cache check already computed when the
        # chat route populated it; avoids a second embed on the hot path.
        query_embedding=state.get("query_embedding") or None,
    )

    return {
        "exemplars": [
            {
                "query": e.query,
                "answer": e.answer,
                "score": e.score,
                "similarity": e.similarity,
            }
            for e in exemplars
        ],
        "antipatterns": [
            {
                "query": a.query,
                "reasoning": a.reasoning,
                "score": a.score,
                "similarity": a.similarity,
            }
            for a in antipatterns
        ],
    }


def build_experience_prompt_block(state: AgentState) -> str:
    """
    Render recalled experience for the responder prompt.

    Kept as a pure function so it is unit-testable without a graph run, and so
    the responder stays a single place that assembles context.
    """
    exemplars = state.get("exemplars") or []
    antipatterns = state.get("antipatterns") or []

    if not exemplars and not antipatterns:
        return ""

    parts: list[str] = []

    if exemplars:
        rendered = "\n\n".join(
            f"Q: {e.get('query', '')}\nA: {e.get('answer', '')}" for e in exemplars
        )
        parts.append(
            "--- Prior answers to similar questions that were rated highly ---\n"
            "Match their depth, structure, and citation style. Do not reuse their "
            "content unless the retrieved context supports it.\n\n" + rendered
        )

    if antipatterns:
        rendered = "\n\n".join(
            f"Q: {a.get('query', '')}\nWhat went wrong: {a.get('reasoning', '')}"
            for a in antipatterns
        )
        parts.append(
            "--- Known failure modes on similar questions ---\n"
            "These previous attempts were rated poor for the stated reason. "
            "Avoid repeating them.\n\n" + rendered
        )

    return "\n\n".join(parts)
