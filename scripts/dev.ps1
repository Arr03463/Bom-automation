# AutoBOM — start both dev servers (Windows / PowerShell).
#
# Opens the backend (FastAPI :8000) and frontend (Vite :3000) each in its own
# window so Ctrl+C shuts each down cleanly (uvicorn --reload spawns a child
# worker; a separate window makes stopping it reliable).
#
# Usage:  pwsh scripts\dev.ps1     (or right-click > Run with PowerShell)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

$backend = @"
Set-Location '$root\backend'
Write-Host 'AutoBOM backend  ->  http://localhost:8000' -ForegroundColor Cyan
& '$root\backend\.venv\Scripts\python.exe' main.py
"@

$frontend = @"
Set-Location '$root\frontend'
Write-Host 'AutoBOM frontend ->  http://localhost:3000' -ForegroundColor Cyan
npm run dev
"@

Start-Process powershell -ArgumentList '-NoExit', '-Command', $backend
Start-Process powershell -ArgumentList '-NoExit', '-Command', $frontend

Write-Host ''
Write-Host 'Started AutoBOM:' -ForegroundColor Green
Write-Host '  backend  -> http://localhost:8000/api/health'
Write-Host '  frontend -> http://localhost:3000'
Write-Host 'Close the two spawned windows (or Ctrl+C in each) to stop.'
