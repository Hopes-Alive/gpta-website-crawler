# Calling the Website Crawler API

Use this service from another Web App when you need to scrape one public web page or crawl same-domain links from a starting URL.

## Base URL

Current Azure Web App:

```text
https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net
```

Health check:

```text
GET /health
```

Scrape endpoint:

```text
POST /scrape
```

Full production URL:

```text
https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net/scrape
```

In the consuming Web App, store this as an environment variable:

```env
WEBSITE_CRAWLER_URL=https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net/scrape
```

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
curl -X POST "https://website-crawler-e0chg5dhhugzgyfm.australiaeast-01.azurewebsites.net/scrape" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","linkHopLimit":0,"maxUrls":200}'
```

## Notes For Calling Apps

- The endpoint is public HTTPS and currently does not require an API key.
- Set a long timeout in the calling app. Multi-page Playwright crawls can take several minutes.
- Use `linkHopLimit: 0` for fastest single-page extraction.
- Use `maxUrls` whenever `linkHopLimit` is greater than `0` to avoid unexpectedly large crawls.
- Only public internet URLs are accepted by the crawler.
