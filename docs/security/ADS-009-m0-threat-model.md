# ADS-009 M0 Integration Threat Model

Status: **Review**
Security reviewer: ____________________  Date: __________  Decision: __________
Engineering reviewer: __________________  Date: __________  Decision: __________

This threat model covers the deterministic local M0 composition harness only.
Human and security approval are still pending; this document is not an
approval or a production-readiness claim.

## Trust boundaries and assets

| Boundary | Assets and authority | Required control |
|---|---|---|
| Caller to run state | tenant, purpose, request and graph identity | typed state validation; tenant/purpose carried on every fact |
| Worker to control store | checkpoints, leases, transition evidence | conditional fencing and append-only transition facts |
| Graph node to tool registry | tool identity, contracts, scope, retry/idempotency metadata | exact lookup; registry has metadata only and no executor |
| Route selection to governed action | rollout, approval and audit context | explicit enablement; disabled/legacy/shadow fail closed |
| Test harness to fake graph | synthetic state and evidence | test-only fake nodes; no provider, API, cloud, or customer rows |

Assets include run identity, immutable transition evidence, checkpoint history,
lease fencing sequence, outbox dedupe key, routing approval context, and
redacted diagnostics. Secrets, raw SQL, customer rows, and executable tool
handles are explicitly outside the harness.

## Attacker assumptions and abuse cases

Assume a malicious or faulty model/node can forge payload fields, request an
unknown tool, broaden tenant or purpose scope, replay an outbox event, submit
a stale worker write, or attempt to enable governed routing. Assume a worker
can crash after work and before checkpoint, and that an operator can receive
duplicate delivery. The harness tests these cases:

- stale fencing is rejected after a resumed worker owns a newer sequence;
- duplicate outbox delivery has one dedupe record;
- cross-tenant/purpose use is not admitted by the declared scope boundary;
- governed routing requires explicit rollout, approval, and audit evidence;
- disabled and implicit governed routes refuse action;
- raw SQL and tool-execution capabilities cannot be registered;
- a registry result exposes metadata, not an executable handle.

## Mitigations and residual risks

Typed Pydantic contracts reject unknown fields and malformed state, transitions
are authored and evidence-bearing, SQLite migration constraints exercise
checkpoint uniqueness and append-only facts, and the route/registry contracts
fail closed. The fake graph uses deterministic synthetic identifiers and does
not execute tools or SQL.

Residual risks are material: SQLite does not prove PostgreSQL locking or
production isolation; the harness is not a distributed crash drill; repository
compare-and-set and authorization/RLS wiring remain future work; adapter
idempotency and outbox claim behavior require live integration evidence; and
no security reviewer has signed off. These risks block a security approval and
must remain visible at the M0 go/no-go review.
