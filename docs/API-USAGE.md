# Calling the Website Crawler API

Use this service from another Web App when you need to scrape one public web page or crawl same-domain links from a starting URL.

## Base URL

Current Azure Web App:

```text
https://app-expressagent-crawler-prod-aue.azurewebsites.net
```

Health check:

```text
GET /health
```

Scrape endpoint (blocking compatibility):

```text
POST /scrape
```

Async job API (preferred for live crawl progress; Azure App Service may drop long POSTs):

```text
POST /scrape/start
GET  /scrape/jobs/{jobId}
GET  /scrape/jobs/{jobId}/result
POST /scrape/jobs/{jobId}/cancel
```

Full production URL:

```text
https://app-expressagent-crawler-prod-aue.azurewebsites.net/scrape
```

In the consuming Web App, store this as an environment variable:

```env
WEBSITE_CRAWLER_URL=https://app-expressagent-crawler-prod-aue.azurewebsites.net/scrape
```

The Express Agent API still calls the previous crawler. Change `WEBSITE_CRAWLER_URL` on the API apps to the URL above only after this app is running the crawler image.

## Request

Send `POST /scrape` with `Content-Type: application/json`.

```json
{
  "url": "https://example.com",
  "linkHopLimit": 0,
  "maxUrls": 200
}
```

Fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Public `http://` or `https://` URL to scrape. Private hosts, localhost, non-public IPs, and custom ports are rejected. |
| `linkHopLimit` | number | No | `0` scrapes only the seed URL. `1` or higher follows same-domain links up to that many hops. Maximum is `20`. |
| `maxUrls` | number | No | Maximum number of pages to visit. Use this with `linkHopLimit` to control crawl size. Maximum is `5000`; default is configured by the crawler service. |

Recommended starting values:

```json
{
  "url": "https://example.com",
  "linkHopLimit": 0,
  "maxUrls": 200
}
```

For a small same-domain crawl:

```json
{
  "url": "https://example.com",
  "linkHopLimit": 2,
  "maxUrls": 200
}
```

## Response

Success:

```json
{
  "success": true,
  "context": "Extracted text content from the page or crawl...",
  "pages": [
    { "url": "https://example.com", "hop": 0 },
    { "url": "https://example.com/about", "hop": 1 }
  ]
}
```

`pages` is the same-site inventory the consumer stores for the UI: seed is hop `0`, links found on that page are hop `1`, and so on.

Failure:

```json
{
  "success": false,
  "context": "",
  "error": "Reason the crawl failed"
}
```

The `context` field is plain extracted text intended for downstream processing, such as indexing, summarization, or feeding into an LLM. It is not HTML. Use `pages` for the structured URL list.

## Async job API (live progress)

Prefer this path when the caller needs to show which page is being scraped. `POST /scrape` remains the blocking compatibility API (one JSON body when the whole BFS finishes).

Jobs live in memory on a **single** app instance and are removed about **2 hours** after complete, fail, or cancel. URL validation is the same as `POST /scrape` (public `http(s)` only).

### Start

`POST /scrape/start` with the same JSON body as `POST /scrape`.

`202`:

```json
{ "success": true, "jobId": "3f1c0a2e-2c8a-4f1d-9e3a-7b2d1c4e5f60" }
```

Invalid URL: `400` `{ "success": false, "error": "..." }` (no job is created).

### Poll

`GET /scrape/jobs/{jobId}` about every 2.5s. The poll payload does **not** include `context`.

```json
{
  "success": true,
  "jobId": "3f1c0a2e-2c8a-4f1d-9e3a-7b2d1c4e5f60",
  "status": "running",
  "progress": {
    "pagesDone": 4,
    "maxUrls": 100,
    "queueSize": 12,
    "lastUrls": ["https://example.com/about", "https://example.com/contact"],
    "linksDiscoveredLastBatch": 8,
    "collectedPages": [
      { "url": "https://example.com/", "hop": 0 },
      { "url": "https://example.com/about", "hop": 1 }
    ],
    "phase": "crawling"
  },
  "error": null
}
```

