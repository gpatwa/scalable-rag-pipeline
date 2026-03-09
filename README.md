# Enterprise Agentic RAG Platform

![Architecture](https://img.shields.io/badge/Architecture-Agentic%20LangGraph-blueviolet)
![Orchestration](https://img.shields.io/badge/Orchestration-LangGraph%20%2B%20Ray-orange)
![Cloud](https://img.shields.io/badge/Cloud-AWS%20%7C%20Azure-blue)
![Tests](https://img.shields.io/badge/Tests-132%20passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

A production-grade, **multi-cloud**, **multi-tenant** Retrieval-Augmented Generation platform built on FastAPI, LangGraph, Qdrant, Neo4j, and Kubernetes. Supports both self-hosted (Ray/vLLM) and API-based (OpenAI) LLMs with a provider-abstraction pattern that makes every infrastructure component swappable.

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
Client  ──>  Chat UI (built-in SPA)
                │
                ▼
         NGINX Ingress (Load Balancer)
                │
                ▼
         FastAPI API Server
                │
     ┌──────────┼──────────────┐
     ▼          ▼              ▼
  LangGraph   Cache        Memory
  Agent       (Redis)      (Postgres)
     │
     ├── Planner    ── intent classification
     ├── Retriever  ── hybrid vector + graph search + re-ranking
     ├── Responder  ── LLM answer synthesis
     └── Evaluator  ── answer quality scoring
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
  Qdrant     Neo4j     Ray Serve
  (vectors)  (graph)   (LLM/Embed)
```

### Key Design Principles

- **Agentic reasoning** via LangGraph state machine (plan, retrieve, respond, evaluate)
- **Hybrid retrieval** combining vector search (Qdrant) + knowledge graph (Neo4j) + optional re-ranking
- **Dedicated embedding model** (`nomic-embed-text` / `bge-m3`) separate from the generative LLM
- **Multi-cloud** --- identical codebase runs on AWS EKS or Azure AKS
- **Multi-tenant** --- per-tenant data isolation, config, rate limits, and auth
- **Provider-abstraction** --- every component (LLM, storage, vector DB, secrets, reranker) is swappable via env vars

### Provider Abstraction

| Component | Env Var | Options |
|-----------|---------|---------|
| LLM | `LLM_PROVIDER` | `ray` (self-hosted vLLM), `openai` |
| Embeddings | `EMBED_PROVIDER` / `EMBED_MODEL` | `ray` + `nomic-embed-text`, `openai` + `text-embedding-3-small` |
| Re-ranker | `RERANKER_PROVIDER` | `none`, `llm` (LLM-based scoring), `cross_encoder` (dedicated model) |
| Vector DB | `VECTORDB_PROVIDER` | `qdrant` |
| Graph DB | `GRAPHDB_PROVIDER` | `neo4j`, `none` (disable) |
| Storage | `STORAGE_PROVIDER` | `s3` (AWS), `azure_blob` (Azure) |
| Secrets | `SECRETS_PROVIDER` | `env`, `aws_sm` (Secrets Manager), `azure_kv` (Key Vault) |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture & Design](docs/architecture.md) | System design, agentic pipeline, retrieval strategies, multi-tenancy |
| [AWS Deployment](docs/deployment-aws.md) | EKS provisioning, staging/prod environments, bootstrap, cost management |
| [Azure Deployment](docs/deployment-azure.md) | AKS provisioning, Workload Identity, Key Vault integration |
| [API Reference & Chat UI](docs/api-reference.md) | Endpoints, streaming protocol, sample queries, Chat UI |
| [Operations Guide](docs/operations.md) | CI/CD, observability, testing, security, troubleshooting |

## Make Commands

```
make install           Install Python dependencies
make up                Start local DBs via Docker Compose
make init              Initialize DBs, collections, indexes, buckets
make dev               Run FastAPI server locally (hot reload, port 8000)
make test              Run full test suite (132 tests)
make down              Stop local DBs

make infra             Provision AWS prod infrastructure (Terraform)
make infra-staging     Provision AWS staging infrastructure
make bootstrap         Bootstrap prod EKS cluster
make bootstrap-staging Bootstrap staging EKS cluster
make deploy-staging    Full staging deploy (infra + bootstrap)
```

## Project Structure

```
scalable-rag-pipeline/
├── services/api/              # FastAPI backend + Chat UI
│   ├── app/
│   │   ├── agents/            # LangGraph nodes (planner, retriever, responder, evaluator)
│   │   ├── clients/           # Provider-abstracted clients
│   │   │   ├── vectordb/      # Qdrant (Protocol + Factory)
│   │   │   ├── graphdb/       # Neo4j (Protocol + Factory)
│   │   │   ├── storage/       # S3 / Azure Blob (Protocol + Factory)
│   │   │   ├── secrets/       # env / AWS SM / Azure KV (Protocol + Factory)
│   │   │   └── reranker/      # none / LLM / cross-encoder (Protocol + Factory)
│   │   ├── auth/              # JWT, JWKS, multi-tenant auth
│   │   ├── tenants/           # Per-tenant config & registry
│   │   └── memory/            # Postgres chat history
│   ├── static/index.html      # Built-in Chat UI (dark-theme SPA)
│   └── Dockerfile
├── scripts/                   # Bootstrap, init, ingest, debug
├── deploy/
│   ├── helm/api/              # API Helm chart + values-{staging,prod,azure}.yaml
│   ├── helm/qdrant/           # Qdrant Helm values
│   ├── helm/neo4j/            # Neo4j Helm values
│   ├── karpenter/             # NodePool + EC2NodeClass (envsubst templates)
│   ├── ray/                   # RayCluster + RayServe manifests
│   ├── ingress/               # NGINX Ingress rules
│   └── secrets/               # ExternalSecret manifests
├── infra/terraform/           # AWS infrastructure (EKS, Aurora, Redis, S3, IAM)
│   ├── envs/staging.tfvars    # Staging variables
│   └── azure/                 # Azure infrastructure (AKS, PostgreSQL, Redis, Blob, ACR)
├── tests/                     # 132 tests
├── eval/                      # RAG evaluation datasets
└── .github/workflows/         # CI (lint + test) + CD (deploy)
```

## License

MIT
