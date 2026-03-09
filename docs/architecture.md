# RAG Platform — Architecture

## Core Principles

1. **Multi-cloud by design** — runs on AWS (EKS) and Azure (AKS) with a provider abstraction layer. No cloud lock-in.
2. **Decoupled compute** — the API orchestrator (CPU) is separate from the AI engines (GPU). Each scales independently.
3. **Hybrid retrieval** — combines vector search (semantic meaning) and graph search (entity relationships) for higher accuracy than either alone.
4. **Async ingestion** — document processing runs as a separate Ray pipeline, never blocking query latency.
5. **Zero static credentials** — all secrets live in Key Vault / Secrets Manager, injected at runtime via Workload Identity.

---

## 1. System Architecture (Multi-Cloud)

```mermaid
graph TB
    subgraph Clients["Client Layer"]
        Browser["Browser / Chat UI"]
        ExtAPI["External API Consumers"]
    end

    subgraph CICD["CI/CD (GitHub Actions)"]
        direction LR
        PR["Pull Request\n(feature branch)"]
        CI["CI Pipeline\nlint · test · build · push"]
        Staging["Auto-deploy\nto Staging"]
        Prod["Manual approval\nto Production"]
        PR --> CI --> Staging --> Prod
    end

    subgraph AWS["AWS Cloud"]
        ALB["ALB\nLoad Balancer"]
        subgraph EKS["EKS Cluster (Karpenter autoscale)"]
            direction TB
            Ingress_AWS["NGINX Ingress\nTLS · Rate Limit"]
            subgraph CPU_AWS["CPU Node Pool"]
                API_AWS["FastAPI\nOrchestrator"]
                Sandbox_AWS["Code Sandbox\n(isolated)"]
            end
            subgraph GPU_AWS["GPU Node Pool"]
                Ray_AWS["Ray Serve"]
                vLLM_AWS["vLLM Engine\nLlama-3-70B"]
                Embed_AWS["Embedding Engine\nnomic-embed-text / bge-m3"]
            end
            Qdrant_AWS["Qdrant\nVector DB"]
        end
        subgraph Managed_AWS["Managed Services"]
            Aurora["Aurora Postgres\n(chat history)"]
            ElastiCache["ElastiCache Redis\n(cache · sessions)"]
            S3["S3\n(documents)"]
            ECR["ECR\n(container registry)"]
            SM["Secrets Manager\n(credentials)"]
        end
    end

    subgraph Azure["Azure Cloud"]
        AFD["Azure Load Balancer"]
        subgraph AKS["AKS Cluster (Karpenter autoscale)"]
            direction TB
            Ingress_AZ["NGINX Ingress\nTLS · Rate Limit"]
            subgraph CPU_AZ["CPU Node Pool"]
                API_AZ["FastAPI\nOrchestrator"]
                Sandbox_AZ["Code Sandbox\n(isolated)"]
            end
            subgraph GPU_AZ["GPU Node Pool"]
                Ray_AZ["Ray Serve"]
                vLLM_AZ["vLLM Engine\nLlama-3-70B"]
                Embed_AZ["Embedding Engine\nnomic-embed-text / bge-m3"]
            end
            Qdrant_AZ["Qdrant\nVector DB"]
        end
        subgraph Managed_AZ["Managed Services"]
            PgFlex["Postgres Flex\n(chat history)"]
            AzRedis["Azure Cache\nfor Redis"]
            Blob["Blob Storage\n(documents)"]
            ACR["ACR\n(container registry)"]
            KeyVault["Key Vault\n(credentials)"]
        end
    end

    Browser --> ALB & AFD
    ExtAPI --> ALB & AFD

    ALB --> Ingress_AWS --> API_AWS
    AFD --> Ingress_AZ --> API_AZ

    API_AWS <--> Aurora & ElastiCache
    API_AWS --> Ray_AWS & Sandbox_AWS
    Ray_AWS --> vLLM_AWS & Embed_AWS
    Ray_AWS <--> Qdrant_AWS

    API_AZ <--> PgFlex & AzRedis
    API_AZ --> Ray_AZ & Sandbox_AZ
    Ray_AZ --> vLLM_AZ & Embed_AZ
    Ray_AZ <--> Qdrant_AZ

    SM -.->|"ESO + IRSA"| API_AWS
    KeyVault -.->|"ESO + Workload Identity"| API_AZ
```

---

