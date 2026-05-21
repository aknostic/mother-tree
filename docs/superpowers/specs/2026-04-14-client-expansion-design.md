# Client Expansion Infrastructure

## Problem

Mother Tree tracks signals, contacts, and opportunities but has no structured view of existing client accounts. Hunters can't see white space, expansion triggers go unnoticed, and there's no quarterly review discipline. Expansion from existing accounts is 3-5x more efficient than new logos — this infrastructure makes it systematic.

## Decision

Three layers, built on one data model:

1. **Account plans** — strategic view per client (white space, triggers, services, strategy). Populated hybrid: Mother Tree drafts from data, hunter fills gaps conversationally.
2. **Expansion trigger detection** — Pulse scanner pattern-matches for role changes, contract renewal proximity, signal density, and stale plans. Nudges the account owner.
3. **QBR rhythm** — quarterly scheduled briefing per account plus on-demand review. Same synthesis pattern as weekly/monthly reviews.

## Schema

### Modified tables

**`companies`** — add client account fields:

```sql
ALTER TABLE companies ADD COLUMN IF NOT EXISTS client_since DATE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contract_value TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS services TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
```

### New tables

**`account_plans`** — strategic layer, one per company:

```sql
CREATE TABLE IF NOT EXISTS account_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) UNIQUE,
    white_space TEXT,
    expansion_triggers TEXT[],
    strategy TEXT,
    qbr_notes TEXT,
    qbr_at TIMESTAMPTZ,
    next_qbr DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_account_plans_company ON account_plans(company_id);
CREATE INDEX IF NOT EXISTS idx_account_plans_next_qbr ON account_plans(next_qbr) WHERE next_qbr IS NOT NULL;
CREATE TRIGGER account_plans_updated_at BEFORE UPDATE ON account_plans FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

`UNIQUE` on `company_id` — one plan per company. The strategic layer that changes quarterly. Contacts are already linked to companies via `company_id` FK — they serve as the stakeholder map.

## Account Plan Population (Hybrid)

Hunter says "account plan Sanoma Learning" in DM. Mother Tree:

1. Find company by name (fuzzy match via existing `search_contacts_fuzzy` pattern)
2. Gather available data: contacts linked to company, interactions, signals, opportunities, current services
3. Draft a plan summary: "Here's what I know about Sanoma Learning: [stakeholders, services, recent activity]. What's the white space? What triggers should I watch for?"
4. Hunter fills gaps conversationally — Mother Tree extracts structured fields from the response
5. Store/update `account_plans` record

If the company doesn't exist, create it first.

## Expansion Trigger Detection

New scan in `pulse/scanner.py`: `scan_expansion_triggers`. Runs alongside existing scans (every 5 minutes, same CronJob).

Pattern matches (no LLM, just date/count logic):
- **Contract renewal proximity** — `account_plans.next_qbr` approaching within 14 days or past due
- **Signal density** — 3+ signals from the same company within 7 days (something's happening)
- **Stale account plan** — `account_plans.updated_at` older than 90 days for a company with `client_since` set
- **Role changes** — signals or interactions mentioning role changes for contacts at client companies (detected by Spotter, matched by Weaver)

Each trigger generates a Pulse nudge (type `expansion`) to the account owner via DM. Uses existing `generate_nudge` with new nudge type.

Only nudge per company once per `MIN_NUDGE_INTERVAL_DAYS` (7 days), same as existing Pulse behavior. Needs a `pulse_nudged_at` column on `account_plans` or `companies`.

```sql
ALTER TABLE companies ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;
```

## Service Meetings (Monthly, per engagement)

Monthly operational review per active engagement. Engagement owners run them (e.g., JJ, Ilja, Tero at Sanoma Learning; Ferran at Consumentenbond).

### Schema

Add to `engagements` table:

```sql
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS next_service_meeting DATE;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS last_service_meeting TIMESTAMPTZ;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS service_meeting_notes TEXT;
```

### Prep (1 day before)

When `next_service_meeting` is within 1 day, generate a prep briefing:
1. Gather: recent interactions, signals, open issues for that engagement's company
2. Include: contact activity for the engagement owner's contacts
3. Seth synthesizes a service meeting prep: delivery status, open items, things to raise
4. DM the engagement owner

### Debrief (after meeting)

Hunter pastes raw service meeting notes in DM: `service meeting [notes]`. Mother Tree:
1. Runs existing debrief extraction pipeline (entities, actions, pain signals, value hooks)
2. Anonymization approval flow — hunter reviews sensitive items before ingestion
3. Stores extracted data against the engagement
4. Updates `last_service_meeting`, advances `next_service_meeting` by 1 month
5. Stores summary in `service_meeting_notes`

### Cadence

Monthly per active engagement. Tracked via `next_service_meeting` on `engagements`. The discipline CronJob checks both service meetings and QBRs.

## QBR Rhythm (Quarterly, per account)

Strategic review at the company level. Includes engagement owners AND their superiors (the decision makers — e.g., Albert, Mariusz, Marja at Sanoma Learning).

### Scheduled (quarterly)

New module: `jobs/discipline/qbr_review.py`. Runs as a monthly CronJob (checks if any QBRs are due).

Flow:
1. Query `account_plans` where `next_qbr <= now()`
2. For each due plan, gather account state: contacts (stakeholder hierarchy — both delivery and strategic contacts), interactions (last 90 days), signals (last 90 days), opportunities, current services, engagement history, service meeting summaries
3. Seth synthesizes a QBR briefing: what happened this quarter, what's working, what's stalled, where's the white space, recommended actions. Frames for the strategic audience, not the delivery team.
4. Store synthesis in `account_plans.qbr_notes`, update `qbr_at` to now
5. DM the account owner (via `get_slack_user_id` reverse lookup)
6. Advance `next_qbr` by 3 months

### On demand

Hunter DMs "review Sanoma Learning". Same synthesis logic, returns inline. Does NOT advance `next_qbr` — that's the scheduled rhythm's job.

Works in channels too: "@Mother Tree review Sanoma Learning".

## Bot Commands

### DM commands (detect.py)

- `review <company>` — on-demand QBR synthesis for a company
- `account plan <company>` — create or update account plan (conversational)
- `accounts` — list all companies with account plans
- `service meeting <notes>` — debrief from a service meeting (anonymization flow)

### Pipeline handlers

- `type: "account_review"` — triggers QBR synthesis, returns briefing
- `type: "account_plan"` — starts conversational plan creation/update
- `type: "account_list"` — returns formatted list of accounts
- `type: "service_meeting"` — routes to debrief extraction with anonymization

### Admin context

Admin commands work on accounts too: `enroll <email> as hunter` assigns a user who can then own accounts.

## CLI

```
mothertree accounts list                    — list all companies with account plans
mothertree accounts review <company>        — generate QBR briefing
```

## GraphQL Functions

Add to `graphql_client.py`:

```python
# --- Account plans ---
def get_account_plan(company_id: str) -> dict | None
def create_account_plan(company_id: str, **fields) -> dict
def update_account_plan(plan_id: str, **fields) -> None
def get_due_qbrs() -> list[dict]  # next_qbr <= now()
def get_accounts_with_plans() -> list[dict]  # companies JOIN account_plans

