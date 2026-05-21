# OSS Release Plan — Saga + Lena Rename and Generic-ification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the GitLab `mother-tree` repo (Aknostic's living instance) and produce a generic, content-agnostic, OSS-licensed `mother-tree` on GitHub — the canonical "clone-and-deploy" upstream. The GitLab repo continues as Aknostic's production deployment; the two relate in spirit, not via git history.

**Architecture:** A clone of the current repo with three classes of change applied: (1) identity rename — Seth Godin → Saga, Lawrence Miller → Lena, with inspirations credited in a single document; (2) content scrub — Aknostic-specific content, customer references, test-data dumps, and the academic paper are removed from the OSS repo (production keeps its own copy); (3) OSS scaffolding — Apache 2.0 LICENSE, OSS-facing README, CONTRIBUTING, a docker-compose dev path, and GitHub Actions CI in place of GitLab CI.

**Tech Stack:** Python 3.13, Slack Bolt, PostgreSQL 17 + pgvector, PostGraphile, Scaleway Generative APIs, pytest. No new tech — the plan is mechanical change.

**Spec:** This document. No separate spec exists; the requirements were captured in conversation on 2026-05-21.

---

## Repo Relationship Model

Two repositories, sharing methodology not git history:

| Aspect | GitHub `mother-tree` (OSS upstream) | GitLab `aknostic/mother-tree` (instance) |
|---|---|---|
| Audience | Anyone | Aknostic only |
| Personas | Saga + Lena, archetypal | Saga + Lena (same code), Aknostic-tuned voice in production overrides |
| Customer content | None — content layer is bring-your-own | Aknostic sitemaps, real test-data dumps, customer references |
| Academic paper | None | Lives in the marketing repo (moved out of this one) |
| CI | GitHub Actions | GitLab CI + Kaniko + Flux (unchanged) |
| License | Apache 2.0 | Internal — Apache 2.0 inherited |
| Sync direction | Manual cherry-pick, both ways | Manual cherry-pick, both ways |

There is no `git remote` link. When a generic fix lands in GitLab, it gets cherry-picked into GitHub by hand (after sanity-checking it has no Aknostic-specific content). When a community PR lands on GitHub, it gets cherry-picked into GitLab.

---

## Preconditions

Before starting:

- The GitLab `mother-tree` is up to date and clean (`git status` empty, all CI green).
- A fresh **GitHub repository** has been created at `github.com/aknostic/mother-tree` (or similar — final name TBD).
- A working copy of the GitLab repo has been cloned, the `origin` remote re-pointed to GitHub, and pushed once so `main` exists on GitHub. The GitLab `main` will continue to be the production branch.
- All work in this plan happens on the GitHub clone. Cherry-picks back to GitLab happen at the end of the plan if any of the changes (e.g. Saga/Lena rename) should also propagate to production.

---

## File Structure

### New files (on the OSS clone)

| File | Responsibility |
|------|---------------|
| `LICENSE` | Apache 2.0 full text |
| `NOTICE` | Third-party attributions (one-liner if minimal) |
| `CONTRIBUTING.md` | How to contribute, run tests, file issues |
| `CODE_OF_CONDUCT.md` | Standard Contributor Covenant v2.1 |
| `docs/inspirations.md` | Credits the thinkers whose work informs Saga and Lena (Godin, Moore, Miller, Rackham, Richardson, Simard, Wintzen, …) |
| `docs/methodology.md` | The Mycorrhizal Method — public-facing methodology overview, derived from `methodology/` |
| `docker-compose.yml` | Local dev stack: Postgres 17 + pgvector, PostGraphile, optional Slack stub |
| `.github/workflows/test.yml` | GitHub Actions: lint + pytest on every PR and push to main |
| `.github/workflows/build-images.yml` | GitHub Actions: build and publish container images to GHCR on tags |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Bug report template |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Feature request template |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR template |
| `jobs/bot/characters/saga.py` | Renamed from `seth.py` |
| `jobs/bot/characters/lena.py` | Renamed from `lawrence.py` |

### Modified files (selected — full list discovered per task)

