# Enterprise Analytics Task Packets

These packets are the first bounded assignments from the
[Enterprise Analytics Roadmap](../../ENTERPRISE_ANALYTICS_EXECUTION_PLAN.md).
They are written for independent coding-model sessions and human reviewers.

## Dispatch Order

| Packet | Can start | Merge order | Primary ownership |
|---|---|---:|---|
| [EA-001](EA-001-canonical-fixtures.md) | Now | 1 | Analytics test fixtures only |
| [EA-070](EA-070-design-partner-scorecard.md) | Now | Independent | Discovery artifacts only |
| [EA-003](EA-003-ast-sql-validation.md) | After EA-001 fixture shape is stable | 2 | SQL safety and parser dependency |
| [EA-004](EA-004-v2-outcome-contract.md) | After EA-001 fixture shape is stable | 2 | New v2 contract module |
| [EA-060](EA-060-evaluation-harness.md) | After EA-001 merges | 3 | Analytics evaluation package |

`EA-003` and `EA-004` may run concurrently because their owned file sets do
not overlap. `EA-060` consumes the fixtures from `EA-001`; refresh its branch
after `EA-001` merges.

## Dispatch Rules

1. Give each model one packet and a fresh worktree.
2. Require a commit before handoff; do not accept an uncommitted diff as done.
3. Do not let a delegated model expand scope without returning a written stop
   condition.
4. Use a separate session for adversarial review.
5. Merge in the order above and run the analytics CI-equivalent commands after
   every merge.

## Integration Gate

From the repository root:

```bash
ruff check services/analytics-api/app services/analytics-api/tests packages
PYTHONPATH="$PWD/services/analytics-api:$PWD" \
  pytest services/analytics-api/tests -v --tb=short
git diff --check
```

Do not commit or discard unrelated work already present in the repository.
