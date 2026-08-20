# Local Demo Readiness

This checklist verifies the Compass demo locally only. It does not deploy to
Azure, AWS, or any remote environment.

## Start

1. Start Docker Desktop.
2. Run the local API:

   ```bash
   make dev
   ```

3. In another terminal, run the frontend:

   ```bash
   make dev-support-web
   ```

4. Run the local demo gate:

   ```bash
   make demo-ready-local
   ```

## Expected URLs

- Frontend: http://localhost:5173
- API: http://localhost:8080
- API readiness: http://localhost:8080/health/readiness

## Demo Path

- Resolution (`/`): run the support resolution workflow.
- Knowledge chat (`/home`): confirm seeded threads and pinned questions render.
- Sources: confirm live source health and the GitHub demo connector show.

## Caveats To Say Out Loud

- Seeded business data is illustrative.
- The GitHub connector is a demo connection with placeholder credentials.
- Slack data is not connected in the local demo.
- Google Drive requires the OAuth flow before a real customer demo.
- The Trust + Execution demo persists commands, approvals, audit events, and local mock
  artifacts. External write-back to helpdesks, KBs, CRM, or product trackers is not enabled.

## Local Verification Commands

```bash
make demo-ready-local
make support-demo
pytest
pytest services/control-plane/tests/ -x -q
make test-data-plane
ruff check
cd apps/support-web && npm run lint && npm run typecheck && npm test -- --run && npm run build:fast
```

The analytics product has a separate local gate and is not required for the
support prospect demo:

```bash
make seed-olist
make dev-analytics-api
make dev-analytics-web
make test-analytics
```

Analytics web runs at http://localhost:5174 and analytics API at
http://localhost:8090.
