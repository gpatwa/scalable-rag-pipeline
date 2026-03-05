#!/bin/bash
# scripts/cleanup.sh
# Comprehensive teardown of ALL AWS resources to avoid surprise bills.
# Removes K8s resources (in correct order) THEN destroys Terraform infra.
#
# Usage:
#   ./scripts/cleanup.sh           # Full destroy (interactive)
#   ./scripts/cleanup.sh --force   # Skip confirmation (CI/CD)

set -euo pipefail

CLUSTER_NAME="rag-platform-cluster"
REGION="us-east-1"
FORCE=false

[ "${1:-}" = "--force" ] && FORCE=true

echo "=============================================="
echo "  COMPLETE AWS TEARDOWN"
echo "=============================================="
echo ""
echo "  This will PERMANENTLY DESTROY:"
echo "    - EKS cluster and all pods"
echo "    - Aurora PostgreSQL database"
echo "    - ElastiCache Redis"
echo "    - S3 document bucket"
echo "    - All EBS volumes (Qdrant + Neo4j data)"
echo "    - Load Balancers"
echo "    - VPC, NAT Gateway, subnets"
echo "    - ECR container images"
echo ""
echo "  Estimated time: 15-20 minutes"
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
# Phase 1: Delete K8s resources that create AWS resources
# (Must happen BEFORE terraform destroy to avoid orphaned LBs/EBS)
# =============================================================
echo ""
echo "Phase 1: Deleting Kubernetes resources..."
echo "  (This must happen first to release AWS Load Balancers and EBS volumes)"
echo ""

if [ "$KUBECTL_OK" = true ]; then

    # Step 1: Delete Ray Serve services (releases GPU nodes)
    echo "  1/8  Deleting Ray Serve services..."
    kubectl delete rayservice llm-service 2>/dev/null || true
    kubectl delete rayservice embed-service 2>/dev/null || true

    # Step 2: Delete Ray Cluster
    echo "  2/8  Deleting Ray Cluster..."
    kubectl delete raycluster rag-ray-cluster 2>/dev/null || true

    # Step 3: Delete Ingress (releases AWS Load Balancer — this is the critical one!)
    echo "  3/8  Deleting Ingress resources..."
    kubectl delete -f deploy/ingress/nginx.yaml 2>/dev/null || true

    # Step 4: Uninstall Helm releases (order matters: apps first, operators last)
    echo "  4/8  Uninstalling Helm releases..."
    helm uninstall api 2>/dev/null || true
    helm uninstall qdrant 2>/dev/null || true
    helm uninstall neo4j 2>/dev/null || true
    helm uninstall kuberay-operator 2>/dev/null || true
    helm uninstall ingress-nginx -n ingress-nginx 2>/dev/null || true
    helm uninstall external-secrets -n external-secrets 2>/dev/null || true

    # Step 5: Delete Karpenter NodePools (stops provisioning new nodes)
    echo "  5/8  Deleting Karpenter NodePools..."
    kubectl delete -f deploy/karpenter/nodepool.yaml 2>/dev/null || true

    # Step 6: Delete Persistent Volume Claims (orphaned PVCs = orphaned EBS = $$)
    echo "  6/8  Deleting Persistent Volume Claims..."
    kubectl delete pvc --all --namespace default 2>/dev/null || true
    echo "        (PVCs deleted — EBS volumes will be released)"

    # Step 7: Delete remaining resources
    echo "  7/8  Cleaning up remaining resources..."
    kubectl delete -f deploy/ray/ 2>/dev/null || true
    kubectl delete -f deploy/secrets/external-secrets.yaml 2>/dev/null || true
    kubectl delete clustersecretstore aws-secrets-manager 2>/dev/null || true
    kubectl delete namespace external-secrets 2>/dev/null || true
    kubectl delete namespace ingress-nginx 2>/dev/null || true

    # Step 8: Wait for Load Balancers to be fully deregistered
    echo "  8/8  Waiting 60s for AWS Load Balancers to fully release..."
    echo "        (AWS needs time to deregister LBs, otherwise terraform destroy fails)"
    sleep 60

    echo ""
    echo "  Remaining pods (should be system pods only):"
    kubectl get pods --all-namespaces --no-headers 2>/dev/null | while read line; do echo "    $line"; done
    echo ""
else
    echo "  WARNING: kubectl not connected to cluster."
    echo "  K8s resources will be force-destroyed by Terraform."
    echo "  AWS Load Balancers may become orphaned — check AWS console after destroy."
    echo ""
fi

