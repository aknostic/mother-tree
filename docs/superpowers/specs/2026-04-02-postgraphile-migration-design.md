# PostGraphile Migration — Design Spec

## Goal

Replace Hasura with PostGraphile as the GraphQL API layer. Big bang migration — no adapter, no dual support. Clean cut.

## Why

- Hasura's `run_sql` workaround for pgvector is inelegant
- PostGraphile auto-exposes Postgres functions as GraphQL mutations — native support for custom operations
- pgvecto.rs → pgvector migration already done; PostGraphile is the natural next step
- Lighter footprint (Node.js vs Haskell), no metadata store, no console dependency
- Future-proof: Postgres-native approach scales with the schema

## What changes

### 1. Deployment

**Remove:**
- `deploy/hasura/deployment.yaml`
- `deploy/hasura/service.yaml`
- `deploy/hasura/admin-secret.yaml` (repurpose as `graphql-secret.yaml`)

**Add:**
- `deploy/graphql/deployment.yaml` — PostGraphile container
- `deploy/graphql/service.yaml` — ClusterIP on port 5000
- `deploy/graphql/Dockerfile` — Node.js with postgraphile + plugins
- Update `deploy/kustomization.yaml`

**PostGraphile container:**
- Image: custom Dockerfile based on `node:22-slim`
- Packages: `postgraphile`, `@graphile/pg-aggregates`, `postgraphile-plugin-connection-filter`
- Connects to Postgres via `mother-tree-db-app` secret (same as Hasura)
- Auth: Express middleware checks `x-hasura-admin-secret` header (same header name — zero changes in Python config)
- Port: 5000 (internal)
- Endpoint: `/graphql`
- No GraphiQL in production
- Smart comments on schema for fine-tuning (e.g., `@omit` on internal columns)

**Config change:**
- `HASURA_URL` env var → still works, just points to `http://graphql:5000/graphql` instead of `http://hasura:8080/v1/graphql`
- All CronJob and bot deployments update the env var

### 2. Postgres functions

Three JSONB append functions (replace Hasura's `_append` operator):

```sql
CREATE FUNCTION append_channel_message(p_channel_id TEXT, p_message JSONB)
RETURNS channel_memory AS $$
  UPDATE channel_memory
  SET messages = messages || jsonb_build_array(p_message)
  WHERE channel_id = p_channel_id
  RETURNING *;
$$ LANGUAGE sql VOLATILE;

CREATE FUNCTION append_thread_message(p_thread_ts TEXT, p_channel_id TEXT, p_message JSONB)
RETURNS thread_memory AS $$
  UPDATE thread_memory
  SET messages = messages || jsonb_build_array(p_message)
  WHERE thread_ts = p_thread_ts
  RETURNING *;
$$ LANGUAGE sql VOLATILE;

CREATE FUNCTION append_conversation_message(p_conversation_id UUID, p_message JSONB)
RETURNS conversations AS $$
  UPDATE conversations
  SET messages = messages || jsonb_build_array(p_message)
  WHERE id = p_conversation_id
  RETURNING *;
$$ LANGUAGE sql VOLATILE;
```

PostGraphile auto-exposes these as `appendChannelMessage`, `appendThreadMessage`, `appendConversationMessage` mutations.

One upsert function for ingestion log:

```sql
CREATE FUNCTION upsert_ingestion_log(p_source TEXT, p_hash TEXT, p_counts JSONB)
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

### 3. Python query translation

All 89 `graphql()` calls rewritten to PostGraphile syntax. Key patterns:

**Inserts:**
```
# Hasura
insert_change_one(object: $obj) { id }

# PostGraphile
createChange(input: {change: $obj}) { change { id } }
```

**Updates by PK:**
```
# Hasura
update_change_by_pk(pk_columns: {id: $id}, _set: $updates) { id }

# PostGraphile
updateChangeById(input: {id: $id, changePatch: $updates}) { change { id } }
```

**Deletes by PK:**
```
# Hasura
delete_change_by_pk(id: $id) { id }

# PostGraphile
deleteChangeById(input: {id: $id}) { change { id } }
```

**Bulk deletes:**
```
# Hasura
delete_change(where: {source: {_eq: $s}}) { affected_rows }

# PostGraphile (via deleteChange custom function or condition-based)
-- Use a Postgres function: delete_by_source(table, source) RETURNS int
```

**Selects with filters:**
```
# Hasura
change(where: {source: {_eq: $s}}, limit: 10, order_by: {confidence: desc_nulls_last})

# PostGraphile with connection-filter plugin
allChanges(filter: {source: {equalTo: $s}}, first: 10, orderBy: CONFIDENCE_DESC_NULLS_LAST)
```

**Aggregates:**
```
# Hasura
change_aggregate { aggregate { count } }

# PostGraphile with pg-aggregates plugin
allChanges { totalCount }
-- or: allChanges { aggregates { count } }
```

**JSONB append:**
```
# Hasura
update_channel_memory_by_pk(pk_columns: {...}, _append: {messages: $msg})

# PostGraphile (via Postgres function)
appendChannelMessage(input: {pChannelId: $id, pMessage: $msg}) { channelMemory { id } }
```

**Nested relationships:**
```
# Hasura
conversations { exercise { content } }

# PostGraphile
allConversations { nodes { exerciseByExerciseId { content } } }
-- or with smart comments: allConversations { nodes { exercise { content } } }
```

### 4. run_sql replacement

The `run_sql()` function currently uses Hasura's `/v2/query` endpoint. Replace with direct Postgres connection via `psycopg2` or keep using httpx to hit a PostGraphile-exposed SQL function.

Recommended: expose `search_similar` and `store_embedding` as Postgres functions, auto-exposed by PostGraphile. Then `run_sql()` becomes unnecessary.

```sql
CREATE FUNCTION search_similar_insights(query_embedding vector(3584), max_results INT, min_threshold FLOAT)
RETURNS TABLE(id UUID, category TEXT, reframe TEXT, evidence TEXT, trigger TEXT, confidence REAL, similarity FLOAT) AS $$
  SELECT id, category, reframe, evidence, trigger, confidence,
         1 - (embedding <-> query_embedding) as similarity
  FROM insights
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <-> query_embedding) > min_threshold
  ORDER BY embedding <-> query_embedding
  LIMIT max_results;
