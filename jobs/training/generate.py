#!/usr/bin/env python3
"""Generate training content from the central intelligence.

Usage:
  generate.py saga          # Saga's assessment of the foundation
  generate.py onboarding    # Foundational instruction for a new hunter
"""

import sys

from mothertree.graphql_client import graphql
from mothertree.llm import generate


def fetch_foundation() -> dict:
    """Fetch all foundation data from the central intelligence."""
    data = graphql("""
    {
      allChangesList { statement context }
      allWorldviewsList { belief pain readinessSignal }
      allPersonasList { name role profile }
      allCompetitorsList { type positioning }
    }
    """)
    # Remap to legacy keys for downstream formatting
    return {
        "change": data.get("allChangesList", []),
        "worldview": [
            {**w, "readiness_signal": w.pop("readinessSignal", None)}
            for w in data.get("allWorldviewsList", [])
        ],
        "personas": data.get("allPersonasList", []),
        "competitors": data.get("allCompetitorsList", []),
    }


def _format_foundation(data: dict, include_profile: bool = False) -> str:
    """Format foundation data into a context string."""
    changes = "\n".join(f"- {c['statement']}: {c['context']}" for c in data["change"][:10])
    worldviews = "\n".join(f"- Belief: {w['belief']} | Pain: {w['pain']}" for w in data["worldview"][:10])
    personas = "\n".join(
        f"- {p['name']} ({p['role']}){': ' + p.get('profile', '')[:200] if include_profile else ''}"
        for p in data["personas"][:5]
    )
    parts = [f"CHANGE STATEMENTS:\n{changes}", f"WORLDVIEW:\n{worldviews}", f"PERSONAS:\n{personas}"]
    if "competitors" in data:
        competitors = "\n".join(f"- vs {c['type']}: {c['positioning']}" for c in data["competitors"][:10])
        parts.append(f"COMPETITIVE POSITIONING:\n{competitors}")
    return "\n\n".join(parts)


def cmd_saga():
    """Ask Saga to assess the foundation based on central intelligence only."""
    data = fetch_foundation()
    context = _format_foundation(data)

    system = """You are Saga. You assess positioning with your characteristic
directness, clarity, and focus on the change being offered. You care about:
Is there a real change? Is the worldview clear? Is the smallest viable audience defined?
Are the stories authentic? You praise what works and you're blunt about what doesn't."""

    user = f"""Based only on the data below — extracted from a company's website — assess their
positioning foundation. What's the change they're offering? Is the worldview clear?
Who is their smallest viable audience? What's working? What's missing?

Be Saga. Be direct. Be useful.

{context}"""

    print(generate(system, user))


def cmd_onboarding():
    """Generate the foundational instruction for a new hunter."""
    data = fetch_foundation()
    context = _format_foundation(data, include_profile=True)

    system = """You write foundational training instructions for sales teams at technology
consultancies. The instruction should explain: what change we offer, who we're talking to,
what they believe, and why they're ready. It should be concise, direct, and make a new
team member understand the core of what they're selling — not features, but the transformation.
Write in second person ("you"). No bullet points — flowing prose, 3-4 paragraphs max."""

    user = f"""Based only on the data below — extracted from a company's central intelligence —
write the foundational instruction that a new hunter receives on their first day.
What is the core message about how we see the world?

{context}"""

    print(generate(system, user))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "saga":
        cmd_saga()
    elif cmd == "onboarding":
        cmd_onboarding()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
