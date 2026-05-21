# Mother Tree System Design — Full Production Architecture

## Components

### Always-on services

| Service | What it does | Image |
|---------|-------------|-------|
| **PostgreSQL** | Central intelligence store | CNPG managed (already deployed) |
| **Hasura** | GraphQL API over PostgreSQL | `hasura/graphql-engine:v2.44.0` (already deployed) |
| **Slack bot** | Signal capture, enrichment, thread conversations, training delivery, enrollment | `registry.aknostic.com/mother-tree/slack-bot:latest` |

### Scheduled jobs (CronJobs)

| Job | Schedule | What it does | Image |
|-----|----------|-------------|-------|
| **foundation-ingest-marketing** | Weekly Sun 02:00 | Foundation lens on marketing repo | `registry.aknostic.com/mother-tree/jobs:latest` |
| **foundation-ingest-site** | Weekly Sun 02:30 | Foundation lens on aknostic.com sitemap | same |
| **narrative-ingest-coe** | Daily 02:00 | Narrative lens on clouds-of-europe.eu | same |
| **narrative-ingest-site** | Daily 03:00 | Narrative lens on aknostic.com blog/cases | same |
| **narrative-ingest-marketing** | Daily 04:00 | Narrative lens on marketing repo | same |
| **thread-reminders** | Daily 09:00 weekdays | Re-enter signal threads where remind_after has passed | same |
| **training-refresher** | Daily 08:00 weekdays | Send daily training exercises to enrolled users | same |
| **stale-relationships** | Daily 10:00 weekdays | Check for cold contacts, notify hunters | same |

### Future CronJobs (not in v1 deployment)

| Job | Schedule | What it does |
|-----|----------|-------------|
| calendar-sync | Hourly | Sync Google Calendar, prep/debrief prompts |
| weekly-review | Mondays 09:00 | Pipeline review summary to hunters |
| monthly-retro | First Monday 09:00 | Monthly pipeline health + training progress |
| signal-scanner | Weekdays 07:00 | Scan external sources (RSS, job boards) |

## Container images

Two images, built from the same repo:

### `mother-tree/slack-bot`

```
FROM python:3.12-slim
COPY jobs/slack-bot/ /app/
RUN pip install -r /app/requirements.txt
ENTRYPOINT ["python", "/app/bot.py"]
```

### `mother-tree/jobs`

A single image for all CronJobs. The entrypoint determines what runs:

```
FROM python:3.12-slim
COPY jobs/content-ingestion/ /app/ingestion/
COPY jobs/training-generator/ /app/training/
COPY jobs/reminders/ /app/reminders/
RUN pip install -r /app/ingestion/requirements.txt
# Entrypoint set per CronJob via args
```

Usage:
```yaml
# Foundation ingest
args: ["python", "/app/ingestion/ingest.py", "foundation", "repo", "/data/marketing"]

# Narrative ingest from sitemap
args: ["python", "/app/ingestion/ingest.py", "narrative", "sitemap", "https://clouds-of-europe.eu/sitemap.xml"]

# Thread reminders
args: ["python", "/app/reminders/thread_reminders.py"]

# Training refresher
args: ["python", "/app/training/refresher.py"]
```

## CI/CD — GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - build
  - deploy

