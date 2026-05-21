# Small Wins Plan B: New Features

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add debrief ingestion with sensitivity gate, onboarding profile collection, enrollment approval flow, and the handbook system for feature awareness and onboarding.

**Architecture:** Four new user-facing features that extend the dispatcher and pipeline. The handbook provides the documentation layer that ties everything together. Each task builds on the existing message routing architecture (dispatcher → pipeline → character response).

**Tech Stack:** Python, PostGraphile GraphQL, Slack SDK, python-frontmatter, Mistral Small (extraction), Pydantic.

**Spec:** `docs/superpowers/specs/2026-04-11-small-wins-batch.md` (sections 1, 7, 8, 10)

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `jobs/mothertree/handbook.py` | Load, index, and query handbook markdown entries |
| `jobs/handbook/*.md` | ~22 handbook entries (one per feature/concept) |
| `jobs/tests/test_handbook.py` | Tests for handbook loading and querying |
| `jobs/tests/test_debrief.py` | Tests for debrief extraction and approval flow |
| `jobs/tests/test_enrollment_approval.py` | Tests for enrollment request/approval flow |
| `jobs/tests/test_profile_collection.py` | Tests for profile detail extraction |

### Modified Files

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add enrollment_requests table, help_delivered table, pending_debrief on conversations, profile fields on enrollment |
| `jobs/mothertree/config.py` | Add ADMIN_SLACK_ID |
| `jobs/bot/characters/dispatcher.py` | Debrief detection, profile detection, enrollment approval detection, help routing |
| `jobs/bot/characters/spotter.py` | Debrief prompt extension with sensitivity flagging |
| `jobs/bot/pipeline.py` | Debrief approval flow, profile update handling, enrollment request flow, handbook contextual delivery |
| `jobs/mothertree/graphql_client.py` | CRUD for enrollment_requests, help_delivered, update_enrollment_profile, pending_debrief |
| `jobs/requirements.txt` | Add python-frontmatter |
| `deploy/base/slack-bot.yaml` | Add ADMIN_SLACK_ID env var |

---

## Task 1: Schema Migration

**Files:**
- Modify: `deploy/database/schema.sql`

- [ ] **Step 1: Add all new schema elements**

Append to `deploy/database/schema.sql`:

```sql
-- === ENROLLMENT APPROVAL ===
CREATE TABLE IF NOT EXISTS enrollment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    requested_role TEXT NOT NULL CHECK (requested_role IN ('hunter', 'gatherer', 'farmer', 'citizen')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_role TEXT,
    admin_slack_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_enrollment_requests_status
    ON enrollment_requests(status) WHERE status = 'pending';

-- === HANDBOOK DELIVERY TRACKING ===
CREATE TABLE IF NOT EXISTS help_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id TEXT NOT NULL,
    help_key TEXT NOT NULL,
    delivered_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (slack_user_id, help_key)
);

-- === DEBRIEF PENDING STATE ===
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_debrief JSONB;

-- === ONBOARDING PROFILE FIELDS ===
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS working_days TEXT[];
```

- [ ] **Step 2: Commit**

```bash
git add deploy/database/schema.sql
git commit -m "schema: add enrollment_requests, help_delivered, debrief state, profile fields"
```

---

## Task 2: Handbook System

**Files:**
- Create: `jobs/mothertree/handbook.py`
- Create: `jobs/handbook/` (directory with ~22 .md files)
- Modify: `jobs/requirements.txt`
- Test: `jobs/tests/test_handbook.py`

- [ ] **Step 1: Add python-frontmatter dependency**

Add to `jobs/requirements.txt`:

```
python-frontmatter>=1.0.0
```

- [ ] **Step 2: Write failing test**

Create `jobs/tests/test_handbook.py`:

```python
"""Tests for handbook loading and querying."""
import os
import tempfile
from pathlib import Path


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_handbook.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mothertree.handbook'`

- [ ] **Step 4: Implement handbook module**

Create `jobs/mothertree/handbook.py`:

