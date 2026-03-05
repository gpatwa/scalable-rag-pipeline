# AWS Deployment — Cost-Effective Dev/Learning Setup

## Context

The codebase works locally and is architecturally solid. The goal is to deploy to AWS for **development and learning**, keeping costs low while preserving the full Ray Serve + vLLM architecture. GPU workers will scale to zero when idle, only incurring cost during active use.

---

## Estimated Monthly Cost After Optimizations

| Resource | Config | Est. Cost/mo |
|----------|--------|-------------|
| EKS Control Plane | 1 cluster | $73 |
| NAT Gateway | 1 single gateway | $32 |
| EKS System Node (t3a.medium SPOT) | 1 node | ~$11 |
| App Worker Node (t3a.medium SPOT) | 1 node for API + Qdrant + Neo4j | ~$11 |
| Aurora Serverless v2 (min 0.5 ACU) | scales to 0.5 when idle | ~$22 |
| ElastiCache Redis (t4g.micro) | 1 node | ~$9 |
| S3 Bucket | minimal storage | ~$1 |
| EBS Volumes (Neo4j 20Gi + Qdrant 20Gi) | 40Gi gp3 | ~$3 |
| Ray GPU (g5.xlarge SPOT, scale-to-zero) | 0 when idle, ~$0.60/hr active | $0 idle |
| Ray CPU workers (t3a.medium SPOT) | 0 min, on-demand | $0 idle |
| **Baseline (idle)** | | **~$162/mo** |
| **With GPU active 2 hrs/day** | | **~$198/mo** |

---

## Phase 1: Terraform Cost Optimizations

### 1.1 Lower Aurora ACU minimum
- **File:** `infra/terraform/rds.tf`
- `min_capacity = 2` → `min_capacity = 0.5`
- Saves ~$65/mo — Aurora nearly pauses when idle

### 1.2 Downsize Ray cluster for dev
- **File:** `deploy/ray/ray-cluster.yaml`
- CPU workers: `maxReplicas: 50` → `maxReplicas: 3`, resources `8 CPU / 32Gi` → `2 CPU / 8Gi`
- GPU workers: keep `minReplicas: 0` (scale-to-zero), `maxReplicas: 20` → `maxReplicas: 2`
- GPU resources: `4 CPU / 32Gi` → `4 CPU / 16Gi`
- Head node: `2 CPU / 8Gi` → `1 CPU / 4Gi`

### 1.3 Reduce Qdrant to 1 replica
- **File:** `deploy/helm/qdrant/values.yaml`
- `replicaCount: 3` → `replicaCount: 1`, storage `50Gi` → `20Gi`
- Resources: `2-4 CPU / 4-8Gi` → `1 CPU / 2Gi` (requests), `2 CPU / 4Gi` (limits)

### 1.4 Reduce Neo4j resources
- **File:** `deploy/helm/neo4j/values.yaml`
- Resources: `2 CPU / 8Gi` → `1 CPU / 2Gi`
- Storage: `100Gi` → `20Gi`

### 1.5 Update budget alert
- **File:** `infra/terraform/budgets.tf`
- `limit_amount = "15"` → `limit_amount = "200"`

### 1.6 Disable S3 Transfer Acceleration
- **File:** `infra/terraform/s3.tf`
- Change `status = "Enabled"` → `status = "Suspended"` on `aws_s3_bucket_accelerate_configuration`
- Not needed for dev (saves per-GB transfer fees)

---

## Phase 2: Fixes Required for Working Deployment

### 2.1 Secure secrets
- **File:** `.gitignore` — add `terraform.tfvars` and verify `.env` is listed
- **File:** `infra/terraform/terraform.tfvars` → create `terraform.tfvars.example` with placeholders
- Password in `terraform.tfvars` must be rotated after deploy

### 2.2 Add CORS middleware
- **File:** `services/api/main.py`
- Add `CORSMiddleware` with `allow_origins` from settings (configurable via env)
- Add `CORS_ORIGINS` to `services/api/app/config.py`

### 2.3 Add health probes to Helm
- **File:** `deploy/helm/api/templates/deployment.yaml`
- Add `livenessProbe`: `httpGet /health/liveness`, period 30s, timeout 3s, failureThreshold 3
- Add `readinessProbe`: `httpGet /health/readiness`, period 10s, timeout 3s, failureThreshold 1
- Add `startupProbe`: `httpGet /health/liveness`, period 5s, failureThreshold 30

