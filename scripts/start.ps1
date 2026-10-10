param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run scripts/setup.ps1 first.' }
if ($Rebuild -or -not (Test-Path 'frontend\dist\index.html')) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location frontend
        try { npm run build; if ($LASTEXITCODE -ne 0) { throw 'Build failed' } } finally { Pop-Location }
    } else {
        $npmLocal = Join-Path (Get-Location) '.tools\package\bin\npm-cli.js'
        Push-Location frontend
        try { node $npmLocal run build; if ($LASTEXITCODE -ne 0) { throw 'Build failed' } } finally { Pop-Location }
    }
}
Set-Location backend
& '..\.venv\Scripts\python.exe' -m scripts.init_db
if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed' }
Write-Host 'Open http://127.0.0.1:8000 . Press Ctrl+C to stop.'
& '..\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000

