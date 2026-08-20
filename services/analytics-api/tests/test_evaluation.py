"""EA-060 to EA-065 deterministic evaluation and release gate tests."""
from app.evaluation import evaluate_case, release_gate
from packages.platform_contracts.analytics_intent import AnalyticalIntent, IntentMetric, SemanticContractReference
from packages.platform_contracts.evaluation import EvaluationCase


def intent():
    return AnalyticalIntent(
        query_id="q1", tenant_id="demo", dataset_id="orders",
        semantic_contract=SemanticContractReference(contract_id="sales", contract_version="v1"),
        metrics=[IntentMetric(metric_id="revenue")],
    )


def test_evaluation_grader_checks_typed_intent_and_outcome():
    case = EvaluationCase(case_id="c1", tenant_id="demo", question="revenue", expected_outcome="answer", expected_metric_ids=["revenue"], expected_dataset_id="orders")
    result = evaluate_case(case, outcome="answer", intent=intent())
    assert result.passed is True
    assert release_gate([result], "suite-1").blocked is False


def test_release_gate_blocks_regression():
    case = EvaluationCase(case_id="c1", tenant_id="demo", question="revenue", expected_outcome="answer", expected_metric_ids=["revenue"])
    result = evaluate_case(case, outcome="clarify", intent=intent())
    report = release_gate([result], "suite-1")
    assert report.blocked is True
    assert report.pass_rate == 0
