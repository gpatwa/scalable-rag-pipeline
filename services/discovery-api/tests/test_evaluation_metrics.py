import json
import math

import pytest

from app.evaluation.metrics import (
    EvaluationReport,
    aggregate_report,
    calibration_error,
    catalog_coverage,
    intra_list_diversity,
    mean_reciprocal_rank,
    ndcg_at_k,
    negative_feedback_rate,
    policy_violation_rate,
    recall_at_k,
    unique_creator_coverage,
)


def test_retrieval_metrics_deduplicate_and_match_hand_worked_values() -> None:
    retrieved = ["a", "a", "b", "c"]
    relevance = {"a": 3, "b": 1, "c": 0, "d": 2}
    assert recall_at_k(retrieved, relevance, k=3) == pytest.approx(2 / 3)
    assert mean_reciprocal_rank(retrieved, relevance, k=3) == pytest.approx(1.0)
    expected = (7 / math.log2(2) + 1 / math.log2(3)) / (7 / math.log2(2) + 3 / math.log2(3) + 1 / math.log2(4))
    assert ndcg_at_k(retrieved, relevance, k=3) == pytest.approx(expected)


def test_coverage_and_creator_coverage_deduplicate_results() -> None:
    retrieved = {"q1": ["a", "a", "b"], "q2": ["c"]}
    catalog = {"a": {"creator_id": "one"}, "b": {"creator_id": "one"}, "c": {"creator_id": "two"}, "d": {"creator_id": "three"}}
    assert catalog_coverage(retrieved, catalog) == pytest.approx(3 / 4)
    assert unique_creator_coverage(retrieved, catalog) == pytest.approx(2 / 3)


def test_diversity_uses_categorical_fallback_for_zero_vectors() -> None:
    items = [
        {"experience_id": "a", "creator_id": "one", "genres": ["puzzle"], "themes": ["ocean"]},
        {"experience_id": "b", "creator_id": "two", "genres": ["racing"], "themes": ["space"]},
        {"experience_id": "c", "creator_id": "three", "genres": ["puzzle"], "themes": ["ocean"]},
    ]
    assert intra_list_diversity(items, embeddings={"a": [0.0], "b": [0.0], "c": [0.0]}) == pytest.approx(2 / 3)
    assert intra_list_diversity([]) == 0.0


def test_calibration_feedback_and_policy_values() -> None:
    assert calibration_error([0.1, 0.9], [0, 1]) == pytest.approx(0.1)
    assert negative_feedback_rate([False, True, True, False]) == pytest.approx(0.5)
    assert policy_violation_rate([0, 1, 0, 0]) == pytest.approx(0.25)
    assert calibration_error([], []) == 0.0
    assert negative_feedback_rate([]) == 0.0
    assert policy_violation_rate([]) == 0.0


def test_empty_judgments_and_empty_retrieval_are_deterministic() -> None:
    assert recall_at_k([], {}) == 0.0
    assert mean_reciprocal_rank([], {}) == 0.0
    assert ndcg_at_k([], {}) == 0.0
    report = aggregate_report({}, {}, cohort_labels=["cold-start"])
    assert report.query_count == 0
    assert report.to_dict()["metrics"][0]["value"] == 0.0


def test_report_serialization_is_stable_and_versioned() -> None:
    report = aggregate_report(
        {"q1": ["a", "a"]},
        {"q1": {"a": 1}},
        catalog_ids=["a", "b"],
        cohort_labels=["new-user", "mobile"],
    )
    first = json.dumps(report.to_dict(), sort_keys=True)
    second = json.dumps(report.to_dict(), sort_keys=True)
    assert first == second
    assert {metric["version"] for metric in report.to_dict()["metrics"]} == {"v1"}
    assert isinstance(report, EvaluationReport)


@pytest.mark.parametrize("call", [
    lambda: recall_at_k(["a"], {"a": 1}, k=0),
    lambda: catalog_coverage({}, []),
    lambda: calibration_error([math.nan], [0]),
    lambda: calibration_error([0.5], [2]),
    lambda: negative_feedback_rate([0, 2]),
    lambda: policy_violation_rate([False, "unknown"]),
])
def test_invalid_or_ambiguous_inputs_fail_clearly(call) -> None:
    with pytest.raises(ValueError):
        call()
