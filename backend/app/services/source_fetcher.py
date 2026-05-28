import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urldefrag, urlencode, urljoin, urlparse

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.core.config import get_settings

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_MARKET_MODE = "finnhub_market_news"
FINNHUB_COMPANY_MODE = "finnhub_company_news"
FINNHUB_ECONOMIC_MODE = "finnhub_economic_calendar"
FINNHUB_FETCH_MODES = {FINNHUB_MARKET_MODE, FINNHUB_COMPANY_MODE, FINNHUB_ECONOMIC_MODE}


@dataclass(frozen=True)
class FetchCandidate:
    title: str
    url: str
    published_at: str | None = None
    snippet: str | None = None
    status: str = "ok"
    error: str | None = None


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ARTICLE_DATE_RE = re.compile(r"(?:/|-)20\d{2}[-/]\d{2}[-/]\d{2}(?:/|-|$)")
ARTICLE_PATH_RE = re.compile(r"/(?:news|article|articles|story|stories|features?)(?:/|$)")
ARTICLE_TEXT_RE = re.compile(r"\b(news|market|stocks?|fed|rates?|inflation|earnings|shares?)\b")
STATIC_EXTENSION_RE = re.compile(r"\.(?:css|js|json|png|jpe?g|gif|svg|ico|webp|mp4|mp3|zip)$")

NAV_TEXT_PATTERNS = (
    "skip to content",
    "company & its products",
    "demo request",
    "remote login",
    "customer support",
    "software updates",
    "manage products",
    "inclusion at",
    "tech at",
    "philanthropy",
    "subscribe",
    "sign in",
    "log in",
    "login",
    "search",
    "privacy",
    "terms",
    "cookies",
    "ad choices",
    "careers",
    "about us",
    "contact us",
    "help center",
)

NAV_PATH_PATTERNS = (
    "/account",
    "/billing",
    "/careers",
    "/company",
    "/contact",
    "/customer-support",
    "/help",
    "/login",
    "/notices",
    "/professional",
    "/settings",
    "/signin",
    "/sign-in",
    "/subscribe",
    "/subscriptions",
    "/terms",
    "/tos",
    "/privacy",
)

NON_ARTICLE_TEXT_PATTERNS = (
    "listen (",
    "newsletter:",
    "podcast:",
    "video:",
)

NON_ARTICLE_PATH_PATTERNS = (
    "/audio",
    "/live",
    "/news/newsletters",
    "/news/videos",
    "/podcasts",
    "/video",
    "/videos",
)


def test_fetch(
    entry_url: str,
    fetch_mode: str,
    selectors: dict | None = None,
) -> list[FetchCandidate]:
    selectors = selectors or {}
    try:
        if fetch_mode in FINNHUB_FETCH_MODES:
            return _fetch_finnhub(entry_url, fetch_mode, selectors)
        if fetch_mode == "rss":
            return _fetch_rss(entry_url)
        if fetch_mode in {"article", "pdf"}:
            return [_fetch_article(entry_url)]
        return _fetch_list_page(entry_url, selectors)
    except httpx.HTTPStatusError as exc:
        message = f"Fetch failed: HTTP {exc.response.status_code} for {entry_url}."
        if exc.response.status_code in {401, 403, 429}:
            message += (
                " The site may block automated requests; try RSS mode, article mode, "
                "or a source-specific selector."
            )
        return [
            FetchCandidate(
                title="Fetch failed",
                url=entry_url,
                snippet=message,
                status="failed",
                error=message,
            )
        ]
    except httpx.HTTPError as exc:
        message = f"Fetch failed: {exc}"
        return [
            FetchCandidate(
                title="Fetch failed",
                url=entry_url,
                snippet=message,
                status="failed",
                error=message,
            )
        ]


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
        return [
            FetchCandidate(
                title="RSS fetch failed",
                url=url,
                status="failed",
                error=str(parsed.bozo_exception),
            )
        ]
    return candidates


