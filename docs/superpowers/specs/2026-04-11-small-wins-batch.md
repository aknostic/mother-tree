# Small Wins Batch

## Problem

Mother Tree has accumulated a backlog of small improvements that individually don't justify a design cycle but collectively raise the platform's quality and unlock service meeting ingestion — the prerequisite for the commercial practices push.

## 1. Debrief Ingestion with Sensitivity Gate

Service meeting debriefs contain commercial intelligence (client pain, stakeholder dynamics, expansion signals) but also sensitive material (performance commentary about team members). Consultants are citizens on the platform — their performance assessments must not enter the shared CI pool.

### Trigger

User says "debrief" (or "meeting notes", "service meeting") in a DM or private channel, followed by pasted content. The dispatcher detects the keyword and routes to Mother Tree with annotation `{type: "debrief"}`.

Detection: add `debrief`, `meeting notes`, `service meeting` to a new pattern set in the dispatcher, checked in DMs before freeform fallback.

### Extraction

Spotter runs with a debrief-specific system prompt addition that extracts commercial intelligence AND flags sensitive parts in one pass. Same categories as normal signal extraction (entities, pain signals, value hooks, actions, stage) plus a `sensitive` boolean on each item.

**What counts as sensitive:** Anything that names or identifies an internal team member in a performance context. "The migration went well" → not sensitive. "Pim struggled with the client presentation" → sensitive. "A team member raised concerns about timeline" → not sensitive (already anonymized by the person who wrote it).

Spotter prompt addition for debrief mode:

```
You are extracting commercial intelligence from a service meeting debrief.

Extract the same categories as usual, but also flag sensitive items.
An item is sensitive if it names or identifies an internal team member
in a performance context — positive or negative.

Factual observations about project status are not sensitive.
Client-facing information is not sensitive.
Internal team performance commentary IS sensitive.

For each extracted item, add: "sensitive": true/false
```

### Approval Flow

1. Mother Tree presents the extraction as a preview message in the DM/thread
2. Sensitive items are marked: `⚠️ [name] — [the flagged content]`
3. Non-sensitive items shown normally
4. Message ends with: "Reply *approve* to ingest, *edit* to remove items, or *skip* to discard."
5. **Approve** → all non-sensitive items enter CI via Weaver → signal pipeline. Sensitive items are dropped.
6. **Edit** → Mother Tree asks which items to remove (by number). User replies with numbers. Remaining items enter CI.
7. **Skip** → nothing stored, conversation continues.

### State Tracking

The approval loop spans multiple messages. Track pending debrief state in the DM conversation memory (`dm_conversations.messages` JSONB). When Spotter returns the extraction:

1. Store the extraction result on the DM conversation record itself as a `pending_debrief` JSONB field (not in the messages array — avoids being trimmed by message windowing)
2. On the user's next message, check if `pending_debrief` is non-null on the conversation
3. Process the response (approve/edit/skip), then set `pending_debrief` to null

Schema addition:
```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_debrief JSONB;
```

This keeps pending state safe from memory trimming and clearly separate from conversation history.

### Storage

Approved items flow through the normal pipeline: Weaver resolves entities, signals are inserted, contacts/companies are created or enriched. The signal's `source` field records `"debrief:slack_user_name"` to distinguish from live conversation signals.

### Files

| File | Change |
|------|--------|
| `jobs/bot/characters/dispatcher.py` | Add debrief keyword detection in DMs |
| `jobs/bot/characters/spotter.py` | Add debrief prompt extension, `sensitive` flag in output |
| `jobs/bot/pipeline.py` | Handle debrief annotation: extract → preview → approval loop |
| `jobs/bot/extraction.py` | Support `debrief=True` flag to use debrief Spotter prompt |

---

## 2. Pulse: CI Context in Nudges

Stale thread and contact nudges are generic — they tell hunters something went quiet but don't give them a reason to act. The spec says nudges should include a CI nugget.

### Change

In `pulse/scanner.py`, before calling `generate_nudge()` for stale threads and contacts, run a semantic search against insights + worldview tables using the contact or company name as query. Pass the top 2-3 results as `ci_context`.

