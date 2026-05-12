# Triggers GitHub Actions deploy workflow (requires: gh CLI, auth to GitHub)
param(
  [string]$Ref = "main",
  [string]$ImageTag = "",
  [ValidateSet("ghcr", "acr")]
  [string]$Registry = "ghcr"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$wf = if ($Registry -eq "acr") { "deploy-acr-webapp.yml" } else { "deploy-ghcr-webapp.yml" }
if ($ImageTag) {
  gh workflow run $wf --ref $Ref -f image_tag=$ImageTag
} else {
  gh workflow run $wf --ref $Ref
}
Write-Host "Workflow dispatch sent ($wf). Watch: gh run watch"