```python
"""Handbook — role-aware feature documentation for help, onboarding, and contextual tips.

Loads markdown files with YAML frontmatter from a directory. Each file is one
feature or concept. The bot uses this for:
1. Contextual tips (first-encounter, by trigger)
2. Help command (role-filtered, grouped by topic)
3. Onboarding sequence (ordered entries for new users)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

log = logging.getLogger(__name__)


@dataclass
class HandbookEntry:
    key: str
    roles: list[str]
    trigger: str | None
    onboarding: bool
    onboarding_order: int | None
    topic: str
    summary: str
    content: str


class Handbook:
    """In-memory index of handbook entries, loaded from markdown files."""

    def __init__(self, directory: str = None):
        self.entries: dict[str, HandbookEntry] = {}
        self._by_trigger: dict[str, HandbookEntry] = {}
        if directory:
            self.load(directory)

    def load(self, directory: str) -> None:
        """Load all .md files from directory."""
        path = Path(directory)
        if not path.is_dir():
            log.warning("Handbook directory not found: %s", directory)
            return
        for md_file in sorted(path.glob("*.md")):
            try:
                post = frontmatter.load(str(md_file))
                entry = HandbookEntry(
                    key=post["key"],
                    roles=post.get("roles", []),
                    trigger=post.get("trigger"),
                    onboarding=post.get("onboarding", False),
                    onboarding_order=post.get("onboarding_order"),
                    topic=post.get("topic", "general"),
                    summary=post.get("summary", ""),
                    content=post.content,
                )
                self.entries[entry.key] = entry
                if entry.trigger:
                    self._by_trigger[entry.trigger] = entry
            except Exception:
                log.exception("Failed to load handbook entry: %s", md_file)

    def for_role(self, role: str) -> list[HandbookEntry]:
        """Get all entries visible to a role."""
        return [e for e in self.entries.values() if role in e.roles]

    def by_trigger(self, trigger: str) -> HandbookEntry | None:
        """Get the entry for a specific trigger."""
        return self._by_trigger.get(trigger)

    def onboarding_sequence(self, role: str) -> list[HandbookEntry]:
        """Get onboarding entries for a role, sorted by order."""
        entries = [e for e in self.entries.values()
                   if e.onboarding and role in e.roles]
        return sorted(entries, key=lambda e: e.onboarding_order or 999)

    def grouped_by_topic(self, role: str) -> dict[str, list[HandbookEntry]]:
        """Get entries grouped by topic for a role."""
        groups: dict[str, list[HandbookEntry]] = {}
        for entry in self.for_role(role):
            groups.setdefault(entry.topic, []).append(entry)
        return groups
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_handbook.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/mothertree/handbook.py jobs/tests/test_handbook.py jobs/requirements.txt
git commit -m "feat: handbook system — load, index, query markdown feature entries"
```

- [ ] **Step 7: Write handbook entries**

Create `jobs/handbook/` directory and write all entries. Each file follows the frontmatter pattern. Here are the entries to create:

**getting_started/enrollment.md** — key: `enrollment`, roles: all, trigger: `enrollment_complete`, onboarding: true, order: 0
**getting_started/what_is_mother_tree.md** — key: `what_is_mother_tree`, roles: all, trigger: null, onboarding: true, order: 1
**getting_started/profile_setup.md** — key: `profile_setup`, roles: all, trigger: null, onboarding: true, order: 4
**getting_started/help_command.md** — key: `help_command`, roles: all, trigger: null, onboarding: true, order: 5

**intelligence/signal_capture.md** — key: `signal_capture`, roles: [hunter, gatherer], trigger: `first_signal_captured`
**intelligence/debrief_ingestion.md** — key: `debrief_ingestion`, roles: [hunter, gatherer, farmer], trigger: `first_debrief_attempt`
**intelligence/briefing.md** — key: `briefing`, roles: [hunter], trigger: null
**intelligence/ask_personas.md** — key: `ask_personas`, roles: all, trigger: null

**training/training_overview.md** — key: `training_overview`, roles: [hunter, gatherer, farmer], trigger: null, onboarding: true, order: 2
**training/training_commands.md** — key: `training_commands`, roles: [hunter, gatherer, farmer], trigger: `first_training_exercise`
**training/training_scoring.md** — key: `training_scoring`, roles: [hunter, gatherer, farmer], trigger: null
**training/citizen_inspiration.md** — key: `citizen_inspiration`, roles: [citizen], trigger: null, onboarding: true, order: 2

**rhythm/pulse_nudges.md** — key: `pulse_nudges`, roles: [hunter, gatherer], trigger: `first_pulse_nudge`, onboarding: true, order: 3
**rhythm/pulse_snooze.md** — key: `pulse_snooze`, roles: [hunter, gatherer], trigger: null
**rhythm/weekly_review.md** — key: `weekly_review`, roles: [hunter], trigger: null
**rhythm/monthly_retro.md** — key: `monthly_retro`, roles: [hunter], trigger: null
**rhythm/calendar_prep.md** — key: `calendar_prep`, roles: [hunter], trigger: null

**contacts/contacts_overview.md** — key: `contacts_overview`, roles: [hunter, gatherer], trigger: null
**contacts/opportunities.md** — key: `opportunities`, roles: [hunter], trigger: null
**contacts/temperature.md** — key: `temperature`, roles: [hunter, gatherer], trigger: null

**admin/enrollment_approval.md** — key: `enrollment_approval`, roles: [hunter], trigger: `first_enrollment_request`
**admin/pending_requests.md** — key: `pending_requests`, roles: [hunter], trigger: null

Each entry body should be 3-8 lines: what it does, why it matters, how to use it. Write in Mother Tree's voice — direct, warm, practitioner-friendly.

- [ ] **Step 8: Commit handbook entries**

```bash
git add jobs/handbook/
git commit -m "content: handbook entries for all features (~22 files)"
```

---

## Task 3: Handbook GraphQL + Delivery