build-slack-bot:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker build -t registry.aknostic.com/mother-tree/slack-bot:$CI_COMMIT_SHORT_SHA -f jobs/slack-bot/Dockerfile jobs/slack-bot/
    - docker push registry.aknostic.com/mother-tree/slack-bot:$CI_COMMIT_SHORT_SHA
    - docker tag registry.aknostic.com/mother-tree/slack-bot:$CI_COMMIT_SHORT_SHA registry.aknostic.com/mother-tree/slack-bot:latest
    - docker push registry.aknostic.com/mother-tree/slack-bot:latest
  only:
    changes:
      - jobs/slack-bot/**

build-jobs:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker build -t registry.aknostic.com/mother-tree/jobs:$CI_COMMIT_SHORT_SHA -f jobs/Dockerfile jobs/
    - docker push registry.aknostic.com/mother-tree/jobs:$CI_COMMIT_SHORT_SHA
    - docker tag registry.aknostic.com/mother-tree/jobs:$CI_COMMIT_SHORT_SHA registry.aknostic.com/mother-tree/jobs:latest
    - docker push registry.aknostic.com/mother-tree/jobs:latest
  only:
    changes:
      - jobs/content-ingestion/**
      - jobs/training-generator/**
      - jobs/reminders/**
      - jobs/Dockerfile

# Deploy happens via Flux — merge to main triggers reconciliation
```

## Kubernetes resources

### Namespace (managed by groupware)

```
mother-tree namespace
├── Labels: gateway-access: "true"
├── HTTPRoute: mothertree.aknostic.com → hasura:8080
└── TLS: managed by groupware
```

### Secrets (SOPS encrypted in deploy/)

| Secret | Keys | Used by |
|--------|------|---------|
| `mother-tree-backup-s3` | ACCESS_KEY_ID, SECRET_ACCESS_KEY | CNPG backup |
| `hasura-admin-secret` | admin-secret | Hasura, slack-bot, jobs |
| `scaleway-ai` | api-key, secret-key | slack-bot, jobs |
| `slack-credentials` | bot-token, app-token | slack-bot |
| `gitlab-deploy-token` | token | jobs (clone marketing repo) |

### Deployments

**Slack bot:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: slack-bot
spec:
  replicas: 1
  selector:
    matchLabels: {app: slack-bot}
  template:
    spec:
      containers:
        - name: slack-bot
          image: registry.aknostic.com/mother-tree/slack-bot:latest
          env:
            - name: SLACK_BOT_TOKEN
              valueFrom: {secretKeyRef: {name: slack-credentials, key: bot-token}}
            - name: SLACK_APP_TOKEN
              valueFrom: {secretKeyRef: {name: slack-credentials, key: app-token}}
            - name: SLACK_SIGNALS_CHANNEL
              value: "signals"
            - name: HASURA_URL
              value: "http://hasura:8080/v1/graphql"
            - name: HASURA_ADMIN_SECRET
              valueFrom: {secretKeyRef: {name: hasura-admin-secret, key: admin-secret}}
            - name: SCALEWAY_AI_API_KEY
              valueFrom: {secretKeyRef: {name: scaleway-ai, key: secret-key}}
          resources:
            requests: {cpu: 50m, memory: 128Mi}
            limits: {cpu: 500m, memory: 256Mi}
```

### CronJobs

**Foundation ingest — marketing repo:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: foundation-ingest-marketing
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          initContainers:
            - name: clone-repo
              image: alpine/git
              command: ["git", "clone", "--depth", "1", "https://deploy-token:$(TOKEN)@gitlab.aknostic.com/aknostic/marketing.git", "/data/marketing"]
              env:
                - name: TOKEN
                  valueFrom: {secretKeyRef: {name: gitlab-deploy-token, key: token}}
              volumeMounts:
                - name: repo
                  mountPath: /data
          containers:
            - name: ingest
              image: registry.aknostic.com/mother-tree/jobs:latest
              args: ["python", "/app/ingestion/ingest.py", "foundation", "repo", "/data/marketing"]
              env:
                - name: HASURA_URL
                  value: "http://hasura:8080/v1/graphql"
                - name: HASURA_ADMIN_SECRET
                  valueFrom: {secretKeyRef: {name: hasura-admin-secret, key: admin-secret}}
                - name: SCALEWAY_AI_API_KEY
                  valueFrom: {secretKeyRef: {name: scaleway-ai, key: secret-key}}
              volumeMounts:
                - name: repo
                  mountPath: /data
          volumes:
            - name: repo
              emptyDir: {}
          restartPolicy: Never
```

**Narrative ingest — CoE sitemap:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: narrative-ingest-coe
spec:
  schedule: "0 */6 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: ingest
              image: registry.aknostic.com/mother-tree/jobs:latest
              args: ["python", "/app/ingestion/ingest.py", "narrative", "sitemap", "https://clouds-of-europe.eu/sitemap.xml"]
              env: [same as above]
          restartPolicy: Never
