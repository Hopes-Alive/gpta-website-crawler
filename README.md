# GPTA Website Crawler

Standalone **FastAPI** service used by the GPTA backend when `WEBSITE_CRAWLER_URL` points at this app’s `POST /scrape` endpoint. It uses **Crawl4AI** (Playwright) for same-domain BFS crawling.

This repository was split from the main [GPTA](https://github.com/) monorepo so you can **deploy and version it independently** (Azure Web App, Container Apps, Fly.io, VM + Docker, etc.).

## Quick start (local)

```bash
cd gpta-website-crawler
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
playwright install
python main.py --host 0.0.0.0 --port 8000
```

- **Health:** `GET http://localhost:8000/health`
- **Scrape:** `POST http://localhost:8000/scrape` with JSON `{ "url": "https://example.com", "linkHopLimit": 0, "maxUrls": 200 }`
- **OpenAPI:** `http://localhost:8000/docs`

## GPTA backend wiring

In the API server `.env`:

```bash
WEBSITE_CRAWLER_URL=https://<your-deployed-host>/scrape
# optional
WEBSITE_CRAWLER_TIMEOUT_MS=600000
```

Use the **public HTTPS URL** of this service in production (the crawler validates that target URLs are public hosts).

## Docker

```bash
docker build -t gpta-website-crawler .
docker run -p 8000:8000 gpta-website-crawler
```

## Tests

```bash
python -m pytest tests/ -v
```

## Deploy to Azure (Web App for Containers)

- **GHCR** ([ghcr.io](https://ghcr.io)) — if your Web App registry URL is GitHub Container Registry: **`.github/workflows/deploy-ghcr-webapp.yml`**
- **ACR** — Azure Container Registry: **`.github/workflows/deploy-acr-webapp.yml`**

One-time OIDC + variables: **[docs/DEPLOY-AZURE.md](./docs/DEPLOY-AZURE.md)**.

```bash
gh workflow run deploy-ghcr-webapp.yml --ref main   # GHCR
# gh workflow run deploy-acr-webapp.yml --ref main   # ACR
```

Or on Windows: `.\scripts\trigger-deploy.ps1` (defaults to GHCR workflow; edit script to switch).

In **Cursor**, open this repo and ask the agent to **deploy** — the rule in `.cursor/rules/azure-deploy-crawler.mdc` picks **GHCR or ACR** workflow as documented.

## CI

- **GHCR + Web App:** `deploy-ghcr-webapp.yml`
- **ACR + Web App:** `deploy-acr-webapp.yml`

## Docs

See [CRAWLER_AGENTS.md](./CRAWLER_AGENTS.md) for API details and security notes.
See [docs/DEPLOY-AZURE.md](./docs/DEPLOY-AZURE.md) for Azure variables, OIDC, and GPTA `WEBSITE_CRAWLER_URL`.
