# API Reference & Chat UI

## Chat UI

The platform includes a built-in dark-themed single-page application served at the root URL (`/`). No separate frontend deployment is needed.

- **Local:** `http://localhost:8000/`
- **Staging/Prod:** `https://api.your-domain.com/`
- **Port-forward:** `kubectl port-forward svc/api-service 8080:80` → `http://localhost:8080/`

### Features

- Real-time streaming responses (Server-Sent Events)
- Conversation history with session management
- Source attribution with document references
- Dark theme with responsive layout
- Works identically on AWS and Azure (backend-agnostic)

---

## Authentication

### Development Token

In `ENV=dev` mode, a convenience endpoint generates test tokens:

```bash
curl -X POST http://localhost:8000/auth/token \
    -H "Content-Type: application/json" \
    -d '{"username": "testuser", "tenant_id": "default"}'
```

Response:
```json
{
    "access_token": "eyJ...",
    "token_type": "bearer"
}
```

> This endpoint is disabled in staging/production. Use your configured IdP (Auth0, Azure AD, Cognito) instead.

### Production Auth Providers

| Provider | Env Var | Config |
|----------|---------|--------|
| Local JWT | `AUTH_PROVIDER=local` | Built-in, dev only |
| Auth0 | `AUTH_PROVIDER=auth0` | Set `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` |
| Azure AD | `AUTH_PROVIDER=azure_ad` | Set `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID` |
| AWS Cognito | `AUTH_PROVIDER=cognito` | Set `COGNITO_USER_POOL_ID`, `COGNITO_REGION` |

The API validates JWTs using JWKS (JSON Web Key Sets) fetched from the IdP at startup.

---

## Endpoints

### POST `/api/v1/chat/stream`

Stream a chat response using the agentic RAG pipeline.

**Request:**
```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "message": "Who founded Acme Corp?",
        "session_id": "optional-session-uuid",
        "model": "llama3"
    }'
```

**Response (Server-Sent Events):**
```
event: planner
data: {"node": "planner", "content": "Classifying intent..."}

event: retriever
data: {"node": "retriever", "content": "Found 3 relevant chunks"}

event: token
data: {"node": "responder", "content": "Acme"}

event: token
data: {"node": "responder", "content": " Corp"}

event: token
data: {"node": "responder", "content": " was founded by Jane Smith"}

event: sources
data: {"sources": [{"file": "company_overview.txt", "chunk_id": "c-001", "score": 0.92}]}

event: evaluator
data: {"node": "evaluator", "score": 0.87, "reasoning": "Answer is grounded in sources"}

event: done
data: {"session_id": "abc-123", "message_id": "msg-456"}
```

### POST `/api/v1/upload`

Get a presigned URL for direct document upload to S3/Blob Storage.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/upload \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"filename": "report.pdf", "content_type": "application/pdf"}'
```

**Response:**
```json
{
    "upload_url": "https://s3.amazonaws.com/rag-docs/...",
    "file_id": "f-789",
    "expires_in": 3600
}
```

The client PUTs the file directly to the presigned URL (no data goes through the API server).

### POST `/api/v1/feedback`

Submit feedback on a chat response (used for evaluation).

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/feedback \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message_id": "msg-456", "rating": "positive", "comment": "Accurate answer"}'
```

### GET `/health/liveness`

Kubernetes liveness probe — returns 200 if the process is running.

```bash
curl http://localhost:8000/health/liveness
# {"status": "ok"}
```

### GET `/health/readiness`

Kubernetes readiness probe — returns 200 if all dependencies are connected.

```bash
curl http://localhost:8000/health/readiness
# {"status": "ready", "checks": {"postgres": "ok", "redis": "ok", "qdrant": "ok"}}
```

---

## Streaming Protocol

The chat endpoint uses **Server-Sent Events (SSE)** for real-time streaming:

| Event Type | Description |
|------------|-------------|
| `planner` | Intent classification result |
| `retriever` | Retrieved chunks summary |
| `token` | Individual response tokens (streamed) |
| `sources` | Source documents with scores |
| `evaluator` | Answer quality score (0-1) |
| `done` | Stream complete, includes session/message IDs |
| `error` | Error details if pipeline fails |

### Client Integration

