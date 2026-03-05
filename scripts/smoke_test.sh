#!/bin/bash
# scripts/smoke_test.sh
# Post-deployment smoke test for the RAG pipeline on AWS.
# Tests health endpoints, auth, and chat flow.
#
# Usage:
#   ./scripts/smoke_test.sh                           # Uses port-forward on localhost:8000
#   ./scripts/smoke_test.sh https://api.your-domain.com  # Uses production URL

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

echo "========================================"
echo "  RAG Pipeline — Smoke Test"
echo "  Target: $BASE_URL"
echo "========================================"
echo ""

check() {
    local name="$1"
    local cmd="$2"
    local expected="$3"

    result=$(eval "$cmd" 2>/dev/null || echo "CONN_ERROR")

    if echo "$result" | grep -q "$expected"; then
        echo "  PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  $name"
        echo "        Expected: $expected"
        echo "        Got: $(echo "$result" | head -1)"
        FAIL=$((FAIL + 1))
    fi
}

# -----------------------------------------------------------
# 1. Health Checks
# -----------------------------------------------------------
echo "--- Health Checks ---"

check "Liveness probe" \
    "curl -sf '$BASE_URL/health/liveness'" \
    '"status":"ok"'

check "Readiness probe" \
    "curl -sf '$BASE_URL/health/readiness'" \
    '"redis"'

# -----------------------------------------------------------
# 2. Authentication
# -----------------------------------------------------------
echo ""
echo "--- Authentication ---"

TOKEN_RESPONSE=$(curl -sf -X POST "$BASE_URL/auth/token" 2>/dev/null || echo '{}')
TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
    echo "  PASS  Token generation"
    PASS=$((PASS + 1))
else
    echo "  FAIL  Token generation (empty token)"
    echo "        Response: $TOKEN_RESPONSE"
    FAIL=$((FAIL + 1))
    TOKEN="invalid"
fi

# -----------------------------------------------------------
# 3. Chat Streaming (if token available)
# -----------------------------------------------------------
echo ""
echo "--- Chat Pipeline ---"

if [ "$TOKEN" != "invalid" ]; then
    CHAT_RESPONSE=$(curl -sf -X POST "$BASE_URL/api/v1/chat/stream" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"message": "Hello, are you working?"}' \
        --max-time 60 2>/dev/null || echo "TIMEOUT")

    if echo "$CHAT_RESPONSE" | grep -q "answer\|status\|planner\|responder"; then
        echo "  PASS  Chat stream responds"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  Chat stream"
        echo "        Response: $(echo "$CHAT_RESPONSE" | head -3)"
        FAIL=$((FAIL + 1))
    fi
else
    echo "  SKIP  Chat stream (no valid token)"
fi

# -----------------------------------------------------------
# 4. UI
# -----------------------------------------------------------
echo ""
echo "--- UI ---"

check "Chat UI serves" \
    "curl -sf -o /dev/null -w '%{http_code}' '$BASE_URL/'" \
    "200"

# -----------------------------------------------------------
# 5. Kubernetes Resources (if kubectl available)
# -----------------------------------------------------------
echo ""
echo "--- Kubernetes ---"

if command -v kubectl &>/dev/null && kubectl cluster-info &>/dev/null 2>&1; then
    API_PODS=$(kubectl get pods -l app=api --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$API_PODS" -gt 0 ]; then
        echo "  PASS  API pods running ($API_PODS)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  No API pods in Running state"
        FAIL=$((FAIL + 1))
    fi

    QDRANT_PODS=$(kubectl get pods -l app.kubernetes.io/name=qdrant --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$QDRANT_PODS" -gt 0 ]; then
        echo "  PASS  Qdrant pods running ($QDRANT_PODS)"
        PASS=$((PASS + 1))
    else
        echo "  WARN  No Qdrant pods detected"
    fi
else
    echo "  SKIP  kubectl not connected"
fi

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
