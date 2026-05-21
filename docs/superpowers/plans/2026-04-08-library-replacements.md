# Library Replacements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-rolled date parsing and retry/rate-limiting with `dateparser` and `tenacity`.

**Architecture:** Drop-in replacements — same function signatures, same callers. `_parse_date()` becomes a thin wrapper around `dateparser.parse()`. Manual retry loops and global rate-limiting state in `llm.py` become `@retry` decorators from tenacity.

**Tech Stack:** dateparser>=1.2, tenacity>=9.0

**Spec:** `docs/superpowers/specs/2026-04-08-library-replacements-design.md`

---

### Task 1: Add dependencies

**Files:**
- Modify: `jobs/requirements.txt`

- [ ] **Step 1: Add dateparser and tenacity to requirements**

```
dateparser>=1.2
tenacity>=9.0
```

Append these two lines to `jobs/requirements.txt`.

- [ ] **Step 2: Install and verify**

Run: `cd jobs && uv pip install -r requirements.txt`
Expected: Both packages install successfully.

- [ ] **Step 3: Commit**

```bash
git add jobs/requirements.txt
git commit -m "Add dateparser and tenacity dependencies"
```

---

### Task 2: Replace `_parse_date()` with dateparser — tests first

**Files:**
- Modify: `jobs/tests/test_signal_pipeline.py` (class `TestDateParsing`, lines 159-193)
- Modify: `jobs/bot/extraction.py` (function `_parse_date`, lines 90-132)

- [ ] **Step 1: Add new test cases for Dutch and complex dates**

Add these tests to the `TestDateParsing` class in `jobs/tests/test_signal_pipeline.py` after line 193:

```python
    def test_dutch_relative_dates(self):
        from bot.extraction import _parse_date
        assert _parse_date("morgen") is not None
        assert _parse_date("overmorgen") is not None
        assert _parse_date("volgende week") is not None

    def test_complex_relative_dates(self):
        from bot.extraction import _parse_date
        result = _parse_date("next Tuesday")
        assert result is not None
        # Should be a valid ISO date
        from datetime import datetime
        datetime.strptime(result, "%Y-%m-%d")

    def test_in_weeks(self):
        from bot.extraction import _parse_date
        result = _parse_date("in 3 weeks")
        assert result is not None

```

Note: "Sometime later" is already tested in `test_unparseable_returns_none` (line 193). No need to duplicate it.

- [ ] **Step 2: Run all date tests to see current state**

Run: `cd jobs && python -m pytest tests/test_signal_pipeline.py::TestDateParsing -v`
Expected: Existing tests pass. New Dutch tests fail (current `_parse_date` doesn't handle "morgen" etc). `test_sometime_later_still_none` should pass (already in `_NO_DATE_VALUES` as "none" substring check won't catch it, but the function returns None for unparseable strings).

- [ ] **Step 3: Replace `_parse_date()` in extraction.py**

In `jobs/bot/extraction.py`, replace the entire `_parse_date` function (lines 90-132) with:

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

This fully replaces the old function — the inline `import re` and `from datetime` statements inside the old body are gone with it.

- [ ] **Step 4: Run all date tests**

Run: `cd jobs && python -m pytest tests/test_signal_pipeline.py::TestDateParsing -v`
Expected: All tests pass — existing 7 + new 3.

- [ ] **Step 5: Verify edge case — "Sometime later"**

The existing `test_unparseable_returns_none` tests this. If it fails after the dateparser swap (dateparser might parse vague phrases), add `"sometime later"` to `_NO_DATE_VALUES`.

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: All tests pass. The three callers of `_parse_date` (`extraction.py:224`, `extraction.py:281`, `pipeline.py:530`) use the same signature and return type.

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/extraction.py jobs/tests/test_signal_pipeline.py
git commit -m "Replace _parse_date with dateparser — Dutch and complex dates supported"
```

---

### Task 3: Replace retry logic in `consolidate()` with tenacity

**Files:**
- Modify: `jobs/mothertree/llm.py` (function `consolidate`, lines 110-131)

- [ ] **Step 1: Add tenacity import and replace consolidate()**

In `jobs/mothertree/llm.py`, add to the imports at the top:

```python
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
```

Replace the `consolidate` function (lines 110-131) with:

```python
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
        raise RuntimeError(f"Empty response from {model or GENERATION_MODEL} (thinking may have consumed all tokens)")
    return _parse_json(text)
