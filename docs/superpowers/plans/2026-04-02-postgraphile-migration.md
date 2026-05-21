# PostGraphile Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Hasura with PostGraphile as the GraphQL API layer. Big bang migration, no adapter.

**Architecture:** PostGraphile Node.js container auto-generates GraphQL from the Postgres schema. Postgres functions handle JSONB appends, upserts, and semantic search. Python `graphql()` function stays as the single client — queries rewritten to PostGraphile syntax.

**Tech Stack:** PostGraphile 4.x, @graphile/pg-aggregates, postgraphile-plugin-connection-filter, Node.js 22, Express

---

### Task 1: PostGraphile server + Dockerfile + deployment manifests

**Files:**
- Create: `deploy/graphql/server.js`
- Create: `deploy/graphql/package.json`
- Create: `deploy/graphql/Dockerfile`
- Create: `deploy/graphql/deployment.yaml`
- Create: `deploy/graphql/service.yaml`
- Remove: `deploy/hasura/deployment.yaml`
- Remove: `deploy/hasura/service.yaml`
- Modify: `deploy/kustomization.yaml`

- [ ] **Step 1: Create the PostGraphile server**

`deploy/graphql/server.js`:
```javascript
const express = require("express");
const { postgraphile } = require("postgraphile");
const ConnectionFilterPlugin = require("postgraphile-plugin-connection-filter");
const PgAggregatesPlugin = require("@graphile/pg-aggregates").default;

const app = express();

// Auth middleware — check admin secret header
const ADMIN_SECRET = process.env.ADMIN_SECRET;
app.use("/graphql", (req, res, next) => {
  if (ADMIN_SECRET && req.headers["x-hasura-admin-secret"] !== ADMIN_SECRET) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
});

app.use(
  postgraphile(process.env.DATABASE_URL, "public", {
    appendPlugins: [ConnectionFilterPlugin, PgAggregatesPlugin],
    watchPg: false,
    graphiql: false,
    enhanceGraphiql: false,
    dynamicJson: true,
    setofFunctionsContainNulls: false,
    ignoreRBAC: false,
    showErrorStack: false,
    extendedErrors: [],
    graphqlRoute: "/graphql",
    legacyRelations: "omit",
    simpleCollections: "both",  // enables allChanges and changesList
  })
);

app.get("/healthz", (req, res) => res.send("ok"));

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`PostGraphile running on port ${PORT}`));
```

`deploy/graphql/package.json`:
```json
{
  "name": "mother-tree-graphql",
  "private": true,
  "dependencies": {
    "express": "^4.21",
    "postgraphile": "^4.14",
    "postgraphile-plugin-connection-filter": "^2.3",
    "@graphile/pg-aggregates": "^0.2"
  }
}
```

- [ ] **Step 2: Create the Dockerfile**

`deploy/graphql/Dockerfile`:
```dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json ./
RUN npm install --production
COPY server.js ./
EXPOSE 5000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Create deployment + service manifests**

`deploy/graphql/deployment.yaml` — same pattern as the old Hasura deployment but:
- Image: build from `deploy/graphql/Dockerfile` (add to `.gitlab-ci.yml`)
- Env: `DATABASE_URL` from `mother-tree-db-app` secret, `ADMIN_SECRET` from `hasura-admin-secret`
- Port: 5000
- Health: `/healthz`

`deploy/graphql/service.yaml`:
- Name: `graphql` (not `hasura`)
- Port: 5000

- [ ] **Step 4: Update kustomization.yaml**

Replace:
```yaml
  - hasura/deployment.yaml
  - hasura/service.yaml
```
With:
```yaml
  - graphql/deployment.yaml
  - graphql/service.yaml
