# Enterprise Agentic RAG Platform

![Architecture](https://img.shields.io/badge/Architecture-Event--Driven-blueviolet)
![Orchestration](https://img.shields.io/badge/Orchestration-LangGraph%20%2B%20Ray-orange)
![Infrastructure](https://img.shields.io/badge/Infrastructure-AWS%20EKS%20%2B%20Terraform-blue)
![Compute](https://img.shields.io/badge/AI%20Compute-Nvidia%20A10G%20%2F%20vLLM-green)

## Table of Contents
- [Quick Start (Local Development)](#quick-start-local-development)
1. [System Overview](#1-system-overview)
2. [RAG Methodologies & Agentic Logic](#2-rag-methodologies--agentic-logic)
3. [Prerequisites & Tooling](#3-prerequisites--tooling)
4. [Phase 1: Infrastructure Initialization (Terraform)](#4-phase-1-infrastructure-initialization-terraform)
5. [Phase 2: Cluster Bootstrapping (Kubernetes)](#5-phase-2-cluster-bootstrapping-kubernetes)
6. [Phase 3: The Data Plane (Ray & Databases)](#6-phase-3-the-data-plane-ray--databases)
7. [Phase 4: The Control Plane (API Deployment)](#7-phase-4-the-control-plane-api-deployment)
8. [Phase 5: Data Ingestion Pipeline](#8-phase-5-data-ingestion-pipeline)
9. [Validation & Testing](#9-validation--testing)
10. [Cost Optimization & Scaling](#10-cost-optimization--scaling)
11. [Troubleshooting](#11-troubleshooting)

---

## Quick Start (Local Development)

Run the full RAG pipeline on your machine — no AWS, no Kubernetes, no GPU required.

### Prerequisites

- **Python 3.10+**
- **Docker** (for Postgres, Redis, Qdrant, Neo4j, MinIO)
- **[Ollama](https://ollama.com)** with a model pulled (e.g., `ollama pull llama3`)

### Setup

```bash
# 1. Install Python dependencies
make install

# 2. Start local databases (Postgres, Redis, Qdrant, Neo4j, MinIO)
make up

# 3. Configure environment
cp .env.example .env
# Edit .env — set endpoints to Ollama:
#   RAY_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
#   RAY_EMBED_ENDPOINT=http://localhost:11434/api/embeddings
#   LLM_MODEL=llama3

# 4. Initialize datastores (tables, collections, indexes, buckets)
make init

# 5. Ingest sample documents
python3 scripts/ingest_local.py --sample

# 6. Start the API server
make dev
```

### Usage

```bash
# Get a dev JWT token
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "dev-user"}'

# Ask a question (replace <TOKEN> with access_token from above)
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"message": "Who founded Acme Corp?"}'
```

### Local Architecture

| Component | Local Service | Port |
|-----------|--------------|------|
| LLM + Embeddings | Ollama | 11434 |
| Vector DB | Qdrant (Docker) | 6333 |
| Graph DB | Neo4j (Docker) | 7474 / 7687 |
| SQL DB | Postgres (Docker) | 5432 |
| Cache | Redis (Docker) | 6379 |
| Object Storage | MinIO (Docker) | 9000 / 9001 |

### Ingest Your Own Documents

```bash
# Ingest a single text/markdown file
python3 scripts/ingest_local.py path/to/document.txt

# Ingest the built-in sample dataset
python3 scripts/ingest_local.py --sample
```

### Available Make Commands

```
make install    Install Python dependencies
make up         Start local DBs (Docker)
make init       Initialize DBs, collections, indexes, buckets
make dev        Run FastAPI server locally (hot reload)
make down       Stop local DBs
make test       Run tests
```

## 1. System Overview

This repository contains the source code and Infrastructure-as-Code (IaC) definitions for a production-grade **Retrieval-Augmented Generation (RAG)** system. Unlike standard RAG implementations, this platform utilizes an **Agentic Architecture** (via LangGraph) to perform multi-step reasoning, query expansion, and hybrid retrieval (Vector + Knowledge Graph).

### High-Level Architecture

The system is decoupled into two primary processing planes:
1.  **Control Plane (The Brain):** Handles HTTP requests, state management, agent orchestration, and business logic. Runs on low-cost CPU nodes.
2.  **Data Plane (The Muscle):** Handles heavy compute tasks including LLM Inference, Embedding generation, and Graph Extraction. Runs on autoscaling GPU nodes via **Ray**.

<img src="https://miro.medium.com/v2/resize:fit:4800/format:webp/1*UjVAQrrQcw5lKN4NuuhB1g.jpeg" alt="RAG Platform Architecture" />

---

## 2. RAG Methodologies & Agentic Logic

This platform implements advanced RAG techniques to solve common failure modes (hallucination, retrieval misses).

### 2.1. The Planning Agent (`services/api/app/agents/`)
Instead of a linear chain, we use **LangGraph** to model the RAG process as a state machine.
*   **Planner Node:** Analyzes user intent. Decides whether to perform a direct answer, a retrieval, or use a tool (Code Interpreter).
*   **Query Rewriter:** Uses an LLM to rewrite the user's query, resolving coreferences (e.g., changing "How much does *it* cost?" to "How much does *Kubernetes* cost?").
*   **HyDE (Hypothetical Document Embeddings):** Generates a fake "ideal" answer, embeds it, and uses that vector to find real documents. This bridges the semantic gap between a question and a declarative statement.

### 2.2. Hybrid Retrieval
*   **Vector Search (Qdrant):** Uses **BGE-M3** embeddings (dense retrieval) to find semantically similar text chunks.
*   **Graph Search (Neo4j):** Executes Cypher queries to find entities and their relationships (e.g., `(Entity A)-[RELATED_TO]->(Entity B)`). This captures structural knowledge that vector search misses.

---

## 3. Prerequisites & Tooling

Ensure the following tools are installed on your workstation (Bastion Host):

*   **AWS CLI (`v2.x`):** Configured with AdministratorAccess.
*   **Terraform (`v1.5+`):** For infrastructure provisioning.
*   **Kubectl (`v1.29+`):** For Kubernetes interaction.
*   **Helm (`v3.x`):** For chart management.
*   **Python (`3.10+`)**: For local scripting.
*   **Docker:** For building container images.

---

## 4. Phase 1: Infrastructure Initialization (Terraform)

We use Terraform to provision the "Hardware" layer: VPC, EKS Control Plane, S3, and RDS.

### 4.1. Remote State Setup (Manual Step)
Terraform requires a backend to store the state file safely.
1.  Log in to the **AWS Console**.
2.  Navigate to **S3** and create a bucket named: `rag-platform-terraform-state-prod-001` (Must be unique globally).
3.  Navigate to **DynamoDB** and create a table named `terraform-state-lock`.
    *   **Partition Key:** `LockID` (String).

### 4.2. Provisioning Resources
Navigate to the infrastructure directory:
```bash
cd infra/terraform
```

Initialize the backend and providers:
```bash
terraform init
```

Review the execution plan. This will show creation of:
*   **VPC:** 10.0.0.0/16 with 3 Public, 3 Private, and 3 Database subnets.
*   **EKS:** Cluster named `rag-platform-cluster` (Version 1.29).
*   **RDS:** Aurora Postgres Serverless v2.
*   **IAM:** OIDC Providers and IRSA roles.

```bash
terraform plan -var="db_password=YourStrongPassword#123" -out=tfplan
```

Apply the infrastructure (Estimated time: 20 minutes):
```bash
terraform apply tfplan
```

### 4.3. Connection Configuration
Once Terraform completes, configure `kubectl` to communicate with the new cluster:
```bash
aws eks update-kubeconfig --region us-east-1 --name rag-platform-cluster
```

Verify connectivity:
```bash
kubectl get nodes
# Expected Output: ip-10-0-x-x.ec2.internal   Ready   <none>   m6i.large
```

---

## 5. Phase 2: Cluster Bootstrapping (Kubernetes)

The EKS cluster is currently empty. We need to install the core system controllers.

### 5.1. Run Bootstrap Script
Execute the helper script to install **Karpenter** (Autoscaler), **KubeRay Operator**, **External Secrets**, and **Ingress Controller**.

```bash
cd scripts
chmod +x bootstrap_cluster.sh
./bootstrap_cluster.sh
```

### 5.2. Configure Karpenter Provisioners
Karpenter is responsible for analyzing unschedulable pods and spinning up EC2 instances dynamically.

**Apply the CPU Provisioner (For API & System pods):**
```bash
kubectl apply -f infra/karpenter/provisioner-cpu.yaml
```
*   *Technical Detail:* This targets `m6i`, `c6i` instances and uses Spot pricing where available.

**Apply the GPU Provisioner (For AI Inference):**
```bash
kubectl apply -f infra/karpenter/provisioner-gpu.yaml
```
*   *Technical Detail:* This targets `g5` (Nvidia A10G) instances. It creates a taint `nvidia.com/gpu=true:NoSchedule` to prevent non-AI pods from accidentally using expensive nodes.

---

## 6. Phase 3: The Data Plane (Ray & Databases)

We now deploy the "Muscle" of the system.

### 6.1. Deploy Vector & Graph Databases
In a full production environment, you might use Terraform managed services (AWS Neptune / Qdrant Cloud), but for this setup, we deploy HA clusters inside K8s.

```bash
# Deploy Qdrant
helm upgrade --install qdrant deploy/helm/qdrant --namespace default

# Deploy Neo4j
helm upgrade --install neo4j deploy/helm/neo4j --namespace default
```

### 6.2. Deploy Ray Cluster
The Ray Cluster consists of a Head Node (orchestrator) and Worker Groups.
```bash
kubectl apply -f deploy/ray/ray-cluster.yaml
```
*Verification:*
```bash
kubectl get pods -l ray.io/cluster=rag-ray-cluster
# Wait until the 'ray-head' pod is Running.
```

### 6.3. Deploy Model Services (Ray Serve)
We deploy two separate Ray Services. These utilize the `ServeConfigV2` specification.

**A. Embedding Service (BGE-M3):**
```bash
kubectl apply -f deploy/ray/ray-serve-embed.yaml
```

**B. LLM Service (vLLM / Llama-3-70B):**
This is the most resource-intensive step.
```bash
kubectl apply -f deploy/ray/ray-serve-llm.yaml
```

**What happens technically:**
1.  The `RayService` CRD submits a request to the Ray Head.
2.  Ray realizes it needs 1 GPU (`nvidia.com/gpu: 1` resource request).
3.  The Ray Worker pod goes into `Pending` state.
4.  **Karpenter** detects the pending pod, calls AWS Fleet API, and provisions a `g5.xlarge` instance.
5.  Once the node joins (approx. 90s), the pod starts, downloads the weights (approx. 40GB) from HuggingFace, and initializes the vLLM engine (PagedAttention).

---

## 7. Phase 4: The Control Plane (API Deployment)

### 7.1. Secret Management
Create the Kubernetes Secret containing database credentials and keys.
```bash
kubectl create secret generic app-env-secret \
  --from-literal=DATABASE_URL="postgresql+asyncpg://ragadmin:YourStrongPassword#123@rag-platform-cluster-postgres.cluster-xxxx.us-east-1.rds.amazonaws.com:5432/rag_db" \
  --from-literal=REDIS_URL="redis://rag-redis-prod.xxxx.ng.0001.use1.cache.amazonaws.com:6379/0" \
  --from-literal=NEO4J_PASSWORD="password" \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=QDRANT_HOST="qdrant" \
  --from-literal=RAY_LLM_ENDPOINT="http://llm-service:8000/llm" \
  --from-literal=RAY_EMBED_ENDPOINT="http://embed-service:8000/embed"
```

### 7.2. Deploy the API
Deploy the FastAPI application using Helm.
```bash
helm upgrade --install api deploy/helm/api
```

### 7.3. Apply Ingress
Configure the Load Balancer to route traffic to the API.
```bash
kubectl apply -f deploy/ingress/nginx.yaml
```
*   *Note:* Get your Load Balancer DNS name via `kubectl get ingress`. Map your domain (CNAME) to this DNS.

---

## 8. Phase 5: Data Ingestion Pipeline

The system requires data to function. The ingestion pipeline is an asynchronous, distributed Ray Job.

### 8.1. Bulk Upload to S3
Upload your dataset (PDF, DOCX, HTML) to the S3 bucket created by Terraform.
```bash
# Retrieve bucket name
BUCKET_NAME=$(cd infra/terraform && terraform output -raw s3_documents_bucket_name)

# Run bulk uploader script
python scripts/bulk_upload_s3.py ./data/finance_reports $BUCKET_NAME
```

### 8.2. Trigger Ingestion Job
Normally triggered by S3 Events, we can manually submit the job to the Ray Cluster.

1.  **Port Forward Ray Dashboard:**
    ```bash
    kubectl port-forward service/rag-ray-cluster-head-svc 8265:8265
    ```

2.  **Submit Job via Python SDK:**
    ```bash
    python -m pipelines.jobs.s3_event_handler
    ```

**Technical Workflow:**
1.  **Ray Data** reads binaries from S3 lazily.
2.  **MapBatches (CPU):** `unstructured` library parses PDFs (OCR via Tesseract if needed) and chunks text (512 tokens).
3.  **MapBatches (GPU - Embed):** Chunks are sent to the `embed-service` Actor.
4.  **MapBatches (GPU - Graph):** Chunks are sent to the `llm-service` to extract `(Subject, Predicate, Object)` tuples.
5.  **Write:**
    *   Vectors -> Qdrant (Upsert).
    *   Nodes/Edges -> Neo4j (MERGE queries).

---

## 9. Validation & Testing

### 9.1. Health Checks
Verify the API connects to all subsystems.
```bash
curl https://<YOUR_ALB_DNS>/health/readiness
# Expected: {"redis": "up", "neo4j": "up"}
```

### 9.2. End-to-End Chat Test
Perform a request to verify the Agentic flow (Authentication required).

1.  **Obtain Token (Dev Mode):** Use the `jwt.py` utility or disable auth in `config.py` temporarily for testing.
2.  **Curl Request:**
    ```bash
    curl -X POST https://<YOUR_ALB_DNS>/api/v1/chat/stream \
      -H "Content-Type: application/json" \
      -d '{
        "message": "Analyze the financial risks mentioned in the Q3 report.",
        "session_id": "test-session-1"
      }'
    ```

---

## 10. Cost Optimization & Scaling

The system uses aggressive scaling policies to minimize costs:

1.  **Spot Instances:** `provisioner-gpu.yaml` is configured to request Spot instances (`karpenter.sh/capacity-type: spot`). This reduces GPU costs by ~70%.
2.  **Scale-to-Zero:**
    *   The **Ray Autoscaler** is configured in `ray-serve-llm.yaml` with `min_replicas: 1` (can be 0 for dev).
    *   If `min_replicas` is 0 and no requests arrive, Ray kills the Pod.
    *   **Karpenter** sees the node is empty (TTL 30s) and terminates the EC2 instance.

---

## 11. Troubleshooting

*   **Pod Pending (Insufficient CPU/Mem):** Check `kubectl describe pod <pod_name>`. If it says `FailedScheduling`, check if Karpenter logs show `launching node`.
*   **Ray Actor Death:** Check Ray Dashboard `http://localhost:8265`. Common issue is OOM (Out Of Memory) on the GPU. Decrease `max_num_seqs` in `llama-70b.yaml`.
*   **Database Connection Refused:** Ensure Security Groups in `infra/terraform/vpc.tf` allow traffic on ports 5432 (Postgres), 6333 (Qdrant), and 7687 (Neo4j) from the EKS Subnet CIDR.

---

## 12. Contributing

1.  Create a feature branch (`git checkout -b feature/amazing-feature`).
2.  Commit your changes.
3.  Run tests (`make test`).
4.  Push to the branch.
5.  Open a Pull Request.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.