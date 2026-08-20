# Task EA-004: Analytics v2 Outcome Contract

## Objective

Define an additive v2 public contract that can represent successful answers,
clarification, refusal, human review, and operational failure without breaking
v1 clients.

## Depends On

Review the fixture terminology from `EA-001`. This task defines transport
contracts only; it does not wire routes or implement planner behavior.

## Allowed Scope

- A new module under `packages/platform_contracts/` dedicated to analytics v2
- `packages/platform_contracts/__init__.py` only if an export is required
- New contract tests under `services/analytics-api/tests/`
- Contract documentation/examples under `services/analytics-api/README.md`

Do not change v1 field meaning, API routes, service behavior, database models,
frontend code, or support-product contracts.

## Required Behavior

1. Define explicit outcome types: `answer`, `clarify`, `refuse`, `review`, and
   `failed`.
2. Every response carries contract version, query ID, tenant/user identity
   references, dataset/domain, timestamps, and outcome.
3. Answer evidence can carry semantic-contract versions, metric and dimension
   IDs, source assets, filters, generated SQL, result fingerprint, freshness,
   model/prompt versions, and policy decision references.
4. Clarification carries one or more structured questions and bounded choices
   without forcing choices when free text is required.
5. Refusal carries a stable reason code, safe explanation, and remediation when
   one exists.
6. Review carries review ID, risk reasons, expiry, and allowed reviewer actions.
7. Operational failure is distinguishable from semantic refusal.
8. Confidence and assumptions are optional and explicitly typed.
9. Sensitive reasoning traces and secrets have no public contract field.
10. Pydantic discriminated-union parsing rejects mismatched payloads.

## Acceptance Tests

- Round-trip examples pass for all five outcomes.
- Invalid outcome/payload combinations fail validation.
- Evidence defaults do not use mutable shared objects.
- v1 imports and tests remain unchanged and green.
- Generated JSON Schema is stable and contains a discriminator.

## Validation Commands

```bash
ruff check packages services/analytics-api/tests
PYTHONPATH="$PWD/services/analytics-api:$PWD" \
  pytest services/analytics-api/tests -v --tb=short
git diff --check
```

## Deliverables

- Additive v2 contract module.
- Contract tests and one example per outcome.
- Compatibility and eventual v1 retirement note.
- Handoff listing unresolved fields that require ADR decisions.

## Stop Conditions

- The implementation would need to change the current v1 route.
- Identity or policy semantics cannot be represented without an architecture
  decision; record the question rather than inventing the decision.
- Another active task owns the same contract file.
