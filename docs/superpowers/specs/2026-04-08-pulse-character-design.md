# Pulse — The Heartbeat of the Mycorrhizal Network

## Problem

Mother Tree's follow-up system is fragmented. Thread reminders run once daily at 09:00 with mechanical phrasing. Stale contact checks broadcast the same report to all hunters. There is no pipeline stage awareness, no ownership tracking, and no way for the team to snooze or complete a follow-up conversationally. Reminder scheduling fails on relative-to-event expressions ("remind me 3 days before the meeting").

The schema lacks ownership — nothing tracks which team member owns a thread, opportunity, or interaction. The system cannot DM the right person about the right thing.

## Solution

Pulse, the 8th character in the ensemble. An invisible background scanner that checks in on things the team committed to — stale threads, due reminders, stuck pipeline stages. Speaks as Mother Tree. Every nudge carries a reason rooted in the prospect's world (Seth) and earns the right to the next conversation (Lawrence). Never a naked status check.

Runs as a CronJob every 5 minutes with random jitter (0-600 seconds), making it feel almost continuous without process lifecycle management. Three scan types run sequentially. Nudges go as DMs to the person who owns the action.

## Character Identity

```
You are Pulse. You are the heartbeat of the mycorrhizal network — the
steady rhythm that keeps nutrients flowing to where they're needed.

In a healthy forest, the network doesn't wait for a tree to collapse
before sending resources. It monitors, it anticipates, it nudges. A
seedling that hasn't received carbon in two weeks gets attention. A
mature tree hoarding resources gets a gentle signal to share.

You check in on things the team committed to. A signal thread that
went quiet — did the prospect follow through? A meeting prep that was
promised — is it time? A pipeline stage that hasn't moved — worth a
conversation?

You don't nag. You don't alarm. You arrive like a colleague who
remembers what you said last week and asks how it went. Brief, warm,
Dutch-direct.

YOUR RULES:
- Speak as Mother Tree. The team never sees "Pulse."
- One DM per topic. Never batch multiple nudges into one message.
- Never re-summarize the whole thread. Build on what was said.
- If someone snoozed, respect it. Don't nudge before the snooze expires.
- Be brief. Two sentences is usually enough.
- Never say "if you need further assistance." You are a colleague,
  not a helpdesk.
```

**Model:** Mistral Small 3.2 (fast, cheap — Pulse generates short DMs, not deep analysis).

**Tone guidance:** Every message blends Seth's positioning instinct with Lawrence's relationship-building talent. Seth says: give them a reason rooted in their world — a market shift, a competitor move, a new insight. Lawrence says: earn the right to the next conversation — don't chase it, make it worth having. Together: Pulse nudges should make the hunter *want* to follow up, not feel obligated to.

## Scan Types

Three scans run sequentially each cycle.

### 1. Due Reminders

Query `thread_memory` where `remind_after <= now()`.

- Look up the owner via `owner_slack_id`
- Include `remind_context` in the prompt to Pulse for message generation
- Fetch relevant CI context (thread history, contact details, opportunity stage) to give the nudge substance
- DM the owner
- After sending: clear `remind_after` (one-shot reminders)
- Set `pulse_nudged_at` to prevent duplicate nudges within the same scan window

**Example:** "The DSC meeting with Steven and Marco is April 21. You asked for prep help — want me to pull their context and your positioning assets?"

### 2. Stale Threads and Contacts

Two sub-scans:

**Stale threads:** Query `thread_memory` joined with signals/interactions for threads where activity has lapsed beyond the stage-aware threshold. Skip threads with a future `remind_after` (already scheduled) or recent `pulse_nudged_at`.

**Stale contacts:** Query `contacts` by temperature and `last_contact` for contacts that have gone quiet. This catches contacts without signal threads.

**Stage-aware thresholds (calibrated for 12-24 month sales cycles):**

| Stage | Nudge after | Tone |
|-------|-------------|------|
| Soil | 60 days | "Still relevant? Here's a recent signal that connects." |
| Signal | 30 days | "Worth re-engaging? I have context." |
| Reframe | 21 days | Substantive — "what happened after the conversation?" |
| Diagnosis | 14 days | "How's the diagnosis progressing?" |
| Proposal | 21 days | Value-add — "found something relevant to their concern." |
| Converted | 30 days | "How's delivery? Any stories or signals?" |

Note: the schema uses `converted` as the final opportunity stage. The methodology's "Sustain" phase (ongoing delivery relationship) is tracked via the `engagements` table, not the opportunity pipeline.

