# Enterprise Agentic RAG Platform

![Architecture](https://img.shields.io/badge/Architecture-Agentic%20LangGraph-blueviolet)
![Orchestration](https://img.shields.io/badge/Orchestration-LangGraph%20%2B%20Ray-orange)
![Cloud](https://img.shields.io/badge/Cloud-AWS%20%7C%20Azure-blue)
![Tests](https://img.shields.io/badge/Tests-132%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

A production-grade, **multi-cloud**, **multi-tenant** Retrieval-Augmented Generation platform built on FastAPI, LangGraph, Qdrant, Neo4j, and Kubernetes. Supports both self-hosted (Ray/vLLM) and API-based (OpenAI) LLMs with a provider-abstraction pattern that makes every infrastructure component swappable.

## Table of Contents

- [Quick Start (Local Development)](#quick-start-local-development)
- [1. System Overview](#1-system-overview)
- [2. RAG Methodologies & Agentic Logic](#2-rag-methodologies--agentic-logic)
- [3. Provider Abstraction Architecture](#3-provider-abstraction-architecture)
- [4. Multi-Tenancy](#4-multi-tenancy)
- [5. Prerequisites & Tooling](#5-prerequisites--tooling)
- [6. AWS Deployment](#6-aws-deployment)
- [7. Azure Deployment](#7-azure-deployment)
- [8. Data Ingestion](#8-data-ingestion)
- [9. Chat UI](#9-chat-ui)
- [10. API Reference](#10-api-reference)
- [11. Sample Queries](#11-sample-queries)
- [12. CI/CD Pipelines](#12-cicd-pipelines)
- [13. Observability](#13-observability)
- [14. Validation & Testing](#14-validation--testing)
- [15. Cost Optimization & Scaling](#15-cost-optimization--scaling)
- [16. Troubleshooting](#16-troubleshooting)

---

## Quick Start (Local Development)

Run the full RAG pipeline locally — no cloud account, no Kubernetes, no GPU required.

### Prerequisites

- **Python 3.10+**
- **Docker** (for Postgres, Redis, Qdrant, Neo4j, MinIO)
- **[Ollama](https://ollama.com)** (optional — for local LLM) **or** an OpenAI API key

### Setup

```bash
# 1. Install Python dependencies
make install

# 2. Start local databases (Postgres, Redis, Qdrant, Neo4j, MinIO)
make up

# 3. Configure environment
cp .env.example .env
# Edit .env — choose your LLM provider:
#
# Option A: Ollama (local, no cost)
#   LLM_PROVIDER=ray
#   EMBED_PROVIDER=ray
#   RAY_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
#   RAY_EMBED_ENDPOINT=http://localhost:11434/api/embeddings
#   LLM_MODEL=llama3
#
# Option B: OpenAI API
#   LLM_PROVIDER=openai
#   EMBED_PROVIDER=openai
#   OPENAI_API_KEY=sk-...

# 4. Initialize datastores (tables, collections, indexes, buckets)
make init

# 5. Ingest sample documents
python3 scripts/ingest_local.py --sample

# 6. Start the API server (with hot reload)
make dev
```

### Usage

```bash
# Get a dev JWT token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "dev-user", "role": "admin", "tenant_id": "default"}'

# Chat (replace <TOKEN> with access_token from above)
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"message": "What are the five pillars of the AWS Well-Architected Framework?", "tenant_id": "default"}'
```

Open the **Chat UI** at `http://localhost:8000/`.

### Local Services

| Component      | Service                | Port        |
|---------------|------------------------|-------------|
| LLM + Embed   | Ollama or OpenAI API   | 11434 / API |
| Vector DB     | Qdrant (Docker)        | 6333        |
| Graph DB      | Neo4j (Docker)         | 7474 / 7687 |
| SQL DB        | Postgres (Docker)      | 5432        |
| Cache         | Redis (Docker)         | 6379        |
| Object Storage| MinIO (Docker)         | 9000 / 9001 |

### Available Make Commands

```
make install    Install Python dependencies
make up         Start local DBs via Docker Compose
make init       Initialize DBs, collections, indexes, buckets
make dev        Run FastAPI server locally (hot reload, port 8000)
make test       Run full test suite (132 tests)
make down       Stop local DBs
```

---

## 1. System Overview

This platform implements a **production-grade Agentic RAG** system with the following design principles:

- **Agentic reasoning** via LangGraph state machine (plan → retrieve → respond)
- **Hybrid retrieval** combining vector search (Qdrant) + knowledge graph traversal (Neo4j)
- **Multi-cloud** — identical codebase runs on AWS EKS or Azure AKS
- **Multi-tenant** — per-tenant data isolation, config, rate limits, and auth
- **Provider-abstraction** — every infra component (LLM, storage, vector DB, secrets) is swappable via config
- **OpenAI or self-hosted** — use OpenAI API for fast onboarding, or Ray/vLLM for GPU inference

### High-Level Architecture

The system is split into two planes:

| Plane | Responsibility | Compute |
|-------|---------------|---------|
| **Control Plane** | HTTP, agent orchestration, auth, caching, memory | CPU nodes |
| **Data Plane** | LLM inference, embedding, graph extraction | GPU nodes (Ray) |

### Service Map

```
Client
  │
  ▼
NGINX Ingress (Load Balancer)
  │
  ▼
FastAPI (services/api/)
  ├── /auth/token          — Dev JWT issuance (dev mode only)
  ├── /api/v1/chat/stream  — Streaming RAG chat (SSE)
  ├── /api/v1/upload/      — Presigned URL generation for doc upload
  ├── /api/v1/feedback/    — User feedback on responses
  ├── /health/liveness     — Liveness probe
  └── /health/readiness    — Readiness probe (redis + vectordb + graphdb)
  │
  ├── LangGraph Agent
  │     ├── Planner node   — Intent classification
  │     ├── Retriever node — Hybrid vector + graph search
  │     ├── Tool node      — Calculator, web search, code sandbox
  │     └── Responder node — LLM-based answer synthesis
  │
  ├── Cache Layer (Redis)
  │     ├── Exact-match cache
  │     └── Semantic cache (embedding similarity)
  │
  └── Memory (Postgres)
        └── chat_history   — Per-session conversation history
```

---

## 2. RAG Methodologies & Agentic Logic

### 2.1. Planning Agent (`services/api/app/agents/`)

The RAG flow is modelled as a **LangGraph state machine**, not a linear chain:

- **Planner Node** — classifies user intent: direct answer / retrieval / tool use
- **Query Rewriter** — rewrites queries to resolve coreferences and improve retrieval
- **HyDE (Hypothetical Document Embeddings)** — generates a synthetic "ideal answer", embeds it, and uses that vector to retrieve real documents — bridges the semantic gap between questions and declarative text

### 2.2. Hybrid Retrieval

| Method | Implementation | Strength |
|--------|---------------|----------|
| Dense Vector Search | Qdrant (`rag_collection`) | Semantic similarity |
| Knowledge Graph Traversal | Neo4j Cypher queries | Entity relationships |
| Semantic Cache | Qdrant (`semantic_cache`) | Avoid re-embedding repeated queries |

### 2.3. LLM Providers

| Provider | Config | Use Case |
|----------|--------|----------|
| `openai` | `LLM_PROVIDER=openai` + `OPENAI_API_KEY` | Fast onboarding, no GPU required |
| `ray` | `LLM_PROVIDER=ray` + Ray cluster | Self-hosted vLLM (Llama-3, etc.) |

---

## 3. Provider Abstraction Architecture

Every infrastructure dependency is accessed through a **Protocol + Factory** pattern, making each component independently swappable by changing a single environment variable.

### Storage (`STORAGE_PROVIDER`)

| Value | Implementation | Cloud |
|-------|---------------|-------|
| `s3` | `clients/storage/s3.py` | AWS |
| `azure_blob` | `clients/storage/azure_blob.py` | Azure |

```bash
STORAGE_PROVIDER=azure_blob
AZURE_STORAGE_ACCOUNT_NAME=ragplatformaksdocs
```

### Vector DB (`VECTORDB_PROVIDER`)

| Value | Implementation |
|-------|---------------|
| `qdrant` | `clients/vectordb/qdrant_impl.py` |

```bash
VECTORDB_PROVIDER=qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
```

### Graph DB (`GRAPHDB_PROVIDER`)

| Value | Implementation |
|-------|---------------|
| `neo4j` | `clients/graphdb/neo4j_impl.py` |
| `none` | `clients/graphdb/null_client.py` (no-op) |

### Secrets (`SECRETS_PROVIDER`)

| Value | Implementation | Backend |
|-------|---------------|---------|
| `env` | `clients/secrets/env.py` | Environment variables (default) |
| `aws_sm` | `clients/secrets/aws_sm.py` | AWS Secrets Manager |
| `azure_kv` | `clients/secrets/azure_kv.py` | Azure Key Vault |

```bash
# AWS Secrets Manager
SECRETS_PROVIDER=aws_sm
SECRETS_PREFIX=rag-platform/prod/

# Azure Key Vault
SECRETS_PROVIDER=azure_kv
AZURE_KEY_VAULT_URL=https://my-vault.vault.azure.net
```

---

## 4. Multi-Tenancy

The platform supports complete **per-tenant isolation** across all data stores.

### How It Works

1. Every JWT token includes a `tenant_id` claim
2. The `TenantContext` dependency extracts and validates tenant identity per request
3. All database queries are scoped by `tenant_id` — tenants cannot access each other's data
4. Per-tenant configuration (rate limits, model preferences, auth provider) is loaded from the tenant registry

### Tenant Configuration (`app/tenants/config.py`)

```python
TenantConfig(
    tenant_id="acme-corp",
    rate_limit_rpm=100,
    llm_provider="openai",
    embed_model="text-embedding-3-small",
    vectordb_collection="rag_collection",
)
```

### Auth Providers (per-tenant)

| Provider | Config |
|----------|--------|
| `local` | HS256 JWT with shared secret (dev default) |
| `auth0` | RS256 JWKS validation |
| `azure_ad` | Azure AD / Entra ID JWKS |
| `cognito` | AWS Cognito JWKS |

---

## 5. Prerequisites & Tooling

### Common

- **Python 3.10+**
- **Docker**
- **kubectl v1.28+**
- **Helm v3.x**
- **Terraform v1.5+**

### AWS Deployment

- **AWS CLI v2** — configured with `AdministratorAccess`

### Azure Deployment

- **Azure CLI (`az`)** — logged in via `az login`
- **Active Azure subscription** with quota for: `Standard_B2s`, `Standard_B2s_v2`

---

## 6. AWS Deployment

### 6.1. Remote State Setup

```bash
# Create S3 bucket for Terraform state
aws s3api create-bucket \
  --bucket rag-platform-terraform-state-prod-001 \
  --region us-east-1

# Create DynamoDB lock table
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### 6.2. Provision Infrastructure

```bash
cd infra/terraform

terraform init
terraform plan -var="db_password=YourStrongPassword#123" -out=tfplan
terraform apply tfplan   # ~20 min
```

Creates: VPC, EKS (v1.29), Aurora Postgres Serverless v2, ElastiCache Redis, S3, IAM/IRSA roles.

### 6.3. Bootstrap Cluster

```bash
aws eks update-kubeconfig --region us-east-1 --name rag-platform-cluster

chmod +x scripts/bootstrap_cluster.sh
./scripts/bootstrap_cluster.sh
```

Installs: Karpenter (autoscaler), KubeRay Operator, External Secrets, NGINX Ingress.

### 6.4. Create Kubernetes Secret

```bash
kubectl create secret generic app-env-secret \
  --from-literal=DATABASE_URL="postgresql+asyncpg://ragadmin:YourPassword@<RDS_ENDPOINT>:5432/ragdb" \
  --from-literal=REDIS_URL="redis://<ELASTICACHE_ENDPOINT>:6379/0" \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=NEO4J_PASSWORD="password" \
  --from-literal=CLOUD_PROVIDER="aws" \
  --from-literal=STORAGE_PROVIDER="s3" \
  --from-literal=QDRANT_HOST="qdrant" \
  --from-literal=QDRANT_PORT="6333" \
  --from-literal=OPENAI_API_KEY="sk-..." \
  --from-literal=LLM_PROVIDER="openai" \
  --from-literal=EMBED_PROVIDER="openai" \
  --from-literal=ENV="dev"
```

### 6.5. Deploy Services

```bash
# Build & push image to ECR
./scripts/build_push.sh

# Deploy databases
helm upgrade --install qdrant qdrant/qdrant -f deploy/helm/qdrant/values.yaml
helm upgrade --install neo4j neo4j/neo4j --set neo4j.password=password \
  --set volumes.data.mode=defaultStorageClass

# Deploy Ray (for self-hosted LLM — skip if using OpenAI)
kubectl apply -f deploy/ray/ray-cluster.yaml
kubectl apply -f deploy/ray/ray-serve-embed.yaml
kubectl apply -f deploy/ray/ray-serve-llm.yaml

# Deploy API
helm upgrade --install api deploy/helm/api \
  --set image.repository=<ECR_URI>/rag-backend-api \
  --set image.tag=latest

# Apply ingress
kubectl apply -f deploy/ingress/nginx.yaml
```

### 6.6. Initialize Database & Ingest

```bash
# Initialize PostgreSQL schema
kubectl exec -it deploy/api-deployment -- python3 -c "
import asyncio, sys; sys.path.insert(0, '/app')
from app.memory.postgres import Base, engine
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"

# Ingest documents
OPENAI_API_KEY=sk-... QDRANT_HOST=localhost QDRANT_PORT=6333 \
  python3 scripts/ingest_openai.py data/test-docs/aws_well_architected.pdf
```

---

## 7. Azure Deployment

### 7.1. Prerequisites

1. Active Azure subscription
2. Azure CLI: `az login`
3. Create Terraform remote state storage:

```bash
az group create --name terraform-state-rg --location eastus
az storage account create --name <YOUR_STORAGE_ACCOUNT> \
  --resource-group terraform-state-rg --sku Standard_LRS
az storage container create --name tfstate \
  --account-name <YOUR_STORAGE_ACCOUNT>
```

### 7.2. Configure Terraform

```bash
cd infra/terraform/azure

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   resource_group_name  = "rag-platform-rg"
#   location             = "eastus"
#   db_password          = "YourStrongPassword#123"
#   acr_name             = "ragplatformacr"

# Update backend in main.tf:
#   resource_group_name  = "terraform-state-rg"
#   storage_account_name = "<YOUR_STORAGE_ACCOUNT>"
```

### 7.3. Provision Infrastructure

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan   # ~25 min
```

Creates:

| Resource | Details |
|----------|---------|
| AKS Cluster | K8s 1.32, system (Standard_B2s) + app (Standard_B2s_v2) node pools |
| PostgreSQL | Flexible Server, Burstable B1ms, centralus |
| Redis Cache | Basic C0, eastus |
| ACR | Basic, for container images |
| Storage Account | Standard LRS, blob container `documents` |
| VNet + NSG | 10.0.0.0/16 with AKS, database, Redis subnets |
| Managed Identities | API + Ray, with Workload Identity federation |
| Role Assignments | AcrPull, Storage Blob Contributor |

### 7.4. Bootstrap AKS Cluster

```bash
az aks get-credentials --resource-group rag-platform-rg --name rag-platform-aks

# Get outputs for secret creation
cd infra/terraform/azure
POSTGRES_FQDN=$(terraform output -raw postgres_fqdn)
REDIS_HOST=$(terraform output -raw redis_hostname)
REDIS_KEY=$(terraform output -raw redis_primary_key)
STORAGE_ACCOUNT=$(terraform output -raw storage_account_name)
API_IDENTITY_CLIENT_ID=$(terraform output -raw api_identity_client_id)

# Create Kubernetes secret
kubectl create secret generic app-env-secret \
  --from-literal=DATABASE_URL="postgresql+asyncpg://ragadmin:<DB_PASSWORD>@${POSTGRES_FQDN}:5432/ragdb" \
  --from-literal=REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0" \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=NEO4J_PASSWORD="password" \
  --from-literal=AZURE_STORAGE_ACCOUNT_NAME="$STORAGE_ACCOUNT" \
  --from-literal=CLOUD_PROVIDER="azure" \
  --from-literal=STORAGE_PROVIDER="azure_blob" \
  --from-literal=QDRANT_HOST="qdrant" \
  --from-literal=QDRANT_PORT="6333" \
  --from-literal=S3_BUCKET_NAME="not-used-on-azure" \
  --from-literal=OTEL_EXPORTER="none" \
  --from-literal=OPENAI_API_KEY="sk-..." \
  --from-literal=ENV="dev"

# Install cluster components
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm repo add qdrant https://qdrant.to/helm
helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm upgrade --install kuberay-operator kuberay/kuberay-operator --version 1.0.0

helm upgrade --install qdrant qdrant/qdrant \
  --set persistence.storageClassName=managed-csi \
  -f deploy/helm/qdrant/values.yaml

helm upgrade --install neo4j neo4j/neo4j \
  --set neo4j.password=password \
  --set neo4j.resources.memory=2Gi \
  --set volumes.data.mode=defaultStorageClass

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.service.type=LoadBalancer
```

### 7.5. Build & Deploy API

```bash
# Build using ACR Build Tasks (avoids ARM/AMD64 cross-compile issues)
az acr build \
  --registry ragplatformacr \
  --image rag-backend-api:latest \
  --platform linux/amd64 \
  --file services/api/Dockerfile \
  services/api/

# Deploy via Helm
helm upgrade --install api deploy/helm/api \
  -f deploy/helm/api/values-azure.yaml \
  --set image.repository=ragplatformacr.azurecr.io/rag-backend-api \
  --set image.tag=latest \
  --set serviceAccount.annotations."azure\.workload\.identity/client-id"="$API_IDENTITY_CLIENT_ID" \
  --set image.pullPolicy=Always
```

### 7.6. Initialize Database Schema & Ingest

```bash
# Initialize PostgreSQL tables
POD=$(kubectl get pods -l app=api -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$POD" -- python3 -c "
import asyncio, sys; sys.path.insert(0, '/app')
from app.memory.postgres import Base, engine
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"

# Initialize Qdrant collections (with correct 1536 dims for OpenAI embeddings)
kubectl port-forward svc/qdrant 6333:6333 &
python3 - << 'EOF'
from qdrant_client import QdrantClient
from qdrant_client.http import models
client = QdrantClient(host="localhost", port=6333)
for name in ["rag_collection", "semantic_cache"]:
    client.create_collection(name, vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE))
    print(f"Created {name}")
EOF

# Ingest sample documents
OPENAI_API_KEY=sk-... QDRANT_HOST=localhost QDRANT_PORT=6333 \
  python3 scripts/ingest_openai.py data/test-docs/aws_well_architected.pdf --tenant-id default
```

### 7.7. Ingress

```bash
# Get Load Balancer public IP
kubectl get svc -n ingress-nginx ingress-nginx-controller

# Apply ingress (accepts any hostname/IP for dev)
cat << 'EOF' | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: rag-ingress
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
spec:
  ingressClassName: nginx
  rules:
  - http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 80
EOF
```

### 7.8. Cost Management (Azure)

**Daily cost estimate (dev configuration):**

| Resource | SKU | Daily |
|----------|-----|-------|
| AKS System Node | Standard_B2s | ~$1.19 |
| AKS App Node | Standard_B2s_v2 | ~$2.00 |
| PostgreSQL | Burstable B1ms | ~$0.50 |
| Redis | Basic C0 | ~$0.53 |
| Load Balancer | Standard | ~$0.79 |
| ACR + Storage | Basic / LRS | ~$0.18 |
| **Total** | | **~$5.19/day** |

**Stop resources when not in use (~$0.53/day overnight):**

```bash
# Stop (saves ~$4.66/day)
az aks stop --resource-group rag-platform-rg --name rag-platform-aks
az postgres flexible-server stop --resource-group rag-platform-rg --name ragplatform-pgdb-central

# Start
az aks start --resource-group rag-platform-rg --name rag-platform-aks
az postgres flexible-server start --resource-group rag-platform-rg --name ragplatform-pgdb-central
az aks get-credentials --resource-group rag-platform-rg --name rag-platform-aks --overwrite-existing
```

> **Note:** Redis cannot be stopped without deleting it — it accrues ~$0.53/day regardless.

---

## 8. Data Ingestion

### Quick Ingestion (OpenAI Embeddings)

Works from your local machine with port-forwarded Qdrant:

```bash
# Port-forward Qdrant
kubectl port-forward svc/qdrant 6333:6333 &

# Ingest a PDF
OPENAI_API_KEY=sk-... python3 scripts/ingest_openai.py path/to/document.pdf

# Ingest with a specific tenant
OPENAI_API_KEY=sk-... python3 scripts/ingest_openai.py path/to/doc.pdf --tenant-id acme-corp
```

**Pipeline steps:**
1. **Parse** — `pypdf` extracts text from PDF (1,002 pages in ~2s)
2. **Chunk** — 500-character chunks with 50-character overlap
3. **Embed** — OpenAI `text-embedding-3-small` (1536 dimensions), batched in 100s
4. **Upsert** — Vectors stored in Qdrant `rag_collection`, tagged with `tenant_id`

### Full Ray Pipeline (Distributed, GPU)

For large-scale ingestion using the Ray distributed pipeline:

```bash
# Submit Ray job
python -m pipelines.jobs.s3_event_handler
```

**Pipeline steps:**
1. **Ray Data** reads documents from S3/Azure Blob lazily
2. **MapBatches (CPU)** — parse + chunk (PDF, DOCX, HTML)
3. **MapBatches (GPU - Embed)** — BGE-M3 embeddings via Ray Serve
4. **MapBatches (GPU - Graph)** — LLM extracts `(Subject, Predicate, Object)` tuples
5. **Write** — Vectors → Qdrant, Nodes/Edges → Neo4j

### Sample Documents

| File | Location | Pages |
|------|----------|-------|
| AWS Well-Architected Framework | `data/test-docs/aws_well_architected.pdf` | 1,002 |

---

## 9. Chat UI

A built-in dark-theme Chat UI is served directly by the API at the root path.

**Access:** `http://<LOAD_BALANCER_IP>/` or `http://localhost:8000/` (local)

**Features:**
- Real-time streaming responses (SSE)
- Session persistence
- Status indicator (Connected / Degraded) based on `/health/readiness`
- Auto-authentication via dev token endpoint

**Status indicator checks:**
- `redis === 'up'`
- `graphdb === 'up'`

> The dev token endpoint (`/auth/token`) requires `ENV=dev` in the Kubernetes secret. In production, replace with your IdP (Auth0, Azure AD, Cognito).

---

## 10. API Reference

All endpoints require `Authorization: Bearer <TOKEN>` except `/health/*` and `/auth/token`.

### Authentication

#### `POST /auth/token`
Issues a development JWT token. **Only available when `ENV=dev`.**

```bash
curl -X POST http://<HOST>/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "dev-user",
    "role": "admin",
    "tenant_id": "default"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "user_id": "dev-user",
  "tenant_id": "default",
  "expires_in": 86400
}
```

> In production, replace with your IdP (Auth0, Azure AD, AWS Cognito). Set `JWT_JWKS_URL`, `JWT_AUDIENCE`, `JWT_ISSUER` in config.

---

### Chat

#### `POST /api/v1/chat/stream`
Streaming RAG chat using Server-Sent Events (NDJSON). Runs the full LangGraph pipeline: plan → retrieve → respond.

```bash
curl -X POST http://<HOST>/api/v1/chat/stream \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the five pillars of the AWS Well-Architected Framework?",
    "session_id": "optional-uuid-for-conversation-continuity"
  }'
```

**Streamed NDJSON response (one JSON object per line):**
```jsonl
{"type": "status", "node": "planner",   "session_id": "abc123", "info": "Completed step: planner"}
{"type": "status", "node": "retriever", "session_id": "abc123", "info": "Completed step: retriever"}
{"type": "status", "node": "responder", "session_id": "abc123", "info": "Completed step: responder"}
{"type": "answer",  "content": "The five pillars are: 1. Operational Excellence...", "session_id": "abc123"}
{"type": "status", "node": "__end__",   "session_id": "abc123", "info": "Completed step: __end__"}
```

**Error event:**
```json
{"type": "error", "content": "An internal error occurred."}
```

**Session behaviour:**
- Omit `session_id` → new session created, ID returned in each event
- Provide `session_id` → conversation history loaded (last 6 turns)
- Sessions are tenant-scoped — cross-tenant access returns HTTP 403

---

### File Upload

#### `POST /api/v1/upload/generate-presigned-url`
Generates a secure, time-limited URL for direct client-to-storage upload (bypasses API server for large files).

```bash
curl -X POST http://<HOST>/api/v1/upload/generate-presigned-url \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "quarterly_report.pdf",
    "content_type": "application/pdf"
  }'
```

**Response:**
```json
{
  "upload_url": "https://ragplatformaksdocs.blob.core.windows.net/documents/...",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "object_key": "uploads/default/dev-user/550e8400.pdf"
}
```

Upload directly to `upload_url` using a `PUT` request with the matching `Content-Type`.

---

### Feedback

#### `POST /api/v1/feedback/`
Submit user feedback on a chat response (thumbs up/down, comments).

```bash
curl -X POST http://<HOST>/api/v1/feedback/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "message_id": "msg-456",
    "rating": 1,
    "comment": "Great answer!"
  }'
```

---

### Health

#### `GET /health/liveness`
Kubernetes liveness probe — returns 200 if the process is alive.
```json
{"status": "ok"}
```

#### `GET /health/readiness`
Kubernetes readiness probe — checks all dependency connections.
```json
{"redis": "up", "vectordb": "up", "graphdb": "up"}
```
Returns HTTP 503 if any dependency is down.

---

### Swagger UI

Interactive API documentation is available at:
```
http://<HOST>/docs        # Swagger UI
http://<HOST>/redoc       # ReDoc
http://<HOST>/openapi.json # OpenAPI schema
```

---

## 11. Sample Queries

Use these queries against the ingested `aws_well_architected.pdf` (included in `data/test-docs/`) or your own documents.

### Quick Test via curl

```bash
# 1. Get token
TOKEN=$(curl -s -X POST http://<HOST>/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"dev-user","role":"admin","tenant_id":"default"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Ask a question
curl -s -X POST http://<HOST>/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "<YOUR QUESTION HERE>", "tenant_id": "default"}'
```

---

### AWS Well-Architected Framework (`data/test-docs/aws_well_architected.pdf`)

This 1,002-page document covers AWS architecture best practices and is pre-ingested as 4,286 vectors.

**Foundational questions:**
```
What are the five pillars of the AWS Well-Architected Framework?
Describe the Operational Excellence pillar and its key principles.
What is the difference between reliability and availability in cloud architecture?
How does AWS define the Sustainability pillar?
What are the design principles for the Security pillar?
```

**Deep-dive questions:**
```
What are the best practices for designing loosely coupled architectures on AWS?
How should I approach disaster recovery planning according to the Well-Architected Framework?
What is the difference between RPO and RTO in the context of reliability?
How does the Performance Efficiency pillar recommend choosing the right compute service?
What cost optimization strategies does AWS recommend for storage services?
```

**Cross-topic reasoning (tests multi-hop retrieval):**
```
How do the Security and Reliability pillars interact when designing a multi-region application?
Compare the trade-offs between cost optimization and performance efficiency for a latency-sensitive API.
What governance mechanisms does the Well-Architected Framework recommend for multi-account AWS environments?
```

---

### Kubernetes / Cloud Operations (`eval/datasets/true_data/`)

The `eval/datasets/true_data/` directory contains additional documents (DOCX, HTML, TXT) for testing:

| File | Topics |
|------|--------|
| `cronjobs.docx` | Kubernetes CronJob scheduling, timing, retries |
| `job_management.html` | K8s Job lifecycle, parallelism, completion modes |
| `monitor_job.docx` | Job monitoring, status conditions, failure handling |
| `parallel_work_queue.txt` | Work queue patterns, parallel job coordination |
| `pods_autoscale.html` | HPA, VPA, custom metrics autoscaling |
| `architecture.pptx` | System architecture diagrams |

**Sample queries for these documents:**
```
How do you configure a Kubernetes CronJob to run every 15 minutes?
What happens when a Kubernetes Job fails — does it retry automatically?
How does the Horizontal Pod Autoscaler decide when to scale up?
What is the difference between Job parallelism and completions in Kubernetes?
How can I monitor the status of a running Kubernetes Job?
```

---

### System Design (if using `grok_system_design_interview.pdf`)

```
What is consistent hashing and why is it used in distributed systems?
How would you design a URL shortening service like TinyURL?
What are the trade-offs between SQL and NoSQL databases?
How does database sharding work and what are common sharding strategies?
What is the CAP theorem?
```

---

### Multi-Turn Conversation (tests session memory)

Use the same `session_id` across requests to test conversation continuity:

```bash
SESSION="my-test-session-$(date +%s)"

# Turn 1
curl -s -X POST http://<HOST>/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is the Reliability pillar?\", \"session_id\": \"$SESSION\"}"

# Turn 2 — references Turn 1 (tests coreference resolution)
curl -s -X POST http://<HOST>/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"How does it relate to disaster recovery?\", \"session_id\": \"$SESSION\"}"

# Turn 3 — tests semantic cache (exact same question → cached response)
curl -s -X POST http://<HOST>/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is the Reliability pillar?\", \"session_id\": \"$SESSION\"}"
```

---

### Ingest Your Own Documents

```bash
# Port-forward Qdrant
kubectl port-forward svc/qdrant 6333:6333 &

# Ingest a PDF (OpenAI embeddings)
OPENAI_API_KEY=sk-... python3 scripts/ingest_openai.py /path/to/your/document.pdf

# Ingest for a specific tenant
OPENAI_API_KEY=sk-... python3 scripts/ingest_openai.py /path/to/doc.pdf --tenant-id acme-corp

# Ingest locally (Ollama embeddings)
python3 scripts/ingest_local.py /path/to/document.pdf
```

Supported formats: **PDF**, **DOCX**, **HTML**, **TXT**

---

## 12. CI/CD Pipelines

### CI — `.github/workflows/ci.yml`


Triggered on every push and pull request:

| Step | Tool | Detail |
|------|------|--------|
| Lint | `ruff` | Python style + import checks |
| Test | `pytest` | 132 tests, all must pass |
| Docker Build | `docker buildx` | Validates Dockerfile compiles |
| Terraform Validate | `terraform validate` | Both AWS + Azure configs |

### CD — `.github/workflows/deploy.yml`

Manual trigger (`workflow_dispatch`) with cloud selector:

```
Inputs:
  cloud: aws | azure
  environment: staging | production
  image_tag: (git SHA or semver)
```

Steps: OIDC auth → ECR/ACR push → Helm upgrade → smoke test

---

## 13. Observability

Cloud-agnostic OpenTelemetry via `OTEL_EXPORTER` config:

| Value | Exporter | Use Case |
|-------|----------|----------|
| `otlp` | OTLP (Jaeger, Grafana) | Self-hosted or vendor-neutral |
| `xray` | AWS X-Ray | AWS deployments |
| `azure_monitor` | Azure Monitor / App Insights | Azure deployments |
| `none` | No-op | Dev / cost saving |

```bash
# AWS X-Ray
OTEL_EXPORTER=xray

# Azure Monitor
OTEL_EXPORTER=azure_monitor
AZURE_MONITOR_CONNECTION_STRING=InstrumentationKey=...

# OTLP (Jaeger)
OTEL_EXPORTER=otlp
OTEL_ENDPOINT=http://jaeger:4317
```

---

## 14. Validation & Testing

### Run Tests

```bash
make test
# 132 tests, 0 failures
```

### Test Coverage

| Test File | What It Covers |
|-----------|---------------|
| `test_tenant_auth.py` | JWT issuance, JWKS validation, auth providers |
| `test_tenant_data_isolation.py` | Cross-tenant data leakage prevention |
| `test_tenant_config_auth.py` | Per-tenant config loading |
| `test_vectordb_graphdb_abstraction.py` | VectorDB + GraphDB protocol conformance |
| `test_storage_abstraction.py` | StorageClient S3 + Azure Blob protocol |
| `test_ops_observability.py` | SecretsClient factory, OTel exporter routing |

### Health Checks

```bash
# Liveness — is the process up?
curl http://<IP>/health/liveness
# {"status": "ok"}

# Readiness — are all dependencies connected?
curl http://<IP>/health/readiness
# {"redis": "up", "vectordb": "up", "graphdb": "up"}
```

### End-to-End Chat Test

```bash
# 1. Get token
TOKEN=$(curl -s -X POST http://<IP>/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"dev-user","role":"admin","tenant_id":"default"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Chat — streams SSE events
curl -X POST http://<IP>/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the five pillars of the AWS Well-Architected Framework?", "tenant_id": "default"}'

# Expected SSE response:
# {"type":"status","node":"planner",...}
# {"type":"status","node":"retriever",...}
# {"type":"status","node":"responder",...}
# {"type":"answer","content":"The five pillars are..."}
```

---

## 15. Cost Optimization & Scaling

### AWS

- **Karpenter + Spot:** GPU nodes use Spot pricing (~70% cost reduction)
- **Scale-to-Zero:** Ray autoscaler terminates idle workers; Karpenter deprovisions empty nodes (TTL 30s)
- **Aurora Serverless v2:** Scales down to 0.5 ACUs when idle

### Azure

- **Cluster autoscaler:** Node pools scale 1→2 (system) and 1→3 (app) automatically
- **Stop/Start:** AKS and PostgreSQL can be stopped to save ~$3.69/day
- **Redis:** Basic C0 (250MB) — upgrade to Standard C1 for persistence/replication (+$1.50/day)

### General

```bash
# Scale app node pool to 0 during development
az aks nodepool scale \
  --resource-group rag-platform-rg \
  --cluster-name rag-platform-aks \
  --name app --node-count 0
# Saves ~$2.00/day
```

---

## 16. Troubleshooting

### Pod Stuck in Pending

```bash
kubectl describe pod <pod-name>
# Look for: "Insufficient cpu", "Insufficient memory", "disk-pressure"
# Fix: Delete other pods to free resources, or scale up node pool
```

### ImagePullBackOff on AKS

```bash
# Ensure ACR is attached to AKS
az aks update --resource-group rag-platform-rg \
  --name rag-platform-aks --attach-acr ragplatformacr

# Build with correct platform (M1/M2 Mac → AKS is amd64)
az acr build --registry ragplatformacr \
  --image rag-backend-api:latest --platform linux/amd64 \
  --file services/api/Dockerfile services/api/
```

### QDRANT_PORT Collision

Kubernetes auto-injects `QDRANT_PORT=tcp://...` (service discovery) which conflicts with the integer config field. Fix:

```bash
kubectl patch secret app-env-secret \
  --type='json' \
  -p="[{\"op\":\"add\",\"path\":\"/data/QDRANT_PORT\",\"value\":\"$(echo -n '6333' | base64)\"}]"
kubectl rollout restart deployment/api-deployment
```

### API CrashLoopBackOff — `chat_history` Table Missing

The PostgreSQL schema must be initialized after first deployment:

```bash
POD=$(kubectl get pods -l app=api -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$POD" -- python3 -c "
import asyncio, sys; sys.path.insert(0, '/app')
from app.memory.postgres import Base, engine
async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(init())
"
```

### Chat UI Shows "Degraded"

The readiness endpoint returns `graphdb`, not `neo4j`. Ensure you are running the latest image — older images had a key mismatch in the UI health check.

### Terraform State Lock

```bash
terraform force-unlock -force <LOCK_ID>
```

### Azure PostgreSQL LocationIsOfferRestricted

The Flexible Server Burstable tier is restricted in `eastus` and `eastus2`. Use `centralus` or `westus`:

```hcl
location = "centralus"
```

---

## Repository Structure

```
scalable-rag-pipeline/
├── services/api/              # FastAPI backend + Chat UI
│   ├── app/
│   │   ├── agents/            # LangGraph state machine (planner, retriever, responder)
│   │   ├── auth/              # JWT, JWKS, tenant context
│   │   ├── cache/             # Redis exact + semantic cache
│   │   ├── clients/           # Provider-abstracted clients
│   │   │   ├── vectordb/      # Qdrant (swappable)
│   │   │   ├── graphdb/       # Neo4j + null (swappable)
│   │   │   ├── storage/       # S3 + Azure Blob (swappable)
│   │   │   └── secrets/       # Env + AWS SM + Azure KV (swappable)
│   │   ├── enhancers/         # HyDE, query rewriter
│   │   ├── memory/            # Postgres chat history
│   │   ├── middleware/        # Rate limiting
│   │   ├── routes/            # chat, upload, health, auth, feedback
│   │   ├── tenants/           # Multi-tenant config + registry
│   │   ├── tools/             # Calculator, web search, code sandbox
│   │   ├── config.py          # Pydantic settings (all env vars)
│   │   └── observability.py   # OTel setup (OTLP/X-Ray/Azure Monitor)
│   ├── main.py                # FastAPI app + lifespan
│   ├── static/                # Chat UI (index.html)
│   ├── tests/                 # 132 tests
│   ├── Dockerfile             # Multi-stage, non-root, python:3.10-slim
│   └── requirements.txt
├── pipelines/ingestion/       # Distributed Ray ingestion pipeline
│   ├── loaders/               # PDF, DOCX, HTML parsers
│   ├── chunking/              # Text splitter + metadata
│   ├── embedding/             # Embedding compute
│   ├── graph/                 # Entity extraction → Neo4j
│   └── indexing/              # Qdrant + Neo4j writers
├── infra/terraform/           # AWS infrastructure
│   ├── eks.tf, vpc.tf, rds.tf, redis.tf, s3.tf, iam.tf, karpenter.tf
│   └── azure/                 # Azure infrastructure
│       ├── aks.tf, vnet.tf, postgres.tf, redis.tf, acr.tf, storage.tf, iam.tf
│       └── terraform.tfvars.example
├── deploy/
│   ├── helm/api/              # API Helm chart (values.yaml + values-azure.yaml)
│   ├── helm/qdrant/           # Qdrant Helm values
│   ├── helm/neo4j/            # Neo4j Helm values
│   ├── ray/                   # Ray Cluster + Serve configs
│   ├── ingress/               # NGINX + Kong ingress manifests
│   └── secrets/               # External Secrets operator
├── scripts/                   # Operational scripts
│   ├── ingest_openai.py       # Quick ingestion (OpenAI + Qdrant)
│   ├── ingest_local.py        # Local ingestion (Ollama)
│   ├── init_db.py             # PostgreSQL schema creation
│   ├── init_qdrant.py         # Qdrant collection creation
│   ├── bootstrap_cluster.sh   # AWS EKS bootstrap
│   ├── bootstrap_cluster_azure.sh # Azure AKS bootstrap
│   └── load_test.py           # Load testing
├── .github/workflows/
│   ├── ci.yml                 # Lint + Test + Docker Build + Terraform Validate
│   └── deploy.yml             # Manual deploy (AWS or Azure)
├── eval/                      # RAGAS evaluation framework
├── docs/                      # Architecture, security, scaling, cost model
├── libs/                      # Shared: observability, retry, schemas
├── models/                    # vLLM/BGE model configs (YAML)
├── data/test-docs/            # Sample documents for ingestion
├── docker-compose.yml         # Local development stack
└── Makefile                   # Developer shortcuts
```

---

## Contributing

1. Create a feature branch: `git checkout -b feature/amazing-feature`
2. Run tests: `make test` — all 132 must pass
3. Commit your changes
4. Open a Pull Request — CI runs automatically

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
