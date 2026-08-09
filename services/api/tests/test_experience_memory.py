# services/api/tests/test_experience_memory.py
"""
Tests for the across-run self-improvement loop (app/learning).

The property under test is the one that distinguishes this from the existing
evaluator retry: an outcome graded in run N must be able to change the prompt
built in run N+1. `test_loop_closes_across_runs` is the load-bearing test —
everything else guards its preconditions.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.learning.recall import build_experience_prompt_block, experience_recall_node
from app.learning.store import ExperienceMemory, experience_memory


class FakeVectorDB:
    """Minimal in-memory stand-in for the VectorDB abstraction.

    Similarity is deliberately crude (token overlap) — these tests are about
    loop wiring, not retrieval quality, and a real embedding model would make
    them slow and non-deterministic.
    """

    def __init__(self):
        self.points: list[dict] = []

    async def upsert(self, collection, points):
        for p in points:
            self.points.append({"collection": collection, **p})

    async def search(self, collection, vector, limit, filters=None, score_threshold=0.0):
        hits = []
        for p in self.points:
            if p["collection"] != collection:
                continue
            payload = p["payload"]
            if filters:
                if any(payload.get(k) != v for k, v in filters.items()):
                    continue
            score = _overlap(vector, p["vector"])
            if score >= score_threshold:
                hits.append({"score": score, "payload": payload})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]


def _overlap(a, b):
    """Cosine-ish similarity for the fake 3-dim vectors used below."""
    if not a or not b:
        return 0.0
    return 1.0 if list(a) == list(b) else 0.3


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeVectorDB()
    monkeypatch.setattr("app.learning.store._vectordb_client", db)
    return db


@pytest.fixture
def mem():
    return ExperienceMemory()


# ── scoring policy ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "score,expected",
    [
        (5, "exemplar"),
        (4, "exemplar"),
        (3, None),   # deliberately unstored — teaching mediocrity is worse than silence
        (2, "antipattern"),
        (1, "antipattern"),
        (0, None),   # 0 means "not evaluated" in AgentState, NOT "terrible"
    ],
)
def test_score_classification(mem, score, expected):
    assert mem._classify(score) == expected


@pytest.mark.asyncio
async def test_score_zero_is_not_recorded_as_failure(mem, fake_db):
    """Regression guard: evaluator returns eval_score=0 when it errors or is
    skipped. Recording that as an anti-pattern would poison recall with runs
    that were never actually judged."""
    wrote = await mem.record(
        query="what is a pod?", answer="A pod is...", score=0, reasoning="Skipped",
        query_embedding=[1, 0, 0],
    )
    assert wrote is False
    assert fake_db.points == []


# ── write / read round trip ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exemplar_round_trip(mem, fake_db):
    await mem.record(
        query="how do I autoscale pods?",
        answer="Use a HorizontalPodAutoscaler targeting CPU.",
        score=5,
        reasoning="Comprehensive and well cited",
        query_embedding=[1, 0, 0],
    )
    exemplars, antipatterns = await mem.recall(
        query="how do I autoscale pods?", query_embedding=[1, 0, 0]
    )
    assert len(exemplars) == 1
    assert antipatterns == []
    assert "HorizontalPodAutoscaler" in exemplars[0].answer


@pytest.mark.asyncio
async def test_antipattern_recall_omits_the_bad_answer(mem, fake_db):
    """A failed answer must not be replayed verbatim into a later prompt —
    in-context examples get imitated. Only the judge's diagnosis is useful."""
    await mem.record(
        query="how do I autoscale pods?",
        answer="Just add more servers.",
        score=1,
        reasoning="Hallucinated; ignored the retrieved context",
        query_embedding=[1, 0, 0],
    )
    _, antipatterns = await mem.recall(
        query="how do I autoscale pods?", query_embedding=[1, 0, 0]
    )
    assert len(antipatterns) == 1
    block = antipatterns[0].as_antipattern_block()
    assert "Hallucinated" in block
    assert "Just add more servers" not in block


