#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env.deploy.local"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "No .env.deploy.local — using existing environment variables." >&2
fi

: "${DEPLOY_IMAGE:?}"
: "${AZURE_WEBAPP_NAME:?}"
: "${AZURE_RESOURCE_GROUP:?}"

command -v docker >/dev/null
command -v az >/dev/null

echo "Building $DEPLOY_IMAGE ..."
docker build -t "$DEPLOY_IMAGE" .

ilower=$(echo "$DEPLOY_IMAGE" | tr '[:upper:]' '[:lower:]')
if [[ "$ilower" == ghcr.io/* ]]; then
  : "${GHCR_USERNAME:?}"
  : "${GHCR_TOKEN:?}"
  echo "Logging in to ghcr.io ..."
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
elif echo "$DEPLOY_IMAGE" | grep -qE '^[^/]+\.azurecr\.io/'; then
  : "${ACR_LOGIN_SERVER:?}"
  : "${ACR_USERNAME:?}"
  : "${ACR_PASSWORD:?}"
  echo "Logging in to $ACR_LOGIN_SERVER ..."
  echo "$ACR_PASSWORD" | docker login "$ACR_LOGIN_SERVER" -u "$ACR_USERNAME" --password-stdin
else
  echo "DEPLOY_IMAGE must be ghcr.io/... or *.azurecr.io/..." >&2
  exit 1
fi

echo "Pushing $DEPLOY_IMAGE ..."
docker push "$DEPLOY_IMAGE"

echo "Updating Web App ..."
az webapp config container set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_WEBAPP_NAME" \
  --container-image-name "$DEPLOY_IMAGE"

az webapp restart --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_WEBAPP_NAME"
echo "Done."
