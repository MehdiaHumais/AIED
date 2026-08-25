# AIED Setup Script
# Run this script to set up the development environment

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " AIED - Britsync AI Engineering Department" -ForegroundColor Cyan
Write-Host " Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python 3.12+ is required!" -ForegroundColor Red
    exit 1
}

# Check Node.js
Write-Host "Checking Node.js..." -ForegroundColor Yellow
node --version
npm --version

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
pip install -e ".[dev]"

# Create .env if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "Please edit .env with your API keys" -ForegroundColor Yellow
}

# Test database connections
Write-Host "Testing Neon PostgreSQL connection..." -ForegroundColor Yellow
python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://neondb_owner:npg_B7dXEKQmFT5Z@ep-weathered-bonus-at5l05mx-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require'))" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Neon PostgreSQL connected" -ForegroundColor Green
} else {
    Write-Host "  ✗ Neon PostgreSQL connection failed" -ForegroundColor Red
}

Write-Host "Testing Upstash Redis connection..." -ForegroundColor Yellow
python -c "import redis; r = redis.Redis.from_url('redis://default:gQAAAAAAAegaAAIgcDFmYjY5ZTQ1YjIyNmE0NzRhOTkzZmRhOGFlNzY0YzI1Yw@comic-lobster-124954.upstash.io:6379'); r.ping()" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Upstash Redis connected" -ForegroundColor Green
} else {
    Write-Host "  ✗ Upstash Redis connection failed" -ForegroundColor Red
}

# Install dashboard dependencies
Write-Host "Installing dashboard dependencies..." -ForegroundColor Yellow
Push-Location apps/dashboard
npm install
Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Infrastructure:" -ForegroundColor Cyan
Write-Host "  PostgreSQL: Neon (cloud)" -ForegroundColor White
Write-Host "  Redis: Upstash (cloud)" -ForegroundColor White
Write-Host "  Qdrant: Qdrant Cloud (cloud)" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Run: python -m apps.api.main"
Write-Host "  2. Run: cd apps/dashboard && npm run dev"
Write-Host "  3. Open http://localhost:3000"
Write-Host ""
