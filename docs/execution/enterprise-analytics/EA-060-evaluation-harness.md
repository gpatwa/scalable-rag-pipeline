# Task EA-060: Analytics Evaluation Harness

## Objective

Create a deterministic analytics evaluation package that consumes `EA-001`
fixtures and can later add dataset-selection and typed-intent graders without
rewriting the runner.

## Depends On

`EA-001` must be merged. Refresh the worktree before implementation. The typed
intent grader remains a documented extension point until `EA-012` exists.

## Allowed Scope

- A new `eval/analytics/` package and datasets
- Analytics evaluation tests under `services/analytics-api/tests/` or
  `eval/analytics/tests/`
- A new analytics-eval Make target if no other task owns `Makefile`
- CI changes only in a separate commit and only if the workflow has no active
  owner

Do not modify production query behavior, semantic metric definitions, public
contracts, support evaluation datasets, or existing report artifacts.

## Required Behavior

1. Define a versioned case format with question, domain, expected outcome,
   expected assets, expected metric IDs, reference SQL or intent, parameters,
   and expected result.
2. Separate runner, executor, graders, and report rendering.
3. Include deterministic graders for result equivalence, SQL parseability,
   selected physical assets, and outcome type.
4. Normalize row ordering, decimal representation, timestamps, and tolerances
   explicitly rather than through string comparison.
5. Reserve an extension point for typed-intent equivalence after `EA-012`.
6. Pin dataset and evaluator versions in every report.
7. Produce machine-readable JSON and a concise human-readable report.
8. Exit nonzero when required thresholds fail.
9. Do not require an external LLM or network access for the baseline suite.

## Acceptance Tests

- Equal results with different row order pass when order is not semantic.
- Numeric values within configured tolerance pass; values outside fail.
- Duplicate or missing rows fail.
- Incorrect dataset/table selection fails independently of final prose.
- Unsupported/refusal cases do not require SQL.
- A deliberately incorrect fanout result from the `EA-001` fixture fails.
- Re-running the same suite produces equivalent machine-readable output except
  for explicitly ignored timing metadata.

## Validation Commands

```bash
PYTHONPATH="$PWD/services/analytics-api:$PWD" \
  pytest services/analytics-api/tests eval/analytics -v --tb=short
git diff --check
```

## Deliverables

- Versioned eval dataset schema and baseline cases.
- Runner, deterministic graders, and report outputs.
- Tests for normalizers and failing cases.
- Local usage documentation and a proposed CI gate, even if CI wiring is
  deferred due to file ownership.

## Stop Conditions

- Required expected values are not available from merged `EA-001` artifacts.
- The task would need a live model or customer warehouse to pass locally.
- Another task owns `Makefile` or the CI workflow; leave a documented follow-up
  instead of creating a merge conflict.
