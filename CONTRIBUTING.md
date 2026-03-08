# Contributing

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Terraform 1.7+
- Helm 3
- `kubectl`
- `pre-commit`

## Local Setup

```bash
make setup          # Install deps, pre-commit hooks, dev tools
make up             # Start local DBs (Postgres, Redis, Neo4j, Qdrant)
make init           # Seed local databases
make dev            # Run API with hot reload on :8000
```

## Development Workflow

We use **trunk-based development**. All changes go through short-lived feature branches merged to `main` via pull request.

### Branch Naming

| Prefix     | Purpose                |
|------------|------------------------|
| `feature/` | New functionality      |
| `fix/`     | Bug fixes              |
| `chore/`   | Tooling, deps, config  |
| `docs/`    | Documentation only     |

### PR Requirements

1. CI passes (lint + tests + Docker build + Terraform validate)
2. At least one code review approval
3. Branch is up to date with `main`

### Commands

```bash
make lint           # Run ruff linter
make format         # Auto-fix lint issues + format
make test           # Run pytest (uses pyproject.toml config)
```

## Environment Promotion

```
feature/* --> PR --> CI passes --> merge to main
                                      |
                          deploy-staging.yml (auto)
                                      |
                          staging verified
                                      |
                          deploy-prod.yml (manual + approval)
```

- **Staging**: auto-deploys on every push to `main`
- **Production**: manual trigger via `workflow_dispatch`, requires environment approval

## Terraform

Per-environment state isolation via `-backend-config`:

```bash
# Staging
terraform init -backend-config="key=staging/terraform.tfstate"
terraform plan -var-file=envs/staging.tfvars

# Production
terraform init -backend-config="key=prod/terraform.tfstate"
terraform plan -var-file=envs/prod.tfvars
```

## Helm Deploys

Values are layered: **base -> cloud -> environment**.

```bash
# Azure staging
helm upgrade --install api deploy/helm/api \
  -f deploy/helm/api/values-azure.yaml \
  -f deploy/helm/api/values-staging.yaml

# Azure production
helm upgrade --install api deploy/helm/api \
  -f deploy/helm/api/values-azure.yaml \
  -f deploy/helm/api/values-prod.yaml
```
