# Email-First Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace slack_user_id-based identity with email-first identity, adding channel_links for Slack mapping and an admins table for privilege management.

**Architecture:** Three new tables (users, admins, channel_links) replace enrollment as the identity anchor. Identity resolution goes through channel_links → users, with auto-citizen creation on first Slack contact. All slack_user_id/owner_slack_id references shift to user_id UUIDs. Tables are empty (just truncated), so this is a clean rewrite — no migration.

**Tech Stack:** Python, PostgreSQL, PostGraphile GraphQL, Slack SDK, pytest.

**Spec:** `docs/superpowers/specs/2026-04-13-email-identity-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `jobs/mothertree/identity.py` | Identity resolution: resolve_user(), reverse lookup, admin checks |
| `jobs/tests/test_identity.py` | Tests for identity resolution, admin system, channel linking |

### Modified Files

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Drop enrollment/enrollment_requests, create users/admins/channel_links, update all FKs |
| `jobs/mothertree/config.py` | `ADMIN_SLACK_ID` → `ADMIN_EMAIL` |
| `jobs/mothertree/graphql_client.py` | Rewrite enrollment functions → user functions, add channel_links/admin CRUD |
| `jobs/bot/pipeline.py` | `_get_enrollment()` → `_resolve_user()`, pass `client` for Slack API |
| `jobs/bot/memory.py` | `slack_user_id` → `user_id` in DM and thread memory |
| `jobs/bot/extraction.py` | `slack_user_id` → `user_id` in signal extraction |
| `jobs/bot/detect.py` | `slack_user_id` → `user_id` pass-through |
| `jobs/bot/characters/dispatcher.py` | Admin detection via admins table, enrollment annotation uses email |
| `jobs/training/operations.py` | `enroll(slack_user_id)` → `enroll(email)`, all internal refs to user_id |
| `jobs/training/deliver.py` | Reverse lookup for DM sending |
| `jobs/pulse/scanner.py` | `owner_slack_id` → `owner_user_id`, reverse lookup for DMs |
| `jobs/discipline/weekly_review.py` | Enrollment queries → users table |
| `jobs/discipline/monthly_retro.py` | Enrollment queries → users table |
| `jobs/cli.py` | Commands take email instead of slack_user_id, add admin subcommands |
| `deploy/slack-bot/deployment.yaml` | `ADMIN_SLACK_ID` → `ADMIN_EMAIL` env var |
| `jobs/tests/test_identity.py` | New: identity resolution, admin, channel link tests |
| `jobs/tests/test_operations.py` | Update fixtures from slack_user_id to email/user_id |
| `jobs/tests/test_training.py` | Update enrollment mocks to users table |
| `jobs/tests/test_unified.py` | Update memory and pipeline mocks |
| `jobs/tests/test_signal_pipeline.py` | Update slack_user_id assertions to user_id |
| `jobs/tests/test_characters.py` | Update dispatcher and pipeline integration tests |
| `jobs/tests/test_enrollment_approval.py` | Rewrite for new enrollment_requests schema |
| `jobs/tests/test_profile_collection.py` | Update for user_id instead of slack_user_id |
| `jobs/tests/test_handbook.py` | Update help_delivered mocks |
| `jobs/tests/test_debrief.py` | Update pipeline mocks |

---

## Task 1: Schema Rewrite

**Files:**
- Modify: `deploy/database/schema.sql`

- [ ] **Step 1: Replace enrollment table with users table**

In `deploy/database/schema.sql`, find the enrollment table definition (lines 274-286) and the ALTER statements that added email/phone/working_days (lines 471-473). Replace the enrollment block with:

```sql
-- === USER IDENTITY ===
CREATE TABLE IF NOT EXISTS users (
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

CREATE TABLE IF NOT EXISTS admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL CHECK (email = lower(email)),
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channel_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL DEFAULT 'slack',
    channel_user_id TEXT NOT NULL,
    linked_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (channel_type, channel_user_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_links_lookup ON channel_links(channel_type, channel_user_id);
```

- [ ] **Step 2: Update all FK references from enrollment(id) to users(id)**

In the exercises table (line 306): `user_id UUID REFERENCES enrollment(id)` → `user_id UUID REFERENCES users(id)`
In the responses table (line 320): same change.
In the conversations table (line 336): same change.

- [ ] **Step 3: Replace slack_user_id columns with user_id UUIDs**

Remove `conversations.slack_user_id TEXT` (line 338) and its index (line 371). The `conversations.user_id` FK already exists.

Replace the ALTER statements (lines 418-421):
```sql
-- Old:
-- ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS owner_slack_id TEXT;
-- ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_slack_id TEXT;
-- ALTER TABLE interactions ADD COLUMN IF NOT EXISTS slack_user_id TEXT;
-- ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_slack_id TEXT;

-- New:
ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);
```

Update Pulse indexes to use new column names:
```sql
CREATE INDEX IF NOT EXISTS idx_thread_memory_owner ON thread_memory(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_owner ON opportunities(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_user_id);
```

- [ ] **Step 4: Rewrite enrollment_requests table**

Replace the enrollment_requests CREATE TABLE (lines 443-453) with:

```sql
CREATE TABLE IF NOT EXISTS enrollment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    requested_role TEXT NOT NULL CHECK (requested_role IN ('hunter', 'gatherer', 'farmer')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_enrollment_requests_status
    ON enrollment_requests(status) WHERE status = 'pending';
```

- [ ] **Step 5: Update help_delivered table**

Replace `slack_user_id TEXT NOT NULL` with `user_id UUID NOT NULL REFERENCES users(id)` and update the UNIQUE constraint:

```sql
CREATE TABLE IF NOT EXISTS help_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    help_key TEXT NOT NULL,
    delivered_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, help_key)
);
```

- [ ] **Step 6: Update training_progress table**

Replace `hunter_id TEXT` with `user_id UUID REFERENCES users(id)` and update the UNIQUE constraint from `(hunter_id, area)` to `(user_id, area)`.

- [ ] **Step 7: Remove the old enrollment ALTER statements**

Remove the three ALTER lines that added email/phone/working_days to enrollment (lines 471-473) — these fields are now in the `users` table definition.

- [ ] **Step 8: Commit**

```bash
git add deploy/database/schema.sql
git commit -m "schema: replace enrollment with users/admins/channel_links, shift all slack_user_id to user_id"
```

---

## Task 2: Config + GraphQL Client — Core Identity Functions

**Files:**
- Modify: `jobs/mothertree/config.py`
- Create: `jobs/mothertree/identity.py`
- Modify: `jobs/mothertree/graphql_client.py`
- Create: `jobs/tests/test_identity.py`

- [ ] **Step 1: Update config**

In `jobs/mothertree/config.py` (line 35), replace:
```python
ADMIN_SLACK_ID = os.environ.get("ADMIN_SLACK_ID", "")
```
with:
```python
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
```

- [ ] **Step 2: Write failing tests for identity resolution**

Create `jobs/tests/test_identity.py`:

```python
"""Tests for email-first identity resolution."""
from unittest.mock import MagicMock, patch


class TestChannelLinkLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_finds_existing_link(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": [
            {"userId": "user-uuid-1", "channelType": "slack", "channelUserId": "U_JURG"}
        ]}
        from mothertree.graphql_client import get_channel_link
        link = get_channel_link("slack", "U_JURG")
        assert link is not None
        assert link["userId"] == "user-uuid-1"

    @patch("mothertree.graphql_client.graphql")
    def test_returns_none_when_no_link(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": []}
        from mothertree.graphql_client import get_channel_link
        link = get_channel_link("slack", "U_UNKNOWN")
        assert link is None


class TestUserLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_get_user_by_email(self, mock_gql):
        mock_gql.return_value = {"allUsersList": [
            {"id": "user-uuid-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        ]}
        from mothertree.graphql_client import get_user_by_email
        user = get_user_by_email("jurg@aknostic.com")
        assert user is not None
        assert user["role"] == "hunter"

    @patch("mothertree.graphql_client.graphql")
    def test_get_user_by_email_normalizes(self, mock_gql):
        mock_gql.return_value = {"allUsersList": [
            {"id": "user-uuid-1", "email": "jurg@aknostic.com", "name": "Jurg", "role": "hunter"}
        ]}
        from mothertree.graphql_client import get_user_by_email
        get_user_by_email("Jurg@Aknostic.com")
        call_vars = mock_gql.call_args[0][1] if len(mock_gql.call_args[0]) > 1 else mock_gql.call_args[1].get("variables", {})
        # Should have been lowercased
        assert "jurg@aknostic.com" in str(mock_gql.call_args)

    @patch("mothertree.graphql_client.graphql")
    def test_create_user(self, mock_gql):
        mock_gql.return_value = {"createUser": {"user": {"id": "new-uuid", "email": "pim@aknostic.com"}}}
        from mothertree.graphql_client import create_user
        user = create_user("pim@aknostic.com", "Pim", "citizen")
        assert user is not None


class TestCreateChannelLink:
    @patch("mothertree.graphql_client.graphql")
    def test_creates_link(self, mock_gql):
        mock_gql.return_value = {"createChannelLink": {"channelLink": {"id": "link-1"}}}
        from mothertree.graphql_client import create_channel_link
        create_channel_link("user-uuid-1", "slack", "U_JURG")
        mock_gql.assert_called_once()


class TestReverseLookup:
    @patch("mothertree.graphql_client.graphql")
    def test_get_slack_user_id(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": [
            {"channelUserId": "U_JURG", "channelType": "slack"}
        ]}
        from mothertree.graphql_client import get_slack_user_id
        sid = get_slack_user_id("user-uuid-1")
        assert sid == "U_JURG"

    @patch("mothertree.graphql_client.graphql")
    def test_returns_none_when_no_slack(self, mock_gql):
        mock_gql.return_value = {"allChannelLinksList": []}
        from mothertree.graphql_client import get_slack_user_id
        sid = get_slack_user_id("user-uuid-orphan")
        assert sid is None


class TestAdminFunctions:
    @patch("mothertree.graphql_client.graphql")
    def test_is_admin(self, mock_gql):
        mock_gql.return_value = {"allAdminsList": [{"email": "jurg@aknostic.com"}]}
        from mothertree.graphql_client import is_admin
        assert is_admin("jurg@aknostic.com") is True

    @patch("mothertree.graphql_client.graphql")
    def test_is_not_admin(self, mock_gql):
        mock_gql.return_value = {"allAdminsList": []}
        from mothertree.graphql_client import is_admin
        assert is_admin("random@example.com") is False

    @patch("mothertree.graphql_client.graphql")
    def test_add_admin(self, mock_gql):
        mock_gql.return_value = {"createAdmin": {"admin": {"id": "a1"}}}
        from mothertree.graphql_client import add_admin
        add_admin("pim@aknostic.com", granted_by="jurg@aknostic.com")
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_ensure_root_admin(self, mock_gql):
        # First call: check if exists (empty). Second call: insert.
        mock_gql.side_effect = [
            {"allAdminsList": []},
            {"createAdmin": {"admin": {"id": "root-1"}}},
        ]
        from mothertree.graphql_client import ensure_root_admin
        ensure_root_admin("jurg@aknostic.com")
        assert mock_gql.call_count == 2


class TestResolveUser:
    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.create_user")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_cached_path(self, mock_link, mock_email, mock_create, mock_create_link):
        """Known Slack user with existing channel_link."""
        mock_link.return_value = {"userId": "user-1"}
        with patch("mothertree.graphql_client.get_user") as mock_get:
            mock_get.return_value = {"id": "user-1", "email": "jurg@aknostic.com", "role": "hunter"}
            from mothertree.identity import resolve_user
            client = MagicMock()
            user = resolve_user("U_JURG", client)
            assert user["id"] == "user-1"
            client.users_info.assert_not_called()  # No Slack API call needed

    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_first_contact_existing_user(self, mock_link, mock_email, mock_create_link):
        """New Slack user, but email already in users table (admin pre-enrolled)."""
        mock_link.return_value = None
        mock_email.return_value = {"id": "user-1", "email": "jurg@aknostic.com", "role": "hunter"}
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {"email": "jurg@aknostic.com"}, "real_name": "Jurg"}}
        user = resolve_user("U_JURG", client)
        assert user["id"] == "user-1"
        mock_create_link.assert_called_once()

    @patch("mothertree.graphql_client.create_channel_link")
    @patch("mothertree.graphql_client.create_user")
    @patch("mothertree.graphql_client.get_user_by_email")
    @patch("mothertree.graphql_client.get_channel_link")
    def test_first_contact_new_user(self, mock_link, mock_email, mock_create, mock_create_link):
        """Completely new user — auto-create as citizen."""
        mock_link.return_value = None
        mock_email.return_value = None
        mock_create.return_value = {"id": "new-user", "email": "newcomer@example.com", "role": "citizen"}
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {"email": "newcomer@example.com"}, "real_name": "New Person"}}
        user = resolve_user("U_NEW", client)
        assert user["role"] == "citizen"
        mock_create.assert_called_once_with(email="newcomer@example.com", name="New Person", role="citizen")

    @patch("mothertree.graphql_client.get_channel_link")
    def test_bot_user_no_email(self, mock_link):
        """Slack bot user with no email → returns None."""
        mock_link.return_value = None
        from mothertree.identity import resolve_user
        client = MagicMock()
        client.users_info.return_value = {"user": {"profile": {}, "real_name": "SomeBot"}}
        user = resolve_user("U_BOT", client)
        assert user is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_identity.py -v`
Expected: FAIL — ImportError

- [ ] **Step 4: Add GraphQL functions for users, channel_links, and admins**

In `jobs/mothertree/graphql_client.py`, replace the existing enrollment functions (`get_enrollment` at line 477, `enroll_user` at line 490, `get_active_enrollments` at line 735) with:

```python
# --- User identity ---

