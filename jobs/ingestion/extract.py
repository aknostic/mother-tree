"""Extraction prompts by source type.

Foundation (Saga's lens) → the change, the worldview, personas, competitors
Narrative (Lena's lens) → stories, evidence, reframes for sales conversations
"""

from mothertree.graphql_client import graphql
from mothertree.llm import extract_deep

# --- Foundation extraction (Saga's lens) ---

FOUNDATION_EXTRACTION_TEMPLATE = """
You are extracting foundational positioning through Saga's lens — story, tribe, change.
Think like Saga: what's the change? Who's it for? What do they already believe?

Every organization offers a transformation — not features, not services. The change.
Your job is to find it in this document and articulate it the way Saga would.

CRITICAL RULES:
- Extract the ORGANIZATION'S positioning only. Not client transformations from case studies.
  If a document describes what a CLIENT achieved, that's evidence for narrative extraction,
  not a change statement. The change is what THIS ORGANIZATION offers to ALL its customers.
- Do NOT repeat what we already have (see EXISTING FOUNDATION below).
  Only extract genuinely new insights or significantly sharper versions of existing ones.
  "Significantly sharper" means a real improvement in specificity — not just different words.
- If the document adds nothing new to our foundation, return an empty array [].

{existing_context}

Extract four types of content:

1. CHANGE STATEMENTS: The core transformation the organization offers.
   Not "we build platforms" — that's a feature.
   The change is what the CUSTOMER becomes. "From vendor-dependent to infrastructure-independent."
   Be specific. Be punchy.

   Return as: {{"type": "change", "statement": "...", "context": "why this matters", "confidence": 0.0-1.0}}

2. WORLDVIEW RECORDS: What does the smallest viable audience already believe?
   These are beliefs the BUYER holds BEFORE they meet the organization.
   Not what the organization teaches them — what they already know to be true.

   Return as: {{"type": "worldview", "persona_name": "...", "belief": "what they already believe",
   "pain": "what they feel right now", "readiness_signal": "how you'd spot someone ready for this change",
   "confidence": 0.0-1.0}}

3. PERSONAS: Who specifically is this for? Not "everyone" — the smallest viable audience.
   These are BUYERS — the people who sign contracts and make decisions.
   Not end-users of a client's product. Not researchers, not students, not consumers.
   Not named individuals from case studies — archetypes with worldviews.

   Make them HUMAN, not functional. A hunter needs to empathize with this person.
   What keeps them up at 2AM? What does personal success look like for them?
   What event in their world makes them ready to have this conversation?

   Return as: {{"type": "persona", "name": "...", "role": "...", "profile": "goals and challenges",
   "fears": "what keeps them up at 2AM — the personal risk they carry",
   "motivation": "what does success look like for them personally, not just their company",
   "trigger": "what event or change makes them ready to buy right now",
   "communication": "how they engage", "decision_criteria": [...],
   "objections": [{{"objection": "...", "response": "..."}}],
   "how_to_reach": "channels that work", "confidence": 0.0-1.0}}

4. COMPETITORS: Not companies — categories of alternatives. How does the audience
   currently solve this problem without the organization?

   Return as: {{"type": "competitor", "competitor_type": "category not company name",
   "positioning": "how to differentiate", "when_mentioned": "context", "response": "what to say",
   "confidence": 0.0-1.0}}

Return a JSON array mixing all types. Each object MUST have a "type" field.
Confidence (0.0-1.0): how directly the document states this. 0.9+ = explicitly stated,
0.7-0.8 = clearly implied, 0.5-0.6 = inferred from context, below 0.5 = speculative.
If the document adds nothing new, return [].
"""


# --- Narrative extraction (Lena's lens) ---

