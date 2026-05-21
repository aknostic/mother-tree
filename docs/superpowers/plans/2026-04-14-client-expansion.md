# Client Expansion Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build account plans, service meeting rhythm, QBR discipline, and expansion trigger detection for existing client accounts.

**Architecture:** New `account_plans` table + enriched `companies`/`engagements` tables. Account plan creation via conversational DM. Service meetings (monthly per engagement) and QBRs (quarterly per account) use the same pattern as existing discipline modules. Expansion triggers added to Pulse scanner.

**Tech Stack:** Python, PostgreSQL, PostGraphile GraphQL, Scaleway Generative APIs, pytest.

**Spec:** `docs/superpowers/specs/2026-04-14-client-expansion-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `jobs/discipline/qbr_review.py` | QBR synthesis + service meeting prep/tracking + delivery |
| `jobs/tests/test_account_plans.py` | Account plan CRUD, service meeting, bot command tests |
| `jobs/tests/test_qbr.py` | QBR synthesis + expansion trigger tests |
| `deploy/cronjobs/discipline-qbr-review.yaml` | Monthly CronJob: check QBRs + service meetings |

### Modified Files

| File | Change |
|------|--------|
| `deploy/database/schema.sql` | Add `account_plans` table, ALTER `companies` + `engagements` |
| `jobs/mothertree/graphql_client.py` | Account plan + company + engagement CRUD functions |
| `jobs/bot/detect.py` | Detect `review`, `account plan`, `accounts`, `service meeting` commands |
| `jobs/bot/characters/dispatcher.py` | Detect `review`, `accounts`, `account plan`, `service meeting` in DM |
| `jobs/bot/pipeline.py` | Handle account_review, account_plan, account_list, service_meeting annotations |
| `jobs/pulse/scanner.py` | Add `scan_expansion_triggers` |
| `jobs/cli.py` | Add `accounts` subcommand |
| `deploy/kustomization.yaml` | Add QBR CronJob reference |

---

## Task 1: Schema

**Files:**
- Modify: `deploy/database/schema.sql`

- [ ] **Step 1: Add client fields to companies table**

After the existing `companies` table and its indexes, add:

```sql
-- === CLIENT ACCOUNT MANAGEMENT ===
ALTER TABLE companies ADD COLUMN IF NOT EXISTS client_since DATE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contract_value TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS services TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;
```

- [ ] **Step 2: Add service meeting fields to engagements table**

```sql
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS next_service_meeting DATE;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS last_service_meeting TIMESTAMPTZ;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS service_meeting_notes TEXT;
```

- [ ] **Step 3: Create account_plans table**

After the enrollment_requests section:

```sql
-- === ACCOUNT PLANS ===
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

- [ ] **Step 4: Commit**

```bash
git add deploy/database/schema.sql
git commit -m "schema: add account_plans table, client fields on companies, service meeting fields on engagements"
```

---

## Task 2: GraphQL CRUD Functions

**Files:**
- Modify: `jobs/mothertree/graphql_client.py`
- Create: `jobs/tests/test_account_plans.py`

- [ ] **Step 1: Write failing tests for account plan CRUD**

Create `jobs/tests/test_account_plans.py`:

