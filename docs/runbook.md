# Operations Runbook

All commands assume `KUBECONFIG=kubeconfig-mother-tree.yaml` is set or exported.

## Common tasks

### Enroll a user (CLI)

```bash
kubectl run enroll --rm -i --restart=Never -n mother-tree \
  --image=<jobs-image> -- ingest train enroll user@example.com "Name" hunter
```

Or via admin DM: `enroll user@example.com as hunter`

### Grant/revoke admin

DM Mother Tree: `make admin user@example.com` / `remove admin user@example.com`

CLI: `mothertree admin add user@example.com` / `mothertree admin remove user@example.com`

### Run foundation ingest manually

```bash
kubectl create job foundation-site-manual --from=cronjob/foundation-ingest-site -n mother-tree
kubectl create job foundation-marketing-manual --from=cronjob/foundation-ingest-marketing -n mother-tree
```

Watch progress: `kubectl logs -f -l job-name=foundation-site-manual -n mother-tree`

### Run narrative ingest manually

```bash
kubectl create job narrative-site-manual --from=cronjob/narrative-ingest-site -n mother-tree
kubectl create job narrative-marketing-manual --from=cronjob/narrative-ingest-marketing -n mother-tree
kubectl create job narrative-coe-manual --from=cronjob/narrative-ingest-coe -n mother-tree
```

### Run consolidation manually

```bash
kubectl create job consolidate-manual --from=cronjob/foundation-ingest-site -n mother-tree
# Override args to just run consolidate:
kubectl run consolidate --rm -i --restart=Never -n mother-tree \
  --image=<jobs-image> \
  --overrides='{"spec":{"containers":[{"name":"consolidate","image":"<jobs-image>","args":["ingest","consolidate"],"env":[...]}]}}'
```

### Truncate a CI table

```bash
kubectl exec -n mother-tree mother-tree-db-1 -c postgres -- \
  psql -U postgres -d mothertree -c "TRUNCATE <table> CASCADE;"
```

Tables: `change`, `worldview`, `personas`, `competitors`, `insights`, `proof_points`, `signals`, `organization`, `contacts`, `companies`, `interactions`, `opportunities`.

After truncating, re-run the relevant ingest jobs.

### Clean up completed jobs

```bash
kubectl delete jobs --field-selector status.successful=1 -n mother-tree
```

CronJobs auto-clean (keep last 1 successful + 1 failed).

## Restart services

### Restart bot (picks up new image or clears error state)

```bash
kubectl rollout restart deployment slack-bot -n mother-tree
kubectl rollout status deployment slack-bot -n mother-tree
```

### Restart PostGraphile (after schema changes)

```bash
kubectl rollout restart deployment graphql -n mother-tree
kubectl rollout status deployment graphql -n mother-tree
```

### Apply schema changes

```bash
kubectl exec -i -n mother-tree mother-tree-db-1 -c postgres -- \
  psql -U postgres -d mothertree < deploy/database/schema.sql
```

Then restart PostGraphile. Remember to grant permissions on new tables:

```bash
kubectl exec -n mother-tree mother-tree-db-1 -c postgres -- \
  psql -U postgres -d mothertree -c "GRANT ALL ON TABLE <new_table> TO mothertree;"
```

## Secrets management

Secrets are SOPS-encrypted in `deploy/`. The age private key is in 1Password (groupware vault), NOT in the repo.

### Encrypt a new secret

```bash
sops encrypt --age <public-key> --encrypted-regex '^(data|stringData)$' --in-place deploy/secrets/new-secret.yaml
```

### Update an existing secret (if you can't decrypt)

Write plaintext, encrypt, commit. The old ciphertext is replaced.

### Rotate SOPS key

1. Generate new age keypair: `age-keygen -o key.txt`
2. Update `.sops.yaml` with new recipient public key
3. Re-encrypt all secrets with new key
4. Distribute new private key via 1Password
5. Update cluster-side key (coordinate with groupware)

## Monitoring

### Bot logs

```bash
kubectl logs deployment/slack-bot -n mother-tree --tail=50
kubectl logs deployment/slack-bot -n mother-tree -f  # stream
```

### GraphQL logs

```bash
kubectl logs deployment/graphql -n mother-tree --tail=50
```

### Check CI table health

```bash
kubectl exec -n mother-tree mother-tree-db-1 -c postgres -- psql -U postgres -d mothertree -c "
SELECT 'change' as t, count(*) FROM change
UNION ALL SELECT 'worldview', count(*) FROM worldview
UNION ALL SELECT 'personas', count(*) FROM personas
UNION ALL SELECT 'competitors', count(*) FROM competitors
UNION ALL SELECT 'insights', count(*) FROM insights
UNION ALL SELECT 'proof_points', count(*) FROM proof_points
UNION ALL SELECT 'organization', count(*) FROM organization
UNION ALL SELECT 'signals', count(*) FROM signals
UNION ALL SELECT 'contacts', count(*) FROM contacts
UNION ALL SELECT 'users', count(*) FROM users
ORDER BY t;"
```

## Troubleshooting

### Bot shows "thinking" but never responds

Check logs for errors. Common causes:
- PostGraphile doesn't know about new tables → restart graphql deployment
- Missing table permissions → `GRANT ALL ON TABLE <table> TO mothertree;`
- Scaleway AI timeout → check API status, retry

### Ingestion skips all files as "unchanged"

The `ingestion_log` table tracks content hashes. If you changed extraction prompts but not content:
- Use `--force` flag to re-extract
- Or truncate the ingestion_log: `TRUNCATE ingestion_log;`

### Training chapter is a wall of text

Training engine prompt needs Slack formatting instructions. Fixed in engine.py — redeploy.

### Flux not deploying new image

1. Check image policy: `kubectl get imagepolicy -n mother-tree -o jsonpath='{.items[*].status.latestRef.tag}'`
2. If tag is updated but deployment isn't: ask groupware to reconcile the kustomization
3. Verify kustomization builds: check for missing file references in `deploy/kustomization.yaml`
