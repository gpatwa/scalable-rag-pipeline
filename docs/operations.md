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
  │   └── pytest (132 tests, SQLite mock)
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

132 tests covering:

| Category | Count | Description |
|----------|-------|-------------|
| Unit Tests | ~90 | Config, auth, tenants, clients, agents |
| Integration | ~30 | API endpoints, streaming, upload flow |
| Provider Tests | ~12 | Factory pattern, provider switching |

### Running Tests

```bash
# Full suite
make test
# Or: pytest tests/ -x -q

# Specific category
pytest tests/test_config.py -v
pytest tests/test_agents.py -v
pytest tests/test_reranker.py -v

# With coverage
pytest tests/ --cov=services/api/app --cov-report=term-missing
```

### Test Environment

Tests use lightweight mocks — no Docker or cloud services needed:

- **Database:** SQLite in-memory (instead of Postgres)
- **Redis:** Mock client
- **Qdrant:** Mock client
- **LLM:** Mock responses
- **Neo4j:** Mock client (when `GRAPHDB_PROVIDER=none`)

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

## Related Docs

- [Architecture & Design](architecture.md)
- [AWS Deployment](deployment-aws.md)
- [Azure Deployment](deployment-azure.md)
- [API Reference & Chat UI](api-reference.md)
