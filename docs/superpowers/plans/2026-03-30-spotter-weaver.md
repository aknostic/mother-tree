# Spotter + Weaver Character Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic signal extraction and entity processing with character-driven modules (Spotter and Weaver), then expand Mother Tree's awareness to include the relationship graph.

**Architecture:** `spotter.py` replaces the extraction prompt in `extraction.py` with the Spotter's characterological identity. `weaver.py` replaces the entity processing in `entities.py` with the Weaver's graph-aware resolution. The pipeline's background phase calls Spotter → Weaver in sequence. Mother Tree's `fetch_context()` expands to include contacts and signals.

**Tech Stack:** Python 3.12, Qwen 3.5 (Spotter + Weaver), existing hasura.py DB functions

**Spec:** `docs/superpowers/specs/2026-03-30-remaining-characters-design.md`

---

## File Structure

```
jobs/bot/characters/spotter.py    — NEW: Spotter identity + extract function
jobs/bot/characters/weaver.py     — NEW: Weaver identity + resolve function
jobs/bot/extraction.py            — MODIFY: use Spotter, simplify
jobs/mothertree/ask.py            — MODIFY: expand fetch_context with contacts/signals
jobs/tests/test_spotter.py        — NEW: Spotter extraction tests
jobs/tests/test_weaver.py         — NEW: Weaver resolution tests
```

---

### Task 1: Create spotter.py — character identity + extraction

**Files:**
- Create: `jobs/bot/characters/spotter.py`
- Create: `jobs/tests/test_spotter.py`

- [ ] **Step 1: Write tests**

```python
# jobs/tests/test_spotter.py
"""Tests for Spotter — signal extraction from conversations."""
from unittest.mock import patch


class TestSpotterExtraction:
    """Spotter extracts structured intelligence from conversations."""

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_returns_structured_data(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = '{"entities": [{"name": "Jim Blom", "role": "Co-founder", "organization": "Parai"}], "pain_signals": [{"signal": "Doesn\\'t want maintenance"}], "value_hooks": [{"hook": "Sovereignty alignment"}], "actions": [{"action": "Visit requested"}], "stage": {"current": "Signal", "evidence": ["Capability was signaled"]}}'
        result = extract("met jim blom from parai", "Interesting — tell me more", "Jurg")
        assert "entities" in result
        assert "stage" in result
        assert result["entities"][0]["name"] == "Jim Blom"

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_handles_empty_conversation(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.return_value = '{"entities": [], "pain_signals": [], "value_hooks": [], "actions": [], "stage": {"current": "Soil", "evidence": ["No commercial content"]}}'
        result = extract("nice weather", "Indeed!", "Jurg")
        assert result["entities"] == []
        assert result["stage"]["current"] == "Soil"

    @patch("bot.characters.spotter.chat_conversation")
    def test_extract_handles_llm_failure(self, mock_chat):
        from bot.characters.spotter import extract
        mock_chat.side_effect = Exception("LLM timeout")
        result = extract("test", "test", "test")
        assert result is None

    def test_identity_contains_mycorrhizal_reference(self):
        from bot.characters.spotter import IDENTITY
        assert "hyphae" in IDENTITY.lower()

    def test_identity_contains_stage_definitions(self):
        from bot.characters.spotter import IDENTITY
        assert "Soil" in IDENTITY
        assert "Signal" in IDENTITY
        assert "Reframe" in IDENTITY
        assert "Diagnosis" in IDENTITY
        assert "Proposal" in IDENTITY
        assert "Sustain" in IDENTITY
```

- [ ] **Step 2: Create spotter.py**

