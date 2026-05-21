"""Tests for Spotter — signal extraction from conversations."""
from unittest.mock import patch


class TestSpotterExtraction:

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_returns_structured_data(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = '{"entities": [{"name": "Jim Blom", "type": "person", "role": "Co-founder", "organization": "Parai"}], "pain_signals": [{"signal": "Doesn\'t want maintenance"}], "value_hooks": [{"hook": "Sovereignty alignment"}], "actions": [{"action": "Visit requested"}], "stage": {"current": "Signal", "evidence": ["Capability was signaled"]}}'
        result = extract("met jim blom from parai", "Interesting", "Jurg")
        assert "entities" in result
        assert "stage" in result
        assert result["entities"][0]["name"] == "Jim Blom"

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_handles_empty(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = '{"entities": [], "pain_signals": [], "value_hooks": [], "actions": [], "stage": {"current": "Soil", "evidence": ["No commercial content"]}}'
        result = extract("nice weather", "Indeed!", "Jurg")
        assert result["entities"] == []

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_handles_failure(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.side_effect = Exception("LLM timeout")
        result = extract("test", "test", "test")
        assert result is None

    def test_identity_contains_hyphae(self):
        from bot.characters.spotter import IDENTITY
        assert "hyphae" in IDENTITY.lower()

    def test_identity_contains_all_stages(self):
        from bot.characters.spotter import IDENTITY
        for stage in ("Soil", "Signal", "Reframe", "Diagnosis", "Proposal", "Sustain"):
            assert stage in IDENTITY

    def test_identity_contains_fact_vs_signal_rule(self):
        from bot.characters.spotter import IDENTITY
        assert "Scaleway" in IDENTITY

    def test_identity_contains_invisibility_rule(self):
        from bot.characters.spotter import IDENTITY
        assert "invisible" in IDENTITY.lower()
