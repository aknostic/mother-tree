# Mother Tree — local development with Docker Compose

The compose stack runs three services: a PostgreSQL database (with pgvector), a PostGraphile GraphQL API, and the Slack bot. You can bring up the DB and GraphQL services alone for content ingestion without needing Slack credentials.

---

## Bringing the stack up

```bash
cp .env.example .env   # then edit .env with your Scaleway API key etc.
docker compose up -d
```

On first start, Postgres initialises the schema from `deploy/database/schema.sql` automatically. Subsequent starts use the persisted volume and skip schema init.

---

## What each service does

**`db`** runs `pgvector/pgvector:pg17` — a standard Postgres 17 image with the pgvector extension pre-installed. The Mother Tree schema (all CI tables, vector columns, indexes) is loaded from `deploy/database/schema.sql` on first boot. Data persists in the `mother-tree-pgdata` named volume. Port `5432` is exposed to the host so the CLI and any Postgres client can connect directly.

> **Dev-only credentials:** the database uses `mothertree`/`mothertree` as username/password. These are hardcoded in the compose file for local convenience. Never use these credentials in a production or shared environment.

**`graphql`** builds and runs the PostGraphile server from `deploy/graphql/`. It connects to `db`, introspects the public schema, and serves a typed GraphQL API at `http://localhost:5000/graphql`. The `ADMIN_SECRET` variable is optional; if left empty the endpoint is open to anyone reaching it — fine for local development on `localhost`. The service waits for `db` to be healthy before starting.

**`bot`** builds and runs the Slack bot from `jobs/Dockerfile.bot`. It connects to `graphql` for all CI data and to the Scaleway and Anthropic APIs for LLM calls. The bot requires valid Slack credentials (`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`) to connect to a workspace. It waits for `graphql` to be healthy before starting, and will restart up to three times if it exits — useful for transient startup failures, but it will remain stopped if Slack credentials are missing or invalid.

---

## Where to put Slack tokens

Add your tokens to `.env`:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Without these, the bot service will start, fail to connect to Slack, and stop after three restart attempts. The `db` and `graphql` services are unaffected and remain running. You can ingest content and run CLI commands without the bot being online.

---

## Smoke test

Once the stack is up, verify the GraphQL API is reachable:

```bash
curl -X POST http://localhost:5000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { queryType { name } } }"}'
```

Expected: a JSON response containing `"name":"Query"`.

---

## Ingesting a first sitemap from the host

The host CLI connects to GraphQL on `localhost:5000`. Make sure `uv` is installed, then:

```bash
HASURA_URL=http://localhost:5000/graphql \
  SCALEWAY_AI_API_KEY=$(grep ^SCALEWAY_AI_API_KEY .env | cut -d= -f2) \
  uv run python -m cli ingest foundation url https://your-marketing-site.example/sitemap.xml
```

Replace the sitemap URL with your own. Foundation extraction builds the change, worldview, persona, and competitor tables. Run narrative extraction afterwards to populate insights:

```bash
HASURA_URL=http://localhost:5000/graphql \
  SCALEWAY_AI_API_KEY=$(grep ^SCALEWAY_AI_API_KEY .env | cut -d= -f2) \
  uv run python -m cli ingest narrative url https://your-marketing-site.example/sitemap.xml
```

---

## Where logs land

```bash
docker compose logs -f          # all services
docker compose logs -f bot      # bot only
docker compose logs -f graphql  # GraphQL only
```

---

## Tearing down

```bash
docker compose down        # stop services, keep the DB volume
docker compose down -v     # stop services and destroy the DB volume (all data lost)
```