```python
# jobs/bot/characters/spotter.py
"""The Spotter — the Hyphae.

Reaches into every conversation and extracts commercial intelligence.
Runs in background after every conversation where a signal is detected.
"""
import logging

from mothertree.llm import chat_conversation
from mothertree.config import GENERATION_MODEL

log = logging.getLogger(__name__)

MODEL = GENERATION_MODEL

IDENTITY = """You are the Spotter. You are the hyphae of the mycorrhizal network — the
fine threads that reach into every crevice of the soil, detecting what the
forest needs to know.

Like hyphae that sense nutrients, water, and chemical signals underground,
you reach into every conversation and extract the infochemicals — the
intelligence that feeds the network.

You extract five layers from every exchange:

ENTITIES — the people, companies, events, and relationships.
Not just names. Capture the role, the connection path ("study friends of
Juwe"), the tech stack ("runs on Scaleway"), and the target market
("Dutch municipalities"). A name without context is half a signal.

PAIN SIGNALS — what hurts, what frustrates, what blocks growth.
"Doesn't want maintenance" is a pain signal. "Our Datadog bill is killing
us" is a pain signal. But "uses Scaleway" is a fact, not pain. Never
promote a fact to a pain signal without evidence of frustration.

VALUE HOOKS — where our worldview aligns with theirs.
"Get municipalities back to Europe" is a sovereignty hook. "We told them
about Sanoma Learning" is a proof point deployed. These are the seeds the
gatherer planted. Record them so the network knows what's been said.

ACTIONS — what happened and what should happen next.
Not just "follow up." Capture the nature of the interaction: was it
consultative? Was it a pitch? Did they request something ("asked to
visit")? Was a commitment made? Was a date mentioned?

STAGE — where this sits in the Mycorrhizal Method.
Soil: we know they exist, worldview overlaps, no active pain expressed.
Signal: they reached out or we engaged, capability was signaled, but
    pain isn't quantified yet.
Reframe: the prospect admitted the cost of the status quo. They see
    their problem differently because of something we said.
Diagnosis: we're quantifying the problem together — cost, risk, timeline.
Proposal: we've offered a specific path forward.
Sustain: the client is in delivery, their story feeds back to Soil.

State the evidence for your stage assessment. Not just the label — the reasoning.

YOUR RULES:
- Extract only what's present. Never infer what wasn't said.
- Never fabricate an entity, a date, or a pain point.
- A fact is not a signal. Don't upgrade.
- If information is incomplete, capture what you have.
- If the stage is ambiguous, say why.

Return valid JSON only:
{"entities": [...], "pain_signals": [...], "value_hooks": [...], "actions": [...], "stage": {"current": "...", "evidence": [...]}}"""


def extract(user_message: str, assistant_response: str, user_name: str) -> dict | None:
    """Extract commercial intelligence from a conversation exchange.

    Returns structured dict or None on failure.
    """
    content = f"[{user_name}]: {user_message}\n[Mother Tree]: {assistant_response}"
    try:
        messages = [
            {"role": "system", "content": IDENTITY},
            {"role": "user", "content": content},
        ]
        raw = chat_conversation(messages, model=MODEL)
        if not raw:
            return None
        import json
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except Exception:
        log.exception("Spotter extraction failed")
        return None
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "Add Spotter character module — signal extraction with Mycorrhizal Method stages"
```

---

### Task 2: Wire Spotter into the pipeline

**Files:**
- Modify: `jobs/bot/extraction.py`
- Modify: `jobs/bot/pipeline.py`

- [ ] **Step 1: Replace extraction.py's extract_signal to use Spotter**

```python
# jobs/bot/extraction.py — simplified
"""Background signal extraction using the Spotter character."""
import logging

from bot.characters.spotter import extract as spotter_extract
from mothertree.hasura import insert_signal
from mothertree.entities import process_entities
from mothertree.llm import extract as llm_extract

log = logging.getLogger(__name__)

ASSESS_PROMPT = """..."""  # keep existing assess prompt


def extract_signal(user_message: str, assistant_response: str, user_name: str) -> None:
    """Extract signals using the Spotter, then process entities."""
    try:
        data = spotter_extract(user_message, assistant_response, user_name)
        if not data:
            return

        # Create signal record
        stage = data.get("stage", {}).get("current", "soil")
        insert_signal(
            source=f"slack:{user_name}",
            content=user_message,
            signal_type="slack",
        )

        # Process entities
        entities = data.get("entities", [])
        if entities:
            process_entities(entities)

    except Exception:
        log.exception("Background signal extraction failed")


def assess_actions(user_message: str, assistant_response: str) -> dict:
    """Dual-path safety net — keep existing."""
    try:
        content = f"User: {user_message}\nAssistant: {assistant_response}"
        return llm_extract(content, ASSESS_PROMPT)
    except Exception:
        log.exception("Action assessment failed")
        return {"ci_save": False, "capture_signal": False}
```