**Contact temperature thresholds (no pipeline stage):**

| Temperature | Nudge after |
|-------------|-------------|
| Hot | 14 days |
| Warm | 30 days |
| Cold | Not nudged |

- DM the owner of the thread/contact. For contacts without a clear owner, DM all active hunters (current behavior).
- Stale contacts scan excludes contacts that have an active `thread_memory` with a future `remind_after` or recent `pulse_nudged_at` — avoids double-nudging from both thread and contact scans.
- Pulse tries to include a CI nugget — a recent insight, a competitor move, a worldview connection — so the hunter has a reason to reach out, not just a reminder.
- One nudge per stale period. If ignored, the threshold resets from the nudge date. Never more than one nudge per cycle.

**Example:** "The STACKIT thread with Sarah has been quiet for three weeks. Their platform independence concerns align with the sovereignty reframe we extracted last month. Worth a check-in?"

### 3. Pipeline Nudges

Query opportunities where `updated_at` has exceeded the stage threshold (same table as above). These are conversational — framed as an offer to help, not a status demand.

- DM the opportunity owner
- Frame as a conversation starter that deepens CI: the hunter's reply feeds back through the signal pipeline
- Include relevant CI context: what do we know about this company's pain, what positioning assets are relevant

**Example:** "The Parai opportunity has been in Signal for five weeks. From what I know about their sovereignty concerns, a reframe conversation about total cost of dependency might move this forward. Want me to pull context?"

## Snooze and Completion Handling

Responses to Pulse DMs flow through the normal conversation pipeline, not through Pulse.

**Snooze** — "I'll do that tomorrow" / "park it until after KubeCon" / "not now, check back next week"
- Dispatcher recognizes snooze intent
- `resolve_date()` computes the new date (dateparser first, LLM fallback)
- Updates `remind_after` on the relevant record
- Mother Tree confirms: "Got it, I'll check back April 17."

**Completion** — "sent the mail to Hans yesterday" / "met with them, see below"
- Dispatcher recognizes completion/update
- Spotter extracts new signal data
- Weaver resolves entities
- Thread updated: `remind_after` cleared, new interaction recorded
- Mother Tree acknowledges: "Noted. I'll update the STACKIT thread."

**No response** — recipient ignores the DM
- Pulse does not re-nudge on the next cycle
- Stale threshold resets from the nudge date
- If it goes stale again after a full cycle, Pulse nudges once more
- Never more than one nudge per stale period

## Smart Date Resolution

Two-tier date parsing in the conversation pipeline. Pulse reads the computed dates, it doesn't calculate them.

**Tier 1: dateparser (instant, free)**
Handles: "tomorrow", "April 21", "volgende week dinsdag", "in 3 weeks", "morgen"
Already deployed.

**Tier 2: LLM fallback (Mistral Small, fast)**
Fires when dateparser returns `None` and thread context is available:

```
The user said: "remind me 3 or 4 days before the meeting"

Context from this thread:
- Meeting: April 21, 2026 with Steven Klompenhouwer and Marco van der Veer
- Today: 2026-04-08

Resolve to an absolute date. If ambiguous, pick the earlier date
(more preparation time is better than less).

Return JSON only: {"date": "YYYY-MM-DD", "reasoning": "..."}
```

**Location:** `jobs/mothertree/dates.py` — `resolve_date(text, context=None) -> str | None`
- `_parse_date()` in `extraction.py` becomes a thin wrapper calling `resolve_date(text)` (no context = dateparser only, backward compatible)
- Conversation pipeline calls `resolve_date(text, thread_context)` for reminder requests

## Schema Changes

Ownership tracking and Pulse state, applied to the existing schema. CI data will be re-ingested after migration.

```sql
-- Ownership: who captured/owns this
ALTER TABLE thread_memory ADD COLUMN owner_slack_id TEXT;
ALTER TABLE opportunities ADD COLUMN owner_slack_id TEXT;
ALTER TABLE interactions ADD COLUMN slack_user_id TEXT;
ALTER TABLE contacts ADD COLUMN owner_slack_id TEXT;

-- Pulse state: when was this last nudged
ALTER TABLE thread_memory ADD COLUMN pulse_nudged_at TIMESTAMPTZ;
ALTER TABLE opportunities ADD COLUMN pulse_nudged_at TIMESTAMPTZ;
ALTER TABLE contacts ADD COLUMN pulse_nudged_at TIMESTAMPTZ;

-- Indexes for Pulse scans
CREATE INDEX idx_thread_memory_remind_after
    ON thread_memory(remind_after) WHERE remind_after IS NOT NULL;
CREATE INDEX idx_thread_memory_pulse_nudged
    ON thread_memory(pulse_nudged_at);
CREATE INDEX idx_opportunities_owner
    ON opportunities(owner_slack_id);
CREATE INDEX idx_opportunities_pulse_nudged
    ON opportunities(pulse_nudged_at);
CREATE INDEX idx_contacts_owner
    ON contacts(owner_slack_id);
CREATE INDEX idx_contacts_pulse_nudged
    ON contacts(pulse_nudged_at);
```

