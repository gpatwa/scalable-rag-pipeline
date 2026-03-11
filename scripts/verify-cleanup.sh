#!/bin/bash
# scripts/verify-cleanup.sh
# Run AFTER terraform destroy to catch orphaned resources still billing you.
# This is the safety net that prevents surprise AWS bills.
#
# Usage:
#   ./scripts/verify-cleanup.sh              # Check only (default)
#   ./scripts/verify-cleanup.sh --delete     # Check + delete orphans

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="rag-platform-cluster"
PROJECT_TAG="Enterprise-RAG"
DELETE=false
FOUND_RESOURCES=false

[ "${1:-}" = "--delete" ] && DELETE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "  POST-DESTROY VERIFICATION"
echo "  Region: $REGION"
echo "  Mode: $([ "$DELETE" = true ] && echo 'CHECK + DELETE' || echo 'CHECK ONLY')"
echo "=============================================="
echo ""

# ── 1. EKS Cluster ──────────────────────────────
echo "1/10  Checking EKS clusters..."
EKS_CLUSTERS=$(aws eks list-clusters --region "$REGION" \
    --query "clusters[?contains(@, 'rag')]" --output text 2>/dev/null || echo "")
if [ -n "$EKS_CLUSTERS" ] && [ "$EKS_CLUSTERS" != "None" ]; then
    echo -e "  ${RED}FOUND: $EKS_CLUSTERS${NC}"
    echo "  !! EKS clusters cost ~\$0.10/hr + EC2 node costs"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for cluster in $EKS_CLUSTERS; do
            echo "  Deleting nodegroups for $cluster..."
            for ng in $(aws eks list-nodegroups --cluster-name "$cluster" --region "$REGION" \
                --query "nodegroups[]" --output text 2>/dev/null); do
                aws eks delete-nodegroup --cluster-name "$cluster" --nodegroup-name "$ng" --region "$REGION" 2>/dev/null
                echo "    Nodegroup $ng: deletion initiated"
            done
            echo "  Waiting for nodegroups..."
            aws eks wait nodegroup-deleted --cluster-name "$cluster" --region "$REGION" 2>/dev/null || sleep 60
            echo "  Deleting cluster $cluster..."
            aws eks delete-cluster --name "$cluster" --region "$REGION" 2>/dev/null
            echo "    Cluster deletion initiated (takes ~10 min)"
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 2. RDS Clusters ─────────────────────────────
echo "2/10  Checking RDS clusters..."
RDS_CLUSTERS=$(aws rds describe-db-clusters --region "$REGION" \
    --query "DBClusters[?contains(DBClusterIdentifier, 'rag')].{Id:DBClusterIdentifier,Status:Status}" \
    --output text 2>/dev/null || echo "")
if [ -n "$RDS_CLUSTERS" ] && [ "$RDS_CLUSTERS" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $RDS_CLUSTERS"
    echo "  !! Aurora Serverless costs even when stopped (storage charges)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for cluster_id in $(aws rds describe-db-clusters --region "$REGION" \
            --query "DBClusters[?contains(DBClusterIdentifier, 'rag')].DBClusterIdentifier" \
            --output text 2>/dev/null); do
            cluster_status=$(aws rds describe-db-clusters --region "$REGION" \
                --db-cluster-identifier "$cluster_id" \
                --query "DBClusters[0].Status" --output text)
            if [ "$cluster_status" = "stopped" ]; then
                echo "  Starting stopped cluster $cluster_id first..."
                aws rds start-db-cluster --db-cluster-identifier "$cluster_id" --region "$REGION"
                echo "  Waiting for cluster to become available..."
                aws rds wait db-cluster-available --db-cluster-identifier "$cluster_id" --region "$REGION" 2>/dev/null || sleep 300
            fi
            for instance_id in $(aws rds describe-db-clusters --region "$REGION" \
                --db-cluster-identifier "$cluster_id" \
                --query "DBClusters[0].DBClusterMembers[].DBInstanceIdentifier" --output text 2>/dev/null); do
                echo "  Deleting instance $instance_id..."
                aws rds delete-db-instance --db-instance-identifier "$instance_id" --skip-final-snapshot --region "$REGION" 2>/dev/null
            done
            echo "  Waiting for instances to delete..."
            sleep 120
            echo "  Deleting cluster $cluster_id..."
            aws rds delete-db-cluster --db-cluster-identifier "$cluster_id" --skip-final-snapshot --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 3. EC2 Instances (EKS nodes) ────────────────
echo "3/10  Checking EC2 instances..."
EC2_INSTANCES=$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" "Name=instance-state-name,Values=running,stopped" \
    --query "Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,State:State.Name}" \
    --output text 2>/dev/null || echo "")