```

**Thread reminders:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: thread-reminders
spec:
  schedule: "0 9 * * 1-5"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: reminders
              image: registry.aknostic.com/mother-tree/jobs:latest
              args: ["python", "/app/reminders/thread_reminders.py"]
              env:
                - [hasura + scaleway + slack credentials]
          restartPolicy: Never
```

**Training refresher:**
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-refresher
spec:
  schedule: "0 8 * * 1-5"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: training
              image: registry.aknostic.com/mother-tree/jobs:latest
              args: ["python", "/app/training/refresher.py"]
              env:
                - [hasura + scaleway + slack credentials]
          restartPolicy: Never
```

## Data flow

```
                    EXTERNAL SOURCES
    ┌────────────────────┬───────────────────┬──────────────────┐
    │  Marketing repo    │  aknostic.com     │  clouds-of-europe│
    │  (git clone)       │  (sitemap)        │  (sitemap)       │
    └────────┬───────────┴────────┬──────────┴────────┬─────────┘
             │                    │                   │
    ┌────────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐
    │ CronJobs        │  │ CronJobs       │  │ CronJob        │
    │ foundation +    │  │ foundation +   │  │ narrative      │
    │ narrative       │  │ narrative      │  │                │
    └────────┬────────┘  └───────┬────────┘  └───────┬────────┘
             │                   │                   │
             └───────────┬───────┴───────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  PostgreSQL         │
              │  (central           │
              │   intelligence)     │      ◄──── Slack bot writes
              │                     │            signals, contacts,
              │  change             │            conversations
              │  worldview          │
              │  personas           │
              │  competitors        │
              │  insights           │
              │  contacts           │
              │  signals            │
              │  signal_threads     │
              │  enrollment         │
              │  exercises          │
              │  responses          │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Hasura (GraphQL)   │
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────▼─────┐  ┌────▼─────┐  ┌────▼──────┐
    │ Slack bot │  │ CronJobs │  │ Future:   │
    │           │  │ (read    │  │ Claude    │
    │ signals   │  │  data,   │  │ Code      │
    │ training  │  │  send    │  │ skill     │
    │ enrichment│  │  via     │  │           │
    │ threads   │  │  Slack)  │  │           │
    └───────────┘  └──────────┘  └───────────┘
```

## Deploy directory structure

```
deploy/
├── kustomization.yaml
├── base/
│   └── scaleway-ai-secret.yaml          (SOPS encrypted)
├── database/
│   ├── cluster.yaml                      (CNPG PostgreSQL)
│   ├── backup-secret.yaml                (SOPS encrypted)
│   └── schema.sql                        (reference, applied manually)
├── hasura/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── admin-secret.yaml                 (SOPS encrypted)
├── slack-bot/
│   ├── deployment.yaml
│   └── slack-credentials-secret.yaml     (SOPS encrypted)
├── cronjobs/
│   ├── foundation-ingest-marketing.yaml
│   ├── foundation-ingest-site.yaml
│   ├── narrative-ingest-coe.yaml
│   ├── narrative-ingest-site.yaml
│   ├── narrative-ingest-marketing.yaml
│   ├── thread-reminders.yaml
│   ├── training-refresher.yaml
│   └── stale-relationships.yaml
├── secrets/
│   └── gitlab-deploy-token.yaml          (SOPS encrypted)
└── images/
    └── (image tags updated by CI or Flux image automation)
```

## Deployment sequence

1. Create Slack credentials secret (SOPS encrypt bot-token + app-token)
2. Create GitLab deploy token for marketing repo (SOPS encrypt)
3. Build and push container images (GitLab CI or manual first time)
4. Update kustomization.yaml to include all new resources
5. Push to main → Flux reconciles
6. Verify: slack-bot pod running, CronJobs created
7. Truncate central intelligence
8. Trigger first ingestion run manually (or wait for schedule)
9. Test: post signal in Slack, verify enrichment and thread conversation

## What's NOT deployed in v1

- Calendar sync (needs Google Calendar OAuth setup)
- Weekly/monthly reviews (need more data in the system first)
- Signal scanner (external RSS/job boards — needs source configuration)
- Training refresher (Phase B of training engine — bot delivers, CronJob triggers)
- Claude Code skill (Phase 7 of implementation plan)

These are added incrementally as CronJobs — each is an independent container with a schedule. No architectural changes needed.
