# Email-First Identity

> **For agentic workers:** Use superpowers:writing-plans to create an implementation plan from this spec.

## Problem

Mother Tree uses `slack_user_id` as the canonical identity everywhere — enrollment, contacts, conversations, signals, training. This ties the platform to Slack and makes privilege management awkward. Admin identity is a single env var pointing to a Slack user ID.

## Decision

Email becomes the canonical identity. Slack is a linked channel. Admin privileges are stored in a dedicated table, seeded from an env var, and manageable by admins at runtime.

## Schema

### New tables

**`users`** — replaces `enrollment` as the identity anchor.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL CHECK (email = lower(email)),
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('hunter', 'gatherer', 'farmer', 'citizen')),
    current_stage INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ,
    calendar_url TEXT,
    phone TEXT,
    working_days TEXT[],
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true
);
```

**`admins`** — privilege table with audit trail.

```sql
CREATE TABLE admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL CHECK (email = lower(email)),
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT now()
);
```

**`channel_links`** — maps channel identities to users.

```sql
CREATE TABLE channel_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL DEFAULT 'slack',
    channel_user_id TEXT NOT NULL,
    linked_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (channel_type, channel_user_id)
);

CREATE INDEX idx_channel_links_lookup ON channel_links(channel_type, channel_user_id);
```

### Dropped tables

**`enrollment`** — replaced by `users`. Drop (tables are empty, clean break).

### Redesigned tables

**`enrollment_requests`** — drop and recreate with user_id FK instead of slack_user_id:

```sql
CREATE TABLE enrollment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    requested_role TEXT NOT NULL CHECK (requested_role IN ('hunter', 'gatherer', 'farmer')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
```

### Modified tables

All tables that reference `enrollment(id)` via `user_id UUID` keep the same FK column name but point to `users(id)`:

- `exercises(user_id)` → `REFERENCES users(id)`
- `responses(user_id)` → `REFERENCES users(id)`
- `conversations(user_id)` → `REFERENCES users(id)`
- `training_progress(hunter_id TEXT)` → `training_progress(user_id UUID REFERENCES users(id))`, update UNIQUE constraint `(hunter_id, area)` → `(user_id, area)`

All tables with `slack_user_id TEXT` columns shift to `user_id UUID REFERENCES users(id)`:

- `conversations.slack_user_id` → `conversations.user_id` (already exists as FK, remove the text column)
- `interactions.slack_user_id` → `interactions.user_id`
- `help_delivered.slack_user_id` → `help_delivered.user_id`
- `contacts.slack_user_id` → `contacts.user_id` (the identity link, separate from owner)

Tables with `owner_slack_id TEXT` shift to `owner_user_id UUID`:

- `thread_memory.owner_slack_id` → `thread_memory.owner_user_id`
- `opportunities.owner_slack_id` → `opportunities.owner_user_id`
- `contacts.owner_slack_id` → `contacts.owner_user_id`

## Identity Resolution

### First contact flow (Slack DM)

```
Message arrives with slack_user_id
  → channel_links lookup (channel_type='slack', channel_user_id=slack_user_id)
  → if found: resolved to user_id, proceed
  → if not found:
      → Slack API: client.users_info(user=slack_user_id) → email
      → users lookup by email
      → if found: create channel_link, proceed
      → if not found: auto-create citizen user, create channel_link, proceed
```

### Identity resolution function

Replaces `get_enrollment(slack_user_id)`. Returns user dict or creates citizen.

```python
def resolve_user(slack_user_id: str, client) -> dict:
    """Resolve Slack user to Mother Tree user. Auto-creates citizens."""
    # 1. Check channel_links
    link = get_channel_link("slack", slack_user_id)
    if link:
        return get_user(link["userId"])

    # 2. Look up email from Slack
    info = client.users_info(user=slack_user_id)
    email = info["user"]["profile"].get("email")
    name = info["user"].get("real_name", "Unknown")

    if not email:
        return None  # Can't resolve without email

    # 3. Check users by email
    user = get_user_by_email(email)
    if not user:
        # Auto-create as citizen
        user = create_user(email=email, name=name, role="citizen")

    # 4. Link channel
    create_channel_link(user["id"], "slack", slack_user_id)
    return user
```

### Channel context

In channel messages (not DMs), the bot sees `slack_user_id` from the event. Same resolution applies — look up via channel_links, resolve to user.

## Admin System

### Root admin

`ADMIN_EMAIL` env var. On bot startup, ensure this email exists in the `admins` table (upsert with `granted_by='system'`).

### Admin operations (DM commands)

Admins detected by: resolve user → check `admins` table for their email.

- `make admin <email>` — insert into admins, granted_by = current admin email
- `remove admin <email>` — delete from admins (cannot remove root admin)
- `enroll <email> as <role>` — create user or update role. Non-citizen roles don't need approval when issued by admin.
- `pending` — list pending enrollment requests (users who self-enrolled as non-citizen)

### Non-admin enrollment

User says "enroll hunter" in DM:
1. Resolve user (auto-created as citizen if new)
2. If requesting citizen → already done
3. If requesting non-citizen role → create enrollment request, notify admins
4. Admin approves → update user role

### Enrollment request flow

Uses the redesigned `enrollment_requests` table (see Schema section above).

## Config Changes

| Old | New |
|-----|-----|
| `ADMIN_SLACK_ID = os.environ.get("ADMIN_SLACK_ID", "")` | `ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")` |

## Email Normalization

All email addresses are lowercased before storage and lookup. The `CHECK (email = lower(email))` constraint on `users` and `admins` enforces this at the database level. Application code must call `.lower()` on email inputs.

## Reverse Lookup (user → Slack)

DM sending, Pulse nudges, and training delivery need to resolve a user_id back to a Slack user ID. Add to `graphql_client.py`:

```python
def get_slack_user_id(user_id: str) -> str | None:
    """Reverse lookup: user_id → slack channel_user_id for DM sending."""
    link = get_channel_link_by_user(user_id, "slack")
    return link["channelUserId"] if link else None
```

All callers of `_send_dm` and `slack.chat_postMessage` that currently pass `slack_user_id` directly must resolve through this function.

## Bot/Service Account Handling

Slack bot users and app integrations may not have an email in their profile. When `resolve_user` gets no email from `users.info`, return `None`. The pipeline should silently skip identity resolution for these messages (no error, no user record) — they can still trigger signal extraction but not training or commands.

## Pipeline Changes

### `bot/pipeline.py`

`_get_enrollment(user_slack_id, participant_count)` → `_resolve_user(slack_user_id, client)`.

The `client` (Slack WebClient) must be passed through to enable `users.info` calls for email lookup. Currently `_process_message` has `client` available.

### `bot/bot.py`

Entry point where `message["user"]` is extracted. No change to extraction, but `client` must be passed through to pipeline for `users.info` calls (already available).

### `bot/characters/dispatcher.py`

Admin detection changes from `slack_user_id == ADMIN_SLACK_ID` to checking the `admins` table by resolved user email.

### `bot/memory.py`

Uses `slack_user_id` for DM conversation creation and `owner_slack_id` for thread memory. Shift to `user_id` references.

### `bot/extraction.py`

Passes `slack_user_id` to signal extraction. Shift to `user_id`.

### `bot/detect.py`

Passes `slack_user_id` through detection pipeline. Shift to `user_id`.

### `mothertree/graphql_client.py`

Replace:
- `get_enrollment(slack_user_id)` → `get_user_by_email(email)`, `get_user(user_id)`
- `enroll_user(slack_user_id, name, role)` → `create_user(email, name, role)`
- Add: `get_channel_link()`, `create_channel_link()`, `get_channel_link_by_user()`, `get_user_by_email()`, `get_slack_user_id()`, `is_admin()`, `add_admin()`, `remove_admin()`, `ensure_root_admin()`

### `training/operations.py`

`enroll(slack_user_id, name, role)` → `enroll(email, name, role)`. Internal references shift from slack_user_id to user_id.

### `training/deliver.py`

Uses `slack.chat_postMessage(channel=user["slack_user_id"])`. Must resolve via `get_slack_user_id(user_id)`.

### `pulse/scanner.py`

Owner lookups shift from `owner_slack_id` to `owner_user_id`. DM sending resolves via `get_slack_user_id()`. `_get_all_hunters` returns user_id instead of slackUserId.

### `discipline/weekly_review.py` and `monthly_retro.py`

Query enrollments for reporting. Shift to `users` table queries.

### CLI

```
mothertree train enroll <email> <name> <role>
mothertree train status <email>
mothertree train pending
mothertree admin add <email>
mothertree admin remove <email>
mothertree admin list
```

Existing commands that take `<slack_id>` (train status, calendar sync) shift to `<email>`.

### Deployment

`deploy/slack-bot/deployment.yaml`: rename `ADMIN_SLACK_ID` → `ADMIN_EMAIL`, update secret key reference.

## Testing

- Identity resolution: Slack user → channel_link → user (cached path)
- Identity resolution: Slack user → no link → Slack API → email → user (first contact)
- Identity resolution: Slack user → no link → no email → None (bot user)
- Auto-citizen creation on first contact
- Email normalization (mixed case → lowercase)
- Admin enrollment by email
- Admin designation and revocation
- Root admin cannot be revoked
- Root admin seeded on startup
- Non-citizen self-enrollment → approval flow
- Citizen self-enrollment → no approval needed
- Reverse lookup: user_id → slack_user_id for DM sending
- Pulse/deliver use reverse lookup for notifications
- All existing training, debrief, profile, handbook features work with new identity model
- Update existing test files: test_signal_pipeline.py, test_characters.py, test_unified.py, test_training.py, test_operations.py