```python
"""Tests for account plan and client expansion GraphQL functions."""
from unittest.mock import patch


class TestAccountPlanCRUD:
    @patch("mothertree.graphql_client.graphql")
    def test_get_account_plan(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "whiteSpace": "AI platform", "strategy": "Expand to ML ops"}
        ]}
        from mothertree.graphql_client import get_account_plan
        plan = get_account_plan("co-1")
        assert plan is not None
        assert plan["whiteSpace"] == "AI platform"

    @patch("mothertree.graphql_client.graphql")
    def test_get_account_plan_not_found(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": []}
        from mothertree.graphql_client import get_account_plan
        assert get_account_plan("co-unknown") is None

    @patch("mothertree.graphql_client.graphql")
    def test_create_account_plan(self, mock_gql):
        mock_gql.return_value = {"createAccountPlan": {"accountPlan": {"id": "plan-1", "companyId": "co-1"}}}
        from mothertree.graphql_client import create_account_plan
        plan = create_account_plan("co-1", white_space="AI platform")
        assert plan is not None

    @patch("mothertree.graphql_client.graphql")
    def test_update_account_plan(self, mock_gql):
        mock_gql.return_value = {"updateAccountPlanById": {"accountPlan": {"id": "plan-1"}}}
        from mothertree.graphql_client import update_account_plan
        update_account_plan("plan-1", strategy="Expand to ML ops")
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_get_due_qbrs(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "nextQbr": "2026-04-01"}
        ]}
        from mothertree.graphql_client import get_due_qbrs
        plans = get_due_qbrs()
        assert len(plans) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_get_accounts_with_plans(self, mock_gql):
        mock_gql.return_value = {"allAccountPlansList": [
            {"id": "plan-1", "companyId": "co-1", "companyByCompanyId": {"name": "Sanoma Learning"}}
        ]}
        from mothertree.graphql_client import get_accounts_with_plans
        accounts = get_accounts_with_plans()
        assert len(accounts) == 1


class TestCompanyClientFields:
    @patch("mothertree.graphql_client.graphql")
    def test_update_company_client_fields(self, mock_gql):
        mock_gql.return_value = {"updateCompanyById": {"company": {"id": "co-1"}}}
        from mothertree.graphql_client import update_company_client_fields
        update_company_client_fields("co-1", client_since="2014-01-01", services=["IDP", "operate"])
        mock_gql.assert_called_once()

    @patch("mothertree.graphql_client.graphql")
    def test_get_client_companies(self, mock_gql):
        mock_gql.return_value = {"allCompaniesList": [
            {"id": "co-1", "name": "Sanoma Learning", "clientSince": "2014-01-01"}
        ]}
        from mothertree.graphql_client import get_client_companies
        clients = get_client_companies()
        assert len(clients) == 1


class TestEngagementServiceMeeting:
    @patch("mothertree.graphql_client.graphql")
    def test_get_due_service_meetings(self, mock_gql):
        mock_gql.return_value = {"allEngagementsList": [
            {"id": "eng-1", "title": "IDP Build", "nextServiceMeeting": "2026-04-14", "ownerUserId": "user-1"}
        ]}
        from mothertree.graphql_client import get_due_service_meetings
        meetings = get_due_service_meetings()
        assert len(meetings) == 1

    @patch("mothertree.graphql_client.graphql")
    def test_update_service_meeting(self, mock_gql):
        mock_gql.return_value = {"updateEngagementById": {"engagement": {"id": "eng-1"}}}
        from mothertree.graphql_client import update_service_meeting
        update_service_meeting("eng-1", notes="All good", next_date="2026-05-14")
        mock_gql.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_account_plans.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement GraphQL functions**

In `jobs/mothertree/graphql_client.py`, add after the admin management section:

```python
# --- Account plans ---

def get_account_plan(company_id: str) -> dict | None:
    """Get account plan for a company."""
    result = graphql("""
    query($cid: UUID!) {
        allAccountPlansList(condition: {companyId: $cid}, first: 1) {
            id companyId whiteSpace expansionTriggers strategy
            qbrNotes qbrAt nextQbr createdAt updatedAt
        }
    }
    """, {"cid": company_id})
    plans = result.get("allAccountPlansList", [])
    return plans[0] if plans else None


def create_account_plan(company_id: str, **fields) -> dict:
    """Create an account plan for a company."""
    obj = {"companyId": company_id}
    field_map = {
        "white_space": "whiteSpace", "expansion_triggers": "expansionTriggers",
        "strategy": "strategy", "next_qbr": "nextQbr",
    }
    for k, v in fields.items():
        if v is not None and k in field_map:
            obj[field_map[k]] = v
    result = graphql("""
    mutation($obj: AccountPlanInput!) {
        createAccountPlan(input: {accountPlan: $obj}) {
            accountPlan { id companyId }
        }
    }
    """, {"obj": obj})
    return result.get("createAccountPlan", {}).get("accountPlan")


def update_account_plan(plan_id: str, **fields) -> None:
    """Update an account plan."""
    field_map = {
        "white_space": "whiteSpace", "expansion_triggers": "expansionTriggers",
        "strategy": "strategy", "qbr_notes": "qbrNotes", "qbr_at": "qbrAt",
        "next_qbr": "nextQbr",
    }
    patch = {}
    for k, v in fields.items():
        if k in field_map:
            patch[field_map[k]] = v
    if not patch:
        return
    graphql("""
    mutation($id: UUID!, $patch: AccountPlanPatch!) {
        updateAccountPlanById(input: {id: $id, accountPlanPatch: $patch}) {
            accountPlan { id }
        }
    }
    """, {"id": plan_id, "patch": patch})


def get_due_qbrs() -> list[dict]:
    """Get account plans with QBR due (next_qbr <= now)."""
    from datetime import datetime
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    result = graphql("""
    query($now: Date!) {
        allAccountPlansList(filter: {nextQbr: {lessThanOrEqualTo: $now}}) {
            id companyId whiteSpace strategy qbrNotes nextQbr
            companyByCompanyId { id name services ownerUserId }
        }
    }
    """, {"now": now})
    return result.get("allAccountPlansList", [])


