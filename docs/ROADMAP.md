# Product Roadmap

## Current State (v1.0)

### What's Production-Ready

| Area | Status | Details |
|------|--------|---------|
| Multi-tenancy | Strong | Per-tenant isolation in Postgres, Qdrant, Neo4j, S3/Blob. Immutable TenantConfig. Rate limits per tenant. |
| Authentication | Strong | JWT with JWKS/IdP support (Auth0, Azure AD, Cognito). Tenant + user context injection. |
| Testing | Strong | 173 tests — tenant auth, data isolation, VectorDB/GraphDB abstraction, storage, observability, secrets. |
| CI/CD | Strong | Trunk-based: lint → test → build → staging (auto) → prod (manual approval). |
| Multi-cloud | Strong | AWS (EKS, Aurora, S3, ECR) and Azure (AKS, Postgres Flex, Blob, ACR) with provider abstraction. |
| Secrets | Strong | Azure Key Vault + ESO + Workload Identity. AWS Secrets Manager + IRSA. No static credentials on pods. |
| Observability | Good | OpenTelemetry with X-Ray, Azure Monitor, OTLP. Structured JSON logging. |
| Container security | Good | Non-root, drop ALL capabilities, multi-stage builds, 125MB API image. |
| API design | Good | v1 prefix, Pydantic validation, per-tenant rate limiting with 429 + Retry-After. |
| Documentation | Good | Architecture docs, request flow, security guide, CONTRIBUTING.md. |

---

## Phase 1 — Security Hardening (Practical)

Priority: **High** | Effort: **1-2 days** | Blocks: production confidence

These are proportional security improvements — not full zero trust, which would be overkill at this stage.

### 1.1 TLS on Ingress
- [ ] Install cert-manager via Helm
- [ ] Create ClusterIssuer with Let's Encrypt
- [ ] Add TLS section to ingress template (`deploy/helm/api/templates/ingress.yaml`)
- [ ] Add HSTS annotation: `nginx.ingress.kubernetes.io/hsts: "true"`

### 1.2 CORS Lockdown
- [ ] Change `CORS_ORIGINS` default from `"*"` to empty string in `services/api/app/config.py`
- [ ] Set explicit allowed origins per environment in Helm values

### 1.3 API Pod NetworkPolicy
- [ ] Create `deploy/helm/api/templates/networkpolicy.yaml`
- [ ] Default deny all ingress/egress
- [ ] Allow ingress from ingress-nginx on port 8000
- [ ] Allow egress to Postgres (5432), Redis (6379/6380), Qdrant (6333/6334), Neo4j (7687)
- [ ] Allow egress to Key Vault / Secrets Manager endpoints (HTTPS 443)

### 1.4 Re-enable Access Logs
- [ ] Remove `logging.getLogger("uvicorn.access").disabled = True` from logging config
- [ ] Add request_id correlation to access log format

### 1.5 Encryption at Rest
- [ ] AWS: Add `storage_encrypted = true` to Aurora in `infra/terraform/rds.tf`
- [ ] AWS: Add `server_side_encryption_configuration` to S3 in `infra/terraform/s3.tf`
- [ ] Azure: Add `storage_mb` encryption settings to Postgres (enabled by default)
- [ ] Azure: Verify Blob Storage encryption (enabled by default, confirm CMK if needed)

---

## Phase 2 — Enterprise Features

Priority: **Critical for deals** | Effort: **2-3 weeks** | Blocks: enterprise sales

### 2.1 Admin API & Tenant Management
**Why:** Enterprises need self-service onboarding, not hardcoded tenant configs.

- [ ] Move tenant registry from static config to database table
- [ ] `POST /api/v1/admin/tenants` — create tenant with config (rate limits, quotas, features)
- [ ] `GET /api/v1/admin/tenants` — list all tenants with usage summary
- [ ] `PATCH /api/v1/admin/tenants/{id}` — update config, enable/disable
- [ ] `GET /api/v1/admin/tenants/{id}/usage` — queries, tokens, storage, active users
- [ ] Admin role check middleware (only `role=admin` can access `/admin/*`)
- [ ] Usage metering table — record per-request: tenant_id, user_id, tokens_in, tokens_out, timestamp

