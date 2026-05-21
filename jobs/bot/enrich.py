"""URL extraction and fetching utilities."""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import httpx

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
                follow_timeout = int(timeout)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(
                        lambda u: fetch_url_context(u, timeout=follow_timeout),
                        links_to_fetch,
                    ))
                for link, content in zip(links_to_fetch, results, strict=False):
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


def extract_urls(text: str) -> list[str]:
    """Extract URLs from message text. Slack wraps them in <url|label> or <url>."""
    urls = re.findall(r'<(https?://[^|>]+)', text)
    if not urls:
        urls = re.findall(r'https?://[^\s>]+', text)
    return urls


def fetch_url_context(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and return text content. Skip LinkedIn and other unfetchable sites."""
    if "linkedin.com" in url:
        # Extract what we can from the URL structure
        parts = url.rstrip("/").split("/")
        if "/in/" in url:
            slug = parts[-1] if parts else ""
            return f"[LinkedIn profile: {slug.replace('-', ' ')}]"
        if "/company/" in url:
            slug = parts[-1] if parts else ""
            return f"[LinkedIn company page: {slug.replace('-', ' ')}]"
        return f"[LinkedIn URL: {url}]"

    try:
        from bs4 import BeautifulSoup
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        if not article:
            return None
        text = article.get_text(separator="\n", strip=True)
        if len(text) < 50:
            return None
        return text[:3000]  # limit context size
    except Exception:
        return None
