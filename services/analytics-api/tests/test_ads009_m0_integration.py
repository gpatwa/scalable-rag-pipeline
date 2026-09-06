"""ADS-009 deterministic M0 composition and security harness.

This is deliberately a test-only fake: it composes contracts and the durable
schema without becoming a production graph runner or tool executor.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from packages.platform_contracts.agent_runtime import (
    AgentRunState,
    EvidenceReference,
    RunBudget,
    TerminalOutcome,
    Transition,
)
from packages.platform_contracts.routing import (
    RoutingConfig,
    RoutingContext,
    RoutingRefusal,
    require_governed_action,
    resolve_route,
)
from packages.platform_contracts.tool_registry import (
    RiskClass,
    ToolRegistry,
    ToolRegistryError,
    ToolSpec,
)

SERVICE_ROOT = Path(__file__).parent.parent


def evidence(seq):
    return EvidenceReference(evidence_id=f"transition-{seq}", kind="transition", fingerprint=f"fp-{seq}")


def _db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ads009.db'}"
    monkeypatch.setenv("ANALYTICS_CONTROL_DB_URL", url)
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    command.upgrade(config, "head")
    return create_engine(url)


def test_fake_two_node_graph_create_checkpoint_worker_loss_resume_terminal(tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    state = AgentRunState(
        run_id="run-ads009",
        request_id="req-1",
        tenant_id="tenant-a",
        purpose="reporting",
        graph_version="fake-v1",
        current_node="create",
        context_snapshot_id="snapshot-1",
        budget=RunBudget(deadline=now + timedelta(minutes=5), max_transitions=32),
    )
    transitions = []

    def commit(from_node, to_node, sequence, fencing=1, status="active"):
        transition = Transition(
            run_id=state.run_id,
            tenant_id=state.tenant_id,
            graph_version=state.graph_version,
            sequence=sequence,
            from_node=from_node,
            to_node=to_node,
            from_status=state.status,
            to_status=status,
            idempotency_key=f"{state.run_id}:{sequence}",
            evidence=(evidence(sequence),),
        )
        transitions.append(transition)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE analytics_agent_runs SET current_node=:node, transition_seq=:seq WHERE run_id=:run"),
                {"node": to_node or from_node, "seq": sequence, "run": state.run_id},
            )
            conn.execute(
                text("""INSERT INTO analytics_run_transitions
                (run_id, transition_seq, tenant_id, from_node, to_node, from_status, to_status, fencing_seq, idempotency_key, evidence_payload)
                VALUES (:run, :seq, :tenant, :from_node, :to_node, :from_status, :to_status, :fence, :key, :evidence)"""),
                {
                    "run": state.run_id,
                    "seq": sequence,
                    "tenant": state.tenant_id,
                    "from_node": from_node,
                    "to_node": to_node,
                    "from_status": state.status,
                    "to_status": status,
                    "fence": fencing,
                    "key": transition.idempotency_key,
                    "evidence": '[{"evidence_id": "transition"}]',
                },
            )
        return transition

    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO analytics_agent_runs
            (run_id, tenant_id, purpose, graph_version, state_version, current_node, state_payload)
            VALUES (:run, :tenant, :purpose, 'fake-v1', 'v1', 'create', '{}')"""),
            {"run": state.run_id, "tenant": state.tenant_id, "purpose": state.purpose},
        )
    commit("create", "bootstrap", 1)
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO analytics_run_checkpoints
            (run_id, checkpoint_seq, tenant_id, graph_version, state_version, current_node, transition_seq, lease_fencing_seq, state_payload)
            VALUES (:run, 1, :tenant, 'fake-v1', 'v1', 'bootstrap', 1, 1, '{}')"""),
            {"run": state.run_id, "tenant": state.tenant_id},
        )
    # Worker A is lost; worker B resumes from the committed checkpoint.
    commit("bootstrap", "retrieve", 2)
    for seq, (source, target) in enumerate(
        (
            ("retrieve", "resolve"),
            ("resolve", "plan"),
            ("plan", "validate"),
            ("validate", "compile"),
            ("compile", "policy"),
        ),
        3,
    ):
        commit(source, target, seq)
    outcome = TerminalOutcome(
        kind="succeeded", summary_reference="summary-1", evidence=(evidence(9),), completed_at=now
    )
    commit("policy", None, 9, status="terminal")
    assert len(transitions) == 8 and all(t.evidence for t in transitions)
    assert outcome.kind == "succeeded"


def test_fencing_scope_outbox_dedupe_routing_and_registry_fail_closed(tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO analytics_agent_runs
            (run_id, tenant_id, purpose, graph_version, state_version, current_node, state_payload)
            VALUES ('run-2', 'tenant-a', 'reporting', 'fake-v1', 'v1', 'bootstrap', '{}')""")
        )
        conn.execute(
            text("""INSERT INTO analytics_run_leases
            (run_id, tenant_id, owner_id, lease_token, fencing_seq, expires_at)
            VALUES ('run-2', 'tenant-a', 'worker-b', 'lease-b', 2, CURRENT_TIMESTAMP)""")
        )
        conn.execute(
            text("""INSERT INTO analytics_run_outbox
            (tenant_id, run_id, event_type, dedupe_key, payload) VALUES ('tenant-a', 'run-2', 'checkpoint', 'once', '{}')""")
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text("""INSERT INTO analytics_run_outbox
                (tenant_id, run_id, event_type, dedupe_key, payload) VALUES ('tenant-a', 'run-2', 'checkpoint', 'once', '{}')""")
            )

    # The fake repository applies the same compare-and-set invariant required
    # by ADS-005: an old worker cannot commit after resume.
    def require_current_fence(candidate, current):
        if candidate < current:
            raise PermissionError("stale fencing sequence rejected")

    with pytest.raises(PermissionError, match="stale fencing"):
        require_current_fence(1, 2)
    context = RoutingContext(tenant_id="tenant-a", request_id="req-2", purpose="reporting")
    assert resolve_route(RoutingConfig(tenant_modes={"tenant-a": "disabled"}), context).execute_governed is False
    with pytest.raises(RoutingRefusal):
        require_governed_action(resolve_route(RoutingConfig(tenant_modes={"tenant-a": "governed"}), context))
    registry = ToolRegistry(
        (
            ToolSpec(
                tool_id="read_context",
                version="v1",
                capability="context.read",
                risk_class=RiskClass.READ,
                timeout_ms=1000,
                idempotency_mode="required",
                idempotency_key_required=True,
                input_contract_version="v1",
                output_contract_version="v1",
                required_scope="tenant_and_purpose",
            ),
        )
    )
    metadata = registry.lookup("read_context", "v1", input_contract_version="v1", output_contract_version="v1")
    assert not hasattr(metadata, "execute") and metadata.required_scope == "tenant_and_purpose"
    with pytest.raises(ToolRegistryError):
        ToolRegistry(
            (
                ToolSpec(
                    tool_id="raw",
                    version="v1",
                    capability="raw_sql",
                    risk_class=RiskClass.READ,
                    timeout_ms=1000,
                    idempotency_mode="none",
                    input_contract_version="v1",
                    output_contract_version="v1",
                    required_scope="tenant",
                ),
            )
        )
