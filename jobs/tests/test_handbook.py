"""Tests for handbook loading and querying."""
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestHandbookLoading:
    def _write_entry(self, dir_path, filename, content):
        path = Path(dir_path) / filename
        path.write_text(content)
        return path

    def test_loads_entries_from_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_entry(tmpdir, "test_entry.md", """---
key: test_entry
roles: [hunter]
trigger: null
onboarding: false
onboarding_order: null
topic: testing
summary: A test entry.
---

This is the full content.
""")
            from mothertree.handbook import Handbook
            hb = Handbook(tmpdir)
            assert len(hb.entries) == 1
            assert hb.entries["test_entry"].summary == "A test entry."

    def test_get_by_role(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_entry(tmpdir, "hunter_only.md", """---
key: hunter_only
roles: [hunter]
trigger: null
onboarding: false
onboarding_order: null
topic: training
summary: Hunter stuff.
---
Content.
""")
            self._write_entry(tmpdir, "all_roles.md", """---
key: all_roles
roles: [hunter, gatherer, farmer, citizen]
trigger: null
onboarding: false
onboarding_order: null
topic: general
summary: For everyone.
---
Content.
""")
            from mothertree.handbook import Handbook
            hb = Handbook(tmpdir)
            hunter_entries = hb.for_role("hunter")
            citizen_entries = hb.for_role("citizen")
            assert len(hunter_entries) == 2
            assert len(citizen_entries) == 1

    def test_get_by_trigger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_entry(tmpdir, "triggered.md", """---
key: triggered
roles: [hunter]
trigger: first_pulse_nudge
onboarding: false
onboarding_order: null
topic: rhythm
summary: About Pulse.
---
Content.
""")
            from mothertree.handbook import Handbook
            hb = Handbook(tmpdir)
            entry = hb.by_trigger("first_pulse_nudge")
            assert entry is not None
            assert entry.key == "triggered"
            assert hb.by_trigger("nonexistent") is None

    def test_onboarding_sequence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_entry(tmpdir, "second.md", """---
key: second
roles: [hunter]
trigger: null
onboarding: true
onboarding_order: 2
topic: training
summary: Second step.
---
Content.
""")
            self._write_entry(tmpdir, "first.md", """---
key: first
roles: [hunter]
trigger: enrollment_complete
onboarding: true
onboarding_order: 1
topic: getting_started
summary: First step.
---
Content.
""")
            from mothertree.handbook import Handbook
            hb = Handbook(tmpdir)
            seq = hb.onboarding_sequence("hunter")
            assert len(seq) == 2
            assert seq[0].key == "first"
            assert seq[1].key == "second"

    def test_grouped_by_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_entry(tmpdir, "a.md", """---
key: a
roles: [hunter]
trigger: null
onboarding: false
onboarding_order: null
topic: rhythm
summary: Rhythm A.
---
Content.
""")
            self._write_entry(tmpdir, "b.md", """---
key: b
roles: [hunter]
trigger: null
onboarding: false
onboarding_order: null
topic: training
summary: Training B.
---
Content.
""")
            from mothertree.handbook import Handbook
            hb = Handbook(tmpdir)
            grouped = hb.grouped_by_topic("hunter")
            assert "rhythm" in grouped
            assert "training" in grouped


class TestHelpDelivery:
    @patch("mothertree.graphql_client.graphql")
    def test_check_help_delivered(self, mock_gql):
        mock_gql.return_value = {"allHelpDeliveredsList": []}
        from mothertree.graphql_client import has_help_been_delivered
        result = has_help_been_delivered("U123", "pulse_nudges")
        assert result is False

    @patch("mothertree.graphql_client.graphql")
    def test_check_help_already_delivered(self, mock_gql):
        mock_gql.return_value = {"allHelpDeliveredsList": [{"id": "x"}]}
        from mothertree.graphql_client import has_help_been_delivered
        result = has_help_been_delivered("U123", "pulse_nudges")
        assert result is True

    @patch("mothertree.graphql_client.graphql")
    def test_record_help_delivered(self, mock_gql):
        mock_gql.return_value = {"createHelpDelivered": {"helpDelivered": {"id": "x"}}}
        from mothertree.graphql_client import record_help_delivered
        record_help_delivered("U123", "pulse_nudges")
        mock_gql.assert_called_once()


class TestContextualDelivery:
    @patch("mothertree.graphql_client.has_help_been_delivered")
    @patch("mothertree.graphql_client.record_help_delivered")
    def test_delivers_tip_on_first_encounter(self, mock_record, mock_check):
        mock_check.return_value = False
        from mothertree.handbook import HandbookEntry
        entry = HandbookEntry(
            key="pulse_snooze", roles=["hunter"], trigger="first_pulse_nudge",
            onboarding=False, onboarding_order=None, topic="rhythm",
            summary="You can snooze nudges.", content="Full content here.",
        )
        from bot.pipeline import _maybe_deliver_contextual_help
        tip = _maybe_deliver_contextual_help("U123", "first_pulse_nudge", entry)
        assert tip is not None
        assert "snooze" in tip.lower()
        mock_record.assert_called_once_with("U123", "pulse_snooze")

    @patch("mothertree.graphql_client.has_help_been_delivered")
    def test_skips_already_delivered(self, mock_check):
        mock_check.return_value = True
        from mothertree.handbook import HandbookEntry
        entry = HandbookEntry(
            key="pulse_snooze", roles=["hunter"], trigger="first_pulse_nudge",
            onboarding=False, onboarding_order=None, topic="rhythm",
            summary="You can snooze nudges.", content="Full content here.",
        )
        from bot.pipeline import _maybe_deliver_contextual_help
        tip = _maybe_deliver_contextual_help("U123", "first_pulse_nudge", entry)
        assert tip is None
