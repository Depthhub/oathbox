# Oathbox install for Windows PowerShell:  .\scripts\install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$pyArgs = if ($py -eq "py") { @("-3") } else { @() }

& $py @pyArgs -m venv backend\.venv
& backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install -e "backend[dev]"

Push-Location web
npm ci
npm run build
Pop-Location

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env - fill in NEARAI_API_KEY, NEAR_ACCOUNT_ID, NEAR_PRIVATE_KEY"
}
Write-Host "Done. Run .\scripts\demo.ps1 and open http://127.0.0.1:8000"
