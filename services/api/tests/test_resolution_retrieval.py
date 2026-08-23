import pytest

from app.resolution.models import ConfidenceLevel, QueryMode, QueryVariant, SearchPlan
from app.resolution.retrieval import MultiQueryRetriever
from app.search.models import RetrievalSource, SearchResponse, SearchResult, SearchScope


def scope():
    return SearchScope(tenant_id="tenant-a", principal_id="agent", purpose="support", acl_tokens=("tenant:tenant-a",))


def result(document_id, score, rank, explanation=None):
    return SearchResult(document_id=document_id, tenant_id="tenant-a", source_type="kb", source_id=document_id,
                        title=document_id, text="evidence", score=score, rank=rank, retrieval_source=RetrievalSource.LEXICAL,
                        index_generation="g1", content_version="v1", permission_version="p1", explanation=explanation)


def plan(*variants):
    return SearchPlan(scope=scope(), variants=variants, reason="test", confidence=ConfidenceLevel.HIGH)


@pytest.mark.asyncio
async def test_maps_modes_preserves_scope_deduplicates_and_bounds():
    calls = []
    class Fake:
        async def search(self, request):
            calls.append(request)
            return SearchResponse(results=(result("a", 0.5, 2), result("b", 0.4, 1)), index_alias="x", index_generation="g1")
    variants = tuple(QueryVariant(query=str(i), mode=mode, reason="r", confidence=ConfidenceLevel.HIGH)
                    for i, mode in enumerate((QueryMode.EXACT, QueryMode.SEMANTIC, QueryMode.HYBRID, QueryMode.LEXICAL)))
    search_plan = plan(*variants)
    output = await MultiQueryRetriever(Fake(), per_query_result_limit=2, total_result_limit=1).retrieve(search_plan)
    assert len(calls) == 4
    assert all(call.scope is search_plan.scope for call in calls)
    assert [call.mode.value for call in calls] == ["lexical", "vector", "hybrid", "lexical"]
    assert len(output.results) == 1 and output.results[0].document_id == "a"
    assert output.executed_variants == 4


@pytest.mark.asyncio
async def test_failure_is_explicit_and_does_not_stop_other_variants():
    class Fake:
        async def search(self, request):
            if request.text == "bad":
                raise RuntimeError("down")
            return SearchResponse(results=(result("ok", 1, 1),), index_alias="x", index_generation="g1")
    output = await MultiQueryRetriever(Fake()).retrieve(plan(
        QueryVariant(query="bad", mode=QueryMode.LEXICAL, reason="r", confidence=ConfidenceLevel.LOW),
        QueryVariant(query="good", mode=QueryMode.LEXICAL, reason="r", confidence=ConfidenceLevel.LOW),
    ))
    assert output.partial and output.executed_variants == 2
    assert output.failures[0].query == "bad" and [r.document_id for r in output.results] == ["ok"]
