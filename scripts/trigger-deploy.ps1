# Triggers GitHub Actions deploy workflow (requires: gh CLI, auth to GitHub)
param(
  [string]$Ref = "main",
  [string]$ImageTag = ""
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
if ($ImageTag) {
  gh workflow run deploy-acr-webapp.yml --ref $Ref -f image_tag=$ImageTag
} else {
  gh workflow run deploy-acr-webapp.yml --ref $Ref
}
Write-Host "Workflow dispatch sent. Watch: gh run watch"
