#!/bin/bash
# scripts/build_push.sh
# Builds the API Docker image and pushes to Amazon ECR.
# Usage: ./scripts/build_push.sh [TAG]
#   TAG defaults to git short SHA if not provided.

set -euo pipefail

REGION="us-east-1"
REPO_NAME="rag-backend-api"
TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"

echo "========================================"
echo "  Build & Push to ECR"
echo "========================================"
echo "  Region:  $REGION"
echo "  Repo:    $REPO_NAME"
echo "  Tag:     $TAG"
echo "========================================"

# 1. Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT_ID" ]; then
    echo "ERROR: Could not get AWS Account ID. Is AWS CLI configured?"
    echo "  Run: aws configure --profile rag-prod"
    exit 1
fi
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
FULL_IMAGE="${ECR_URI}/${REPO_NAME}:${TAG}"

echo ""
echo "Step 1: Creating ECR repository (if not exists)..."
aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository \
        --repository-name "$REPO_NAME" \
        --region "$REGION" \
        --image-scanning-configuration scanOnPush=true \
        --image-tag-mutability MUTABLE

echo ""
echo "Step 2: Logging into ECR..."
aws ecr get-login-password --region "$REGION" | \
    docker login --username AWS --password-stdin "$ECR_URI"

echo ""
echo "Step 3: Building Docker image..."
docker build -t "${REPO_NAME}:${TAG}" -f services/api/Dockerfile services/api/

echo ""
echo "Step 4: Tagging image..."
docker tag "${REPO_NAME}:${TAG}" "$FULL_IMAGE"
# Also tag as latest for convenience
docker tag "${REPO_NAME}:${TAG}" "${ECR_URI}/${REPO_NAME}:latest"

echo ""
echo "Step 5: Pushing to ECR..."
docker push "$FULL_IMAGE"
docker push "${ECR_URI}/${REPO_NAME}:latest"

echo ""
echo "========================================"
echo "  Image pushed successfully!"
echo "  ${FULL_IMAGE}"
echo "========================================"

# Update Helm values with the new image
echo ""
echo "Tip: Update deploy/helm/api/templates/values.yaml with:"
echo "  repository: ${ECR_URI}/${REPO_NAME}"
echo "  tag: \"${TAG}\""