### 2.4 Fix Helm image reference
- **File:** `deploy/helm/api/templates/values.yaml`
- `repository: rag-backend-api` → `repository: <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/rag-backend-api`
- `tag: latest` → `tag: "{{ .Chart.AppVersion }}"`

### 2.5 Wire up observability
- **File:** `services/api/main.py`
- Add `setup_observability(app)` call in lifespan startup (function already exists)

### 2.6 Harden API Dockerfile
- **File:** `services/api/Dockerfile`
- Add non-root user: `RUN useradd -r -u 1000 appuser` + `USER appuser`
- Add `HEALTHCHECK CMD curl -f http://localhost:8080/health/liveness || exit 1`
- Add `.dockerignore` to exclude `.env`, `.git`, `__pycache__`, `tests/`

### 2.7 Add Karpenter NodePool for GPU SPOT
- **File:** New `deploy/karpenter/nodepool.yaml`
- Define NodePool with `g5.xlarge` SPOT for GPU, `t3a.medium` SPOT for general
- Set `ttlSecondsAfterEmpty: 300` (5 min idle → node terminated)
- This is what makes scale-to-zero actually work

### 2.8 Add app worker node group (untainted)
- **File:** `infra/terraform/eks.tf`
- Add second managed node group `app` without taints (system nodes have `CriticalAddonsOnly` taint, so app pods can't schedule there)
- Or: remove taint from system group (simpler for dev)

---

## Phase 3: Nice-to-Have (Do Later)

- Add basic test suite (`tests/`)
- Add GitHub Actions CI/CD (build → ECR → helm upgrade)
- Add Alembic for database migrations
- Add NetworkPolicy
- Add HPA for API auto-scaling
- Add TLS to Ingress with cert-manager

---

## Gap Analysis Summary

### What's Already Good
- Terraform modules: VPC, EKS, Aurora Serverless, ElastiCache, S3, IAM/IRSA, Karpenter
- SPOT instances for system nodes (70% savings)
- Single NAT gateway ($32/mo vs $96/mo)
- Graviton Redis (t4g.micro — cheapest option)
- Aurora Serverless v2 (scales with load)
- Ray GPU workers at minReplicas: 0 (scale-to-zero ready)
- Budget alerts configured
- ExternalSecrets integration for K8s secrets from AWS Secrets Manager
- Helm charts for API, Neo4j, Qdrant
- Bootstrap and shutdown scripts

### What's Missing or Broken

| Category | Issue | Severity |
|----------|-------|----------|
| **Security** | DB password plaintext in `terraform.tfvars` | CRITICAL |
| **Security** | No CORS middleware on FastAPI | HIGH |
| **Security** | API Dockerfile runs as root | HIGH |
| **K8s** | No liveness/readiness probes in Helm | HIGH |
| **K8s** | System nodes have taint, no app nodes defined | HIGH |
| **K8s** | No Karpenter NodePool defined | HIGH |
| **K8s** | Helm image tag is `latest` (not versioned) | MEDIUM |
| **Observability** | `setup_observability()` exists but never called | MEDIUM |
| **Cost** | Aurora min 2 ACU ($87/mo when idle) | MEDIUM |
| **Cost** | S3 Transfer Acceleration enabled (not needed for dev) | LOW |
| **Cost** | Budget alert set to $15 (unrealistic for EKS) | LOW |
| **Cost** | Qdrant 3 replicas (overkill for dev) | LOW |
| **Cost** | Neo4j 100Gi storage (overkill for dev) | LOW |
| **Testing** | No test files exist | MEDIUM |
| **CI/CD** | No pipeline defined | MEDIUM |
| **DB** | No Alembic migrations | MEDIUM |

---

## Files Summary

| File | Action |
|------|--------|
| `infra/terraform/rds.tf` | Lower ACU min to 0.5 |
| `infra/terraform/budgets.tf` | Raise budget to $200 |
| `infra/terraform/s3.tf` | Suspend transfer acceleration |
| `infra/terraform/eks.tf` | Add app node group or remove system taint |
| `infra/terraform/terraform.tfvars` | Move to .gitignore |
| `deploy/ray/ray-cluster.yaml` | Downsize workers for dev |
| `deploy/helm/qdrant/values.yaml` | 1 replica, 20Gi, smaller resources |
| `deploy/helm/neo4j/values.yaml` | 1 CPU/2Gi, 20Gi storage |
| `deploy/helm/api/templates/deployment.yaml` | Add health probes, security context |
| `deploy/helm/api/templates/values.yaml` | ECR image, versioned tag |
| `services/api/main.py` | Add CORS, wire observability |
| `services/api/Dockerfile` | Non-root user, HEALTHCHECK |
| `services/api/app/config.py` | Add CORS_ORIGINS field |
| `.gitignore` | Add terraform.tfvars |
| New: `infra/terraform/terraform.tfvars.example` | Template with placeholders |
| New: `services/api/.dockerignore` | Exclude sensitive/unnecessary files |
| New: `deploy/karpenter/nodepool.yaml` | GPU SPOT + general SPOT pools |

---

## Deployment Scripts

All scripts are in `scripts/` and orchestrated via `Makefile`:

| Script | Make Target | Description |
|--------|-------------|-------------|
| `scripts/deploy_aws.sh` | `make deploy-aws` | Full orchestrator: Terraform + Build + Bootstrap |
| `scripts/build_push.sh` | `make build` | Build Docker image and push to ECR |
| `scripts/bootstrap_cluster.sh` | `make bootstrap` | Bootstrap EKS: KubeRay, Qdrant, Neo4j, Ray, NVIDIA, Karpenter, Ingress, API |
| `scripts/init_cloud.py` | `make init-cloud` | Initialize cloud databases (Qdrant collections, Neo4j indexes) |
| `scripts/smoke_test.sh` | `make smoke-test` | Post-deploy verification (health, auth, chat, UI) |
| `scripts/cleanup.sh` | `make destroy` | Tear down ALL AWS resources (with confirmation) |

### First-Time Deployment

```bash
# Prerequisites: AWS CLI configured, Docker running, terraform/helm/kubectl installed

# Option A: Full automated deploy
make deploy-aws

# Option B: Step by step
make infra          # 1. Provision AWS infrastructure (~15 min)
make build          # 2. Build & push Docker image to ECR
make bootstrap      # 3. Bootstrap EKS cluster with all K8s resources
make init-cloud     # 4. Initialize Qdrant collections, Neo4j indexes
make smoke-test     # 5. Verify everything works
```

### Subsequent Deploys (Code Changes Only)

```bash
make build          # Rebuild Docker image
make deploy         # Helm upgrade API pods
make smoke-test     # Verify
```

### Tear Down (Stop Billing)

```bash
make destroy        # Requires typing "DESTROY" to confirm
```

---

## Verification Checklist

1. `terraform plan` — dry-run infra changes, verify no unexpected resource creation
2. `docker build -f services/api/Dockerfile .` — verify hardened Dockerfile builds
3. `helm template deploy/helm/api` — verify health probes render correctly
4. `make deploy-aws` — full deploy to EKS
5. `kubectl get pods` — verify all pods healthy
6. `make smoke-test` — automated health, auth, chat, UI tests
7. Test chat endpoint — verify Ray GPU scales up, answers, then scales back to zero
8. Check AWS Cost Explorer after 1 week — verify baseline ~$162/mo

---

## Scaling to Production (When Ready)

When you're ready to scale this for production traffic:

1. **Aurora:** Raise `min_capacity` back to 2+, add second instance for HA
2. **Qdrant:** Scale to 3 replicas, increase storage to 50Gi+
3. **Neo4j:** Scale to 8Gi RAM, consider Enterprise edition for clustering
4. **Ray:** Increase GPU `maxReplicas` to 5-20, add CPU worker capacity
5. **EKS:** Add dedicated node groups per workload type
6. **VPC:** Switch to multi-AZ NAT gateways for HA
7. **Security:** Add WAF, NetworkPolicy, Pod Security Standards, TLS everywhere
8. **CI/CD:** Add full pipeline with staging environment
9. **Monitoring:** Add CloudWatch alarms, Prometheus/Grafana stack
10. **Budget:** Adjust to production spend expectations
