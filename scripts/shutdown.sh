#!/usr/bin/env bash
#
# Stops all RAG Platform local services.
# Usage: ./scripts/shutdown.sh   OR   make stop
#
set -euo pipefail

YELLOW='\033[0;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo "======================================================"
echo "  RAG Platform — Shutting Down"
echo "======================================================"

# ── 1. FastAPI / Uvicorn (port 8000) ────────────────────
echo ""
echo -e "${YELLOW}[1/3] Stopping API server (port 8000)...${RESET}"
API_PIDS=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$API_PIDS" ]; then
    echo "$API_PIDS" | xargs kill -15 2>/dev/null || true
    sleep 1
    # Force-kill if still running
    REMAINING=$(lsof -ti:8000 2>/dev/null || true)
    if [ -n "$REMAINING" ]; then
        echo "$REMAINING" | xargs kill -9 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✅ API server stopped${RESET}"
else
    echo -e "  ${DIM}⏭️  Not running${RESET}"
fi

# ── 2. Docker containers ───────────────────────────────
echo ""
echo -e "${YELLOW}[2/3] Stopping Docker containers...${RESET}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if docker compose -f "$PROJECT_DIR/docker-compose.yml" ps --quiet 2>/dev/null | head -1 | grep -q .; then
    docker compose -f "$PROJECT_DIR/docker-compose.yml" down 2>&1 | while read -r line; do
        echo "  $line"
    done
    echo -e "  ${GREEN}✅ Docker containers stopped${RESET}"
else
    echo -e "  ${DIM}⏭️  No containers running${RESET}"
fi

# ── 3. Stale Python processes from this project ───────
echo ""
echo -e "${YELLOW}[3/3] Checking for stale processes...${RESET}"
STALE_PIDS=$(pgrep -f "uvicorn services.api.main" 2>/dev/null || true)
if [ -n "$STALE_PIDS" ]; then
    echo "$STALE_PIDS" | xargs kill -15 2>/dev/null || true
    echo -e "  ${GREEN}✅ Killed stale uvicorn processes${RESET}"
else
    echo -e "  ${DIM}⏭️  No stale processes${RESET}"
fi

# ── Summary ────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "  ${GREEN}✅  All services stopped.${RESET}"
echo ""
echo "  To restart:  make up && make dev"
echo "======================================================"
echo ""