## 2. Query Request Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant I as Ingress (NGINX)
    participant A as FastAPI API
    participant C as Semantic Cache (Redis)
    participant LG as LangGraph Agent
    participant E as Embedding Engine (Ray)
    participant V as Qdrant (Vector Search)
    participant G as Neo4j (Graph Search)
    participant R as Re-ranker
    participant L as vLLM (Llama-3)
    participant DB as Postgres

    U->>I: POST /api/v1/chat/stream (JWT)
    I->>I: TLS termination · Rate limit check
    I->>A: Forward request
    A->>A: JWT validation · Tenant context injection
    A->>C: Embed query → check semantic cache
    alt Cache HIT (similarity > 0.95)
        C-->>U: Stream cached answer (fast path ~50ms)
    else Cache MISS
        A->>LG: Start LangGraph execution
        LG->>E: Embed query
        par Parallel retrieval
            E->>V: Vector search (top-k chunks)
        and
            LG->>G: Graph search (entity relationships)
        end
        V-->>LG: Relevant chunks
        G-->>LG: Entity graph context
        LG->>R: Re-rank merged results (filter score < threshold)
        R-->>LG: Top-ranked chunks
        LG->>L: Synthesize answer (chunks + graph + query)
        L-->>U: Stream tokens as SSE
        Note over LG: Evaluator scores answer quality (0-1)
        LG-->>A: Final answer + evaluation score
        A->>DB: Save Q&A (background)
        A->>C: Update semantic cache (background)
    end
```

---

## 3. Document Ingestion Pipeline

```mermaid
flowchart LR
    subgraph Upload
        Client["Client\nUpload"]
        PSU["Presigned URL\n(S3 / Blob)"]
        Client -->|"PUT file directly"| PSU
    end

    subgraph Storage["Object Storage"]
        Bucket["S3 / Blob\nuploads/{tenant}/{user}/{file_id}"]
        PSU --> Bucket
    end

    subgraph Trigger
        Bucket -->|"Object created event"| RayJob
    end

    subgraph RayPipeline["Ray Ingestion Pipeline"]
        direction TB
        RayJob["Ray Job\nOrchestrator"]
        Parse["Parse & Extract\n(unstructured, pytesseract)"]
        Chunk["Text Chunker\n(recursive, semantic)"]
        EmbedI["Embedding Engine\nnomic-embed-text / bge-m3"]
        GraphEx["Graph Extractor\nvLLM (entity/relation)"]

        RayJob --> Parse --> Chunk
        Chunk --> EmbedI & GraphEx
    end

    subgraph Indexes
        QdrantIdx["Qdrant\nVector Index"]
        Neo4jIdx["Neo4j\nGraph Index"]
        EmbedI -->|"Upsert vectors"| QdrantIdx
        GraphEx -->|"Upsert nodes/edges"| Neo4jIdx
    end
```

---

## 4. CI/CD & Developer Lifecycle

```mermaid
flowchart LR
    subgraph Dev["Local Development"]
        Code["Write Code\n(feature branch)"]
        PreCommit["pre-commit hooks\nruff · terraform_fmt\ndetect-private-key"]
        Code --> PreCommit
    end

    subgraph PR["Pull Request"]
        GH["GitHub PR\nto main"]
        PreCommit --> GH
    end

    subgraph CI["CI Pipeline (ci.yml)"]
        direction TB
        Lint["Lint\n(ruff check)"]
        Tests["Tests\n(pytest · 173 tests)"]
        DockerBuild["Docker Build\n(125MB API image)"]
        TFValidate["Terraform\nValidate"]
        Lint --> Tests --> DockerBuild --> TFValidate
    end

    subgraph Staging["Staging Deploy (auto)"]
        PushImage_S["Push image\nstaging-sha"]
        HelmS["Helm upgrade\nvalues-staging.yaml\n1 replica · DEBUG logs"]
        PushImage_S --> HelmS
    end

    subgraph Prod["Production Deploy (manual)"]
        Approval["Environment\nApproval Gate"]
        PushImage_P["Re-tag image\nprod-sha"]
        HelmP["Helm upgrade\nvalues-prod.yaml\n2 replicas · WARNING logs"]
        Approval --> PushImage_P --> HelmP
    end

    GH --> CI
    CI -->|"merge to main"| Staging
    Staging -->|"manual trigger"| Prod
