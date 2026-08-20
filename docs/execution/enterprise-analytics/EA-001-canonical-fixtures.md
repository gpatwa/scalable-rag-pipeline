# Task EA-001: Canonical Analytics Fixtures

## Objective

Create a small deterministic Olist-compatible dataset and SQL-independent
expected results that expose aggregation-grain and join-fanout errors.

## Context

Current tests confirm that metadata exists but do not prove that business
metrics are correct. The fixture must become the source of truth for `EA-002`
metric corrections and `EA-060` evaluation.

## Allowed Scope

- `services/analytics-api/tests/fixtures/olist/**`
- A new test module under `services/analytics-api/tests/`
- Test-only helpers under `services/analytics-api/tests/`

Do not modify production analytics code, package contracts, dependency files,
CI, seed scripts, or existing demo values.

## Required Behavior

1. Represent at least six orders including delivered, canceled, and late cases.
2. Include one order with multiple items and one with split payments.
3. Include two product categories and at least two customers.
4. Store source rows in a deterministic, reviewable format such as CSV or JSON.
5. Store canonical expected values separately from SQL implementation.
6. Cover total delivered revenue, order count, average order value, item GMV,
   category item GMV, average review score, delivery duration, and late rate.
7. Include a regression demonstration showing how a direct payment-to-item join
   overcounts the multi-item order.
8. Document metric assumptions, especially delivered-only treatment and the
   distinction between order revenue and item GMV.

## Acceptance Tests

- Expected values are derived in test code from independent source rows, not
  imported from `schema_context.py` or copied from generated SQL.
- Split payments are aggregated to one order before average order value.
- Payment totals are not multiplied by item count.
- Canceled orders are excluded where the metric contract requires delivered
  orders.
- Reordering fixture rows does not change expected results.

## Validation Commands

```bash
PYTHONPATH="$PWD/services/analytics-api:$PWD" \
  pytest services/analytics-api/tests -v --tb=short
git diff --check
```

## Deliverables

- Canonical source fixtures.
- Canonical expected-result fixture or deterministic reference calculator.
- Focused tests and a short fixture README.
- Handoff listing exact expected values and unresolved semantic questions.

## Stop Conditions

- A metric requires a product decision not stated here.
- The task would need to modify production metric definitions.
- Existing unrelated changes conflict with the owned test paths.
