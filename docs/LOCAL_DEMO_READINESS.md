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
   cd services/api/frontend
   npm run dev -- --host 0.0.0.0
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

- Home: confirm seeded threads and pinned questions render.
- Sources: confirm live source health and the GitHub demo connector show.
- Resolution: run or inspect the support resolution workflow.

## Caveats To Say Out Loud

- Seeded business data is illustrative.
- The GitHub connector is a demo connection with placeholder credentials.
- Slack data is not connected in the local demo.
- Google Drive requires the OAuth flow before a real customer demo.
- Write-back actions are not enabled; the current demo is read-only.

## Local Verification Commands

```bash
make demo-ready-local
make support-demo
pytest
pytest services/control-plane/tests/ -x -q
make test-data-plane
ruff check
cd services/api/frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build:fast
```