def get_user(user_id: str) -> dict | None:
    """Get user by UUID."""
    result = graphql("""
    query($id: UUID!) {
        userById(id: $id) {
            id email name role currentStage currentChapter active
            streak lastActivity calendarUrl phone workingDays
        }
    }
    """, {"id": user_id})
    return result.get("userById")


def get_user_by_email(email: str) -> dict | None:
    """Get user by email (normalized to lowercase)."""
    result = graphql("""
    query($email: String!) {
        allUsersList(condition: {email: $email}, first: 1) {
            id email name role currentStage currentChapter active
            streak lastActivity calendarUrl
        }
    }
    """, {"email": email.lower()})
    users = result.get("allUsersList", [])
    return users[0] if users else None


def create_user(email: str, name: str, role: str) -> dict:
    """Create a new user."""
    result = graphql("""
    mutation($obj: UserInput!) {
        createUser(input: {user: $obj}) {
            user { id email name role currentStage currentChapter }
        }
    }
    """, {"obj": {"email": email.lower(), "name": name, "role": role}})
    return result.get("createUser", {}).get("user")


def get_active_users() -> list[dict]:
    """Get all active users (replaces get_active_enrollments)."""
    result = graphql("""
    query {
        allUsersList(condition: {active: true}) {
            id email name role currentStage currentChapter
            streak lastActivity calendarUrl
        }
    }
    """)
    return result.get("allUsersList", [])


