# Content Pipeline

How external content flows into Mother Tree's central intelligence.

## The two lenses

Every piece of content — a markdown file in the marketing repo, a blog post on aknostic.com, an article on Clouds of Europe — contains two kinds of information:

**Foundation** — who we are, what we promise, who we're for. The positioning that changes slowly.
**Narrative** — proof the change is real. The stories, evidence, and reframes that accumulate over time.

A single page often contains both. A case study on aknostic.com states the change ("we help engineering leaders escape lock-in") *and* provides evidence ("this client cut costs by 40%"). The pipeline handles this by running the same content through two independent extraction lenses:

```
                        ┌──────────────────────────────────────────────┐
                        │              CONTENT SOURCE                  │
                        │                                              │
                        │  Marketing repo, aknostic.com, Clouds of    │
                        │  Europe, individual files, web pages...      │
                        └──────────────┬───────────────────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │                         │
                          ▼                         ▼
               ┌─────────────────────┐   ┌─────────────────────┐
               │  FOUNDATION LENS    │   │  NARRATIVE LENS      │
               │                     │   │                      │
               │  "What is the       │   │  "What reframe could │
               │   positioning here?"│   │   a hunter use in    │
               │                     │   │   conversation?"     │
               │  Extracts:          │   │                      │
               │  • Change statements│   │  Extracts:           │
               │  • Worldview records│   │  • Insights/reframes │
               │  • Personas         │   │  • Evidence          │
               │  • Competitors      │   │  • Stakeholder lens  │
               └────────┬────────────┘   │  • Triggers          │
                        │                └──────────┬───────────┘
                        │                           │
                        ▼                           ▼
               ┌─────────────────────┐   ┌─────────────────────┐
               │  FOUNDATION TABLES  │   │  NARRATIVE TABLES    │
               │                     │   │                      │
               │  change             │   │  insights            │
               │  worldview          │   │  (case_studies)      │
               │  personas           │   │                      │
               │  competitors        │   │                      │
               └─────────────────────┘   └─────────────────────┘
```

The lenses are independent. You can run foundation once and narrative daily. You can run both on the same source or only one. The source keys use different prefixes (`foundation:` vs `narrative:`) so they never collide.

## How the lenses map to Seth Godin's framework

The pipeline directly implements the marketing framework described in `methodology/marketing-framework.md`:

```
        SETH GODIN'S STRUCTURE              PIPELINE LAYER         DATABASE TABLES
        ──────────────────────              ──────────────         ───────────────

        The Change                    ───►  Foundation         ──► change
        "What transformation do                                    statement, context
         we offer?"

        The Worldview                 ───►  Foundation         ──► worldview
        "What does the audience                                    belief, pain,
         already believe?"                                         readiness_signal

        The Audience                  ───►  Foundation         ──► personas
        "Who specifically?"                                        name, role, profile,
                                                                   objections, criteria

        vs. Alternatives              ───►  Foundation         ──► competitors
        "How do we differentiate?"                                 type, positioning,
                                                                   response

        ─────────────────────────────────────────────────────────────────────────

        The Story                     ───►  Narrative          ──► insights
        "What proof exists that                                    reframe, evidence,
         the change is real?"                                      stakeholder_lens,
                                                                   trigger, next_step
```

Foundation answers: *what do we say, and to whom?*
Narrative answers: *what proof do we have, and how does a hunter use it?*

## Three source types in the framework

The central intelligence organizes content by the role it plays:

### Foundation

Who we are, what we promise, who we're for. This is Seth's domain — the change and the worldview.

**Sources:** Marketing repository (all markdown files), aknostic.com (full sitemap).
**Extracts:** Change statements, worldview records (beliefs, pains, readiness signals), personas, competitive positioning.
**Changes:** Slowly. Foundational positioning evolves over months, not days.
**Schedule:** Run after significant content changes — a new positioning page, updated personas, revised competitive landscape.

### Narrative

Proof the change is real. Stories that resonate with the audience's worldview.

