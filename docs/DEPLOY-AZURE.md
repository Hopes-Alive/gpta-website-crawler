# Deploy to Azure (Linux Web App for Containers)

Pick **one** registry path:

| Workflow | Registry | When to use |
|----------|----------|-------------|
| **Local scripts** | GHCR or ACR | **No GitHub** — see **[docs/LOCAL-DEPLOY.md](./LOCAL-DEPLOY.md)** |
| **`deploy-ghcr-webapp.yml`** | [GitHub Container Registry](https://ghcr.io) (`ghcr.io/...`) | Web App **Configuration** uses `DOCKER_REGISTRY_SERVER_URL=https://ghcr.io` (your setup). |
| **`deploy-acr-webapp.yml`** | Azure Container Registry (`*.azurecr.io`) | Web App pulls from ACR. |

---

## GitHub Container Registry (GHCR) — typical setup

Your Web App already has registry settings similar to:

- `DOCKER_REGISTRY_SERVER_URL` = `https://ghcr.io`
- `DOCKER_REGISTRY_SERVER_USERNAME` = your GitHub user (e.g. `zuhairm2001`)
- `DOCKER_REGISTRY_SERVER_PASSWORD` = a **GitHub PAT** with `read:packages` (and `write:packages` only if you push manually from laptop — **not** stored in this repo)

**Do not** paste the PAT into GitHub Issues or chat. Only in **Azure Portal → Web App → Configuration**.

### GitHub Actions variables (GHCR workflow)

| Variable | Your example | Notes |
|----------|----------------|-------|
| `AZURE_RESOURCE_GROUP` | `mpn-aicg-hotelai-perm-dev-rg-ae` | Resource group containing the Web App |
| `AZURE_WEBAPP_NAME` | `website-crawler-e0chg5dhhugzgyfm` | From hostname `website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net` ([live check](https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net/)) |
| `GHCR_IMAGE` (optional) | `ghcr.io/zuhairm2001/gpta-website-crawler` | Set if the image name **must** differ from `ghcr.io/<lowercase_owner>/<lowercase_repo>` |

### GitHub Actions secrets (same for GHCR or ACR deploy)

| Secret | Still required? |
|--------|------------------|
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | **Yes** — for OIDC so the workflow can call `azure/webapps-deploy`. We still need your **Azure subscription ID** if it is not already in secrets. |

### Run (GHCR)

```bash
gh workflow run deploy-ghcr-webapp.yml --ref main
```

### GPTA `WEBSITE_CRAWLER_URL`

Use the public app URL (no trailing slash before path is fine):

```text
https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net/scrape
```

### Portal hygiene

- Remove **duplicate** application settings keys (you listed `DOCKER_REGISTRY_SERVER_USERNAME` twice).
- Keep **`WEBSITES_PORT`** = **`8000`** for this image.

---

## Azure Container Registry (ACR)

This repo ships **`.github/workflows/deploy-acr-webapp.yml`**: build the `Dockerfile`, push to your **Azure Container Registry**, then point your existing **Web App** at that image.

## One-time: GitHub → Azure (OIDC)

Use a **federated workload identity** so GitHub never stores Azure passwords.

1. In Azure Portal, create or pick an **App registration** (service principal) for CI.
2. Add **Federated credential** (GitHub Actions):
   - Entity: **Environment** or **Branch** (recommended: branch `main` on your repo).
   - Issuer: `https://token.actions.githubusercontent.com`
   - Subject: `repo:YOUR_ORG/YOUR_REPO:ref:refs/heads/main` (see [Microsoft docs](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure?tabs=azure-portal%2Clinux)).
3. Grant that identity on Azure:
   - **AcrPush** on the target **Container registry** (scope: registry or repository).
   - **Website Contributor** (or narrower) on the **Web App** or its resource group so deployment can update the container image.

4. In GitHub → your crawler repo → **Settings → Secrets and variables → Actions**:

   **Secrets**

   | Name | Value |
   |------|--------|
   | `AZURE_CLIENT_ID` | Application (client) ID of the app registration |
   | `AZURE_TENANT_ID` | Directory (tenant) ID |
   | `AZURE_SUBSCRIPTION_ID` | Subscription ID |

   **Variables** (repository or environment)

   | Name | Example | Meaning |
   |------|---------|--------|
   | `ACR_NAME` | `mycompanyacr` | Registry **short name** (not the full `*.azurecr.io` host) |
   | `IMAGE_REPOSITORY` | `gpta-website-crawler` | Image name **inside** ACR (create in portal or first push creates it) |
   | `AZURE_RESOURCE_GROUP` | `rg-ai-prod` | Resource group that contains the **Web App** |
   | `AZURE_WEBAPP_NAME` | `app-gpta-crawler-prod` | Linux Web App name |

## Web App settings (Azure Portal)

1. **Deployment Center** / **Container** settings: after first successful workflow run, the workflow updates the image; ensure the Web App is **Linux** and configured for **single container** from ACR.
2. **Configuration → Application settings**
   - **`WEBSITES_PORT`** = `8000` (the container listens on port 8000; see `Dockerfile` / `main.py`).
3. **HTTPS only** on; note the site URL, e.g. `https://<AZURE_WEBAPP_NAME>.azurewebsites.net`.

## GPTA backend

Set:

```bash
WEBSITE_CRAWLER_URL=https://<AZURE_WEBAPP_NAME>.azurewebsites.net/scrape
```

(Path is `/scrape`, same as local.)

## Run the deploy

### GitHub UI

**Actions** → **Deploy crawler (ACR + Web App)** → **Run workflow** (optional custom tag).

### CLI (from laptop, GitHub CLI logged in)

```bash
cd /path/to/gpta-website-crawler
gh workflow run deploy-acr-webapp.yml --ref main
```

Optional custom tag:

```bash
gh workflow run deploy-acr-webapp.yml --ref main -f image_tag=v1.2.3
```

### Cursor agent

Open this repo in Cursor and say **deploy** (or “run the crawler deploy workflow”). The project rule under `.cursor/rules/` tells the agent to use `gh workflow run` or the Actions tab as above.

## Troubleshooting

- **`az acr login` fails**: identity needs **AcrPush** (or AcrDelete for admin tasks) on that registry.
- **Web App does not update**: identity needs permission to update the app; check **Activity log** on the Web App.
- **502 / connection reset**: set **`WEBSITES_PORT=8000`** and restart the app.
- **Playwright in container**: the Dockerfile already installs browser deps and runs `playwright install`; cold start can be slow.

## What we need from you (checklist)

Fill these in GitHub **Variables** / **Secrets** (and optionally paste into a secure note for your team):

1. **GitHub repository** path (`org/repo`) for federated credential subject.
2. **`ACR_NAME`** (short name).
3. **`IMAGE_REPOSITORY`** (image name in ACR).
4. **`AZURE_WEBAPP_NAME`** and **`AZURE_RESOURCE_GROUP`**.
5. Confirm the Web App is **Linux + container from ACR** (not .NET zip deploy).

After that, OIDC secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) complete the loop.
