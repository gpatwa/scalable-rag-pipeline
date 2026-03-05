# docs/security.md

# Security Model

- **Authentication:** All API endpoints are protected by JWT validation (`services/api/app/auth/jwt.py`).
- **Network Isolation:** Databases (RDS, Redis, Neo4j) are deployed in private VPC subnets, inaccessible from the public internet.
- **IAM Least Privilege:** Pods are granted specific permissions via IAM Roles for Service Accounts (IRSA). The Ingestion Pod can write to S3, but the API Pod cannot.
- **Code Execution:** Untrusted code from the `Code Interpreter` tool runs in a hardened Docker container (`services/sandbox/`) with no network access and strict CPU/memory limits.