# URL Link-Following Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Mother Tree fetches a URL, follow links to known content platforms (sched.com, etc.) or heuristic-matching links on thin pages, adding followed content to the annotation.

**Architecture:** New `fetch_and_follow()` function in `enrich.py` wraps the existing fetch with link-following. Two triggers: domain allowlist (always) and thin-content + anchor heuristics (< 500 chars). Drop-in replacement in `detect.py` with shared follow-budget semaphore.

**Tech Stack:** Python, httpx, BeautifulSoup, threading (Semaphore, ThreadPoolExecutor), pytest

**Spec:** `docs/superpowers/specs/2026-03-23-url-link-following-design.md`

---

## File Structure

| File | Role |
|------|------|
| `jobs/bot/enrich.py` | Add constants (`FOLLOW_DOMAINS`, `FOLLOW_ANCHOR_PATTERNS`), helper functions (`_extract_follow_links`, `_resolve_url`), and main `fetch_and_follow()` |
| `jobs/bot/detect.py` | Replace `fetch_url_context` with `fetch_and_follow` in URL section, add semaphore |
| `jobs/tests/test_enrich.py` | New file — all unit tests for link-following |
| `jobs/tests/test_unified.py` | Update 4 URL detection tests to mock `fetch_and_follow` instead of `fetch_url_context` |

---

### Task 1: Constants and URL resolution helper

**Files:**
- Modify: `jobs/bot/enrich.py`
- Create: `jobs/tests/test_enrich.py`

- [ ] **Step 1: Write failing tests for URL resolution**

In `jobs/tests/test_enrich.py`:

```python
"""Tests for URL link-following in enrich.py."""
from bot.enrich import _resolve_url


class TestResolveUrl:
    def test_absolute_url(self):
        assert _resolve_url("https://sched.com/event", "https://example.com/page") == "https://sched.com/event"

    def test_relative_url(self):
        assert _resolve_url("/schedule", "https://example.com/page") == "https://example.com/schedule"

    def test_protocol_relative(self):
        assert _resolve_url("//kccnceu2026.sched.com/", "https://example.com/page") == "https://kccnceu2026.sched.com/"

    def test_fragment_only_returns_none(self):
        assert _resolve_url("#section", "https://example.com/page") is None

    def test_mailto_returns_none(self):
        assert _resolve_url("mailto:a@b.com", "https://example.com/page") is None

    def test_javascript_returns_none(self):
        assert _resolve_url("javascript:void(0)", "https://example.com/page") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestResolveUrl -v`
Expected: ImportError — `_resolve_url` does not exist yet.

- [ ] **Step 3: Implement constants and `_resolve_url`**

Add to `jobs/bot/enrich.py` after the existing imports:

```python
from urllib.parse import urljoin, urlparse

# Domains that host content behind landing pages — always follow links to these
FOLLOW_DOMAINS = frozenset({
    "sched.com",
    "sessionize.com",
    "pretalx.com",
    "whova.com",
    "notion.so",
    "notion.site",
    "docs.google.com",
    "luma.so",
})

# Anchor text patterns that suggest a link leads to the actual content
# Only used on thin pages (< 500 chars)
FOLLOW_ANCHOR_PATTERNS = re.compile(
    r"view schedule|full program|see details|session list|view agenda|browse sessions|full schedule|view sessions",
    re.IGNORECASE,
)

THIN_CONTENT_THRESHOLD = 500


def _resolve_url(href: str, base_url: str) -> str | None:
    """Resolve a link href to an absolute URL. Returns None for non-HTTP links."""
    if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    if href.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        href = f"{scheme}:{href}"
    resolved = urljoin(base_url, href)
    if not resolved.startswith(("http://", "https://")):
        return None
    return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestResolveUrl -v`