**Files:**
- Modify: `jobs/mothertree/graphql_client.py`
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/bot/characters/dispatcher.py`
- Test: `jobs/tests/test_handbook.py` (extend)

- [ ] **Step 1: Write failing test for delivery tracking**

Add to `jobs/tests/test_handbook.py`:

```python
from unittest.mock import patch


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_handbook.py::TestHelpDelivery -v`
Expected: FAIL

- [ ] **Step 3: Add GraphQL functions**

Append to `jobs/mothertree/graphql_client.py`:

```python
# --- Handbook delivery tracking ---

def has_help_been_delivered(slack_user_id: str, help_key: str) -> bool:
    """Check if a help entry has been delivered to a user."""
    result = graphql("""
    query($uid: String!, $key: String!) {
        allHelpDeliveredsList(condition: {slackUserId: $uid, helpKey: $key}) { id }
    }
    """, {"uid": slack_user_id, "key": help_key})
    return len(result.get("allHelpDeliveredsList", [])) > 0


def record_help_delivered(slack_user_id: str, help_key: str) -> None:
    """Record that a help entry was delivered to a user."""
    graphql("""
    mutation($obj: HelpDeliveredInput!) {
        createHelpDelivered(input: {helpDelivered: $obj}) {
            helpDelivered { id }
        }
    }
    """, {"obj": {"slackUserId": slack_user_id, "helpKey": help_key}})
```

- [ ] **Step 4: Wire help command into dispatcher**

In `dispatcher.py`, the "help" command already routes with `annotation = {"type": "help"}`. Extend it to support topic lookups: if the user says "help debrief", set `annotation = {"type": "help", "topic": "debrief"}`.

In the `dispatch()` function, replace the help handling (around line 216):

```python
        elif first == "help":
            topic = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "help", "topic": topic}
```

- [ ] **Step 5: Wire help response into pipeline**

In `pipeline.py`, when the annotation type is "help", load the handbook and format the response. In `_get_response()`, add a branch for help:

```python
if routing["annotation"] and routing["annotation"].get("type") == "help":
    from mothertree.handbook import Handbook
    hb = Handbook("handbook")
    topic = routing["annotation"].get("topic")
    role = (enrollment or {}).get("role", "citizen")
    if topic:
        # Find entry by key or topic keyword
        entry = hb.entries.get(topic) or next(
            (e for e in hb.for_role(role) if topic.lower() in e.key or topic.lower() in e.summary.lower()), None)
        if entry:
            return entry.content
        return f"I don't have help on '{topic}'. Say *help* to see all topics."
    # Full help listing grouped by topic
    grouped = hb.grouped_by_topic(role)
    lines = ["Here's what I can help with:\n"]
    for topic_name, entries in grouped.items():
        lines.append(f"*{topic_name.replace('_', ' ').title()}*")
        for e in entries:
            lines.append(f"  • {e.summary}")
    lines.append("\nSay *help [topic]* for details.")
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_handbook.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/mothertree/graphql_client.py jobs/bot/characters/dispatcher.py jobs/bot/pipeline.py jobs/tests/test_handbook.py
git commit -m "feat: help command with role-aware handbook and delivery tracking"
```

---

## Task 4: Debrief Ingestion — Dispatcher + Spotter

**Files:**
- Modify: `jobs/bot/characters/dispatcher.py`
- Modify: `jobs/bot/characters/spotter.py`
- Test: `jobs/tests/test_debrief.py`

- [ ] **Step 1: Write failing test for debrief detection**

Create `jobs/tests/test_debrief.py`:

```python
"""Tests for debrief ingestion flow."""
from unittest.mock import patch


class TestDebriefDetection:
    def test_detects_debrief_keyword(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "debrief\nAttendees: Jurg, client team\nDiscussed migration timeline.",
            participant_count=1,
        )
        assert result["intent"] == "debrief"
        assert result["annotation"]["type"] == "debrief"

    def test_detects_meeting_notes(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "meeting notes\nQ4 review with Sanoma Learning.",
            participant_count=1,
        )
        assert result["intent"] == "debrief"

    def test_detects_service_meeting(self):
        from bot.characters.dispatcher import dispatch
        result = dispatch(
            "service meeting\nMonthly review with the delivery team.",
            participant_count=1,
        )
        assert result["intent"] == "debrief"

    def test_no_debrief_in_channels(self):
        """Debrief detection only in DMs."""
        with patch("bot.characters.dispatcher._call_triage_llm") as mock_triage:
            mock_triage.return_value = {"respond": False, "signal": {"capture": False}}
            from bot.characters.dispatcher import dispatch
            result = dispatch("debrief\nSome notes.", participant_count=5)
            assert result["intent"] != "debrief"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_debrief.py::TestDebriefDetection -v`
Expected: FAIL

- [ ] **Step 3: Add debrief detection to dispatcher**

In `dispatcher.py`, add debrief patterns and detection. After the snooze/completion block (section 4b) and before URL detection (section 5), add:

```python
    # 4c. DM debrief ingestion
    _DEBRIEF_TRIGGERS = {"debrief", "meeting notes", "service meeting"}

    if participant_count == 1:
        first_line = clean.split("\n")[0].lower().strip()
        if first_line in _DEBRIEF_TRIGGERS:
            result["must_respond"] = True
            result["intent"] = "debrief"
            result["annotation"] = {
                "type": "debrief",
                "content": "\n".join(clean.split("\n")[1:]).strip(),
            }
            return result