def get_accounts_with_plans() -> list[dict]:
    """Get all companies that have account plans."""
    result = graphql("""
    query {
        allAccountPlansList {
            id companyId whiteSpace strategy nextQbr
            companyByCompanyId { id name clientSince services ownerUserId }
        }
    }
    """)
    return result.get("allAccountPlansList", [])


# --- Company client fields ---

def update_company_client_fields(company_id: str, **fields) -> None:
    """Update client-specific fields on a company."""
    field_map = {
        "client_since": "clientSince", "contract_value": "contractValue",
        "services": "services", "owner_user_id": "ownerUserId",
    }
    patch = {}
    for k, v in fields.items():
        if k in field_map:
            patch[field_map[k]] = v
    if not patch:
        return
    graphql("""
    mutation($id: UUID!, $patch: CompanyPatch!) {
        updateCompanyById(input: {id: $id, companyPatch: $patch}) {
            company { id }
        }
    }
    """, {"id": company_id, "patch": patch})


def get_client_companies() -> list[dict]:
    """Get companies that are active clients (client_since is set)."""
    result = graphql("""
    query {
        allCompaniesList(filter: {clientSince: {isNull: false}}) {
            id name clientSince contractValue services ownerUserId
        }
    }
    """)
    return result.get("allCompaniesList", [])


# --- Engagement service meetings ---

def get_due_service_meetings() -> list[dict]:
    """Get engagements with service meetings due (next_service_meeting <= now)."""
    from datetime import datetime
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    result = graphql("""
    query($now: Date!) {
        allEngagementsList(filter: {
            nextServiceMeeting: {lessThanOrEqualTo: $now},
            status: {equalTo: "active"}
        }) {
            id title ownerUserId nextServiceMeeting lastServiceMeeting
            companyByCompanyId { id name }
        }
    }
    """, {"now": now})
    return result.get("allEngagementsList", [])


def update_service_meeting(engagement_id: str, notes: str = None, next_date: str = None) -> None:
    """Update service meeting state on an engagement."""
    from datetime import datetime
    patch = {"lastServiceMeeting": datetime.now(UTC).isoformat()}
    if notes:
        patch["serviceMeetingNotes"] = notes
    if next_date:
        patch["nextServiceMeeting"] = next_date
    graphql("""
    mutation($id: UUID!, $patch: EngagementPatch!) {
        updateEngagementById(input: {id: $id, engagementPatch: $patch}) {
            engagement { id }
        }
    }
    """, {"id": engagement_id, "patch": patch})
```

- [ ] **Step 4: Run tests**

Run: `cd jobs && python -m pytest tests/test_account_plans.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/graphql_client.py jobs/tests/test_account_plans.py
git commit -m "feat: GraphQL CRUD for account plans, company client fields, service meetings"
```

---

## Task 3: Bot Commands — Detection + Dispatch

**Files:**
- Modify: `jobs/bot/detect.py`
- Modify: `jobs/bot/characters/dispatcher.py`

- [ ] **Step 1: Add account commands to detect.py**

In `detect.py`, add `"review"`, `"accounts"` to `GLOBAL_COMMANDS` (line 14):

```python
GLOBAL_COMMANDS = {"enroll", "status", "progress", "stats", "help", "review", "accounts"}
```

In the global commands section (after the `help` handler), add:

```python
        elif first == "review":
            company_name = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "account_review", "company": company_name}

        elif first == "accounts":
            result["annotation"] = {"type": "account_list"}
```

In the DM-only section (before the training patterns, around line 310), add account plan and service meeting detection:

```python
        # Account plan creation/update
        if first == "account" and len(parts) >= 3 and parts[1].lower() == "plan":
            company_name = " ".join(parts[2:])
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "account_plan", "company": company_name}
            return result

        # Service meeting debrief
        if first == "service" and len(parts) >= 2 and parts[1].lower() == "meeting":
            content = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["pattern_matched"] = True
            result["must_respond"] = True
            result["annotation"] = {"type": "service_meeting", "content": content}
            return result
```

- [ ] **Step 2: Add same patterns to dispatcher.py**

In `dispatcher.py`, the `dispatch()` function handles global commands (line 218). Add the same patterns there so both detect.py (used by tests) and dispatcher.py (used by pipeline) recognize them.

Add `"review"`, `"accounts"` to `GLOBAL_COMMANDS` (line 19):

```python
GLOBAL_COMMANDS = {"enroll", "status", "progress", "stats", "help", "review", "accounts"}
```

Add handlers in the global commands section:

```python
        elif first == "review":
            company_name = " ".join(parts[1:]) if len(parts) > 1 else None
            result["annotation"] = {"type": "account_review", "company": company_name}
        elif first == "accounts":
            result["annotation"] = {"type": "account_list"}