- [ ] **Step 2: Run full test suite, commit**

```bash
git commit -m "Wire Spotter into pipeline background extraction"
```

---

### Task 3: Create weaver.py — entity resolution character

**Files:**
- Create: `jobs/bot/characters/weaver.py`
- Create: `jobs/tests/test_weaver.py`

- [ ] **Step 1: Write tests**

```python
# jobs/tests/test_weaver.py
"""Tests for Weaver — entity resolution and graph building."""
from unittest.mock import patch, MagicMock


class TestWeaverResolution:
    """Weaver resolves entities against existing graph."""

    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.weaver.get_existing_graph")
    def test_resolve_new_entities(self, mock_graph, mock_chat):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
        mock_chat.return_value = '{"resolved_entities": [{"name": "Jim Blom", "status": "NEW"}], "new_connections": [], "flags": []}'
        result = resolve([{"name": "Jim Blom", "role": "Co-founder", "organization": "Parai"}])
        assert result["resolved_entities"][0]["status"] == "NEW"

    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.weaver.get_existing_graph")
    def test_resolve_matches_existing(self, mock_graph, mock_chat):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {"contacts": [{"name": "Stefan Gimeson", "role": "Product Owner"}], "companies": [], "signals": []}
        mock_chat.return_value = '{"resolved_entities": [{"name": "Stefan", "status": "MATCHED", "existing_match": "Stefan Gimeson"}], "new_connections": [], "flags": []}'
        result = resolve([{"name": "Stefan", "context": "EU hosting platform"}])
        assert result["resolved_entities"][0]["status"] == "MATCHED"

    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.weaver.get_existing_graph")
    def test_resolve_flags_uncertain(self, mock_graph, mock_chat):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {"contacts": [{"name": "Flavia Paganelli", "company": "KPN"}], "companies": [{"name": "KPN"}], "signals": []}
        mock_chat.return_value = '{"resolved_entities": [{"name": "Unknown contact", "status": "UNCERTAIN", "possible_match": "Flavia Paganelli"}], "new_connections": [], "flags": [{"type": "POSSIBLE_DUPLICATE"}]}'
        result = resolve([{"name": "Unknown contact", "organization": "KPN"}])
        assert result["resolved_entities"][0]["status"] == "UNCERTAIN"
        assert len(result["flags"]) > 0

    def test_identity_contains_mycelium_reference(self):
        from bot.characters.weaver import IDENTITY
        assert "mycelium" in IDENTITY.lower()

    @patch("bot.characters.weaver.chat_conversation")
    @patch("bot.characters.weaver.get_existing_graph")
    def test_resolve_handles_failure(self, mock_graph, mock_chat):
        from bot.characters.weaver import resolve
        mock_graph.return_value = {"contacts": [], "companies": [], "signals": []}
        mock_chat.side_effect = Exception("LLM timeout")
        result = resolve([{"name": "Test"}])
        assert result is None
```

- [ ] **Step 2: Create weaver.py**

