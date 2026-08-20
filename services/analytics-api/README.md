# Compass Analytics API

Standalone FastAPI service for guarded text-to-SQL analytics. It owns schema
grounding, LLM configuration, SQL safety, read-only execution, chart result
assembly, and analytics-specific tests.

The service depends on the public v1 models in
`packages/platform_contracts/analytics.py`. It does not import support API
routes, graph state, models, or connectors.

## Local Development

```bash
make install-analytics
make seed-olist
make dev-analytics-api
```

The API listens on http://localhost:8090. Configure it from
`services/analytics-api/.env.example`.

```bash
make test-analytics
curl http://localhost:8090/health
curl -X POST http://localhost:8090/api/v1/analytics/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Revenue by month"}'
```

`ANALYTICS_API_KEY` is optional for local development. When set, clients must
send the value in `X-API-Key`.
