# Copies the three secret values from .env into the Azure Container App as encrypted
# secrets, and points the app's settings at them. Values are never printed.
#   .\scripts\azure-set-secrets.ps1            (uses resource group oathbox-rg, app oathbox)
param(
    [string]$ResourceGroup = "oathbox-rg",
    [string]$App = "oathbox"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Read .env without echoing anything
$vals = @{}
foreach ($line in Get-Content .env) {
    if ($line -match '^\s*(NEARAI_API_KEY|NEAR_ACCOUNT_ID|NEAR_PRIVATE_KEY)\s*=\s*(.*?)\s*$') {
        $vals[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
    }
}
foreach ($k in "NEARAI_API_KEY", "NEAR_ACCOUNT_ID", "NEAR_PRIVATE_KEY") {
    if (-not $vals[$k]) { throw "$k is empty in .env" }
}
if (-not $vals["NEAR_ACCOUNT_ID"].EndsWith(".testnet")) { throw "NEAR_ACCOUNT_ID must be a .testnet account" }

# Values go straight from .env to az; they are not printed or saved in shell history.
Write-Host "==> Storing 3 secrets in $App (values hidden)"
az containerapp secret set -g $ResourceGroup -n $App -o none --secrets `
    "nearai-api-key=$($vals['NEARAI_API_KEY'])" `
    "near-account-id=$($vals['NEAR_ACCOUNT_ID'])" `
    "near-private-key=$($vals['NEAR_PRIVATE_KEY'])"
$ok = $LASTEXITCODE -eq 0
$vals = $null
if (-not $ok) { throw "az containerapp secret set failed" }

Write-Host "==> Pointing app settings at the secrets"
az containerapp update -g $ResourceGroup -n $App -o none --set-env-vars `
    "NEARAI_API_KEY=secretref:nearai-api-key" `
    "NEAR_ACCOUNT_ID=secretref:near-account-id" `
    "NEAR_PRIVATE_KEY=secretref:near-private-key"
if ($LASTEXITCODE -ne 0) { throw "az containerapp update failed" }
Write-Host "Done. The app restarts with the keys in a minute or two."
