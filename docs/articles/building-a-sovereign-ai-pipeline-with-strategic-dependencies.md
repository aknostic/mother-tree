# Building a Sovereign AI Pipeline with Strategic Dependencies

**Category:** Policy and Sovereignty / Provider Ecosystem

---

We are building an AI-powered commercial intelligence platform. It extracts structured knowledge from our content, scores it for quality using multiple independent models, and feeds a training system that helps our sales team articulate our value proposition.

The core of this pipeline runs on European infrastructure with open-weight models. But we also use Claude Code and Anthropic models — deliberately, in roles where they add value without creating dependency.

Here is how we designed it, and why.

## The problem

We have a growing library of content: marketing documents, published articles, case studies, competitive positioning. This content contains commercial insights — perspective shifts that help prospects see their own situation differently.

Manually curating these insights does not scale. As we publish more, the gap between what exists and what our sales team actually uses widens. We needed a system that automatically extracts, validates, and maintains a structured knowledge base from our content sources.

The catch: this system touches our most sensitive commercial intelligence. It must run on infrastructure we control, using models we can replace.

## The architecture

Our pipeline has five stages, each with a deliberate model choice.

### Stage 1: Extraction

A large language model reads each content source and extracts structured entities — insights with reframes, evidence, stakeholder tailoring, and triggers. This is the most demanding task: it requires deep comprehension of what makes a commercial insight useful versus what is merely a summary.

**Model:** Qwen 3.5 397B-A17B, running on Scaleway Generative APIs in Paris. Open-weight (Apache 2.0), Mixture-of-Experts architecture (only 17 billion parameters active per token, making it cost-efficient despite 397 billion total). Tier S on the Onyx self-hosted LLM leaderboard.

**Why this model:** It has the best structured output quality of any open-weight model available to us. The MoE architecture keeps costs reasonable for processing large document sets.

### Stage 2: Field validation

Code, not a model. Strict schema validation rejects malformed records — unknown fields, missing required fields, invalid categories. This catches the inevitable quirks of LLM output (misspelled field names, objects where strings are expected) before they enter the database.

**Why code, not a model:** Validation rules are deterministic. There is no reason to spend inference tokens on something a few lines of Python handles perfectly.

### Stage 3: Confidence scoring

Three architecturally different models independently score each extracted insight on a 0.0-1.0 scale. The key principle: the scorers must be different from the extractor. Same model scoring its own output is biased. Different architectures trained on different data with different biases give genuinely independent assessments.

**Models:**
1. DeepSeek R1-Distill Llama 70B — reasoning specialist, evaluates through chain-of-thought
2. Llama 3.3 70B Instruct — best instruction-following in its class, reliably applies the scoring rubric
3. Gemma 3 27B — Google architecture, cheapest scorer, catches what the other two miss

All three run on Scaleway Generative APIs. Open-weight. European infrastructure.

**Decision logic:** Take the median score (resists one outlier). If all three agree above 0.7, auto-accept. If all three agree below 0.4, auto-reject. If they disagree significantly (spread above 0.3), flag for review.

### Stage 4: Triage coordination

Flagged items — the ones where the three scorers disagreed — need a more nuanced evaluation. Is this a genuine insight that one scorer undervalued, or is it borderline content that happened to get one generous score?

**Model:** Claude Haiku 4.5 (Anthropic). Fast, cost-effective, handles classification at 90% of the quality of larger models. Processes the flagged queue in bulk.

### Stage 5: Arbitration

The truly ambiguous cases — where even Haiku cannot make a confident call — escalate to a final arbiter.

**Model:** Claude Sonnet 4.6 (Anthropic). The deepest reasoning available. Only touches the small subset of cases that survived four previous stages of filtering.

## The sovereignty posture

The core pipeline — extraction, validation, scoring, accept/reject — runs entirely on European infrastructure using open-weight models. No data leaves the European jurisdiction for these functions.

Anthropic models handle triage and arbitration. These are quality-enhancement functions, not critical-path functions. If Anthropic becomes unavailable tomorrow:

- The extraction continues (Qwen on Scaleway)
- The scoring continues (DeepSeek, Llama, Gemma on Scaleway)
- Auto-accept and auto-reject continue (code logic, no model needed)
- Flagged items queue for human review instead of Haiku triage
- Ambiguous items go directly to human review instead of Sonnet arbitration

The pipeline degrades gracefully. More human review, same data quality. No data loss, no service interruption, no architectural change required.

## The model selection policy

We formalized three rules:

1. **No OpenAI models.** Not for extraction, scoring, embedding, or any other function.
2. **Open source first.** Prefer open-weight models that can be self-hosted if needed.
3. **European second.** When choosing between equivalent open-source models, prefer European-origin models.

Anthropic models are used where they add unique value — and only in roles where they can be replaced by human review if needed. We use Claude Code as an interactive interface for our team. It queries our central intelligence via GraphQL. The intelligence layer does not depend on Claude Code.

## Why not fully sovereign?

We could run the entire pipeline on open-weight models. Replace Haiku triage with a fourth Scaleway model. Replace Sonnet arbitration with human review only.

We chose not to — for now. The Anthropic models genuinely improve quality at the triage and arbitration stages. They are better at nuanced evaluation than any open-weight model currently available to us. Removing them would mean more false positives reaching our training system, or more human review time.

The key is that this is a choice, not a dependency. The architecture supports full sovereignty. We opt into Anthropic where the quality justifies it, and we can opt out at any time without redesigning the system.

This is the same principle we advocate to our clients: freedom to operate means your systems work for you, you can change providers when you want, and you stay because you choose to — not because you are locked in.

## The data store

PostgreSQL with pgvector on Kubernetes, managed by CloudNativePG. Hasura generates a typed GraphQL API from the database schema. All on Scaleway, all European infrastructure. Backups to Scaleway Object Storage.

The database holds the structured knowledge base: insights with confidence scores, buyer personas, case studies, competitive positioning. The training system queries this database to generate exercises for our sales team.

## What we learned

**Use a different model to judge than to create.** Self-evaluation is unreliable. Three independent judges catch what self-scoring misses.

**Field validation is not optional.** LLMs generate creative field names. One run produced "refidence" instead of "evidence." Strict schema validation before database insertion is essential.

**Replace, do not accumulate.** Running the same extraction twice produces slightly different results. Each ingestion run replaces all records from that source. The database always reflects the latest extraction, not an accumulation of probabilistic runs.

**Design for graceful degradation.** Every external dependency should have a fallback. Our fallback for Anthropic is human review. Our fallback for Scaleway is self-hosting the same open-weight models. Our fallback for any single scoring model is the other two.

**Sovereignty is a spectrum, not a binary.** Fully sovereign is possible but has a quality cost. Strategically using non-European services in non-critical roles — with clear fallback paths — is a pragmatic approach that most organizations can adopt today.
