# multi_page/multiple_page_scrapper.py
from __future__ import annotations

import asyncio
import hashlib
import re
from collections import deque
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse, urljoin, urldefrag

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

FetchOne = Callable[[str], Awaitable[tuple[list[str], str]]]


# ---------- URL + HTML helpers ----------


def normalize_url(url: str, base: Optional[str] = None) -> str:
    """Resolve relative URLs, strip fragments, normalize trailing slash (except root)."""
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path if parsed.path != "" else "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return parsed._replace(path=path, query=parsed.query).geturl()


def _norm_host(h: Optional[str]) -> str:
    if not h:
        return ""
    h = h.strip().lower().rstrip(".")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        h = h.encode("idna").decode("ascii")
    except Exception:
        pass
    return h


def same_domain(url: str, base_domain: str) -> bool:
    """
    Return True if URL's host is the same as, or a subdomain of, base_domain.
    Ignores ports. Handles IPv6 + IDN.
    """
    host = _norm_host(urlparse(url).hostname)
    base = _norm_host(base_domain)
    return host == base or (host.endswith("." + base) if host and base else False)


def should_skip_url(url: str) -> bool:
    """Filter non-content or noisy URLs."""
    u = url.lower()
    skip_keywords = [
        "login", "logout", "signin", "signup", "register",
        "account", "profile", "cart", "checkout", "wishlist",
        "search", "query=", "filter=", "sort=",
        "wp-json", "xmlrpc",
    ]
    if any(kw in u for kw in skip_keywords):
        return True
    non_html_ext = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".7z", ".gz", ".tar",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
        ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
        ".json", ".xml", ".rss", ".atom", ".ics",
    )
    if any(u.endswith(ext) for ext in non_html_ext):
        return True
    return False


