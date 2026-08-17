import pytest

from multi_page.multiple_page_scrapper import bfs_crawl_same_site, normalize_url


@pytest.mark.asyncio
async def test_link_hop_zero_only_fetches_seed():
    calls: list[str] = []

    async def fetch_one(url: str) -> tuple[list[str], str]:
        calls.append(url)
        return (["https://ex.com/child"], "only-seed")

    root = normalize_url("https://ex.com/")
    out = await bfs_crawl_same_site(
        root,
        link_hop_limit=0,
        max_urls=50,
        batch_size=5,
        fetch_one=fetch_one,
    )
    assert out.context == "only-seed"
    assert out.pages == [{"url": root, "hop": 0}]
    assert calls == [root]


@pytest.mark.asyncio
async def test_bfs_respects_max_urls():
    async def fetch_one(url: str) -> tuple[list[str], str]:
        n = int(url.rstrip("/").split("/")[-1] or "0")
        nxt = f"https://ex.com/{n + 1}"
        return ([nxt], f"p{n}")

    out = await bfs_crawl_same_site(
        "https://ex.com/0",
        link_hop_limit=10,
        max_urls=3,
        batch_size=1,
        fetch_one=fetch_one,
    )
    parts = [p for p in out.context.split("\n\n") if p]
    assert len(parts) <= 3
    assert 1 <= len(out.pages) <= 3
    assert out.pages[0]["hop"] == 0


@pytest.mark.asyncio
async def test_bfs_two_hops_linear_graph():
    root = normalize_url("https://a.com/")
    b = normalize_url("/b", root)
    c = normalize_url("/c", root)
    graph: dict[str, tuple[list[str], str]] = {
        root: ([b], "A"),
        b: ([c], "B"),
        c: ([], "C"),
    }

    async def fetch_one(url: str) -> tuple[list[str], str]:
        return graph.get(url, ([], ""))

    out1 = await bfs_crawl_same_site(
        root,
        link_hop_limit=1,
        max_urls=20,
        batch_size=5,
        fetch_one=fetch_one,
    )
    assert "A" in out1.context and "B" in out1.context
    assert "C" not in out1.context
    assert out1.pages == [{"url": root, "hop": 0}, {"url": b, "hop": 1}]

    out2 = await bfs_crawl_same_site(
        root,
        link_hop_limit=2,
        max_urls=20,
        batch_size=5,
        fetch_one=fetch_one,
    )
    assert "C" in out2.context
    assert out2.pages == [
        {"url": root, "hop": 0},
        {"url": b, "hop": 1},
        {"url": c, "hop": 2},
    ]
