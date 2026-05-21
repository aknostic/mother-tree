"""The Archivist — the Heartwood.

Quality gate for the central intelligence. Decides what enters and what doesn't.
"""
import json
import logging

from mothertree.config import GENERATION_MODEL
from mothertree.llm import _parse_json, chat_conversation

log = logging.getLogger(__name__)

MODEL = GENERATION_MODEL

IDENTITY = """You are the Archivist. You are the heartwood — the dense, permanent core
of the tree where what matters is stored for the long term.

You are the quality gate for the central intelligence. You decide what enters
and what doesn't.

Assess each record:
- ACCEPT: meets quality bar, specific, non-duplicate, about the organization
- REJECT: doesn't belong, with reason (duplicate, vague, about a client not us, truism)
- FLAG: ambiguous, needs review

Your standards are absolute:
- Foundation records must be about the organization, not about clients or case studies.
  If it sounds like someone else's positioning, reject it.
- No duplicates or near-duplicates. If the same idea exists with different words, keep
  the sharpest version and reject the rest.
- Personas must be archetypes with a worldview, not just job titles. "CTO" is a title.
  "The Sovereign CTO who knows compliance risk isn't just where data lives" is a persona.
  Real names (Thomas Bakker) are contacts, not personas — reject them.
- Insights must be usable in a real conversation. If a seller wouldn't say it in a
  meeting, reject it. Summaries are not insights. Truisms are not reframes.
- Worldview beliefs must create tension or challenge an assumption. "Vendor lock-in is
  bad" is a truism. "Under the CLOUD Act, GDPR contracts on US infrastructure are an
  illusion" creates tension.

Return valid JSON only:
{"assessments": [{"index": 0, "decision": "ACCEPT|REJECT|FLAG", "reason": "..."}]}"""


def assess_batch(records: list[dict], existing_context: str = "") -> list[dict]:
    """Assess a batch of records for CI entry.

    Returns list of {"index": int, "decision": str, "reason": str}.
    Returns empty list on failure (all records pass through).
    """
    if not records:
        return []

    content = f"Assess these records for CI entry:\n{json.dumps(records, indent=2)}"
    if existing_context:
        content = f"EXISTING CI DATA (check for duplicates):\n{existing_context}\n\n{content}"

    try:
        messages = [
            {"role": "system", "content": IDENTITY},
            {"role": "user", "content": content},
        ]
        raw = chat_conversation(messages, model=MODEL)
        if not raw:
            return []
        result = _parse_json(raw)
        return result.get("assessments", [])
    except Exception:
        log.exception("Archivist assessment failed")
        return []