| File | Changes |
|------|---------|
| `README.md` | Rewritten for OSS audience — what it is, who it's for, quick start via docker-compose, how to bring your own content |
| `CLAUDE.md` | Generic-ified. Aknostic-specific bits move to a separate `CLAUDE.local.md` (gitignored) on the GitLab instance only. |
| `jobs/cli.py` | `ask seth` / `ask lawrence` → `ask saga` / `ask lena`; help text |
| `jobs/mothertree/ask.py` | `PERSONAS["seth"]` / `PERSONAS["lawrence"]` → `"saga"` / `"lena"`; persona system prompts rewritten ("You are Saga…" / "You are Lena…"); consensus path renamed |
| `jobs/mothertree/intelligence.py` | Any `seth`/`lawrence` keys/labels renamed |
| `jobs/bot/characters/dispatcher.py` | Persona trigger words `seth`/`lawrence` → `saga`/`lena`; backward-compat alias map for the GitLab instance (NOT in OSS) |
| `jobs/ingestion/extract.py` | "Seth Godin's marketing lens" → "Saga's positioning lens"; "Lawrence Miller's consultative lens" → "Lena's consultative lens" |
| `jobs/ingestion/ingest.py` | `SETH_CONSOLIDATE` / `LAWRENCE_CONSOLIDATE` → `SAGA_CONSOLIDATE` / `LENA_CONSOLIDATE`; in-prompt references |
| `jobs/training/curriculum.py` | `trainer` field values `"seth"`/`"lawrence"` → `"saga"`/`"lena"` |
| `jobs/bot/pipeline.py` | Trainer routing in `_trainer_character_response`: `if trainer == "lawrence"` → `if trainer == "lena"` etc. |
| `jobs/tests/test_*.py` | All test fixtures and assertions referencing seth/lawrence renamed |
| All in-repo docs (`docs/`, `methodology/`) | s/Seth Godin/Saga/, s/Lawrence Miller/Lena/, with inspirations linked once |

### Removed (from OSS clone only — kept on GitLab)

| Path | Why removed | Keep where |
|---|---|---|
| `test-data/post-foundation-extraction.json` | Real CI signals from Aknostic ingest | GitLab only |
| `test-data/post-foundation-context-aware.json` | Real Aknostic foundation data | GitLab only |
| `test-data/post-narrative-extraction.json` | Real narrative extracts | GitLab only |
| `test-data/post-opus-consolidated.json` | Real consolidated CI data | GitLab only |
| `docs/papers/asisas-2026/` | Academic paper draft (single directory) | Move to marketing repo |
| `latex/` (if present) | Paper LaTeX sources | Move to marketing repo |
| `kubeconfig-mother-tree.yaml` | Already gitignored — verify in `.gitignore` | N/A |
| `mother-tree-methodology-brainstorm.md` | Internal brainstorm with customer names | GitLab only or marketing repo |
| `PROJECT.md` | Aknostic-specific project notes | GitLab only |
| `docs/next-session-prompt.md` | Internal hand-off | GitLab only |
| `docs/superpowers/` | Internal planning archive | GitLab only |
| `assessments/`, `briefings/`, `insights/`, `patterns/` | Per `ls` output, internal note dirs | GitLab only — verify each before deciding |
| `deploy/cronjobs/foundation-ingest-marketing.yaml` etc. | Aknostic-specific CronJobs pointing at aknostic.com/CoE sitemaps | Replace with sample manifests in `deploy/cronjobs.example/` |

The Aknostic-specific *sitemap source URLs* (aknostic.com, cloudsofeurope.eu) **stay** in the example CronJobs as documentation — they are public and help users understand what a real deployment looks like.

---

## Tasks

### Task 1: Add LICENSE and NOTICE

**Files:**
- Create: `LICENSE`
- Create: `NOTICE`

- [ ] **Step 1: Write `LICENSE`** — full Apache 2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt. Update the `[yyyy]` and `[name of copyright owner]` placeholders to `2026 Aknostic B.V.` (or whichever legal entity is correct).

- [ ] **Step 2: Write `NOTICE`** — short notice block:

```
Mother Tree — commercial intelligence platform
Copyright 2026 Aknostic B.V.

This product includes software developed by Aknostic B.V.
(https://aknostic.com).

This product is informed by the published work of Seth Godin,
Lawrence Miller, Geoffrey Moore, Linda Richardson, Neil Rackham,
Suzanne Simard, and Eckart Wintzen. See docs/inspirations.md.
```

- [ ] **Step 3: Commit**

```bash
git add LICENSE NOTICE
git commit -m "license: Apache 2.0 + NOTICE attributions"
```

---

### Task 2: Rename character modules to Saga and Lena

**Files:**
- Move: `jobs/bot/characters/seth.py` → `jobs/bot/characters/saga.py`
- Move: `jobs/bot/characters/lawrence.py` → `jobs/bot/characters/lena.py`

- [ ] **Step 1: Rename files via git mv**

```bash
git mv jobs/bot/characters/seth.py jobs/bot/characters/saga.py
git mv jobs/bot/characters/lawrence.py jobs/bot/characters/lena.py
```

