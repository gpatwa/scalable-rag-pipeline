#!/bin/bash
# scripts/post_deploy_verify.sh
# Run this AFTER 'make deploy-aws' completes.
# Automates: pod check → port-forward → cloud DB init → smoke test → UI launch.
#
# Usage:
#   ./scripts/post_deploy_verify.sh
#   ./scripts/post_deploy_verify.sh --skip-init   # Skip DB init (already done)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SKIP_INIT=false
PIDS_TO_CLEANUP=()

[ "${1:-}" = "--skip-init" ] && SKIP_INIT=true

# Cleanup port-forwards on exit
cleanup() {
    echo ""
    echo "Cleaning up port-forwards..."
    for pid in "${PIDS_TO_CLEANUP[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "Done. Port-forwards stopped."
}
trap cleanup EXIT

echo "=============================================="
echo "  Post-Deployment Verification"
echo "=============================================="
echo ""

# =============================================================
# Step 1: Verify kubectl connection
# =============================================================
echo "Step 1: Verifying cluster connection..."
if ! kubectl cluster-info &>/dev/null 2>&1; then
    echo "  ERROR: kubectl not connected to cluster."
    echo "  Run: aws eks update-kubeconfig --name rag-platform-cluster --region us-east-1"
    exit 1
fi
echo "  Connected to: $(kubectl config current-context)"
echo ""

# =============================================================
# Step 2: Check pod status
# =============================================================
echo "Step 2: Checking pod status..."
echo ""

# Wait for critical pods
echo "  Waiting for API pods..."
kubectl wait --for=condition=ready pod -l app=api --timeout=180s 2>/dev/null || \
    echo "  WARNING: API pods not ready yet"

echo ""
echo "  All pods:"
echo "  ---------------------------------------------------------------"
printf "  %-45s %-10s %-10s\n" "NAME" "READY" "STATUS"
echo "  ---------------------------------------------------------------"
kubectl get pods --no-headers 2>/dev/null | while read -r name ready status restarts age; do
    # Color code status
    if [ "$status" = "Running" ]; then
        printf "  %-45s %-10s %-10s\n" "$name" "$ready" "$status"
    else
        printf "  %-45s %-10s %-10s ⚠️\n" "$name" "$ready" "$status"
    fi
done
echo "  ---------------------------------------------------------------"

# Count running vs total
TOTAL_PODS=$(kubectl get pods --no-headers 2>/dev/null | wc -l | tr -d ' ')
RUNNING_PODS=$(kubectl get pods --no-headers 2>/dev/null | grep -c "Running" || echo "0")
echo "  $RUNNING_PODS/$TOTAL_PODS pods running"

if [ "$RUNNING_PODS" -eq 0 ]; then
    echo ""
    echo "  ERROR: No pods running. Check logs:"
    echo "    kubectl describe pod <pod-name>"
    echo "    kubectl logs <pod-name>"
    exit 1
fi
echo ""

# =============================================================
# Step 3: Check services
# =============================================================
echo "Step 3: Checking services..."
echo ""
kubectl get svc --no-headers 2>/dev/null | while read line; do echo "  $line"; done
echo ""

# =============================================================
# Step 4: Set up port-forwards
# =============================================================
echo "Step 4: Setting up port-forwards..."

# Kill any existing port-forwards on these ports
for port in 8000 6333 7687; do
    lsof -ti:$port 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 1

# API (8080 in cluster → 8000 local)
API_SVC=$(kubectl get svc --no-headers 2>/dev/null | grep -E "api" | awk '{print $1}' | head -1)
if [ -n "$API_SVC" ]; then
    API_PORT=$(kubectl get svc "$API_SVC" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "8080")
    kubectl port-forward "svc/$API_SVC" "8000:$API_PORT" &>/dev/null &
    PIDS_TO_CLEANUP+=($!)
    echo "  API:     localhost:8000 → $API_SVC:$API_PORT"
else
    echo "  WARNING: No API service found"
fi

# Qdrant
QDRANT_SVC=$(kubectl get svc --no-headers 2>/dev/null | grep -E "qdrant" | awk '{print $1}' | head -1)
if [ -n "$QDRANT_SVC" ]; then
    kubectl port-forward "svc/$QDRANT_SVC" 6333:6333 &>/dev/null &
    PIDS_TO_CLEANUP+=($!)
    echo "  Qdrant:  localhost:6333 → $QDRANT_SVC:6333"