```

Add DM-only patterns before the training section:

```python
    # Account plan + service meeting (DM only)
    if participant_count == 1:
        if first == "account" and len(parts) >= 3 and parts[1].lower() == "plan":
            company_name = " ".join(parts[2:])
            result["must_respond"] = True
            result["intent"] = "account"
            result["annotation"] = {"type": "account_plan", "company": company_name}
            return result

        if first == "service" and len(parts) >= 2 and parts[1].lower() == "meeting":
            content = " ".join(parts[2:]) if len(parts) > 2 else ""
            result["must_respond"] = True
            result["intent"] = "service_meeting"
            result["annotation"] = {"type": "service_meeting", "content": content}
            return result
```

- [ ] **Step 3: Run existing tests**

Run: `cd jobs && python -m pytest tests/test_characters.py tests/test_unified.py -v --tb=short`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add jobs/bot/detect.py jobs/bot/characters/dispatcher.py
git commit -m "feat: detect review, accounts, account plan, service meeting commands"
```

---

## Task 4: Pipeline Handlers

**Files:**
- Modify: `jobs/bot/pipeline.py`

- [ ] **Step 1: Add account handlers to _get_response**

In `_get_response()`, after the admin command handler and before the help handler, add:

```python
        if annotation and annotation.get("type") == "account_review":
            return _handle_account_review(annotation)

        if annotation and annotation.get("type") == "account_plan":
            return _handle_account_plan(annotation)

        if annotation and annotation.get("type") == "account_list":
            return _handle_account_list()

        if annotation and annotation.get("type") == "service_meeting":
            return _handle_service_meeting(annotation)
```

- [ ] **Step 2: Implement _handle_account_review**

```python
def _handle_account_review(annotation: dict) -> str:
    """Generate on-demand QBR synthesis for a company."""
    from discipline.qbr_review import synthesize_qbr
    from mothertree.graphql_client import graphql

    company_name = annotation.get("company")
    if not company_name:
        return "Usage: `review <company name>`"

    # Find company
    result = graphql("""
    query($name: String!) {
        allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) {
            id name
        }
    }
    """, {"name": company_name})
    companies = result.get("allCompaniesList", [])
    if not companies:
        return f"No company found matching '{company_name}'."

    company = companies[0]
    briefing = synthesize_qbr(company["id"], company["name"])
    return briefing
```

- [ ] **Step 3: Implement _handle_account_plan**

```python
def _handle_account_plan(annotation: dict) -> str:
    """Create or update an account plan conversationally."""
    from mothertree.graphql_client import (
        create_account_plan,
        get_account_plan,
        graphql,
    )

    company_name = annotation.get("company")
    if not company_name:
        return "Usage: `account plan <company name>`"

    # Find or create company
    result = graphql("""
    query($name: String!) {
        allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) {
            id name clientSince services
            contactsByCompanyId: contactsList(first: 10) { name role }
        }
    }
    """, {"name": company_name})
    companies = result.get("allCompaniesList", [])
    if not companies:
        return f"No company found matching '{company_name}'. Create it first by mentioning them in a conversation."

    company = companies[0]
    plan = get_account_plan(company["id"])

    contacts = company.get("contactsByCompanyId", [])
    contact_lines = [f"• {c['name']} ({c.get('role', '?')})" for c in contacts] if contacts else ["• (none tracked)"]
    services = company.get("services") or []
    services_str = ", ".join(services) if services else "(not set)"

    if plan:
        return (
            f"*Account plan for {company['name']}:*\n\n"
            f"*Services:* {services_str}\n"
            f"*Stakeholders:*\n" + "\n".join(contact_lines) + "\n\n"
            f"*White space:* {plan.get('whiteSpace') or '(not set)'}\n"
            f"*Strategy:* {plan.get('strategy') or '(not set)'}\n"
            f"*Triggers:* {', '.join(plan.get('expansionTriggers') or []) or '(not set)'}\n\n"
            f"To update, tell me what changed."
        )

    # No plan yet — draft from available data
    create_account_plan(company["id"])
    return (
        f"*Starting account plan for {company['name']}.*\n\n"
        f"Here's what I know:\n"
        f"*Services:* {services_str}\n"
        f"*Stakeholders:*\n" + "\n".join(contact_lines) + "\n\n"
        f"What's the *white space* — where could we expand?\n"
        f"What *triggers* should I watch for? (role changes, contract renewals, new pain)\n"
        f"What's the *strategy* for growing this account?"
    )
```

- [ ] **Step 4: Implement _handle_account_list**