**Populating `contacts.owner_slack_id`:** Auto-set from the most recent interaction's `slack_user_id`. When a hunter logs an interaction with a contact, that contact's `owner_slack_id` updates to the hunter. This means ownership follows activity — whoever last engaged owns the follow-up.

**Populating ownership:** The conversation pipeline passes `slack_user_id` through to all creation calls. For existing data: `signals.source` contains "slack:Username" — match to enrollment records during backfill.

## Pydantic Models

Introduced with Pulse, defined for all characters, migrated incrementally.

**File:** `jobs/mothertree/models.py`

```python
# -- Pulse --
class PulseNudge(BaseModel):
    recipient_slack_id: str
    message: str
    nudge_type: Literal["reminder", "stale_thread", "stale_contact", "pipeline"]
    thread_ts: str | None = None
    context: dict = {}

class SnoozeParsed(BaseModel):
    new_date: str
    reasoning: str

class DateResolution(BaseModel):
    date: str
    reasoning: str
    tier: Literal["dateparser", "llm"]

# -- Existing characters (defined now, enforced incrementally) --
class DispatchResult(BaseModel):
    character: str
    intent: str
    annotation: str | None = None
    must_respond: bool
    training_mode: bool
    signal_flag: bool
    clean_text: str
    exercise_pending: dict | None = None

class SpotterExtraction(BaseModel):
    entities: list[dict]
    pain_signals: list[dict]
    value_hooks: list[dict]
    actions: list[dict]
    stage: dict

class WeaverResolution(BaseModel):
    resolved: list[dict]
    flags: list[str]
```

## Infrastructure

**New CronJob:** `pulse-scan`
- Schedule: `*/5 * * * *`
- Image: `jobs` (shared with all CronJobs)
- Entry point: `mothertree pulse scan`
- `concurrencyPolicy: Forbid`
- Random sleep at start: `time.sleep(random.randint(0, 600))`
- Slack client: `WebClient(token=SLACK_BOT_TOKEN)` from Kubernetes Secret

**Retires:**
- `deploy/cronjobs/thread-reminders.yaml` — subsumed by Pulse due reminders
- `deploy/cronjobs/discipline-stale-check.yaml` — subsumed by Pulse stale scan
- `jobs/reminders/thread_reminders.py` — logic moves to `jobs/pulse/scanner.py`
- `jobs/discipline/stale_check.py` — logic moves to `jobs/pulse/scanner.py`

## Files

**New:**

| File | Responsibility |
|------|---------------|
| `jobs/bot/characters/pulse.py` | Character identity, prompt, message generation |
| `jobs/pulse/__init__.py` | Package init |
| `jobs/pulse/scanner.py` | Three scan functions + DM delivery |
| `jobs/mothertree/dates.py` | Smart date resolution (dateparser + LLM) |
| `jobs/mothertree/models.py` | Pydantic models for all character I/O |
| `deploy/cronjobs/pulse-scan.yaml` | CronJob manifest |

**Modified:**

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add ownership + pulse columns |
| `jobs/bot/extraction.py` | `_parse_date()` wraps `resolve_date()` |
| `jobs/bot/pipeline.py` | Pass `slack_user_id` to creation calls, snooze/completion detection |
| `jobs/bot/characters/dispatcher.py` | Snooze and completion intent detection |
| `jobs/cli.py` | Add `mothertree pulse scan` command |
| `jobs/mothertree/graphql_client.py` | Pulse scan queries, ownership writes |

**Removed:**

| File | Reason |
|------|--------|
| `deploy/cronjobs/thread-reminders.yaml` | Subsumed by pulse-scan |
| `deploy/cronjobs/discipline-stale-check.yaml` | Subsumed by pulse-scan |
| `jobs/reminders/thread_reminders.py` | Logic in pulse/scanner.py |
| `jobs/discipline/stale_check.py` | Logic in pulse/scanner.py |
