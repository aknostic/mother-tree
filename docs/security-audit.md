# Security Audit — 2026-04-14

## Fixed (Critical)

### GraphQL Injection — f-string interpolation in queries

**Status:** Fixed in commit `security: parameterize all GraphQL queries`

Six files had GraphQL queries that interpolated values via f-strings instead of using parameterized variables. Two of these (`pipeline.py` signal correction handler) accepted user-controlled input (`old_name` from Slack messages), making them exploitable.

**Files fixed:**
- `jobs/mothertree/graphql_client.py` — `delete_all_organization()` loop
- `jobs/bot/pipeline.py` — `_handle_signal_correction()` contact/company name search
- `jobs/ingestion/ingest.py` — `consolidate_foundation()` batch deletion, `truncate_table()` loop
- `jobs/ingestion/profile.py` — `consolidate_organization_profile()` element deletion
- `jobs/mothertree/dump.py` — `restore()` truncation loop
- `jobs/cli.py` — `embed` command detail fetch

**Rule:** All GraphQL queries MUST use `$variable` syntax. Never interpolate with f-strings, even for internal IDs. This is enforced in CLAUDE.md.

### SOPS Age Public Key in Documentation

**Status:** Not a vulnerability — false positive.

The age *public* key (`age1ny5rpz82l...`) was flagged as a secret exposure. It's not — public keys are safe to share by design. They encrypt; they can't decrypt. The *private* key lives in the `sops-age` secret in `flux-system` on the cluster and has never been in git. The public key is intentionally shared with tenants for encrypting their secrets.

## Open (High)

### Containers run as root

All three Dockerfiles (`Dockerfile.bot`, `Dockerfile.jobs`, `deploy/graphql/Dockerfile`) lack a `USER` directive. Containers run as root.

**Fix:** Add to each Dockerfile:
```dockerfile
RUN adduser --disabled-password --gecos '' app
USER app
```

Verify no filesystem writes require root. PostGraphile (graphql) may need adjustment for the node_modules path.

### No Kubernetes NetworkPolicies

No NetworkPolicy objects in `deploy/`. All pods can communicate freely within the namespace.

**Fix:** Add `deploy/network-policies.yaml`:
- Default deny all ingress/egress
- Allow graphql ← slack-bot, jobs (port 5000)
- Allow slack-bot, jobs → graphql (port 5000)
- Allow slack-bot → Slack API (external)
- Allow jobs → Scaleway AI API, GitLab (external)
- Allow all → PostgreSQL (port 5432)

### No email validation on admin commands

Admin commands (`make admin`, `enroll <email> as <role>`) accept any string as email.

**Fix:** Add email format validation in `_handle_admin_command()` before calling `add_admin()` or `create_user()`.

### GraphQL errors leak internal details

`graphql_client.py` raises `RuntimeError(f"GraphQL error: {data['errors']}")` which propagates detailed schema/query errors.

**Fix:** Log the full error, raise a generic message.

## Open (Medium)

### No file size limit on Slack downloads

`bot.py` downloads up to 3 files from Slack but doesn't check `Content-Length`. Large files could OOM the pod.

**Fix:** Check `Content-Length` header, skip files > 10MB.

### Calendar URL not validated

`update_user_profile(calendar_url=...)` accepts any string. Could store malicious URLs.

**Fix:** Validate URL scheme (https only) and basic format before storing.

### No multi-stage Docker builds

Production images include pip, build tools, and cache. Larger attack surface.

**Fix:** Use multi-stage builds — compile dependencies in builder stage, copy only runtime files to slim final stage.

### No rate limiting on GraphQL endpoint

PostGraphile accepts unlimited requests. Vulnerable to DoS.

**Fix:** Add express-rate-limit middleware to `deploy/graphql/server.js` or configure at ingress level.

## Open (Low)

- Admin email stored as secret (could be plain ConfigMap)
- Verbose GraphQL error logging
- No SSL certificate pinning for external APIs

## Resolved — No Action Needed

**SOPS age key:** Only the public key was in git history. Public keys are safe to share — they encrypt, they can't decrypt. The private key is in the cluster (`sops-age` secret in `flux-system`), never in git. No rotation needed.
