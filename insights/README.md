# Insight Library

This directory defines the **structure** of the insight library — the categories and the schema for each insight. The actual insight content (specific reframes, evidence, case studies) is loaded from external content sources into the central intelligence (PostgreSQL).

## How insights work

An insight is a perspective shift that teaches a prospect something about their own situation. Hunters use insights in Stage 3 (Reframe) of the choreography.

## Insight schema

Every insight in the database follows this structure:

```yaml
category: string        # Which category this insight belongs to
reframe: string         # The one-sentence perspective shift
evidence: string        # What makes it credible (data, regulation, client pattern)
stakeholder_lens:       # How it lands for different stakeholders
  - role: string        # CTO, CISO, CFO, CEO, etc.
    framing: string     # How to frame for this role
trigger: string         # What makes it timely (regulatory deadline, event, market signal)
next_step: string       # Where this leads (usually toward an assessment)
```

## Categories

Each file in this directory defines a category. Categories are structural — they describe the domain, not specific reframes. Content sources (e.g., a marketing repository) provide the actual insights tagged to these categories.

## Content ingestion

External content sources feed into the insight library through the content pipeline:

1. Source repository contains structured marketing content (reframes, case studies, personas, competitive positioning)
2. A scheduled job scans the source for insight-shaped content
3. Content is parsed, tagged by category and stakeholder, and loaded into PostgreSQL
4. Vector embeddings enable semantic search (e.g., "what reframes work for financial services CTOs?")

See [content pipeline](../docs/content-pipeline.md) for details.
