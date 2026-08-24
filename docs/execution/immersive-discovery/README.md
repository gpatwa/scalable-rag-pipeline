# Immersive Discovery Task Packets

The canonical task list, dependencies, dispatch waves, trust rules, and local
release gates are maintained in the
[Immersive Discovery Vertical Execution Plan](../../IMMERSIVE_DISCOVERY_EXECUTION_PLAN.md).

Use one task ID per Luna session. Give Luna the canonical plan and exactly one
packet. Do not include unrelated chat history, cloud credentials, or broad
repository context.

Current checkpoint: **IMD-005, IMD-007, IMD-010, and IMD-020 complete**.
IMD-001 through IMD-005, IMD-007, IMD-010, and IMD-020 are merged and
validated. The next packetized wave is IMD-006, IMD-011, IMD-012, and IMD-021;
later tasks are backlog rows, not executable prompts, until the
integration owner creates and reviews their exact packet one merge wave ahead.
This just-in-time packet rule keeps owned paths and validation commands aligned
with the code that actually merged.

Next dispatch wave:

- [IMD-006](IMD-006-test-fakes.md) — deterministic discovery test fakes
- [IMD-011](IMD-011-local-configuration.md) — local configuration and flags
- [IMD-012](IMD-012-repository-protocols.md) — provider-neutral repositories
- [IMD-021](IMD-021-catalog-mapping.md) — versioned catalog mapping

## First Dispatch Wave

| Task | Purpose | Can run concurrently |
|---|---|---|
| [IMD-001](IMD-001-architecture-adr.md) | Separate-product architecture ADR | Yes, with IMD-002 |
| [IMD-002](IMD-002-golden-discovery-corpus.md) | Fictional discovery golden corpus | Yes, with IMD-001 |

Merge and review both before dispatching shared or immersive domain contracts.

## Packet Rules

- Name packets `IMD-NNN-short-description.md`.
- Copy dependencies, exact reads, owned files, acceptance evidence, targeted
  tests, stop conditions, and commit subject from the canonical plan.
- Keep one task to one commit and within the Luna limits in Section 8.
- Do not let a delegated task add discovery code to the support or analytics
  products.
- Do not browse, scrape Roblox, download external data, call a live model, or
  deploy infrastructure unless a future packet explicitly authorizes it.
- The integration owner reviews and pushes after every merge wave.
- Do not dispatch a task represented only by the canonical table row.

## Integration Gate

Once the discovery deployables exist, the integration owner runs:

```bash
ruff check services/discovery-api/app services/discovery-api/tests packages
PYTHONPATH="$PWD/services/discovery-api:$PWD" \
  pytest services/discovery-api/tests -q
npm --prefix apps/discovery-web run typecheck
npm --prefix apps/discovery-web test -- --run
npm --prefix apps/discovery-web run build
git diff --check
```

Before those paths exist, documentation and fixture packets run only their
targeted checks. Do not commit or discard unrelated work in the repository.