@pytest.mark.asyncio
async def test_tenant_isolation(mem, fake_db):
    await mem.record(
        query="internal runbook?", answer="Tenant A secret", score=5,
        reasoning="good", tenant_id="tenant-a", query_embedding=[1, 0, 0],
    )
    with patch("app.learning.store.settings") as s:
        s.EXPERIENCE_MEMORY_ENABLED = True
        s.SINGLE_TENANT_MODE = False
        s.EXPERIENCE_MEMORY_TOP_K = 2
        s.EXPERIENCE_MEMORY_THRESHOLD = 0.5
        exemplars, _ = await mem.recall(
            query="internal runbook?", tenant_id="tenant-b", query_embedding=[1, 0, 0]
        )
    assert exemplars == [], "tenant-b must not see tenant-a's experience"


# ── prompt assembly ────────────────────────────────────────────────────────

def test_prompt_block_empty_when_no_experience():
    assert build_experience_prompt_block({"exemplars": [], "antipatterns": []}) == ""


def test_prompt_block_labels_both_sections():
    block = build_experience_prompt_block({
        "exemplars": [{"query": "q1", "answer": "a1", "score": 5, "similarity": 0.9}],
        "antipatterns": [{"query": "q2", "reasoning": "hallucinated", "score": 1, "similarity": 0.8}],
    })
    assert "rated highly" in block
    assert "failure modes" in block
    assert "a1" in block
    assert "hallucinated" in block


# ── failure isolation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_failure_never_raises(mem):
    """Learning is an enhancement; the answer is the product. A broken store
    must degrade to no-learning, not to a failed request."""
    broken = AsyncMock()
    broken.upsert.side_effect = RuntimeError("qdrant down")
    with patch("app.learning.store._vectordb_client", broken):
        wrote = await mem.record(
            query="q", answer="a", score=5, reasoning="r", query_embedding=[1, 0, 0]
        )
    assert wrote is False


@pytest.mark.asyncio
async def test_recall_failure_returns_empty(mem):
    broken = AsyncMock()
    broken.search.side_effect = RuntimeError("qdrant down")
    with patch("app.learning.store._vectordb_client", broken):
        exemplars, antipatterns = await mem.recall(query="q", query_embedding=[1, 0, 0])
    assert exemplars == [] and antipatterns == []


@pytest.mark.asyncio
async def test_disabled_flag_is_a_hard_off_switch(mem, fake_db):
    with patch("app.learning.store.settings") as s:
        s.EXPERIENCE_MEMORY_ENABLED = False
        wrote = await mem.record(
            query="q", answer="a", score=5, reasoning="r", query_embedding=[1, 0, 0]
        )
        exemplars, antipatterns = await mem.recall(query="q", query_embedding=[1, 0, 0])
    assert wrote is False
    assert exemplars == [] and antipatterns == []
    assert fake_db.points == []


# ── the property that matters ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_loop_closes_across_runs(fake_db, monkeypatch):
    """
    THE test. Run 1 is graded; run 2 — a separate invocation with fresh state —
    must produce a different responder prompt as a consequence.

    Without this, the system only has the evaluator's within-run retry, which
    resets on every request and therefore never improves.
    """
    monkeypatch.setattr("app.learning.store.experience_memory", experience_memory)

    question = "how do I autoscale pods?"
    embedding = [1, 0, 0]

    # ---- Run 1: answered and graded well -------------------------------
    await experience_memory.record(
        query=question,
        answer="Use a HorizontalPodAutoscaler targeting CPU utilization.",
        score=5,
        reasoning="Accurate, grounded, well cited",
        query_embedding=embedding,
    )

    # ---- Run 2: brand-new state, nothing carried over in-process -------
    fresh_state = {
        "current_query": question,
        "query_embedding": embedding,
        "messages": [],
        "documents": [],
    }
    recalled = await experience_recall_node(fresh_state)
    fresh_state.update(recalled)

    assert len(fresh_state["exemplars"]) == 1, "run 2 did not recall run 1's outcome"

    block = build_experience_prompt_block(fresh_state)
    assert "HorizontalPodAutoscaler" in block, (
        "recalled experience never reached the responder prompt — the loop is "
        "still open"
    )


@pytest.mark.asyncio
async def test_recall_node_is_inert_without_a_query(fake_db):
    out = await experience_recall_node({"current_query": "   "})
    assert out == {"exemplars": [], "antipatterns": []}