```python
def _handle_account_list() -> str:
    """List all companies with account plans."""
    from mothertree.graphql_client import get_accounts_with_plans

    accounts = get_accounts_with_plans()
    if not accounts:
        return "No account plans yet. Say `account plan <company>` to start one."

    lines = ["*Account plans:*"]
    for a in accounts:
        company = a.get("companyByCompanyId", {})
        name = company.get("name", "?")
        next_qbr = a.get("nextQbr", "not set")
        lines.append(f"• *{name}* — QBR: {next_qbr}")
    return "\n".join(lines)
```

- [ ] **Step 5: Implement _handle_service_meeting**

```python
def _handle_service_meeting(annotation: dict) -> str:
    """Handle service meeting debrief — route to existing debrief pipeline."""
    content = annotation.get("content", "")
    if not content:
        return "Paste your service meeting notes after the command: `service meeting <notes>`"

    from bot.characters.spotter import extract_debrief
    extraction = extract_debrief(content)
    if extraction:
        return _format_debrief_preview(extraction)
    return "I couldn't extract anything meaningful from those notes. Try including more detail about attendees, topics discussed, and outcomes."
```

- [ ] **Step 6: Run tests**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add jobs/bot/pipeline.py
git commit -m "feat: pipeline handlers for account review, account plan, account list, service meeting"
```

---

## Task 5: QBR Review Module

**Files:**
- Create: `jobs/discipline/qbr_review.py`
- Create: `jobs/tests/test_qbr.py`

- [ ] **Step 1: Write failing tests**

Create `jobs/tests/test_qbr.py`:

```python
"""Tests for QBR synthesis and service meeting scheduling."""
from unittest.mock import MagicMock, patch


class TestSynthesizeQBR:
    @patch("discipline.qbr_review.generate")
    @patch("discipline.qbr_review.graphql")
    def test_synthesizes_briefing(self, mock_gql, mock_gen):
        mock_gql.return_value = {
            "allContactsList": [{"name": "JJ", "role": "Engineering Lead"}],
            "allInteractionsList": [],
            "allSignalsList": [],
            "allOpportunitiesList": [],
            "allEngagementsList": [{"title": "IDP Build", "status": "active"}],
        }
        mock_gen.return_value = "QBR briefing for Sanoma Learning"
        from discipline.qbr_review import synthesize_qbr
        result = synthesize_qbr("co-1", "Sanoma Learning")
        assert "Sanoma Learning" in result or "QBR" in result
        mock_gen.assert_called_once()


class TestDeliverQBRs:
    @patch("discipline.qbr_review.get_slack_user_id")
    @patch("discipline.qbr_review.synthesize_qbr")
    @patch("discipline.qbr_review.get_due_qbrs")
    @patch("discipline.qbr_review.update_account_plan")
    def test_delivers_due_qbrs(self, mock_update, mock_due, mock_synth, mock_slack_id):
        mock_due.return_value = [{
            "id": "plan-1", "companyId": "co-1", "nextQbr": "2026-04-01",
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma", "ownerUserId": "user-1"},
        }]
        mock_synth.return_value = "Briefing text"
        mock_slack_id.return_value = "U_JURG"
        from discipline.qbr_review import deliver_qbrs
        slack = MagicMock()
        deliver_qbrs(slack)
        mock_synth.assert_called_once()
        mock_update.assert_called_once()
        slack.chat_postMessage.assert_called_once()


class TestDeliverServiceMeetingPreps:
    @patch("discipline.qbr_review.get_slack_user_id")
    @patch("discipline.qbr_review.generate")
    @patch("discipline.qbr_review.get_due_service_meetings")
    def test_delivers_prep_for_due_meetings(self, mock_due, mock_gen, mock_slack_id):
        mock_due.return_value = [{
            "id": "eng-1", "title": "IDP Build", "ownerUserId": "user-1",
            "nextServiceMeeting": "2026-04-15",
            "companyByCompanyId": {"id": "co-1", "name": "Sanoma"},
        }]
        mock_gen.return_value = "Service meeting prep"
        mock_slack_id.return_value = "U_JURG"
        from discipline.qbr_review import deliver_service_meeting_preps
        slack = MagicMock()
        deliver_service_meeting_preps(slack)
        mock_gen.assert_called_once()
        slack.chat_postMessage.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jobs && python -m pytest tests/test_qbr.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement qbr_review.py**

Create `jobs/discipline/qbr_review.py`:

```python
"""Quarterly business review + service meeting rhythm.

QBRs: quarterly per account, strategic synthesis for decision makers.
Service meetings: monthly per engagement, operational prep for delivery team.
"""
import logging
from datetime import UTC, datetime, timedelta

from slack_sdk import WebClient

from mothertree.config import SLACK_BOT_TOKEN
from mothertree.graphql_client import (
    get_due_qbrs,
    get_due_service_meetings,
    get_slack_user_id,
    graphql,
    update_account_plan,
)
from mothertree.llm import generate

log = logging.getLogger(__name__)


def synthesize_qbr(company_id: str, company_name: str) -> str:
    """Generate a QBR briefing for a company from available data."""
    data = graphql("""
    query($cid: UUID!) {
        allContactsList(condition: {companyId: $cid}) { name role }
        allInteractionsList(filter: {contactByContactId: {companyId: {equalTo: $cid}}}, first: 20, orderBy: DATE_DESC) {
            type summary date
        }
        allSignalsList(filter: {companyByCompanyId: {id: {equalTo: $cid}}}, first: 20, orderBy: CREATED_AT_DESC) {
            content source createdAt
        }
        allOpportunitiesList(condition: {companyId: $cid}) {
            stage title nextAction nextActionDate
        }
        allEngagementsList(condition: {companyId: $cid}) {
            title status type serviceMeetingNotes
        }
    }
    """, {"cid": company_id})

    contacts = data.get("allContactsList", [])
    interactions = data.get("allInteractionsList", [])
    signals = data.get("allSignalsList", [])
    opportunities = data.get("allOpportunitiesList", [])
    engagements = data.get("allEngagementsList", [])

    context = (
        f"Company: {company_name}\n"
        f"Stakeholders: {', '.join(c['name'] + ' (' + (c.get('role') or '?') + ')' for c in contacts) or 'none tracked'}\n"
        f"Active engagements: {', '.join(e['title'] + ' (' + e['status'] + ')' for e in engagements) or 'none'}\n"
        f"Pipeline: {', '.join(o.get('title', o['stage']) for o in opportunities) or 'no opportunities'}\n"
        f"Recent interactions ({len(interactions)}): {'; '.join((i.get('summary') or i['type'])[:80] for i in interactions[:5]) or 'none'}\n"
        f"Recent signals ({len(signals)}): {'; '.join(s['content'][:80] for s in signals[:5]) or 'none'}\n"
    )

    for e in engagements:
        if e.get("serviceMeetingNotes"):
            context += f"\nService meeting notes ({e['title']}): {e['serviceMeetingNotes'][:200]}"

    system = (
        "You are Mother Tree writing a quarterly business review for a consultative sales team. "
        "Be direct and actionable. Structure as:\n"
        "1. *Account health* — what's working, what needs attention\n"
        "2. *Engagement status* — where each engagement stands\n"
        "3. *Expansion opportunities* — white space, triggers, next moves\n"
        "4. *Recommended actions* — 2-3 specific things to do this quarter\n\n"
        "Keep it under 400 words. Use Slack formatting (*bold*, bullets). "
        "Frame for strategic stakeholders, not the delivery team."
    )

    return generate(system, f"QBR data for {company_name}:\n{context}")


def deliver_qbrs(slack: WebClient) -> None:
    """Check and deliver any due QBRs."""
    due = get_due_qbrs()
    log.info("QBR: %d due reviews", len(due))

    for plan in due:
        company = plan.get("companyByCompanyId", {})
        company_name = company.get("name", "?")
        owner_user_id = company.get("ownerUserId")

        try:
            briefing = synthesize_qbr(plan["companyId"], company_name)

            # Store and advance
            next_qbr = (datetime.now(UTC) + timedelta(days=90)).strftime("%Y-%m-%d")
            update_account_plan(
                plan["id"],
                qbr_notes=briefing,
                qbr_at=datetime.now(UTC).isoformat(),
                next_qbr=next_qbr,
            )

            # DM the account owner
            if owner_user_id:
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    slack.chat_postMessage(
                        channel=slack_id,
                        text=f"*Quarterly review: {company_name}*\n\n{briefing}",
                    )
                    log.info("QBR delivered for %s", company_name)
        except Exception:
            log.exception("QBR failed for %s", company_name)


def deliver_service_meeting_preps(slack: WebClient) -> None:
    """Check and deliver service meeting preps for due meetings."""
    due = get_due_service_meetings()
    log.info("Service meetings: %d due", len(due))

    for eng in due:
        company = eng.get("companyByCompanyId", {})
        company_name = company.get("name", "?")
        owner_user_id = eng.get("ownerUserId")

        try:
            # Gather context for prep
            context = f"Engagement: {eng.get('title', '?')} at {company_name}"
            if company.get("id"):
                data = graphql("""
                query($cid: UUID!) {
                    allInteractionsList(filter: {contactByContactId: {companyId: {equalTo: $cid}}}, first: 10, orderBy: DATE_DESC) {
                        type summary date
                    }
                    allSignalsList(filter: {companyByCompanyId: {id: {equalTo: $cid}}}, first: 5, orderBy: CREATED_AT_DESC) {
                        content
                    }
                }
                """, {"cid": company["id"]})
                interactions = data.get("allInteractionsList", [])
                signals = data.get("allSignalsList", [])
                context += f"\nRecent interactions: {'; '.join((i.get('summary') or '')[:60] for i in interactions[:3]) or 'none'}"
                context += f"\nRecent signals: {'; '.join(s['content'][:60] for s in signals[:3]) or 'none'}"

            prep = generate(
                "You are Mother Tree preparing a service meeting briefing. "
                "Summarize what's happened since last meeting, flag open issues, "
                "suggest topics to raise. Under 200 words. Use Slack formatting.",
                context,
            )

            if owner_user_id:
                slack_id = get_slack_user_id(owner_user_id)
                if slack_id:
                    slack.chat_postMessage(
                        channel=slack_id,
                        text=f"*Service meeting prep: {eng.get('title', '?')} ({company_name})*\n\n{prep}",
                    )
                    log.info("Service meeting prep sent for %s", eng.get("title"))
        except Exception:
            log.exception("Service meeting prep failed for %s", eng.get("title"))


def deliver_reviews() -> None:
    """CronJob: check and deliver QBRs + service meeting preps."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    slack = WebClient(token=SLACK_BOT_TOKEN)
    deliver_qbrs(slack)
    deliver_service_meeting_preps(slack)


def main():
    """CLI entry point."""
    deliver_reviews()
```

