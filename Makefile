# Makefile

.PHONY: help install dev up down stop init deploy infra build bootstrap init-cloud smoke-test verify destroy test

help:
	@echo "RAG Platform Commands:"
	@echo ""
	@echo "  Local Development:"
	@echo "    make install       - Install Python dependencies"
	@echo "    make up            - Start local DBs (Docker)"
	@echo "    make init          - Initialize local DBs, collections, indexes"
	@echo "    make dev           - Run FastAPI server locally (hot reload)"
	@echo "    make down          - Stop local DBs (Docker only)"
	@echo "    make stop          - Stop everything (API + Docker + stale processes)"
	@echo "    make test          - Run tests"
	@echo ""
	@echo "  AWS Deployment:"
	@echo "    make deploy-aws    - Full deploy: Terraform + Build + Bootstrap (first time)"
	@echo "    make infra         - Apply Terraform only"
	@echo "    make build         - Build & push Docker image to ECR"
	@echo "    make bootstrap     - Bootstrap EKS cluster (K8s resources)"
	@echo "    make init-cloud    - Initialize cloud databases"
	@echo "    make deploy        - Helm upgrade API only (code changes)"
	@echo "    make verify        - Full post-deploy verify (pods + DB init + tests + UI)"
	@echo "    make smoke-test    - Run smoke tests only"
	@echo "    make destroy       - Tear down ALL AWS resources"
	@echo ""
	@echo "  Quick start (local):  make install && make up && make init && make dev"
	@echo "  Quick start (AWS):    make deploy-aws && make verify"

# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

install:
	pip install -r services/api/requirements.txt

up:
	docker compose up -d

down:
	docker compose down

stop:
	./scripts/shutdown.sh

init:
	python3 scripts/init_local.py

dev:
	uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env

test:
	pytest tests/

# ============================================================
# AWS DEPLOYMENT
# ============================================================

# Full deployment (first time): Terraform + Docker + EKS bootstrap
deploy-aws:
	./scripts/deploy_aws.sh

# Terraform only: provision VPC, EKS, Aurora, Redis, S3
infra:
	cd infra/terraform && terraform init -upgrade && terraform apply

# Build Docker image and push to ECR
build:
	./scripts/build_push.sh

# Bootstrap EKS cluster: KubeRay, Qdrant, Neo4j, Ray, Ingress, API
bootstrap:
	./scripts/bootstrap_cluster.sh

# Initialize cloud databases (Qdrant collections, Neo4j indexes)
init-cloud:
	python3 scripts/init_cloud.py

# Helm upgrade API only (for code changes after initial deploy)
deploy:
	@ACCOUNT_ID=$$(aws sts get-caller-identity --query Account --output text); \
	TAG=$$(git rev-parse --short HEAD 2>/dev/null || echo "v0.1.0"); \
	helm upgrade --install api deploy/helm/api \
		--set image.repository="$${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/rag-backend-api" \
		--set image.tag="$${TAG}" \
		--namespace default

# Full post-deploy verification (pods + port-forward + DB init + smoke test + UI)
verify:
	./scripts/post_deploy_verify.sh

# Smoke tests only (requires port-forward already running)
smoke-test:
	./scripts/smoke_test.sh

# Destroy ALL cloud resources (requires confirmation)
destroy:
	./scripts/cleanup.sh
