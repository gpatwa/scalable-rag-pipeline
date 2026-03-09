# Security Model

## Monolith Mode

- **Authentication:** All API endpoints are protected by JWT validation (`services/api/app/auth/jwt.py`).
- **Network Isolation:** Databases (RDS, Redis, Neo4j) are deployed in private VPC subnets, inaccessible from the public internet.
- **IAM Least Privilege:** Pods are granted specific permissions via IAM Roles for Service Accounts (IRSA). The Ingestion Pod can write to S3, but the API Pod cannot.
- **Code Execution:** Untrusted code from the `Code Interpreter` tool runs in a hardened Docker container (`services/sandbox/`) with no network access and strict CPU/memory limits.

---

## Split-Plane Security Model

The control plane / data plane architecture introduces additional security boundaries and authentication mechanisms.

### Authentication Layers

| Boundary | Mechanism | Implementation |
|----------|-----------|----------------|
| **User -> Control Plane** | JWT (HS256 local / RS256 JWKS) | Standard bearer token in `Authorization` header |
| **Control Plane -> Data Plane** | API key (`X-DataPlane-Key`) | Shared secret set during data plane registration |
| **Data Plane -> Control Plane** | Internal API key (`X-Internal-Key`) | Shared secret for registration, heartbeat, usage reporting |
| **User identity forwarding** | HTTP headers | `X-User-Id` + `X-User-Role` forwarded by control plane proxy |

### Mutual TLS (mTLS)

For production deployments, the control plane supports mTLS for secure communication with data planes:

| Config | Env Var | Purpose |
|--------|---------|---------|
| CA certificate | `DATA_PLANE_MTLS_CA_PATH` | Certificate Authority for verifying data plane certificates |
| Client certificate | `DATA_PLANE_MTLS_CERT_PATH` | Control plane's client certificate presented to data planes |
| Client private key | `DATA_PLANE_MTLS_KEY_PATH` | Control plane's private key for TLS handshake |

When all three mTLS env vars are set, the control plane creates an `httpx.AsyncClient` with a TLS client certificate for every request to data planes. This ensures:

1. The control plane can verify the data plane's identity (server certificate validation)
2. The data plane can verify the control plane's identity (client certificate validation)
3. All traffic is encrypted in transit (TLS 1.2+)

### Data Plane API Key Authentication

Each data plane is configured with a unique API key (`DATA_PLANE_API_KEY`). The control plane includes this key in every proxied request via the `X-DataPlane-Key` header. The data plane validates:

1. The header is present (unless in dev mode with no key configured)
2. The key matches the configured value exactly
3. Invalid/missing keys return `401 Unauthorized`

### Control Plane Internal API Key

The control plane exposes internal routes (`/admin/data-planes/register`, `/admin/data-planes/heartbeat`, `/internal/usage/report`) protected by a separate internal API key (`INTERNAL_API_KEY`). Data planes include this key in registration and heartbeat requests via the `X-Internal-Key` header.

### User Context Forwarding

When the control plane proxies a request to a data plane, it forwards the authenticated user's identity via HTTP headers:

```
Original request (user -> control plane):
    Authorization: Bearer <JWT with tenant_id=acme, user_id=alice, role=admin>

Proxied request (control plane -> data plane):
    X-DataPlane-Key: dp-key-abc123
    X-User-Id: alice
    X-User-Role: admin
```

The data plane trusts these headers because it has validated the `X-DataPlane-Key`. The data plane never validates JWTs directly -- JWT validation is the control plane's responsibility.

### Per-Tenant Rate Limiting

The control plane enforces per-tenant rate limits using a sliding window counter:

- **Default:** 60 requests per minute (configurable via `RATE_LIMIT_DEFAULT_RPM`)
- **Per-tenant override:** Stored in tenant config (e.g., enterprise tenants get higher limits)
- **Unlimited:** Set rate limit to 0 to disable limiting for a tenant
- **Response:** `429 Too Many Requests` with `Retry-After` header

### Threat Model (Split-Plane Specific)

| Threat | Mitigation |
|--------|------------|
| Compromised data plane | Limited blast radius (one customer only); control plane can decommission via registry |
| Stolen API key | Rotate via control plane admin API; each data plane has a unique key |
| Man-in-the-middle (CP <-> DP) | mTLS ensures encrypted + authenticated channel |
| Spoofed user identity | Only the control plane sets `X-User-Id`/`X-User-Role`; data plane trusts only requests with valid API key |
| Denial of service | Per-tenant rate limiting at control plane prevents abuse before requests reach data plane |
| Stale/unhealthy data plane | Health monitor marks unresponsive data planes as unhealthy; excluded from routing |