- [ ] **Step 2: In `saga.py`** — replace identity string. Find the system prompt (typically a top-level constant like `SETH_IDENTITY` or `SYSTEM_PROMPT`) and replace:

  - Constant names: `SETH_*` → `SAGA_*`
  - Self-references: `"You are Seth Godin"` / `"As Seth Godin"` → `"You are Saga. You are the network's positioning strategist — you think in story, tribe, and the change worth making."`
  - Method/function names: keep `respond()` etc.; only rename if they include "seth".

- [ ] **Step 3: In `lena.py`** — same treatment:

  - Constant names: `LAWRENCE_*` → `LENA_*`
  - Self-references: `"You are Lawrence Miller"` → `"You are Lena. You are the network's consultative diagnostician — you ask, listen, and help the buyer name their own problem."`

- [ ] **Step 4: Find and fix imports throughout codebase**

```bash
grep -rln "from bot.characters.seth\|from bot.characters.lawrence\|from .characters.seth\|from .characters.lawrence" jobs/ --include="*.py" | grep -v __pycache__
```

For each match, update the import to `saga` / `lena`.

- [ ] **Step 5: Run tests — character module imports must succeed**

```bash
uv run --quiet pytest jobs/tests/test_characters.py -v
```

Expected: PASS (or specific assertions about persona text — fix those in Task 5).

- [ ] **Step 6: Commit**

```bash
git add -u jobs/bot/characters/ jobs/
git commit -m "rename: bot characters seth.py → saga.py, lawrence.py → lena.py"
```

---

### Task 3: Rename persona registry and consensus path

**Files:**
- Modify: `jobs/mothertree/ask.py`
- Modify: `jobs/mothertree/intelligence.py` (if it references persona keys)

- [ ] **Step 1: Open `ask.py`** — replace `PERSONAS` dict keys and content:

```python
PERSONAS = {
    "saga": (
        "You are Saga. You are the positioning strategist for a consultative sales "
        "network. Speak in terms of story, tribe, and the change worth making. "
        "Be direct, concise, useful. Answer based only on the data provided."
    ),
    "lena": (
        "You are Lena. You are the consultative diagnostician for a consultative "
        "sales network. Ask the question the buyer hasn't asked themselves. "
        "Be direct, concise, useful. Answer based only on the data provided."
    ),
}
```

- [ ] **Step 2: Replace consensus path strings**

In `ask.py`, find lines like `seth_response = generate(PERSONAS["seth"] + ...)`. Replace `seth` → `saga`, `lawrence` → `lena` throughout. The co-training preamble becomes `"You are co-training with Lena (consultative diagnosis). Give your perspective — Saga's angle."` and the mirror.

- [ ] **Step 3: Replace headings in any synthesis prompts**

Where you see literal `"1. Marketing framework (Seth Godin's structure):"`, replace with `"1. Positioning framework (Saga's structure):"` — and similarly for Lawrence/consultative.

- [ ] **Step 4: Run ask-related tests**

```bash
uv run --quiet pytest jobs/tests/ -k "ask or consensus or trainer" -v
```

Expected: PASS. Failures here usually mean a test fixture still expects `"seth"` — fix in Task 5.

- [ ] **Step 5: Commit**

```bash
git add jobs/mothertree/ask.py jobs/mothertree/intelligence.py
git commit -m "rename: persona registry seth/lawrence → saga/lena"
```

---

### Task 4: Rename ingestion prompts

**Files:**
- Modify: `jobs/ingestion/extract.py`
- Modify: `jobs/ingestion/ingest.py`

- [ ] **Step 1: In `extract.py`** — find the docstring/prompt strings:

  - `"You are extracting foundational positioning through Seth Godin's marketing lens"` → `"You are extracting foundational positioning through Saga's lens — story, tribe, change."`
  - `"You are extracting sales conversation material through Lawrence Miller's consultative …"` → `"You are extracting sales conversation material through Lena's consultative lens — diagnose before prescribe."`

- [ ] **Step 2: In `ingest.py`** — rename constants and their content:

  - `SETH_CONSOLIDATE` → `SAGA_CONSOLIDATE`. First line "You are Seth Godin reviewing foundation data…" → "You are Saga reviewing foundation data…"
  - `LAWRENCE_CONSOLIDATE` → `LENA_CONSOLIDATE`. First line "You are Lawrence Miller, a consultative selling expert…" → "You are Lena, the consultative diagnostician…"

- [ ] **Step 3: Update all callers in `ingest.py`** — any reference to the old constant names.

- [ ] **Step 4: Run ingestion tests**