# =============================================================
# Phase 2: Terraform Destroy (removes all AWS infrastructure)
# =============================================================
echo "Phase 2: Terraform Destroy..."
echo "  (VPC, EKS, Aurora, Redis, S3, NAT Gateway, etc.)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/infra/terraform"

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
# Phase 3: Clean up resources NOT managed by Terraform
# =============================================================
echo ""
echo "Phase 3: Cleaning up remaining AWS resources..."

# ECR repository (not managed by Terraform)
echo "  Deleting ECR repository..."
aws ecr delete-repository \
    --repository-name rag-backend-api \
    --region "$REGION" \
    --force 2>/dev/null && echo "    ECR repo deleted" || echo "    ECR repo not found (OK)"

# Check for orphaned EBS volumes
echo ""
echo "  Checking for orphaned EBS volumes..."
ORPHANED_VOLUMES=$(aws ec2 describe-volumes \
    --region "$REGION" \
    --filters "Name=tag:kubernetes.io/cluster/$CLUSTER_NAME,Values=owned" "Name=status,Values=available" \
    --query 'Volumes[].VolumeId' \
    --output text 2>/dev/null || echo "")

if [ -n "$ORPHANED_VOLUMES" ] && [ "$ORPHANED_VOLUMES" != "None" ]; then
    echo "    Found orphaned volumes: $ORPHANED_VOLUMES"
    for vol in $ORPHANED_VOLUMES; do
        aws ec2 delete-volume --volume-id "$vol" --region "$REGION" 2>/dev/null && \
            echo "    Deleted: $vol" || echo "    Failed to delete: $vol"
    done
else
    echo "    No orphaned volumes found"
fi

# Check for orphaned Load Balancers
echo ""
echo "  Checking for orphaned Load Balancers..."
ORPHANED_LBS=$(aws elbv2 describe-load-balancers \
    --region "$REGION" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'k8s') || contains(LoadBalancerName, '$CLUSTER_NAME')].LoadBalancerArn" \
    --output text 2>/dev/null || echo "")

if [ -n "$ORPHANED_LBS" ] && [ "$ORPHANED_LBS" != "None" ]; then
    echo "    WARNING: Found possible orphaned LBs:"
    echo "    $ORPHANED_LBS"
    echo "    Delete manually if these are from this project:"
    echo "    aws elbv2 delete-load-balancer --load-balancer-arn <ARN>"
else
    echo "    No orphaned Load Balancers found"
fi

# Check for orphaned Elastic IPs
echo ""
echo "  Checking for orphaned Elastic IPs..."
ORPHANED_EIPS=$(aws ec2 describe-addresses \
    --region "$REGION" \
    --filters "Name=tag:Project,Values=Enterprise-RAG" \
    --query 'Addresses[?AssociationId==null].AllocationId' \
    --output text 2>/dev/null || echo "")

if [ -n "$ORPHANED_EIPS" ] && [ "$ORPHANED_EIPS" != "None" ]; then
    echo "    Found orphaned EIPs: $ORPHANED_EIPS"
    for eip in $ORPHANED_EIPS; do
        aws ec2 release-address --allocation-id "$eip" --region "$REGION" 2>/dev/null && \
            echo "    Released: $eip" || echo "    Failed to release: $eip"
    done
else
    echo "    No orphaned EIPs found"
fi

# =============================================================
# Summary
# =============================================================
echo ""
echo "=============================================="
echo "  Teardown Complete!"
echo "=============================================="
echo ""
echo "  Resources destroyed:"
echo "    - EKS cluster ($CLUSTER_NAME)"
echo "    - Aurora PostgreSQL"
echo "    - ElastiCache Redis"
echo "    - S3 bucket"
echo "    - VPC + NAT Gateway"
echo "    - ECR images"
echo "    - EBS volumes"
echo ""
echo "  Still exists (manual cleanup if needed):"
echo "    - Terraform state bucket: rag-platform-terraform-state-prod-1"
echo "      (Keep this if you plan to redeploy later)"
echo "    - CloudWatch log groups (minimal cost, auto-expire)"
echo "    - AWS Budget alert (free)"
echo ""
echo "  Verify zero billing:"
echo "    https://console.aws.amazon.com/cost-management/home"
echo "    https://console.aws.amazon.com/ec2/v2/home?region=${REGION}#Volumes"
echo "    https://console.aws.amazon.com/ec2/v2/home?region=${REGION}#LoadBalancers"
echo ""
echo "  To redeploy later: make deploy-aws"
echo ""
