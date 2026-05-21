# Library Replacements — dateparser + tenacity

## Problem

Two hand-rolled utilities in the codebase do a worse job than mature libraries:

1. `_parse_date()` in `bot/extraction.py` (lines 90-132) — 40 lines of regex and if/elif chains for date parsing. Misses Dutch expressions, complex relative dates ("next Tuesday", "in twee weken"), and compound phrases. Used by the Spotter's action processing, event date extraction, and the correction pipeline.

2. `_anthropic_rate_limit()` + manual retry loop in `mothertree/llm.py` — global mutable state for rate limiting (lines 27-36), and a hand-rolled 2-attempt retry with bare `except` for consolidation (lines 110-131). Fragile, no backoff, swallows exceptions on first failure.

## Solution

Replace with `dateparser` and `tenacity`. No behavior changes — same function signatures, same callers, better internals.

## Changes

### 1. dateparser replaces `_parse_date()`

**File:** `jobs/bot/extraction.py`

Remove the 40-line `_parse_date()` function. Replace with a thin wrapper around `dateparser.parse()`:

```python
import dateparser

# Values that indicate "no date" in LLM output
_NO_DATE_VALUES = frozenset({
    "unknown", "none", "n/a", "tbd", "pending",
    "completed", "past", "unspecified", "immediate",
})


def _parse_date(value: str) -> str | None:
    """Parse a freeform date string into ISO format. Returns None if unparseable."""
    if not value or value.lower().strip() in _NO_DATE_VALUES:
        return None
    result = dateparser.parse(
        value,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    return result.strftime("%Y-%m-%d") if result else None
```

**What this gains:**
- Dutch: "morgen", "overmorgen", "volgende week dinsdag", "over twee weken"
- Complex relative: "next Tuesday", "in 3 weeks", "end of month"
- Compound phrases: "Application deadline 16 april 2026" (dateparser handles this)
- Named dates in context: "after Easter" (limited, but better than nothing)
- Timezone awareness available when needed (disabled for now — dates are date-only)

**What stays the same:**
- Function name and signature: `_parse_date(value: str) -> str | None`
- Return format: ISO date string `YYYY-MM-DD` or `None`
- `_NO_DATE_VALUES` filter for LLM noise words
- All three callers unchanged: `extraction.py:224`, `extraction.py:281`, `pipeline.py:530`

**dateparser config:**
- `PREFER_DATES_FROM: "future"` — when someone says "Tuesday" they mean next Tuesday
- `RETURN_AS_TIMEZONE_AWARE: False` — we store dates as date-only strings, no timezone needed

### 2. tenacity replaces retry + rate limiting in llm.py

**File:** `jobs/mothertree/llm.py`

#### Retry for `consolidate()`

Replace the manual for-loop (lines 110-131) with a tenacity decorator:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((json.JSONDecodeError, RuntimeError)),
)
def consolidate(messages: list[dict], model: str = None) -> dict | list:
    """LLM call for consolidation — low temp, high tokens, JSON output."""
    response = scaleway.chat.completions.create(
        model=model or GENERATION_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=16000,
        timeout=180,
    )
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError("Empty response (thinking may have consumed all tokens)")
    return _parse_json(text)
```

**What changes:**
- 2 attempts becomes 3 with exponential backoff (2s, 4s)
- Only retries on `JSONDecodeError` and `RuntimeError` — not all exceptions
- No more bare `except` swallowing unexpected errors
- Backoff gives Scaleway time to recover on transient failures

#### Rate limiting for Anthropic calls

Replace `_anthropic_rate_limit()` global state (lines 27-36) with a tenacity-based rate limiter or keep a minimal version without global state. The simplest correct approach:

```python
from tenacity import retry, wait_fixed, stop_after_attempt

_anthropic_limiter = retry(
    wait=wait_fixed(15),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(anthropic.RateLimitError),
)
```

Applied to `triage()` and `arbitrate()` as a decorator. The 15-second fixed wait matches the current `ANTHROPIC_MIN_INTERVAL`. The global mutable state (`_last_anthropic_call`) is removed.

**Note:** The current rate limiter is a *minimum interval* pattern (wait 15s between calls), not a retry-on-error pattern. If Anthropic calls are infrequent enough that they never overlap (current usage: triage + arbitrate during ingestion only), the simpler approach is to just use `@retry` for error handling and drop the proactive sleep entirely. If rate limit errors appear in production, add `retry_if_exception_type(anthropic.RateLimitError)` with `wait_exponential`.

Recommended: remove `_anthropic_rate_limit()` and `_last_anthropic_call` entirely. Add retry with backoff to `triage()` and `arbitrate()`:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIStatusError)),
)
def triage(insights: list[dict]) -> list[dict]:
    ...

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIStatusError)),
)
def arbitrate(insights: list[dict]) -> list[dict]:
    ...
```

### 3. Requirements

Add to `jobs/requirements.txt`:

```
dateparser>=1.2
tenacity>=9.0
```

### 4. Tests

**Existing tests (must still pass):**
- `test_signal_pipeline.py::TestDateParsing` — all 7 tests

**New test cases to add:**
- Dutch relative dates: `_parse_date("morgen")`, `_parse_date("overmorgen")`, `_parse_date("volgende week")`
- Complex relative: `_parse_date("next Tuesday")` returns a valid date
- Edge case: `_parse_date("Sometime later")` still returns `None` (dateparser might try to parse this — verify the `_NO_DATE_VALUES` filter catches it, or dateparser returns None naturally)

**tenacity tests:** No unit tests needed — tenacity's retry behavior is well-tested. The existing integration tests for `consolidate()`, `triage()`, and `arbitrate()` cover the happy path. If we want to test retry behavior, mock the Scaleway/Anthropic client to fail once and verify the retry fires — but that's optional for this scope.

## What doesn't change

- No new features
- No new callers
- No behavior changes from the user's perspective
- Character modules untouched
- Pipeline flow untouched
- All other `llm.py` functions (`extract`, `extract_deep`, `generate`, `chat`, `chat_conversation`, `score`, `embed`) untouched — they can get tenacity later if needed, but they work fine today

## Files touched

| File | Change |
|------|--------|
| `jobs/requirements.txt` | Add dateparser, tenacity |
| `jobs/bot/extraction.py` | Replace `_parse_date()` with dateparser wrapper |
| `jobs/mothertree/llm.py` | Remove `_anthropic_rate_limit` + global state, add tenacity to `consolidate`, `triage`, `arbitrate` |
| `jobs/tests/test_signal_pipeline.py` | Add Dutch/complex date test cases |