fi

# Neo4j
NEO4J_SVC=$(kubectl get svc --no-headers 2>/dev/null | grep -E "neo4j" | awk '{print $1}' | head -1)
if [ -n "$NEO4J_SVC" ]; then
    kubectl port-forward "svc/$NEO4J_SVC" 7687:7687 &>/dev/null &
    PIDS_TO_CLEANUP+=($!)
    echo "  Neo4j:   localhost:7687 → $NEO4J_SVC:7687"
fi

# Wait for port-forwards to establish
sleep 3
echo ""

# =============================================================
# Step 5: Initialize cloud databases
# =============================================================
if [ "$SKIP_INIT" = false ]; then
    echo "Step 5: Initializing cloud databases..."
    echo ""
    python3 "$SCRIPT_DIR/init_cloud.py" \
        --qdrant-host localhost --qdrant-port 6333 \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-user neo4j --neo4j-password password \
        2>&1 | while read line; do echo "  $line"; done
    echo ""
else
    echo "Step 5: Cloud DB init — SKIPPED (--skip-init)"
    echo ""
fi

# =============================================================
# Step 6: Run smoke tests
# =============================================================
echo "Step 6: Running smoke tests..."
echo ""
bash "$SCRIPT_DIR/smoke_test.sh" http://localhost:8000 2>&1 | while read line; do echo "  $line"; done
SMOKE_EXIT=${PIPESTATUS[0]}
echo ""

# =============================================================
# Step 7: Test GPU scale-up (optional)
# =============================================================
echo "Step 7: GPU scale-to-zero status..."
GPU_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -i "gpu\|g5\|g4" | wc -l | tr -d ' ')
GPU_PODS=$(kubectl get pods --no-headers 2>/dev/null | grep -i "gpu-worker" | wc -l | tr -d ' ')
echo "  GPU nodes: $GPU_NODES (expected: 0 when idle)"
echo "  GPU worker pods: $GPU_PODS (expected: 0 when idle)"
echo ""
if [ "$GPU_NODES" -eq 0 ]; then
    echo "  Scale-to-zero is working! GPU nodes will spin up on first chat request."
    echo "  First request will take ~2-5 min (Karpenter provisions SPOT GPU node)."
else
    echo "  GPU nodes are running. They will terminate ~5 min after last request."
fi
echo ""

# =============================================================
# Step 8: Summary & next steps
# =============================================================
echo "=============================================="
echo "  Verification Complete!"
echo "=============================================="
echo ""
echo "  Pod Status:     $RUNNING_PODS/$TOTAL_PODS running"
if [ "${SMOKE_EXIT:-1}" -eq 0 ]; then
    echo "  Smoke Tests:    PASSED"
else
    echo "  Smoke Tests:    SOME FAILURES (check output above)"
fi
echo "  GPU Scale:      $([ "$GPU_NODES" -eq 0 ] && echo 'Idle (cost-effective)' || echo 'Active')"
echo ""
echo "  -------------------------------------------"
echo "  What to do now:"
echo "  -------------------------------------------"
echo ""
echo "  1. Open Chat UI:"
echo "     http://localhost:8000"
echo ""
echo "  2. Try a test question (from sample_questions.txt):"
echo "     'What is consistent hashing and why is it important?'"
echo "     (First request takes 2-5 min for GPU warmup)"
echo ""
echo "  3. Ingest documents to the cloud:"
echo "     python3 scripts/ingest_local.py /path/to/your/file.pdf"
echo ""
echo "  4. Check AWS costs (after 24 hours):"
echo "     https://console.aws.amazon.com/cost-management/home"
echo ""
echo "  5. Watch GPU nodes scale up/down:"
echo "     kubectl get nodes -w"
echo ""
echo "  6. When done testing, tear everything down:"
echo "     make destroy"
echo ""
echo "  Port-forwards are active. Press Ctrl+C to stop."
echo ""

# Keep script alive to maintain port-forwards
echo "  Keeping port-forwards alive... (Ctrl+C to stop)"
wait