For stale threads: extract contact/company names from thread messages, search insights.
For stale contacts: use the contact name + company name as query.
For pipeline nudges: already passes `opp.notes` as context — enhance with semantic search on the opportunity title + company.

### Files

| File | Change |
|------|--------|
| `jobs/pulse/scanner.py` | Add `_fetch_ci_context(query)` helper, call before `generate_nudge()` |
| `jobs/mothertree/graphql_client.py` | Reuse existing `search_similar()` for insights + worldview |

---

## 3. Pulse: Stage-Aware Stale Thread Thresholds

`scan_stale_threads()` uses a hardcoded 14-day cutoff. Should vary by pipeline stage.

### Change

Instead of `get_stale_threads(days=14)`, fetch all threads not updated in 14 days (the minimum threshold). Then for each, look up the associated opportunity (via contact or company linkage in thread messages) to get the pipeline stage. Apply the existing `STAGE_THRESHOLDS` dict in `scanner.py` (already defined, just unused by stale threads) — threads in early stages (soil: 60 days, signal: 30 days) get longer grace periods. Threads without an opportunity link keep 14-day default.

### Files

| File | Change |
|------|--------|
| `jobs/pulse/scanner.py` | `scan_stale_threads()` — fetch opportunities for stage lookup, filter by stage threshold |

---

## 4. Pulse: interactions.slack_user_id Passthrough

The schema has `slack_user_id` on the interactions table but it's never populated.

### Change

In `extraction.py`'s `_process_actions()`, accept and pass `slack_user_id` when creating interaction records via GraphQL. The pipeline already has the user ID — just needs threading through.

### Files

| File | Change |
|------|--------|
| `jobs/bot/extraction.py` | `_process_actions()` accepts `slack_user_id`, passes to `insert_interaction()` |
| `jobs/mothertree/graphql_client.py` | `insert_interaction()` mutation includes `slackUserId` |
| `jobs/bot/pipeline.py` | Pass `user_slack_id` to `_background_extract()` → `_process_actions()` |

---

## 5. Contact Deduplication

Weaver creates duplicate contacts when names vary ("Jurg" vs "Jurg van Vliet").

### Change

Before creating a new contact in Weaver's resolution flow, run a fuzzy name match against existing contacts:

1. Normalize: lowercase, strip diacritics
2. Substring check: if one name (4+ characters) is contained in another ("Jurg" in "Jurg van Vliet"), AND same company → treat as match. Short names (< 4 chars) require exact match to avoid false positives ("Jan" ≠ "Janet").
3. Same company + similar name → high confidence match
4. Ambiguous matches (similar but not subset) → flag as UNCERTAIN, don't auto-merge

Applied at contact creation time in `_apply_resolution()` in `extraction.py`, not as a batch job.

### Files

| File | Change |
|------|--------|
| `jobs/bot/extraction.py` | `_apply_resolution()` — fuzzy match before creating contact |
| `jobs/mothertree/graphql_client.py` | Add `search_contacts_fuzzy(name, company_id)` query |

---

## 6. Response Verbosity Reduction

Mother Tree's responses are often longer than needed.

### Change

Replace the existing character limit (2500 chars) in `SLACK_FORMATTING_RULES` in `base.py` with a tighter word-based constraint:

```
Keep responses under 150 words unless the user asks for detail or you
are delivering training or factual content (status, stats, progress).
Prefer one clear paragraph over multiple sections. No bullet lists
unless comparing options.
```

Training content (exercises, explanations, feedback) is exempt — those need space. Remove the old "under 2500 characters" rule to avoid conflicting constraints.

### Files

| File | Change |
|------|--------|
| `jobs/bot/characters/base.py` | Add verbosity rule to shared prompt rules |

---

## 7. Onboarding Profile Collection

When users share personal details in DM, Mother Tree should parse and save them.

### Detection

Dispatcher detects profile-sharing patterns in DMs: email addresses, calendar URLs, day-of-week mentions ("I work Tuesday through Thursday"), phone numbers. Routes with annotation `{type: "profile_update", "text": clean}`.

### Extraction

Mother Tree extracts structured fields via Mistral Small:

```json
{
  "email": "jurg@aknostic.com",
  "calendar_url": null,
  "working_days": ["tuesday", "wednesday", "thursday"],
  "phone": null
}
```

