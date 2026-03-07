#!/bin/bash
# scripts/cleanup_azure.sh
# Comprehensive teardown of ALL Azure resources to avoid surprise bills.
# Azure equivalent of scripts/cleanup.sh (AWS).
#
# Usage:
#   ./scripts/cleanup_azure.sh           # Full destroy (interactive)
#   ./scripts/cleanup_azure.sh --force   # Skip confirmation (CI/CD)

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-rag-platform-aks}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rag-platform-rg}"
FORCE=false

[ "${1:-}" = "--force" ] && FORCE=true

echo "=============================================="
echo "  COMPLETE AZURE TEARDOWN"
echo "=============================================="
echo ""
echo "  This will PERMANENTLY DESTROY:"
echo "    - AKS cluster and all pods"
echo "    - Azure PostgreSQL Flexible Server"
echo "    - Azure Cache for Redis"
echo "    - Azure Storage Account (documents)"
echo "    - Azure Container Registry (images)"
echo "    - VNet, subnets, NSGs"
echo "    - Managed Identities"
echo ""
echo "  Estimated time: 10-15 minutes"
echo ""

if [ "$FORCE" = false ]; then
    read -p "Type 'DESTROY' to confirm: " confirm
    if [ "$confirm" != "DESTROY" ]; then
        echo "Aborted."
        exit 1
    fi
fi

# Track if kubectl is connected
KUBECTL_OK=false
if kubectl cluster-info &>/dev/null 2>&1; then
    KUBECTL_OK=true
fi

# =============================================================
# Phase 1: Delete K8s resources (releases Azure Load Balancers)
# =============================================================
echo ""
echo "Phase 1: Deleting Kubernetes resources..."

if [ "$KUBECTL_OK" = true ]; then
    # Uninstall Helm releases
    echo "  Uninstalling Helm releases..."
    helm uninstall api 2>/dev/null || true
    helm uninstall qdrant 2>/dev/null || true
    helm uninstall neo4j 2>/dev/null || true
    helm uninstall kuberay-operator 2>/dev/null || true
    helm uninstall ingress-nginx -n ingress-nginx 2>/dev/null || true

    # Delete PVCs
    echo "  Deleting Persistent Volume Claims..."
    kubectl delete pvc --all --namespace default 2>/dev/null || true

    # Delete namespaces
    kubectl delete namespace ingress-nginx 2>/dev/null || true

    # Wait for Load Balancers to release
    echo "  Waiting 30s for Azure Load Balancers to release..."
    sleep 30
else
    echo "  WARNING: kubectl not connected. K8s resources will be force-destroyed by Terraform."
fi

# =============================================================
# Phase 2: Terraform Destroy
# =============================================================
echo ""
echo "Phase 2: Terraform Destroy..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/infra/terraform/azure"

if [ -f terraform.tfstate ] || [ -d .terraform ]; then
    terraform init -upgrade 2>/dev/null || true
    terraform destroy -auto-approve
else
    echo "  No Terraform state found locally. Trying remote state..."
    terraform init -upgrade 2>/dev/null || true
    terraform destroy -auto-approve 2>/dev/null || echo "  Terraform destroy failed (state may not exist)"
fi

cd "$PROJECT_DIR"

# =============================================================
# Phase 3: Clean up any remaining resources
# =============================================================
echo ""
echo "Phase 3: Checking for orphaned resources..."

# Check if the resource group still exists
if az group show --name "$RESOURCE_GROUP" &>/dev/null 2>&1; then
    echo "  WARNING: Resource group '$RESOURCE_GROUP' still exists."
    echo "  To force delete: az group delete --name $RESOURCE_GROUP --yes --no-wait"
else
    echo "  Resource group deleted successfully."
fi

# =============================================================
# Summary
# =============================================================
echo ""
echo "=============================================="
echo "  Azure Teardown Complete!"
echo "=============================================="
echo ""
echo "  Resources destroyed:"
echo "    - AKS cluster ($CLUSTER_NAME)"
echo "    - PostgreSQL Flexible Server"
echo "    - Azure Cache for Redis"
echo "    - Storage Account"
echo "    - Container Registry"
echo "    - VNet + NSGs"
echo ""
echo "  Still exists (manual cleanup if needed):"
echo "    - Terraform state storage account: ragterraformstate"
echo "      (Keep this if you plan to redeploy later)"
echo "    - Azure Monitor logs (minimal cost, auto-expire)"
echo ""
echo "  Verify zero billing:"
echo "    https://portal.azure.com/#view/Microsoft_Azure_CostManagement"
echo ""
echo "  To redeploy later: ./scripts/deploy_azure.sh"
echo ""