```

Move `_DEBRIEF_TRIGGERS` to module level (outside the function) as a frozenset.

- [ ] **Step 4: Write failing test for debrief Spotter prompt**

Add to `jobs/tests/test_debrief.py`:

```python
class TestDebriefSpotter:
    @patch("bot.characters.spotter.chat_conversation")
    def test_debrief_extraction_includes_sensitivity(self, mock_chat):
        mock_chat.return_value = '{"entities": [{"name": "Sarah", "type": "person"}], "pain_signals": [{"signal": "Timeline pressure", "sensitive": false}], "value_hooks": [], "actions": [{"action": "Pim struggled with presentation", "sensitive": true}], "stage": {"current": "signal"}}'
        from bot.characters.spotter import extract_debrief
        result = extract_debrief("Discussed project timeline. Pim struggled with the client presentation. Sarah from client side happy with progress.")
        assert any(item.get("sensitive") for items in [result.get("actions", [])] for item in items)

    @patch("bot.characters.spotter.chat_conversation")
    def test_debrief_extraction_returns_dict(self, mock_chat):
        mock_chat.return_value = '{"entities": [], "pain_signals": [], "value_hooks": [], "actions": [], "stage": {"current": "signal"}}'
        from bot.characters.spotter import extract_debrief
        result = extract_debrief("Quick sync, nothing notable.")
        assert isinstance(result, dict)
        assert "entities" in result
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_debrief.py::TestDebriefSpotter -v`
Expected: FAIL — `cannot import name 'extract_debrief'`

- [ ] **Step 6: Add extract_debrief to Spotter**

In `jobs/bot/characters/spotter.py`, add a new function after the existing `extract()`:

```python
DEBRIEF_EXTENSION = """
You are extracting commercial intelligence from a service meeting debrief.

Extract the same categories as usual, but also flag sensitive items.
An item is sensitive if it names or identifies an internal team member
in a performance context — positive or negative.

Factual observations about project status are not sensitive.
Client-facing information is not sensitive.
Internal team performance commentary IS sensitive.

For each extracted item, add: "sensitive": true/false
"""


def extract_debrief(content: str) -> dict:
    """Extract commercial intelligence from a debrief with sensitivity flags."""
    messages = [
        {"role": "system", "content": SPOTTER_SYSTEM + "\n\n" + DEBRIEF_EXTENSION},
        {"role": "user", "content": content},
    ]
    response = chat_conversation(messages)
    return _parse_json(response)
```

(Where `SPOTTER_SYSTEM` is the existing system prompt constant and `_parse_json` is from `mothertree.llm`.)

- [ ] **Step 7: Run tests**

Run: `cd jobs && python -m pytest tests/test_debrief.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/bot/characters/spotter.py jobs/tests/test_debrief.py
git commit -m "feat: debrief detection in dispatcher + Spotter extraction with sensitivity flags"
```

---

## Task 5: Debrief Ingestion — Pipeline Approval Flow

**Files:**
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/mothertree/graphql_client.py`
- Test: `jobs/tests/test_debrief.py` (extend)

- [ ] **Step 1: Write failing test for approval flow**

Add to `jobs/tests/test_debrief.py`:

```python
class TestDebriefApprovalFlow:
    @patch("bot.pipeline._send_response")
    @patch("bot.pipeline._post_thinking")
    @patch("bot.pipeline._delete_thinking")
    @patch("bot.characters.spotter.extract_debrief")
    def test_debrief_shows_preview(self, mock_extract, mock_delete, mock_think, mock_send):
        mock_think.return_value = "thinking_ts"
        mock_extract.return_value = {
            "entities": [{"name": "ClientCo", "type": "organization", "sensitive": False}],
            "pain_signals": [{"signal": "Timeline pressure", "sensitive": False}],
            "value_hooks": [],
            "actions": [{"action": "Pim struggled with presentation", "sensitive": True}],
            "stage": {"current": "signal"},
        }
        # The preview should show items with sensitivity markers
        # and ask for approval
        from bot.pipeline import _format_debrief_preview
        preview = _format_debrief_preview(mock_extract.return_value)
        assert "approve" in preview.lower()
        assert "skip" in preview.lower()
        assert "⚠️" in preview  # sensitive marker

    def test_format_preview_marks_sensitive(self):
        from bot.pipeline import _format_debrief_preview
        extraction = {
            "entities": [{"name": "ClientCo", "type": "organization", "sensitive": False}],
            "pain_signals": [{"signal": "Budget concerns", "sensitive": False}],
            "actions": [{"action": "Dev struggled with deadline", "sensitive": True}],
            "value_hooks": [],
            "stage": {"current": "signal"},
        }
        preview = _format_debrief_preview(extraction)
        assert "⚠️" in preview
        assert "Budget concerns" in preview
        assert "approve" in preview.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_debrief.py::TestDebriefApprovalFlow -v`
