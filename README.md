# Enterprise Agentic RAG Platform

![Architecture](https://img.shields.io/badge/Architecture-Agentic%20LangGraph-blueviolet)
![Orchestration](https://img.shields.io/badge/Orchestration-LangGraph%20%2B%20Ray-orange)
![Cloud](https://img.shields.io/badge/Cloud-AWS%20%7C%20Azure-blue)
![Tests](https://img.shields.io/badge/Tests-198%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

Turn any document corpus into an **intelligent, conversational knowledge base** — deployed as a fully managed SaaS or inside a customer's own cloud — with enterprise-grade security, data residency, and zero vendor lock-in.

### Why This Platform

| Business Need | How It's Solved |
|--------------|----------------|
| **Data residency & compliance** | Control Plane / Data Plane split — customer data never leaves their cloud region; mTLS secures every cross-plane call |
| **Zero vendor lock-in** | Provider-abstraction layer — swap LLMs (vLLM ↔ OpenAI), vector DBs, storage, and secrets backends with a single env var |
| **Multi-tenant SaaS at scale** | Per-tenant auth, rate limiting, usage metering, and isolated data planes — onboard new customers without redeploying |
| **Accurate, grounded answers** | Agentic LangGraph pipeline: intent classification → hybrid vector + knowledge-graph retrieval → LLM synthesis → automated quality scoring |
| **Multi-cloud portability** | Identical codebase deploys to AWS EKS and Azure AKS with cloud-specific Terraform, Helm, and secrets integrations |
| **Cost efficiency** | Spot/GPU scale-to-zero via Karpenter, semantic caching (Redis), and dedicated embedding models separate from the generative LLM |

### Technology Stack

Built on **FastAPI**, **LangGraph**, **Qdrant**, **Neo4j**, **Ray/vLLM**, and **Kubernetes** — with 198 tests, CI/CD pipelines, and full observability (OpenTelemetry, X-Ray, Azure Monitor).

## Quick Start (Local Development)

```bash
# 1. Install Python dependencies
make install

# 2. Start local databases (Postgres, Redis, Qdrant, Neo4j, MinIO)
make up

# 3. Configure environment
cp .env.example .env
# Edit .env: set LLM_PROVIDER, EMBED_MODEL, etc.

# 4. Initialize datastores (tables, collections, indexes, buckets)
make init

# 5. Ingest sample documents
python3 scripts/ingest_local.py --sample

# 6. Start the API server (with hot reload)
make dev
```

Open the **Chat UI** at `http://localhost:8000/`.

| Component       | Service                 | Port        |
|----------------|------------------------|-------------|
| LLM + Embed    | Ollama or OpenAI API   | 11434 / API |
| Vector DB      | Qdrant (Docker)        | 6333        |
| Graph DB       | Neo4j (Docker)         | 7474 / 7687 |
| SQL DB         | Postgres (Docker)      | 5432        |
| Cache          | Redis (Docker)         | 6379        |
| Object Storage | MinIO (Docker)         | 9000 / 9001 |

## Architecture Overview

```
Client  -->  Chat UI (built-in SPA)
                |
                v
         NGINX Ingress (Load Balancer)
                |
                v
         FastAPI API Server
                |
     +----------+----------+
     v          v          v
  LangGraph   Cache     Memory
  Agent       (Redis)   (Postgres)
     |
     +-- Planner           -- intent classification (retrieve / data_query / tool_use)
     +-- Retriever         -- hybrid vector + graph search + re-ranking
     +-- Data Analytics    -- text-to-SQL → execute → tables + charts (optional)
     +-- Context Enricher  -- business glossary, metadata, code/pipeline context (optional)
     +-- Responder         -- LLM answer synthesis (docs + data + business context)
     +-- Evaluator         -- answer quality scoring
                |
     +----------+---------+
     v          v         v
  Qdrant     Neo4j    Ray Serve
  (vectors)  (graph)  (LLM/Embed)
```

### Control Plane / Data Plane (SaaS Mode)

For multi-tenant SaaS deployments with data residency requirements, the platform splits into two independent services:

```
                     +---------------------------+
                     |     Control Plane (SaaS)  |
                     |  Auth, Routing, Rate Limit|
                     |  Tenant & Usage Mgmt      |
                     +------+--------+-----------+
                            |        |
               REST + mTLS  |        |  REST + mTLS
                            v        v
              +-------------+--+  +--+-------------+
              | Data Plane A   |  | Data Plane B   |
              | Customer: Acme |  | Customer: Globex|
              | Region: eu-w-1 |  | Region: us-e-1 |
              | LLM + Qdrant + |  | LLM + Qdrant + |
              | Neo4j + PG     |  | Neo4j + PG     |
              +----------------+  +----------------+
```

| Mode | `DEPLOYMENT_MODE` | Use Case |
|------|-------------------|----------|
| `monolith` | (default) | Single-instance dev/prod |
| `control_plane` | CP only | SaaS management: auth, routing, proxy, admin |
| `data_plane` | DP only | Customer-deployed: query processing, single-tenant |

See [Architecture docs](docs/architecture.md#9-control-plane--data-plane-architecture) for full details.

### Key Design Principles

- **Agentic reasoning** via LangGraph state machine (plan, retrieve, respond, evaluate)
- **Hybrid retrieval** combining vector search (Qdrant) + knowledge graph (Neo4j) + optional re-ranking
- **Dedicated embedding model** (`nomic-embed-text` / `bge-m3`) separate from the generative LLM
- **Multi-cloud** --- identical codebase runs on AWS EKS or Azure AKS
- **Multi-tenant** --- per-tenant data isolation, config, rate limits, and auth
- **Control plane / data plane** --- SaaS-ready split with data residency, mTLS, per-tenant rate limiting
- **Context layer enrichment** --- optional 4-layer business context (glossary, metadata, code/pipeline, business rules) injected at query time
- **Data analytics agent** --- text-to-SQL engine with safety guardrails, auto-schema discovery, tables + Vega-Lite charts in chat UI
- **Provider-abstraction** --- every component (LLM, storage, vector DB, secrets, reranker) is swappable via env vars

### Provider Abstraction

| Component | Env Var | Options |
|-----------|---------|---------|
| LLM | `LLM_PROVIDER` | `ray` (self-hosted vLLM), `openai` |
| Embeddings | `EMBED_PROVIDER` / `EMBED_MODEL` | `ray` + `nomic-embed-text`, `openai` + `text-embedding-3-small` |
| Re-ranker | `RERANKER_PROVIDER` | `none`, `llm` (LLM-based scoring), `cross_encoder` (dedicated model) |
| Context Layers | `CONTEXT_LAYERS_ENABLED` | `false` (off), `true` (glossary, metadata, code, business rules) |
| Data Analytics | `DATA_ANALYTICS_ENABLED` | `false` (off), `true` (text-to-SQL with tables + charts) |
| Vector DB | `VECTORDB_PROVIDER` | `qdrant` |
| Graph DB | `GRAPHDB_PROVIDER` | `neo4j`, `none` (disable) |
| Storage | `STORAGE_PROVIDER` | `s3` (AWS), `azure_blob` (Azure) |
| Secrets | `SECRETS_PROVIDER` | `env`, `aws_sm` (Secrets Manager), `azure_kv` (Key Vault) |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture & Design](docs/architecture.md) | System design, agentic pipeline, retrieval strategies, multi-tenancy, CP/DP split |
| [AWS Deployment](docs/deployment-aws.md) | EKS provisioning, staging/prod environments, bootstrap, cost management |
| [Azure Deployment](docs/deployment-azure.md) | AKS provisioning, Workload Identity, Key Vault integration |
| [API Reference & Chat UI](docs/api-reference.md) | Endpoints (monolith + CP/DP), streaming protocol, sample queries, Chat UI |
| [Operations Guide](docs/operations.md) | CI/CD, observability, testing, security, troubleshooting, split-plane ops |
| [Security](docs/security.md) | Security model, mTLS, API key auth, rate limiting, threat model |
| [Scaling](docs/scaling.md) | Autoscaling strategy, per-tenant data plane scaling, capacity planning |
| [Request Flow](docs/request_flow.md) | Step-by-step query lifecycle (monolith + split-plane modes) |
| [Roadmap](docs/ROADMAP.md) | Enterprise features, SaaS connectors, zero trust roadmap |

## Make Commands

```
Monolith:
  make install               Install Python dependencies
  make up                    Start local DBs via Docker Compose
  make init                  Initialize DBs, collections, indexes, buckets
  make dev                   Run FastAPI server locally (hot reload, port 8000)
  make test                  Run monolith test suite (132 tests)
  make seed-olist            Load Olist e-commerce dataset for data analytics
  make seed-dataset NAME=x   Load any CSV dataset with auto-schema discovery
  make down                  Stop local DBs

Split-Plane:
  make dev-control-plane     Run control plane locally (port 8001)
  make dev-data-plane        Run data plane locally (port 8080)
  make dev-split             Run both planes via Docker Compose
  make test-control-plane    Run control plane tests (48 tests)
  make test-data-plane       Run data plane tests (18 tests)
  make test-all              Run all tests (198 tests across 3 suites)

Cloud:
  make infra                 Provision AWS prod infrastructure (Terraform)
  make infra-staging         Provision AWS staging infrastructure
  make bootstrap             Bootstrap prod EKS cluster
  make bootstrap-staging     Bootstrap staging EKS cluster
  make deploy-staging        Full staging deploy (infra + bootstrap)
```

## Project Structure

```
scalable-rag-pipeline/
+-- services/
|   +-- api/                      # Monolith: FastAPI backend + Chat UI
|   |   +-- app/
|   |   |   +-- agents/           # LangGraph nodes (planner, retriever, context_enricher, responder, evaluator)
|   |   |   +-- context/          # Context layer architecture (glossary, metadata, business rules, code context)
|   |   |   +-- clients/          # Provider-abstracted clients
|   |   |   |   +-- vectordb/     # Qdrant (Protocol + Factory)
|   |   |   |   +-- graphdb/      # Neo4j (Protocol + Factory)
|   |   |   |   +-- storage/      # S3 / Azure Blob (Protocol + Factory)
|   |   |   |   +-- secrets/      # env / AWS SM / Azure KV (Protocol + Factory)
|   |   |   |   +-- reranker/     # none / LLM / cross-encoder (Protocol + Factory)
|   |   |   +-- auth/             # JWT, JWKS, multi-tenant auth
|   |   |   +-- tenants/          # Per-tenant config & registry
|   |   |   +-- memory/           # Postgres chat history
|   |   +-- static/index.html     # Built-in Chat UI (dark-theme SPA)
|   |   +-- tests/                # 132 monolith tests
|   |   +-- Dockerfile
|   +-- control-plane/            # Control Plane: SaaS management layer
|   |   +-- app/
|   |   |   +-- auth/             # JWT auth (local + JWKS)
|   |   |   +-- middleware/       # Per-tenant rate limiting (sliding window)
|   |   |   +-- models/           # Tenant, DataPlane, UsageEvent (SQLAlchemy)
|   |   |   +-- proxy/            # Streaming proxy, mTLS, tenant routing
|   |   |   +-- registry/         # Data plane health monitor
|   |   |   +-- routes/           # Auth, tenants, data planes, proxy, usage, health
|   |   +-- main.py               # FastAPI app (port 8001)
|   |   +-- tests/                # 48 control plane tests
|   |   +-- Dockerfile
|   +-- data-plane/               # Data Plane: customer-deployed query processing
|       +-- app/
|       |   +-- auth/             # API key validation + user context forwarding
|       |   +-- registration/     # Heartbeat loop to control plane
|       |   +-- routes/           # Chat, upload, health
|       +-- main.py               # FastAPI app (port 8080)
|       +-- tests/                # 18 data plane tests
|       +-- Dockerfile
+-- scripts/                      # Bootstrap, init, ingest, debug
+-- deploy/
|   +-- helm/api/                 # API Helm chart + values-{staging,prod,azure}.yaml
|   +-- helm/qdrant/              # Qdrant Helm values
|   +-- helm/neo4j/               # Neo4j Helm values
|   +-- karpenter/                # NodePool + EC2NodeClass (envsubst templates)
|   +-- ray/                      # RayCluster + RayServe manifests
|   +-- ingress/                  # NGINX Ingress rules
|   +-- secrets/                  # ExternalSecret manifests
+-- infra/terraform/              # AWS infrastructure (EKS, Aurora, Redis, S3, IAM)
|   +-- envs/staging.tfvars       # Staging variables
|   +-- azure/                    # Azure infrastructure (AKS, PostgreSQL, Redis, Blob, ACR)
+-- eval/                         # RAG evaluation datasets
+-- .github/workflows/            # CI (lint + test) + CD (deploy)
```

## License

MIT
