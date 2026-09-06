# ADS-009: M0 Integration Gate

Status: **Review**
Milestone: M0
Dependencies: ADS-003 agent-run-state contracts, ADS-004 typed tool registry,
ADS-005 PostgreSQL control-store schema, ADS-006 routing flags, ADS-007
baseline evidence, and ADS-008 compatibility boundary.

## Scope

The dedicated local test harness composes the existing state, transition,
routing, registry, and control-store contracts. It drives a deterministic fake
two-node graph through create, checkpoint, worker-loss/resume, and terminal
evidence. It also checks stale fencing rejection, outbox deduplication,
tenant/purpose scope, fail-closed routing, and absence of raw SQL/tool
execution authority.

The fake graph is test-only. This packet does not add a production graph
runner, API wiring, providers, cloud deployment, or ADS-030 functionality.

## Acceptance evidence and commands

```bash
PYTHONPATH=. pytest -q services/analytics-api/tests/test_ads009_m0_integration.py
PYTHONPATH=. pytest -q services/analytics-api/tests
ruff check services/analytics-api/tests/test_ads009_m0_integration.py
ruff format --check services/analytics-api/tests/test_ads009_m0_integration.py
ADS009_DATABASE_URL=postgresql://<local-user>:<local-password>@127.0.0.1:5432/<disposable-db> \\
  python3 scripts/analytics/ads009_postgres_drill.py
git diff --check
```

The full analytics suite and focused checks are evidence for review, not a
security approval. ADS-007 and ADS-008 remain compatibility/baseline inputs;
this packet does not reproduce or alter them.

## Live local PostgreSQL evidence

On 2026-09-06, PostgreSQL 15.0 was started from the local Docker Compose
`postgres:15-alpine` service. Alembic upgraded a disposable database through
`0002_agent_control_store`, and `scripts/analytics/ads009_postgres_drill.py`
passed the following checks:

```text
fencing_cas=pass
append_only_transition=pass
outbox_dedupe=pass
skip_locked_contention=pass
```

The disposable database was removed after the run. The shared local `rag_db`
was not used for drill data. This is local PostgreSQL evidence only; it does
not substitute for production topology, authorization/RLS, or security sign-off.

## M0 go/no-go checklist

- [x] Create, checkpoint, worker-loss resume, and terminal path is deterministic.
- [x] Every accepted fake transition carries evidence and a monotonic sequence.
- [x] Stale fencing, duplicate outbox delivery, scope, routing, and registry
  boundaries have negative assertions.
- [x] No production graph runtime, API, provider, cloud, manifest, or ADS-030
  change is included.
- [x] Local PostgreSQL concurrency/locking drill completed with migration,
  fencing CAS, append-only transition, outbox dedupe, and `SKIP LOCKED`
  contention evidence.
- [ ] Independent engineering review completed.
- [ ] Human/security reviewer signs the threat model.
- [ ] M0 go decision recorded by the authorized owner.

Until all unchecked items are resolved, the gate remains **Review** and must
not be described as complete or security-approved.