**Sources:** Clouds of Europe (articles, guides, analysis), aknostic.com blog and case studies, marketing repository (case study documents, blog drafts).
**Extracts:** Insights/reframes — perspective shifts a hunter can use in conversation. Each scored by three independent models for quality.
**Changes:** Frequently. Every new article, every new case study adds to the evidence.
**Schedule:** Run on a recurring basis — every few hours for sitemaps, daily for local repos. New articles become training material within hours of publication.

### Conversation

What happens in practice. The live loop from the Mycorrhizal Method.

**Sources:** Hunters and gatherers via Slack, Claude Code skill, or direct API.
**Not ingested by the pipeline.** Entered by humans through daily work. Meeting notes, signal observations, debrief responses, follow-up actions.

### The key insight: same source, different lenses

A blog post on aknostic.com contains both positioning and stories. A case study in the marketing repo contains both personas and evidence. The pipeline doesn't force you to choose — you run the same source through both lenses independently:

```
    Marketing repo
    ├── foundation lens  →  change, worldview, personas, competitors
    └── narrative lens   →  insights (reframes, evidence, triggers)

    aknostic.com/sitemap.xml
    ├── foundation lens  →  change, worldview, personas, competitors
    └── narrative lens   →  insights (filtered to /blog/, /case-studies/, /insights/)

    clouds-of-europe.eu/sitemap.xml
    └── narrative lens   →  insights (all pages)
```

Foundation and narrative have different cadences. Foundation is a snapshot of positioning — refresh it when the positioning changes. Narrative is a growing body of evidence — refresh it regularly to catch new stories.

## The ingestion CLI

All ingestion goes through `jobs/cli.py` (which delegates to `jobs/ingestion/ingest.py`). Both lenses support all five input modes:

```
ingest <lens> <mode> <target> [--filter /path1 /path2] [--force]
```

### Lenses

| Lens | What it extracts | Target tables |
|------|-----------------|---------------|
| `foundation` | Change statements, worldview, personas, competitors | `change`, `worldview`, `personas`, `competitors` |
| `narrative` | Insights: reframes, evidence, stakeholder lens, triggers | `insights` |

### Input modes

| Mode | Target | Description |
|------|--------|-------------|
| `file` | Local path | Single markdown file |
| `dir` | Local path | All `.md` files in a directory (non-recursive) |
| `repo` | Local path | All `.md` files tracked by git in a repository |
| `url` | URL | Single web page (HTML converted to text) |
| `sitemap` | Sitemap URL | All pages listed in an XML sitemap |

### Flags

| Flag | Effect |
|------|--------|
| `--filter /path1 /path2 ...` | Only process URLs containing one of these path segments (sitemap mode only) |
| `--force` | Re-ingest even if content hasn't changed since last run |

### Examples

```bash
# Foundation from the marketing repo (run after significant changes)
ingest.py foundation repo /path/to/marketing

# Narrative from the same marketing repo (run on schedule)
ingest.py narrative repo /path/to/marketing

# Narrative from Clouds of Europe (run on schedule)
ingest.py narrative sitemap https://clouds-of-europe.eu/sitemap.xml

# Narrative from aknostic.com blog posts and case studies only
ingest.py narrative sitemap https://aknostic.com/sitemap.xml --filter /blog/ /case-studies/ /insights/

# Foundation from the full aknostic.com site (run after site updates)
ingest.py foundation sitemap https://aknostic.com/sitemap.xml

# Single file, either lens
ingest.py foundation file /path/to/positioning.md
ingest.py narrative file /path/to/case-study.md

# Check current database state
ingest.py stats
```

### Environment variables

```
HASURA_URL              GraphQL endpoint (default: cluster-internal URL)
HASURA_ADMIN_SECRET     Hasura admin secret (required)
SCALEWAY_AI_API_KEY     Scaleway Generative APIs key (required)
```

Optional overrides for models and thresholds are in `config.py`.

## Extraction in detail

### Foundation extraction

