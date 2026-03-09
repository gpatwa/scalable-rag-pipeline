# Operations Guide

CI/CD pipelines, observability, testing, security, and troubleshooting.

---

## CI/CD Pipelines

### GitHub Actions Workflows

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | PR + push to main | Lint (ruff), Test (pytest), Docker Build, Terraform Validate |
| `deploy-staging.yml` | Push to main | Build → Push to ECR/ACR → Helm upgrade staging |
| `deploy-prod.yml` | Manual dispatch | Approval gate → Re-tag image → Helm upgrade prod |

### CI Pipeline (`ci.yml`)

```
PR opened / push to main
  ├── Lint & Test
  │   ├── ruff check (linting)
  │   └── pytest (198 tests, SQLite mock)
  ├── Docker Build
  │   └── Buildx with GHA cache
  └── Terraform Validate
      ├── AWS (infra/terraform/)
      └── Azure (infra/terraform/azure/)
```

### Staging Deploy (Automatic)

Every merge to `main` triggers a staging deploy:

1. Build Docker image with tag `staging-<SHA>`
2. Push to ECR (AWS) and ACR (Azure)
3. Helm upgrade with `values-staging.yaml` (1 replica, DEBUG logs, LLM reranker)
4. Concurrency limit: 1 (new deploys cancel in-progress ones)

### Production Deploy (Manual)

```bash
# Trigger via GitHub Actions UI or CLI
gh workflow run deploy-prod.yml \
    -f cloud=aws \
    -f image_tag=staging-abc1234
```

1. **Approval gate** — requires environment approval
2. **Re-tag image** — `staging-abc1234` → `prod-abc1234`
3. **Helm upgrade** — `values-prod.yaml` (2 replicas, WARNING logs, cross-encoder reranker)

---

## Observability

### OpenTelemetry Integration

The API includes built-in tracing via OpenTelemetry, configured by environment:

| Env Var | Options | Description |
|---------|---------|-------------|
| `OTEL_EXPORTER` | `none`, `otlp`, `xray`, `azure_monitor` | Trace exporter |
| `OTEL_ENDPOINT` | URL | OTLP collector endpoint |

### AWS Observability

- **AWS X-Ray** — distributed tracing across API → Ray → Qdrant
- **CloudWatch** — container logs, Aurora metrics, Redis metrics
- **CloudWatch Alarms** — CPU, memory, error rate thresholds

### Azure Observability

- **Azure Monitor** — container insights, metrics
- **Application Insights** — distributed tracing, live metrics
- **Log Analytics** — centralized log queries (KQL)

### Structured Logging

The API uses structured JSON logging with configurable levels:

| Environment | Log Level | Reranker |
|-------------|-----------|----------|
| Dev | DEBUG | none |
| Staging | DEBUG | llm |
| Production | WARNING | cross_encoder |

---

## Testing

### Test Suite

198 tests across three service test suites:

| Suite | Count | Description |
|-------|-------|-------------|
| **Monolith** (`services/api/tests/`) | 132 | Config, auth, tenants, clients, agents, API endpoints, streaming, upload, providers |
| **Control Plane** (`services/control-plane/tests/`) | 48 | JWT auth, tenant CRUD, data plane registry, proxy routing, rate limiting, usage tracking |
| **Data Plane** (`services/data-plane/tests/`) | 18 | API key auth, user context extraction, TenantContext, health endpoints, registration, config |

### Running Tests

```bash
# Monolith tests (default)
make test

# Control plane tests only
make test-control-plane

# Data plane tests only
make test-data-plane

# All three suites (runs sequentially to avoid conftest.py collisions)
make test-all

# Specific test file
pytest services/control-plane/tests/test_cp_auth.py -v
pytest services/data-plane/tests/test_dp_auth.py -v

# With coverage
pytest services/api/tests/ --cov=services/api/app --cov-report=term-missing
```

