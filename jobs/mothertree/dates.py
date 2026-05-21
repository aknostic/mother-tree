"""Smart date resolution — two-tier parsing.

Tier 1: dateparser (instant, free) — handles "tomorrow", "April 21", "in 3 weeks", Dutch dates.
Tier 2: LLM fallback (Mistral Small) — fires when dateparser returns None and thread context
        is available. Resolves expressions like "3 days before the meeting".
"""

import logging
import re

import dateparser
from dateparser.search import search_dates

from mothertree.llm import extract
from mothertree.models import DateResolution

log = logging.getLogger(__name__)

# Values that are not dates — carried over from extraction.py
_NO_DATE_VALUES = frozenset({
    "", "n/a", "none", "unknown", "tbd", "ongoing", "asap",
    "completed", "past", "unspecified", "immediate",
    "sometime later",
})

# Dutch weekday names → English equivalents (for compound phrase normalization)
_DUTCH_WEEKDAYS = {
    "maandag": "Monday",
    "dinsdag": "Tuesday",
    "woensdag": "Wednesday",
    "donderdag": "Thursday",
    "vrijdag": "Friday",
    "zaterdag": "Saturday",
    "zondag": "Sunday",
}

# Relative-to-event patterns that need context to resolve (not standalone dates)
_EVENT_RELATIVE_RE = re.compile(
    r"\b\d+\s+\w+\s+(before|after)\s+(the|a|an)\b",
    re.IGNORECASE,
)


def resolve_date(text: str, context: str | None = None) -> DateResolution | None:
    """Resolve a freeform date string to an absolute date.

    Args:
        text: The date expression to parse ("tomorrow", "3 days before the meeting").
        context: Optional thread context for LLM fallback (meeting dates, etc.).

    Returns:
        DateResolution with date (YYYY-MM-DD), reasoning, and tier. None if unparseable.
    """
    if not text or text.lower().strip() in _NO_DATE_VALUES:
        return None

    # Skip event-relative expressions — they need context (LLM tier)
    if _EVENT_RELATIVE_RE.search(text):
        if context:
            return _llm_resolve(text, context)
        return None

    # Tier 1: dateparser
    result = _dateparser_parse(text)
    if result:
        return DateResolution(date=result, reasoning=text, tier="dateparser")

    # Tier 2: LLM fallback (only if context provided)
    if context:
        return _llm_resolve(text, context)

    return None


def _normalize_dutch(text: str) -> str:
    """Normalize common Dutch compound date phrases to English equivalents."""
    t = text.lower().strip()
    # "volgende week <weekday>" → "next <Weekday>"
    m = re.match(r"volgende week (\w+)$", t)
    if m and m.group(1) in _DUTCH_WEEKDAYS:
        return f"next {_DUTCH_WEEKDAYS[m.group(1)]}"
    # "volgende <weekday>" → "next <Weekday>"
    m = re.match(r"volgende (\w+)$", t)
    if m and m.group(1) in _DUTCH_WEEKDAYS:
        return f"next {_DUTCH_WEEKDAYS[m.group(1)]}"
    # Direct Dutch weekday
    if t in _DUTCH_WEEKDAYS:
        return _DUTCH_WEEKDAYS[t]
    return text


def _dateparser_parse(text: str) -> str | None:
    """Parse with dateparser. Returns YYYY-MM-DD or None."""
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }

    # Normalize Dutch compound phrases before parsing
    normalized = _normalize_dutch(text)

    # Try direct parse (auto-detect language)
    result = dateparser.parse(normalized, settings=settings)
    if result:
        return result.strftime("%Y-%m-%d")

    # Fall back to search_dates (handles "next Tuesday" → finds "Tuesday")
    found = search_dates(normalized, settings=settings)
    if found:
        return found[0][1].strftime("%Y-%m-%d")

    # If normalization changed the text, also try original
    if normalized != text:
        result = dateparser.parse(text, settings=settings)
        if result:
            return result.strftime("%Y-%m-%d")
        found = search_dates(text, settings=settings)
        if found:
            return found[0][1].strftime("%Y-%m-%d")

    return None


def _llm_resolve(text: str, context: str) -> DateResolution | None:
    """Tier 2: LLM fallback for complex date expressions."""
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    prompt = (
        f'The user said: "{text}"\n\n'
        f"Context from this thread:\n{context}\n\n"
        f"Today: {today}\n\n"
        "Resolve to an absolute date. If ambiguous, pick the earlier date "
        "(more preparation time is better than less).\n\n"
        'Return JSON only: {{"date": "YYYY-MM-DD", "reasoning": "..."}}'
    )

    try:
        result = extract("", prompt)
        if isinstance(result, dict) and "date" in result:
            return DateResolution(
                date=result["date"],
                reasoning=result.get("reasoning", text),
                tier="llm",
            )
    except Exception:
        log.exception("LLM date resolution failed for: %s", text)

    return None