Qwen 3.5 (deep extraction) receives the full document, existing records from the database (to avoid duplicates), and a prompt asking for four types of content. Mistral Small 3.2 handles classification. Context-aware — fetches current change statements, worldviews, personas, and competitors and injects them into the extraction prompt so the model can avoid extracting what already exists. A deterministic pre-insert dedup check catches any stragglers.

```
Document + existing records ──► Qwen 3.5 ──► [
    {"type": "change",     "statement": "...", "context": "..."},
    {"type": "worldview",  "persona_name": "...", "belief": "...", "pain": "...", "readiness_signal": "..."},
    {"type": "persona",    "name": "...", "role": "...", "profile": "...", ...},
    {"type": "competitor", "competitor_type": "...", "positioning": "...", ...}
]
```

Each record is validated against its schema (required fields, types, unknown fields stripped), dedup-checked against the database, then inserted with the source key. Vector embeddings (BGE Multilingual Gemma2) are generated on insert for all records, enabling semantic search across the full CI. Foundation runs are sequential: site first (builds context), then marketing (sees site's output).

### Narrative extraction

Qwen 3.5 (deep extraction) receives the article content, grounded in foundation data (top changes, worldviews, personas), and a prompt focused on commercial insights — not summaries, but perspective shifts usable in conversation:

```
Document + foundation context ──► Qwen 3.5 ──► [
    {
        "category":         "lock-in-freedom",
        "reframe":          "The one-sentence perspective shift",
        "evidence":         "The specific supporting data or argument",
        "stakeholder_lens": [{"role": "CTO", "framing": "How it lands for them"}],
        "trigger":          "What makes this timely for a prospect",
        "next_step":        "Where this naturally leads in conversation"
    },
    ...
]
```

Insight categories: `lock-in-freedom`, `regulatory-pressure`, `capability-vs-dependency`, `cost-reality`, `developer-experience`, `resilience-reliability`.

After extraction, each batch of insights goes through multi-model confidence scoring. Accepted insights receive vector embeddings on insert, enabling semantic search for training source selection and briefings.

## Quality control

### Foundation records

Field validation only — strict schema enforcement, required fields checked, unknown fields stripped. Foundation records reflect the company's own positioning, so confidence scoring would be circular.

### Narrative insights

Four-stage quality pipeline:

```
    ┌──────────┐     ┌──────────────────────────────────────┐     ┌───────────┐     ┌────────────┐
    │          │     │     THREE INDEPENDENT SCORERS         │     │           │     │            │
    │ Validate ├────►│                                      ├────►│  Triage   ├────►│ Arbitrate  │
    │ fields   │     │  Devstral 2 123B  ─┐                │     │           │     │            │
    │          │     │  Llama 3.3 70B   ──┼── median score  │     │  Haiku    │     │  Sonnet    │
    │          │     │  Gemma 3 27B     ──┘                │     │  4.5      │     │  4.6       │
    └──────────┘     └──────────────────────────────────────┘     └───────────┘     └────────────┘

    Required         Different architectures,                     Flagged items     Genuinely
    fields,          different biases.                             reviewed.         ambiguous
    type checks.     Auto-accept ≥ 0.7                            Low cost,         cases only.
                     Auto-reject ≤ 0.4                            fast model.
                     Flag if spread > 0.3
```

1. **Field validation** — required fields present, correct types, unknown fields stripped
2. **Three-model confidence scoring** — independent judges with different architectures and biases, median score used
3. **Haiku triage** — flagged items (scorers disagree or borderline confidence) reviewed by Claude Haiku 4.5
4. **Sonnet arbitration** — genuinely ambiguous cases escalated to Claude Sonnet 4.6
5. **Graceful degradation** — the core pipeline runs on Scaleway (open-weight models) without Anthropic. If Anthropic is unavailable, flagged items go to human review instead of automated triage/arbitration

### Confidence thresholds

| Threshold | Default | Effect |
|-----------|---------|--------|
| `CONFIDENCE_AUTO_ACCEPT` | 0.7 | All three scorers agree it's good — insert directly |
| `CONFIDENCE_AUTO_REJECT` | 0.4 | All three scorers agree it's weak — discard |
| `CONFIDENCE_DISAGREEMENT_SPREAD` | 0.3 | Scorers disagree significantly — flag for triage |

## Idempotency and skip-unchanged

### Replace-per-source

Every ingestion run uses replace-per-source: delete all records from that source key, then insert fresh extractions. Running the pipeline twice produces the same result, not accumulation.

Source keys are prefixed by lens:
- `foundation:/path/to/file.md` — foundation records from that file
- `narrative:/path/to/file.md` — narrative records from the same file
- `foundation:https://aknostic.com/some-page` — foundation records from that URL
- `narrative:https://aknostic.com/some-page` — narrative records from the same URL

This means foundation and narrative records from the same source are tracked independently. Re-running narrative doesn't touch foundation records, and vice versa.

### Skip-unchanged detection

Before processing a document, the pipeline checks the `ingestion_log` table for a matching source key and content hash (SHA-256, first 16 hex chars). If the content hasn't changed since the last successful ingestion, it's skipped entirely — no LLM calls, no database writes.

Use `--force` to bypass this check and re-extract regardless of content changes. Useful when the extraction prompts or models have been updated.

```
    Content arrives
         │
         ▼
    Hash content ──► Compare to ingestion_log
         │                    │
         │              ┌─────┴─────┐
         │              │           │
         │           Changed    Unchanged
         │              │           │
         │              ▼           ▼
         │          Extract      Skip
         │          Score        (unless --force)
         │          Insert
         │              │
         └──────────────┴──► Update ingestion_log
```

## Recommended operational cadence

```
    FOUNDATION (positioning — changes slowly)
    ──────────────────────────────────────────

    Marketing repo          After significant content changes
    aknostic.com sitemap    After site updates

    NARRATIVE (evidence — grows continuously)
    ──────────────────────────────────────────

    Marketing repo          Daily
    aknostic.com blog       Every 6 hours
    Clouds of Europe        Every 6 hours

    CONVERSATION (live loop — not pipeline-managed)
    ────────────────────────────────────────────────

    Entered by humans via Slack, skill, or API
```

Foundation is a snapshot of how we position ourselves. Run it when the positioning changes.

Narrative is a growing body of evidence. Run it on schedule — skip-unchanged detection means unchanged pages cost nothing, while new or updated articles flow into the insights table automatically.

## Training curriculum

The training engine (`jobs/training/`) consumes the central intelligence to deliver role-specific training via Slack DM.

```
    ┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │  Foundation   │     │                  │     │                  │
    │  tables       ├────►│  Curriculum      ├────►│  Slack DM        │
    │              │     │  + Generator      │     │                  │
    ├──────────────┤     │                  │     │  • Instructions  │
    │  Narrative    │     │  Seth (marketing)│     │  • Exercises     │
    │  tables       ├────►│  Lawrence (sales)│     │  • Refreshers    │
    │              │     │  Mother Tree      │     │  • Progress      │
    └──────────────┘     └──────────────────┘     └──────────────────┘
```

**Role-specific paths** — defined in `jobs/training/curriculum.py`:

- **Hunter:** The Foundation → The Offering → The Conversation → The Difference → The Hunt
- **Gatherer:** The Change → Signal Recognition → Delivery → Content Creation → Feedback
- **Farmer:** The Platform → The Community → The Practice

Each stage has 2-3 chapters. Each chapter specifies which trainer (Seth, Lawrence, or Mother Tree) teaches it and which CI tables provide source data. Stage 0 works with foundation data only; stage 1+ requires narrative insights.

**Proficiency decay** — completed chapters decay over time if not practiced. When proficiency drops below threshold, the system delivers targeted refreshers instead of new material.

**Daily delivery** — the `training-deliver` CronJob checks each enrolled user, determines whether to advance (new chapter), refresh (decayed chapter), or nudge (idle too long), and delivers via Slack DM with progress context.
