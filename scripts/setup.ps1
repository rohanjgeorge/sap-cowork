param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        if ($Python) { & $Python -m venv .venv }
        else {
            $bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
            if (Test-Path -LiteralPath $bundledPython) { & $bundledPython -m venv .venv }
            else { & py -3.12 -m venv .venv }
        }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Pass -Python with its executable path.' }
    }
    & '.venv/Scripts/python.exe' -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & '.venv/Scripts/python.exe' -m pip install --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
    Push-Location -LiteralPath 'frontend'
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        & npx.cmd playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw 'Browser test installation failed.' }
    } finally { Pop-Location }
    Write-Output 'Setup complete. Run ./start.ps1 to open the local application server.'
} finally { Pop-Location }
