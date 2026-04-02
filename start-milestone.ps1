# Milestone Startup Script for Windows
# This script ensures a clean environment and launches both backend and frontend

Write-Host "--- Milestone Recovery Tool Startup ---" -ForegroundColor Cyan

# 1. Kill any stale processes
Write-Host "Cleaning up stale processes..."
Stop-Process -Name node -ErrorAction SilentlyContinue
Stop-Process -Name electron -ErrorAction SilentlyContinue
Stop-Process -Name python -ErrorAction SilentlyContinue

# 2. Check for .env
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..."
    Copy-Item ".env.example" ".env"
}

# 3. Start Backend (Uvicorn)
Write-Host "Starting Backend API (localhost:8000)..." -ForegroundColor Yellow
cd services/api
# We use 'python3' as we found it is the Windows Store alias on this system
Start-Job -ScriptBlock { 
    & 'C:\Users\other\AppData\Local\Microsoft\WindowsApps\python3.exe' -m uvicorn src.main:app --host 127.0.0.1 --port 8000 
}
cd ../..

# 4. Start Frontend (Vite + Electron)
Write-Host "Starting Milestone Desktop..." -ForegroundColor Green
$env:ELECTRON_RUN_AS_NODE=$null
$env:NODE_ENV="development"

cd apps/desktop
Start-Process npm.cmd -ArgumentList "run dev" -WindowStyle Normal

Write-Host "Startup complete! The app window should appear shortly." -ForegroundColor Cyan
Write-Host "Backend is running in the background as a job."
