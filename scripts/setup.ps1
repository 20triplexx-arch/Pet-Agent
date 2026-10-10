param()
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" } }
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv; Check-Exit }
python -m pip --python .venv\Scripts\python.exe install -r backend\requirements.txt
Check-Exit
if (Get-Command npm -ErrorAction SilentlyContinue) { $npmCommand = 'npm'; $npmPrefix = @() }
else {
    if (-not (Test-Path '.tools\package\bin\npm-cli.js')) {
        New-Item -ItemType Directory -Force '.tools' | Out-Null
        Invoke-WebRequest 'https://registry.npmjs.org/npm/-/npm-11.6.2.tgz' -OutFile '.tools\npm.tgz'
        tar -xzf '.tools\npm.tgz' -C '.tools'; Check-Exit
    }
    $npmCommand = 'node'; $npmPrefix = @((Join-Path (Get-Location) '.tools\package\bin\npm-cli.js'))
}
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Push-Location frontend
try { & $npmCommand @npmPrefix ci; Check-Exit; & $npmCommand @npmPrefix run build; Check-Exit } finally { Pop-Location }
Push-Location backend
try { & '..\.venv\Scripts\python.exe' -m scripts.init_db --demo; Check-Exit } finally { Pop-Location }
Write-Host 'Ready. Run: powershell -ExecutionPolicy Bypass -File scripts/start.ps1'

