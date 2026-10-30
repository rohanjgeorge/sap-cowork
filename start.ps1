$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run ./scripts/setup.ps1 first.' }
    if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Run npm run build in frontend first.' }
    Write-Output 'SAP CoWork: http://127.0.0.1:8000 (Ctrl+C stops the server)'
    & '.venv/Scripts/python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
} finally { Pop-Location }
