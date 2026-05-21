# Seed Reminders

Plant a reminder in another team member's thread memory. The pulse scanner delivers it as a DM when the time comes.

## Context

Mother Tree already sends DMs (training nudges, stale contact nudges, enrollment expiry). The pulse scanner runs every 5 minutes and fires due reminders from `thread_memory.remind_after`. Snooze and completion detection exist in the dispatcher but are not wired up.

What is missing: the ability for one user to create a reminder targeting another user, natural language date parsing, and handlers for snooze/completion responses.

## Constraints

- Seeds are strictly between working roles: hunters, gatherers, farmers. Citizens cannot plant or receive.
- No new tables. Seeds are `thread_memory` rows where `thread_ts IS NULL`.
- The pulse scanner already processes due reminders. Minimal changes needed.

## Design

### Schema migration

Make `thread_ts` and `channel_id` nullable. Add `originator_id`.

```sql
-- Make thread_ts and channel_id nullable for seed reminders
ALTER TABLE thread_memory ALTER COLUMN thread_ts DROP NOT NULL;
ALTER TABLE thread_memory ALTER COLUMN channel_id DROP NOT NULL;

-- Drop the unique constraint on thread_ts (nullable values break uniqueness semantics)
ALTER TABLE thread_memory DROP CONSTRAINT IF EXISTS thread_memory_thread_ts_key;
-- Re-add as partial unique index (only for non-null thread_ts)
CREATE UNIQUE INDEX IF NOT EXISTS thread_memory_thread_ts_unique
    ON thread_memory(thread_ts) WHERE thread_ts IS NOT NULL;

-- Who planted the seed
ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS originator_id UUID REFERENCES users(id);
```

PostGraphile picks this up automatically. No Hasura metadata changes needed.

### User resolution by name

New function in `graphql_client.py`:

```python
def get_non_citizen_by_name(name: str) -> list[dict]:
    """Find active non-citizen users matching a first name (case-insensitive)."""
    result = graphql("""
    query {
        allUsersList(condition: {active: true}, filter: {
            role: {in: ["hunter", "gatherer", "farmer"]}
        }) {
            id email name role
        }
    }
    """)
    users = result.get("allUsersList", [])
    needle = name.lower()
    return [u for u in users if u["name"].lower().split()[0] == needle]
```

If zero matches: "I don't know anyone called {name}."
If multiple matches: "I know a few people called {name}: {list}. Which one?"
If one match: proceed.

### Date parsing

Reuse `mothertree.dates.resolve_date()` — already two-tier:
- Tier 1: `dateparser` library (instant, free) — handles "tomorrow", "morgen", "donderdag", "in 3 weeks", "volgende week", all Dutch weekdays, natural language.
- Tier 2: LLM fallback (Mistral Small) — fires when dateparser fails and context is available. Handles "3 days before the meeting".

`resolve_date()` returns a `DateResolution(date="YYYY-MM-DD", reasoning=..., tier=...)`. The seed handler calls it with the `when_text` and optionally thread context for LLM fallback.

Default fire time: 09:00 Europe/Amsterdam on the resolved date. If `resolve_date()` returns None, ask.

### Dispatcher changes

New pattern in `dispatch()`, checked in DM context after admin commands (section 2a) and **before** global commands (section 2) and snooze detection (section 4b). This ordering matters: "remind Pim to send the deck tomorrow" contains both "remind" and "tomorrow", which would falsely match the snooze pattern if checked later. Only matches for non-citizen users.

Pattern: `remind <name> (to|about|that) <context> (tomorrow|thursday|next week|in N days|...)`

Returns:
```python
{
    "character": "mother_tree",
    "intent": "seed",
    "annotation": {
        "type": "seed",
        "target_name": "pim",
        "remind_context": "send the Sanoma deck to Charlotte",
        "when_text": "thursday",
    },
    "must_respond": True,
}
```

### Pipeline handler

In `_get_response()`, before the default Mother Tree fallback:

```python
if annotation and annotation.get("type") == "seed":
    return _handle_seed(annotation, user)
```

`_handle_seed`:
1. Resolve target name via `get_non_citizen_by_name()`. If ambiguous, return question.
2. Parse date from `when_text`. If unrecognized, ask.
3. Check planter is non-citizen. If citizen, reject.
4. Create thread_memory row: `thread_ts=None, channel_id=None, owner_user_id=target, originator_id=planter, remind_after=parsed_date, remind_context=context`.
5. Return confirmation: "Seed planted. {target_name} will hear from me {when}."

### GraphQL helper

```python
def create_seed_reminder(originator_id: str, owner_user_id: str,
                         remind_after: str, remind_context: str) -> dict:
    """Create a seed reminder (thread_memory with no thread)."""
    result = graphql("""
    mutation($obj: ThreadMemoryInput!) {
        createThreadMemory(input: {threadMemory: $obj}) {
            threadMemory { id remindAfter remindContext ownerUserId originatorId }
        }
    }
    """, {"obj": {
        "ownerUserId": owner_user_id,
        "originatorId": originator_id,
        "remindAfter": remind_after,
        "remindContext": remind_context,
        "messages": [],
    }})
    return result.get("createThreadMemory", {}).get("threadMemory", {})
```

### Pulse scanner changes

`scan_due_reminders` already queries `WHERE remind_after <= now()`. Three changes:

1. Include `originatorId` in the query fields.
2. **Guard null threadTs/channelId.** The existing code uses `thread['threadTs']` and `thread['channelId']` unconditionally in the target description and log line. Add a branch early in the loop: if `thread_ts is None` (seed row), take the seed path; otherwise fall through to existing reminder logic.
3. When `originator_id` is set, look up the originator's name and pass it to `generate_nudge()` with `nudge_type="seed"`. The originator lookup must NOT filter by `active=true` — the seed is still valid even if the planter was deactivated after planting.
4. **Check target is still active** before delivering. If `owner_user_id` resolves to an inactive user, skip delivery and clear the reminder.

Seeds are one-shot: after firing, `clear_thread_remind_after` runs (same as existing reminders). A snoozed seed gets a new `remind_after` and fires again.

The nudge message becomes: "{originator_name} wanted me to remind you: {remind_context}"

### Nudge generation

Add `"seed"` to the `generate_nudge()` function in `bot/characters/pulse.py`. The seed nudge prompt is simpler than stale/pipeline nudges — it's a direct message relay with the originator's name.

### Snooze wiring

When a user replies to a seed DM with a snooze phrase ("tomorrow", "next week", etc.), the dispatcher already detects it as `annotation.type == "snooze"`. Wire this up:

1. In `_get_response()`, add handler for snooze annotation.
2. Parse the snooze phrase to a new `remind_after` timestamp using the same date parser.
3. Update the thread_memory row: set new `remind_after`, clear `pulse_nudged_at`.
4. Respond: "Parked. I'll check back {new_date}."

Challenge: the snooze handler needs to know which thread_memory row to update. The DM doesn't carry a thread_memory ID.

Solution: when the pulse scanner sends a seed nudge DM, embed the thread_memory ID in the message metadata. Specifically, append it as a hidden marker in the DM message JSONB: `{"role": "assistant", "content": "...", "seed_id": 42}`. The snooze/completion handler in `_get_response()` scans the most recent assistant messages in the DM conversation for a `seed_id` field. If found, it knows which thread_memory row to update. If not found (user replies to a non-seed DM with a snooze phrase), fall through to normal Mother Tree response.

This approach requires no schema change to `conversations` — the `messages` JSONB array already stores arbitrary fields per message.

### Completion wiring

When the recipient replies with a completion phrase ("sent", "done", "called"), the dispatcher already detects `annotation.type == "completion"`. Wire this up:

1. In `_get_response()`, add handler for completion annotation.
2. Clear the `remind_after` on the thread_memory row.
3. Respond: "Nice. Marking that as done."
4. Optionally notify the originator that the seed was completed (stretch goal, not in v1).

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Nullable thread_ts/channel_id, originator_id, recurrence columns |
| `jobs/mothertree/graphql_client.py` | `get_non_citizen_by_name()`, `create_seed_reminder()`, `get_active_seeds()`, `cancel_seed()` |
| `jobs/bot/characters/dispatcher.py` | Seed/recurring/cancel/list patterns, ordering before snooze |
| `jobs/bot/pipeline.py` | `_handle_seed()`, `_handle_snooze()`, `_handle_completion()`, `_handle_seed_list()`, `_handle_seed_cancel()` |
| `jobs/pulse/scanner.py` | Null guard, originator enrichment, active check, recurrence advancement, completion notification |
| `jobs/bot/characters/pulse.py` | `nudge_type="seed"` prompt |
| `jobs/bot/memory.py` | Seed ID retrieval from recent DM messages for snooze/completion |

### Originator notification on completion

When the recipient completes a seed (replies "sent", "done", etc.), notify the originator via DM: "{recipient_name} completed your reminder: {remind_context}". Uses the same `_send_dm` path. Skip if originator is inactive.

### Recurring seeds

Pattern: "remind Pim every Monday to check the pipeline". Creates a seed with a `recurrence` field (stored in thread_memory as a new nullable column).

```sql
ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS recurrence TEXT;
```

Values: `"weekly"`, `"daily"`, `"biweekly"`. When the pulse scanner fires a recurring seed, instead of clearing `remind_after`, it advances it by the recurrence interval. Completion clears the recurrence (stops the series). Snooze shifts the next occurrence only.

Dispatcher pattern: "remind <name> every <interval> to <context>".

### Seed listing

DM command: "my seeds" or "seeds" — lists active seeds where the user is originator or recipient.

Returns:
- Seeds I planted (originator_id = me): "{target_name}: {context} — fires {date}"
- Seeds planted for me (owner_user_id = me): "{originator_name}: {context} — fires {date}"

New GraphQL helper: `get_active_seeds(user_id)` — queries thread_memory where `thread_ts IS NULL AND remind_after IS NOT NULL AND (originator_id = $id OR owner_user_id = $id)`.

Dispatcher: add "seeds" and "my seeds" to DM command patterns.

### Editing and cancelling seeds

DM command: "cancel seed for Pim about the deck" — finds the most recent matching seed (by target name + fuzzy context match) and clears `remind_after`.

If ambiguous (multiple seeds for Pim), list them and ask which one.

Originator can cancel their own seeds. Recipients can cancel seeds planted for them. Both sides have control.

### Rate limiting

Max 10 active seeds per originator. If exceeded: "You've planted 10 seeds already. Complete or cancel some before planting more." Checked in `_handle_seed()` before creating.

## Files changed

(Updated to reflect full scope)
