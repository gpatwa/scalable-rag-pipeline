#!/bin/bash
# scripts/bootstrap_cluster.sh
# Bootstraps the EKS cluster with all required K8s resources.
# Run this AFTER terraform apply has provisioned the infrastructure.

set -euo pipefail

CLUSTER_NAME="rag-platform-cluster"
REGION="us-east-1"

echo "========================================"
echo "  EKS Cluster Bootstrap"
echo "========================================"

# -----------------------------------------------------------
# 1. Configure kubectl
# -----------------------------------------------------------
echo ""
echo "Step 1: Updating kubeconfig..."
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"
kubectl cluster-info

# -----------------------------------------------------------
# 2. Install NVIDIA Device Plugin (required for GPU nodes)
# -----------------------------------------------------------
echo ""
echo "Step 2: Installing NVIDIA device plugin..."
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.3/nvidia-device-plugin.yml 2>/dev/null || \
    echo "  NVIDIA plugin already installed or namespace issue (non-fatal)"

# -----------------------------------------------------------
# 3. Apply Karpenter NodePools
# -----------------------------------------------------------
echo ""
echo "Step 3: Applying Karpenter NodePools..."
kubectl apply -f deploy/karpenter/nodepool.yaml
echo "  NodePools: general (SPOT) + gpu (SPOT, scale-to-zero)"

# -----------------------------------------------------------
# 4. Install ExternalSecrets Operator
# -----------------------------------------------------------
echo ""
echo "Step 4: Installing External Secrets Operator..."
helm repo add external-secrets https://charts.external-secrets.io 2>/dev/null || true
helm repo update
helm upgrade --install external-secrets external-secrets/external-secrets \
    --namespace external-secrets \
    --create-namespace \
    --wait

# Create ClusterSecretStore for AWS Secrets Manager
kubectl apply -f - <<'EOF'
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
EOF

# Apply ExternalSecret to pull app secrets
kubectl apply -f deploy/secrets/external-secrets.yaml
echo "  Secrets will sync from AWS Secrets Manager"

# -----------------------------------------------------------
# 5. Install KubeRay Operator
# -----------------------------------------------------------
echo ""
echo "Step 5: Installing KubeRay Operator..."
helm repo add kuberay https://ray-project.github.io/kuberay-helm/ 2>/dev/null || true
helm repo update
helm upgrade --install kuberay-operator kuberay/kuberay-operator \
    --version 1.0.0 \
    --wait

# -----------------------------------------------------------
# 6. Deploy Qdrant (Vector Database)
# -----------------------------------------------------------
echo ""
echo "Step 6: Deploying Qdrant..."
helm repo add qdrant https://qdrant.to/helm 2>/dev/null || true
helm repo update
helm upgrade --install qdrant qdrant/qdrant \
    --namespace default \
    --values deploy/helm/qdrant/values.yaml \
    --wait --timeout 120s

# -----------------------------------------------------------
# 7. Deploy Neo4j (Graph Database)
# -----------------------------------------------------------
echo ""
echo "Step 7: Deploying Neo4j..."
helm repo add neo4j https://helm.neo4j.com/neo4j 2>/dev/null || true
helm repo update
helm upgrade --install neo4j neo4j/neo4j \
    --namespace default \
    --values deploy/helm/neo4j/values.yaml \
    --set neo4j.password="$(kubectl get secret app-env-secret -o jsonpath='{.data.NEO4J_PASSWORD}' 2>/dev/null | base64 -d 2>/dev/null || echo 'password')" \
    --wait --timeout 180s

# -----------------------------------------------------------
# 8. Deploy Ray Cluster
# -----------------------------------------------------------
echo ""
echo "Step 8: Deploying Ray Cluster (head node + worker config)..."
kubectl apply -f deploy/ray/ray-cluster.yaml

echo "  Waiting 30s for Ray head to initialize..."
sleep 30

# -----------------------------------------------------------
# 9. Deploy Ray Serve (LLM + Embeddings)
# -----------------------------------------------------------
echo ""
echo "Step 9: Deploying Ray Serve AI engines..."
echo "  These will trigger Karpenter to provision GPU SPOT nodes on demand."
kubectl apply -f deploy/ray/ray-serve-llm.yaml
kubectl apply -f deploy/ray/ray-serve-embed.yaml

# -----------------------------------------------------------
# 10. Deploy NGINX Ingress
# -----------------------------------------------------------
echo ""
echo "Step 10: Deploying NGINX Ingress..."
# Install NGINX Ingress Controller if not present
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.service.type=LoadBalancer \
    --set controller.tolerations[0].key=CriticalAddonsOnly \
    --set controller.tolerations[0].operator=Exists \
    --set controller.tolerations[0].effect=NoSchedule \
    --wait --timeout 120s || echo "  Ingress controller install (may already exist)"

# Apply ingress routing rules
kubectl apply -f deploy/ingress/nginx.yaml

# -----------------------------------------------------------
# 11. Deploy Backend API
# -----------------------------------------------------------
echo ""
echo "Step 11: Deploying Backend API..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "v0.1.0")

helm upgrade --install api deploy/helm/api \
    --set image.repository="${ECR_URI}/rag-backend-api" \
    --set image.tag="${TAG}" \
    --wait --timeout 120s

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
echo ""
echo "========================================"
echo "  Cluster Bootstrap Complete!"
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