- [ ] **Step 4: Run tests**

Run: `cd jobs && python -m pytest tests/test_qbr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/discipline/qbr_review.py jobs/tests/test_qbr.py
git commit -m "feat: QBR synthesis + service meeting prep module"
```

---

## Task 6: Expansion Trigger Detection

**Files:**
- Modify: `jobs/pulse/scanner.py`
- Modify: `jobs/tests/test_qbr.py` (add trigger tests)

- [ ] **Step 1: Write failing tests**

Add to `jobs/tests/test_qbr.py`:

```python
class TestExpansionTriggers:
    @patch("pulse.scanner.get_slack_user_id")
    @patch("pulse.scanner.generate_nudge")
    @patch("pulse.scanner.graphql")
    def test_detects_stale_account_plan(self, mock_gql, mock_nudge, mock_slack_id):
        from datetime import UTC, datetime, timedelta
        stale_date = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        mock_gql.return_value = {"allAccountPlansList": [{
            "id": "plan-1",
            "updatedAt": stale_date,
            "companyByCompanyId": {"name": "Sanoma", "ownerUserId": "user-1", "clientSince": "2014-01-01", "pulseNudgedAt": None},
        }]}
        mock_nudge.return_value = "Time to review Sanoma"
        mock_slack_id.return_value = "U_JURG"
        from pulse.scanner import scan_expansion_triggers
        slack = MagicMock()
        scan_expansion_triggers(slack)
        mock_nudge.assert_called_once()

    @patch("pulse.scanner.graphql")
    def test_skips_recently_nudged(self, mock_gql):
        from datetime import UTC, datetime
        mock_gql.return_value = {"allAccountPlansList": [{
            "id": "plan-1",
            "updatedAt": "2026-01-01T00:00:00+00:00",
            "companyByCompanyId": {"name": "Sanoma", "ownerUserId": "user-1", "clientSince": "2014-01-01", "pulseNudgedAt": datetime.now(UTC).isoformat()},
        }]}
        from pulse.scanner import scan_expansion_triggers
        slack = MagicMock()
        scan_expansion_triggers(slack)
        slack.chat_postMessage.assert_not_called()
```

- [ ] **Step 2: Implement scan_expansion_triggers**

In `jobs/pulse/scanner.py`, before the `run_scan()` function, add:

```python
def scan_expansion_triggers(slack: WebClient) -> None:
    """Nudge account owners about expansion opportunities."""
    from datetime import timedelta

    now = datetime.now(UTC)

    # Check stale account plans (>90 days since update, active client)
    result = graphql("""
    query {
        allAccountPlansList {
            id updatedAt
            companyByCompanyId { name ownerUserId clientSince pulseNudgedAt }
        }
    }
    """)
    plans = result.get("allAccountPlansList", [])
    log.info("Expansion: %d account plans to check", len(plans))

    for plan in plans:
        company = plan.get("companyByCompanyId", {})
        if not company.get("clientSince"):
            continue  # Not an active client
        if _recently_nudged(company.get("pulseNudgedAt")):
            continue

        updated = datetime.fromisoformat(plan["updatedAt"])
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        days_stale = (now - updated).days

        if days_stale < 90:
            continue

        owner_user_id = company.get("ownerUserId")
        if not owner_user_id:
            continue

        message = generate_nudge(
            nudge_type="expansion",
            target_description=f"Account plan for {company['name']} — last updated {days_stale} days ago",
            ci_context="",
        )

        slack_id = get_slack_user_id(owner_user_id)
        if slack_id:
            _send_dm(slack, slack_id, message)
            mark_contact_pulse_nudged(plan["id"])  # Reuse for account plan nudge tracking
            log.info("Expansion: nudged stale plan for %s", company["name"])
```

