"""Evaluation graders that do not require an LLM judge."""
from __future__ import annotations

from packages.platform_contracts.analytics_intent import AnalyticalIntent
from packages.platform_contracts.evaluation import EvaluationCase, EvaluationResult, ReleaseGateReport


def evaluate_case(case: EvaluationCase, *, outcome: str, intent: AnalyticalIntent | None = None, sql_fingerprint: str | None = None) -> EvaluationResult:
    metric_ids = {metric.metric_id for metric in intent.metrics} if intent else set()
    metric_match = set(case.expected_metric_ids) == metric_ids
    dataset_match = case.expected_dataset_id is None or (intent is not None and intent.dataset_id == case.expected_dataset_id)
    sql_match = None if case.expected_sql_fingerprint is None else sql_fingerprint == case.expected_sql_fingerprint
    passed = outcome == case.expected_outcome and metric_match and dataset_match and (sql_match is None or sql_match)
    return EvaluationResult(case_id=case.case_id, outcome=outcome, metric_match=metric_match, dataset_match=dataset_match, sql_match=sql_match, passed=passed)


def release_gate(results: list[EvaluationResult], suite_version: str, minimum_pass_rate: float = 1.0) -> ReleaseGateReport:
    passed = sum(result.passed for result in results)
    total = len(results)
    rate = passed / total if total else 0.0
    reasons = [] if rate >= minimum_pass_rate else [f"pass rate {rate:.3f} below required {minimum_pass_rate:.3f}"]
    return ReleaseGateReport(suite_version=suite_version, total_cases=total, passed_cases=passed, pass_rate=rate, blocked=bool(reasons), reasons=reasons)
