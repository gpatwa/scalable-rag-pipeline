from __future__ import annotations

import pytest

from app.resolution.evaluation import (
    action_validity,
    abstention_accuracy,
    citation_precision,
    evaluate_resolution,
    supported_claim_rate,
)


def test_metrics_match_hand_computed_values():
    report = evaluate_resolution(
        cited_labels=["[E1]", "[E9]", "[E1]"],
        authorized_labels=["[E1]", "[E2]"],
        supported=[True, False, True],
        predicted_abstentions=[False, True, False],
        expected_abstentions=[False, False, False],
        action_types=["draft_agent_response", "delete_events"],
        allowed_action_types=[["draft_agent_response"], ["route_to_human"]],
        latency_ms=125.5,
        input_tokens=100,
        output_tokens=40,
        estimated_cost=0.002,
    )
    assert report.metrics.citation_precision == pytest.approx(2 / 3)
    assert report.metrics.supported_claim_rate == pytest.approx(2 / 3)
    assert report.metrics.abstention_accuracy == pytest.approx(2 / 3)
    assert report.metrics.action_validity == pytest.approx(0.5)
    assert (report.latency_ms, report.input_tokens, report.output_tokens) == (125.5, 100, 40)


def test_empty_denominators_are_zero():
    assert citation_precision([], ["[E1]"]) == 0.0
    assert supported_claim_rate([]) == 0.0
    assert abstention_accuracy([], []) == 0.0
    assert action_validity([], []) == 0.0


@pytest.mark.parametrize("field", ["latency_ms", "input_tokens", "output_tokens", "estimated_cost"])
def test_negative_telemetry_is_rejected(field):
    values = dict(
        cited_labels=[], authorized_labels=[], supported=[], predicted_abstentions=[],
        expected_abstentions=[], action_types=[], allowed_action_types=[], latency_ms=0,
        input_tokens=0, output_tokens=0, estimated_cost=0,
    )
    values[field] = -1
    with pytest.raises(ValueError, match="non-negative"):
        evaluate_resolution(**values)