```bash
uv run --quiet pytest jobs/tests/ -k "ingest or extract or consolid" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs/ingestion/extract.py jobs/ingestion/ingest.py
git commit -m "rename: ingestion prompts seth/lawrence → saga/lena"
```

---

### Task 5: Rename CLI and bot commands

**Files:**
- Modify: `jobs/cli.py`
- Modify: `jobs/bot/characters/dispatcher.py`
- Modify: `jobs/bot/pipeline.py`
- Modify: `jobs/training/curriculum.py`
- Modify: `jobs/training/generate.py` (contains `cmd_seth()`, `if cmd == "seth":`, and module docstring references)

- [ ] **Step 1: In `cli.py`** — replace user-facing CLI help and command parsing:

  - `mothertree ask seth <question>` → `mothertree ask saga <question>`
  - `mothertree ask lawrence <question>` → `mothertree ask lena <question>`
  - Help comments: `"Ask Seth Godin"` → `"Ask Saga (positioning strategist)"`, `"Ask Lawrence Miller"` → `"Ask Lena (consultative diagnostician)"`
  - Any `if persona == "seth"` / `"lawrence"` branches.

- [ ] **Step 2: In `dispatcher.py`** — Slack persona triggers:

  Find the code that matches `ask seth` / `ask lawrence` / `seth` / `lawrence` patterns (likely in the persona-mention routing around line ~320+). Rename to `saga` / `lena`. The `_DEBRIEF_TRIGGERS` and similar constants don't change.

- [ ] **Step 3: In `pipeline.py`** — trainer character routing:

  Find `_trainer_character_response`. Replace `trainer == "lawrence"` → `trainer == "lena"` and the import paths (`from bot.characters.lawrence` → `from bot.characters.lena`). Replace `trainer == "seth"` → `trainer == "saga"` if explicit; otherwise just rename the default branch's import.

- [ ] **Step 4: In `curriculum.py`** — trainer field values:

  Every `"trainer": "seth"` becomes `"trainer": "saga"`. Every `"trainer": "lawrence"` becomes `"trainer": "lena"`. `"trainer": "mother_tree"` stays.

- [ ] **Step 5: Run full bot + training tests**

```bash
uv run --quiet pytest jobs/tests/test_pulse_dispatcher.py jobs/tests/test_unified.py jobs/tests/test_training.py jobs/tests/test_curriculum.py jobs/tests/test_operations.py -v
```

Expected: PASS, with the caveat that test fixtures referencing seth/lawrence still fail — fix in Task 6.

- [ ] **Step 6: Commit**

```bash
git add jobs/cli.py jobs/bot/characters/dispatcher.py jobs/bot/pipeline.py jobs/training/curriculum.py
git commit -m "rename: CLI and bot commands ask seth/lawrence → saga/lena"
```

---

### Task 6: Update all tests for the rename

**Files:**
- Modify: every file under `jobs/tests/` referencing `seth`, `lawrence`, `Seth`, `Lawrence`.

- [ ] **Step 1: Find all test references**

```bash
grep -rln "seth\|lawrence\|Seth\|Lawrence" jobs/tests/ --include="*.py"
```

- [ ] **Step 2: For each file, edit in-place** — replace identifiers, persona keys, prompt strings, and assertion expectations. Be careful with case: code keys are lowercase (`"saga"`, `"lena"`); prose in test docstrings can use proper-case (`Saga`, `Lena`).

- [ ] **Step 3: Run the full suite**

```bash
uv run --quiet pytest jobs/tests/ 2>&1 | tail -5
```

Expected: All previously-passing tests pass. New count: 636 (or whatever current count is) all green.

- [ ] **Step 4: Commit**

```bash
git add jobs/tests/
git commit -m "test: update fixtures and assertions for saga/lena rename"
```

---

### Task 7: Write `docs/inspirations.md`

**Files:**
- Create: `docs/inspirations.md`

- [ ] **Step 1: Write the file**