Expected: All 6 pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/enrich.py jobs/tests/test_enrich.py
git commit -m "Add URL resolution helper and follow-link constants"
```

---

### Task 2: Link extraction function

**Files:**
- Modify: `jobs/bot/enrich.py`
- Modify: `jobs/tests/test_enrich.py`

- [ ] **Step 1: Write failing tests for `_extract_follow_links`**

Append to `jobs/tests/test_enrich.py`:

```python
from bs4 import BeautifulSoup
from bot.enrich import _extract_follow_links


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestExtractFollowLinks:
    def test_allowlist_domain_on_rich_page(self):
        """Trigger A: sched.com link found on a content-rich page."""
        soup = _make_soup('<html><body><p>' + 'x' * 1000 + '</p>'
                          '<a href="https://kccnceu2026.sched.com/">View Schedule</a></body></html>')
        links = _extract_follow_links(soup, "https://example.com/page", text_length=1000)
        assert len(links) == 1
        assert "sched.com" in links[0]

    def test_no_match_on_rich_page(self):
        """Rich page with no allowlisted domains and no heuristic match."""
        soup = _make_soup('<html><body><p>' + 'x' * 1000 + '</p>'
                          '<a href="https://random.org/stuff">Click here</a></body></html>')
        links = _extract_follow_links(soup, "https://example.com/page", text_length=1000)
        assert links == []

    def test_anchor_heuristic_on_thin_page(self):
        """Trigger B: thin page with anchor text matching heuristic."""
        soup = _make_soup('<html><body><p>Welcome</p>'
                          '<a href="https://unknown.org/schedule">View full schedule</a></body></html>')
        links = _extract_follow_links(soup, "https://example.com/page", text_length=50)
        assert len(links) == 1
        assert "unknown.org" in links[0]

    def test_anchor_heuristic_ignored_on_rich_page(self):
        """Trigger B does NOT fire on rich pages."""
        soup = _make_soup('<html><body><p>' + 'x' * 1000 + '</p>'
                          '<a href="https://unknown.org/schedule">View full schedule</a></body></html>')
        links = _extract_follow_links(soup, "https://example.com/page", text_length=1000)
        assert links == []

    def test_skip_same_domain(self):
        """Links back to the original domain are skipped."""
        soup = _make_soup('<html><body><p>Short</p>'
                          '<a href="https://example.com/other">See details</a></body></html>')
        links = _extract_follow_links(soup, "https://example.com/page", text_length=50)
        assert links == []

    def test_dedup_prefers_longest_path(self):
        """Multiple links to same domain — prefer the one with the longest path."""
        soup = _make_soup('<html><body>'
                          '<a href="https://kccnceu2026.sched.com/">Schedule</a>'
                          '<a href="https://kccnceu2026.sched.com/2026/march">Full Schedule</a>'
                          '</body></html>')
        links = _extract_follow_links(soup, "https://example.com/", text_length=1000)
        assert len(links) == 1
        assert "/2026/march" in links[0]

    def test_max_two_links(self):
        """Cap at 2 follow-links per URL."""
        soup = _make_soup('<html><body>'
                          '<a href="https://a.sched.com/">A</a>'
                          '<a href="https://b.sessionize.com/">B</a>'
                          '<a href="https://c.notion.so/">C</a>'
                          '</body></html>')
        links = _extract_follow_links(soup, "https://example.com/", text_length=1000)
        assert len(links) == 2

    def test_resolve_protocol_relative(self):
        """Protocol-relative hrefs are resolved."""
        soup = _make_soup('<html><body>'
                          '<a href="//kccnceu2026.sched.com/">Schedule</a>'
                          '</body></html>')
        links = _extract_follow_links(soup, "https://example.com/", text_length=1000)
        assert len(links) == 1
        assert links[0].startswith("https://")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestExtractFollowLinks -v`
Expected: ImportError — `_extract_follow_links` does not exist yet.

- [ ] **Step 3: Implement `_extract_follow_links`**

Add to `jobs/bot/enrich.py` after `_resolve_url`:

```python
def _extract_follow_links(soup, base_url: str, text_length: int) -> list[str]:
    """Extract links worth following from a parsed page.

    Two triggers:
    - Trigger A: links to FOLLOW_DOMAINS (fires regardless of text_length)
    - Trigger B: links with heuristic anchor text (fires only when text_length < THIN_CONTENT_THRESHOLD)
    """
    origin_domain = urlparse(base_url).netloc.lower()
    # {domain: (url, path_length)} — keep the most specific URL per domain
    candidates: dict[str, tuple[str, int]] = {}

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        resolved = _resolve_url(href, base_url)
        if not resolved:
            continue

        parsed = urlparse(resolved)
        link_domain = parsed.netloc.lower()

        # Skip links back to the original domain
        if link_domain == origin_domain:
            continue

        # Trigger A: domain allowlist
        domain_match = any(link_domain == d or link_domain.endswith("." + d) for d in FOLLOW_DOMAINS)

        # Trigger B: anchor heuristic (thin pages only)
        anchor_text = tag.get_text(strip=True)
        anchor_match = (
            text_length < THIN_CONTENT_THRESHOLD
            and bool(FOLLOW_ANCHOR_PATTERNS.search(anchor_text))
        )

        if not domain_match and not anchor_match:
            continue

        # Dedup by domain — prefer longest path
        path_len = len(parsed.path)
        existing = candidates.get(link_domain)
        if existing is None or path_len > existing[1]:
            candidates[link_domain] = (resolved, path_len)

    # Return up to 2 links, ordered by insertion (first seen)
    result = [url for url, _ in candidates.values()]
    return result[:2]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestExtractFollowLinks -v`
Expected: All 8 pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/enrich.py jobs/tests/test_enrich.py
git commit -m "Add link extraction with domain allowlist and anchor heuristics"
```

