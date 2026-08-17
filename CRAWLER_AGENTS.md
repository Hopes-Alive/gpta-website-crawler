# Website crawler (standalone GPTA companion service)

## Overview

- **Stack**: FastAPI + Crawl4AI (Playwright) for all scrape jobs, including single-URL (`linkHopLimit: 0`).
- **Same-domain BFS**: `linkHopLimit` controls how many link hops to follow from the seed URL; optional `maxUrls` caps distinct pages (default from env `WEBSITE_SCRAPE_MAX_URLS`, default 1500).
- **Security**: URL validation and public-host checks in `main.py`.
- **Local**: `python main.py --host 0.0.0.0 --port 8000`
- **Endpoints**: `POST /scrape`, `GET /health`, `GET /docs`

## Setup

```bash
cd gpta-website-crawler
pip install -r requirements.txt
playwright install
python main.py --host 0.0.0.0 --port 8000
```

## Request body (`POST /scrape`)

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | http(s) seed URL |
| `linkHopLimit` | int 0–20 | `0` = seed only; `N` = follow same-domain links up to N hops (BFS) |
| `maxUrls` | int (optional) | Hard cap on pages visited (1–5000); omit to use `WEBSITE_SCRAPE_MAX_URLS` (default 1500) |

Success response includes `pages: [{ "url", "hop" }]` so the product UI can list every fetched URL by hop. Seed is hop `0`.

## Examples

```bash
# Seed page only (Playwright still used)
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "linkHopLimit": 0}'

# Follow internal links up to 2 hops
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "linkHopLimit": 2, "maxUrls": 200}'
```

## Tests

```bash
cd gpta-website-crawler
python -m pytest tests/ -v
```

## CLI (no server)

```bash
python main.py --cli --json '{"url": "https://example.com", "linkHopLimit": 0}'
```

## Backend integration

The GPTA API **defaults to in-process Playwright** for scrape-ingest (no Python process required). To use this crawler instead, set `WEBSITE_CRAWLER_URL` on the API host to this service’s `POST /scrape` URL. Payloads use `linkHopLimit` (and optional `maxUrls`).

## Deployment

When offloading: point `WEBSITE_CRAWLER_URL` to your crawler’s `POST /scrape` URL (for example Azure Function). Set `WEBSITE_SCRAPE_MAX_URLS` on the crawler process if you need a different default cap.