def update_user_role(user_id: str, role: str) -> None:
    """Update a user's role."""
    graphql("""
    mutation($id: UUID!, $patch: UserPatch!) {
        updateUserById(input: {id: $id, userPatch: $patch}) {
            user { id }
        }
    }
    """, {"id": user_id, "patch": {"role": role}})
```

Add channel_links functions:

```python
# --- Channel links ---

def get_channel_link(channel_type: str, channel_user_id: str) -> dict | None:
    """Look up a channel link."""
    result = graphql("""
    query($type: String!, $uid: String!) {
        allChannelLinksList(condition: {channelType: $type, channelUserId: $uid}, first: 1) {
            id userId channelType channelUserId
        }
    }
    """, {"type": channel_type, "uid": channel_user_id})
    links = result.get("allChannelLinksList", [])
    return links[0] if links else None


def create_channel_link(user_id: str, channel_type: str, channel_user_id: str) -> None:
    """Create a channel link mapping."""
    graphql("""
    mutation($obj: ChannelLinkInput!) {
        createChannelLink(input: {channelLink: $obj}) {
            channelLink { id }
        }
    }
    """, {"obj": {"userId": user_id, "channelType": channel_type, "channelUserId": channel_user_id}})


def get_slack_user_id(user_id: str) -> str | None:
    """Reverse lookup: user_id → Slack channel_user_id for DM sending."""
    result = graphql("""
    query($uid: UUID!, $type: String!) {
        allChannelLinksList(condition: {userId: $uid, channelType: $type}, first: 1) {
            channelUserId
        }
    }
    """, {"uid": user_id, "type": "slack"})
    links = result.get("allChannelLinksList", [])
    return links[0]["channelUserId"] if links else None
