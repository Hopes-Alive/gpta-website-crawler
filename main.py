# main.py
import json
import asyncio
import sys
import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
import logging
import socket
import ipaddress
from fastapi import FastAPI, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
import uvicorn

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("web-scraper")
logger.setLevel(logging.DEBUG)

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass

from multi_page.multiple_page_scrapper import crawl_site


def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in d.items()}


def _coerce_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _validate_url(url: Any) -> Tuple[bool, str]:
    if not isinstance(url, str) or not url.strip():
        return False, "Missing URL"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "Invalid URL (must start with http(s) and include host)"
    if parsed.port and parsed.port not in {80, 443}:
        return False, "Port not allowed"
    host = parsed.hostname or ""
    if not _host_is_public(host):
        return False, "URL must point to a public internet host"
    return True, ""


def _host_is_public(host: str) -> bool:
    if not host:
        return False
    h = host.lower().strip()
    if h in {"localhost"} or h.endswith(".local"):
        return False
    if h in {"169.254.169.254"}:
        return False
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_global
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(h, None)
    except Exception:
        return False
    for _, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        if not ip.is_global:
            return False
    return True


DEFAULT_MAX_URLS_ENV = "WEBSITE_SCRAPE_MAX_URLS"


def _default_max_urls() -> int:
    return max(1, min(_coerce_int(os.getenv(DEFAULT_MAX_URLS_ENV, "1500"), 1500), 5000))


def _clamp_link_hop_limit(v: Any) -> int:
    n = _coerce_int(v, 0)
    return max(0, min(n, 20))


def _clamp_max_urls(v: Any, fallback: int) -> int:
    n = _coerce_int(v, fallback)
    return max(1, min(n, 5000))


_LOG_W = 64


def _log_sep(char: str = "─") -> None:
    logger.info(char * _LOG_W)


def _log_banner(title: str, char: str = "═") -> None:
    logger.info(char * _LOG_W)
    logger.info("  %s", title)
    logger.info(char * _LOG_W)


def _log_field(label: str, value: object) -> None:
    logger.info("    %-18s%s", label, value)


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input:
      {"url": "https://example.com", "linkHopLimit": 2, "maxUrls": 500}

    linkHopLimit: 0 = seed URL only; N = follow same-domain links up to N hops (BFS).

    Output:
      {"success": bool, "context": "...", "error": "...optional"}
    """
    try:
        if not isinstance(req, dict):
            return {"success": False, "context": "", "error": "Invalid request type"}

        data = _lower_keys(req)
        url = data.get("url") or data.get("u")
        ok, err = _validate_url(url)
        if not ok:
            _log_banner("❌  SCRAPE REQUEST — REJECTED")
            _log_field("Reason", err)
            _log_field("URL", url)
            _log_sep()
            return {"success": False, "context": "", "error": err}

        link_hop_limit = _clamp_link_hop_limit(data.get("linkhoplimit", data.get("link_hop_limit")))
        max_urls = _clamp_max_urls(data.get("maxurls"), _default_max_urls())

        _log_banner("📥  SCRAPE REQUEST RECEIVED")
        _log_field("URL", url)
        _log_field("linkHopLimit", link_hop_limit)
        _log_field("maxUrls", max_urls)
        _log_sep()

        start_time = time.time()
        context = crawl_site(str(url), link_hop_limit=link_hop_limit, max_urls=max_urls)
        elapsed = time.time() - start_time

        if not isinstance(context, str):
            context = "" if context is None else str(context)

        if not context.strip():
            _log_banner("⚠️   SCRAPE COMPLETE — NO CONTENT")
            _log_field("URL", url)
            _log_field("Elapsed", f"{elapsed:.2f}s")
            _log_sep()
            return {"success": False, "context": "", "error": "No extractable content from crawl"}

        _log_banner("✅  SCRAPE COMPLETE")
        _log_field("URL", url)
        _log_field("Context size", f"{len(context):,} chars")
        _log_field("Elapsed", f"{elapsed:.2f}s")
        _log_sep()
        return {"success": True, "context": context}

    except Exception as e:
        logger.exception("Unhandled error in handle_request")
        return {"success": False, "context": "", "error": f"Internal error: {str(e)}"}


app = FastAPI(title="Web Scraper API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    """Request model used in Swagger (/docs)."""
    url: str = Field(..., description="Must start with http:// or https://")
    linkHopLimit: int = Field(
        0,
        ge=0,
        le=20,
        description="0 = seed page only; N = same-domain BFS up to N link hops from seed.",
    )
    maxUrls: Optional[int] = Field(
        None,
        ge=1,
        le=5000,
        description="Safety cap on pages visited (default from WEBSITE_SCRAPE_MAX_URLS or 1500).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.com/",
                "linkHopLimit": 2,
                "maxUrls": 200,
            }
        }
    )


@app.get("/")
def root():
    return {"status": "ok", "use": "POST /scrape", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scrape", summary="Scrape page or crawl site (Crawl4AI / Playwright)")
async def scrape(
    req_model: Optional[ScrapeRequest] = Body(default=None, description="Preferred JSON body."),
    request: Request = None,
):
    body: Optional[Dict[str, Any]] = None

    if isinstance(req_model, ScrapeRequest):
        body = req_model.model_dump(exclude_none=False)

    if body is None:
        try:
            obj = await request.json()
            if isinstance(obj, dict):
                body = obj
        except Exception as e:
            logger.debug("Raw JSON parsing failed: %s", e)

    if body is None:
        try:
            raw = (await request.body()).decode("utf-8", errors="ignore").strip()
            if raw:
                maybe = json.loads(raw)
                if isinstance(maybe, dict):
                    body = maybe
        except Exception as e:
            logger.debug("Raw body parsing failed: %s", e)

    if body is None:
        try:
            form = await request.form()
            if form:
                body = dict(form)
        except Exception as e:
            logger.debug("Form parsing failed: %s", e)

    if body is None:
        logger.error("No valid request body found")
        return {"success": False, "context": "", "error": "Invalid or missing request body"}

    try:
        resp = await asyncio.to_thread(handle_request, body)
        return resp
    except Exception as e:
        logger.exception("Error in worker thread")
        return {"success": False, "context": "", "error": f"Thread error: {str(e)}"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Web Scraper API / CLI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cli", action="store_true", help="Run once (no server): read JSON from --json or stdin")
    parser.add_argument("--json", help='Payload, e.g. {"url": "https://example.com", "linkHopLimit": 1}')
    args = parser.parse_args()

    if args.cli:
        raw = args.json if args.json else sys.stdin.read()
        try:
            req = json.loads(raw)
        except Exception:
            print(json.dumps({"success": False, "context": "", "error": "Invalid JSON"}))
            sys.exit(1)
        print(json.dumps(handle_request(req), ensure_ascii=False, indent=2))
    else:
        uvicorn.run(app, host=args.host, port=args.port)