`status`: `queued` | `running` | `complete` | `failed` | `cancelled`.  
`progress.phase`: `crawling` until the crawl loop ends, then `complete` or `failed`.  
`collectedPages` lists fetched URLs in order (seed hop `0`), capped at 200. `lastUrls` are full URLs from the latest batch (max 8).

Unknown `jobId`: `404`.

### Result

`GET /scrape/jobs/{jobId}/result`

| Job status | HTTP | Body |
|---|---|---|
| `complete` | 200 | `{ "success": true, "context": "...", "pages": [{ "url", "hop" }] }` (same as blocking `POST /scrape`) |
| `failed` | 200 | `{ "success": false, "context": "", "error": "..." }` |
| `queued` / `running` | 409 | `{ "success": false, "error": "Job still running" }` |

### Cancel

`POST /scrape/jobs/{jobId}/cancel` stops the crawl between batches and returns pages fetched so far:

```json
{
  "success": true,
  "status": "cancelled",
  "pages": [
    { "url": "https://example.com/", "hop": 0 }
  ]
}
```

The crawler does not decide whether to index a partial crawl; the caller does.

### TypeScript poll example

```ts
const crawlerOrigin = process.env.WEBSITE_CRAWLER_ORIGIN; // host only, no /scrape

const start = await fetch(`${crawlerOrigin}/scrape/start`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ url: "https://example.com", linkHopLimit: 2, maxUrls: 200 }),
});
const { jobId } = await start.json();

for (;;) {
  const snap = await fetch(`${crawlerOrigin}/scrape/jobs/${jobId}`);
  const job = await snap.json();
  // job.progress.lastUrls / collectedPages → live UI
  if (job.status === "complete") {
    const done = await fetch(`${crawlerOrigin}/scrape/jobs/${jobId}/result`);
    const result = await done.json();
    break;
  }
  if (job.status === "failed" || job.status === "cancelled") {
    break;
  }
  await new Promise((r) => setTimeout(r, 2500));
}
```

## JavaScript / TypeScript Example

```ts
const crawlerUrl = process.env.WEBSITE_CRAWLER_URL;

if (!crawlerUrl) {
  throw new Error("Missing WEBSITE_CRAWLER_URL");
}

const response = await fetch(crawlerUrl, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    url: "https://example.com",
    linkHopLimit: 0,
    maxUrls: 200,
  }),
});

if (!response.ok) {
  throw new Error(`Crawler HTTP error: ${response.status}`);
}

const result = await response.json();

if (!result.success) {
  throw new Error(result.error || "Crawler failed");
}

console.log(result.context);
```

## C# Example

```csharp
using System.Net.Http.Json;

var crawlerUrl = Environment.GetEnvironmentVariable("WEBSITE_CRAWLER_URL")
    ?? throw new InvalidOperationException("Missing WEBSITE_CRAWLER_URL");

using var http = new HttpClient
{
    Timeout = TimeSpan.FromMinutes(10)
};

var response = await http.PostAsJsonAsync(crawlerUrl, new
{
    url = "https://example.com",
    linkHopLimit = 0,
    maxUrls = 200
});

response.EnsureSuccessStatusCode();

var result = await response.Content.ReadFromJsonAsync<CrawlerResponse>();

if (result is null || !result.Success)
{
    throw new Exception(result?.Error ?? "Crawler failed");
}

Console.WriteLine(result.Context);

public sealed record CrawlerResponse(bool Success, string Context, string? Error);
```

## curl Example

```bash
curl -X POST "https://app-expressagent-crawler-prod-aue.azurewebsites.net/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","linkHopLimit":0,"maxUrls":200}'
```

## Notes For Calling Apps

- The **blocking** `POST /scrape` endpoint is public HTTPS and currently does not require an API key. Set a long timeout; multi-page Playwright crawls can take several minutes.
- For live progress, use `POST /scrape/start` and poll `GET /scrape/jobs/{jobId}` (short timeouts). Fetch `context` from `/result` only after `complete`.
- Jobs are in-memory (one app instance). Do not scale the crawler to multiple instances if you rely on job polling.
- Use `linkHopLimit: 0` for fastest single-page extraction.
- Use `maxUrls` whenever `linkHopLimit` is greater than `0` to avoid unexpectedly large crawls.
- Only public internet URLs are accepted by the crawler.