NARRATIVE_EXTRACTION_TEMPLATE = """
You are extracting sales conversation material through Lena's consultative lens — diagnose before prescribe. Think like Lena: how would a seller USE this in a real conversation?

Lena teaches selling in the spirit of service — shared problem-solving, not pitching.
Every insight you extract should be something a consultative seller could say to a prospect
that makes them see their own situation differently. Not a fact. A reframe.

OUR FOUNDATION (what we know about ourselves):
{foundation_context}

---

Now analyze this content. For each insight, think:
- What question from a prospect does this answer?
- What objection does this overcome?
- At what moment in a consultative conversation would you use this?
- How does this help the prospect see their problem differently?

An insight is NOT a summary. It IS a one-sentence perspective shift that a seller
could drop into a conversation: "Most companies think managed Kubernetes solves 80%
of their platform problem. It's actually 20%."

Ground your insights in our foundation:
- Connect reframes to specific change statements or worldview beliefs
- Frame stakeholder lenses using our persona roles and their known concerns
- Identify triggers that match readiness signals — what happened that makes this timely?

For each insight, return:
- category: one of "lock-in-freedom", "regulatory-pressure", "capability-vs-dependency",
  "cost-reality", "developer-experience", "resilience-reliability"
- reframe: the one-sentence perspective shift (direct, punchy, conversational — something
  you'd actually say to a CTO over coffee)
- evidence: the specific data or argument that backs up the reframe
- stakeholder_lens: array of {{role, framing}} — who cares about this and why?
- trigger: what happened or is happening that makes this timely for a prospect?
- next_step: where does this naturally lead in the conversation?

ALSO extract PROOF POINTS — specific, measurable outcomes from real work.
Not vague claims. Real numbers, real durations, real outcomes.

CRITICAL: Use ONLY names that appear in the document. Never invent client names.
- If the document names the project or client, use that exact name (e.g., "Project SeaSense", "Qualtrics to Formbricks migration")
- If the document describes the author's own work, use the project name or article subject, not "Internal Case Study"
- If no name is given, use "Undisclosed client" — never fabricate a name or industry
- Industry facts (e.g., AWS pricing) are NOT proof points — they are evidence for insights

For each proof point, return:
- type: "proof_point"
- client: the exact name from the document (project name, client name, or "Undisclosed client")
- outcome: the specific result with numbers ("reduced AWS bill by 40%", "12-year ongoing relationship")
- duration: how long (if mentioned)
- relevance: which change statement this proves
- confidence: 0.0-1.0

Return a JSON array mixing insights and proof points. Each object MUST have a "type" field
("insight" for insights, "proof_point" for proof points).
Only extract genuine material. If you wouldn't say it in a meeting, don't extract it.
If the content contains no usable conversation material, return [].
"""


def _fetch_existing_foundation() -> str:
    """Fetch existing foundation data so extraction can avoid duplicates."""
    result = graphql("""query {
        allChangesList(first: 20, orderBy: CONFIDENCE_DESC) { statement }
        allWorldviewsList(first: 20, orderBy: CONFIDENCE_DESC) { belief }
        allPersonasList(first: 10) { name role }
        allCompetitorsList(first: 15) { type positioning }
    }""")
    sections = []
    changes = result.get("allChangesList", [])
    if changes:
        sections.append("Changes already captured:\n" + "\n".join(f"- {c['statement']}" for c in changes))
    beliefs = result.get("allWorldviewsList", [])
    if beliefs:
        sections.append("Worldviews already captured:\n" + "\n".join(f"- {w['belief']}" for w in beliefs))
    personas = result.get("allPersonasList", [])
    if personas:
        sections.append("Personas already captured:\n" + "\n".join(f"- {p['name']} ({p.get('role', '')})" for p in personas))
    competitors = result.get("allCompetitorsList", [])
    if competitors:
        sections.append("Competitors already captured:\n" + "\n".join(f"- {c['type']}" for c in competitors))
    if sections:
        return "EXISTING FOUNDATION (do NOT repeat these):\n" + "\n\n".join(sections)
    return "EXISTING FOUNDATION: empty — this is the first extraction."


def extract_foundation(content: str) -> list[dict]:
    """Extract change, worldview, personas, and competitors from foundation content.

    Context-aware: fetches existing foundation data so the LLM avoids duplicates.
    """
    existing = _fetch_existing_foundation()
    prompt = FOUNDATION_EXTRACTION_TEMPLATE.format(existing_context=existing)
    return extract_deep(content, prompt)


def _fetch_foundation_context() -> str:
    """Fetch foundation data to ground narrative extraction."""
    result = graphql("""query {
        allChangesList(first: 10, orderBy: CONFIDENCE_DESC) { statement context }
        allWorldviewsList(first: 10, orderBy: CONFIDENCE_DESC) { belief pain readinessSignal }
        allPersonasList(first: 5) { name role profile }
    }""")
    parts = []
    for stmt in result.get("allChangesList", []):
        parts.append(f"Change: {stmt['statement']} ({stmt.get('context', '')})")
    for wv in result.get("allWorldviewsList", []):
        parts.append(f"Worldview: {wv['belief']} | Pain: {wv.get('pain', '')} | Signal: {wv.get('readinessSignal', '')}")
    for p in result.get("allPersonasList", []):
        parts.append(f"Persona: {p['name']} ({p.get('role', '')}) — {p.get('profile', '')[:100]}")
    return "\n".join(parts) if parts else "No foundation data available yet."


def extract_narrative(content: str) -> list[dict]:
    """Extract insights/reframes from narrative content, grounded in foundation."""
    foundation = _fetch_foundation_context()
    prompt = NARRATIVE_EXTRACTION_TEMPLATE.format(foundation_context=foundation)
    return extract_deep(content, prompt)
