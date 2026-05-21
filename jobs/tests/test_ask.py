"""Tests for ask.py — small helpers that remain after the intelligence migration.

The former fetch_context contact/signal/semantic-search tests live in
test_intelligence.py now — fetch_context has been replaced by
intelligence.gather_context + intelligence.format_context_for_prompt.
"""


class TestEmbedTextForRecord:
    """Test text generation for embedding."""

    def test_insight_text(self):
        from mothertree.graphql_client import _embed_text_for_record
        record = {"category": "lock-in", "reframe": "Break free", "evidence": "40% savings", "trigger": "NIS2"}
        text = _embed_text_for_record("insights", record)
        assert "lock-in" in text
        assert "Break free" in text
        assert "40% savings" in text
        assert "NIS2" in text

    def test_change_text(self):
        from mothertree.graphql_client import _embed_text_for_record
        text = _embed_text_for_record("change", {"statement": "Freedom to operate", "context": "cloud"})
        assert "Freedom to operate" in text
        assert "cloud" in text

    def test_worldview_text(self):
        from mothertree.graphql_client import _embed_text_for_record
        text = _embed_text_for_record("worldview", {"belief": "Speed matters", "pain": "slow delivery"})
        assert "Speed matters" in text

    def test_empty_record(self):
        from mothertree.graphql_client import _embed_text_for_record
        text = _embed_text_for_record("change", {"statement": "", "context": ""})
        assert text == ""
