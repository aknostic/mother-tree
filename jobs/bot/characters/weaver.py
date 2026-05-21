"""The Weaver — the Mycelium.

Takes the Spotter's raw extractions and weaves them into the relationship graph.
Runs after the Spotter, resolving entities against what the network already knows.

TODO: Switch to Sonnet 4.6 (Anthropic) when credits available — better reasoning
for identity judgment calls. For now uses Qwen 3.5.
"""
import logging

from mothertree.config import GENERATION_MODEL, ORGANIZATION_NAME
from mothertree.graphql_client import graphql
from mothertree.llm import _parse_json, chat_conversation

log = logging.getLogger(__name__)

MODEL = GENERATION_MODEL

IDENTITY = """You are the Weaver. You are the mycelium — the branching network that
connects every tree in the forest. Without you, the hyphae detect signals
that go nowhere. With you, every signal finds its place in the web.

The Spotter captures raw intelligence — names, companies, pain signals,
actions. Your job is to connect the dots. Is this Jim Blom the same Jim
who was mentioned last month? Does Parai connect to the Dutch municipality
work we discussed with someone else? Is Stefan's EU hosting platform
related to the sovereignty thread we've been tracking?

You maintain the relationship graph — the living map of who we know, how
we know them, what they care about, and where they sit in the sales
choreography. Every person connects to a company. Every company connects
to an industry and a set of pain points. Every interaction moves the
relationship forward or reveals something new.

Like mycelium that connects trees bidirectionally — carbon flows from
birch to fir in summer, from fir to birch in fall — your connections
are not one-directional. A contact at KPN who mentioned lock-in frustration
connects to our competitive positioning against hyperscalers, which
connects to the insight about EUR 800K Datadog bills, which connects
to the CTO persona who cares about cost. You weave the web that makes
Mother Tree's answers rich.

You resolve, you don't duplicate. When the Spotter says "someone from
KPN" and last week captured "Flavia from KPN," you check: same person?
If you're not sure, keep them separate and flag the possible match. A
false merge is worse than a missed connection — you can always merge
later, but splitting is painful.

You track the source-sink relationships. Where is intelligence flowing?
Who is an active source of signals (a gatherer producing weekly)? Who
is a sink that needs nurturing (a prospect gone quiet)? The network's
health depends on these flows.

YOUR RULES:
- Prefer matching existing entities over creating duplicates.
- When uncertain about a match, flag it — never force a merge.
- Maintain referential integrity. Every contact has a company. Every
  signal has a source. Every opportunity has a stage.
- You are invisible. You run after the Spotter, enriching what was
  captured. The team sees Mother Tree's answers, not your work.
- Never fabricate a relationship. If the Spotter didn't capture a
  connection, you don't invent one.

For each entity from the Spotter, return one of:
- NEW: not found in the existing graph, should be created
- MATCHED: found an existing record (include matched_id)
- UNCERTAIN: possible match but not confident (include candidate_ids and reason)

Return valid JSON only:
{"resolved": [{"entity": {...}, "resolution": "NEW|MATCHED|UNCERTAIN", "matched_id": "...", "candidate_ids": [...], "reason": "..."}], "flags": [...]}"""


def get_existing_graph() -> dict:
    """Query existing contacts, companies, and signals from Hasura.

    Returns a summary of the current relationship graph for Weaver context.
    """
    try:
        result = graphql("""
        query {
          allContactsList(first: 100, orderBy: CREATED_AT_DESC) {
            id fullName role companyId
          }
          allCompaniesList(first: 100, orderBy: CREATED_AT_DESC) {
            id name industry
          }
          allSignalsList(first: 50, orderBy: CREATED_AT_DESC) {
            id source content type status
          }
          allPersonasList(first: 50) {
            id name role profile
          }
        }
        """)
        return {
            "contacts": result.get("allContactsList", []),
            "companies": result.get("allCompaniesList", []),
            "signals": result.get("allSignalsList", []),
            "personas": result.get("allPersonasList", []),
        }
    except Exception:
        log.exception("Failed to fetch existing graph")
        return {"contacts": [], "companies": [], "signals": [], "personas": []}


def resolve(entities: list[dict]) -> dict | None:
    """Resolve extracted entities against the existing relationship graph.

    Takes Spotter entities, queries current graph state, calls the LLM
    to determine NEW/MATCHED/UNCERTAIN for each entity.

    Returns resolution dict or None on failure.
    """
    if not entities:
        return {"resolved": [], "flags": []}

    try:
        graph = get_existing_graph()
        graph_summary = _format_graph_summary(graph)

        # Inject team and org context so the Weaver knows who WE are
        team_context = _get_team_context()

        entities_text = "\n".join(
            f"- {e.get('type', 'unknown')}: {e.get('name', 'Unknown')} "
            f"(role: {e.get('role', 'unknown')}, org: {e.get('organization', e.get('company', 'unknown'))})"
            for e in entities
        )

        user_content = f"""TEAM CONTEXT (these are US — always resolve as MATCHED):
{team_context}

Existing graph:
{graph_summary}

Entities to resolve:
{entities_text}

Raw entities JSON:
{entities}

Resolve each entity against the existing graph."""

        messages = [
            {"role": "system", "content": IDENTITY},
            {"role": "user", "content": user_content},
        ]
        raw = chat_conversation(messages, model=MODEL)
        if not raw:
            return None
        return _parse_json(raw)
    except Exception:
        log.exception("Weaver resolution failed")
        return None


def _get_team_context() -> str:
    """Build team context for the Weaver — who we are, so it never flags us as unknown."""
    org_name = ORGANIZATION_NAME or "our organization"
    parts = [f"Our company: {org_name}"]
    try:
        # Get enrolled team members
        result = graphql("""
        query {
          allUsersList(condition: {active: true}) { name role }
        }
        """)
        for e in result.get("allUsersList", []):
            parts.append(f"Team member: {e['name']} (role: {e['role']})")
    except Exception:
        pass
    try:
        # Get org profile identity
        result = graphql("""
        query {
          allOrganizationsList(condition: {elementType: "identity"}, first: 2) { content }
        }
        """)
        for o in result.get("allOrganizationsList", []):
            parts.append(f"About us: {o['content'][:150]}")
    except Exception:
        pass
    return "\n".join(parts)


def _format_graph_summary(graph: dict) -> str:
    """Format the graph for LLM context."""
    lines = []

    contacts = graph.get("contacts", [])
    if contacts:
        lines.append("Contacts:")
        for c in contacts[:30]:
            lines.append(f"  [{c['id']}] {c.get('fullName', '?')} — role: {c.get('role', '?')}")

    companies = graph.get("companies", [])
    if companies:
        lines.append("Companies:")
        for c in companies[:30]:
            lines.append(f"  [{c['id']}] {c.get('name', '?')} — industry: {c.get('industry', '?')}")

    personas = graph.get("personas", [])
    if personas:
        lines.append("Known personas (fictional — NOT real contacts, do NOT create contacts for these):")
        for p in personas:
            profile_snippet = (p.get("profile") or "")[:80]
            desc = f"  {p.get('name', '?')} — {p.get('role', '?')}"
            if profile_snippet:
                desc += f" ({profile_snippet})"
            lines.append(desc)

    if not lines:
        lines.append("(empty graph — no existing records)")

    return "\n".join(lines)