```
Keep `hasura/admin-secret.yaml` (rename later or keep — it's just a k8s secret name).

- [ ] **Step 5: Add PostGraphile build to .gitlab-ci.yml**

Add a `build-graphql` job alongside `build-slack-bot` and `build-jobs`.

- [ ] **Step 6: Commit**

```
PostGraphile server, Dockerfile, deployment manifests
```

---

### Task 2: Postgres functions for JSONB appends, upserts, bulk deletes, and semantic search

**Files:**
- Modify: `deploy/database/schema.sql`

- [ ] **Step 1: Add JSONB append functions**

```sql
-- Append a message to channel memory
CREATE OR REPLACE FUNCTION append_channel_message(p_channel_id TEXT, p_message JSONB)
RETURNS channel_memory AS $$
  UPDATE channel_memory
  SET messages = messages || jsonb_build_array(p_message)
  WHERE channel_id = p_channel_id
  RETURNING *;
$$ LANGUAGE sql VOLATILE;

-- Append a message to thread memory
CREATE OR REPLACE FUNCTION append_thread_message_fn(p_thread_ts TEXT, p_channel_id TEXT, p_message JSONB)
RETURNS thread_memory AS $$
  UPDATE thread_memory
  SET messages = messages || jsonb_build_array(p_message)
  WHERE thread_ts = p_thread_ts
  RETURNING *;
$$ LANGUAGE sql VOLATILE;

-- Append a message to a conversation
CREATE OR REPLACE FUNCTION append_conversation_message(p_conversation_id UUID, p_message JSONB)
RETURNS conversations AS $$
  UPDATE conversations
  SET messages = messages || jsonb_build_array(p_message)
  WHERE id = p_conversation_id
  RETURNING *;
$$ LANGUAGE sql VOLATILE;
```

- [ ] **Step 2: Add upsert function for ingestion log**

```sql
CREATE OR REPLACE FUNCTION upsert_ingestion_log(p_source TEXT, p_hash TEXT, p_counts JSONB)
RETURNS ingestion_log AS $$
  INSERT INTO ingestion_log (source, content_hash, record_counts)
  VALUES (p_source, p_hash, p_counts)
  ON CONFLICT (source) DO UPDATE SET
    content_hash = p_hash,
    ingested_at = now(),
    record_counts = p_counts
  RETURNING *;
$$ LANGUAGE sql VOLATILE;
```

- [ ] **Step 3: Add upsert function for training progress**

```sql
CREATE OR REPLACE FUNCTION upsert_training_progress_fn(
  p_hunter_id TEXT, p_area TEXT, p_score REAL,
  p_last_refresher TIMESTAMPTZ DEFAULT NULL
)
RETURNS training_progress AS $$
  INSERT INTO training_progress (hunter_id, area, score, last_refresher)
  VALUES (p_hunter_id, p_area, p_score, p_last_refresher)
  ON CONFLICT (hunter_id, area) DO UPDATE SET
    score = p_score,
    last_refresher = COALESCE(p_last_refresher, training_progress.last_refresher),
    updated_at = now()
  RETURNING *;
$$ LANGUAGE sql VOLATILE;
```

- [ ] **Step 4: Add bulk delete function**

```sql
CREATE OR REPLACE FUNCTION delete_by_source(p_table TEXT, p_source TEXT)
RETURNS INT AS $$
DECLARE
  row_count INT;
BEGIN
  EXECUTE format('DELETE FROM %I WHERE source = $1', p_table) USING p_source;
  GET DIAGNOSTICS row_count = ROW_COUNT;
  RETURN row_count;
END;
$$ LANGUAGE plpgsql VOLATILE;
```

- [ ] **Step 5: Add semantic search functions (replace run_sql)**

```sql
CREATE OR REPLACE FUNCTION search_similar_insights(
  query_embedding vector(3584), max_results INT DEFAULT 10, min_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE(id UUID, category TEXT, reframe TEXT, evidence TEXT, trigger TEXT, confidence REAL, similarity FLOAT) AS $$
  SELECT id, category, reframe, evidence, trigger, confidence,
         (1 - (embedding <-> query_embedding))::float as similarity
  FROM insights
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <-> query_embedding) > min_threshold
  ORDER BY embedding <-> query_embedding
  LIMIT max_results;
$$ LANGUAGE sql STABLE;

