"""Tests for smart date resolution."""
from unittest.mock import patch

from mothertree.dates import resolve_date


class TestResolveDateTier1:
    """Dateparser-only resolution (no context needed)."""

    def test_tomorrow(self):
        result = resolve_date("tomorrow")
        assert result is not None
        assert result.tier == "dateparser"

    def test_absolute_date(self):
        result = resolve_date("April 21, 2026")
        assert result is not None
        assert result.date == "2026-04-21"
        assert result.tier == "dateparser"

    def test_dutch_date(self):
        result = resolve_date("volgende week dinsdag")
        assert result is not None
        assert result.tier == "dateparser"

    def test_relative_weeks(self):
        result = resolve_date("in 3 weeks")
        assert result is not None
        assert result.tier == "dateparser"

    def test_unparseable_returns_none(self):
        result = resolve_date("whenever you feel like it")
        assert result is None

    def test_empty_returns_none(self):
        assert resolve_date("") is None
        assert resolve_date(None) is None

    def test_no_date_values(self):
        assert resolve_date("ongoing") is None
        assert resolve_date("completed") is None


class TestResolveDateTier2:
    """LLM fallback resolution (with context)."""

    @patch("mothertree.dates.extract")
    def test_llm_fallback_with_context(self, mock_extract):
        mock_extract.return_value = {
            "date": "2026-04-18",
            "reasoning": "3 days before April 21 meeting",
        }
        result = resolve_date(
            "remind me 3 days before the meeting",
            context="Meeting: April 21, 2026 with Steven and Marco",
        )
        assert result is not None
        assert result.date == "2026-04-18"
        assert result.tier == "llm"
        mock_extract.assert_called_once()

    @patch("mothertree.dates.extract")
    def test_llm_fallback_error_returns_none(self, mock_extract):
        mock_extract.side_effect = RuntimeError("LLM failed")
        result = resolve_date(
            "a few days before the event",
            context="Event: May 10, 2026",
        )
        assert result is None

    def test_no_context_no_llm(self):
        """Without context, unparseable expressions return None (no LLM call)."""
        result = resolve_date("3 days before the meeting")
        assert result is None
