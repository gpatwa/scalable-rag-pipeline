"""Pure, provider-neutral metrics for offline resolution evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ResolutionMetrics:
    citation_precision: float
    supported_claim_rate: float
    abstention_accuracy: float
    action_validity: float


@dataclass(frozen=True)
class ResolutionEvaluationReport:
    metrics: ResolutionMetrics
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float


def citation_precision(cited_labels: Sequence[str], authorized_labels: Sequence[str]) -> float:
    """Return the fraction of cited labels that are authorized."""
    cited = list(cited_labels)
    if not cited:
        return 0.0
    authorized = set(authorized_labels)
    return sum(label in authorized for label in cited) / len(cited)


def supported_claim_rate(supported: Sequence[bool]) -> float:
    """Return the fraction of claims supported by authorized evidence."""
    if not supported:
        return 0.0
    return sum(supported) / len(supported)


def abstention_accuracy(predicted: Sequence[bool], expected: Sequence[bool]) -> float:
    """Return exact-match accuracy for abstention decisions."""
    if len(predicted) != len(expected):
        raise ValueError("predicted and expected abstentions must have the same length")
    if not expected:
        return 0.0
    return sum(actual == target for actual, target in zip(predicted, expected)) / len(expected)


def action_validity(action_types: Sequence[str | None], allowed_types: Sequence[Sequence[str]]) -> float:
    """Return the fraction of proposed actions allowed by their case policy."""
    if len(action_types) != len(allowed_types):
        raise ValueError("action_types and allowed_types must have the same length")
    if not action_types:
        return 0.0
    return sum(action is not None and action in allowed for action, allowed in zip(action_types, allowed_types)) / len(action_types)


def evaluate_resolution(
    *,
    cited_labels: Sequence[str],
    authorized_labels: Sequence[str],
    supported: Sequence[bool],
    predicted_abstentions: Sequence[bool],
    expected_abstentions: Sequence[bool],
    action_types: Sequence[str | None],
    allowed_action_types: Sequence[Sequence[str]],
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    estimated_cost: float,
) -> ResolutionEvaluationReport:
    """Build a deterministic resolution report from already-collected values."""
    _validate_non_negative("latency_ms", latency_ms)
    _validate_non_negative("input_tokens", input_tokens)
    _validate_non_negative("output_tokens", output_tokens)
    _validate_non_negative("estimated_cost", estimated_cost)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ValueError("token counts must be integers")
    return ResolutionEvaluationReport(
        metrics=ResolutionMetrics(
            citation_precision(cited_labels, authorized_labels),
            supported_claim_rate(supported),
            abstention_accuracy(predicted_abstentions, expected_abstentions),
            action_validity(action_types, allowed_action_types),
        ),
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimated_cost,
    )


def _validate_non_negative(name: str, value: float | int) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be non-negative")