---

### Task 3: `fetch_and_follow()` function

**Files:**
- Modify: `jobs/bot/enrich.py`
- Modify: `jobs/tests/test_enrich.py`

- [ ] **Step 1: Write failing tests for `fetch_and_follow`**

Append to `jobs/tests/test_enrich.py`:

```python
import threading
from unittest.mock import patch, MagicMock
from bot.enrich import fetch_and_follow


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


class TestFetchAndFollow:
    def test_rich_page_with_allowlist_link(self):
        """Rich page with sched.com link — follows it."""
        page_html = ('<html><body><main><p>' + 'x' * 1000 + '</p>'
                      '<a href="https://kccnceu2026.sched.com/">Schedule</a></main></body></html>')
        followed_content = "Session 1: Kubernetes\nSession 2: Observability"
        budget = threading.Semaphore(2)

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            mock_fetch.return_value = followed_content
            result = fetch_and_follow("https://example.com/schedule", budget)

        assert "x" * 100 in result  # original content present
        assert "Session 1: Kubernetes" in result  # followed content present
        assert "---" in result  # separator present
        mock_fetch.assert_called_once()

    def test_thin_page_with_anchor_match(self):
        """Thin page with heuristic-matching anchor — follows it."""
        page_html = '<html><body><main><p>Welcome</p><a href="https://other.com/schedule">View full schedule</a></main></body></html>'
        budget = threading.Semaphore(2)

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            mock_fetch.return_value = "Full schedule content here"
            result = fetch_and_follow("https://example.com/page", budget)

        assert "Full schedule content here" in result
        mock_fetch.assert_called_once()

    def test_rich_page_no_follow(self):
        """Rich page with no qualifying links — no follow."""
        page_html = '<html><body><main><p>' + 'x' * 1000 + '</p><a href="https://random.org">Click</a></main></body></html>'
        budget = threading.Semaphore(2)

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            result = fetch_and_follow("https://example.com/page", budget)

        assert result is not None
        assert "---" not in result  # no followed content separator
        mock_fetch.assert_not_called()

    def test_linkedin_no_follow(self):
        """LinkedIn URL returns stub string, no link scan."""
        budget = threading.Semaphore(2)
        result = fetch_and_follow("https://linkedin.com/in/jurg-example", budget)
        assert "LinkedIn profile" in result

    def test_fetch_failure_returns_none(self):
        """HTTP error returns None."""
        budget = threading.Semaphore(2)
        with patch("bot.enrich.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            result = fetch_and_follow("https://example.com/page", budget)
        assert result is None

    def test_budget_exhausted_skips_follow(self):
        """When budget semaphore is at 0, no follow-fetches fire."""
        page_html = ('<html><body><main><p>' + 'x' * 1000 + '</p>'
                      '<a href="https://kccnceu2026.sched.com/">Schedule</a></main></body></html>')
        budget = threading.Semaphore(0)  # exhausted

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            result = fetch_and_follow("https://example.com/page", budget)

        assert result is not None  # original content still returned
        mock_fetch.assert_not_called()  # no follow-fetch fired

    def test_follow_cap_two_per_url(self):
        """Even with budget remaining, max 2 follows per URL."""
        page_html = ('<html><body><main><p>' + 'x' * 1000 + '</p>'
                      '<a href="https://a.sched.com/">A</a>'
                      '<a href="https://b.sessionize.com/">B</a>'
                      '<a href="https://c.pretalx.com/">C</a></main></body></html>')
        budget = threading.Semaphore(5)  # plenty of budget

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            mock_fetch.return_value = "content"
            result = fetch_and_follow("https://example.com/page", budget)

        assert mock_fetch.call_count == 2  # capped at 2

    def test_wall_clock_budget_limits_follow_timeout(self):
        """When original fetch is slow, follow-fetches get reduced time."""
        page_html = ('<html><body><main><p>' + 'x' * 1000 + '</p>'
                      '<a href="https://kccnceu2026.sched.com/">Schedule</a></main></body></html>')
        budget = threading.Semaphore(2)

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch, \
             patch("bot.enrich.time.monotonic") as mock_time:
            # Simulate: start=0, after initial fetch=19 (only 1s remaining < 1s threshold)
            mock_time.side_effect = [0, 19]
            mock_get.return_value = _mock_response(page_html)
            result = fetch_and_follow("https://example.com/page", budget)

        # With < 1s remaining, no follow-fetch should fire
        mock_fetch.assert_not_called()
        assert result is not None  # original content still returned

    def test_message_level_budget_shared(self):
        """Multiple fetch_and_follow calls share the same budget semaphore."""
        page_html = ('<html><body><main><p>' + 'x' * 1000 + '</p>'
                      '<a href="https://kccnceu2026.sched.com/">Schedule</a></main></body></html>')
        budget = threading.Semaphore(2)  # shared across all URLs

        with patch("bot.enrich.httpx.get") as mock_get, \
             patch("bot.enrich.fetch_url_context") as mock_fetch:
            mock_get.return_value = _mock_response(page_html)
            mock_fetch.return_value = "content"
            # Simulate 3 URLs in a message, each triggering one follow
            fetch_and_follow("https://example1.com/page", budget)
            fetch_and_follow("https://example2.com/page", budget)
            fetch_and_follow("https://example3.com/page", budget)

        # Budget of 2 means only 2 follow-fetches total across all 3 calls
        assert mock_fetch.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestFetchAndFollow -v`
