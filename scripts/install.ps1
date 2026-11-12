# Oathbox install for Windows PowerShell:  .\scripts\install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Step($what, [scriptblock]$run) {
    Write-Host "==> $what"
    & $run
    if ($LASTEXITCODE -ne 0) { throw "Failed: $what (exit code $LASTEXITCODE)" }
}

# Python 3.11+ virtual environment for the backend
if (Get-Command py -ErrorAction SilentlyContinue) {
    Step "Create Python venv" { py -3 -m venv backend\.venv }
} else {
    Step "Create Python venv" { python -m venv backend\.venv }
}
$venvPy = "backend\.venv\Scripts\python.exe"
Step "Upgrade pip" { & $venvPy -m pip install --quiet --upgrade pip }
Step "Install backend" { & $venvPy -m pip install --quiet -e "backend[dev]" }

# Web app
Push-Location web
try {
    Step "Install web packages" { npm ci --no-fund --no-audit }
    Step "Build web app" { npm run build }
} finally {
    Pop-Location
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env - fill in NEARAI_API_KEY, NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY and SAMPLE_ROOM_ID"
}
Write-Host "Done. Run .\scripts\demo.ps1 and open http://127.0.0.1:8000"
