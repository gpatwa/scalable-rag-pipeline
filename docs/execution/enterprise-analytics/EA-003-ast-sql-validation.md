# Task EA-003: AST-Based SQL Validation

## Objective

Replace fragile text-oriented SQL inspection with dialect-aware PostgreSQL AST
validation while preserving the current validation API.

## Depends On

`EA-001` fixture shape should be stable. This task does not change metric
semantics.

## Allowed Scope

- `services/analytics-api/app/analytics/safety.py`
- SQL-safety tests under `services/analytics-api/tests/`
- `services/analytics-api/requirements.txt`

Do not modify the LLM prompt, engine orchestration, public API contracts,
semantic metadata, UI, support product, or root dependency manifests.

## Required Behavior

1. Use a maintained structured SQL parser with PostgreSQL dialect support.
2. Accept exactly one read-only query expression, including valid CTEs.
3. Reject DDL, DML, transaction, session, copy, command, and multi-statement
   constructs even when hidden in CTEs, comments, or unusual casing.
4. Resolve physical tables separately from CTE aliases and subquery aliases.
5. Enforce the existing physical-table allowlist.
6. Validate qualified physical columns without treating projected aliases as
   warehouse columns.
7. Apply a deny-by-default policy to unsafe functions and table-valued calls.
8. Keep `validate_sql(sql) -> tuple[bool, str]` compatible for callers.
9. Return stable, non-sensitive failure categories suitable for later v2
   mapping.
10. Preserve cost-guard behavior unless AST extraction can replace it without
    broadening accepted queries.

## Acceptance Tests

- Existing safety tests pass or are intentionally strengthened.
- Adversarial cases cover nested CTE writes, semicolon smuggling, comments,
  quoted identifiers, unknown schemas, set operations, subqueries, system
  catalogs, dangerous functions, and parser failures.
- Valid aggregate, grouped, window, CTE, and alias-heavy SELECT queries pass.
- Parser errors fail closed and do not expose stack traces to callers.

## Validation Commands

```bash
ruff check services/analytics-api/app/analytics/safety.py \
  services/analytics-api/tests
PYTHONPATH="$PWD/services/analytics-api:$PWD" \
  pytest services/analytics-api/tests -v --tb=short
git diff --check
```

## Deliverables

- AST-based validator and parser dependency.
- Focused malicious and valid-query corpus.
- Compatibility note and residual limitations.
- Handoff identifying constructs intentionally unsupported.

## Stop Conditions

- The selected parser license is incompatible with the repository.
- Correct validation requires a semantic contract not yet defined.
- A proposed change would turn the validator into the authorization boundary;
  that belongs to later policy/compiler tasks.
