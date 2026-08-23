import pytest

from app.resolution.ranking import RerankCandidate, RerankItem, RerankRequest, RerankResult


def candidate(document_id="doc-1", rank=1):
    return RerankCandidate(
        document_id=document_id, original_rank=rank, original_score=0.5,
        source_type="article", source_id=document_id, index_version="idx-1",
        permission_version="perm-1", evidence_version="ev-1",
    )


def item(document_id="doc-1", score=0.8):
    return RerankItem(
        document_id=document_id, score=score, source_type="article", source_id=document_id,
        index_version="idx-1", permission_version="perm-1", evidence_version="ev-1",
    )


def request(*candidates_, max_candidates=20):
    return RerankRequest(query_id="q-1", query="reset password", scope_identity="tenant/t/principal/p", candidates=candidates_, max_candidates=max_candidates)


def test_result_must_be_a_closed_reordering_and_preserve_provenance():
    result = RerankResult(query_id="q-1", scope_identity="tenant/t/principal/p", items=(item("doc-2"), item()))
    assert result.validate_against(request(candidate(), candidate("doc-2", 2))) == result


@pytest.mark.parametrize("bad", [
    (candidate(), candidate()),
    (candidate(), candidate("doc-2", 1)),
])
def test_request_rejects_duplicate_candidates(bad):
    with pytest.raises(ValueError):
        request(*bad)


def test_request_rejects_candidate_bound_and_result_rejects_unknown_or_missing_ids():
    with pytest.raises(ValueError):
        request(candidate(), candidate("doc-2", 2), max_candidates=1)
    with pytest.raises(ValueError, match="exactly"):
        RerankResult(query_id="q-1", scope_identity="tenant/t/principal/p", items=(item("doc-3"),)).validate_against(request(candidate()))


def test_models_reject_extra_fields_and_scores_out_of_range():
    with pytest.raises(ValueError):
        item(score=1.1)
    with pytest.raises(ValueError):
        RerankCandidate(**{**candidate().model_dump(), "unexpected": True})
