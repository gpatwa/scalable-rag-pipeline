#!/bin/bash
# scripts/bootstrap_cluster_azure.sh
# Bootstraps the AKS cluster with all required K8s resources.
# Run this AFTER terraform apply has provisioned the Azure infrastructure.
#
# Azure equivalent of scripts/bootstrap_cluster.sh (AWS EKS).
# Key differences: no Karpenter (AKS has built-in autoscaler), Workload Identity
# (not IRSA), ACR pull is handled via Terraform role assignment.

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-rag-platform-aks}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rag-platform-rg}"
ACR_NAME="${ACR_NAME:-ragplatformacr}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  AKS Cluster Bootstrap"
echo "========================================"
echo "  Cluster:  $CLUSTER_NAME"
echo "  RG:       $RESOURCE_GROUP"
echo "  ACR:      $ACR_NAME"
echo "========================================"

# -----------------------------------------------------------
# 1. Configure kubectl
# -----------------------------------------------------------
echo ""
echo "Step 1: Getting AKS credentials..."
az aks get-credentials --resource-group "$RESOURCE_GROUP" --name "$CLUSTER_NAME" --overwrite-existing
kubectl cluster-info

# -----------------------------------------------------------
# 2. Create Kubernetes Secrets
# -----------------------------------------------------------
echo ""
echo "Step 2: Creating app-env-secret..."

# Get Terraform outputs
cd "$PROJECT_DIR/infra/terraform/azure"
POSTGRES_FQDN=$(terraform output -raw postgres_fqdn 2>/dev/null || echo "")
REDIS_HOST=$(terraform output -raw redis_hostname 2>/dev/null || echo "")
REDIS_PORT=$(terraform output -raw redis_ssl_port 2>/dev/null || echo "6380")
REDIS_KEY=$(terraform output -raw redis_primary_key 2>/dev/null || echo "")
STORAGE_ACCOUNT=$(terraform output -raw storage_account_name 2>/dev/null || echo "")
API_IDENTITY_CLIENT_ID=$(terraform output -raw api_identity_client_id 2>/dev/null || echo "")
cd "$PROJECT_DIR"

# Read DB password from tfvars (or prompt)
DB_PASSWORD="${DB_PASSWORD:-}"
if [ -z "$DB_PASSWORD" ]; then
    read -sp "Enter PostgreSQL password: " DB_PASSWORD
    echo ""
fi

DATABASE_URL="postgresql+asyncpg://ragadmin:${DB_PASSWORD}@${POSTGRES_FQDN}:5432/ragdb"
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:${REDIS_PORT}/0"

kubectl create secret generic app-env-secret \
    --from-literal=DATABASE_URL="$DATABASE_URL" \
    --from-literal=REDIS_URL="$REDIS_URL" \
    --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
    --from-literal=NEO4J_PASSWORD="password" \
    --from-literal=AZURE_STORAGE_ACCOUNT_NAME="$STORAGE_ACCOUNT" \
    --from-literal=CLOUD_PROVIDER="azure" \
    --from-literal=STORAGE_PROVIDER="azure_blob" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "  Secret app-env-secret created/updated"

# -----------------------------------------------------------
# 3. Install KubeRay Operator
# -----------------------------------------------------------
echo ""
echo "Step 3: Installing KubeRay Operator..."
helm repo add kuberay https://ray-project.github.io/kuberay-helm/ 2>/dev/null || true
helm repo update
helm upgrade --install kuberay-operator kuberay/kuberay-operator \
    --version 1.0.0 \
    --wait

# -----------------------------------------------------------
# 4. Deploy Qdrant (Vector Database)
# -----------------------------------------------------------
echo ""
echo "Step 4: Deploying Qdrant..."
helm repo add qdrant https://qdrant.to/helm 2>/dev/null || true
helm repo update
helm upgrade --install qdrant qdrant/qdrant \
    --namespace default \
    --values deploy/helm/qdrant/values.yaml \
    --wait --timeout 120s

# -----------------------------------------------------------
# 5. Deploy Neo4j (Graph Database)
# -----------------------------------------------------------
echo ""
echo "Step 5: Deploying Neo4j..."
helm repo add neo4j https://helm.neo4j.com/neo4j 2>/dev/null || true
helm repo update
helm upgrade --install neo4j neo4j/neo4j \
    --namespace default \
    --values deploy/helm/neo4j/values.yaml \
    --set neo4j.password="$(kubectl get secret app-env-secret -o jsonpath='{.data.NEO4J_PASSWORD}' 2>/dev/null | base64 -d 2>/dev/null || echo 'password')" \
    --wait --timeout 180s

# -----------------------------------------------------------
# 6. Deploy NGINX Ingress Controller
# -----------------------------------------------------------
echo ""
echo "Step 6: Deploying NGINX Ingress..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.service.type=LoadBalancer \
    --set controller.service.annotations."service\.beta\.kubernetes\.io/azure-load-balancer-health-probe-request-path"=/healthz \
    --wait --timeout 120s || echo "  Ingress controller install (may already exist)"

# Apply ingress routing rules
kubectl apply -f deploy/ingress/nginx.yaml

# -----------------------------------------------------------
# 7. Deploy Backend API
# -----------------------------------------------------------
echo ""
echo "Step 7: Deploying Backend API..."
ACR_URI="${ACR_NAME}.azurecr.io"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "v0.1.0")

helm upgrade --install api deploy/helm/api \
    -f deploy/helm/api/values-azure.yaml \
    --set image.repository="${ACR_URI}/rag-backend-api" \
    --set image.tag="${TAG}" \
    --set serviceAccount.annotations."azure\.workload\.identity/client-id"="${API_IDENTITY_CLIENT_ID}" \
    --wait --timeout 120s

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
echo ""
echo "========================================"
echo "  AKS Cluster Bootstrap Complete!"
echo "========================================"
echo ""
echo "  Pods:"
kubectl get pods --no-headers 2>/dev/null | while read line; do echo "    $line"; done
echo ""
echo "  Services:"
kubectl get svc --no-headers 2>/dev/null | while read line; do echo "    $line"; done
echo ""
echo "  Ingress:"
kubectl get ingress --no-headers 2>/dev/null | while read line; do echo "    $line"; done
echo ""
echo "  Next: Run 'python3 scripts/init_cloud.py' to initialize databases."
echo "  Monitor: kubectl get pods -w"
echo ""