def clean_html(html_content: Optional[str]) -> str:
    """Remove scripts/styles/layout elements and return readable text from headings/paras/lists."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form", "aside"]):
        tag.decompose()
    parts = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        txt = tag.get_text(" ", strip=True)
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    if text.strip():
        return text.strip()

    # Many SPAs / marketing sites use almost no semantic tags after we strip chrome — fall back to body text.
    body = soup.body
    blob = (body or soup).get_text("\n", strip=True)
    blob = re.sub(r"[ \t]+", " ", blob)
    blob = re.sub(r"\n\s*\n+", "\n\n", blob)
    return blob.strip()


def _markdown_from_result(result: object) -> str:
    """Best-effort string from Crawl4AI markdown field (str or MarkdownGenerationResult)."""
    m = getattr(result, "markdown", None)
    if m is None:
        return ""
    if isinstance(m, str):
        return m.strip()
    for attr in ("fit_markdown", "raw_markdown"):
        raw = getattr(m, attr, None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


# ---------- Crawl4AI single-page fetch (production) ----------


async def _fetch_and_extract(crawler: AsyncWebCrawler, url: str, base_domain: str):
    """
    Returns: (internal_links: list[str], cleaned_text: str)
    """
    cfg = CrawlerRunConfig(
        verbose=False,
        cache_mode=CacheMode.ENABLED,
        check_robots_txt=True,
        remove_overlay_elements=True,
        page_timeout=60000,
        # Loose wait: many sites lack <main>/<article>; strict wait caused empty crawls on Azure.
        wait_for="css:body",
        js_code=["window.scrollTo(0, document.body.scrollHeight);"],
    )
    result = await crawler.arun(url=url, config=cfg)
    if not getattr(result, "success", False):
        status = getattr(result, "status_code", "unknown")
        print(f" ❌ Failed: {url} (status: {status})")
        return [], ""

    html = getattr(result, "html", "") or ""
    cleaned_text = clean_html(html)
    if not cleaned_text.strip():
        cleaned_text = _markdown_from_result(result)
    low = cleaned_text.lower()
    if ("page you are trying to access is no longer available" in low) or ("404" in low and "page" in low):
        print(f" ⚠️ Skipped error/empty: {url}")
        return [], ""

    links_field = getattr(result, "links", None)
    hrefs: list[str] = []
    if isinstance(links_field, dict):
        internal_objs = links_field.get("internal", []) or []
        external_objs = links_field.get("external", []) or []
        for obj in (internal_objs + external_objs):
            href = obj.get("href")
            if href:
                hrefs.append(href)
    elif isinstance(links_field, list):
        hrefs = [str(x) for x in links_field]
    elif isinstance(links_field, str):
        hrefs = [links_field]

    internal_links = []
    for href in hrefs:
        absolute = normalize_url(href, base=url)
        if same_domain(absolute, base_domain) and not should_skip_url(absolute):
            internal_links.append(absolute)

    print(f" ✅ Success: {url} (+{len(internal_links)} links)")
    return internal_links, cleaned_text


# ---------- BFS by link hops (testable core) ----------


async def bfs_crawl_same_site(
    start_url: str,
    *,
    link_hop_limit: int,
    max_urls: int,
    batch_size: int,
    fetch_one: FetchOne,
) -> str:
    """
    Same-domain BFS using Crawl4AI-style fetch_one(url) -> (internal_links, text).

    link_hop_limit:
      0 = only the seed URL (no following links).
      N = follow same-domain links up to N hops from the seed (BFS layers).

    max_urls: hard cap on distinct URLs visited (safety).

    Each unique URL is visited at most once; crawl stops when the queue is empty
    or hop limit / max_urls is reached.
    """
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {start_url}")
    base_domain = (parsed.hostname or "").lower()
    if not base_domain:
        raise ValueError(f"Invalid URL: missing host: {start_url}")

    normalized_start = normalize_url(start_url)
    to_visit: deque[tuple[str, int]] = deque([(normalized_start, 0)])
    visited: set[str] = set()
    content_hashes: set[str] = set()
    texts: list[str] = []
    pages_fetched = 0

    print(f"🚀 Crawl: {start_url} (domain: {base_domain}, hops≤{link_hop_limit}, max_urls={max_urls})")

    while to_visit and len(visited) < max_urls:
        batch: list[tuple[str, int]] = []
        while to_visit and len(batch) < batch_size and len(visited) < max_urls:
            u, depth = to_visit.popleft()
            if u in visited:
                continue
            if pages_fetched > 0 and should_skip_url(u):
                visited.add(u)
                continue
            visited.add(u)
            pages_fetched += 1
            print(f"[{len(visited)}/{max_urls}] Depth {depth} → {u}")
            batch.append((u, depth))

        if not batch:
            break

        tasks = [fetch_one(u) for (u, _) in batch]
        results = await asyncio.gather(*tasks)

        for (u, depth), (links, text) in zip(batch, results):
            if text:
                h = hashlib.md5(text.encode("utf-8")).hexdigest()
                if h not in content_hashes:
                    content_hashes.add(h)
                    texts.append(text)

            next_depth = depth + 1
            if next_depth <= link_hop_limit and links:
                for link in links:
                    if link not in visited:
                        to_visit.append((link, next_depth))

    print(f"📊 Done: {len(visited)} visited, {len(texts)} pages contributed to context.")
    return "\n\n".join(texts)


async def _crawl_with_crawl4ai(
    start_url: str,
    *,
    link_hop_limit: int,
    max_urls: int,
    batch_size: int = 5,
) -> str:
    async with AsyncWebCrawler() as crawler:
        base_domain = (urlparse(start_url).hostname or "").lower()

        async def fetch_one(u: str) -> tuple[list[str], str]:
            return await _fetch_and_extract(crawler, u, base_domain)

        return await bfs_crawl_same_site(
            start_url,
            link_hop_limit=link_hop_limit,
            max_urls=max_urls,
            batch_size=batch_size,
            fetch_one=fetch_one,
        )


def crawl_site(
    url: str,
    *,
    link_hop_limit: int,
    max_urls: int,
    batch_size: int = 5,
) -> str:
    """
    Sync entry: Playwright-backed crawl for all hop levels (including 0 = single URL).
    """
    return asyncio.run(
        _crawl_with_crawl4ai(
            url,
            link_hop_limit=link_hop_limit,
            max_urls=max_urls,
            batch_size=batch_size,
        )
    )


# ---------- Back-compat alias (internal / tests) ----------
def crawl_full_site(url: str, max_pages: int = 50, max_depth: int = 3, batch_size: int = 5) -> str:
    """Deprecated: use crawl_site(link_hop_limit=..., max_urls=...)."""
    return crawl_site(url, link_hop_limit=max_depth, max_urls=max_pages, batch_size=batch_size)


if __name__ == "__main__":
    import json
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    try:
        req = json.loads(raw)
        u = req.get("url")
        if not u:
            raise ValueError("Missing 'url'")
        hops = int(req.get("linkHopLimit", req.get("maxDepth", 0)))
        cap = int(req.get("maxUrls", 500))
        ctx = crawl_site(u, link_hop_limit=hops, max_urls=cap)
        print(json.dumps({"success": True, "context": ctx}))
    except Exception as e:
        print(json.dumps({"success": False, "context": "", "error": str(e)}))
