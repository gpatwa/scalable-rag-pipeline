# ADS-009 Independent Review and Remediation Plan

Status: **Not ready for M0 approval**
Reviewed commit: `b9868b5`
Judge: GPT-5.6 Sol, high reasoning effort
Review type: independent engineering and security assessment
Date: 2026-09-06

## Decision summary

The independent judge recommends **NOT READY**. The existing tests and local
PostgreSQL drill demonstrate useful primitives, but they do not yet prove the
tenant isolation, durable recovery, contract alignment, or trusted authority
boundaries required by the M0 gate.

This document is an engineering aid, not a security approval. Only the
authorized engineering and security reviewers may close the actions below and
record the M0 go/no-go decision.

## Findings and required actions

| ID | Severity | Finding | Required action | Acceptance evidence | M0 impact |
|---|---|---|---|---|---|
| M0-01 | Critical | Child control-store rows can carry a tenant ID that differs from the parent run; purpose is not consistently carried through transition, routing, and tool boundaries. | Enforce run/tenant consistency with composite foreign keys or authoritative joins. Define the purpose authorization boundary. Carry purpose where it is part of authorization. Add negative PostgreSQL tests for mismatched checkpoint, lease, transition, and outbox rows plus route/tool scope. | A mismatched tenant or purpose cannot be inserted or admitted; tests pass on PostgreSQL. | Blocking |
| M0-02 | High | The fake graph does not reload a checkpoint after worker loss or persist a terminal outcome. Transition evidence is not proven contiguous and durable. | Simulate worker loss, acquire a new lease, reload and validate the last checkpoint, replay contiguous transitions, and atomically persist the terminal outcome, final checkpoint, run projection, and evidence. Reopen the database and assert the durable terminal state. | Recovery test proves new-owner resume, contiguous sequence, terminal status, validated `TerminalOutcome`, and complete evidence. | Blocking |
| M0-03 | High | Runtime statuses and PostgreSQL statuses diverge; checkpoint history is mutable; the drill does not prove expiry-aware lease acquisition or one atomic CAS transition. | Align status vocabularies across contracts and schema. Add immutable checkpoint protection. Implement and test expiry/nonterminal lease acquisition and a transactional CAS that checks expected node, status, sequence, and fencing token while writing the transition/checkpoint/projection. | Contract/schema matrix is versioned; PostgreSQL concurrency tests reject stale or expired ownership and checkpoint mutation. | Blocking |
| M0-04 | High | Governed routing trusts caller-provided evidence strings, and the tool registry relies on a narrow denylist. `allowed_purposes` is not enforced. | Derive governed enablement from a trusted authorization artifact or trusted caller boundary. Use an allowlisted capability taxonomy, reject SQL-bearing capabilities and aliases, and enforce purpose scope at the execution boundary. | Adversarial tests cannot self-enable governed execution or register a SQL/execution capability under an alternate name. | Blocking |
| M0-05 | High | Engineering review, security sign-off, and authorized go/no-go are not recorded. | Obtain independent architecture/engineering review, security disposition of residual risks, and the authorized owner’s M0 decision. Update the gate and threat-model sign-off fields with identity, date, decision, and evidence links. | Completed reviewer fields, decision record, and all blocking actions closed or explicitly accepted by the security owner. | Blocking |

## Accepted only with explicit sign-off

These items may remain deferred only if the security reviewer explicitly accepts
them in the M0 decision record:

- Production RLS and deployment-topology hardening beyond the local reference
  PostgreSQL drill.
- Distributed crash testing beyond the deterministic local recovery harness.
- Production graph-runner/API wiring and provider adapters reserved for later
  milestones.
- Adapter-level idempotent delivery beyond control-store enqueue deduplication.

An accepted residual risk must name the owner, affected boundary, mitigation,
expiry/review date, and follow-up milestone. Silence does not count as
acceptance.

## Evidence snapshot

- ADS-009 focused harness: `2 passed`.
- Analytics service suite: `166 passed`.
- Platform contract tests before ADS-009: `37 passed`.
- Local PostgreSQL 15 drill after the judge review setup: fencing CAS,
  append-only transition protection, outbox deduplication, and `SKIP LOCKED`
  contention all passed against a disposable database.
- The current M0 gate remains in `Review`; no security approval is implied.

## Review record

Engineering reviewer: ____________________  Date: __________  Decision: __________

Security reviewer: _______________________  Date: __________  Decision: __________

Authorized M0 owner: _____________________  Date: __________  Decision: __________

Remediation tracking issue/packet: ______________________________