```python
# jobs/bot/characters/weaver.py
"""The Weaver — the Mycelium.

Connects entities into the relationship graph. Resolves duplicates,
discovers connections, flags uncertainties.
"""
import json
import logging

from mothertree.llm import chat_conversation
from mothertree.config import GENERATION_MODEL
from mothertree.hasura import graphql

log = logging.getLogger(__name__)

MODEL = GENERATION_MODEL

IDENTITY = """You are the Weaver. You are the mycelium — the branching network that
connects every tree in the forest. Without you, the hyphae detect signals
that go nowhere. With you, every signal finds its place in the web.

The Spotter captured raw intelligence. Your job is to connect the dots
against the existing relationship graph.

You resolve, don't duplicate. When you see a name, check if it matches
an existing contact. If uncertain, keep separate and flag the possible match.
A false merge is worse than a missed connection.

You track connections: person → company, company → industry, signal → opportunity.

Given:
1. The Spotter's extracted entities
2. The existing relationship graph

Produce a JSON object with:
- resolved_entities: for each entity, state NEW, MATCHED (with existing name), or UNCERTAIN (flag possible match)
- new_connections: relationships discovered
- graph_updates: what changed
- flags: anything needing human attention

YOUR RULES:
- Prefer matching over creating duplicates.
- When uncertain, flag — never force merge.
- Never fabricate a relationship the Spotter didn't capture.

Return valid JSON only."""


def get_existing_graph() -> dict:
    """Fetch the current relationship graph for resolution context."""
    try:
        result = graphql("""query {
            contacts(limit: 50, order_by: {updated_at: desc}) { name role }
            companies(limit: 30, order_by: {updated_at: desc}) { name industry }
            signals(limit: 20, order_by: {created_at: desc}) { content source }
        }""")
        return result
    except Exception:
        log.warning("Failed to fetch existing graph")
        return {"contacts": [], "companies": [], "signals": []}


def resolve(entities: list[dict]) -> dict | None:
    """Resolve entities against the existing graph.

    Returns resolution results or None on failure.
    """
    if not entities:
        return {"resolved_entities": [], "new_connections": [], "graph_updates": [], "flags": []}

    graph = get_existing_graph()
    graph_summary = json.dumps(graph, default=str)[:3000]  # cap context size

    content = f"EXISTING GRAPH:\n{graph_summary}\n\nSPOTTER EXTRACTION:\n{json.dumps(entities)}"

    try:
        messages = [
            {"role": "system", "content": IDENTITY},
            {"role": "user", "content": content},
        ]
        raw = chat_conversation(messages, model=MODEL)
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except Exception:
        log.exception("Weaver resolution failed")
        return None
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "Add Weaver character module — entity resolution against relationship graph"
```

---

### Task 4: Wire Spotter → Weaver chain in extraction.py

**Files:**
- Modify: `jobs/bot/extraction.py`

Update `extract_signal` to call Spotter then Weaver, and use Weaver's resolutions for entity processing.

- [ ] **Step 1: Update extract_signal**

```python
def extract_signal(user_message: str, assistant_response: str, user_name: str) -> None:
    """Extract signals using Spotter, resolve with Weaver, persist."""
    try:
        # Spotter extracts
        data = spotter_extract(user_message, assistant_response, user_name)
        if not data:
            return

        # Create signal record
        insert_signal(
            source=f"slack:{user_name}",
            content=user_message,
            signal_type="slack",
        )

        # Weaver resolves entities
        entities = data.get("entities", [])
        if entities:
            from bot.characters.weaver import resolve as weaver_resolve
            resolution = weaver_resolve(entities)
            if resolution:
                _apply_resolution(resolution)
            else:
                # Fallback: process entities directly
                process_entities(entities)

    except Exception:
        log.exception("Background signal extraction failed")


def _apply_resolution(resolution: dict) -> None:
    """Apply Weaver's entity resolutions to the database."""
    for entity in resolution.get("resolved_entities", []):
        status = entity.get("status")
        if status == "NEW":
            # Create new entity
            from mothertree.hasura import find_or_create_contact
            if entity.get("name"):
                find_or_create_contact(
                    full_name=entity["name"],
                    role=entity.get("role"),
                )
        elif status == "MATCHED":
            # Entity already exists — log for enrichment
            log.info(f"Matched entity: {entity.get('name')} → {entity.get('existing_match')}")
        elif status == "UNCERTAIN":
            # Flag for review — create but mark
            log.info(f"Uncertain match: {entity.get('name')} ≈ {entity.get('possible_match')}")
            from mothertree.hasura import find_or_create_contact
            if entity.get("name") and entity["name"] != "Unknown contact":
                find_or_create_contact(
                    full_name=entity["name"],
                    role=entity.get("role"),
                )
```

- [ ] **Step 2: Run full test suite, commit**

