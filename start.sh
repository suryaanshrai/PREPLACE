#!/usr/bin/env bash
# PREPLACE — Development Startup Script (Linux / macOS)
#
# Requirements
#   - Docker (running)
#   - Python venv at backend/.venv  (python3 -m venv backend/.venv)
#   - pip dependencies installed    (pip install -r backend/requirements.txt)
#   - Node.js + npm installed       (for frontend)
#
# Usage (from project root):
#   chmod +x start.sh   # first time only
#   ./start.sh
#
# What it does
#   1. Starts a PostgreSQL 16 Docker container  (preplace-db, port 5433)
#   2. Waits until the database is ready
#   3. Seeds demo data via backend/seed.py      (idempotent)
#   4. Starts the FastAPI backend in background (uvicorn, port 8000)
#      — logs to backend/logs/backend.log
#   5. Starts the Vite frontend in background   (port 5173)
#      — logs to frontend/logs/frontend.log
#   6. Prints service URLs and demo credentials
#   7. Ctrl+C gracefully stops all services

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
BACKEND_LOG="$BACKEND_DIR/logs/backend.log"
FRONTEND_LOG="$FRONTEND_DIR/logs/frontend.log"
CONTAINER_NAME="preplace-db"

# PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

# ── Colours ───────────────────────────────────────────────────────────────
CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
MAGENTA="\033[0;35m"
BOLD="\033[1m"
RESET="\033[0m"

step()  { echo -e "\n${CYAN}  $*${RESET}"; }
ok()    { echo -e "${GREEN}  ✓ $*${RESET}"; }
warn()  { echo -e "${YELLOW}  ! $*${RESET}"; }
abort() { echo -e "\n${RED}  [ERROR] $*${RESET}\n"; exit 1; }

# ── Cleanup on exit / Ctrl+C ──────────────────────────────────────────────
cleanup() {
    echo -e "\n${YELLOW}  Shutting down services...${RESET}"
    [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null && echo "  Stopped backend  (PID $BACKEND_PID)"
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null && echo "  Stopped frontend (PID $FRONTEND_PID)"
    echo -e "${GREEN}  Done. Database container '$CONTAINER_NAME' is still running.${RESET}"
    echo "  To stop it: docker stop $CONTAINER_NAME"
    echo ""
}
trap cleanup EXIT INT TERM

# ── Banner ────────────────────────────────────────────────────────────────
echo ""
echo -e "${MAGENTA}══════════════════════════════════════════════${RESET}"
echo -e "${MAGENTA}       PREPLACE  —  Dev Startup${RESET}"
echo -e "${MAGENTA}══════════════════════════════════════════════${RESET}"

# ── 0. Preflight checks ───────────────────────────────────────────────────
step "Checking prerequisites..."

command -v docker &>/dev/null || abort "Docker not found. Install it from https://docs.docker.com/get-docker/"
docker info &>/dev/null       || abort "Docker daemon is not running. Start Docker and try again."

[[ -f "$VENV_PYTHON" ]] || abort "Python venv not found at '$VENV_PYTHON'.\n  Create it: python3 -m venv backend/.venv\n  Install deps: backend/.venv/bin/pip install -r backend/requirements.txt"

command -v npm &>/dev/null || abort "npm not found. Install Node.js from https://nodejs.org"

ok "All prerequisites met."

# ── 1. PostgreSQL via Docker ──────────────────────────────────────────────
step "Setting up PostgreSQL container '$CONTAINER_NAME' on port 5433..."

if docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    if docker ps --filter "name=^/${CONTAINER_NAME}$" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        ok "Container is already running."
    else
        echo "  Starting existing container..." 
        docker start "$CONTAINER_NAME" >/dev/null
        ok "Container started."
    fi
else
    echo "  Creating new container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -e POSTGRES_USER=preplace_user \
        -e POSTGRES_PASSWORD=preplace_pass \
        -e POSTGRES_DB=preplac \
        -p 5433:5432 \
        --restart unless-stopped \
        postgres:16 >/dev/null
    ok "Container created and started."
fi

# Wait for PostgreSQL to accept connections (up to 45 seconds)
echo "  Waiting for PostgreSQL to accept connections..."
ready=0
for i in $(seq 1 45); do
    if docker exec "$CONTAINER_NAME" pg_isready -U preplace_user -d preplac -q 2>/dev/null; then
        ready=1
        break
    fi
    printf "  ...[$i/45]\r"
    sleep 1
done
printf "\033[K"  # clear the progress line

[[ $ready -eq 1 ]] || abort "PostgreSQL did not become ready in 45 seconds.\n  Check logs: docker logs $CONTAINER_NAME"
ok "PostgreSQL is ready."

# ── 2. Seed demo data ─────────────────────────────────────────────────────
step "Seeding demo data (idempotent — safe to re-run)..."
(cd "$BACKEND_DIR" && "$VENV_PYTHON" seed.py) || abort "seed.py failed. Check the output above."
ok "Demo data ready."

# ── 3. Backend — FastAPI / uvicorn ────────────────────────────────────────
step "Starting FastAPI backend (port 8000)..."
mkdir -p "$BACKEND_DIR/logs"
(
    cd "$BACKEND_DIR"
    source .venv/bin/activate
    uvicorn main:app --reload --host 0.0.0.0 --port 8000 >"$BACKEND_LOG" 2>&1
) &
BACKEND_PID=$!

# Wait briefly and confirm the process is alive
sleep 2
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    abort "Backend failed to start. Check logs: $BACKEND_LOG"
fi
ok "Backend running (PID $BACKEND_PID) — logs: backend/logs/backend.log"

# ── 4. Frontend — Vite dev server ─────────────────────────────────────────
step "Setting up frontend..."
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "  Installing npm dependencies (first run only)..."
    (cd "$FRONTEND_DIR" && npm install) || abort "npm install failed."
fi

step "Starting Vite frontend (port 5173)..."
mkdir -p "$FRONTEND_DIR/logs"
(cd "$FRONTEND_DIR" && npm run dev >"$FRONTEND_LOG" 2>&1) &
FRONTEND_PID=$!

sleep 2
if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    abort "Frontend failed to start. Check logs: $FRONTEND_LOG"
fi
ok "Frontend running (PID $FRONTEND_PID) — logs: frontend/logs/frontend.log"

# ── 5. Summary ────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  PREPLACE is up and running!${RESET}"
echo -e "${GREEN}══════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Services${RESET}"
echo    "    Frontend   http://localhost:5173"
echo    "    Backend    http://localhost:8000"
echo    "    API Docs   http://localhost:8000/docs"
echo ""
echo -e "  ${BOLD}Demo credentials${RESET}"
echo    "    Admin      admin@preplace.smvdu  /  admin@123"
echo    "    Recruiter  priya@techcorp.com    /  recruiter@123"
echo    "    Recruiter  rahul@dataco.com      /  recruiter@123"
echo    "    Applicant  alice@example.com     /  applicant@123"
echo    "    Applicant  bob@example.com       /  applicant@123"
echo    "    Applicant  charlie@example.com   /  applicant@123"
echo ""
echo    "  Press Ctrl+C to stop all services."
echo -e "${GREEN}══════════════════════════════════════════════${RESET}"
echo ""

# Keep the script alive so Ctrl+C triggers cleanup
wait