if [ -n "$EC2_INSTANCES" ] && [ "$EC2_INSTANCES" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $EC2_INSTANCES"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 4. NAT Gateways ─────────────────────────────
echo "4/10  Checking NAT Gateways..."
NAT_GWS=$(aws ec2 describe-nat-gateways --region "$REGION" \
    --filter "Name=state,Values=available,pending" \
    --query "NatGateways[?Tags[?Key=='Project' && Value=='$PROJECT_TAG']].{Id:NatGatewayId,State:State}" \
    --output text 2>/dev/null || echo "")
if [ -n "$NAT_GWS" ] && [ "$NAT_GWS" != "None" ]; then
    echo -e "  ${RED}FOUND: $NAT_GWS${NC}"
    echo "  !! NAT Gateways cost ~\$0.045/hr + data transfer"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 5. Elastic IPs ──────────────────────────────
echo "5/10  Checking Elastic IPs..."
EIPS=$(aws ec2 describe-addresses --region "$REGION" \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" \
    --query "Addresses[].{AllocationId:AllocationId,PublicIp:PublicIp}" \
    --output text 2>/dev/null || echo "")
if [ -n "$EIPS" ] && [ "$EIPS" != "None" ]; then
    echo -e "  ${RED}FOUND: $EIPS${NC}"
    echo "  !! Unattached EIPs cost \$0.005/hr"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 6. Load Balancers ───────────────────────────
echo "6/10  Checking Load Balancers..."
# Classic LBs (created by K8s)
CLB=$(aws elb describe-load-balancers --region "$REGION" \
    --query "LoadBalancerDescriptions[?contains(LoadBalancerName, 'k8s') || contains(LoadBalancerName, 'a1') || contains(LoadBalancerName, 'ae6')].LoadBalancerName" \
    --output text 2>/dev/null || echo "")
# ALB/NLBs
ALB=$(aws elbv2 describe-load-balancers --region "$REGION" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'k8s') || contains(LoadBalancerName, 'rag')].{Name:LoadBalancerName,Arn:LoadBalancerArn}" \
    --output text 2>/dev/null || echo "")
if [ -n "$CLB" ] && [ "$CLB" != "None" ]; then
    echo -e "  ${RED}Classic LBs: $CLB${NC}"
    FOUND_RESOURCES=true
fi
if [ -n "$ALB" ] && [ "$ALB" != "None" ]; then
    echo -e "  ${RED}ALB/NLBs: $ALB${NC}"
    FOUND_RESOURCES=true
fi
if [ -z "$CLB" ] || [ "$CLB" = "None" ]; then
    if [ -z "$ALB" ] || [ "$ALB" = "None" ]; then
        echo -e "  ${GREEN}None found${NC}"
    fi
fi

# ── 7. EBS Volumes ──────────────────────────────
echo "7/10  Checking orphaned EBS volumes..."
EBS=$(aws ec2 describe-volumes --region "$REGION" \
    --filters "Name=status,Values=available" "Name=tag:Project,Values=$PROJECT_TAG" \
    --query "Volumes[].{Id:VolumeId,Size:Size}" \
    --output text 2>/dev/null || echo "")
# Also check for K8s-tagged volumes
EBS_K8S=$(aws ec2 describe-volumes --region "$REGION" \
    --filters "Name=status,Values=available" "Name=tag-key,Values=kubernetes.io/cluster/$CLUSTER_NAME" \
    --query "Volumes[].{Id:VolumeId,Size:Size}" \
    --output text 2>/dev/null || echo "")
if ([ -n "$EBS" ] && [ "$EBS" != "None" ]) || ([ -n "$EBS_K8S" ] && [ "$EBS_K8S" != "None" ]); then
    echo -e "  ${RED}FOUND: $EBS $EBS_K8S${NC}"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 8. S3 Buckets ───────────────────────────────
echo "8/10  Checking S3 buckets..."
S3=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'rag')].Name" --output text 2>/dev/null || echo "")
if [ -n "$S3" ] && [ "$S3" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $S3${NC}"
    echo "  (S3 cost is minimal — keep if you plan to redeploy)"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 9. VPCs ─────────────────────────────────────
echo "9/10  Checking VPCs..."
VPCS=$(aws ec2 describe-vpcs --region "$REGION" \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" \
    --query "Vpcs[].{Id:VpcId,Cidr:CidrBlock}" \
    --output text 2>/dev/null || echo "")
if [ -n "$VPCS" ] && [ "$VPCS" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $VPCS${NC}"
    echo "  (VPCs are free, but may contain billable sub-resources)"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 10. ECR Repos ───────────────────────────────
echo "10/10 Checking ECR repositories..."
ECR=$(aws ecr describe-repositories --region "$REGION" \
    --query "repositories[?contains(repositoryName, 'rag')].repositoryName" \
    --output text 2>/dev/null || echo "")
if [ -n "$ECR" ] && [ "$ECR" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $ECR${NC}"
    echo "  (ECR cost is minimal unless storing large images)"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── Summary ─────────────────────────────────────
echo ""
echo "=============================================="
if [ "$FOUND_RESOURCES" = true ]; then
    echo -e "  ${RED}ORPHANED RESOURCES DETECTED${NC}"
    echo ""
    echo "  Run with --delete to clean up:"
    echo "    ./scripts/verify-cleanup.sh --delete"
    echo ""
    echo "  Or check the AWS Cost Explorer:"
    echo "    https://console.aws.amazon.com/cost-management/home"
else
    echo -e "  ${GREEN}ALL CLEAR — No orphaned resources found${NC}"
fi
echo "=============================================="
