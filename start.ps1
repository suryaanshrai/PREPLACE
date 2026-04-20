# PREPLACE — Development Startup Script (Windows / PowerShell)
#
# Requirements
#   - Docker Desktop (running)
#   - Python venv at backend/.venv  (python -m venv backend/.venv)
#   - pip dependencies installed    (pip install -r backend/requirements.txt)
#   - Node.js + npm installed       (for frontend)
#
# Usage (from project root):
#   .\start.ps1
#
# What it does
#   1. Starts a PostgreSQL 16 Docker container  (preplace-db, port 5433)
#   2. Waits until the database is ready
#   3. Seeds demo data via backend/seed.py      (idempotent)
#   4. Opens a new window for the FastAPI backend (uvicorn, port 8000)
#   5. Opens a new window for the Vite frontend  (port 5173)
#   6. Prints service URLs and demo credentials

$ErrorActionPreference = "Stop"
$ProjectRoot  = $PSScriptRoot
$BackendDir   = Join-Path $ProjectRoot "backend"
$FrontendDir  = Join-Path $ProjectRoot "frontend"
$VenvPython   = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"

# ── Helpers ──────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  ! $msg" -ForegroundColor Yellow
}

function Abort([string]$msg) {
    Write-Host ""
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ── 0. Preflight checks ──────────────────────────────────────────────────

Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "       PREPLACE  —  Dev Startup" -ForegroundColor Magenta
Write-Host "══════════════════════════════════════════════" -ForegroundColor Magenta

Write-Step "Checking prerequisites..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Abort "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop"
}

$ErrorActionPreference = "Continue"
$null = docker info 2>&1
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Abort "Docker daemon is not running. Please start Docker Desktop and try again."
}

if (-not (Test-Path $VenvPython)) {
    Abort "Python venv not found at '$VenvPython'.`n  Create it with: python -m venv backend/.venv`n  Then: backend/.venv/Scripts/pip install -r backend/requirements.txt"
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Abort "npm not found. Install Node.js from https://nodejs.org"
}

Write-Ok "All prerequisites met."

# ── 1. PostgreSQL via Docker ─────────────────────────────────────────────

$ContainerName = "preplace-db"
Write-Step "Setting up PostgreSQL container '$ContainerName' on port 5433..."

$existingContainer = docker ps -a --filter "name=^/${ContainerName}$" --format "{{.Names}}" 2>$null

if ($existingContainer -eq $ContainerName) {
    $runningContainer = docker ps --filter "name=^/${ContainerName}$" --format "{{.Names}}" 2>$null
    if ($runningContainer -eq $ContainerName) {
        Write-Ok "Container is already running."
    } else {
        Write-Host "  Starting existing container..." -ForegroundColor Gray
        docker start $ContainerName | Out-Null
        Write-Ok "Container started."
    }
} else {
    Write-Host "  Creating new container..." -ForegroundColor Gray
    docker run -d `
        --name $ContainerName `
        -e POSTGRES_USER=preplace_user `
        -e POSTGRES_PASSWORD=preplace_pass `
        -e POSTGRES_DB=preplac `
        -p 5433:5432 `
        --restart unless-stopped `
        postgres:16 | Out-Null
    Write-Ok "Container created and started."
}

# Wait for PostgreSQL to be ready (up to 45 seconds)
Write-Host "  Waiting for PostgreSQL to accept connections..." -ForegroundColor Gray
$ready = $false
for ($i = 1; $i -le 45; $i++) {
    docker exec $ContainerName pg_isready -U preplace_user -d preplac -q 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Write-Host "  ...[$i/45]" -ForegroundColor DarkGray
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Abort "PostgreSQL did not become ready in 45 seconds. Check: docker logs $ContainerName"
}
Write-Ok "PostgreSQL is ready."

# ── 2. Seed demo data ────────────────────────────────────────────────────

Write-Step "Seeding demo data (idempotent — safe to re-run)..."
Push-Location $BackendDir
try {
    & $VenvPython seed.py
    if ($LASTEXITCODE -ne 0) {
        Abort "seed.py exited with a non-zero code. Check the output above."
    }
} finally {
    Pop-Location
}
Write-Ok "Demo data ready."

# ── 3. Backend — FastAPI / uvicorn ───────────────────────────────────────

Write-Step "Launching FastAPI backend in a new window (port 8000)..."
Start-Process pwsh -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$BackendDir'; & '$VenvActivate'; uvicorn main:app --reload --host 0.0.0.0 --port 8000"
)
Write-Ok "Backend window opened."

# ── 4. Frontend — Vite dev server ────────────────────────────────────────

Write-Step "Setting up frontend..."
$nodeModulesPath = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $nodeModulesPath)) {
    Write-Host "  Installing npm dependencies (first run only)..." -ForegroundColor Gray
    Push-Location $FrontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { Abort "npm install failed." }
    } finally {
        Pop-Location
    }
}

Write-Step "Launching Vite frontend in a new window (port 5173)..."
Start-Process pwsh -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$FrontendDir'; npm run dev"
)
Write-Ok "Frontend window opened."

# ── 5. Summary ───────────────────────────────────────────────────────────

Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  PREPLACE is starting up!" -ForegroundColor Green
Write-Host "══════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Services" -ForegroundColor White
Write-Host "    Frontend   http://localhost:5173"
Write-Host "    Backend    http://localhost:8000"
Write-Host "    API Docs   http://localhost:8000/docs"
Write-Host ""
Write-Host "  Demo credentials" -ForegroundColor White
Write-Host "    Admin      admin@preplace.smvdu  /  admin@123"
Write-Host "    Recruiter  priya@techcorp.com    /  recruiter@123"
Write-Host "    Recruiter  rahul@dataco.com      /  recruiter@123"
Write-Host "    Applicant  alice@example.com     /  applicant@123"
Write-Host "    Applicant  bob@example.com       /  applicant@123"
Write-Host "    Applicant  charlie@example.com   /  applicant@123"
Write-Host ""
Write-Host "  To stop: close the backend/frontend windows and run:"
Write-Host "    docker stop $ContainerName"
Write-Host "══════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
