# docs/cost_model.md

# Cost Model (Estimates)

- **Variable Costs (Primary Drivers):**
    - **GPU Instances (EKS):** `g5.xlarge` Spot instances for inference. Cost is directly proportional to user traffic.
    - **LLM API Calls:** If using external models (GPT-4 for judging), this is a major cost factor.
- **Fixed Costs (Baseline):**
    - EKS Control Plane
    - Aurora DB (Serverless v2 scales to a minimum)
    - NAT Gateway
- **Cost Optimization Strategies:**
    - **Spot Instances:** Karpenter is configured to prefer Spot instances (~70% savings).
    - **Semantic Caching:** Reduces GPU inference costs by serving repeat queries from Redis.
    - **Scale-to-Zero:** Ray Serve and Karpenter can scale GPU nodes down to 0 during off-peak hours.