# --- Company enrichment ---
def update_company_client_fields(company_id: str, **fields) -> None
def get_client_companies() -> list[dict]  # companies WHERE client_since IS NOT NULL
```

## CronJob

New CronJob manifest: `deploy/cronjobs/discipline-qbr-review.yaml`

Schedule: `0 8 1 * *` (1st of month, 08:00 — same day as monthly retro but runs independently). Checks both `account_plans.next_qbr` and `engagements.next_service_meeting` dates.

## Testing

- Account plan CRUD: create, update, retrieve
- QBR synthesis: mock company data, verify briefing generated
- Service meeting prep: verify prep generated for due meetings
- Service meeting debrief: verify extraction + anonymization + storage
- Expansion triggers: test each pattern (signal density, stale plan, QBR approaching)
- Pulse integration: verify nudge generated and sent to owner
- Bot commands: detect "review X", "account plan X", "accounts", "service meeting"
- CLI: list, review

## File Inventory

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add `account_plans` table, ALTER `companies` + `engagements` |
| `jobs/mothertree/graphql_client.py` | Account plan + company + engagement CRUD functions |
| `jobs/bot/detect.py` | Detect `review`, `account plan`, `accounts`, `service meeting` commands |
| `jobs/bot/pipeline.py` | Handle account_review, account_plan, account_list, service_meeting annotations |
| `jobs/pulse/scanner.py` | Add `scan_expansion_triggers` |
| `jobs/discipline/qbr_review.py` | New: QBR synthesis + service meeting prep/tracking |
| `jobs/cli.py` | Add `accounts` subcommand |
| `deploy/cronjobs/discipline-qbr-review.yaml` | New: monthly QBR + service meeting CronJob |
| `deploy/kustomization.yaml` | Add CronJob reference |
| `jobs/tests/test_account_plans.py` | New: account plan + service meeting tests |
| `jobs/tests/test_qbr.py` | New: QBR synthesis tests |