Expected: FAIL — `cannot import name '_format_debrief_preview'`

- [ ] **Step 3: Implement preview formatting**

Add to `jobs/bot/pipeline.py`:

```python
def _format_debrief_preview(extraction: dict) -> str:
    """Format debrief extraction as a preview with sensitivity markers."""
    lines = ["*Debrief extraction preview:*\n"]
    item_num = 0

    for category in ("entities", "pain_signals", "value_hooks", "actions"):
        items = extraction.get(category, [])
        if not items:
            continue
        label = category.replace("_", " ").title()
        lines.append(f"*{label}:*")
        for item in items:
            item_num += 1
            text = item.get("name") or item.get("signal") or item.get("hook") or item.get("action") or str(item)
            sensitive = item.get("sensitive", False)
            marker = "⚠️ " if sensitive else ""
            lines.append(f"  {item_num}. {marker}{text}")

    stage = extraction.get("stage", {}).get("current", "")
    if stage:
        lines.append(f"\n_Stage: {stage}_")

    lines.append("\n⚠️ = sensitive (will be dropped on approve)")
    lines.append("Reply *approve* to ingest, *edit* to remove items, or *skip* to discard.")
    return "\n".join(lines)
```

- [ ] **Step 4: Add pending_debrief GraphQL functions**

Append to `jobs/mothertree/graphql_client.py`:

```python
# --- Debrief pending state ---

def set_pending_debrief(conversation_id: str, extraction: dict) -> None:
    """Store pending debrief extraction on a conversation record."""
    import json
    graphql("""
    mutation($id: UUID!, $patch: ConversationPatch!) {
        updateConversationById(input: {id: $id, conversationPatch: $patch}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id, "patch": {"pendingDebrief": json.dumps(extraction)}})


def get_pending_debrief(conversation_id: str) -> dict | None:
    """Get pending debrief from conversation, if any."""
    result = graphql("""
    query($id: UUID!) {
        conversationById(id: $id) { pendingDebrief }
    }
    """, {"id": conversation_id})
    conv = result.get("conversationById", {})
    pending = conv.get("pendingDebrief")
    if pending:
        import json
        return json.loads(pending) if isinstance(pending, str) else pending
    return None


def clear_pending_debrief(conversation_id: str) -> None:
    """Clear pending debrief after approval/skip."""
    graphql("""
    mutation($id: UUID!) {
        updateConversationById(input: {id: $id, conversationPatch: {pendingDebrief: null}}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id})
```

- [ ] **Step 5: Wire debrief flow into pipeline**

In `_process_message()`, after the dispatch phase, add handling for debrief annotation. When `routing["annotation"]["type"] == "debrief"`:

1. Call `extract_debrief()` with the content
2. Format preview with `_format_debrief_preview()`
3. Store extraction via `set_pending_debrief()`
4. Send preview as response

When a user's next message arrives and `get_pending_debrief()` returns data:
- "approve" → filter out sensitive items, run through Weaver → signal pipeline, clear pending
- "edit" → ask for item numbers, wait for next message
- "skip" → clear pending, acknowledge

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_debrief.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/pipeline.py jobs/mothertree/graphql_client.py jobs/tests/test_debrief.py
git commit -m "feat: debrief approval flow — preview, approve/edit/skip, pending state"
```

---

## Task 6: Enrollment Approval

**Files:**
- Modify: `jobs/mothertree/config.py`
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/bot/characters/dispatcher.py`
- Modify: `jobs/mothertree/graphql_client.py`
- Modify: `jobs/pulse/scanner.py`
- Modify: `jobs/cli.py`
- Modify: `deploy/base/slack-bot.yaml`
- Test: `jobs/tests/test_enrollment_approval.py`

- [ ] **Step 1: Add ADMIN_SLACK_ID to config**

In `jobs/mothertree/config.py`, add:

```python
ADMIN_SLACK_ID = os.environ.get("ADMIN_SLACK_ID", "")
```

- [ ] **Step 2: Write failing test**

Create `jobs/tests/test_enrollment_approval.py`:

```python
"""Tests for enrollment approval flow."""
from unittest.mock import MagicMock, patch


class TestEnrollmentRequest:
    @patch("mothertree.graphql_client.graphql")
    def test_create_enrollment_request(self, mock_gql):
        mock_gql.return_value = {"createEnrollmentRequest": {"enrollmentRequest": {"id": "req-1"}}}
        from mothertree.graphql_client import create_enrollment_request
        result = create_enrollment_request("U_PIM", "Pim", "hunter")
        assert result is not None

    @patch("mothertree.graphql_client.graphql")
    def test_get_pending_requests(self, mock_gql):
        mock_gql.return_value = {"allEnrollmentRequestsList": [
            {"id": "req-1", "slackUserId": "U_PIM", "name": "Pim", "requestedRole": "hunter"}
        ]}
        from mothertree.graphql_client import get_pending_enrollment_requests
        results = get_pending_enrollment_requests()
        assert len(results) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_resolve_request(self, mock_gql):
        mock_gql.return_value = {"updateEnrollmentRequestById": {"enrollmentRequest": {"id": "req-1"}}}
        from mothertree.graphql_client import resolve_enrollment_request
        resolve_enrollment_request("req-1", "approved", "hunter", "U_ADMIN")
        mock_gql.assert_called_once()


class TestApprovalDetection:
    def test_detects_approve_in_admin_dm(self):
        from bot.characters.dispatcher import _detect_enrollment_action
        result = _detect_enrollment_action("approve")
        assert result == ("approve", None)

    def test_detects_approve_with_role(self):
        from bot.characters.dispatcher import _detect_enrollment_action
        result = _detect_enrollment_action("approve as citizen")
        assert result == ("approve", "citizen")

    def test_detects_reject(self):
        from bot.characters.dispatcher import _detect_enrollment_action
        result = _detect_enrollment_action("reject")
        assert result == ("reject", None)

    def test_no_match_on_regular_text(self):
        from bot.characters.dispatcher import _detect_enrollment_action
        result = _detect_enrollment_action("what's the status?")
        assert result is None


class TestRequestTimeout:
    @patch("mothertree.graphql_client.graphql")
    def test_expire_old_requests(self, mock_gql):
        mock_gql.return_value = {"allEnrollmentRequestsList": [
            {"id": "req-old", "slackUserId": "U_OLD", "createdAt": "2026-04-08T00:00:00+00:00"}
        ]}
        from mothertree.graphql_client import get_expired_enrollment_requests
        results = get_expired_enrollment_requests(hours=48)
        assert len(results) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_enrollment_approval.py -v`
Expected: FAIL

- [ ] **Step 4: Add GraphQL functions for enrollment requests**

Append to `jobs/mothertree/graphql_client.py`:

```python
# --- Enrollment approval ---

def create_enrollment_request(slack_user_id: str, name: str, role: str) -> dict:
    """Create a pending enrollment request."""
    result = graphql("""
    mutation($obj: EnrollmentRequestInput!) {
        createEnrollmentRequest(input: {enrollmentRequest: $obj}) {
            enrollmentRequest { id slackUserId name requestedRole }
        }
    }
    """, {"obj": {"slackUserId": slack_user_id, "name": name, "requestedRole": role}})
    return result.get("createEnrollmentRequest", {}).get("enrollmentRequest")


def get_pending_enrollment_requests() -> list[dict]:
    """Get all pending enrollment requests."""
    result = graphql("""
    query {
        allEnrollmentRequestsList(condition: {status: "pending"}) {
            id slackUserId name requestedRole createdAt
        }
    }
    """)
    return result.get("allEnrollmentRequestsList", [])


def resolve_enrollment_request(request_id: str, status: str, role: str = None, admin_id: str = None) -> None:
    """Resolve an enrollment request (approve/reject)."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    patch = {"status": status, "resolvedAt": now}
    if role:
        patch["approvedRole"] = role
    if admin_id:
        patch["adminSlackId"] = admin_id
    graphql("""
    mutation($id: UUID!, $patch: EnrollmentRequestPatch!) {
        updateEnrollmentRequestById(input: {id: $id, enrollmentRequestPatch: $patch}) {
            enrollmentRequest { id }
        }
    }
    """, {"id": request_id, "patch": patch})


def get_expired_enrollment_requests(hours: int = 48) -> list[dict]:
    """Get pending requests older than `hours` hours."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    result = graphql("""
    query($cutoff: Datetime!) {
        allEnrollmentRequestsList(filter: {
            status: {equalTo: "pending"},
            createdAt: {lessThan: $cutoff}
        }) { id slackUserId name createdAt }
    }
    """, {"cutoff": cutoff})
    return result.get("allEnrollmentRequestsList", [])
```

- [ ] **Step 5: Add enrollment action detection to dispatcher**

In `dispatcher.py`, add:

```python
def _detect_enrollment_action(text: str) -> tuple[str, str | None] | None:
    """Detect enrollment approval/rejection from admin DM."""
    lower = text.lower().strip()
    if lower == "approve":
        return ("approve", None)
    if lower.startswith("approve as "):
        role = lower.replace("approve as ", "").strip()
        if role in ("hunter", "gatherer", "farmer", "citizen"):
            return ("approve", role)
    if lower == "reject":
        return ("reject", None)
    return None
```

- [ ] **Step 6: Wire enrollment flow into pipeline**

