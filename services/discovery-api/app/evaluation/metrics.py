"""Pure, backend-neutral evaluation metrics for immersive discovery."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


METRIC_VERSION = "v1"


@dataclass(frozen=True)
class MetricValue:
    metric_id: str
    version: str
    value: float

    def __post_init__(self) -> None:
        if not self.metric_id.strip():
            raise ValueError("metric_id must not be blank")
        if not self.version.strip():
            raise ValueError("metric version must not be blank")
        _finite(self.value, "metric value")

    def to_dict(self) -> dict[str, Any]:
        return {"metric_id": self.metric_id, "version": self.version, "value": self.value}


@dataclass(frozen=True)
class EvaluationReport:
    query_count: int
    cohort_labels: tuple[str, ...]
    metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        if self.query_count < 0:
            raise ValueError("query_count must not be negative")
        if len(set(self.cohort_labels)) != len(self.cohort_labels):
            raise ValueError("cohort labels must be unique")
        ids = [metric.metric_id for metric in self.metrics]
        if len(set(ids)) != len(ids):
            raise ValueError("metric IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_count": self.query_count,
            "cohort_labels": list(self.cohort_labels),
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


def recall_at_k(
    retrieved_ids: Sequence[str],
    relevance: Mapping[str, int],
    *,
    k: int = 10,
    minimum_grade: int = 1,
) -> float:
    """Fraction of judged relevant IDs found in the stable unique top-k."""
    _validate_k(k)
    _validate_grade(minimum_grade)
    relevant = {item_id for item_id, grade in relevance.items() if _grade(grade) >= minimum_grade}
    if not relevant:
        return 0.0
    return len(set(_unique_prefix(retrieved_ids, k)) & relevant) / len(relevant)


def mean_reciprocal_rank(
    retrieved_ids: Sequence[str],
    relevance: Mapping[str, int],
    *,
    k: int = 10,
    minimum_grade: int = 1,
) -> float:
    """Reciprocal rank of the first relevant unique result, or zero."""
    _validate_k(k)
    _validate_grade(minimum_grade)
    relevant = {item_id for item_id, grade in relevance.items() if _grade(grade) >= minimum_grade}
    for rank, item_id in enumerate(_unique_prefix(retrieved_ids, k), start=1):
        if item_id in relevant:
            return 1.0 / rank
    return 0.0


def mrr_at_k(
    retrieved_ids: Sequence[str], relevance: Mapping[str, int], *, k: int = 10, minimum_grade: int = 1
) -> float:
    """Alias with an explicit top-k name for report callers."""
    return mean_reciprocal_rank(retrieved_ids, relevance, k=k, minimum_grade=minimum_grade)


def ndcg_at_k(retrieved_ids: Sequence[str], relevance: Mapping[str, int], *, k: int = 10) -> float:
    """Graded normalized discounted cumulative gain over unique top-k IDs."""
    _validate_k(k)
    grades = {item_id: _grade(grade) for item_id, grade in relevance.items()}
    retrieved = _unique_prefix(retrieved_ids, k)
    actual = _discounted_gain((grades.get(item_id, 0) for item_id in retrieved))
    ideal = _discounted_gain(sorted(grades.values(), reverse=True)[:k])
    return 0.0 if ideal == 0.0 else actual / ideal


def catalog_coverage(retrieved_by_query: Mapping[str, Sequence[str]], catalog_ids: Sequence[str]) -> float:
    """Unique catalog items retrieved divided by the non-empty catalog size."""
    catalog = set(catalog_ids)
    if not catalog:
        raise ValueError("catalog denominator is undefined for an empty catalog")
    retrieved = {item_id for ids in retrieved_by_query.values() for item_id in _unique(ids) if item_id in catalog}
    return len(retrieved) / len(catalog)


def unique_creator_coverage(
    retrieved_by_query: Mapping[str, Sequence[str]],
    catalog_by_id: Mapping[str, Any],
) -> float:
    """Unique creators represented in results divided by catalog creator count."""
    catalog_creators = {_field(item, "creator_id") for item in catalog_by_id.values()}
    if not catalog_creators or any(not creator for creator in catalog_creators):
        raise ValueError("creator denominator is undefined for an empty or invalid catalog")
    retrieved_creators = {
        _field(catalog_by_id[item_id], "creator_id")
        for ids in retrieved_by_query.values()
        for item_id in _unique(ids)
        if item_id in catalog_by_id
    }
    return len(retrieved_creators & catalog_creators) / len(catalog_creators)


def intra_list_diversity(
    items: Sequence[Any],
    *,
    embeddings: Mapping[str, Sequence[float]] | None = None,
) -> float:
    """Mean pairwise distance, using cosine distance or categorical fallback.

    Empty and one-item lists are defined as zero. A zero vector (or a pair of
    zero vectors) uses the deterministic genre/theme Jaccard fallback.
    """
    if len(items) < 2:
        return 0.0
    distances = []
    for left_index, left in enumerate(items):
        for right in items[left_index + 1 :]:
            left_id, right_id = _field(left, "experience_id"), _field(right, "experience_id")
            left_vector = embeddings.get(left_id) if embeddings else None
            right_vector = embeddings.get(right_id) if embeddings else None
            if left_vector is not None and right_vector is not None and _has_nonzero_norm(left_vector) and _has_nonzero_norm(right_vector):
                distances.append(1.0 - _cosine(left_vector, right_vector))
            else:
                distances.append(_categorical_distance(left, right))
    return sum(distances) / len(distances)


def calibration_error(predicted_probabilities: Sequence[float], observed_outcomes: Sequence[int | bool], *, bins: int = 10) -> float:
    """Expected calibration error using equal-width probability bins."""
    if bins < 1:
        raise ValueError("bins must be at least 1")
    if len(predicted_probabilities) != len(observed_outcomes):
        raise ValueError("predicted probabilities and outcomes must have equal lengths")
    if not predicted_probabilities:
        return 0.0
    pairs = [(_probability(probability), _binary(outcome)) for probability, outcome in zip(predicted_probabilities, observed_outcomes)]
    error = 0.0
    for bin_index in range(bins):
        members = [pair for pair in pairs if min(int(pair[0] * bins), bins - 1) == bin_index]
        if members:
            error += len(members) / len(pairs) * abs(sum(pair[0] for pair in members) / len(members) - sum(pair[1] for pair in members) / len(members))
    return error


def negative_feedback_rate(outcomes: Sequence[int | bool]) -> float:
    """Fraction of observed binary outcomes marked as negative feedback."""
    if not outcomes:
        return 0.0
    values = [_binary(outcome) for outcome in outcomes]
    return sum(values) / len(values)


def policy_violation_rate(violations: Sequence[int | bool]) -> float:
    """Fraction of evaluated candidates or decisions that violated policy."""
    if not violations:
        return 0.0
    values = [_binary(violation) for violation in violations]
    return sum(values) / len(values)


def aggregate_report(
    retrieved_by_query: Mapping[str, Sequence[str]],
    relevance_by_query: Mapping[str, Mapping[str, int]],
    *,
    catalog_ids: Sequence[str] | None = None,
    catalog_by_id: Mapping[str, Any] | None = None,
    predicted_probabilities: Sequence[float] = (),
    observed_outcomes: Sequence[int | bool] = (),
    negative_feedback: Sequence[int | bool] = (),
    policy_violations: Sequence[int | bool] = (),
    cohort_labels: Sequence[str] = (),
    k: int = 10,
) -> EvaluationReport:
    """Create a stable, versioned report from independent metric inputs."""
    _validate_k(k)
    query_ids = sorted(relevance_by_query)
    metrics = [
        MetricValue("recall_at_k", METRIC_VERSION, _mean(recall_at_k(retrieved_by_query.get(query_id, ()), relevance_by_query[query_id], k=k) for query_id in query_ids)),
        MetricValue("mrr_at_k", METRIC_VERSION, _mean(mrr_at_k(retrieved_by_query.get(query_id, ()), relevance_by_query[query_id], k=k) for query_id in query_ids)),
        MetricValue("ndcg_at_k", METRIC_VERSION, _mean(ndcg_at_k(retrieved_by_query.get(query_id, ()), relevance_by_query[query_id], k=k) for query_id in query_ids)),
        MetricValue("calibration_error", METRIC_VERSION, calibration_error(predicted_probabilities, observed_outcomes)),
        MetricValue("negative_feedback_rate", METRIC_VERSION, negative_feedback_rate(negative_feedback)),
        MetricValue("policy_violation_rate", METRIC_VERSION, policy_violation_rate(policy_violations)),
    ]
    if catalog_ids is not None:
        metrics.append(MetricValue("catalog_coverage", METRIC_VERSION, catalog_coverage(retrieved_by_query, catalog_ids)))
    if catalog_by_id is not None:
        metrics.append(MetricValue("unique_creator_coverage", METRIC_VERSION, unique_creator_coverage(retrieved_by_query, catalog_by_id)))
    return EvaluationReport(len(query_ids), tuple(cohort_labels), tuple(metrics))


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _unique_prefix(values: Sequence[str], k: int) -> list[str]:
    return _unique(values)[:k]


def _discounted_gain(grades: Sequence[int] | Any) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def _grade(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("relevance grades must be non-negative integers")
    return value


def _validate_grade(value: int) -> None:
    _grade(value)


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")


def _finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _probability(value: float) -> float:
    value = _finite(float(value), "probability")
    if not 0.0 <= value <= 1.0:
        raise ValueError("probabilities must be between 0 and 1")
    return value


def _binary(value: int | bool) -> int:
    if value not in (0, 1, False, True):
        raise ValueError("outcomes must be binary")
    return int(value)


def _mean(values: Sequence[float] | Any) -> float:
    values = list(values)
    return 0.0 if not values else sum(values) / len(values)


def _field(item: Any, name: str) -> Any:
    value = item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)
    if value is None:
        raise ValueError(f"diversity item is missing {name}")
    return value


def _categorical_distance(left: Any, right: Any) -> float:
    left_features = set(_field(left, "genres")) | set(_field(left, "themes"))
    right_features = set(_field(right, "genres")) | set(_field(right, "themes"))
    union = left_features | right_features
    return 0.0 if not union else 1.0 - len(left_features & right_features) / len(union)


def _has_nonzero_norm(vector: Sequence[float]) -> bool:
    return bool(vector) and all(math.isfinite(float(value)) for value in vector) and math.sqrt(sum(float(value) ** 2 for value in vector)) > 0.0


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions must match")
    numerator = sum(float(a) * float(b) for a, b in zip(left, right))
    denominator = math.sqrt(sum(float(a) ** 2 for a in left)) * math.sqrt(sum(float(b) ** 2 for b in right))
    return max(-1.0, min(1.0, numerator / denominator))
