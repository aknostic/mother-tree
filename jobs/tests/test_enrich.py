"""Tests for URL link-following in enrich.py."""
import pytest

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


import threading
from unittest.mock import MagicMock, patch

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
            fetch_and_follow("https://example.com/page", budget)

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
        assert "---" in result, "Expected followed content separator"