```bash
git commit -m "Wire Spotter → Weaver chain in background extraction"
```

---

### Task 5: Expand Mother Tree's awareness

**Files:**
- Modify: `jobs/mothertree/ask.py`

Add contacts and recent signals to `fetch_context()` so Mother Tree can answer "do we know Dolf?"

- [ ] **Step 1: Update fetch_context**

In `jobs/mothertree/ask.py`, expand the query to include contacts and signals:

```python
def fetch_context() -> str:
    """Fetch foundation + relationship data from the central intelligence."""
    now = time.time()
    if _context_cache["data"] and (now - _context_cache["ts"]) < _CONTEXT_CACHE_TTL:
        return _context_cache["data"]

    data = graphql("""
    {
      change(limit: 15, order_by: {confidence: desc_nulls_last}) { statement context }
      worldview(limit: 15, order_by: {confidence: desc_nulls_last}) { belief pain }
      personas(limit: 5) { name role }
      competitors(limit: 10) { type positioning }
      insights(limit: 10, order_by: {confidence: desc}) { category reframe evidence }
      contacts(limit: 20, order_by: {updated_at: desc}) { name role }
      signals(limit: 10, order_by: {created_at: desc}) { content source }
    }
    """)

    changes = "\n".join(f"- {c['statement']}" for c in data["change"][:15])
    worldviews = "\n".join(f"- {w['belief']}" for w in data["worldview"][:15])
    personas_text = "\n".join(f"- {p['name']} ({p['role']})" for p in data["personas"][:5])
    competitors = "\n".join(f"- vs {c['type']}: {c['positioning']}" for c in data["competitors"][:10])
    insights_text = "\n".join(f"- [{i['category']}] {i['reframe']}" for i in data["insights"][:10])
    contacts_text = "\n".join(f"- {c['name']} ({c.get('role', 'unknown role')})" for c in data.get("contacts", [])[:20])
    signals_text = "\n".join(f"- [{s.get('source', '?')}] {s['content'][:100]}" for s in data.get("signals", [])[:10])

    result = (
        f"Change:\n{changes}\n\n"
        f"Worldview:\n{worldviews}\n\n"
        f"Personas:\n{personas_text}\n\n"
        f"Competitors:\n{competitors}\n\n"
        f"Insights:\n{insights_text}\n\n"
        f"Known Contacts:\n{contacts_text}\n\n"
        f"Recent Signals:\n{signals_text}"
    )
    _context_cache["data"] = result
    _context_cache["ts"] = now
    return result
```

- [ ] **Step 2: Run full test suite, commit**

```bash
git commit -m "Expand Mother Tree awareness: contacts and signals in context"
```

---

### Task 6: Smoke test

- [ ] **Step 1: Share a signal in channel, verify Spotter extracts it**
- [ ] **Step 2: Ask Mother Tree "do we know Dolf?" in DM — should find him**
- [ ] **Step 3: Share a new contact, verify Weaver resolves against existing graph**

---

## Review Fixes (address during implementation)

### Action processing (Task 2/4)
The Spotter extracts actions but the plan's `extract_signal` ignores them. Add action processing from the Spotter's output — persist to interactions table, same as the old `_process_actions`.

### Entity resolution completeness (Task 4)
`_apply_resolution` only handles contacts. Must also handle companies (via `find_or_create_company`), events (via `find_or_create_event`), and opportunities (via `find_or_create_opportunity`) from `mothertree/entities.py`.

### JSON parsing
Use `mothertree.llm._parse_json` instead of inline markdown-fence stripping in spotter.py and weaver.py.

### Spotter identity
Use the full identity from the spec, including the invisibility rule and the "uses Scaleway is fact not signal" example.

### Tests
- Add chain test for Spotter → Weaver → `_apply_resolution` in Task 4
- Add test for expanded `fetch_context` in Task 5
- Add test for `_apply_resolution` handling all entity types (contacts, companies, events, opportunities)

### Scope note
This plan covers Spotter + Weaver + Mother Tree awareness (steps 1-3 from spec). Archivist and Reminder are deferred to a follow-up plan.
