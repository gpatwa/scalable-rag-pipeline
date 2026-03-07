#!/bin/bash
# scripts/deploy_azure.sh
# Full Azure deployment orchestrator: Terraform -> ACR -> AKS -> Verify
# Usage: ./scripts/deploy_azure.sh [--skip-infra] [--skip-build] [--skip-bootstrap]
#
# Azure equivalent of scripts/deploy_aws.sh.
# For first-time deploy, run without flags.
# For subsequent deploys (code changes only): ./scripts/deploy_azure.sh --skip-infra

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-rag-platform-aks}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rag-platform-rg}"
ACR_NAME="${ACR_NAME:-ragplatformacr}"
REPO_NAME="rag-backend-api"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Parse flags
SKIP_INFRA=false
SKIP_BUILD=false
SKIP_BOOTSTRAP=false

for arg in "$@"; do
    case $arg in
        --skip-infra) SKIP_INFRA=true ;;
        --skip-build) SKIP_BUILD=true ;;
        --skip-bootstrap) SKIP_BOOTSTRAP=true ;;
    esac
done

echo "========================================"
echo "  RAG Pipeline — Azure Deployment"
echo "========================================"
echo "  Cluster:  $CLUSTER_NAME"
echo "  RG:       $RESOURCE_GROUP"
echo "  ACR:      $ACR_NAME"
echo "  Flags:    infra=$([ "$SKIP_INFRA" = true ] && echo 'skip' || echo 'apply')" \
     "build=$([ "$SKIP_BUILD" = true ] && echo 'skip' || echo 'run')" \
     "bootstrap=$([ "$SKIP_BOOTSTRAP" = true ] && echo 'skip' || echo 'run')"
echo "========================================"
echo ""

# -----------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------
echo "Pre-flight checks..."

# Azure CLI
if ! az account show &>/dev/null; then
    echo "ERROR: Azure CLI not logged in. Run: az login"
    exit 1
fi
SUBSCRIPTION=$(az account show --query name -o tsv)
echo "  Azure Subscription: $SUBSCRIPTION"

# Terraform
if ! command -v terraform &>/dev/null; then
    echo "ERROR: terraform not found. Install: https://developer.hashicorp.com/terraform/install"
    exit 1
fi
echo "  Terraform: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"

# kubectl
if ! command -v kubectl &>/dev/null; then
    echo "ERROR: kubectl not found. Install: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi
echo "  kubectl: installed"

# Helm
if ! command -v helm &>/dev/null; then
    echo "ERROR: helm not found. Install: https://helm.sh/docs/intro/install/"
    exit 1
fi
echo "  Helm: $(helm version --short 2>/dev/null)"

# Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: docker not found. Install Docker Desktop."
    exit 1
fi
echo "  Docker: $(docker version --format '{{.Client.Version}}' 2>/dev/null || echo 'installed')"

echo "  Pre-flight: OK"
echo ""

# -----------------------------------------------------------
# Step 1: Terraform — Provision Azure Infrastructure
# -----------------------------------------------------------
if [ "$SKIP_INFRA" = false ]; then
    echo "========================================"
    echo "  Step 1: Terraform Apply (Azure)"
    echo "========================================"

    cd "$PROJECT_DIR/infra/terraform/azure"

    # Check that terraform.tfvars exists
    if [ ! -f terraform.tfvars ]; then
        echo "ERROR: infra/terraform/azure/terraform.tfvars not found."
        echo "  Copy terraform.tfvars.example to terraform.tfvars and set your db_password."
        exit 1
    fi

    terraform init -upgrade
    terraform plan -out=tfplan
    echo ""
    read -p "Apply this plan? (yes/no): " apply_confirm
    if [ "$apply_confirm" != "yes" ]; then
        echo "Terraform apply cancelled."
        exit 1
    fi
    terraform apply tfplan
    rm -f tfplan

    echo ""
    echo "Terraform outputs:"
    terraform output
    cd "$PROJECT_DIR"
    echo ""
else
    echo "Step 1: Terraform — SKIPPED (--skip-infra)"
    echo ""
fi

# -----------------------------------------------------------
# Step 2: Build & Push Docker Image to ACR
# -----------------------------------------------------------
if [ "$SKIP_BUILD" = false ]; then
    echo "========================================"
    echo "  Step 2: Build & Push Docker Image (ACR)"
    echo "========================================"
    TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "v0.1.0")
    CLOUD_PROVIDER=azure ACR_NAME="$ACR_NAME" bash "$SCRIPT_DIR/build_push.sh" "$TAG"
    echo ""
else
    echo "Step 2: Docker Build — SKIPPED (--skip-build)"
    echo ""
fi

# -----------------------------------------------------------
# Step 3: Bootstrap AKS Cluster
# -----------------------------------------------------------
if [ "$SKIP_BOOTSTRAP" = false ]; then
    echo "========================================"
    echo "  Step 3: Bootstrap AKS Cluster"
    echo "========================================"
    CLUSTER_NAME="$CLUSTER_NAME" \
    RESOURCE_GROUP="$RESOURCE_GROUP" \
    ACR_NAME="$ACR_NAME" \
    bash "$SCRIPT_DIR/bootstrap_cluster_azure.sh"
    echo ""
else
    echo "Step 3: Cluster Bootstrap — SKIPPED (--skip-bootstrap)"
    echo ""
fi

# -----------------------------------------------------------
# Step 4: Verify Deployment
# -----------------------------------------------------------
echo "========================================"
echo "  Step 4: Verify Deployment"
echo "========================================"

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=api --timeout=120s 2>/dev/null || \
    echo "  API pods not ready yet (may still be starting)"

echo ""
echo "Pod status:"
kubectl get pods -o wide 2>/dev/null || echo "  (kubectl not connected to cluster)"

echo ""
echo "Services:"
kubectl get svc 2>/dev/null || echo "  (kubectl not connected to cluster)"

echo ""
echo "========================================"
echo "  Azure Deployment Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Port-forward to test locally:"
echo "     kubectl port-forward svc/api-service 8000:80"
echo "     curl http://localhost:8000/health/readiness"
echo ""
echo "  2. Initialize cloud databases:"
echo "     python3 scripts/init_cloud.py"
echo ""
echo "  3. Get Ingress URL:"
echo "     kubectl get ingress"
echo ""
echo "  4. Run smoke test:"
echo "     bash scripts/smoke_test.sh"
echo ""
echo "  5. Monitor costs:"
echo "     https://portal.azure.com/#view/Microsoft_Azure_CostManagement"
echo ""
