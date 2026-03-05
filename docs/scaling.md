# docs/scaling.md

# System Scaling Strategy

- **Node Scaling (Hardware):** `Karpenter` is responsible for adding/removing EC2 instances. The `provisioner-cpu.yaml` and `provisioner-gpu.yaml` files define rules for which instance types to launch (e.g., `g5.xlarge` for GPU tasks). It is demand-driven and can scale from 0 nodes to 100s in minutes.
- **Application Scaling (Software):** `Ray Autoscaler` and `Ray Serve` manage the number of replicas (pods) running on the nodes. This is configured in `deploy/ray/ray-serve-llm.yaml` based on `target_num_ongoing_requests_per_replica`.
- **Database Scaling:** AWS Aurora Serverless v2 automatically scales its compute capacity (ACUs) based on query load.