> **Note:** The three test suites run in separate pytest sessions because each service has its own `conftest.py` with different path and module setup. `make test-all` handles this automatically.

### Test Environment

Tests use lightweight mocks — no Docker or cloud services needed:

- **Database:** SQLite in-memory via `aiosqlite` (instead of Postgres)
- **Redis:** Mock client
- **Qdrant:** Mock client
- **LLM:** Mock responses
- **Neo4j:** Mock client (when `GRAPHDB_PROVIDER=none`)
- **Control Plane DB:** SQLite in-memory (async via `aiosqlite`)
- **Data Plane auth:** Mock `Request` objects with `X-DataPlane-Key` headers

---

## Security

### Authentication & Authorization

- **JWT validation** on every API endpoint (`services/api/app/auth/jwt.py`)
- **JWKS** — public keys fetched from IdP at startup, cached with rotation
- **Multi-tenant isolation** — `tenant_id` from JWT used to scope all queries
- **RBAC** — role-based permissions per tenant

### Network Security

- **Private subnets** — databases (RDS, Redis, Neo4j) are not internet-accessible
- **NGINX Ingress** — TLS termination, rate limiting, proxy timeouts
- **Pod security** — non-root containers (uid 1000), read-only root filesystem

### Secrets Management

| Environment | Method |
|-------------|--------|
| Local dev | `.env` file (`SECRETS_PROVIDER=env`) |
| AWS | Secrets Manager + IRSA + External Secrets Operator |
| Azure | Key Vault + Workload Identity + External Secrets Operator |

Zero static credentials in production — pods authenticate via workload identity.

### Container Security

- Non-root user (uid 1000) in Dockerfile
- Health check in Dockerfile
- `.dockerignore` excludes `.env`, `.git`, `__pycache__`, `tests/`
- Minimal base image (125MB)

### Pre-commit Hooks

```bash
make setup  # Installs pre-commit hooks
```

Hooks run on every commit:
- `ruff` — Python linting
- `terraform_fmt` — Terraform formatting
- `detect-private-key` — prevents credential leaks

---

## Cost Optimization

### Karpenter Autoscaling

| Strategy | Savings | How |
|----------|---------|-----|
| SPOT instances | ~70% | Karpenter prefers SPOT for both CPU and GPU pools |
| GPU scale-to-zero | 100% idle | GPU nodes terminate 30s after last pod exits |
| Consolidation | variable | Karpenter repacks pods onto fewer nodes when underutilized |
| Burstable instances | ~60% vs general | t3a/t4g for dev, c6i/m6i for prod |

### Semantic Caching

Redis-based semantic cache avoids redundant LLM calls:
- Similar queries (cosine similarity > 0.95) return cached answers
- Cache hit latency: ~50ms vs ~2-5s for full RAG pipeline
- Reduces GPU inference costs proportional to query repetition

### Database Scaling

| Service | Dev | Production |
|---------|-----|------------|
| Aurora | 0.5 ACU min (nearly pauses idle) | 2+ ACU min |
| Qdrant | 1 replica, 20Gi | 3 replicas, 50Gi+ |
| Neo4j | 1 CPU / 2Gi | 4 CPU / 8Gi |
| Redis | t4g.micro (1 node) | r6g.large (2 nodes) |

---

## Troubleshooting

### Common Issues

#### Pods stuck in Pending

```bash
kubectl describe pod <pod-name>
# Look for: "Insufficient cpu/memory" or "no nodes available"
```

**Fix:** Check Karpenter logs — it may not have suitable node types configured:
```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter
```

#### PVC stuck in Pending

```bash
kubectl describe pvc <pvc-name>
```