```

Add admin functions:

```python
# --- Admin management ---

def is_admin(email: str) -> bool:
    """Check if email is an admin."""
    result = graphql("""
    query($email: String!) {
        allAdminsList(condition: {email: $email}) { email }
    }
    """, {"email": email.lower()})
    return len(result.get("allAdminsList", [])) > 0


def add_admin(email: str, granted_by: str) -> None:
    """Grant admin privileges."""
    graphql("""
    mutation($obj: AdminInput!) {
        createAdmin(input: {admin: $obj}) { admin { id } }
    }
    """, {"obj": {"email": email.lower(), "grantedBy": granted_by}})


def remove_admin(email: str) -> None:
    """Revoke admin privileges."""
    result = graphql("""
    query($email: String!) {
        allAdminsList(condition: {email: $email}) { id }
    }
    """, {"email": email.lower()})
    admins = result.get("allAdminsList", [])
    if admins:
        graphql("""
        mutation($id: UUID!) {
            deleteAdminById(input: {id: $id}) { admin { id } }
        }
        """, {"id": admins[0]["id"]})


def get_all_admins() -> list[dict]:
    """List all admins."""
    result = graphql("""
    query { allAdminsList { email grantedBy grantedAt } }
    """)
    return result.get("allAdminsList", [])


def ensure_root_admin(email: str) -> None:
    """Ensure root admin exists in admins table."""
    if not email:
        return
    if not is_admin(email):
        add_admin(email, granted_by="system")
```

- [ ] **Step 5: Create identity resolution module**

Create `jobs/mothertree/identity.py`:

```python
"""Identity resolution — maps Slack users to Mother Tree users via channel_links.

First contact flow:
1. Check channel_links for existing mapping
2. If not found, look up email from Slack API
3. If email matches existing user, link and proceed
4. If no user found, auto-create as citizen
"""

import logging

from mothertree.graphql_client import (
    create_channel_link,
    create_user,
    get_channel_link,
    get_user,
    get_user_by_email,
)

log = logging.getLogger(__name__)


def resolve_user(slack_user_id: str, client) -> dict | None:
    """Resolve Slack user to Mother Tree user. Auto-creates citizens."""
    # 1. Check channel_links (fast path)
    link = get_channel_link("slack", slack_user_id)
    if link:
        return get_user(link["userId"])

    # 2. Look up email from Slack
    try:
        info = client.users_info(user=slack_user_id)
    except Exception:
        log.exception("Failed to look up Slack user %s", slack_user_id)
        return None

    profile = info.get("user", {}).get("profile", {})
    email = profile.get("email")
    name = info.get("user", {}).get("real_name", "Unknown")

    if not email:
        return None  # Bot or service account — no email

    email = email.lower()

    # 3. Check users by email
    user = get_user_by_email(email)
    if not user:
        # Auto-create as citizen
        user = create_user(email=email, name=name, role="citizen")
        log.info("Auto-created citizen: %s (%s)", email, name)

    # 4. Link channel
    create_channel_link(user["id"], "slack", slack_user_id)
    log.info("Linked Slack %s → %s", slack_user_id, email)
    return user
```

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest tests/test_identity.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/mothertree/config.py jobs/mothertree/graphql_client.py jobs/mothertree/identity.py jobs/tests/test_identity.py
git commit -m "feat: email-first identity — users/admins/channel_links GraphQL + resolve_user"
```

---

## Task 3: Rewrite Existing GraphQL Functions

**Files:**
- Modify: `jobs/mothertree/graphql_client.py`

This task rewrites all existing functions that use `slack_user_id` or reference the `enrollment` table to use `user_id` and the `users` table instead. Functions already added in Task 2 are not touched.

- [ ] **Step 1: Rewrite `get_or_create_dm_conversation` (line 750)**

Change parameter from `slack_user_id: str` to `user_id: str`. Update the GraphQL query to filter by `userId` instead of `slackUserId`. Update the create mutation to use `userId` instead of `slackUserId`.

- [ ] **Step 2: Rewrite `get_or_create_thread_memory` (line 858)**