### 2.2 Data Governance (GDPR / SOC2)
**Why:** Deal-breaker for EU customers and any SOC2-audited buyer.

- [ ] `GET /api/v1/users/{id}/export` — export all user data as JSON (chat history, uploaded docs, feedback)
- [ ] `DELETE /api/v1/users/{id}/data` — cascade delete across Postgres, Qdrant, Neo4j, S3/Blob
- [ ] Configurable per-tenant data retention TTL on chat sessions
- [ ] Async cleanup job — purge expired sessions on schedule
- [ ] Audit log middleware — emit structured events: who accessed what resource, when, outcome
- [ ] Audit events stored in append-only table (or shipped to immutable log sink)

### 2.3 Database High Availability
**Why:** Required to commit to any uptime SLA (99.9%+).

- [ ] AWS: Uncomment second Aurora instance in `infra/terraform/rds.tf` (`two = {}`)
- [ ] AWS: Set Redis `num_cache_clusters = 2` in `infra/terraform/redis.tf`
- [ ] Azure: Set `zone_redundant = true` on Postgres Flexible Server
- [ ] Azure: Enable Redis geo-replication or zone redundancy
- [ ] Add PodDisruptionBudget to Helm chart (`minAvailable: 1`)
- [ ] Document RTO/RPO targets in `docs/disaster-recovery.md`

### 2.4 Python SDK
**Why:** Developers evaluate platforms by how fast they can integrate.

- [ ] Auto-generate typed client from OpenAPI spec (`openapi-python-client`)
- [ ] Package as `rag-platform-sdk` with retry logic, streaming support, typed responses
- [ ] Publish to private PyPI or Artifactory
- [ ] Include quickstart examples in SDK README
```python
from rag_platform import RAGClient

client = RAGClient(base_url="https://api.example.com", api_key="...")
response = client.chat("What does our policy say about remote work?")
print(response.answer)
```

### 2.5 Webhook / Event System
**Why:** Enterprise integrations are async — teams need to trigger downstream workflows.

- [ ] `POST /api/v1/webhooks` — register callback URL with event filter
- [ ] `GET /api/v1/webhooks` — list registered webhooks for tenant
- [ ] `DELETE /api/v1/webhooks/{id}` — unregister
- [ ] Event types: `document.ingested`, `document.failed`, `feedback.submitted`, `session.created`
- [ ] Async worker: poll events table, send HTTP POST to registered URLs with HMAC signature
- [ ] Retry with exponential backoff (3 attempts), dead letter after failure

---

## Phase 3 — Operational Maturity

Priority: **Medium** | Effort: **1-2 weeks** | Blocks: scale

### 3.1 Backup & Disaster Recovery
- [ ] Enable cross-region read replica for Aurora (warm standby)
- [ ] Enable Azure Postgres geo-redundant backup
- [ ] Automated backup restoration tests (weekly cron, verify integrity)
- [ ] Document failover runbook in `docs/disaster-recovery.md`
- [ ] S3/Blob cross-region replication for document storage

### 3.2 Observability Dashboards & Alerting
- [ ] Grafana dashboards: request latency (p50/p95/p99), error rate, active sessions per tenant
- [ ] Alert rules: error rate > 5%, latency p99 > 2s, pod restarts > 3 in 10min
- [ ] Business metrics: queries/day per tenant, token usage, cache hit rate
- [ ] On-call runbook for each alert

### 3.3 Load Testing
- [ ] k6 or Locust test suite simulating concurrent tenants
- [ ] Scenarios: sustained load, spike, long-running sessions
- [ ] Integrate into CI as nightly job (not blocking PRs)
- [ ] Document capacity limits (max concurrent users per pod, max throughput)

### 3.4 API Pagination & Versioning
- [ ] Add cursor-based pagination to chat history (`GET /api/v1/sessions?cursor=...&limit=20`)
- [ ] Add pagination to admin endpoints
- [ ] Document API deprecation policy (min 6 months notice)
- [ ] Support `Accept-Version` header for future breaking changes

---

## Phase 4 — Search Quality

Priority: **Medium** | Effort: **1-2 weeks** | Blocks: accuracy