In `pipeline.py`, modify the existing enroll handling. Instead of calling `operations.enroll()` directly:

1. Create an enrollment_request via `create_enrollment_request()`
2. DM the admin with the request details
3. Respond to the user: "I've sent your enrollment request to the admin."

When admin replies with approve/reject (detected by dispatcher), process it:
1. `resolve_enrollment_request()`
2. If approved: call `operations.enroll()` with the approved role
3. DM both user and admin with confirmation

- [ ] **Step 7: Add timeout check to Pulse scanner**

In `pulse/scanner.py`, in `run_scan()`, after the four scans, add:

```python
    # Check for expired enrollment requests
    _check_expired_enrollments(slack)
```

Implement `_check_expired_enrollments()`:

```python
def _check_expired_enrollments(slack: WebClient) -> None:
    """Expire enrollment requests older than 48 hours."""
    from mothertree.graphql_client import get_expired_enrollment_requests, resolve_enrollment_request
    expired = get_expired_enrollment_requests(hours=48)
    for req in expired:
        resolve_enrollment_request(req["id"], "rejected")
        try:
            _send_dm(slack, req["slackUserId"],
                     "Your enrollment request expired. Try again or reach out to the admin directly.")
        except Exception:
            log.exception("Failed to notify expired enrollment %s", req["id"])
    if expired:
        log.info("Pulse: expired %d enrollment requests", len(expired))
```

- [ ] **Step 8: Add `mothertree train pending` CLI command**

In `jobs/cli.py`, in the `elif cmd == "train":` block, add:

```python
        elif subcmd == "pending":
            from mothertree.graphql_client import get_pending_enrollment_requests
            pending = get_pending_enrollment_requests()
            if not pending:
                print("No pending enrollment requests.")
            else:
                for req in pending:
                    print(f"  {req['name']} ({req['slackUserId']}) wants to enroll as {req['requestedRole']} — {req['createdAt'][:10]}")
```

- [ ] **Step 9: Add ADMIN_SLACK_ID to deployment**

In `deploy/base/slack-bot.yaml`, add to the env section:

```yaml
                - name: ADMIN_SLACK_ID
                  valueFrom:
                    secretKeyRef:
                      name: slack-credentials
                      key: admin-slack-id
```

- [ ] **Step 10: Run tests**

Run: `cd jobs && python -m pytest tests/test_enrollment_approval.py -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add jobs/mothertree/config.py jobs/bot/pipeline.py jobs/bot/characters/dispatcher.py jobs/mothertree/graphql_client.py jobs/pulse/scanner.py jobs/cli.py deploy/base/slack-bot.yaml jobs/tests/test_enrollment_approval.py
git commit -m "feat: enrollment approval — admin gate with 48h timeout via Pulse"
```

---

## Task 7: Onboarding Profile Collection

**Files:**
- Modify: `jobs/bot/characters/dispatcher.py`
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/mothertree/graphql_client.py`
- Test: `jobs/tests/test_profile_collection.py`

- [ ] **Step 1: Write failing test**

Create `jobs/tests/test_profile_collection.py`:

```python
"""Tests for profile detail collection from DMs."""
from unittest.mock import patch


