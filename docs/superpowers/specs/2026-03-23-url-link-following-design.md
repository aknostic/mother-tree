# URL Link-Following in Detect Phase

## Problem

When someone shares a URL, Mother Tree fetches the page. But many pages — conference landing pages, event listings, redirect pages — don't contain the actual content. They link to it. The KubeCon schedule page links to `kccnceu2026.sched.com/`; the actual sessions live there. Mother Tree should follow that link automatically.

## What this adds

After fetching a URL's content in the detect phase, scan the page for links that host the real data. If found, fetch those too. Add the followed content to the annotation alongside the original.

## Design

### New function: `fetch_and_follow()`

Lives in `jobs/bot/enrich.py`. Wraps `fetch_url_context()` with link-following logic.

```
fetch_and_follow(url, follow_budget) -> str | None

1. Fetch URL with httpx (15s timeout, follow redirects)
2. If fetch fails → return None
3. Parse HTML with BeautifulSoup — keep the unmodified soup for link extraction
4. Extract links from the unmodified soup (before any tag decomposition)
5. Strip script/style/nav/footer tags, extract text (same logic as fetch_url_context)
6. Special case: LinkedIn URLs return the stub string with no link scan
7. Decide whether to scan for follow-links (trigger logic below)
8. If triggered → extract qualifying links, acquire from follow_budget semaphore
9. Fetch follow-links in parallel via fetch_url_context() (10s timeout)
10. Return combined content: original text + followed content separated by ---
```

Returns a single string — same interface as `fetch_url_context()`. Drop-in replacement in `detect.py`.

**Important:** `fetch_and_follow` performs its own initial HTTP fetch and HTML parsing. It does not call `fetch_url_context()` for the original URL because `fetch_url_context()` decomposes nav/footer tags (which often contain the schedule links we need) and discards the soup. `fetch_url_context()` is only used for follow-link fetches, where we just need text content.

### Trigger logic

Two independent triggers. Either one fires the link scan.

**Trigger A — Domain allowlist (fires at any content length).**
Scan the page's `<a href>` tags for domains that host content behind landing pages:

- `sched.com` — conference schedules
- `sessionize.com` — conference schedules
- `pretalx.com` — conference schedules
- `whova.com` — conference apps
- `notion.so`, `notion.site` — shared documents
- `docs.google.com` — shared documents
- `luma.so` — event pages

Constant list in `enrich.py`. Easy to extend.

**Trigger B — Thin content + anchor heuristics (fires when text < 500 chars).**
If the fetched text is under 500 characters, scan `<a>` tags for anchor text matching patterns like "view schedule", "full program", "see details", "session list", "view agenda", "browse sessions". Case-insensitive regex.

This catches unknown platforms behind landing pages that have little content of their own.

**What does not trigger:** Rich pages (500+ chars) with links to domains not on the allowlist.

### Link extraction and filtering

When a trigger fires:

1. Extract all `<a href="...">` tags from the BeautifulSoup object.
2. Resolve relative and protocol-relative URLs to absolute (using the page's base URL).
3. Skip fragment-only links, mailto, javascript, and same-page anchors.
4. For Trigger A: keep links whose domain matches the allowlist.
5. For Trigger B: keep links whose anchor text matches the heuristic patterns.
6. Deduplicate by domain — if multiple links point to sched.com, prefer the one with the longest path (most specific URL). Falls back to first-in-DOM if paths are equal length.
7. Skip links pointing back to the original URL's domain.

### Caps and budget

- Max 2 follow-links per original URL.
- Original fetches are not budgeted — they always fire (up to 3 per message, same as today).
- Follow-fetches share a budget of 2 across the entire message, enforced via `threading.Semaphore(2)`. This means: 1 URL gets up to 2 follows; 2 URLs get up to 2 follows total (e.g., 1 each); 3 URLs get up to 2 follows total.
- Follow-fetches use a 10-second timeout (tighter than the 15s original fetch) to limit cascading delays.
- `fetch_and_follow` has a 20-second total wall-clock budget. If the original fetch takes 14 seconds, follow-fetches get at most 6 seconds.

### Integration into detect.py

One change in the URL detection section (lines 282–318). Replace `fetch_url_context` with `fetch_and_follow` in the thread pool:

```python
# Before
fetched = list(pool.map(fetch_url_context, urls))

# After
follow_budget = threading.Semaphore(2)
fetched = list(pool.map(lambda u: fetch_and_follow(u, follow_budget), urls))
```

The rest of detect.py stays unchanged. `fetch_and_follow()` returns a combined string, so the annotation building — `url_results`, `url_failures`, single vs. multi URL — works as-is. No annotation schema changes.

### Parallel fetching

Follow-links are fetched in parallel using a `ThreadPoolExecutor` inside `fetch_and_follow()`. Each follow-fetch calls `fetch_url_context()` (returns text capped at 3000 chars). Follow-fetches use a 10-second timeout to stay within the 20-second wall-clock budget.

Follow-fetches do not recurse. A followed page that itself contains allowlisted links is not followed further. Only the original page triggers link-following.

## Validated against real data

Tested against `https://events.linuxfoundation.org/kubecon-cloudnativecon-europe/program/schedule/`:

- **Original page:** ~45,000 chars of content (event overview, sponsors, navigation). Not thin.
- **Contains link:** `https://kccnceu2026.sched.com/` with anchor text "View the KubeCon + CloudNativeCon Europe 2026 schedule & directory".
- **Trigger A fires:** `sched.com` is on the domain allowlist. Thin-content trigger would miss this page.
- **Followed page:** Full session list — titles, times, speakers, rooms across all conference days.

The combined annotation gives the conversation engine both the event overview and the session-level schedule. Enough to answer "which talks should I attend on day 2?"

## Testing

### Unit tests

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_fetch_and_follow_thin_page` | Page < 500 chars, link with matching anchor text | Follow-fetch fires |
| `test_fetch_and_follow_rich_page_allowlist` | Page 5000 chars, contains sched.com link | Follow-fetch fires |
| `test_fetch_and_follow_rich_page_no_match` | Page 5000 chars, no allowlisted or heuristic links | No follow |
| `test_follow_link_cap` | Page with 5 qualifying links | Only 2 followed |
| `test_follow_budget` | 3 URLs in message, two trigger follows | Total follow-fetches ≤ 2 |
| `test_skip_same_domain` | Page links back to its own domain | Link skipped |
| `test_resolve_relative_urls` | Page has relative href `/schedule` | Resolved to absolute |
| `test_protocol_relative_urls` | Page has `//kccnceu2026.sched.com/` | Resolved correctly |
| `test_linkedin_no_follow` | LinkedIn URL passed to `fetch_and_follow` | Returns stub string, no link scan, no crash |
| `test_wall_clock_budget` | Original fetch takes 14s, follow-fetch available | Follow gets at most 6s timeout |
| `test_dedup_prefers_longest_path` | Two sched.com links: `/` and `/2026/schedule` | Picks the longer path |

### Manual integration test

Fetch the real KubeCon schedule URL. Verify: LF page fetched → sched.com link detected → followed → combined content contains session data.

## Files changed

| File | Change |
|------|--------|
| `jobs/bot/enrich.py` | Add `fetch_and_follow()`, domain allowlist constant, anchor heuristic patterns |
| `jobs/bot/detect.py` | Replace `fetch_url_context` with `fetch_and_follow` in URL section, add semaphore |
| `jobs/tests/test_enrich.py` | Unit tests for `fetch_and_follow()` |
| `jobs/tests/test_detect.py` | Update URL detection tests to use `fetch_and_follow` |
