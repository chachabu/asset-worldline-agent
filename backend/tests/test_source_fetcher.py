from app.services.source_fetcher import _extract_list_candidates


def test_list_page_filters_navigation_links() -> None:
    html = """
    <nav>
      <a href="/">Skip to content</a>
      <a href="/professional">Bloomberg Terminal Demo Request</a>
      <a href="/account/login">Bloomberg Anywhere Remote Login</a>
      <a href="/customer-support">Bloomberg Customer Support Customer Support</a>
      <a href="/software-updates">Software Updates</a>
      <a href="/company/philanthropy">Philanthropy</a>
    </nav>
    <main>
      <article>
        <a href="/news/articles/2026-05-28/nvidia-sales-surge-as-ai-demand-keeps-chip-boom-alive">
          Nvidia Sales Surge as AI Demand Keeps Chip Boom Alive
        </a>
      </article>
      <div class="story-card">
        <a href="/markets/2026/05/28/treasury-yields-rise-after-fed-minutes">
          Treasury Yields Rise After Fed Minutes Signal Caution
        </a>
      </div>
      <a href="/markets">Markets</a>
    </main>
    """

    candidates = _extract_list_candidates(html, "https://www.bloomberg.com/", {})

    titles = [candidate.title for candidate in candidates]
    assert titles == [
        "Nvidia Sales Surge as AI Demand Keeps Chip Boom Alive",
        "Treasury Yields Rise After Fed Minutes Signal Caution",
    ]
    assert all(candidate.status == "ok" for candidate in candidates)


def test_list_page_returns_clear_failure_when_no_articles_exist() -> None:
    html = """
    <nav>
      <a href="/">Skip to content</a>
      <a href="/professional">Bloomberg Terminal Demo Request</a>
      <a href="/customer-support">Bloomberg Customer Support Customer Support</a>
    </nav>
    """

    candidates = _extract_list_candidates(html, "https://www.bloomberg.com/", {})

    assert len(candidates) == 1
    assert candidates[0].status == "failed"
    assert candidates[0].title == "No article candidates found"
