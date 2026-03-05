# docs/architecture.md

# RAG Platform Architecture

This document provides a high-level overview of the system's architecture.

## Core Principles

1.  **Decoupled Compute:** The API (Brain) is separate from the AI Engines (Muscle).
2.  **Scalability:** The system uses Kubernetes (EKS) and Karpenter to scale from zero to hundreds of nodes based on demand.
3.  **Hybrid Retrieval:** Combines Vector Search (for semantic meaning) and Graph Search (for relationships) for superior accuracy.
4.  **Asynchronous Processing:** Data ingestion is handled via a distributed Ray pipeline, triggered by S3 events, ensuring it never impacts user query latency.

## Architecture Diagram

```mermaid
graph TD
    subgraph "User Layer"
        User[Browser/Client]
    end

    subgraph "AWS Cloud"
        LB[AWS Load Balancer]
        subgraph "Kubernetes Cluster (EKS)"
            Ingress[Ingress: Nginx/Kong]
            subgraph "Services (CPU Nodes)"
                API[FastAPI Orchestrator]
                Sandbox[Code Sandbox]
            end
            subgraph "AI Engines (GPU Nodes)"
                Ray[Ray Serve Cluster]
                vLLM[vLLM Engine]
                Embed[Embedding Engine]
            end
            subgraph "Databases (Self-Hosted)"
                Qdrant[Qdrant Vector DB]
            end
        end
        subgraph "Managed Services"
            S3[S3 for Documents]
            Aurora[Aurora Postgres (Memory)]
            Redis[ElastiCache (Cache)]
            Neo4j[Neo4j AuraDB (Graph)]
        end
    end

    User -- HTTPS --> LB
    LB --> Ingress
    Ingress -- Rate Limit & Auth --> API
    API <--> Aurora
    API <--> Redis
    API --> Ray
    API --> Sandbox
    Ray --> vLLM
    Ray --> Embed
    Ray -- Search --> Qdrant
    Ray -- Search --> Neo4j

    subgraph "Ingestion Pipeline (Async)"
      S3 -- Event Trigger --> RayJob[Ray Ingestion Job]
      RayJob -- Read --> S3
      RayJob -- Embed --> Embed
      RayJob -- Index --> Qdrant
      RayJob -- Extract Graph --> vLLM
      RayJob -- Index Graph --> Neo4j
    end