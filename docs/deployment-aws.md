# AWS Deployment Guide

Deploy the RAG platform to **AWS EKS** with Aurora Postgres, ElastiCache Redis, S3, and Karpenter autoscaling.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| AWS CLI | 2.x | `brew install awscli` |
| Terraform | >= 1.5 | `brew install terraform` |
| kubectl | >= 1.28 | `brew install kubectl` |
| Helm | >= 3.12 | `brew install helm` |
| Docker | latest | [docker.com](https://docker.com) |

```bash
# Verify AWS credentials
aws sts get-caller-identity
```

---

## 1. Terraform State Backend

Create an S3 bucket + DynamoDB table for remote state:

```bash
aws s3 mb s3://rag-terraform-state-$(aws sts get-caller-identity --query Account --output text)
aws dynamodb create-table \
    --table-name rag-terraform-lock \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST
```

Update `infra/terraform/main.tf` backend block with your bucket name.

---

## 2. Provision Infrastructure

### Environment Configuration

The platform supports **staging** and **prod** environments using `.tfvars` files:

| File | Environment | Description |
|------|-------------|-------------|
| `infra/terraform/terraform.tfvars` | prod | Production variables |
| `infra/terraform/envs/staging.tfvars` | staging | Staging overrides (smaller instances, lower costs) |

### Deploy Staging

```bash
make infra-staging
# Equivalent to:
# cd infra/terraform && terraform apply -var-file=envs/staging.tfvars
```

### Deploy Production

```bash
make infra
# Equivalent to:
# cd infra/terraform && terraform apply
```

### What Gets Created

| Resource | Staging | Production |
|----------|---------|------------|
| EKS Cluster | 1 cluster, v1.32 | 1 cluster, v1.32 |
| System Node Group | t3a.medium SPOT (1 node) | t3a.medium SPOT (1-2 nodes) |
| App Node Group | t3a.medium SPOT (1 node) | c6i/m6i (2+ nodes) |
| Aurora Postgres | Serverless v2, 0.5 ACU min | Serverless v2, 2 ACU min |
| ElastiCache Redis | t4g.micro, 1 node | r6g.large, 2 nodes |
| S3 | Standard, versioning on | Standard, versioning on |
| NAT Gateway | 1 (single AZ) | 3 (multi-AZ) |
| Karpenter | Installed via Helm | Installed via Helm |

### Key Terraform Outputs

```bash
cd infra/terraform
terraform output cluster_name
terraform output ecr_repository_url
terraform output aurora_endpoint
terraform output redis_endpoint
```

---

## 3. EBS CSI Driver (Required for PVCs)

EKS requires the EBS CSI driver addon for dynamic volume provisioning:

```bash
# 1. Create IAM role for the driver (IRSA)
CLUSTER_NAME=$(terraform -chdir=infra/terraform output -raw cluster_name)
OIDC_ID=$(aws eks describe-cluster --name $CLUSTER_NAME \
    --query "cluster.identity.oidc.issuer" --output text | cut -d '/' -f5)

# 2. Install the addon
aws eks create-addon --cluster-name $CLUSTER_NAME \
    --addon-name aws-ebs-csi-driver \
    --service-account-role-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/AmazonEKS_EBS_CSI_DriverRole

# 3. Create gp3 StorageClass
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
allowVolumeExpansion: true
EOF
```

---

## 4. Bootstrap the Cluster

The bootstrap script installs all K8s resources in the correct order:

```bash
# Staging
make bootstrap-staging
# Equivalent to:
# CLUSTER_NAME=rag-platform-staging REGION=us-east-1 \
#   HELM_VALUES_FILE=deploy/helm/api/values-staging.yaml \
#   scripts/bootstrap_cluster.sh

# Production
make bootstrap
```

### Bootstrap Steps (Automated)

1. **kubeconfig** — configures kubectl
2. **NVIDIA Device Plugin** — enables GPU scheduling
3. **Karpenter NodePools** — auto-detects IAM role, applies via envsubst
4. **External Secrets Operator** — syncs AWS Secrets Manager → K8s Secrets
5. **KubeRay Operator** — manages Ray clusters
6. **Qdrant** — vector database (Helm chart)
7. **Neo4j** — graph database (Helm chart)
8. **Ray Cluster** — head node + worker config
9. **Ray Serve** — LLM + embedding inference endpoints
10. **NGINX Ingress** — load balancer + routing rules
11. **API** — FastAPI backend (Helm chart)

### Karpenter NodePools

The `deploy/karpenter/nodepool.yaml` uses envsubst templates for multi-environment support:

| NodePool | Instances | Capacity | Purpose |
|----------|-----------|----------|---------|
| `general` | t3a, t4g (SPOT) | 16 vCPU / 64Gi max | API, ingestion, CPU workers |
| `gpu` | g5, g4dn (SPOT → on-demand fallback) | 16 vCPU / 64Gi max | LLM + embedding inference |

GPU nodes scale to zero automatically — Karpenter terminates them 30s after the last pod exits.

---

## 5. Create Application Secret

The API reads all credentials from a single K8s Secret:

```bash
kubectl create secret generic app-env-secret \
    --from-literal=DATABASE_URL="postgresql+asyncpg://raguser:<password>@<aurora-endpoint>:5432/ragdb" \
    --from-literal=REDIS_URL="rediss://:<auth-token>@<redis-endpoint>:6379/0" \
    --from-literal=NEO4J_PASSWORD="<password>" \
    --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
    --from-literal=QDRANT_HOST="qdrant" \
    --from-literal=QDRANT_PORT="6333" \
    --from-literal=ENV="staging"
```

> **Note:** Kubernetes auto-injects `<SERVICE>_PORT=tcp://...` for each service. If your config expects an integer port (like `QDRANT_PORT`), set it explicitly in the secret to avoid conflicts.

For production, use External Secrets Operator to sync from AWS Secrets Manager instead:

```bash
kubectl apply -f deploy/secrets/external-secrets.yaml
```

---

## 6. Initialize Databases

After bootstrap, initialize Qdrant collections and Neo4j indexes:

```bash
# Port-forward to Qdrant and Neo4j
kubectl port-forward svc/qdrant 6333:6333 &
kubectl port-forward svc/neo4j 7687:7687 &

# Initialize (auto-detects embedding dimensions)
python3 scripts/init_cloud.py
```

The init script queries your embedding model for its actual dimension (e.g., 768 for `nomic-embed-text`, 1024 for `bge-m3`) rather than hardcoding.

---

## 7. Build & Push Docker Image

```bash
make build
# Equivalent to:
# ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
# ECR_URI="${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com"
# docker build -t ${ECR_URI}/rag-backend-api:$(git rev-parse --short HEAD) -f services/api/Dockerfile services/api
# docker push ${ECR_URI}/rag-backend-api:$(git rev-parse --short HEAD)
```

---

## 8. Verify Deployment

```bash
# Check all pods
kubectl get pods

# Test health endpoint
kubectl port-forward svc/api-service 8080:80
curl http://localhost:8080/health/readiness

# Open Chat UI
open http://localhost:8080/
```

---

## 9. Ingress & DNS

The ingress routes all traffic through NGINX:

```yaml
# deploy/ingress/nginx.yaml
spec:
  rules:
  - host: api.your-domain.com
    http:
      paths:
      - path: /         # Chat UI + catch-all
      - path: /chat     # Chat API
      - path: /upload   # Document upload
      - path: /health   # Health probes
```

Point your domain's DNS to the NGINX LoadBalancer:

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

---

## 10. Cost Management

### Estimated Monthly Costs

| Config | Idle Cost | With GPU 2hr/day |
|--------|-----------|------------------|
| Staging (dev/learning) | ~$162/mo | ~$198/mo |
| Production | ~$400/mo | ~$600/mo |

### Cost Optimization Strategies

- **SPOT instances** via Karpenter (up to 70% savings)
- **Aurora Serverless v2** scales to 0.5 ACU when idle
- **GPU scale-to-zero** — no GPU cost when not querying
- **Single NAT Gateway** for dev (multi-AZ for prod)

### Shutdown to Save Costs

```bash
# Scale workloads to zero (keeps cluster running)
kubectl scale deploy --all --replicas=0
kubectl scale statefulset --all --replicas=0

# Full shutdown (stop billing)
aws rds stop-db-cluster --db-cluster-identifier rag-aurora-staging
aws eks delete-nodegroup --cluster-name rag-platform-staging --nodegroup-name app-nodes
aws eks delete-nodegroup --cluster-name rag-platform-staging --nodegroup-name system-nodes
# Wait for node groups to delete, then:
aws eks delete-cluster --name rag-platform-staging
```

> Aurora auto-restarts after 7 days. ElastiCache Redis cannot be stopped — it must be deleted.

---

## 11. Subsequent Deploys

For code-only changes (no infrastructure updates):

```bash
make build              # Rebuild Docker image
make deploy-staging     # Helm upgrade staging
make smoke-test         # Verify
```

---

## Related Docs

- [Architecture & Design](architecture.md)
- [Azure Deployment](deployment-azure.md)
- [API Reference & Chat UI](api-reference.md)
- [Operations Guide](operations.md)
