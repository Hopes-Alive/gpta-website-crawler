#Requires -Version 5.1
<#
.SYNOPSIS
  Build Docker image, push to GHCR or ACR, update Azure Linux Web App container.
  No GitHub Actions — uses .env.deploy.local (gitignored).

.EXAMPLE
  Copy env.deploy.local.example to .env.deploy.local, fill values, then:
  .\scripts\deploy-local.ps1
#>
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$envFile = Join-Path $repoRoot ".env.deploy.local"
if (-not (Test-Path $envFile)) {
  Write-Error "Missing $envFile — copy env.deploy.local.example to .env.deploy.local and fill in values."
}

Get-Content $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#")) { return }
  $i = $line.IndexOf("=")
  if ($i -lt 1) { return }
  $key = $line.Substring(0, $i).Trim()
  $val = $line.Substring($i + 1).Trim().Trim('"').Trim("'")
  [Environment]::SetEnvironmentVariable($key, $val, "Process")
}

function Require-Env([string]$name) {
  $v = [Environment]::GetEnvironmentVariable($name, "Process")
  if (-not $v) { Write-Error "Missing required env: $name (set in .env.deploy.local)" }
  return $v
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

$lower = $image.ToLowerInvariant()
if ($lower.StartsWith("ghcr.io/")) {
  $user = Require-Env "GHCR_USERNAME"
  $token = Require-Env "GHCR_TOKEN"
  Write-Host "Logging in to ghcr.io ..."
  $token | docker login ghcr.io -u $user --password-stdin
}
elseif ($image -match "^[^/]+\.azurecr\.io/") {
  $server = Require-Env "ACR_LOGIN_SERVER"
  $acrUser = Require-Env "ACR_USERNAME"
  $acrPass = Require-Env "ACR_PASSWORD"
  Write-Host "Logging in to $server ..."
  $acrPass | docker login $server -u $acrUser --password-stdin
}
else {
  Write-Error "DEPLOY_IMAGE must start with ghcr.io/ or be myregistry.azurecr.io/... — set ACR_* vars for ACR."
}

Write-Host "Pushing $image ..."
docker push $image

Write-Host "Updating Web App container (Azure CLI) ..."
az webapp config container set `
  --resource-group $rg `
  --name $webapp `
  --container-image-name $image

Write-Host "Restarting app ..."
az webapp restart --resource-group $rg --name $webapp

Write-Host "Done. Image: $image"