**Common causes:**
- No EBS CSI driver installed → [Install EBS CSI](deployment-aws.md#3-ebs-csi-driver-required-for-pvcs)
- No `gp3` StorageClass → create one with `ebs.csi.aws.com` provisioner
- `WaitForFirstConsumer` — PVC binds when a pod schedules on a node

#### QDRANT_PORT collision with K8s service discovery

Kubernetes injects `<SERVICE>_PORT=tcp://...` for every service. If your Qdrant service is named `qdrant`, K8s sets `QDRANT_PORT=tcp://172.x.x.x:6333`, overriding your integer config.

**Fix:** Set `QDRANT_PORT=6333` explicitly in `app-env-secret`.

#### API CrashLoopBackOff

```bash
kubectl logs <api-pod> --previous
```

**Common causes:**
- Missing `REDIS_URL` in secret
- `QDRANT_PORT` collision (see above)
- Database connection refused (Aurora not started, wrong endpoint)

#### Karpenter iam:PassRole AccessDenied

The Karpenter controller needs `iam:PassRole` permission for the node role specified in `EC2NodeClass`.

**Fix:** Ensure the role name in `nodepool.yaml` matches the IAM role created by Terraform. The bootstrap script auto-detects this.

#### EC2NodeClass spec.role is immutable

Cannot patch `spec.role` on an existing EC2NodeClass. Must delete and recreate:

```bash
kubectl delete ec2nodeclass default gpu
kubectl apply -f <(envsubst < deploy/karpenter/nodepool.yaml)
```

### Log Collection

```bash
# API logs
kubectl logs -l app=api-service --tail=100

# Karpenter logs
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=50

# Ray head logs
kubectl logs -l ray.io/node-type=head --tail=50

# All events (sorted by time)
kubectl get events --sort-by=.metadata.creationTimestamp
```

### Health Checks

```bash
# Liveness (is the process alive?)
curl http://localhost:8080/health/liveness

# Readiness (are dependencies connected?)
curl http://localhost:8080/health/readiness

# From inside the cluster
kubectl exec -it <api-pod> -- curl localhost:8080/health/readiness
```

---

## Split-Plane Operations

### Running Locally

```bash
# Start control plane (port 8001)
make dev-control-plane

# Start data plane (port 8080)
make dev-data-plane

# Or run both via Docker Compose (with all dependencies)
make dev-split
```

### Data Plane Health Monitoring

The control plane runs a background health monitor that:

1. Scans all registered data planes every 60 seconds
2. Marks data planes as `unhealthy` if no heartbeat received for 90+ seconds
3. Unhealthy data planes are excluded from tenant routing
4. Decommissioned data planes are permanently excluded

```bash
# Check data plane health via admin API
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/health/data-planes

# View specific data plane status
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/admin/data-planes/
```

### Data Plane Lifecycle

| State | Description | Routing |
|-------|-------------|---------|
| `active` | Registered and healthy (heartbeat recent) | Included |
| `unhealthy` | No heartbeat for > 90 seconds | Excluded |
| `decommissioned` | Manually decommissioned via admin API | Permanently excluded |

### Troubleshooting Split-Plane

#### Data plane not receiving requests

1. Check registration: `GET /admin/data-planes/` on control plane
2. Check heartbeat: Is the data plane sending heartbeats every 30s?
3. Check health: Is the data plane marked `active`?
4. Check tenant mapping: Is the tenant's `tenant_id` associated with this data plane?

#### Streaming proxy timeout

The control plane uses `httpx.AsyncClient.stream()` with configurable timeouts. If data plane responses are slow:

```bash
# Check data plane health endpoints
curl http://<data-plane>:8080/health/liveness
curl http://<data-plane>:8080/health/info
```

#### Rate limit unexpectedly hit

```bash
# Check tenant's rate limit config
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/admin/tenants/<tenant_id>

# View usage stats
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8001/admin/usage/<tenant_id>
```

---

## Related Docs

- [Architecture & Design](architecture.md)
- [AWS Deployment](deployment-aws.md)
- [Azure Deployment](deployment-azure.md)
- [API Reference & Chat UI](api-reference.md)