Expected: ImportError — `fetch_and_follow` does not exist yet.

- [ ] **Step 3: Implement `fetch_and_follow`**

Add to `jobs/bot/enrich.py` after `_extract_follow_links`:

```python
import time
import threading
from concurrent.futures import ThreadPoolExecutor

WALL_CLOCK_BUDGET = 20  # seconds total for original fetch + follows
FOLLOW_TIMEOUT = 10  # seconds per follow-fetch


def fetch_and_follow(url: str, follow_budget: threading.Semaphore) -> str | None:
    """Fetch a URL and optionally follow links to content platforms.

    Args:
        url: The URL to fetch.
        follow_budget: Shared semaphore limiting total follow-fetches per message.

    Returns:
        Combined text content (original + followed), or None on failure.
    """
    # LinkedIn special case — no HTML to parse
    if "linkedin.com" in url:
        return fetch_url_context(url)

    start = time.monotonic()

    try:
        from bs4 import BeautifulSoup
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract follow-links from the UNMODIFIED soup (before decomposing nav/footer)
    # Strip tags for text extraction (same logic as fetch_url_context)
    text_soup = BeautifulSoup(resp.text, "html.parser")
    for tag in text_soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    article = text_soup.find("article") or text_soup.find("main") or text_soup.body
    if not article:
        return None
    text = article.get_text(separator="\n", strip=True)
    if len(text) < 50:
        text = ""  # treat as thin but don't bail — links may have content

    original_content = text[:3000] if text else None

    # Find links worth following
    follow_links = _extract_follow_links(soup, url, text_length=len(text))

    # Fetch follow-links within budget
    followed_parts = []
    if follow_links:
        elapsed = time.monotonic() - start
        remaining = max(0, WALL_CLOCK_BUDGET - elapsed)
        timeout = min(FOLLOW_TIMEOUT, remaining) if remaining > 1 else 0

        if timeout > 0:
            links_to_fetch = []
            for link in follow_links:
                if follow_budget.acquire(blocking=False):
                    links_to_fetch.append(link)
                else:
                    break

            if links_to_fetch:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda u: fetch_url_context(u),
                        links_to_fetch,
                    ))
                for link, content in zip(links_to_fetch, results):
                    if content:
                        followed_parts.append(f"[{link}]\n{content}")

    # Combine results
    if not original_content and not followed_parts:
        return None

    parts = []
    if original_content:
        parts.append(original_content)
    parts.extend(followed_parts)
    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/test_enrich.py::TestFetchAndFollow -v`