Change parameter `owner_slack_id` to `owner_user_id`. Update the GraphQL mutation to use `ownerUserId` instead of `ownerSlackId`.

- [ ] **Step 3: Rewrite `find_or_create_contact` (line 390)**

Remove the `slack_user_id` parameter lookup path. Add `user_id` parameter. Update the create mutation to include `userId` and `ownerUserId` instead of `slackUserId` and `ownerSlackId`.

- [ ] **Step 4: Rewrite `update_contact_owner` (line 1101)**

Change from `ownerSlackId` to `ownerUserId` in the mutation patch.

- [ ] **Step 5: Rewrite `has_help_been_delivered` and `record_help_delivered` (lines 1116-1134)**

Change `slack_user_id` parameter to `user_id`. Update GraphQL conditions from `slackUserId` to `userId`.

- [ ] **Step 6: Rewrite enrollment request functions (lines 1179+)**

Update `create_enrollment_request` to take `user_id` instead of `slack_user_id`. Remove `name` parameter (it's on the user record). Update `resolve_enrollment_request` to use `approved_by` email instead of `admin_slack_id`. Update `get_expired_enrollment_requests`.

- [ ] **Step 7: Rewrite `advance_enrollment` (line 676) → `advance_user`**

Rename function. Same logic, just rename references from enrollment to user.

- [ ] **Step 8: Rewrite `update_streak` (line 725) → update users table**

Same function but mutation targets `updateUserById` instead of `updateEnrollmentById`.

- [ ] **Step 9: Rewrite `upsert_training_progress` and `get_training_progress` (lines 692-711)**

Change `hunter_id` parameter to `user_id`. Update GraphQL variables accordingly.

- [ ] **Step 10: Rewrite `update_enrollment_profile` (line 1238) → `update_user_profile`**

Change mutation from `updateEnrollmentById` / `EnrollmentPatch` to `updateUserById` / `UserPatch`. Keep the snake_case → camelCase conversion logic.

- [ ] **Step 11: Remove old `get_enrollment`, `enroll_user`, and `get_active_enrollments` functions**

These are replaced by `get_user_by_email`, `create_user`, and `get_active_users` from Task 2. Remove the old functions.

- [ ] **Step 11: Run full test suite**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: Some failures in tests that still reference old functions — that's expected, tests are updated in Task 9.

- [ ] **Step 12: Commit**

```bash
git add jobs/mothertree/graphql_client.py
git commit -m "feat: rewrite all GraphQL functions from slack_user_id to user_id"
```

---

## Task 4: Pipeline Identity Resolution

**Files:**
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/bot/memory.py`
- Modify: `jobs/bot/extraction.py`
- Modify: `jobs/bot/detect.py`

- [ ] **Step 1: Rewrite `_get_enrollment` → `_resolve_user` in pipeline.py**

Replace `_get_enrollment` (line 775-783) with:

```python
def _resolve_user(slack_user_id: str, client, participant_count: int):
    """Resolve Slack user to Mother Tree user.

    In DMs (participant_count == 1): full resolution with auto-create.
    In channels: resolve only if channel_link already exists (no Slack API call, no auto-create).
    """
    from mothertree.identity import resolve_user
    from mothertree.graphql_client import get_channel_link, get_user
    if participant_count == 1:
        # DMs: full resolution, auto-create citizens
        user = resolve_user(slack_user_id, client)
    else:
        # Channels: only use cached channel_link, no API call
        link = get_channel_link("slack", slack_user_id)
        user = get_user(link["userId"]) if link else None
    if not user:
        return None, None, False
    from mothertree.graphql_client import get_active_conversation
    active_exercise = get_active_conversation(user["id"]) if participant_count == 1 else None
    enrolled = user.get("role") != "citizen" or user.get("currentStage", 0) > 0
    return user, active_exercise, enrolled
```

- [ ] **Step 2: Update `_process_message` to use `_resolve_user`**

At line 79, change:
```python
enrollment, active_exercise, enrolled = _get_enrollment(user_slack_id, participant_count)
```
to:
```python
user, active_exercise, enrolled = _resolve_user(user_slack_id, client, participant_count)
```

Update all downstream references from `enrollment` to `user` throughout the function. The `user` dict has the same fields (id, role, currentStage, etc.) so most code works unchanged.

- [ ] **Step 3: Update `_get_response` and `_training_response`**

Change `enrollment=enrollment` parameter passing to `enrollment=user` (the variable name changes but the dict structure is the same).

- [ ] **Step 4: Update help delivery calls**

At lines where `has_help_been_delivered(user_slack_id, ...)` and `record_help_delivered(user_slack_id, ...)` are called, change to pass `user["id"]` instead.

- [ ] **Step 5: Update `_background_extract` calls**

Change `slack_user_id=user_slack_id` to `user_id=user["id"] if user else None`.

- [ ] **Step 6: Update memory.py**

In `get_memory()` (line 26): change `get_or_create_dm_conversation(kwargs["slack_user_id"])` to `get_or_create_dm_conversation(kwargs["user_id"])`.
At line 45: change `owner_slack_id=kwargs.get("owner_slack_id")` to `owner_user_id=kwargs.get("owner_user_id")`.

Update all callers in pipeline.py that pass `slack_user_id=` to memory functions to pass `user_id=` instead.

- [ ] **Step 7: Update extraction.py**

Change `slack_user_id` parameter to `user_id` in `extract_signal()` (line 22) and `_process_actions()` (line 238). Update interaction creation (line 270-271) from `"slackUserId": slack_user_id` to `"userId": user_id`.

- [ ] **Step 8: Update detect.py**

This file has deeper coupling than a simple rename:
- Remove `from mothertree.graphql_client import get_enrollment` import (line 12). Replace with `get_user` if needed.
- `deliver_next(enrollment, slack_user_id)` (line 25): change signature to `deliver_next(user, user_id)`. The `slack_user_id` param was used for DM history lookup — change to `user_id`.
- `generate_citizen_inspiration(enrollment, slack_user_id)` (line 79): same pattern — change to `(user, user_id)`.
- All calls to `get_or_create_dm_conversation(slack_user_id)` → `get_or_create_dm_conversation(user_id)`.
- All calls to `get_enrollment(slack_user_id)` → use the `user` dict already passed as parameter.

- [ ] **Step 9: Run tests**

Run: `cd jobs && python -m pytest tests/test_identity.py -v`
Expected: PASS (identity tests still work)

- [ ] **Step 10: Commit**

```bash
git add jobs/bot/pipeline.py jobs/bot/memory.py jobs/bot/extraction.py jobs/bot/detect.py
git commit -m "feat: pipeline identity resolution via resolve_user + channel_links"
```

---

## Task 5: Dispatcher + Admin System

**Files:**
- Modify: `jobs/bot/characters/dispatcher.py`

- [ ] **Step 1: Update enrollment handling in dispatcher**

At line 239, the enroll annotation stores `slack_user_id`. Change to store the user's email:
```python
result["annotation"]["email"] = user_email  # Was: slack_user_id
```

The dispatcher receives `user` dict (resolved by pipeline). Add `user=None` parameter to `dispatch()` and use `user.get("email")` where `slack_user_id` was used.

- [ ] **Step 2: Add admin detection**

Replace the admin check (if any exists referencing `ADMIN_SLACK_ID`) with:
```python
from mothertree.graphql_client import is_admin

def _is_admin_user(user: dict) -> bool:
    """Check if resolved user is an admin."""
    return is_admin(user.get("email", "")) if user else False
```

- [ ] **Step 3: Add admin command detection**

In the DM commands section (around line 216), add admin command handling before the regular commands:

```python
    # Admin commands (DM only, admin users only)
    if participant_count == 1 and user and _is_admin_user(user):
        admin_action = _detect_admin_command(clean)
        if admin_action:
            result["must_respond"] = True
            result["intent"] = "admin"
            result["annotation"] = {"type": "admin", **admin_action}
            return result
```

Add the detection function:

```python
def _detect_admin_command(text: str) -> dict | None:
    """Detect admin commands from DM text."""
    lower = text.lower().strip()
    parts = lower.split()
    if len(parts) >= 2 and parts[0] == "make" and parts[1] == "admin":
        email = parts[2] if len(parts) > 2 else None
        return {"action": "make_admin", "email": email}
    if len(parts) >= 2 and parts[0] == "remove" and parts[1] == "admin":
        email = parts[2] if len(parts) > 2 else None
        return {"action": "remove_admin", "email": email}
    if lower == "pending":
        return {"action": "pending"}
    # "enroll email as role" — admin enrollment
    if parts[0] == "enroll" and "as" in parts:
        as_idx = parts.index("as")
        email = parts[1] if len(parts) > 1 else None
        role = parts[as_idx + 1] if len(parts) > as_idx + 1 else None
        if email and role and role in ("hunter", "gatherer", "farmer", "citizen"):
            return {"action": "admin_enroll", "email": email, "role": role}
    return None
```

- [ ] **Step 4: Update the existing enroll command**

The self-enroll command (user says "enroll hunter") should create an enrollment request instead of enrolling directly (unless citizen):

Update the annotation to pass `user_id` instead of `slack_user_id`.

- [ ] **Step 5: Remove `_detect_enrollment_action` function**

This function (added in Plan B Task 6) is replaced by `_detect_admin_command`. Delete it entirely.

- [ ] **Step 6: Wire `ensure_root_admin` into bot startup**

In `jobs/bot/bot.py`, after the Slack app is initialized and before the socket mode handler starts, add:

```python
from mothertree.config import ADMIN_EMAIL
from mothertree.graphql_client import ensure_root_admin
if ADMIN_EMAIL:
    ensure_root_admin(ADMIN_EMAIL)
```

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/characters/dispatcher.py jobs/bot/bot.py
git commit -m "feat: admin commands + email-based enrollment in dispatcher, root admin seeding"
```

---

## Task 6: Training Operations + Delivery

**Files:**
- Modify: `jobs/training/operations.py`
- Modify: `jobs/training/deliver.py`

- [ ] **Step 1: Rewrite `enroll()` function**

In `operations.py` (line 180), change signature from `enroll(slack_user_id, name, role)` to `enroll(email, name, role)`:

```python
def enroll(email: str, name: str, role: str) -> str:
    """Enroll a user by email and create them as a team contact."""
    existing = get_user_by_email(email)
    if existing:
        return f"You're already enrolled as {existing['role']}."
    user = create_user(email, name, role)
    # Create team contact
    find_or_create_contact(full_name=name, user_id=user["id"], is_team=True, role=role)
    return f"Welcome to Mother Tree, {name}. You're enrolled as *{role}*."
```

- [ ] **Step 2: Update all enrollment references in operations.py**

Replace `enrollment["slack_user_id"]` with `user["email"]` or `user["id"]` throughout. Update imports from `get_enrollment` to `get_user_by_email`, `enroll_user` to `create_user`.

Update `upsert_training_progress` calls from `hunter_id=enrollment_id` to `user_id=user_id`.

- [ ] **Step 3: Rewrite deliver.py DM sending**

In `deliver.py` (line 41, 61, 70), change:
```python
slack.chat_postMessage(channel=user["slack_user_id"], ...)
```
to:
```python
from mothertree.graphql_client import get_slack_user_id
slack_id = get_slack_user_id(user["id"])
if slack_id:
    slack.chat_postMessage(channel=slack_id, ...)
```

Update the `get_active_enrollments()` call to `get_active_users()`.

- [ ] **Step 4: Commit**

```bash
git add jobs/training/operations.py jobs/training/deliver.py
git commit -m "feat: training operations + delivery use email identity and reverse lookup"
```

---

## Task 7: Pulse Scanner + Discipline

**Files:**
- Modify: `jobs/pulse/scanner.py`
- Modify: `jobs/discipline/weekly_review.py`
- Modify: `jobs/discipline/monthly_retro.py`

- [ ] **Step 1: Update Pulse scanner owner references**

In `scanner.py`, all GraphQL queries that use `ownerSlackId` shift to `ownerUserId`. Update `_get_all_hunters()` to return user_id instead of slackUserId.

- [ ] **Step 2: Update `_send_dm` callers**

Every call to `_send_dm(slack, recipient, message)` where `recipient` was a `slack_user_id` must now resolve via `get_slack_user_id(user_id)`:

```python
slack_id = get_slack_user_id(user_id)
if slack_id:
    _send_dm(slack, slack_id, message)
```

- [ ] **Step 3: Update `_check_expired_enrollments`**

Change to use `user_id` from enrollment_requests. Resolve Slack ID for notification:

```python
def _check_expired_enrollments(slack: WebClient) -> None:
    from mothertree.graphql_client import get_expired_enrollment_requests, resolve_enrollment_request, get_slack_user_id
    expired = get_expired_enrollment_requests(hours=48)
    for req in expired:
        resolve_enrollment_request(req["id"], "rejected")
        slack_id = get_slack_user_id(req["userId"])
        if slack_id:
            try:
                _send_dm(slack, slack_id, "Your enrollment request expired.")
            except Exception:
                log.exception("Failed to notify expired enrollment %s", req["id"])
```

- [ ] **Step 4: Update discipline modules**

`weekly_review.py` has **inline GraphQL queries** that directly query `allEnrollmentsList` (at `gather_pipeline_state()` ~line 35 and the DM sending section ~line 207). These do NOT use `get_active_enrollments()` — they must be rewritten to query `allUsersList` instead. Update `member["slackUserId"]` → resolve via `get_slack_user_id(member["id"])` for DM sending.

In `monthly_retro.py`, same pattern — find inline enrollment queries and rewrite to users table. Update DM sending with reverse lookup.

- [ ] **Step 5: Commit**

```bash
git add jobs/pulse/scanner.py jobs/discipline/weekly_review.py jobs/discipline/monthly_retro.py
git commit -m "feat: Pulse and discipline use user_id identity with reverse lookup"
```

---

## Task 8: CLI + Deployment

**Files:**
- Modify: `jobs/cli.py`
- Modify: `deploy/slack-bot/deployment.yaml`

- [ ] **Step 1: Update `train enroll` command**

In `cli.py` (line 113-120), change:
```python
        elif subcmd == "enroll":
            if len(args) < 5:
                print("Usage: mothertree train enroll <email> <name> <role>")
                print("Roles: hunter, gatherer, farmer, citizen")
                sys.exit(1)
            from training.operations import enroll
            result = enroll(args[2], args[3], args[4])
            print(result)
```

- [ ] **Step 2: Update `train status` command**

Change from `get_enrollment(slack_id)` to `get_user_by_email(email)`:
```python
        elif subcmd == "status":
            if len(args) < 3:
                print("Usage: mothertree train status <email>")
                sys.exit(1)
            from mothertree.graphql_client import get_user_by_email
            user = get_user_by_email(args[2])
            if not user:
                print(f"No user found for {args[2]}")
            else:
                print(f"  Role:    {user.get('role')}")
                print(f"  Stage:   {user.get('currentStage')}")
                print(f"  Chapter: {user.get('currentChapter')}")
                print(f"  Streak:  {user.get('streak', 0)} days")
```

- [ ] **Step 3: Add admin subcommands**

Add new `admin` command block:
```python
    elif cmd == "admin":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "add":
            if len(args) < 3:
                print("Usage: mothertree admin add <email>")
                sys.exit(1)
            from mothertree.graphql_client import add_admin
            add_admin(args[2], granted_by="cli")
            print(f"Admin granted: {args[2]}")
        elif subcmd == "remove":
            if len(args) < 3:
                print("Usage: mothertree admin remove <email>")
                sys.exit(1)
            from mothertree.config import ADMIN_EMAIL
            if args[2].lower() == ADMIN_EMAIL.lower():
                print("Cannot remove root admin.")
                sys.exit(1)
            from mothertree.graphql_client import remove_admin
            remove_admin(args[2])
            print(f"Admin revoked: {args[2]}")
        elif subcmd == "list":
            from mothertree.graphql_client import get_all_admins
            admins = get_all_admins()
            if not admins:
                print("No admins configured.")
            else:
                for a in admins:
                    print(f"  {a['email']} (granted by {a['grantedBy']})")
        else:
            print("Usage: mothertree admin {add|remove|list}")
```

- [ ] **Step 4: Update deployment yaml**

In `deploy/slack-bot/deployment.yaml`, replace the `ADMIN_SLACK_ID` env block with:
```yaml
            - name: ADMIN_EMAIL
              valueFrom:
                secretKeyRef:
                  name: slack-credentials
                  key: admin-email
```

- [ ] **Step 5: Commit**

```bash
git add jobs/cli.py deploy/slack-bot/deployment.yaml
git commit -m "feat: CLI uses email identity, admin subcommands, ADMIN_EMAIL env var"
```

---

## Task 9: Update All Tests

**Files:**
- Modify: `jobs/tests/test_operations.py`
- Modify: `jobs/tests/test_training.py`
- Modify: `jobs/tests/test_unified.py`
- Modify: `jobs/tests/test_signal_pipeline.py`
- Modify: `jobs/tests/test_characters.py`
- Modify: `jobs/tests/test_enrollment_approval.py`
- Modify: `jobs/tests/test_profile_collection.py`
- Modify: `jobs/tests/test_handbook.py`
- Modify: `jobs/tests/test_debrief.py`
- Modify: `jobs/tests/test_pulse_scanner.py`

This task updates all existing tests to use the new identity model. The changes are mechanical — replace `slack_user_id` with `user_id` or `email` in fixtures, mocks, and assertions.

- [ ] **Step 1: Update test_operations.py**

Replace `SAMPLE_ENROLLMENT` fixture `slack_user_id` with `email` and `id` fields. Update all `get_enrollment` mocks to `get_user_by_email`. Update `enroll` calls from `enroll(slack_user_id, name, role)` to `enroll(email, name, role)`.

- [ ] **Step 2: Update test_training.py**

Replace enrollment GraphQL mocks with user table equivalents. Update `get_active_enrollments` → `get_active_users`. Update `slack_user_id` assertions to `email`. Mock `get_slack_user_id` for deliver tests.

- [ ] **Step 3: Update test_unified.py**

Replace `slack_user_id="U123"` in memory fixtures with `user_id="user-uuid"`. Update `get_enrollment` mocks to `resolve_user` or `get_user_by_email`. Update pipeline test fixtures.

- [ ] **Step 4: Update test_signal_pipeline.py**

Replace `slack_user_id` in interaction assertions with `user_id`. Update `test_slack_user_id_included_in_interaction` → `test_user_id_included_in_interaction`.

- [ ] **Step 5: Update test_characters.py**

Update dispatcher tests to pass `user` dict instead of `slack_user_id`. Update enrollment mocks.

- [ ] **Step 6: Update test_enrollment_approval.py**

Rewrite tests for new `enrollment_requests` schema (user_id FK, approved_by email). Remove `_detect_enrollment_action` tests (replaced by `_detect_admin_command`). Add admin command detection tests.

- [ ] **Step 7: Update test_profile_collection.py, test_handbook.py, test_debrief.py**

Replace `slack_user_id` in mocks with `user_id`. Update GraphQL mock return values.

- [ ] **Step 8: Update test_pulse_scanner.py**

Update owner_slack_id mocks to owner_user_id. Mock `get_slack_user_id` for DM sending tests.

- [ ] **Step 9: Run full test suite**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 10: Run ruff**

Run: `cd jobs && ruff check .`
Expected: No errors

- [ ] **Step 11: Commit**

```bash
git add jobs/tests/
git commit -m "test: update all tests for email-first identity model"
```

---

## Task 10: Apply Schema + Seed Admin

**Files:** None (operational task)

- [ ] **Step 1: Apply schema to production database**

```bash
KUBECONFIG=kubeconfig-mother-tree.yaml kubectl exec -n mother-tree mother-tree-db-1 -c postgres -- psql -U postgres -d mothertree
```

Drop old tables (they're empty):
```sql
DROP TABLE IF EXISTS enrollment_requests CASCADE;
DROP TABLE IF EXISTS help_delivered CASCADE;
DROP TABLE IF EXISTS responses CASCADE;
DROP TABLE IF EXISTS training_progress CASCADE;
DROP TABLE IF EXISTS exercises CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS enrollment CASCADE;
```

Then apply the new schema.sql.

- [ ] **Step 2: Add ADMIN_EMAIL to slack-credentials secret**

```bash
KUBECONFIG=kubeconfig-mother-tree.yaml kubectl edit secret slack-credentials -n mother-tree
```

Add `admin-email: <base64-encoded-email>`.

- [ ] **Step 3: Verify PostGraphile picks up new tables**

Restart the graphql deployment:
```bash
KUBECONFIG=kubeconfig-mother-tree.yaml kubectl rollout restart deployment graphql -n mother-tree
```

- [ ] **Step 4: Push and verify CI passes**

```bash
git push
```

Wait for CI to pass (ruff + tests).