class TestProfileDetection:
    def test_detects_email(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("my email is jurg@aknostic.com")
        assert result is True

    def test_detects_calendar_url(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("here's my calendar https://calendar.google.com/ical/xxx")
        assert result is True

    def test_detects_working_days(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("I work Tuesday through Thursday")
        assert result is True

    def test_no_match_on_question(self):
        from bot.characters.dispatcher import _detect_profile_sharing
        result = _detect_profile_sharing("What's the latest on STACKIT?")
        assert result is False


class TestProfileExtraction:
    @patch("mothertree.llm.extract")
    def test_extracts_email(self, mock_extract):
        mock_extract.return_value = {
            "email": "jurg@aknostic.com",
            "calendar_url": None,
            "working_days": None,
            "phone": None,
        }
        from bot.pipeline import _extract_profile_fields
        result = _extract_profile_fields("my email is jurg@aknostic.com")
        assert result["email"] == "jurg@aknostic.com"
        assert result.get("phone") is None


class TestProfileUpdate:
    @patch("mothertree.graphql_client.graphql")
    def test_update_enrollment_profile(self, mock_gql):
        mock_gql.return_value = {"updateEnrollmentById": {"enrollment": {"id": "e1"}}}
        from mothertree.graphql_client import update_enrollment_profile
        update_enrollment_profile("e1", email="jurg@aknostic.com")
        mock_gql.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_profile_collection.py -v`
Expected: FAIL

- [ ] **Step 3: Add profile detection to dispatcher**

In `dispatcher.py`, add:

```python
import re as _re

_EMAIL_RE = _re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CALENDAR_RE = _re.compile(r"https?://calendar\.|\.ics|ical", _re.IGNORECASE)
_DAYS_RE = _re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag)\b", _re.IGNORECASE)


def _detect_profile_sharing(text: str) -> bool:
    """Detect if a DM contains personal profile information."""
    if _EMAIL_RE.search(text):
        return True
    if _CALENDAR_RE.search(text):
        return True
    if _DAYS_RE.search(text) and any(w in text.lower() for w in ("work", "available", "days", "schedule", "werk")):
        return True
    if _re.search(r"\b\+?\d[\d\s\-]{8,}\b", text):  # phone number pattern
        return True
    return False
```

In `dispatch()`, after debrief detection (section 4c) and before URL detection (section 5), add for DMs:

```python
    # 4d. DM profile sharing
    if participant_count == 1 and _detect_profile_sharing(clean):
        result["must_respond"] = True
        result["intent"] = "profile_update"
        result["annotation"] = {"type": "profile_update", "text": clean}
        return result
```

**Important:** This must come AFTER debrief detection so "debrief\nmy email is..." is caught as a debrief, not a profile update.

- [ ] **Step 4: Add profile extraction and GraphQL update**

In `pipeline.py`, add:

```python
def _extract_profile_fields(text: str) -> dict:
    """Extract profile fields from text via LLM."""
    from mothertree.llm import extract
    return extract(text, (
        "Extract personal profile fields from this message. "
        "Return JSON with keys: email, calendar_url, working_days (list of day names), phone. "
        "Set to null if not mentioned."
    ))
```

In `graphql_client.py`, add:

```python
def update_enrollment_profile(enrollment_id: str, **fields) -> None:
    """Update enrollment record with profile fields."""
    patch = {k: v for k, v in fields.items() if v is not None}
    if not patch:
        return
    # Convert snake_case to camelCase for PostGraphile
    camel_patch = {}
    for k, v in patch.items():
        parts = k.split("_")
        camel = parts[0] + "".join(p.title() for p in parts[1:])
        camel_patch[camel] = v
    graphql("""
    mutation($id: UUID!, $patch: EnrollmentPatch!) {
        updateEnrollmentById(input: {id: $id, enrollmentPatch: $patch}) {
            enrollment { id }
        }
    }
    """, {"id": enrollment_id, "patch": camel_patch})
```

- [ ] **Step 5: Wire into pipeline**

In `_process_message()`, when annotation type is `profile_update`:

1. Call `_extract_profile_fields(text)`
2. Filter out null values
3. Call `update_enrollment_profile()` with the enrollment ID
4. Respond with confirmation: "Got it — saved your email as jurg@aknostic.com."

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_profile_collection.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/bot/pipeline.py jobs/mothertree/graphql_client.py jobs/tests/test_profile_collection.py
git commit -m "feat: onboarding profile collection — extract email, calendar, working days from DMs"
```

---

## Task 8: Contextual Handbook Delivery

**Files:**
- Modify: `jobs/bot/pipeline.py`
- Test: `jobs/tests/test_handbook.py` (extend)

- [ ] **Step 1: Write failing test**

Add to `jobs/tests/test_handbook.py`:

```python
class TestContextualDelivery:
    @patch("mothertree.graphql_client.has_help_been_delivered")
    @patch("mothertree.graphql_client.record_help_delivered")
    def test_delivers_tip_on_first_encounter(self, mock_record, mock_check):
        mock_check.return_value = False
        from mothertree.handbook import Handbook, HandbookEntry
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jobs && python -m pytest tests/test_handbook.py::TestContextualDelivery -v`
Expected: FAIL — `cannot import name '_maybe_deliver_contextual_help'`

- [ ] **Step 3: Implement contextual delivery**

Add to `jobs/bot/pipeline.py`:

```python
def _maybe_deliver_contextual_help(slack_user_id: str, trigger: str, entry) -> str | None:
    """Deliver a contextual help tip if not already shown to this user."""
    from mothertree.graphql_client import has_help_been_delivered, record_help_delivered
    if has_help_been_delivered(slack_user_id, entry.key):
        return None
    record_help_delivered(slack_user_id, entry.key)
    return f"\n\n_💡 {entry.summary}_"
```

- [ ] **Step 4: Wire into response delivery**

In `_process_message()`, after the response is generated and before delivery, check if there's a trigger-based handbook entry that should be appended:

```python
    # Contextual help — append tip if this is a first encounter
    from mothertree.handbook import Handbook
    hb = Handbook("handbook")
    trigger_map = {
        "debrief": "first_debrief_attempt",
        "training": "first_training_exercise",
    }
    trigger = trigger_map.get(routing["intent"])
    if trigger:
        entry = hb.by_trigger(trigger)
        if entry and enrollment and enrollment.get("role") in entry.roles:
            tip = _maybe_deliver_contextual_help(user_slack_id, trigger, entry)
            if tip:
                response += tip
```

- [ ] **Step 5: Run tests**

Run: `cd jobs && python -m pytest tests/test_handbook.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jobs/bot/pipeline.py jobs/tests/test_handbook.py
git commit -m "feat: contextual handbook delivery — first-encounter tips with dedup"
```