$$ LANGUAGE sql STABLE;
```

Repeat for each searchable table. PostGraphile exposes these as GraphQL queries automatically.

### 5. Files to change

| File | Changes | Calls |
|---|---|---|
| `jobs/mothertree/hasura.py` | Rewrite all queries, remove `run_sql`, rename to `graphql_client.py` or keep name | 48 |
| `jobs/mothertree/config.py` | Update default URL | 1 |
| `jobs/mothertree/ask.py` | Update import if renamed, query syntax | 4 |
| `jobs/ingestion/ingest.py` | Query syntax | 4 |
| `jobs/mothertree/entities.py` | Query syntax | 6 |
| `jobs/discipline/calendar_sync.py` | Query syntax | 3 |
| `jobs/discipline/weekly_review.py` | Query syntax | 2 |
| `jobs/discipline/stale_check.py` | Query syntax | 2 |
| `jobs/discipline/monthly_retro.py` | Query syntax | 2 |
| `jobs/cli.py` | Query syntax | 4 |
| `jobs/mothertree/dump.py` | Query syntax | 3 |
| `jobs/training/engine.py` | Query syntax (fetch_foundation_for_chapter) | 1 |
| `jobs/reminders/thread_reminders.py` | Query syntax | 1 |
| `jobs/ingestion/profile.py` | Query syntax | 1 |
| `jobs/bot/detect.py` | Query syntax | 1 |
| `jobs/bot/extraction.py` | Query syntax | 1 |
| `jobs/bot/characters/weaver.py` | Query syntax | 1 |
| `deploy/` | New graphql manifests, remove hasura, update kustomization + all CronJobs | ~15 files |

### 6. Testing strategy

1. All 358 existing tests must pass (they mock `graphql()` — mocks need updating for new query syntax)
2. Manual smoke test: `mothertree stats`, `mothertree brief "KPN"`, bot responds in Slack
3. Run one foundation + narrative ingestion to verify full pipeline

### 7. Rollback

If PostGraphile fails: revert the deploy/ changes, Flux restores Hasura. Data is in Postgres, untouched by the migration.

## Not in scope

- Row-level security (all admin access, same as Hasura)
- Subscriptions (not used)
- Schema migrations tooling (schema.sql is manually applied)