```

---

## 5. Secrets & Identity Architecture

```mermaid
flowchart TB
    subgraph Identity["Pod Identity (No Static Credentials)"]
        WI["Azure Workload Identity\n/ AWS IRSA"]
    end

    subgraph Vaults["Secret Stores"]
        KV["Azure Key Vault"]
        SM["AWS Secrets Manager"]
    end

    subgraph ESO["External Secrets Operator"]
        Sync["SecretStore\n(1hr refresh)"]
    end

    subgraph K8s["Kubernetes"]
        Secret["K8s Secret\n(synced)"]
        Pod["API Pod\n(env vars injected)"]
    end

    WI -->|"token exchange"| KV & SM
    KV & SM --> Sync --> Secret --> Pod

    subgraph Stored["Secrets Managed"]
        direction LR
        s1["db-password"]
        s2["redis-primary-key"]
        s3["neo4j-password"]
        s4["jwt-secret-key"]
        s5["openai-api-key"]
    end

    KV & SM -.-> Stored
```

---

## 6. Multi-Tenant Data Isolation

```mermaid
flowchart TD
    JWT["JWT Token\ntenant_id · user_id · role"]

    JWT --> API["FastAPI\nTenantContext injection"]

    API --> PG["Postgres\nWHERE tenant_id = ?"]
    API --> QD["Qdrant\nfilter: tenant_id"]
    API --> N4J["Neo4j\nWHERE n.tenant_id = ?"]
    API --> STORE["S3 / Blob\nuploads/{tenant_id}/{user_id}/..."]
    API --> REDIS["Redis\nKey prefix: tenant:{id}:..."]

    style JWT fill:#f5a623,color:#000
    style API fill:#4a90d9,color:#fff
```

---

## 7. Re-Ranking Layer

After hybrid retrieval merges vector + graph results, an optional re-ranker re-scores documents for relevance:

| Provider | Env Var | Latency | Use Case |
|----------|---------|---------|----------|
| `none` | `RERANKER_PROVIDER=none` | 0ms | Dev (fast iteration) |
| `llm` | `RERANKER_PROVIDER=llm` | ~200ms | Staging (single LLM call scores N docs) |
| `cross_encoder` | `RERANKER_PROVIDER=cross_encoder` | ~50ms | Production (dedicated Ray Serve model) |

**Design decisions:**
- Scores normalized to 0.0–1.0 range
- Threshold filtering (default 0.3) removes irrelevant chunks but always keeps at least 1
- Graceful failure — any error falls back to original document order
- Graph results are prioritized (merged before vector results)

---

## 8. Evaluator Node

The final LangGraph node scores answer quality on a 0-1 scale:
- Checks if the answer is grounded in the retrieved sources
- Detects hallucination or unsupported claims
- Score is returned to the client in the SSE stream
- Can be used for automated quality monitoring and feedback loops

---

## Component Summary

| Component | AWS | Azure | Purpose |
|-----------|-----|-------|---------|
| Kubernetes | EKS + Karpenter | AKS + Karpenter | Container orchestration, autoscaling |
| API | FastAPI (125MB image) | FastAPI (125MB image) | Query orchestration, auth, streaming |
| AI engines | Ray Serve + vLLM + Embedding | Ray Serve + vLLM + Embedding | LLM inference, embeddings (nomic-embed-text / bge-m3) |
| Re-ranker | none / LLM / cross-encoder | none / LLM / cross-encoder | Post-retrieval relevance scoring |
| Vector DB | Qdrant (in-cluster) | Qdrant (in-cluster) | Semantic similarity search |
| Graph DB | Neo4j AuraDB | Neo4j AuraDB | Entity relationship queries |
| Relational DB | Aurora Postgres | Postgres Flexible Server | Chat history, session state |
| Cache | ElastiCache Redis | Azure Cache for Redis | Semantic cache, rate limiting |
| Object storage | S3 | Blob Storage | Document storage, presigned uploads |
| Container registry | ECR | ACR | Docker images |
| Secret store | Secrets Manager + IRSA | Key Vault + Workload Identity | Credential management |
| Ingress | NGINX | NGINX | TLS termination, rate limiting |
| Observability | AWS X-Ray + CloudWatch | Azure Monitor + App Insights | Tracing, logging, metrics |

---

## Related Docs

- [AWS Deployment](deployment-aws.md) — EKS provisioning, staging/prod, bootstrap, cost management
- [Azure Deployment](deployment-azure.md) — AKS provisioning, Workload Identity, Key Vault
- [API Reference & Chat UI](api-reference.md) — endpoints, streaming protocol, sample queries
- [Operations Guide](operations.md) — CI/CD, observability, testing, security, troubleshooting
- [Request Flow](request_flow.md) — detailed step-by-step query lifecycle
- [Security](security.md) — security controls and threat model
- [Scaling](scaling.md) — autoscaling strategy and capacity planning
- [Roadmap](ROADMAP.md) — enterprise features and zero trust roadmap