def _fetch_list_page(url: str, selectors: dict) -> list[FetchCandidate]:
    settings = get_settings()
    with httpx.Client(timeout=settings.fetch_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url, headers=REQUEST_HEADERS)
        response.raise_for_status()
    return _extract_list_candidates(response.text, url, selectors)


def _extract_list_candidates(html: str, url: str, selectors: dict) -> list[FetchCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    link_selector = selectors.get("list_item_selector") or "a"
    custom_selector = bool(selectors.get("list_item_selector"))
    scored_candidates: list[tuple[int, int, FetchCandidate]] = []
    seen: set[str] = set()

    for index, anchor in enumerate(soup.select(link_selector)):
        href = anchor.get("href")
        title = _candidate_title(anchor)
        if not href or not title or len(title) < 8:
            continue
        absolute_url = _normalize_url(url, href)
        if not absolute_url or not _is_candidate_link(title, absolute_url):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        score = _candidate_score(anchor, title, absolute_url)
        if score < (1 if custom_selector else 2):
            continue
        scored_candidates.append(
            (score, index, FetchCandidate(title=title[:240], url=absolute_url))
        )

    scored_candidates.sort(key=lambda item: (-item[0], item[1]))
    candidates = [candidate for _, _, candidate in scored_candidates[:30]]
    if not candidates:
        message = (
            "No article-like links found in the static HTML. Try RSS/article mode or set "
            "list_item_selector for this source."
        )
        return [
            FetchCandidate(
                title="No article candidates found",
                url=url,
                snippet=message,
                status="failed",
                error=message,
            )
        ]
    return candidates


def _fetch_article(url: str) -> FetchCandidate:
    settings = get_settings()
    with httpx.Client(timeout=settings.fetch_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url, headers=REQUEST_HEADERS)
        response.raise_for_status()

    extracted = (
        trafilatura.extract(response.text, include_comments=False, include_tables=False) or ""
    )
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else url
    snippet = extracted[:500] if extracted else soup.get_text(" ", strip=True)[:500]
    return FetchCandidate(title=title[:240], url=url, snippet=snippet)


def _fetch_finnhub(entry_url: str, fetch_mode: str, selectors: dict) -> list[FetchCandidate]:
    settings = get_settings()
    if not settings.finnhub_api_key:
        message = "FINNHUB_API_KEY is not configured."
        return [
            FetchCandidate(
                title="Finnhub key missing",
                url=entry_url,
                status="failed",
                error=message,
            )
        ]

    query = _entry_query(entry_url)
    with httpx.Client(
        base_url=FINNHUB_BASE_URL,
        timeout=settings.fetch_timeout_seconds,
        headers={"X-Finnhub-Token": settings.finnhub_api_key},
    ) as client:
        if fetch_mode == FINNHUB_MARKET_MODE:
            return _fetch_finnhub_market_news(client, entry_url, selectors, query)
        if fetch_mode == FINNHUB_COMPANY_MODE:
            return _fetch_finnhub_company_news(client, entry_url, selectors, query)
        if fetch_mode == FINNHUB_ECONOMIC_MODE:
            return _fetch_finnhub_economic_calendar(client, entry_url, selectors, query)
    return []


def _fetch_finnhub_market_news(
    client: httpx.Client,
    entry_url: str,
    selectors: dict,
    query: dict[str, str],
) -> list[FetchCandidate]:
    category = (
        str(selectors.get("category") or query.get("category") or "").strip()
        or _plain_entry_value(entry_url)
        or "general"
    )
    response = client.get("/news", params={"category": category})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return _finnhub_payload_error(entry_url, payload)
    return _finnhub_news_candidates(payload, category=category, limit=_result_limit(selectors))


def _fetch_finnhub_company_news(
    client: httpx.Client,
    entry_url: str,
    selectors: dict,
    query: dict[str, str],
) -> list[FetchCandidate]:
    symbols = _symbol_list(selectors, query, entry_url)
    if not symbols:
        message = "Finnhub company-news requires one or more symbols, for example: AAPL,NVDA."
        return [
            FetchCandidate(
                title="Finnhub symbols missing",
                url=entry_url,
                status="failed",
                error=message,
            )
        ]

    start, end = _date_range(selectors, query, default_lookback_days=7, default_lookahead_days=0)
    limit = _result_limit(selectors)
    candidates: list[FetchCandidate] = []
    for symbol in symbols:
        response = client.get(
            "/company-news",
            params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            candidates.extend(_finnhub_news_candidates(payload, symbol=symbol, limit=limit))
        if len(candidates) >= limit:
            break
    return candidates[:limit]


def _fetch_finnhub_economic_calendar(
    client: httpx.Client,
    entry_url: str,
    selectors: dict,
    query: dict[str, str],
) -> list[FetchCandidate]:
    start, end = _date_range(selectors, query, default_lookback_days=7, default_lookahead_days=14)
    response = client.get(
        "/calendar/economic",
        params={"from": start.isoformat(), "to": end.isoformat()},
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("economicCalendar") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return _finnhub_payload_error(entry_url, payload)

    candidates: list[FetchCandidate] = []
    for item in items[: _result_limit(selectors)]:
        event = str(item.get("event") or "").strip()
        if not event:
            continue
        country = str(item.get("country") or "Global").strip()
        when = _finnhub_calendar_time(item.get("time"))
        title = f"{country}: {event}"
        snippet = _economic_calendar_snippet(item)
        event_id = urlencode({"time": when or "", "country": country, "event": event})
        candidates.append(
            FetchCandidate(
                title=title[:240],
                url=f"finnhub://economic-calendar?{event_id}",
                published_at=when,
                snippet=snippet,
            )
        )
    return candidates


def _finnhub_news_candidates(
    payload: list[dict],
    *,
    category: str | None = None,
    symbol: str | None = None,
    limit: int,
) -> list[FetchCandidate]:
    candidates: list[FetchCandidate] = []
    for item in payload[:limit]:
        title = str(item.get("headline") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        source = str(item.get("source") or "Finnhub").strip()
        topic = symbol or category
        prefix = f"{source}"
        if topic:
            prefix = f"{prefix} / {topic}"
        summary = str(item.get("summary") or "").strip()
        snippet = f"{prefix}: {summary}" if summary else prefix
        candidates.append(
            FetchCandidate(
                title=title[:240],
                url=url,
                published_at=_finnhub_news_time(item.get("datetime")),
                snippet=snippet[:500],
            )
        )
    return candidates


def _entry_query(entry_url: str) -> dict[str, str]:
    parsed = urlparse(entry_url)
    return {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}


def _plain_entry_value(entry_url: str) -> str:
    value = entry_url.strip()
    if not value or "://" in value or "=" in value:
        return ""
    return value


def _symbol_list(selectors: dict, query: dict[str, str], entry_url: str) -> list[str]:
    raw_symbols = (
        selectors.get("symbols")
        or selectors.get("symbol")
        or query.get("symbols")
        or query.get("symbol")
    )
    if isinstance(raw_symbols, str):
        values = raw_symbols.split(",")
    elif isinstance(raw_symbols, list):
        values = [str(item) for item in raw_symbols]
    else:
        values = _plain_entry_value(entry_url).split(",")
    return [value.strip().upper() for value in values if value.strip()][:20]


def _date_range(
    selectors: dict,
    query: dict[str, str],
    *,
    default_lookback_days: int,
    default_lookahead_days: int,
) -> tuple[date, date]:
    today = date.today()
    lookback_days = _int_option(
        selectors.get("lookback_days") or query.get("lookback_days"),
        default_lookback_days,
    )
    lookahead_days = _int_option(
        selectors.get("lookahead_days") or query.get("lookahead_days"),
        default_lookahead_days,
    )
    start = _date_option(selectors.get("from") or query.get("from")) or today - timedelta(
        days=lookback_days,
    )
    end = _date_option(selectors.get("to") or query.get("to")) or today + timedelta(
        days=lookahead_days,
    )
    return start, end


def _result_limit(selectors: dict) -> int:
    return max(1, min(_int_option(selectors.get("limit"), 30), 100))


def _int_option(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _date_option(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finnhub_news_time(value: object) -> str | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _finnhub_calendar_time(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _economic_calendar_snippet(item: dict) -> str:
    parts = []
    for label, key in (
        ("time", "time"),
        ("impact", "impact"),
        ("actual", "actual"),
        ("estimate", "estimate"),
        ("previous", "prev"),
        ("unit", "unit"),
    ):
        value = item.get(key)
        if value not in {None, ""}:
            parts.append(f"{label}: {value}")
    return "; ".join(parts)


def _finnhub_payload_error(entry_url: str, payload: object) -> list[FetchCandidate]:
    message = f"Unexpected Finnhub response shape: {payload!r}"[:500]
    return [
        FetchCandidate(
            title="Finnhub fetch failed",
            url=entry_url,
            status="failed",
            error=message,
        )
    ]


def _candidate_title(anchor) -> str:
    title = " ".join(anchor.get_text(" ", strip=True).split())
    if not title:
        title = (anchor.get("aria-label") or anchor.get("title") or "").strip()
    title = re.sub(r"^(Earlier|Latest)\s+", "", title)
    return title


def _normalize_url(base_url: str, href: str) -> str | None:
    parsed_href = urlparse(href)
    if parsed_href.scheme and parsed_href.scheme not in {"http", "https"}:
        return None
    absolute_url = urldefrag(urljoin(base_url, href))[0]
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if STATIC_EXTENSION_RE.search(parsed.path.lower()):
        return None
    return absolute_url


def _is_candidate_link(title: str, absolute_url: str) -> bool:
    title_lower = title.lower()
    if any(pattern in title_lower for pattern in NAV_TEXT_PATTERNS):
        return False
    if any(pattern in title_lower for pattern in NON_ARTICLE_TEXT_PATTERNS):
        return False
    if "getty images" in title_lower and "/" in title:
        return False
    if " for bloomberg" in title_lower and len(title.split()) <= 6:
        return False

    parsed = urlparse(absolute_url)
    path = parsed.path.lower().rstrip("/")
    if any(path.startswith(pattern) for pattern in NAV_PATH_PATTERNS):
        return False
    if any(pattern in path for pattern in NON_ARTICLE_PATH_PATTERNS):
        return False
    if path in {"", "/"}:
        return False

    words = [word for word in re.split(r"\s+", title) if word]
    if len(words) <= 2 and not ARTICLE_DATE_RE.search(path):
        return False
    return True


def _candidate_score(anchor, title: str, absolute_url: str) -> int:
    parsed = urlparse(absolute_url)
    path = parsed.path.lower()
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    title_lower = title.lower()

    score = 0
    if ARTICLE_DATE_RE.search(path):
        score += 4
    if ARTICLE_PATH_RE.search(path):
        score += 3
    if "-" in slug and len(slug) >= 18:
        score += 2
    if len(title) >= 24 and len(title.split()) >= 4:
        score += 1
    if ARTICLE_TEXT_RE.search(title_lower):
        score += 1

    parent = anchor
    for _ in range(5):
        parent = parent.parent
        if not parent:
            break
        if getattr(parent, "name", None) == "article":
            score += 3
            break
        class_text = " ".join(parent.get("class", [])) if hasattr(parent, "get") else ""
        marker = f"{parent.get('id', '')} {class_text}".lower() if hasattr(parent, "get") else ""
        if any(word in marker for word in ("article", "story", "headline", "card", "news")):
            score += 1
            break

    if path.count("/") <= 1 and not ARTICLE_DATE_RE.search(path):
        score -= 2
    return score