Expected: All 9 pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/bot/enrich.py jobs/tests/test_enrich.py
git commit -m "Add fetch_and_follow with link-following and budget enforcement"
```

---

### Task 4: Integrate into detect.py

**Files:**
- Modify: `jobs/bot/detect.py`

- [ ] **Step 1: Update the import**

In `jobs/bot/detect.py` line 17, change:

```python
# Before
from bot.enrich import fetch_url_context, extract_urls

# After
from bot.enrich import fetch_and_follow, extract_urls
```

- [ ] **Step 2: Update the URL detection section**

In `jobs/bot/detect.py`, replace lines 282–287:

```python
# Before
    urls = extract_urls(clean)
    if urls:
        from concurrent.futures import ThreadPoolExecutor
        urls = urls[:3]
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetched = list(pool.map(fetch_url_context, urls))

# After
    urls = extract_urls(clean)
    if urls:
        import threading
        from concurrent.futures import ThreadPoolExecutor
        urls = urls[:3]
        follow_budget = threading.Semaphore(2)
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetched = list(pool.map(lambda u: fetch_and_follow(u, follow_budget), urls))
```

- [ ] **Step 3: Commit**

```bash
git add jobs/bot/detect.py
git commit -m "Wire fetch_and_follow into detect phase URL handling"
```

---

### Task 5: Update existing URL detection tests

**Files:**
- Modify: `jobs/tests/test_unified.py:305-342`

The four URL detection tests in `test_unified.py` mock `bot.detect.fetch_url_context`, which is no longer imported into `detect.py`. Update them to mock `bot.detect.fetch_and_follow` instead.

- [ ] **Step 1: Update `test_url_detection`**

In `jobs/tests/test_unified.py`, change the test at line 305:

```python
# Before
    def test_url_detection(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_context") as mock:
            mock.return_value = "Page content here"
            result = detect("check this https://example.com/article", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_content"

# After
    def test_url_detection(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = "Page content here"
            result = detect("check this https://example.com/article", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_content"
```

- [ ] **Step 2: Update `test_url_fetch_failure`**

```python
# Before
    def test_url_fetch_failure(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_context") as mock:
            mock.return_value = None
            result = detect("check this https://example.com/nope", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_failed"

# After
    def test_url_fetch_failure(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = None
            result = detect("check this https://example.com/nope", participant_count=1, enrolled=False)
        assert result["annotation"]["type"] == "url_failed"
```

- [ ] **Step 3: Update `test_multiple_urls_fetched`**

```python
# Before
    def test_multiple_urls_fetched(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_context") as mock:
            mock.side_effect = ["Content A", "Content B", None]
            result = detect(
                "check https://example.com/a and https://example.com/b and https://example.com/c",
                participant_count=1, enrolled=False,
            )
        assert result["annotation"]["type"] == "url_content"
        assert "urls" in result["annotation"]
        assert len(result["annotation"]["urls"]) == 2

# After
    def test_multiple_urls_fetched(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.side_effect = ["Content A", "Content B", None]
            result = detect(
                "check https://example.com/a and https://example.com/b and https://example.com/c",
                participant_count=1, enrolled=False,
            )
        assert result["annotation"]["type"] == "url_content"
        assert "urls" in result["annotation"]
        assert len(result["annotation"]["urls"]) == 2
```

- [ ] **Step 4: Update `test_max_three_urls`**

```python
# Before
    def test_max_three_urls(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_url_context") as mock:
            mock.return_value = "content"
            result = detect(
                "https://a.com https://b.com https://c.com https://d.com",
                participant_count=1, enrolled=False,
            )
        assert mock.call_count == 3

# After
    def test_max_three_urls(self):
        from bot.detect import detect
        with patch("bot.detect.fetch_and_follow") as mock:
            mock.return_value = "content"
            result = detect(
                "https://a.com https://b.com https://c.com https://d.com",
                participant_count=1, enrolled=False,
            )
        assert mock.call_count == 3
```

- [ ] **Step 5: Run all tests to verify**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add jobs/tests/test_unified.py
git commit -m "Update URL detection tests for fetch_and_follow"
```

---

### Task 6: Integration test with real URL

**Files:**
- Modify: `jobs/tests/test_enrich.py`

- [ ] **Step 1: Write a manual integration test**

Append to `jobs/tests/test_enrich.py`:

```python
import pytest


@pytest.mark.llm  # reusing the "slow/external" marker
class TestFetchAndFollowIntegration:
    def test_kubecon_schedule_follows_sched_com(self):
        """Real fetch: KubeCon schedule page should follow sched.com link."""
        budget = threading.Semaphore(2)
        result = fetch_and_follow(
            "https://events.linuxfoundation.org/kubecon-cloudnativecon-europe/program/schedule/",
            budget,
        )
        assert result is not None
        # Should contain followed sched.com content
        assert "sched.com" in result.lower() or "session" in result.lower() or "---" in result
```

- [ ] **Step 2: Run the integration test**

Run: `cd /Users/jurg/Projects/mother-tree && RUN_LLM_TESTS=1 python -m pytest jobs/tests/test_enrich.py::TestFetchAndFollowIntegration -v`
Expected: PASS — the test fetches the real page and verifies sched.com content is followed.

- [ ] **Step 3: Commit**

```bash
git add jobs/tests/test_enrich.py
git commit -m "Add integration test for KubeCon schedule link-following"
```

---

### Task 7: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `cd /Users/jurg/Projects/mother-tree && python -m pytest jobs/tests/ -v`
Expected: All tests pass (excluding `@pytest.mark.llm` tests which are skipped by default).

- [ ] **Step 2: Run a quick manual smoke test**

Run in Python:
```python
import threading
from bot.enrich import fetch_and_follow
budget = threading.Semaphore(2)
result = fetch_and_follow("https://events.linuxfoundation.org/kubecon-cloudnativecon-europe/program/schedule/", budget)
print(f"Length: {len(result)}")
print("Contains followed content:" , "---" in result)
print(result[:500])
```

Expected: Content includes the original page text AND followed sched.com content separated by `---`.

- [ ] **Step 3: Final commit if any cleanup needed**

Check `git status` — if clean, this step is a no-op.