```

- [ ] **Step 2: Run the full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: All tests pass. `consolidate()` signature unchanged — callers unaffected.

- [ ] **Step 3: Commit**

```bash
git add jobs/mothertree/llm.py
git commit -m "Replace manual retry loop in consolidate() with tenacity"
```

---

### Task 4: Replace Anthropic rate limiting with tenacity retry

**Files:**
- Modify: `jobs/mothertree/llm.py` (lines 27-36 for `_anthropic_rate_limit`, lines 208-233 for `triage`/`arbitrate`)

- [ ] **Step 1: Remove the rate limiter**

Delete `_last_anthropic_call`, `ANTHROPIC_MIN_INTERVAL`, and `_anthropic_rate_limit()` (lines 27-36). Also remove `import time` from the top (line 4) — check no other function uses `time` in this file. (`chat_conversation` imports `time` locally at line 166, so the top-level import is only for the rate limiter.)

- [ ] **Step 2: Add retry decorators to triage() and arbitrate()**

Replace `triage()` (lines 208-219) with:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type(Exception),
)
def triage(insights: list[dict]) -> list[dict]:
    """Triage flagged insights using Claude Haiku 4.5."""
    if not anthropic_client:
        return [{"index": i, "decision": "human_review"} for i in range(len(insights))]
    items = [f'{i}. "{ins.get("reframe", "")}" — scores: {ins.get("scores", [])}' for i, ins in enumerate(insights)]
    response = anthropic_client.messages.create(
        model=TRIAGE_MODEL, max_tokens=2048,
        system="Triage commercial insights: accept, reject, or escalate. JSON only: [{index, decision, reason}]",
        messages=[{"role": "user", "content": "Triage:\n" + "\n".join(items)}],
    )
    return _parse_json(response.content[0].text.strip())
```

Replace `arbitrate()` (lines 222-233) with:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    retry=retry_if_exception_type(Exception),
)
def arbitrate(insights: list[dict]) -> list[dict]:
    """Final arbitration using Claude Sonnet 4.6."""
    if not anthropic_client:
        return [{"index": i, "decision": "human_review"} for i in range(len(insights))]
    items = [f'{i}. "{ins.get("reframe", "")}" — scores: {ins.get("scores", [])}' for i, ins in enumerate(insights)]
    response = anthropic_client.messages.create(
        model=ARBITRATION_MODEL, max_tokens=2048,
        system="Final decision on commercial insights: accept or reject. JSON only: [{index, decision, reason}]",
        messages=[{"role": "user", "content": "Arbitrate:\n" + "\n".join(items)}],
    )
    return _parse_json(response.content[0].text.strip())
```

Note: The spec recommends `retry_if_exception_type((anthropic.RateLimitError, anthropic.APIStatusError))` but the `anthropic` module is conditionally imported (only when `ANTHROPIC_API_KEY` is set, line 24). Referencing `anthropic.RateLimitError` in a decorator at module level would cause `NameError` when the key isn't configured. Using `Exception` broadly is safe here — the `stop_after_attempt(3)` with exponential backoff (5s, 10s) prevents infinite loops, and the `if not anthropic_client` early return doesn't raise so it's never retried.

- [ ] **Step 3: Remove the `_anthropic_rate_limit()` calls**

The old calls at lines 212 and 226 are gone because the functions were fully replaced. Verify no other code calls `_anthropic_rate_limit` — it was only used in `triage()` and `arbitrate()`.

- [ ] **Step 4: Run the full test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/llm.py
git commit -m "Replace Anthropic rate limiter with tenacity retry on triage and arbitrate"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run the complete test suite**

Run: `cd jobs && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Verify no leftover references**

Run: `grep -r "_anthropic_rate_limit\|ANTHROPIC_MIN_INTERVAL\|_last_anthropic_call" jobs/`
Expected: No matches.

Run: `grep -rn "from datetime.*import.*timedelta" jobs/bot/extraction.py`
Expected: No matches (the old `_parse_date` imported datetime inline — should be gone).

- [ ] **Step 3: Spot-check dateparser with a quick Python REPL test**

```bash
cd jobs && python -c "
from bot.extraction import _parse_date
print('morgen:', _parse_date('morgen'))
print('overmorgen:', _parse_date('overmorgen'))
print('next Tuesday:', _parse_date('next Tuesday'))
print('15 april 2026:', _parse_date('15 april 2026'))
print('Unknown:', _parse_date('Unknown'))
print('Past:', _parse_date('Past'))
"
```

Expected: Dutch dates return valid ISO strings, "Unknown" and "Past" return `None`.