### 4.1 Reranking
- [ ] Add cross-encoder reranking stage after vector retrieval
- [ ] Configurable per tenant (enable/disable, model choice)
- [ ] Compare retrieval quality with/without reranking via eval suite

### 4.2 Evaluation in CI
- [ ] Integrate Ragas eval suite (`eval/ragas/run.py`) into CI pipeline
- [ ] Maintain golden dataset of Q&A pairs per tenant
- [ ] Block deploys if faithfulness or relevancy drops below threshold
- [ ] Track eval scores over time (regression detection)

### 4.3 Feedback Loop
- [ ] Aggregate user feedback (thumbs up/down) per query pattern
- [ ] Surface low-scoring queries in admin dashboard
- [ ] Use negative feedback to improve retrieval (hard negative mining)

---

## Phase 5 — Zero Trust Architecture

Priority: **Low (unless compliance requires it)** | Effort: **3-4 weeks**

> **When to implement:** Only when compliance frameworks (SOC2 Type II, HIPAA, FedRAMP) or
> customer contracts explicitly require it. The security hardening in Phase 1 is sufficient
> for most enterprise deployments.

### 5.1 Service Mesh (mTLS)
- [ ] Deploy Istio or Linkerd to cluster
- [ ] Enable automatic mTLS for all pod-to-pod communication
- [ ] Configure strict PeerAuthentication (reject plaintext)
- [ ] Authorization policies: API → allowed backends only

### 5.2 Fine-Grained RBAC Enforcement
- [ ] Create `app/middleware/rbac.py` — evaluate `permissions` claim from JWT per endpoint
- [ ] Define permission matrix: `chat:read`, `chat:write`, `admin:read`, `admin:write`, `docs:upload`
- [ ] Route decorator: `@requires_permission("chat:write")`
- [ ] Return 403 with specific missing permission in error response

### 5.3 Secrets Rotation
- [ ] Key Vault rotation policy (90-day auto-rotate for DB passwords)
- [ ] Short-lived database credentials via Postgres Managed Identity (Azure) or IAM auth (AWS)
- [ ] JWT token refresh endpoint with sliding window
- [ ] Token revocation via Redis blacklist (check on every request)

### 5.4 Admission Control & Policy Enforcement
- [ ] Deploy OPA Gatekeeper or Kyverno
- [ ] Policies: only allow images from ACR/ECR, enforce resource limits, block privileged pods
- [ ] Pod Security Standards: enforce `restricted` profile via namespace labels
- [ ] Image signing with cosign in CI, verification in admission webhook

### 5.5 Network Microsegmentation
- [ ] NetworkPolicy per service (not just API — also Qdrant, Neo4j, Ray, Redis)
- [ ] Deny all by default, explicit allow per service dependency
- [ ] Separate namespaces: `rag-api`, `rag-data`, `rag-compute` with cross-namespace policies
- [ ] Egress policies: restrict outbound to known endpoints only

### 5.6 Comprehensive Audit Trail
- [ ] Audit every API call: user, tenant, action, resource, outcome, IP, timestamp
- [ ] Audit secret access via Key Vault diagnostic settings / CloudTrail
- [ ] Ship audit logs to immutable storage (S3 Glacier / Blob Archive with legal hold)
- [ ] Retention: 7 years for compliance, queryable via Athena / Log Analytics

### 5.7 WAF & DDoS Protection
- [ ] AWS: AWS WAF in front of ALB with managed rule groups (core, SQL injection, known bad inputs)
- [ ] Azure: Azure Front Door with WAF policy
- [ ] Per-user/per-tenant rate limiting (replace IP-only limiting)
- [ ] Geographic blocking if required by data residency

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-08 | Trunk-based development | Simpler than GitFlow for small team, faster feedback loop |
| 2026-03-08 | Skip full zero trust | Overkill for current stage — Phase 1 hardening is proportional to actual risk |
| 2026-03-08 | Prioritize admin API + GDPR over SDK | Unblocks procurement; SDK unblocks developer adoption (later) |
| 2026-03-08 | Single-region with backups | Cross-region DR deferred until SLA commitments require it |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-08 | Initial roadmap — security hardening, enterprise features, zero trust analysis |