Only non-null fields update the enrollment record. Mother Tree confirms: "Got it — saved your email as jurg@aknostic.com."

### Schema

```sql
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE enrollment ADD COLUMN IF NOT EXISTS working_days TEXT[];
```

`calendar_url` already exists on enrollment.

### Files

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add email, phone, working_days to enrollment |
| `jobs/bot/characters/dispatcher.py` | Detect profile-sharing patterns in DMs |
| `jobs/bot/pipeline.py` | Handle profile_update annotation: extract → confirm → save |
| `jobs/mothertree/graphql_client.py` | Add `update_enrollment_profile()` mutation |

---

## 8. Enrollment Approval

New enrollments require admin approval. With sensitive debrief data in the system, role assignment needs a gate.

### Flow

1. User says "enroll" (or "enroll as hunter") in DM
2. Mother Tree acknowledges: "I've sent your enrollment request to the admin."
3. Admin gets a DM: "**Pim** wants to enroll as a **hunter**. Reply *approve*, *reject*, or suggest a role (*approve as citizen*)."
4. Admin replies → Mother Tree processes:
   - **approve** → enrollment created, user gets welcome message
   - **approve as [role]** → enrollment created with admin's chosen role
   - **reject** → user gets "Your request wasn't approved. Talk to [admin name] if you have questions."
5. Mother Tree confirms to admin: "Pim enrolled as hunter."

### Pending Requests

Store pending enrollment requests in a new table:

```sql
CREATE TABLE enrollment_requests (
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
```

### Config

```python
# In mothertree/config.py
ADMIN_SLACK_ID = os.environ.get("ADMIN_SLACK_ID", "")
```

Added to CronJob and bot deployment env vars from a Kubernetes Secret.

### Changes to Existing Enroll Flow

The current `dispatch()` routes "enroll" to Mother Tree which calls `training.operations.enroll()` directly. Change: instead of immediate enrollment, create an enrollment_request and DM the admin. The admin's reply triggers the actual enrollment.

The CLI `mothertree train enroll` bypasses approval — it's an admin action already.

**Timeout:** If the admin doesn't respond within 48 hours, the request expires. The user gets: "Your enrollment request expired. Try again or reach out to the admin directly." Add a CLI command `mothertree train pending` that lists open requests for the admin to review. Timeout enforcement: Pulse scanner checks for expired requests during each scan cycle (cheap query, piggybacks on existing CronJob).

### Files

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add enrollment_requests table |
| `jobs/mothertree/config.py` | Add ADMIN_SLACK_ID |
| `jobs/bot/pipeline.py` | Enrollment annotation creates request + DMs admin instead of direct enroll |
| `jobs/bot/characters/dispatcher.py` | Admin approval/rejection intent detection |
| `jobs/mothertree/graphql_client.py` | CRUD for enrollment_requests |
| `deploy/base/slack-bot.yaml` | Add ADMIN_SLACK_ID env var |

---

## 9. PostGraphile Cleanup

Remove old Hasura deployment and service files. Keep `admin-secret.yaml` — it's still referenced by PostGraphile, the Slack bot, and all CronJobs.

### Files

| File | Change |
|------|--------|
| `deploy/hasura/deployment.yaml` | Remove (old Hasura deployment) |
| `deploy/hasura/service.yaml` | Remove (old Hasura service) |

---

## 10. Handbook — Feature Awareness, Help, and Onboarding

The system is growing. Adding features without helping people understand them — including their impact — is how platforms become complex and unused.

### The Handbook

A directory of markdown files (`jobs/handbook/`), one per feature or concept. Each file has YAML frontmatter for metadata and a body with the full explanation.

```markdown
---
key: debrief_ingestion
roles: [hunter, gatherer, farmer]
trigger: first_debrief_attempt
onboarding: false
onboarding_order: null
topic: intelligence
summary: Paste service meeting notes and Mother Tree extracts commercial intelligence with a sensitivity check.
---

Say "debrief" in a DM followed by your meeting notes. Mother Tree extracts
commercial intelligence — client pain, stakeholder dynamics, expansion signals —
and shows you a preview. Sensitive items (performance commentary about team
members) are flagged. You approve, edit, or skip before anything enters the system.

Consultants on the platform never see flagged content.
```