```markdown
# Inspirations

Mother Tree's personas are archetypes, not impersonations. Their craft is
informed by the published work of practitioners who shaped how we think about
positioning, consultative selling, and networked intelligence. Saga and Lena
synthesize methodology; they do not speak for the people listed below.

## Saga — the positioning strategist

Saga's craft is informed by:

- **Seth Godin** — *Purple Cow*, *This Is Marketing*, *Tribes*. The
  positioning question "who's it for and what's it for" is Godin's.
- **Geoffrey Moore** — *Crossing the Chasm*. The discipline of choosing one
  beachhead before building a movement.
- **Al Ries & Jack Trout** — *Positioning: The Battle for Your Mind*. The
  craft of owning a category in the buyer's head.

## Lena — the consultative diagnostician

Lena's craft is informed by:

- **Lawrence Miller** — writing on consultative selling and the discipline
  of diagnosing before prescribing.
- **Neil Rackham** — *SPIN Selling*. The structured question hierarchy that
  turns a sales call into a diagnostic conversation.
- **Linda Richardson** — *The Sales Success Handbook*. The discipline of
  earning the right to the next conversation.

## The network — methodology

The Mycorrhizal Method itself draws on:

- **Suzanne Simard** — *Finding the Mother Tree*. The biological model of
  the mycorrhizal network, from which the metaphor and the project name come.
- **Eckart Wintzen** — *Eckart's Notes*. The cell-division model of
  organizational growth that informs how we think about scaling teams.
- **Matthew Dixon & Brent Adamson** — *The Challenger Sale*. The reframe
  posture used by both Saga and Lena when the buyer's stated problem is the
  wrong one.

If you're an author listed here and would prefer a different framing — or
removal — please open an issue. We are happy to adjust.
```

- [ ] **Step 2: Commit**

```bash
git add docs/inspirations.md
git commit -m "docs: credit the practitioners whose work informs Saga and Lena"
```

---

### Task 8: Update in-repo docs and CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` (full rewrite in Task 12 — minor touch here)
- Modify: every `.md` under `methodology/` and `docs/` (excluding `docs/papers/` and `docs/superpowers/`, which are deleted in Tasks 10–11)

- [ ] **Step 1: Find all doc references**

```bash
grep -rln "Seth Godin\|Lawrence Miller\|seth\|lawrence" --include="*.md" . | grep -v docs/papers/ | grep -v docs/superpowers/
```

- [ ] **Step 2: For each file, replace prose references** — `"Seth Godin (marketing strategy)"` → `"Saga (positioning strategist)"`, etc. Link the first mention to `docs/inspirations.md`.

