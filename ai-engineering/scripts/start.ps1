# AIED Start Script

Write-Host "Starting AIED Services..." -ForegroundColor Cyan

# Start API server
Write-Host "Starting API server on port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..'; python -m apps.api.main"

# Start Dashboard
Write-Host "Starting Dashboard on port 3000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\apps\dashboard'; npm run dev"

Write-Host ""
Write-Host "AIED is starting up!" -ForegroundColor Green
Write-Host "  API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Dashboard: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