### Frontmatter Fields

| Field | Type | Purpose |
|-------|------|---------|
| `key` | string | Unique identifier, used in `help_delivered` tracking |
| `roles` | list | Which roles see this entry (hunter, gatherer, farmer, citizen) |
| `trigger` | string or null | When to surface contextually (e.g., `first_pulse_nudge`, `enrollment_complete`) |
| `onboarding` | bool | Include in the welcome sequence |
| `onboarding_order` | int or null | Position in the welcome sequence |
| `topic` | string | Logical grouping for the help command (e.g., intelligence, training, rhythm, admin) |
| `summary` | string | One-line description for help command listings |

### Three Uses, One Source

**1. Contextual tips** — When a trigger fires (first Pulse nudge, first debrief attempt, post-enrollment), Mother Tree checks `help_delivered` for the user + key. If not yet shown, delivers the summary naturally woven into conversation — not a help dump. Records delivery.

**2. Help command** — "help" in DM returns all entries for the user's role, grouped by `topic`. Each entry shows the `summary`. User can ask for detail on any topic ("help debrief") to get the full body.

**3. Onboarding sequence** — After enrollment approval, Mother Tree delivers `onboarding: true` entries in `onboarding_order`, one per interaction over the first few days. The welcome message is the first entry. Subsequent entries are delivered when the user says "next" or after a natural pause.

### Delivery Tracking

```sql
CREATE TABLE help_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slack_user_id TEXT NOT NULL,
    help_key TEXT NOT NULL,
    delivered_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (slack_user_id, help_key)
);
```

Contextual help checks this table before delivering. The help command ignores it — explicit lookups always show everything.

### Feature Catalog

Full scan of existing and new features, organized by topic:

**Topic: Intelligence**
- `what_is_mother_tree` — What Mother Tree is and how it helps (onboarding: 1)
- `signal_capture` — How signals are captured from conversations
- `debrief_ingestion` — Service meeting debrief with sensitivity gate (new)
- `briefing` — Cross-table briefing on a topic, company, or person
- `ask_personas` — Ask Seth (positioning) or Lawrence (selling) for perspective

**Topic: Training**
- `training_overview` — How training works, stages, progression (onboarding: 2)
- `training_commands` — next, go, practice, A/B/C answers
- `training_scoring` — How exercises are scored and what the feedback means
- `citizen_inspiration` — Lighter inspiration flow for citizens

**Topic: Rhythm**
- `pulse_nudges` — What Pulse is and why you get check-ins (onboarding: 3 for hunters)
- `pulse_snooze` — How to snooze or complete a nudge
- `weekly_review` — Monday pipeline review
- `monthly_retro` — Monthly retrospective
- `calendar_prep` — Meeting prep and debrief from calendar

**Topic: Contacts & Pipeline**
- `contacts_overview` — How contacts and companies are tracked
- `opportunities` — Pipeline stages (soil → converted)
- `temperature` — Hot/warm/cold contact status

**Topic: Getting Started**
- `enrollment` — How to enroll and what roles mean (onboarding: 0)
- `profile_setup` — Share your email, calendar, working days (onboarding: 4)
- `help_command` — How to get help anytime

**Topic: Admin**
- `enrollment_approval` — How to approve/reject enrollment requests (admin only)
- `pending_requests` — Reviewing pending enrollments

### Loading

At bot startup, load all `.md` files from `jobs/handbook/`, parse frontmatter with `python-frontmatter`, index by key, role, trigger, and topic. Cached in memory — the handbook is small and changes only with deploys.

### Files

| File | Change |
|------|--------|
| `jobs/handbook/*.md` | One file per feature/concept (~20 files) |
| `deploy/database/schema.sql` | Add `help_delivered` table |
| `jobs/bot/characters/dispatcher.py` | Route "help" and "help [topic]" commands |
| `jobs/bot/pipeline.py` | Check triggers after response delivery, deliver contextual help |
| `jobs/mothertree/handbook.py` | Load, index, and query handbook entries |
| `jobs/mothertree/graphql_client.py` | CRUD for `help_delivered` |
| `requirements.txt` | Add `python-frontmatter` |
