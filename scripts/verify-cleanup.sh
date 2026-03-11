#!/bin/bash
# scripts/verify-cleanup.sh
# Run AFTER terraform destroy to catch orphaned resources still billing you.
# This is the safety net that prevents surprise AWS bills.
#
# Checks 16 AWS resource categories for orphans tagged with the project
# or matching the "rag" naming convention.
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
TOTAL_CHECKS=16

[ "${1:-}" = "--delete" ] && DELETE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "  POST-DESTROY VERIFICATION"
echo "  Region: $REGION"
echo "  Checks: $TOTAL_CHECKS resource categories"
echo "  Mode: $([ "$DELETE" = true ] && echo 'CHECK + DELETE' || echo 'CHECK ONLY')"
echo "=============================================="
echo ""

# ── 1. EKS Cluster ──────────────────────────────
echo "1/$TOTAL_CHECKS  Checking EKS clusters..."
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
echo "2/$TOTAL_CHECKS  Checking RDS clusters..."
RDS_CLUSTERS=$(aws rds describe-db-clusters --region "$REGION" \
    --query "DBClusters[?contains(DBClusterIdentifier, 'rag')].{Id:DBClusterIdentifier,Status:Status}" \
    --output text 2>/dev/null || echo "")
if [ -n "$RDS_CLUSTERS" ] && [ "$RDS_CLUSTERS" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $RDS_CLUSTERS"
    echo "  !! Aurora costs even when stopped (storage charges)"
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

# ── 3. ElastiCache Clusters ─────────────────────
echo "3/$TOTAL_CHECKS  Checking ElastiCache clusters..."
ELASTICACHE=$(aws elasticache describe-replication-groups --region "$REGION" \
    --query "ReplicationGroups[?contains(ReplicationGroupId, 'rag')].{Id:ReplicationGroupId,Status:Status}" \
    --output text 2>/dev/null || echo "")
if [ -n "$ELASTICACHE" ] && [ "$ELASTICACHE" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $ELASTICACHE"
    echo "  !! ElastiCache costs ~\$12-25/mo even at smallest tier"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for rg in $(aws elasticache describe-replication-groups --region "$REGION" \
            --query "ReplicationGroups[?contains(ReplicationGroupId, 'rag')].ReplicationGroupId" \
            --output text 2>/dev/null); do
            echo "  Deleting ElastiCache replication group $rg..."
            aws elasticache delete-replication-group --replication-group-id "$rg" --no-retain-primary-cluster --region "$REGION" 2>/dev/null
            echo "    Deletion initiated"
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 4. EC2 Instances (EKS nodes) ────────────────
echo "4/$TOTAL_CHECKS  Checking EC2 instances..."
# Check by project tag AND by EKS cluster tag
EC2_INSTANCES=$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=instance-state-name,Values=running,stopped" \
    --query "Reservations[].Instances[?Tags[?Key=='Project' && Value=='$PROJECT_TAG'] || Tags[?Key=='kubernetes.io/cluster/$CLUSTER_NAME']].{Id:InstanceId,Type:InstanceType,State:State.Name}" \
    --output text 2>/dev/null || echo "")
if [ -n "$EC2_INSTANCES" ] && [ "$EC2_INSTANCES" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $EC2_INSTANCES"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 5. NAT Gateways ─────────────────────────────
echo "5/$TOTAL_CHECKS  Checking NAT Gateways..."
NAT_GWS=$(aws ec2 describe-nat-gateways --region "$REGION" \
    --filter "Name=state,Values=available,pending" \
    --query "NatGateways[?Tags[?Key=='Project' && Value=='$PROJECT_TAG'] || Tags[?contains(Value, 'rag')]].{Id:NatGatewayId,State:State}" \
    --output text 2>/dev/null || echo "")
if [ -n "$NAT_GWS" ] && [ "$NAT_GWS" != "None" ]; then
    echo -e "  ${RED}FOUND: $NAT_GWS${NC}"
    echo "  !! NAT Gateways cost ~\$0.045/hr + data transfer"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 6. Elastic IPs ──────────────────────────────
echo "6/$TOTAL_CHECKS  Checking Elastic IPs..."
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

# ── 7. Load Balancers ───────────────────────────
echo "7/$TOTAL_CHECKS  Checking Load Balancers..."
CLB=$(aws elb describe-load-balancers --region "$REGION" \
    --query "LoadBalancerDescriptions[?contains(LoadBalancerName, 'k8s') || contains(LoadBalancerName, 'rag')].LoadBalancerName" \
    --output text 2>/dev/null || echo "")
ALB=$(aws elbv2 describe-load-balancers --region "$REGION" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'k8s') || contains(LoadBalancerName, 'rag')].{Name:LoadBalancerName}" \
    --output text 2>/dev/null || echo "")
if ([ -n "$CLB" ] && [ "$CLB" != "None" ]) || ([ -n "$ALB" ] && [ "$ALB" != "None" ]); then
    [ -n "$CLB" ] && [ "$CLB" != "None" ] && echo -e "  ${RED}Classic LBs: $CLB${NC}"
    [ -n "$ALB" ] && [ "$ALB" != "None" ] && echo -e "  ${RED}ALB/NLBs: $ALB${NC}"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 8. EBS Volumes ──────────────────────────────
echo "8/$TOTAL_CHECKS  Checking orphaned EBS volumes..."
# Check by project tag, K8s tag, AND by "rag" in Name tag
EBS=$(aws ec2 describe-volumes --region "$REGION" \
    --filters "Name=status,Values=available" \
    --query "Volumes[?Tags[?Key=='Project' && Value=='$PROJECT_TAG'] || Tags[?Key=='kubernetes.io/cluster/$CLUSTER_NAME'] || Tags[?(Key=='Name' && contains(Value, 'rag'))]].{Id:VolumeId,Size:Size,Name:Tags[?Key=='Name']|[0].Value}" \
    --output text 2>/dev/null || echo "")
if [ -n "$EBS" ] && [ "$EBS" != "None" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $EBS"
    echo "  !! EBS volumes cost ~\$0.08/GB/month"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for vol in $(aws ec2 describe-volumes --region "$REGION" \
            --filters "Name=status,Values=available" \
            --query "Volumes[?Tags[?Key=='Project' && Value=='$PROJECT_TAG'] || Tags[?Key=='kubernetes.io/cluster/$CLUSTER_NAME'] || Tags[?(Key=='Name' && contains(Value, 'rag'))]].VolumeId" \
            --output text 2>/dev/null); do
            echo "  Deleting volume $vol..."
            aws ec2 delete-volume --volume-id "$vol" --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 9. S3 Buckets ───────────────────────────────
echo "9/$TOTAL_CHECKS  Checking S3 buckets..."
S3=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'rag')].Name" --output text 2>/dev/null || echo "")
if [ -n "$S3" ] && [ "$S3" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $S3${NC}"
    echo "  (S3 cost is minimal — keep if you plan to redeploy)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for bucket in $S3; do
            if [[ "$bucket" == *"terraform"* ]]; then
                echo -e "  ${YELLOW}KEPT: $bucket (Terraform state — delete manually if not redeploying)${NC}"
            else
                echo "  Deleting S3 bucket $bucket..."
                aws s3 rb "s3://$bucket" --force 2>/dev/null
            fi
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 10. VPCs ────────────────────────────────────
echo "10/$TOTAL_CHECKS Checking VPCs..."
VPCS=$(aws ec2 describe-vpcs --region "$REGION" \
    --filters "Name=tag:Project,Values=$PROJECT_TAG" \
    --query "Vpcs[].{Id:VpcId,Cidr:CidrBlock}" \
    --output text 2>/dev/null || echo "")
# Also check by name tag containing "rag"
VPCS_NAME=$(aws ec2 describe-vpcs --region "$REGION" \
    --query "Vpcs[?Tags[?(Key=='Name' && contains(Value, 'rag'))]].{Id:VpcId,Cidr:CidrBlock}" \
    --output text 2>/dev/null || echo "")
ALL_VPCS="$VPCS $VPCS_NAME"
ALL_VPCS=$(echo "$ALL_VPCS" | xargs)
if [ -n "$ALL_VPCS" ] && [ "$ALL_VPCS" != "None" ] && [ "$ALL_VPCS" != " " ]; then
    echo -e "  ${YELLOW}FOUND: $ALL_VPCS${NC}"
    echo "  (VPCs are free, but may contain billable sub-resources)"
    FOUND_RESOURCES=true
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 11. ECR Repos ──────────────────────────────
echo "11/$TOTAL_CHECKS Checking ECR repositories..."
ECR=$(aws ecr describe-repositories --region "$REGION" \
    --query "repositories[?contains(repositoryName, 'rag')].repositoryName" \
    --output text 2>/dev/null || echo "")
if [ -n "$ECR" ] && [ "$ECR" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $ECR${NC}"
    echo "  (ECR cost is minimal unless storing large images)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for repo in $ECR; do
            echo "  Deleting ECR repo $repo..."
            aws ecr delete-repository --repository-name "$repo" --force --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 12. DynamoDB Tables ─────────────────────────
echo "12/$TOTAL_CHECKS Checking DynamoDB tables..."
DYNAMO=$(aws dynamodb list-tables --region "$REGION" \
    --query "TableNames[?contains(@, 'rag') || contains(@, 'terraform')]" \
    --output text 2>/dev/null || echo "")
if [ -n "$DYNAMO" ] && [ "$DYNAMO" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $DYNAMO${NC}"
    echo "  (PAY_PER_REQUEST tables are free when idle)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for table in $DYNAMO; do
            echo "  Deleting DynamoDB table $table..."
            aws dynamodb delete-table --table-name "$table" --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 13. SQS Queues ──────────────────────────────
echo "13/$TOTAL_CHECKS Checking SQS queues..."
SQS=$(aws sqs list-queues --region "$REGION" \
    --queue-name-prefix "Karpenter" \
    --query "QueueUrls" --output text 2>/dev/null || echo "")
SQS_RAG=$(aws sqs list-queues --region "$REGION" \
    --queue-name-prefix "rag" \
    --query "QueueUrls" --output text 2>/dev/null || echo "")
ALL_SQS=$(echo "$SQS $SQS_RAG" | tr -s ' ' | sed 's/None//g' | xargs)
if [ -n "$ALL_SQS" ]; then
    echo -e "  ${YELLOW}FOUND: $ALL_SQS${NC}"
    echo "  (SQS is free when idle, but clean up for hygiene)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for url in $ALL_SQS; do
            [ "$url" = "None" ] && continue
            echo "  Deleting SQS queue $url..."
            aws sqs delete-queue --queue-url "$url" --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 14. CloudWatch Log Groups ───────────────────
echo "14/$TOTAL_CHECKS Checking CloudWatch Log Groups..."
LOGS=$(aws logs describe-log-groups --region "$REGION" \
    --query "logGroups[?contains(logGroupName, 'rag')].logGroupName" \
    --output text 2>/dev/null || echo "")
if [ -n "$LOGS" ] && [ "$LOGS" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $LOGS${NC}"
    echo "  (Log storage costs ~\$0.03/GB/month)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for lg in $LOGS; do
            echo "  Deleting log group $lg..."
            aws logs delete-log-group --log-group-name "$lg" --region "$REGION" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 15. IAM Roles & Policies ────────────────────
echo "15/$TOTAL_CHECKS Checking orphaned IAM roles..."
IAM_ROLES=$(aws iam list-roles \
    --query "Roles[?contains(RoleName, 'rag') || contains(RoleName, 'Karpenter') || contains(RoleName, 'EBS_CSI') || contains(RoleName, 'eks-node-group')].RoleName" \
    --output text 2>/dev/null || echo "")
# Filter out AWS service-linked roles (can't delete those)
CUSTOM_ROLES=""
for role in $IAM_ROLES; do
    path=$(aws iam get-role --role-name "$role" --query "Role.Path" --output text 2>/dev/null || echo "/aws-service-role/")
    if [[ "$path" != /aws-service-role/* ]]; then
        CUSTOM_ROLES="$CUSTOM_ROLES $role"
    fi
done
CUSTOM_ROLES=$(echo "$CUSTOM_ROLES" | xargs)
if [ -n "$CUSTOM_ROLES" ]; then
    echo -e "  ${YELLOW}FOUND: $CUSTOM_ROLES${NC}"
    echo "  (IAM is free, but orphaned roles are a security risk)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for role in $CUSTOM_ROLES; do
            echo "  Cleaning up role $role..."
            for policy in $(aws iam list-attached-role-policies --role-name "$role" \
                --query "AttachedPolicies[*].PolicyArn" --output text 2>/dev/null); do
                aws iam detach-role-policy --role-name "$role" --policy-arn "$policy" 2>/dev/null
            done
            for ip in $(aws iam list-instance-profiles-for-role --role-name "$role" \
                --query "InstanceProfiles[*].InstanceProfileName" --output text 2>/dev/null); do
                aws iam remove-role-from-instance-profile --instance-profile-name "$ip" --role-name "$role" 2>/dev/null
                aws iam delete-instance-profile --instance-profile-name "$ip" 2>/dev/null
            done
            aws iam delete-role --role-name "$role" 2>/dev/null && echo "    Deleted $role"
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 16. EventBridge Rules ────────────────────────
echo "16/$TOTAL_CHECKS Checking EventBridge rules..."
EB_RULES=$(aws events list-rules --region "$REGION" \
    --query "Rules[?contains(Name, 'Karpenter') || contains(Name, 'rag')].Name" \
    --output text 2>/dev/null || echo "")
if [ -n "$EB_RULES" ] && [ "$EB_RULES" != "None" ]; then
    echo -e "  ${YELLOW}FOUND: $EB_RULES${NC}"
    echo "  (EventBridge rules are free, but clean up for hygiene)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for rule in $EB_RULES; do
            targets=$(aws events list-targets-by-rule --rule "$rule" --region "$REGION" \
                --query "Targets[*].Id" --output text 2>/dev/null)
            if [ -n "$targets" ] && [ "$targets" != "None" ]; then
                aws events remove-targets --rule "$rule" --ids $targets --region "$REGION" 2>/dev/null
            fi
            aws events delete-rule --name "$rule" --region "$REGION" 2>/dev/null
            echo "    Deleted rule $rule"
        done
    fi
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