- [ ] **Step 3: Wire into run_scan()**

In `run_scan()`, add after `scan_pipeline(slack)`:

```python
    scan_expansion_triggers(slack)
```

- [ ] **Step 4: Run tests**

Run: `cd jobs && python -m pytest tests/test_qbr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jobs/pulse/scanner.py jobs/tests/test_qbr.py
git commit -m "feat: expansion trigger detection in Pulse scanner"
```

---

## Task 7: CLI + CronJob + Deployment

**Files:**
- Modify: `jobs/cli.py`
- Create: `deploy/cronjobs/discipline-qbr-review.yaml`
- Modify: `deploy/kustomization.yaml`

- [ ] **Step 1: Add accounts subcommand to CLI**

In `jobs/cli.py`, after the `admin` command block, add:

```python
    elif cmd == "accounts":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "list":
            from mothertree.graphql_client import get_accounts_with_plans
            accounts = get_accounts_with_plans()
            if not accounts:
                print("No account plans.")
            else:
                for a in accounts:
                    co = a.get("companyByCompanyId", {})
                    print(f"  {co.get('name', '?')} — QBR: {a.get('nextQbr', 'not set')}")
        elif subcmd == "review":
            if len(args) < 3:
                print("Usage: mothertree accounts review <company>")
                sys.exit(1)
            company_name = " ".join(args[2:])
            from mothertree.graphql_client import graphql
            result = graphql("""
            query($name: String!) {
                allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
            }
            """, {"name": company_name})
            companies = result.get("allCompaniesList", [])
            if not companies:
                print(f"No company found matching '{company_name}'")
            else:
                from discipline.qbr_review import synthesize_qbr
                print(synthesize_qbr(companies[0]["id"], companies[0]["name"]))
        elif subcmd == "qbr":
            from discipline.qbr_review import main as qbr_main
            qbr_main()
        else:
            print("Usage: mothertree accounts {list|review|qbr}")
```

- [ ] **Step 2: Wire QBR into rhythm commands**

In the `rhythm`/`discipline` command block, add after the `pulse` handler:

```python
        elif subcmd == "qbr":
            from discipline.qbr_review import main as qbr_main
            qbr_main()
```

- [ ] **Step 3: Create CronJob manifest**

Create `deploy/cronjobs/discipline-qbr-review.yaml` using the monthly retro as template:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: discipline-qbr-review
  namespace: mother-tree
spec:
  schedule: "0 7 * * 1" # Every Monday 07:00 UTC — checks if any QBRs or service meetings are due
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 1
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          imagePullSecrets:
            - name: gitlab-registry
          containers:
            - name: qbr-review
              image: registry.gitlab.aknostic.com/aknostic/mother-tree/jobs:latest # {"$imagepolicy": "mother-tree:jobs"}
              args: ["accounts", "qbr"]
              env:
                - name: HASURA_URL
                  value: "http://graphql:5000/graphql"
                - name: HASURA_ADMIN_SECRET
                  valueFrom:
                    secretKeyRef:
                      name: hasura-admin-secret
                      key: admin-secret
                - name: SCALEWAY_AI_API_KEY
                  valueFrom:
                    secretKeyRef:
                      name: scaleway-ai
                      key: secret-key
                - name: SLACK_BOT_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: slack-credentials
                      key: bot-token
              resources:
                requests: {cpu: 50m, memory: 128Mi}
                limits: {cpu: 500m, memory: 256Mi}
          restartPolicy: Never
```

- [ ] **Step 4: Add to kustomization**

In `deploy/kustomization.yaml`, add in the CronJobs section:

```yaml
  - cronjobs/discipline-qbr-review.yaml
```

- [ ] **Step 5: Run full test suite**

Run: `cd jobs && python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Run ruff**

Run: `cd jobs && ruff check .`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add jobs/cli.py deploy/cronjobs/discipline-qbr-review.yaml deploy/kustomization.yaml
git commit -m "feat: accounts CLI, QBR CronJob, deployment manifest"
```
