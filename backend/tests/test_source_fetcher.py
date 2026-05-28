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
      <a href="/news/videos/2026-05-28/sk-hynix-joins-1-trillion-club-video">
        1:01 Video: SK Hynix Joins $1 Trillion Club Amid AI Frenzy
      </a>
      <a href="/news/newsletters/2026-05-28/economics-daily-fed-preview">
        Newsletter: Economics Daily How Markets Read the Fed
      </a>
      <a href="/news/articles/2026-05-28/china-crop-belt-faces-flood-risk">
        Zhang Chang/China News Service/VCG/Getty Images
      </a>
      <a href="/news/articles/2026-05-28/china-crop-belt-faces-flood-risk">
        China Crop Belt Faces Flood Risk as Heavy Rains Arrive Early
      </a>
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
        "China Crop Belt Faces Flood Risk as Heavy Rains Arrive Early",
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