- [ ] **Step 3: In `CLAUDE.md`**, also update the "Personas:" bullet under "Key decisions" and the "Slack bot interaction" section's `ask seth/lawrence/trainer` → `ask saga/lena/trainer`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md methodology/ docs/
git commit -m "docs: rename persona references to Saga and Lena across all in-repo docs"
```

---

### Task 9: Remove the academic paper from the OSS repo

**Files:**
- Remove: `docs/papers/asisas-2026/` (entire directory)
- Remove: `latex/` (if it exists at top level — verify first)

Note: the user is moving this content to a marketing repo separately. This task only removes from OSS; the move happens elsewhere.

- [ ] **Step 1: Verify the paper is preserved elsewhere first**

```bash
# This is a sanity gate. Do NOT proceed until confirmed.
echo "Confirm the paper directory has been copied to the marketing repo, then delete here."
```

- [ ] **Step 2: Remove**

```bash
git rm -r docs/papers/asisas-2026/
[ -d latex ] && git rm -r latex/
```

- [ ] **Step 3: Commit**

```bash
git commit -m "remove: academic paper draft — moved to marketing repo"
```

---

### Task 10: Remove test-data dumps with real customer content

**Files:**
- Remove: `test-data/post-foundation-extraction.json`
- Remove: `test-data/post-foundation-context-aware.json`
- Remove: `test-data/post-narrative-extraction.json`
- Remove: `test-data/post-opus-consolidated.json`

These contain real Aknostic CI signals, persona names, and customer references. The directory itself can stay with a README explaining how to generate dumps.

- [ ] **Step 1: Remove the dumps**

```bash
git rm test-data/*.json
```

- [ ] **Step 2: Create `test-data/README.md`**

```markdown
# test-data

Snapshot dumps of CI tables for testing pipeline stages independently.

Dumps are produced by `mothertree dump <path>` and restored with
`mothertree restore <path>`. They are not committed to this repository —
each deployment generates its own dumps from its own ingested content.

To produce a snapshot:

    uv run python -m cli dump test-data/my-snapshot.json

To restore one:

    uv run python -m cli restore test-data/my-snapshot.json
```

- [ ] **Step 3: Commit**

```bash
git add test-data/README.md
git commit -m "remove: test-data dumps with real customer content; document how to generate fresh snapshots"
```

---

### Task 11: Remove other Aknostic-internal documents

**Files:**
- Remove: `PROJECT.md`
- Remove: `mother-tree-methodology-brainstorm.md`
- Remove: `docs/next-session-prompt.md`
- Remove: `docs/superpowers/` (internal planning archive)
- Verify and possibly remove: `assessments/`, `briefings/`, `insights/`, `patterns/`

> ⚠️ **Self-reference warning**: `docs/superpowers/` contains this very plan
> document. Before running the `git rm` below, copy this plan to a location
> outside the repo (or print it) so you can keep referencing it through the
> remaining tasks. The implementer is about to delete their own roadmap.
> Recommended: save to `/tmp/2026-05-21-oss-release-saga-lena.md` first.

- [ ] **Step 1: Preserve this plan outside the repo**

```bash
cp docs/superpowers/plans/2026-05-21-oss-release-saga-lena.md /tmp/
```

- [ ] **Step 2: For each top-level dir on the maybe-list, inspect contents**

```bash
ls -la assessments/ briefings/ insights/ patterns/ 2>/dev/null
```

If any directory contains generic templates or examples useful to OSS adopters, keep it but strip customer-specific files. If it's purely Aknostic internal notes, remove the whole directory.

- [ ] **Step 3: Remove the agreed deletions**

```bash
git rm PROJECT.md mother-tree-methodology-brainstorm.md docs/next-session-prompt.md
git rm -r docs/superpowers/
# Plus the per-directory decisions from Step 2.
```

- [ ] **Step 4: Commit**

```bash
git commit -m "remove: Aknostic-internal documents (planning, brainstorms, briefings)"
```

---

### Task 12: Generic-ify CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

`CLAUDE.md` currently contains Aknostic-specific operational detail (S3 bucket name, internal hostnames, the SOPS age public key, ADMIN_EMAIL hints, calendar URLs). For the OSS repo, this needs to be a generic project guide; the Aknostic-specific bits move to a private `CLAUDE.local.md` in the GitLab instance.

- [ ] **Step 1: Identify Aknostic-specific lines** — grep for `aknostic`, `mothertree.aknostic.com`, `s3.fr-par.scw.cloud`, `groupware-mother-tree-backups`, the age key, real email addresses.

- [ ] **Step 2: Rewrite CLAUDE.md sections** that hardcode environment to use placeholders:

  - `mothertree.aknostic.com` → `<your-graphql-host>`
  - `s3://groupware-mother-tree-backups/` → `s3://<your-backup-bucket>/`
  - `ADMIN_EMAIL` example value → "set this to the seed admin's email in your Slack workspace"
  - Remove the `sops age public key` line — that's deployment-specific.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: generic-ify CLAUDE.md — remove Aknostic-specific hosts and keys"
```

---

### Task 13: Convert Aknostic deploy manifests to examples

**Files:**
- Move: `deploy/cronjobs/foundation-ingest-marketing.yaml` → `deploy/cronjobs.example/foundation-ingest-marketing.yaml.example`
- Same treatment for every CronJob that hardcodes Aknostic sitemaps.
- Modify: `deploy/kustomization.yaml` to drop the now-removed CronJobs.

- [ ] **Step 1: Identify CronJobs that reference Aknostic sources**

```bash
grep -ln "aknostic.com\|cloudsofeurope" deploy/cronjobs/*.yaml
```

The grep will surface ingestion CronJobs (`foundation-ingest-*.yaml`,
`narrative-ingest-*.yaml`) — those are the ones that hardcode public source
URLs and should become examples. It may also surface discipline / pulse /
training CronJobs that mention `aknostic` in env vars or comments — those
stay in `deploy/cronjobs/` after env-var generic-ification (placeholder
values for hostnames, emails, etc.), because they are part of the engine,
not deployment-specific content sources. Sanity-check the list before moving.

- [ ] **Step 2: Move each to `deploy/cronjobs.example/` and append `.example` to filename**

```bash
mkdir -p deploy/cronjobs.example
git mv deploy/cronjobs/foundation-ingest-marketing.yaml deploy/cronjobs.example/foundation-ingest-marketing.yaml.example
# Repeat for each.
```

- [ ] **Step 3: Update `deploy/kustomization.yaml`** to remove the moved files from the resource list. The example files are documentation, not deployable resources.

- [ ] **Step 4: Add `deploy/cronjobs.example/README.md`**

```markdown
# Example CronJobs

These are sample manifests showing how a real deployment wires ingestion
to public content sources. They reference aknostic.com and cloudsofeurope.eu
as concrete examples; replace with your own marketing site sitemap, content
repository, or document source before deploying.

Copy a file, drop the `.example` suffix, edit the source URL, and add it to
`deploy/cronjobs/kustomization.yaml`.
```

- [ ] **Step 5: Commit**

```bash
git add deploy/cronjobs.example/ deploy/cronjobs/ deploy/kustomization.yaml
git commit -m "deploy: move Aknostic-source CronJobs to deploy/cronjobs.example/ as documentation"
```

---

### Task 14: Rewrite README.md for an OSS audience

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write a new README** covering:

  - **What is Mother Tree** — one-paragraph: a commercial intelligence platform for consultative sales teams. The Mycorrhizal Method as the methodology spine. Bring-your-own-content.
  - **Who is it for** — consultative sales teams (hunters, gatherers, farmers, citizens) who run multi-quarter deals and want an always-on intelligence layer.
  - **Quick start** — `docker compose up`, then `uv run python -m cli ingest foundation url https://your-marketing-site.example/sitemap.xml`.
  - **Architecture** — link to `docs/methodology.md`, link to `docs/inspirations.md`, brief diagram of the two layers (always-on + interactive).
  - **Personas — Saga and Lena** — one-paragraph intro, link to `docs/inspirations.md` for sources.
  - **Production deployment** — link to `deploy/` and a note that the example manifests target Scaleway/CNPG but any K8s + Postgres 17 + pgvector works.
  - **Contributing** — link to `CONTRIBUTING.md`.
  - **License** — Apache 2.0.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for OSS audience"
```

---

### Task 15: Add CONTRIBUTING.md and CODE_OF_CONDUCT.md

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`

- [ ] **Step 1: Write `CONTRIBUTING.md`** covering:

  - Issue templates (link `.github/ISSUE_TEMPLATE/`).
  - PR conventions: small focused PRs, conventional commit prefixes (`fix:`, `feat:`, `docs:`, etc.), tests for every behavior change.
  - Running tests locally: `uv run pytest jobs/tests/`.
  - Style: no test mocks for the database (use the docker-compose stack); parameterized GraphQL queries only (no f-string interpolation); prompts live in `jobs/.../characters/*.py` next to the character module.
  - Persona contributions: new personas land in `jobs/bot/characters/`, add inspirations in `docs/inspirations.md` if drawing on a real practitioner's work.

- [ ] **Step 2: Write `CODE_OF_CONDUCT.md`** — drop in the Contributor Covenant v2.1 from https://www.contributor-covenant.org/version/2/1/code_of_conduct.txt, with the contact line pointing to a real email.

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md CODE_OF_CONDUCT.md
git commit -m "docs: add CONTRIBUTING and CODE_OF_CONDUCT"
```

---

### Task 16: Add docker-compose dev path

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.README.md`
- Modify: `jobs/mothertree/config.py` (if defaults need adjusting for the compose stack)

- [ ] **Step 1: Write `docker-compose.yml`** with three services:

  - `db`: `postgres:17` with `pgvector` extension (use the `pgvector/pgvector:pg17` image). Bind `5432`. Initialise with `deploy/database/schema.sql` mounted at `/docker-entrypoint-initdb.d/schema.sql`.
  - `graphql`: build from `deploy/graphql/Dockerfile`, env points at `db`, expose `5000`.
  - `bot`: build from the bot Dockerfile. **Path detail**: the bot/jobs Dockerfiles live at `jobs/Dockerfile.bot` and `jobs/Dockerfile.jobs`, not at repo root. Use `build: { context: jobs, dockerfile: Dockerfile.bot }`. Env points at `graphql`. Slack credentials read from `.env`; if not set, the bot starts in CLI-only mode.

  Use named volumes for the DB. Document the missing-Slack-token case in the README.

- [ ] **Step 2: Write `docker-compose.README.md`** — how to bring the stack up, where to put Slack tokens, how to ingest a first sitemap, where to find logs.

- [ ] **Step 3: Verify locally**

```bash
docker compose up -d
# Wait for graphql to be healthy
curl http://localhost:5000/graphql -X POST -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { queryType { name } } }"}'
# Expected: returns the schema name field, no errors
docker compose down
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.README.md
git commit -m "feat: add docker-compose local dev path"
```

---

### Task 17: Add GitHub Actions CI

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/build-images.yml`
- Keep: `.gitlab-ci.yml` (it's harmless on GitHub; remove only if you want to)

- [ ] **Step 1: Write `.github/workflows/test.yml`**

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install uv
      - run: uv sync
      - run: uv run pytest jobs/tests/
```

- [ ] **Step 2: Write `.github/workflows/build-images.yml`** — build `bot` and `jobs` images from their Dockerfiles, push to GHCR on tag pushes. (Optional for v0.1.0 — can skip if community deployments will build their own.)

- [ ] **Step 3: Push and verify the workflow runs green**

```bash
git push origin <branch>
# Watch in GitHub Actions tab; must end green before tagging.
```

- [ ] **Step 4: Decide on `.gitlab-ci.yml`** — leave it for documentation, or `git rm` if it would confuse contributors. Recommend leaving it with a comment at the top noting "for the Aknostic GitLab instance — not used by GitHub Actions".

- [ ] **Step 5: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions for tests and image builds"
```

---

### Task 18: Add issue and PR templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Use standard GitHub templates**, adapt the language to the project. Each is 10-20 lines.

- [ ] **Step 2: Commit**

```bash
git add .github/ISSUE_TEMPLATE/ .github/PULL_REQUEST_TEMPLATE.md
git commit -m "docs: add issue and PR templates"
```

---

### Task 19: Tag v0.1.0 and write release notes

**Files:**
- Create: `CHANGELOG.md`
- Tag: `v0.1.0`

- [ ] **Step 1: Write `CHANGELOG.md`**

```markdown
# Changelog

## v0.1.0 — 2026-05-21

First open-source release.

- Personas renamed to Saga (positioning strategist) and Lena (consultative
  diagnostician). Inspirations credited in `docs/inspirations.md`.
- Content layer is bring-your-own — no customer-specific content shipped.
- Docker-compose dev path; GitHub Actions CI; Apache 2.0 license.
- Production manifests in `deploy/` (target: Kubernetes with CloudNativePG +
  pgvector + PostGraphile; adapt as needed).
```

- [ ] **Step 2: Tag**

```bash
git tag -a v0.1.0 -m "First open-source release"
git push origin v0.1.0
```

- [ ] **Step 3: Create the GitHub Release** from the tag, paste the changelog entry as the release notes.

- [ ] **Step 4: Commit changelog**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for v0.1.0"
```

---

### Task 20: Cherry-pick the rename back to the GitLab instance

This task happens on the **GitLab** repo, not the GitHub clone.

- [ ] **Step 1: On the GitLab `mother-tree` repo, fetch the rename commits**

The rename should also land in production so Aknostic operators use the same `saga`/`lena` terminology. Options:

  - Cherry-pick Tasks 2-6's commits one by one.
  - Or: produce a single squashed commit from the GitHub branch and apply it.

Either way, the GitLab instance keeps:
  - Its `test-data/*.json` dumps.
  - Its `docs/papers/`, `docs/superpowers/`, `PROJECT.md`, etc.
  - Its Aknostic-specific CronJobs (sites and marketing).
  - Its `CLAUDE.md` with Aknostic-specific hosts.

- [ ] **Step 2: Decide on backward-compat aliases** — operators have been
  typing `ask seth` / `ask lawrence` for months. Two options:

  - **Hard cutover.** Apply the rename and announce on Slack the same day.
    Operators retype. Simplest; works if the team is small.
  - **Alias map.** In `dispatcher.py` on the GitLab instance only, add
    `_PERSONA_ALIASES = {"seth": "saga", "lawrence": "lena"}` and resolve
    triggers through it. Keep for one quarter, then remove. Adds ~5 lines
    of code that never reaches the OSS upstream.

  The OSS surface stays alias-free either way.

- [ ] **Step 3: Verify production tests pass on GitLab CI after the cherry-pick**

- [ ] **Step 4: Tag the GitLab cut** as `v0.1.0-aknostic` or similar — purely for ops bookkeeping.

---

## Verification Gates

After each major section, run the full suite. The numeric counts will rise as tests are added, but everything green is the gate:

```bash
uv run --quiet pytest jobs/tests/ 2>&1 | tail -3
```

After Task 16 (docker-compose), an additional gate:

```bash
docker compose up -d && sleep 15 && \
  curl -sf http://localhost:5000/graphql -X POST \
    -H "Content-Type: application/json" \
    -d '{"query":"{ __type(name:\"User\") { name } }"}' | grep -q '"name":"User"' && \
  echo "✓ schema reachable" || echo "✗ schema not reachable"
docker compose down
```

---

## Out of scope for this plan

- **Trademark check** for "Mother Tree" and "Mycorrhizal Method" — do this *before* announcing publicly. Quick USPTO/EUIPO search and a Google trademark check is enough for v0.1.0.
- **Methodology long-form docs** — `docs/methodology.md` should be a thin starting point. The full methodology lives in the LNCS paper (now in the marketing repo) and in `methodology/`.
- **Outreach to Seth Godin / Lawrence Miller** — optional courtesy. The archetype rename + `docs/inspirations.md` is sufficient for legal safety; a courtesy email at announcement time is goodwill.
- **Public website / landing page** — separate marketing repo concern.
