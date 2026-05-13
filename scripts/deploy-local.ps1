#Requires -Version 5.1
<#
.SYNOPSIS
  Build Docker image, push to GHCR or ACR, update Azure Linux Web App container.
  No GitHub Actions. Uses .env.deploy.local if present (gitignored), else process env.

.EXAMPLE
  Copy env.deploy.local.example to .env.deploy.local, fill values, then:
  .\scripts\deploy-local.ps1
#>
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$envFile = Join-Path $repoRoot ".env.deploy.local"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $i = $line.IndexOf("=")
    if ($i -lt 1) { return }
    $key = $line.Substring(0, $i).Trim()
    $val = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
    [Environment]::SetEnvironmentVariable($key, $val, "Process")
  }
} else {
  Write-Host 'No .env.deploy.local - using process environment (set DEPLOY_IMAGE, GHCR_USERNAME, GHCR_TOKEN, AZURE_WEBAPP_NAME, AZURE_RESOURCE_GROUP before running).'
}

function Require-Env([string]$name) {
  $v = [Environment]::GetEnvironmentVariable($name, "Process")
  if (-not $v) { Write-Error "Missing required env: $name (set in .env.deploy.local or export before running)" }
  return $v
}

function Optional-Env([string]$name) {
  return [Environment]::GetEnvironmentVariable($name, "Process")
}

function Assert-Exit([string]$step) {
  if ($LASTEXITCODE -ne 0) {
    Write-Error "$step failed (exit $LASTEXITCODE)"
  }
}

$image = Require-Env "DEPLOY_IMAGE"
$webapp = Require-Env "AZURE_WEBAPP_NAME"
$rg = Require-Env "AZURE_RESOURCE_GROUP"

foreach ($cmd in @("docker", "az")) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Error "Required command not found: $cmd"
  }
}

Write-Host "Building $image ..."
docker build -t $image .
Assert-Exit "docker build"

$lower = $image.ToLowerInvariant()
if ($lower.StartsWith("ghcr.io/")) {
  $user = Require-Env "GHCR_USERNAME"
  $token = Require-Env "GHCR_TOKEN"
  Write-Host "Logging in to ghcr.io ..."
  $token | docker login ghcr.io -u $user --password-stdin
  Assert-Exit "docker login (ghcr.io)"
}
elseif ($image -match "^[^/]+\.azurecr\.io/") {
  $server = Require-Env "ACR_LOGIN_SERVER"
  $acrUser = Optional-Env "ACR_USERNAME"
  $acrPass = Optional-Env "ACR_PASSWORD"
  if ($acrUser -and $acrPass) {
    Write-Host "Logging in to $server with ACR credentials ..."
    $acrPass | docker login $server -u $acrUser --password-stdin
    Assert-Exit "docker login ($server)"
  } else {
    $acrName = Optional-Env "ACR_NAME"
    if (-not $acrName) {
      $acrName = $server.Split(".")[0]
    }
    Write-Host "Logging in to ACR $acrName with Azure CLI ..."
    az acr login --name $acrName
    Assert-Exit "az acr login ($acrName)"
  }
}
else {
  Write-Error "DEPLOY_IMAGE must start with ghcr.io/ or use an ACR host *.azurecr.io/ (set ACR_LOGIN_SERVER and optionally ACR_NAME)."
}

Write-Host "Pushing $image ..."
docker push $image
Assert-Exit "docker push"

Write-Host "Updating Web App container (Azure CLI) ..."
az webapp config container set `
  --resource-group $rg `
  --name $webapp `
  --container-image-name $image
Assert-Exit "az webapp config container set"

Write-Host "Restarting app ..."
az webapp restart --resource-group $rg --name $webapp
Assert-Exit "az webapp restart"

Write-Host "Done. Image: $image"
