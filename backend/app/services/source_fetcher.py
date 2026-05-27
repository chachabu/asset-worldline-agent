from dataclasses import dataclass
from urllib.parse import urljoin

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.core.config import get_settings


@dataclass(frozen=True)
class FetchCandidate:
    title: str
    url: str
    published_at: str | None = None
    snippet: str | None = None
    status: str = "ok"
    error: str | None = None


def test_fetch(entry_url: str, fetch_mode: str, selectors: dict | None = None) -> list[FetchCandidate]:
    selectors = selectors or {}
    if fetch_mode == "rss":
        return _fetch_rss(entry_url)
    if fetch_mode in {"article", "pdf"}:
        return [_fetch_article(entry_url)]
    return _fetch_list_page(entry_url, selectors)


def _fetch_rss(url: str) -> list[FetchCandidate]:
    parsed = feedparser.parse(url)
    candidates: list[FetchCandidate] = []
    for entry in parsed.entries[:20]:
        candidates.append(
            FetchCandidate(
                title=getattr(entry, "title", "Untitled"),
                url=getattr(entry, "link", url),
                published_at=getattr(entry, "published", None),
                snippet=getattr(entry, "summary", None),
            )
        )
    if not candidates and parsed.bozo_exception:
        return [FetchCandidate(title="RSS fetch failed", url=url, status="failed", error=str(parsed.bozo_exception))]
    return candidates


def _fetch_list_page(url: str, selectors: dict) -> list[FetchCandidate]:
    settings = get_settings()
    with httpx.Client(timeout=settings.fetch_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "asset-worldline-agent/0.1"})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    link_selector = selectors.get("list_item_selector") or "a"
    candidates: list[FetchCandidate] = []
    seen: set[str] = set()
    for anchor in soup.select(link_selector):
        href = anchor.get("href")
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not href or not title or len(title) < 8:
            continue
        absolute_url = urljoin(url, href)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        candidates.append(FetchCandidate(title=title[:240], url=absolute_url))
        if len(candidates) >= 30:
            break
    return candidates


def _fetch_article(url: str) -> FetchCandidate:
    settings = get_settings()
    with httpx.Client(timeout=settings.fetch_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "asset-worldline-agent/0.1"})
        response.raise_for_status()

    extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False) or ""
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else url
    snippet = extracted[:500] if extracted else soup.get_text(" ", strip=True)[:500]
    return FetchCandidate(title=title[:240], url=url, snippet=snippet)

