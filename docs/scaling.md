# System Scaling Strategy

## Monolith Mode

- **Node Scaling (Hardware):** `Karpenter` is responsible for adding/removing EC2 instances. The `provisioner-cpu.yaml` and `provisioner-gpu.yaml` files define rules for which instance types to launch (e.g., `g5.xlarge` for GPU tasks). It is demand-driven and can scale from 0 nodes to 100s in minutes.
- **Application Scaling (Software):** `Ray Autoscaler` and `Ray Serve` manage the number of replicas (pods) running on the nodes. This is configured in `deploy/ray/ray-serve-llm.yaml` based on `target_num_ongoing_requests_per_replica`.
- **Database Scaling:** AWS Aurora Serverless v2 automatically scales its compute capacity (ACUs) based on query load.

---

## Split-Plane Mode (Control Plane / Data Plane)

In split-plane deployments, the control plane and data planes scale independently with different strategies.

### Control Plane Scaling

The control plane is a lightweight stateless service (no AI workloads). It scales horizontally with standard pod autoscaling.

| Resource | Strategy | Notes |
|----------|----------|-------|
| **Compute** | HPA (CPU/memory) or Karpenter | Lightweight -- 1-2 pods handle 1000s of concurrent connections |
| **Database** | SQLite (dev) / Aurora Serverless (prod) | Stores tenants, data plane registry, usage events |
| **Rate limiting** | In-memory (single instance) or Redis (multi-instance) | Sliding window counter per tenant |
| **Routing cache** | In-memory with TTL | Tenant -> data plane resolution cached for fast lookups |

**Bottleneck:** The control plane is a streaming proxy. Each active chat session holds an open httpx connection. Size pods for concurrent connection count, not CPU.

### Data Plane Scaling

Each data plane is a dedicated instance serving one customer (tenant). Data planes scale vertically and horizontally based on the customer's workload.

| Resource | Strategy | Notes |
|----------|----------|-------|
| **GPU compute** | Karpenter + Ray Autoscaler | GPU nodes scale to zero when idle; Ray Serve scales replicas per model |
| **Vector DB** | Qdrant replicas per data plane | Each customer gets their own Qdrant collection (no cross-tenant data) |
| **Graph DB** | Neo4j per data plane | Dedicated graph instance -- no shared tenancy |
| **Database** | Postgres per data plane | Chat history and session state isolated to customer region |

### Per-Tenant Data Plane Isolation

```
Control Plane (single instance, your cloud)
    |
    |--- Tenant "acme-corp"  --> Data Plane A (eu-west-1, 2 GPU nodes)
    |--- Tenant "globex"     --> Data Plane B (us-east-1, 1 GPU node)
    |--- Tenant "initech"    --> Data Plane C (ap-southeast-1, 1 GPU node)
```

**Key benefits:**
- **Data residency:** Each data plane runs in the customer's required cloud region
- **Blast radius:** A data plane failure affects only one customer
- **Right-sizing:** Each data plane is sized for the customer's actual workload (not over-provisioned for the largest tenant)
- **Independent upgrades:** Data planes can be upgraded/rolled back independently

### Capacity Planning

| Deployment | Control Plane | Data Plane (per customer) |
|------------|---------------|---------------------------|
| **Small** (< 100 users) | 1 pod, SQLite, in-memory rate limiting | 1 CPU pod, 1 GPU node, single-replica Qdrant |
| **Medium** (100-1000 users) | 2 pods, Aurora Serverless, Redis rate limiting | 2 CPU pods, 2 GPU nodes, 3-replica Qdrant |
| **Large** (1000+ users) | 3+ pods, Aurora multi-AZ, Redis cluster | HPA on CPU pods, Karpenter GPU autoscaling, Qdrant sharding |
