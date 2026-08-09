# services/api/app/learning/store.py
"""
Experience Memory — the across-run half of the self-improvement loop.

The evaluator node already closes a loop *within* a single request: it scores
the answer and, on a low score, rewrites the query and retries. Nothing learned
in that run survives it — run N+1 starts from exactly the same place run N did.

This module persists graded outcomes so they do. A run that scored well becomes
an *exemplar* other runs can retrieve; a run that scored badly becomes an
*anti-pattern* other runs are warned about. Both are keyed by query embedding,
so recall is by meaning rather than string match.

Architecture mirrors `app/cache/semantic.py` deliberately — same injected
VectorDB client, same tenant scoping, same late-initialisation via the app
lifespan — so this stays provider-agnostic (Qdrant, Azure AI Search, ...) and
reads as native to the codebase rather than bolted on.

Distinction from the two neighbouring stores, since all three are vector-backed:

  semantic_cache      — "I answered this exact question, reuse the answer."
                        Skips work. Keyed on near-duplicate queries.
  user_memories       — "This user prefers X." Per-user facts.
  experience_memory   — "Answering questions *like* this went well when the
                        approach was Y, and badly when it was Z." Shapes how a
                        *new* question gets answered. This file.

The cache short-circuits the graph; experience memory informs it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.clients.ray_embed import embed_client
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"
EXPERIENCE_COLLECTION = "experience_memory"

Outcome = Literal["exemplar", "antipattern"]

# Late-initialised — set by main.py lifespan via set_vectordb_client(),
# same contract as app/cache/semantic.py.
_vectordb_client = None


def set_vectordb_client(client) -> None:
    """Called once during app startup to inject the abstracted VectorDB client."""
    global _vectordb_client
    _vectordb_client = client


@dataclass(frozen=True)
class Experience:
    """One graded outcome, recalled to inform a future run."""

    query: str
    answer: str
    outcome: Outcome
    score: int
    reasoning: str
    # Similarity of this experience's query to the incoming one. Populated on
    # recall, not on write.
    similarity: float = 0.0

    def as_exemplar_block(self) -> str:
        """Render for injection into the responder prompt."""
        return f"Q: {self.query}\nA: {self.answer}"

    def as_antipattern_block(self) -> str:
        """Render a failure as guidance. The answer text is deliberately
        omitted — repeating a bad answer in-context invites imitation. Only the
        judge's diagnosis is useful."""
        return f"Q: {self.query}\nWhat went wrong: {self.reasoning}"


