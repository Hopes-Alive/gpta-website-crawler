# Local deploy (no GitHub Actions)

Build on your machine, push the image with **Docker**, and point the **Azure Web App** at the new tag using **Azure CLI**. No GitHub linking required.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) running
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (`az`) and `az login` (correct subscription selected)
- A registry credential that can **push** (GHCR PAT with `write:packages`, or ACR admin / service principal)

## Configure once

```bash
cp env.deploy.local.example .env.deploy.local
# Edit .env.deploy.local — do not commit it (gitignored)
```

## Run

**Windows (PowerShell):**

```powershell
.\scripts\deploy-local.ps1
```

**macOS / Linux:**

```bash
chmod +x scripts/deploy-local.sh
./scripts/deploy-local.sh
```

The script:

1. Loads `.env.deploy.local`
2. `docker build` tagging `DEPLOY_IMAGE`
3. Logs in to **ghcr.io** or **ACR** depending on `DEPLOY_IMAGE`
4. `docker push`
5. `az webapp config container set` so the Web App pulls that image

## Web App registry settings (Azure Portal)

Your app should already have **pull** credentials (e.g. `DOCKER_REGISTRY_SERVER_*` for [ghcr.io](https://ghcr.io)). The script only updates the **image:tag**; if the first deploy fails, set registry URL / user / PAT in the portal as in [DEPLOY-AZURE.md](./DEPLOY-AZURE.md).

## GPTA

Set `WEBSITE_CRAWLER_URL` to your public app URL + `/scrape`.
