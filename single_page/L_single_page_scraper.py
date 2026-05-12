"""
Single Page Web Scraper
-----------------------
scrape_single_page(url) -> cleaned text

- Fetches a single URL (HTTP/2 when available; falls back to HTTP/1.1)
- Removes <script>/<style>, code samples (<pre>/<code>), and common non-content sections
- Extracts headings, paragraphs, list items, quotes, table cells, captions
- Normalizes whitespace and returns a single text string

CLI (local test):
    python single_page_scraper.py https://example.com

Dependencies:
    pip install "httpx[http2]" selectolax
"""

from __future__ import annotations
import re
from typing import Iterable
import json
import httpx
from selectolax.parser import HTMLParser

# ---------- Public API ----------


def scrape_single_page(
    url: str,
    *,
    timeout: float = 8.0,
    include_meta: bool = True,
    max_chars: int = 60_000,
    user_agent: str = "GPTA-ContextScraper/1.0"
) -> str:
    """
    Scrape and clean readable text from a single web page.

    Raises:
        httpx.HTTPError on network/HTTP issues
        ValueError if no extractable content is found
    """
    html = _fetch_html(url, timeout=timeout, user_agent=user_agent)
    text = _extract_context(
        html, include_meta=include_meta, max_chars=max_chars)
    if not text:
        raise ValueError("No extractable content found.")
    return text


# ---------- Internals ----------

_TEXT_TAGS = {"p", "li", "blockquote", "figcaption", "td", "th"}
_HEADING_TAGS = {"h1", "h2", "h3"}
# Containers we usually don't want in context
_DROP_TAGS = {"nav", "footer", "noscript",
              "form", "iframe", "header", "svg", "aside"}

_WS_RE = re.compile(r"[ \t\u00A0]+")
_NL_RE = re.compile(r"\n{3,}")


def _fetch_html(url: str, *, timeout: float, user_agent: str) -> str:
    """Try HTTP/2 first; fall back to HTTP/1.1 seamlessly."""
    headers = {"User-Agent": user_agent}
    to = httpx.Timeout(connect=3.0, read=timeout, write=3.0, pool=3.0)
    try:
        with httpx.Client(headers=headers, timeout=to, follow_redirects=True, http2=True) as c:
            r = c.get(url)
    except Exception:
        with httpx.Client(headers=headers, timeout=to, follow_redirects=True, http2=False) as c:
            r = c.get(url)
    r.raise_for_status()
    return r.text


def _clean_text(s: str) -> str:
    s = _WS_RE.sub(" ", s)
    s = re.sub(r"(?m)^[ \t]+", "", s)  # trim leading spaces per line
    s = _NL_RE.sub("\n\n", s)          # collapse 3+ blank lines
    return s.strip()


def _iter_text_nodes(root) -> Iterable[str]:
    # Yield text blocks in DOM order
    for node in root.traverse():
        if node.tag in _HEADING_TAGS:
            t = (node.text() or "").strip()
            if t:
                yield t
        elif node.tag in _TEXT_TAGS:
            # Use text() to get text content
            t = (node.text() or "").strip()
            if t and len(t) > 2:
                yield t
        elif node.tag in _TEXT_TAGS:
            # Use text() to get text content
            t = (node.text() or "").strip()
            if t and len(t) > 2:
                yield t
        elif node.tag in _TEXT_TAGS:
            # Use text() to get text content
            t = (node.text() or "").strip()
            if t and len(t) > 2:
                yield t


def _extract_context(html: str, *, include_meta: bool, max_chars: int) -> str:
    tree = HTMLParser(html)

    # Remove obvious non-content
    for n in list(tree.css("script, style")):
        n.decompose()
    # Remove code samples entirely (docs/blogs often have big blocks)
    for n in list(tree.css("pre, code")):
        n.decompose()
    # Remove common layout/boilerplate sections
    for tag in _DROP_TAGS:
        for n in list(tree.css(tag)):
            n.decompose()

    parts: list[str] = []

    # Optional: title + meta description at top
    if include_meta:
        title = tree.css_first("title")
        if title and (title_text := (title.text() or "").strip()):
            parts.append(title_text)
        mdesc = tree.css_first('meta[name="description"]')
        if mdesc and mdesc.attributes.get("content"):
            content = mdesc.attributes["content"]
            if content:
                parts.append(str(content).strip())


    # Prefer article/main; fall back to body
    root = tree.css_first("article") or tree.css_first("main") or tree.body
    if not root:
        return ""

    parts.extend(_iter_text_nodes(root))

    context = _clean_text("\n".join(parts))

    if max_chars and len(context) > max_chars:
        context = context[:max_chars].rsplit("\n", 1)[0] + "\n…"

    return context


# ---------- Minimal CLI for local testing ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python single_page_scraper.py <url>")
        sys.exit(2)
    url = sys.argv[1]
    try:
        ctx = scrape_single_page(url)
        print(json.dumps(
            {"success": True, "context": ctx}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)
