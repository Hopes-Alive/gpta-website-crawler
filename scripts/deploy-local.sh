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
: "${AZURE_SUBSCRIPTION_ID:?}"

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
  ACR_USERNAME="${ACR_USERNAME:-}"
  ACR_PASSWORD="${ACR_PASSWORD:-}"
  if [[ -n "$ACR_USERNAME" && -n "$ACR_PASSWORD" ]]; then
    echo "Logging in to $ACR_LOGIN_SERVER ..."
    echo "$ACR_PASSWORD" | docker login "$ACR_LOGIN_SERVER" -u "$ACR_USERNAME" --password-stdin
  else
    ACR_NAME="${ACR_NAME:-${ACR_LOGIN_SERVER%%.*}}"
    echo "Logging in to ACR $ACR_NAME with Azure CLI ..."
    az acr login --name "$ACR_NAME" --subscription "$AZURE_SUBSCRIPTION_ID"
  fi
else
  echo "DEPLOY_IMAGE must be ghcr.io/... or *.azurecr.io/..." >&2
  exit 1
fi

echo "Pushing $DEPLOY_IMAGE ..."
docker push "$DEPLOY_IMAGE"

echo "Updating Web App ..."
az webapp config container set \
  --subscription "$AZURE_SUBSCRIPTION_ID" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_WEBAPP_NAME" \
  --container-image-name "$DEPLOY_IMAGE"

if echo "$ilower" | grep -qE '\.azurecr\.io/'; then
  if [[ -n "${ACR_IDENTITY_NAME:-}" ]]; then
    identity_id="$(az identity show --subscription "$AZURE_SUBSCRIPTION_ID" -g "$AZURE_RESOURCE_GROUP" -n "$ACR_IDENTITY_NAME" --query id -o tsv)"
    principal_id="$(az identity show --subscription "$AZURE_SUBSCRIPTION_ID" -g "$AZURE_RESOURCE_GROUP" -n "$ACR_IDENTITY_NAME" --query principalId -o tsv)"
    acr_name="${ACR_NAME:-${ACR_LOGIN_SERVER%%.*}}"
    acr_id="$(az acr show --subscription "$AZURE_SUBSCRIPTION_ID" -n "$acr_name" --query id -o tsv)"
    roles="$(az role assignment list --subscription "$AZURE_SUBSCRIPTION_ID" --scope "$acr_id" --assignee-object-id "$principal_id" --query "[].roleDefinitionName" -o tsv)"
    if ! echo "$roles" | grep -q "AcrPull"; then
      az role assignment create --subscription "$AZURE_SUBSCRIPTION_ID" --assignee-object-id "$principal_id" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$acr_id"
    fi
    az webapp config set --subscription "$AZURE_SUBSCRIPTION_ID" -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_WEBAPP_NAME" --acr-use-identity true --acr-identity "$identity_id"
  fi
fi

echo "Setting WEBSITES_PORT=8000 ..."
az webapp config appsettings set --subscription "$AZURE_SUBSCRIPTION_ID" -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_WEBAPP_NAME" --settings WEBSITES_PORT=8000

az webapp restart --subscription "$AZURE_SUBSCRIPTION_ID" --resource-group "$AZURE_RESOURCE_GROUP" --name "$AZURE_WEBAPP_NAME"
echo "Done."
