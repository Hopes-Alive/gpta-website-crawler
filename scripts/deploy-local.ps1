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
$sub = Require-Env "AZURE_SUBSCRIPTION_ID"

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
    az acr login --name $acrName --subscription $sub
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
$containerArgs = @(
  "webapp", "config", "container", "set",
  "--subscription", $sub,
  "--resource-group", $rg,
  "--name", $webapp,
  "--container-image-name", $image
)
if ($lower -match "\.azurecr\.io/") {
  $registryHost = $image.Split("/")[0]
  $containerArgs += @("--container-registry-url", "https://$registryHost")
}
az @containerArgs
Assert-Exit "az webapp config container set"

if ($lower -match "\.azurecr\.io/") {
  $identityName = Optional-Env "ACR_IDENTITY_NAME"
  if ($identityName) {
    $identityId = az identity show --subscription $sub -g $rg -n $identityName --query id -o tsv
    Assert-Exit "az identity show"
    $principalId = az identity show --subscription $sub -g $rg -n $identityName --query principalId -o tsv
    Assert-Exit "az identity show principal"
    $acrName = Optional-Env "ACR_NAME"
    if (-not $acrName) {
      $acrName = ($image.Split("/")[0]).Split(".")[0]
    }
    $acrId = az acr show --subscription $sub -n $acrName --query id -o tsv
    Assert-Exit "az acr show"
    $roles = az role assignment list --subscription $sub --scope $acrId --assignee-object-id $principalId --query "[].roleDefinitionName" -o tsv
    if (-not ($roles -match "AcrPull")) {
      az role assignment create --subscription $sub --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role AcrPull --scope $acrId
      Assert-Exit "az role assignment create AcrPull"
    }
    az webapp config set --subscription $sub -g $rg -n $webapp --acr-use-identity true --acr-identity $identityId
    Assert-Exit "az webapp config set acr identity"
  }
}

Write-Host "Setting WEBSITES_PORT=8000 ..."
az webapp config appsettings set --subscription $sub -g $rg -n $webapp --settings WEBSITES_PORT=8000
Assert-Exit "az webapp config appsettings set WEBSITES_PORT"

Write-Host "Restarting app ..."
az webapp restart --subscription $sub --resource-group $rg --name $webapp
Assert-Exit "az webapp restart"

Write-Host "Done. Image: $image"