```javascript
const eventSource = new EventSource('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({ message: 'Hello', session_id: sessionId })
});

eventSource.addEventListener('token', (e) => {
    const data = JSON.parse(e.data);
    appendToChat(data.content);
});

eventSource.addEventListener('done', (e) => {
    eventSource.close();
});
```

---

## Sample Queries

### Basic RAG Query

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
    -H "Content-Type: application/json" \
    -d '{"username": "test"}' | jq -r .access_token)

curl -N http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message": "What is the companys mission statement?"}'
```

### With Session Context (Multi-Turn)

```bash
# First message
curl -N http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message": "Tell me about Project Alpha", "session_id": "session-1"}'

# Follow-up (remembers context)
curl -N http://localhost:8000/api/v1/chat/stream \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message": "Who is the lead on that project?", "session_id": "session-1"}'
```

### Debug Pipeline

Use the debug script to inspect the full retrieval pipeline:

```bash
python3 scripts/debug_pipeline.py "Who founded Acme Corp?"
# Outputs: embedding vector, Qdrant scores, Neo4j results, re-ranker scores, final answer
```

---

## Control Plane API (Split-Plane Mode)

In split-plane deployment, the control plane (`services/control-plane/`, port 8001) exposes the following additional endpoints. End-user chat/upload endpoints (`/api/v1/*`) are proxied through to the appropriate data plane.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/token` | None (dev only) | Generate a dev JWT token |

### Proxy (forwarded to data planes)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/chat/stream` | JWT | Proxied to tenant's data plane (streaming NDJSON pass-through) |
| `POST` | `/api/v1/upload` | JWT | Proxied to tenant's data plane |

### Tenant Administration

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/tenants/` | Admin JWT | Create a new tenant |
| `GET` | `/admin/tenants/` | Admin JWT | List all tenants |
| `GET` | `/admin/tenants/{id}` | Admin JWT | Get tenant details |
| `PATCH` | `/admin/tenants/{id}` | Admin JWT | Update tenant (plan, rate limit, enable/disable) |

### Data Plane Registry

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/data-planes/register` | Internal API key | Register a new data plane |
| `POST` | `/admin/data-planes/heartbeat` | Internal API key | Data plane heartbeat (health + metrics) |
| `GET` | `/admin/data-planes/` | Admin JWT | List all registered data planes |
| `DELETE` | `/admin/data-planes/{id}` | Admin JWT | Decommission a data plane |

### Usage Tracking

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/internal/usage/report` | Internal API key | Data plane reports usage events |
| `GET` | `/admin/usage/{tenant_id}` | Admin JWT | Get usage summary for a tenant |
| `GET` | `/admin/usage/` | Admin JWT | Get aggregated usage across all tenants |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health/liveness` | None | Control plane liveness probe |
| `GET` | `/health/data-planes` | Admin JWT | Health status of all registered data planes |

---

## Context Layer Admin API

When `CONTEXT_LAYERS_ENABLED=true`, these endpoints manage the structured business knowledge used to enrich RAG responses. All endpoints are tenant-scoped via JWT authentication.

### Annotations (Layer 2 — Glossary, KPIs, Notes)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/context/annotations` | JWT | Create a glossary term, KPI definition, or note |
| `GET` | `/api/v1/context/annotations` | JWT | List annotations (optional `?type=glossary\|kpi\|description\|note`) |
| `GET` | `/api/v1/context/annotations/{id}` | JWT | Get a single annotation |
| `PUT` | `/api/v1/context/annotations/{id}` | JWT | Update an annotation |
| `DELETE` | `/api/v1/context/annotations/{id}` | JWT | Delete an annotation |

**Create Example:**
```bash
curl -X POST http://localhost:8000/api/v1/context/annotations \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "annotation_type": "glossary",
        "key": "churn rate",
        "value": "Percentage of customers who stop using our service within a given period. Calculated as (lost customers / total customers at start) * 100."
    }'
```

### Business Rules (Layer 4 — Terminology, Rules, Org Context)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/context/business-rules` | JWT | Create a business rule or terminology entry |
| `GET` | `/api/v1/context/business-rules` | JWT | List rules (optional `?type=terminology\|business_rule\|role_context\|org_structure`) |
| `GET` | `/api/v1/context/business-rules/{id}` | JWT | Get a single rule |
| `PUT` | `/api/v1/context/business-rules/{id}` | JWT | Update a rule |
| `DELETE` | `/api/v1/context/business-rules/{id}` | JWT | Delete a rule |

**Create Example:**
```bash
curl -X POST http://localhost:8000/api/v1/context/business-rules \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "context_type": "terminology",
        "key": "ARR",
        "value": "Annual Recurring Revenue. Includes all subscription revenue normalized to a 12-month period. Excludes one-time fees and professional services.",
        "applies_to_roles": ["finance", "executive"],
        "priority": 10
    }'
```

### Code Context (Layer 3 — ETL, SQL, Data Lineage)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/context/code-context` | JWT | Create a code/pipeline context entry |
| `GET` | `/api/v1/context/code-context` | JWT | List entries (optional `?type=etl_pipeline\|sql_query\|api_endpoint\|data_lineage`) |
| `GET` | `/api/v1/context/code-context/{id}` | JWT | Get a single entry |
| `PUT` | `/api/v1/context/code-context/{id}` | JWT | Update an entry |
| `DELETE` | `/api/v1/context/code-context/{id}` | JWT | Delete an entry |

### Document Metadata (Layer 1 — Read-Only)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/context/metadata` | JWT | List document metadata (auto-populated during ingestion) |
| `GET` | `/api/v1/context/metadata/{document_id}` | JWT | Get metadata for a specific document |

### Streaming Event

When context layers are enabled, the chat stream includes an additional event:

| Event Type | Description |
|------------|-------------|
| `context_layers` | Business context assembled from all enabled layers (glossary, rules, metadata) |

---

## Data Analytics Streaming Events

When `DATA_ANALYTICS_ENABLED=true`, the chat stream includes additional event types for data queries:

| Event Type | Fields | Description |
|------------|--------|-------------|
| `sql_query` | `sql`, `time_ms` | Generated SQL query and execution time in ms |
| `data_result` | `columns`, `rows`, `row_count`, `table_html`, `chart_spec` | Query results with pre-rendered HTML table and Vega-Lite chart spec |
| `data_error` | `content` | Error message (validation failure, timeout, etc.) |

### Example: Data Query Response Stream

```
{"type":"status","node":"planner","session_id":"..."}
{"type":"status","node":"data_analytics","session_id":"..."}
{"type":"sql_query","sql":"SELECT DATE_TRUNC('month', ...) ...","time_ms":45,"session_id":"..."}
{"type":"data_result","columns":["month","revenue"],"rows":[...],"row_count":18,"table_html":"<table>...","chart_spec":{...},"session_id":"..."}
{"type":"status","node":"responder","session_id":"..."}
{"type":"answer","content":"Revenue showed a steady upward trend...","session_id":"..."}
```

### Dataset Management

| Command | Description |
|---------|-------------|
| `make seed-olist` | Load Olist e-commerce dataset (8 tables, 1.5M rows) |
| `make seed-dataset NAME=x PATH=data/x/` | Load any CSV dataset with auto-schema discovery |
| `make seed-dataset NAME=x KAGGLE=user/dataset` | Download from Kaggle and load |

---

## Data Plane API (Split-Plane Mode)

In split-plane deployment, the data plane (`services/data-plane/`, port 8080) exposes query processing endpoints. These are called by the control plane proxy, not directly by end users.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/chat/stream` | `X-DataPlane-Key` | Execute RAG pipeline (streaming NDJSON) |
| `POST` | `/api/v1/upload` | `X-DataPlane-Key` | Get presigned upload URL |
| `GET` | `/health/liveness` | None | Data plane liveness probe |
| `GET` | `/health/info` | None | Data plane metadata (ID, version, status) |

### Data Plane Headers

Requests from the control plane include these headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-DataPlane-Key` | Shared API key | Authenticate the control plane |
| `X-User-Id` | User ID from JWT | Forward authenticated user identity |
| `X-User-Role` | User role from JWT | Forward user role (admin/user) |

---

## Related Docs

- [Architecture & Design](architecture.md)
- [AWS Deployment](deployment-aws.md)
- [Azure Deployment](deployment-azure.md)
- [Operations Guide](operations.md)