class ExperienceMemory:
    """Vector-backed store of graded run outcomes, scoped by tenant."""

    async def record(
        self,
        *,
        query: str,
        answer: str,
        score: int,
        reasoning: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        query_embedding: Optional[list[float]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Persist a graded outcome.

        Only decisive scores are stored. Mid-range scores (3) are the evaluator
        saying "acceptable but unremarkable" — recalling those as exemplars
        would teach mediocrity, and recalling them as failures would be unfair.
        Storing everything also inflates the collection and dilutes recall
        precision, so the middle is dropped on purpose.

        Returns True if something was written.
        """
        if not settings.EXPERIENCE_MEMORY_ENABLED:
            return False
        if _vectordb_client is None:
            logger.debug("Experience memory: no vectordb client injected, skipping write.")
            return False

        outcome = self._classify(score)
        if outcome is None:
            return False

        if not query.strip() or not answer.strip():
            return False

        try:
            # Reuse the embedding the graph already computed for the semantic
            # cache check when it is available — this write is on the response
            # path, and a second embed call would add latency for no gain.
            vector = query_embedding or await embed_client.embed_query(query)

            payload: dict[str, Any] = {
                "query": query,
                "answer": answer,
                "outcome": outcome,
                "score": score,
                "reasoning": reasoning,
                "tenant_id": tenant_id,
            }
            if metadata:
                payload["metadata"] = metadata

            await _vectordb_client.upsert(
                collection=EXPERIENCE_COLLECTION,
                points=[{
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": payload,
                }],
            )
            logger.info(
                "Experience memory: recorded %s (score=%d) for tenant=%s",
                outcome, score, tenant_id,
            )
            return True

        except Exception as e:
            # Never fail a user-facing request because learning failed. The
            # loop is an enhancement; the answer is the product.
            logger.warning("Experience memory: record failed — %s", e)
            return False

    async def recall(
        self,
        *,
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        query_embedding: Optional[list[float]] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> tuple[list[Experience], list[Experience]]:
        """
        Retrieve prior experience relevant to `query`.

        Returns (exemplars, antipatterns), each ordered most-similar-first.

        The threshold is deliberately looser than the semantic cache's. The
        cache must be near-certain the questions are equivalent before it
        reuses an answer; here a merely *related* prior run is still useful
        guidance, and being wrong costs a slightly noisier prompt rather than
        a wrong answer.
        """
        if not settings.EXPERIENCE_MEMORY_ENABLED:
            return [], []
        if _vectordb_client is None:
            return [], []

        limit = limit or settings.EXPERIENCE_MEMORY_TOP_K
        threshold = threshold if threshold is not None else settings.EXPERIENCE_MEMORY_THRESHOLD

        try:
            vector = query_embedding or await embed_client.embed_query(query)

            filters: dict[str, Any] = {} if settings.SINGLE_TENANT_MODE else {"tenant_id": tenant_id}

            # Over-fetch, then split by outcome. One query beats two round
            # trips, and the split is cheap.
            results = await _vectordb_client.search(
                collection=EXPERIENCE_COLLECTION,
                vector=vector,
                limit=limit * 2,
                filters=filters,
                score_threshold=threshold,
            )

            exemplars: list[Experience] = []
            antipatterns: list[Experience] = []

            for r in results or []:
                exp = self._to_experience(r)
                if exp is None:
                    continue
                bucket = exemplars if exp.outcome == "exemplar" else antipatterns
                if len(bucket) < limit:
                    bucket.append(exp)

            if exemplars or antipatterns:
                logger.info(
                    "Experience memory: recalled %d exemplar(s), %d anti-pattern(s)",
                    len(exemplars), len(antipatterns),
                )
            return exemplars, antipatterns

        except Exception as e:
            logger.warning("Experience memory: recall failed — %s", e)
            return [], []

    # ── internals ──────────────────────────────────────────────────────────

    @staticmethod
    def _classify(score: int) -> Optional[Outcome]:
        """Map an evaluator score to a stored outcome, or None to skip.

        Note score==0 means 'not evaluated' in AgentState, not 'terrible' — it
        must not be recorded as a failure.
        """
        if score >= settings.EXPERIENCE_MEMORY_EXEMPLAR_MIN_SCORE:
            return "exemplar"
        if 0 < score <= settings.EXPERIENCE_MEMORY_ANTIPATTERN_MAX_SCORE:
            return "antipattern"
        return None

    @staticmethod
    def _to_experience(result: Any) -> Optional[Experience]:
        """Normalise a VectorDB hit into an Experience.

        Backends differ in shape (attribute vs mapping, `score` vs `similarity`),
        so this stays defensive rather than assuming Qdrant.
        """
        payload = None
        similarity = 0.0

        if isinstance(result, dict):
            payload = result.get("payload") or result.get("metadata")
            similarity = result.get("score") or result.get("similarity") or 0.0
        else:
            payload = getattr(result, "payload", None)
            similarity = getattr(result, "score", 0.0) or 0.0

        if not isinstance(payload, dict):
            return None

        query = payload.get("query") or ""
        answer = payload.get("answer") or ""
        outcome = payload.get("outcome")
        if outcome not in ("exemplar", "antipattern") or not query:
            return None

        return Experience(
            query=query,
            answer=answer,
            outcome=outcome,
            score=int(payload.get("score") or 0),
            reasoning=payload.get("reasoning") or "",
            similarity=float(similarity),
        )


experience_memory = ExperienceMemory()
