"""Matrix runner: calls handle_request from main (sync). UTF-8 for Windows console."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Crawler package root (parent of scripts/)
_CRAWLER_ROOT = Path(__file__).resolve().parent.parent
if str(_CRAWLER_ROOT) not in sys.path:
    sys.path.insert(0, str(_CRAWLER_ROOT))

os.environ.setdefault("PYTHONUTF8", "1")

from main import handle_request  # noqa: E402

CASES: list[tuple[str, str, int, int]] = [
    ("aicg_h0", "https://aiconsultinggroup.com.au/", 0, 5),
    ("aicg_h1", "https://aiconsultinggroup.com.au/", 1, 10),
    ("aicg_h2", "https://aiconsultinggroup.com.au/", 2, 15),
    ("mon_h0", "https://monastic.edu.np/", 0, 5),
    ("mon_h1", "https://monastic.edu.np/", 1, 12),
    ("mon_h2", "https://monastic.edu.np/", 2, 18),
]


def main() -> None:
    for name, url, hops, cap in CASES:
        data = handle_request({"url": url, "linkHopLimit": hops, "maxUrls": cap})
        ctx = data.get("context") or ""
        preview = (ctx[:240].replace("\n", " ") + "…") if len(ctx) > 240 else ctx.replace("\n", " ")
        row = {
            "case": name,
            "url": url,
            "linkHopLimit": hops,
            "maxUrls": cap,
            "success": data.get("success"),
            "context_chars": len(ctx),
            "error": data.get("error"),
            "preview": preview if data.get("success") else None,
        }
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