-- Repeat pattern for: search_similar_change, search_similar_worldview,
-- search_similar_personas, search_similar_competitors, search_similar_organization,
-- search_similar_signals, search_similar_proof_points
```

One function per table. PostGraphile auto-exposes each as a GraphQL query.

- [ ] **Step 6: Add store_embedding function**

```sql
CREATE OR REPLACE FUNCTION store_embedding(p_table TEXT, p_id UUID, p_embedding vector(3584))
RETURNS VOID AS $$
BEGIN
  EXECUTE format('UPDATE %I SET embedding = $1 WHERE id = $2', p_table) USING p_embedding, p_id;
END;
$$ LANGUAGE plpgsql VOLATILE;
```

- [ ] **Step 7: Apply functions to live database**

Run all functions via kubectl exec into the DB pod.

- [ ] **Step 8: Commit**

```
Postgres functions for PostGraphile: JSONB appends, upserts, semantic search
```

---

### Task 3: Rewrite hasura.py — core client and ingestion functions

**Files:**
- Modify: `jobs/mothertree/hasura.py` (lines 1-150)
- Modify: `jobs/mothertree/config.py`

- [ ] **Step 1: Update config default URL**

```python
HASURA_URL = os.environ.get("HASURA_URL", "http://graphql.mother-tree.svc.cluster.local:5000/graphql")
```

- [ ] **Step 2: Rewrite graphql() client and remove run_sql()**

The `graphql()` function stays identical — PostGraphile speaks standard GraphQL over HTTP. Only the URL changes (config). Remove `run_sql()` entirely.

- [ ] **Step 3: Rewrite ingestion functions to PostGraphile syntax**

Key patterns:
- `insert_X_one(object:)` → `createX(input: {x:})` → result in `{createX: {x: {id}}}`
- `X_by_pk(source:)` → `xBySource(source:)` or `allXList(condition: {source:})`
- `delete_X(where: {source: {_eq:}})` → call `deleteBySource` Postgres function
- `insert_X_one(on_conflict:)` → call upsert Postgres functions

- [ ] **Step 4: Rewrite _insert_record dedup check**

The dedup check queries `table(where: {field: {_eq: $val}})`. In PostGraphile with connection-filter:
```graphql
allChanges(filter: {statement: {equalTo: $val}}, first: 1) { nodes { id } }
```
Or use `simpleCollections: "both"` and query `changesList(condition: {statement: $val}, first: 1) { id }`.

The `condition` syntax (exact match) is simpler than `filter` (operators). Use condition where possible.

- [ ] **Step 5: Rewrite embedding functions — use Postgres functions instead of run_sql**

`store_embedding()` calls the new `store_embedding` Postgres function via GraphQL:
```graphql
mutation { storeEmbedding(input: {pTable: "insights", pId: "...", pEmbedding: "..."}) }
```

`search_similar()` calls table-specific functions:
```graphql
query { searchSimilarInsights(queryEmbedding: "...", maxResults: 10, minThreshold: 0.3) { nodes { id reframe ... similarity } } }
```

- [ ] **Step 6: Run tests, fix mocks**

Most tests mock `graphql()` — the mock interface doesn't change (still returns dicts). But the query strings in call assertions need updating. Fix test assertions that check specific query text.

- [ ] **Step 7: Commit**

```
Rewrite hasura.py core: PostGraphile query syntax, Postgres function calls
```

---

### Task 4: Rewrite hasura.py — signals, contacts, enrollment, training

**Files:**
- Modify: `jobs/mothertree/hasura.py` (lines 247-650)

- [ ] **Step 1: Rewrite signal functions**

`insert_signal`: `createSignal(input: {signal: {...}}) { signal { id } }`
`create_signal_thread`: `createSignalThread(input: {signalThread: {...}}) { signalThread { id } }`
`update_signal_thread`: `updateSignalThreadBySlackThreadTs(...)` or use condition-based update
`get_signal_thread`: `allSignalThreadsList(condition: {slackThreadTs: $ts}) { id ... }`

Note: PostGraphile uses camelCase for GraphQL field names from snake_case columns.

- [ ] **Step 2: Rewrite contact functions**

`find_or_create_contact`: The `_or` + `_ilike` filter needs the connection-filter plugin:
```graphql
allContactsList(filter: {or: [{fullName: {includesInsensitive: $name}}, {name: {includesInsensitive: $name}}]}, first: 1)
```

- [ ] **Step 3: Rewrite enrollment functions**

`get_enrollment`: `allEnrollmentList(condition: {slackUserId: $sid}) { ... }`
`enroll_user`: `createEnrollment(input: {enrollment: {...}}) { enrollment { id } }`
`get_enrollment_stats`: Use aggregates plugin
`advance_enrollment`: `updateEnrollmentById(input: {id: $id, enrollmentPatch: {...}}) { enrollment { id } }`

- [ ] **Step 4: Rewrite training functions**

Most are simple CRUD — translate the insert/update/query patterns.
`update_conversation`: `updateConversationById(input: {id: $id, conversationPatch: {...}})`
`cancel_stale_conversations`: Needs a Postgres function (bulk update with complex WHERE)
`upsert_training_progress`: Call `upsertTrainingProgressFn` Postgres function
`fetch_foundation_for_chapter`: Dynamic multi-table query — build per-table queries

- [ ] **Step 5: Run tests, fix mocks**

- [ ] **Step 6: Commit**

```
Rewrite hasura.py: signals, contacts, enrollment, training
```

---

### Task 5: Rewrite hasura.py — memory (DM, channel, thread) and organization

**Files:**
- Modify: `jobs/mothertree/hasura.py` (lines 650-885)

- [ ] **Step 1: Rewrite DM conversation functions**

`get_or_create_dm_conversation`: Query + create pattern
`append_dm_message`: Call `appendConversationMessage` Postgres function:
```graphql
mutation { appendConversationMessage(input: {pConversationId: $id, pMessage: $msg}) { conversation { id } } }
```
`set_pending_ci_save`: Same pattern as append

- [ ] **Step 2: Rewrite channel memory functions**

`get_or_create_channel_memory`: Query + create
`append_channel_message`: Call `appendChannelMessage` Postgres function
`cap_channel_memory`: `updateChannelMemoryById(input: {id: $id, channelMemoryPatch: {messages: $trimmed}})`

- [ ] **Step 3: Rewrite thread memory functions**

`get_or_create_thread_memory`: Query + create
`append_thread_message`: Call `appendThreadMessageFn` Postgres function
`get_thread_memory_or_signal_thread`: Dual-query pattern stays the same

- [ ] **Step 4: Rewrite organization functions**

`get_organization_profile`: `allOrganizationList(orderBy: [ELEMENT_TYPE_ASC, CONFIDENCE_DESC])`
`insert_organization_element`: `createOrganization(input: {organization: {...}})`
`delete_all_organization`: Needs a Postgres function or direct mutation
`update_organization_element`: `updateOrganizationById(input: {id: $id, organizationPatch: {...}})`

- [ ] **Step 5: Run tests, fix mocks**

- [ ] **Step 6: Commit**

```
Rewrite hasura.py: DM/channel/thread memory, organization profile
```

---

### Task 6: Update all consuming files

**Files:**
- Modify: `jobs/mothertree/ask.py` — 4 graphql calls (fetch_context text search queries)
- Modify: `jobs/ingestion/ingest.py` — 4 graphql calls (stats, truncate, consolidation)
- Modify: `jobs/mothertree/entities.py` — 6 graphql calls
- Modify: `jobs/discipline/calendar_sync.py` — 3 graphql calls
- Modify: `jobs/discipline/weekly_review.py` — 2 graphql calls
- Modify: `jobs/discipline/stale_check.py` — 2 graphql calls
- Modify: `jobs/discipline/monthly_retro.py` — 2 graphql calls
- Modify: `jobs/cli.py` — 4 graphql calls (stats, embed backfill)
- Modify: `jobs/mothertree/dump.py` — 3 graphql calls
- Modify: `jobs/reminders/thread_reminders.py` — 1 graphql call
- Modify: `jobs/bot/characters/weaver.py` — 1 graphql call
- Modify: `jobs/ingestion/profile.py` — 1 graphql call (via delete)

- [ ] **Step 1: Update ask.py text search queries**

The `fetch_context` text search on contacts/signals/interactions uses Hasura `_ilike` and `_or`. Translate to connection-filter `includesInsensitive` and `or`.

- [ ] **Step 2: Update ingest.py**

Stats queries use `*_aggregate`. With pg-aggregates plugin: `allChanges { totalCount }` or `allChanges { aggregates { distinctCount { id } } }`.

Dynamic `delete_{table}(where: {})` for truncate → call `deleteBySource` with empty source or add a `truncate_table` Postgres function.

- [ ] **Step 3: Update all discipline/ files**

Straightforward query syntax translation. These files have simple selects with conditions.

- [ ] **Step 4: Update remaining files (entities, dump, weaver, reminders, profile, cli)**

- [ ] **Step 5: Run full test suite — all 358 tests must pass**

- [ ] **Step 6: Commit**

```
Update all consuming files for PostGraphile query syntax
```

---

### Task 7: Update all CronJob + bot deployment manifests

**Files:**
- Modify: All `deploy/cronjobs/*.yaml` — change `HASURA_URL` env var
- Modify: `deploy/slack-bot/deployment.yaml` — change `HASURA_URL` env var

- [ ] **Step 1: Update HASURA_URL in all manifests**

Change from `http://hasura:8080/v1/graphql` to `http://graphql:5000/graphql`.

Affected files (12+):
- `deploy/slack-bot/deployment.yaml`
- `deploy/cronjobs/foundation-ingest-marketing.yaml`
- `deploy/cronjobs/foundation-ingest-site.yaml`
- `deploy/cronjobs/narrative-ingest-marketing.yaml`
- `deploy/cronjobs/narrative-ingest-site.yaml`
- `deploy/cronjobs/narrative-ingest-coe.yaml`
- `deploy/cronjobs/thread-reminders.yaml`
- `deploy/cronjobs/training-deliver.yaml`
- `deploy/cronjobs/discipline-stale-check.yaml`
- `deploy/cronjobs/discipline-weekly-review.yaml`
- `deploy/cronjobs/discipline-monthly-retro.yaml`
- `deploy/cronjobs/discipline-calendar-sync.yaml`

- [ ] **Step 2: Commit**

```
Update all deployment manifests: graphql:5000 replaces hasura:8080
```

---

### Task 8: Update docs + CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/implementation-plan.md`
- Modify: `briefings/farmer-briefing-deck.md`

- [ ] **Step 1: Replace all Hasura references with PostGraphile**

Key changes:
- Architecture: "Hasura (GraphQL)" → "PostGraphile (GraphQL)"
- Console: remove Hasura console reference
- URL: `mothertree.aknostic.com/console` → removed (no console)
- Stack: "Hasura | Auto-generated GraphQL API" → "PostGraphile | Postgres-native GraphQL API"

- [ ] **Step 2: Commit**

```
Docs: Hasura → PostGraphile throughout
```

---

### Task 9: Deploy and smoke test

- [ ] **Step 1: Push all changes, wait for CI to build PostGraphile + jobs images**

- [ ] **Step 2: Apply Postgres functions to live database via kubectl exec**

- [ ] **Step 3: Verify Flux applies new deployment (PostGraphile replaces Hasura)**

- [ ] **Step 4: Smoke test**

```bash
# Stats
mothertree stats

# Briefing
mothertree brief "KPN"

# Bot responds in Slack
# (send a DM to Mother Tree)

# Profile
mothertree profile
```

- [ ] **Step 5: Truncate and re-run full ingestion pipeline**

Foundation site → foundation marketing → narrative (all three parallel).
This tests the complete pipeline with PostGraphile.

- [ ] **Step 6: Commit any fixes**

---

### Task 10: Clean up

- [ ] **Step 1: Remove old Hasura files**

Delete `deploy/hasura/deployment.yaml` and `deploy/hasura/service.yaml` (already removed from kustomization in Task 1).

- [ ] **Step 2: Rename HASURA_URL config variable (optional)**

Could rename to `GRAPHQL_URL` for clarity. Low priority — env var name doesn't matter if it works.

- [ ] **Step 3: Final commit**

```
Clean up: remove old Hasura manifests
```
