"""Background signal extraction from conversation exchanges."""
import logging

from mothertree.config import EXTRACTION_MODEL
from mothertree.graphql_client import find_similar_signals, insert_signal
from mothertree.llm import extract as llm_extract

log = logging.getLogger(__name__)

ASSESS_PROMPT = """Analyze this conversation exchange and decide:
1. Should this content be saved to the central intelligence? (ci_save: true/false)
2. Does this conversation contain a commercial signal worth capturing? (capture_signal: true/false)

Only say true if there is clear evidence:
- ci_save: user explicitly confirmed saving, or shared content worth preserving
- capture_signal: mentions a prospect, client, market event, competitor, or commercial opportunity

Return JSON only:
{"ci_save": true/false, "capture_signal": true/false}"""


def extract_signal(user_message: str, assistant_response: str, user_name: str,
                   user_id: str = None) -> dict:
    """Extract entities, actions, and qualification from a conversation exchange.

    Uses Spotter → Weaver chain. Falls back to legacy process_entities if Weaver fails.
    Runs in background — must never crash the main flow.
    Returns {"uncertain": [...]} with any entities that need human clarification.
    """
    result = {"uncertain": [], "gaps": []}
    try:
        from bot.characters.spotter import extract as spotter_extract
        from bot.characters.weaver import resolve as weaver_resolve

        # Check for similar past signals before inserting
        similar = find_similar_signals(user_message, limit=3)
        if similar:
            log.info("Similar past signals found: %s",
                     [s.get("content", "")[:80] for s in similar])

        # Insert signal record (with embedding)
        insert_signal(
            source=f"slack:{user_name}",
            content=user_message,
            signal_type="slack",
        )

        # Spotter: extract structured intelligence
        spotter_result = spotter_extract(user_message, assistant_response, user_name)
        if spotter_result is None:
            log.warning("Spotter returned None — skipping entity resolution")
            return result

        entities = spotter_result.get("entities", [])
        actions = spotter_result.get("actions", [])
        log.info("Spotter found %d entities, %d actions", len(entities), len(actions))
        for e in entities:
            log.info("  Entity: %s (%s)", e.get("name", "?"), e.get("type", "?"))

        # Weaver: resolve entities against existing graph
        if entities:
            weaver_result = weaver_resolve(entities)
            if weaver_result is not None:
                log.info("Weaver resolved %d entities", len(weaver_result.get("resolved", [])))
                for item in weaver_result.get("resolved", []):
                    log.info("  %s: %s → %s", item.get("entity", {}).get("name", "?"),
                             item.get("resolution", "?"), item.get("reason", ""))
                resolution = _apply_resolution(weaver_result)
                log.info("Applied resolution: %s", {k: v for k, v in resolution.items() if k != "flags"})
                result["uncertain"] = resolution.get("flags", [])
            else:
                log.warning("Weaver failed — falling back to legacy process_entities")
                _fallback_process_entities(entities)
        else:
            log.info("No entities to resolve")

        # Process actions regardless of Weaver result
        if actions:
            log.info("Processing %d actions", len(actions))
            action_gaps = _process_actions(actions, user_name, user_id=user_id)
            result["gaps"].extend(action_gaps)

        # Collect gaps from entity resolution
        if "resolution" in dir() and hasattr(resolution, "get"):
            result["gaps"].extend(resolution.get("gaps", []))

    except Exception:
        log.exception("Background signal extraction failed")
    return result


# Values that indicate "no date" in LLM output
_NO_DATE_VALUES = frozenset({
    "unknown", "none", "n/a", "tbd", "pending",
    "completed", "past", "unspecified", "immediate",
    "sometime later",
})


def _parse_date(value: str) -> str | None:
    """Parse a freeform date string into ISO format. Returns None if unparseable."""
    from mothertree.dates import resolve_date
    result = resolve_date(value)  # no context = dateparser only, backward compatible
    return result.date if result else None


def _apply_resolution(resolution: dict) -> dict:
    """Apply Weaver resolution results — create NEW, enrich MATCHED, flag UNCERTAIN.

    Handles contacts (person), companies (organization), events, and opportunities.
    MATCHED: already in graph, no action needed.
    UNCERTAIN: flagged, do not create — human review required.
    NEW: create via find_or_create_* helpers.

    Returns summary of what was processed.
    """
    from mothertree.entities import find_or_create_company, find_or_create_event, find_or_create_opportunity
    from mothertree.graphql_client import find_or_create_contact, graphql, search_contacts_fuzzy

    summary = {
        "contacts_processed": 0,
        "companies_processed": 0,
        "gaps": [],
        "events_processed": 0,
        "opportunities_processed": 0,
        "flags": resolution.get("flags", []),
    }

    for item in resolution.get("resolved", []):
        res = item.get("resolution")
        entity = item.get("entity", {})
        entity_type = entity.get("type", "")

        if res != "NEW":
            # MATCHED: already in graph — enrich with any new info
            if res == "MATCHED" and entity_type == "person":
                matched_id = item.get("matched_id")
                if matched_id:
                    updates = {}
                    if entity.get("role"):
                        updates["role"] = entity["role"]
                    org = entity.get("organization") or entity.get("company")
                    if org and org.lower() not in ("unknown", "none", "n/a", ""):
                        try:
                            company = find_or_create_company(org)
                            updates["companyId"] = company.get("id") if isinstance(company, dict) else None
                        except Exception:
                            pass
                    if updates:
                        try:
                            graphql("""
                            mutation($id: UUID!, $patch: ContactPatch!) {
                              updateContactById(input: {id: $id, contactPatch: $patch}) { contact { id } }
                            }
                            """, {"id": matched_id, "patch": updates})
                            log.info("Enriched MATCHED contact %s with %s", entity.get("name"), list(updates.keys()))
                        except Exception:
                            log.warning("Failed to enrich contact %s", entity.get("name"))
            # UNCERTAIN: flagged for human review — collect for clarifying question
            elif res == "UNCERTAIN":
                log.info("Weaver flagged uncertain entity: %s — %s", entity.get("name"), item.get("reason"))
                summary["flags"].append({
                    "entity": entity.get("name", "unknown"),
                    "type": entity_type,
                    "reason": item.get("reason", ""),
                })
            continue

        try:
            log.info("Creating NEW entity: %s (%s)", entity.get("name"), entity_type)
            if entity_type == "person":
                # If person has a company, create it first so we can link
                org = entity.get("organization") or entity.get("company")
                company_id = None
                if org and org.lower() not in ("unknown", "none", "n/a", ""):
                    company = find_or_create_company(org)
                    company_id = company.get("id") if isinstance(company, dict) else None
                    log.info("Company created/found: %s (%s)", org, company_id)
                    summary["companies_processed"] += 1

                # Check for fuzzy name match before creating — avoids duplicates on name variations
                fuzzy = search_contacts_fuzzy(entity.get("name", "Unknown"), company_id=company_id)
                if fuzzy:
                    log.info("Fuzzy match found for %s → %s", entity.get("name"), fuzzy.get("name"))
                    contact = fuzzy
                else:
                    contact = find_or_create_contact(
                        full_name=entity.get("name", "Unknown"),
                        role=entity.get("role"),
                        company_id=company_id,
                    )
                log.info("Contact created/found: %s (company: %s)", contact.get("id"), company_id)
                summary["contacts_processed"] += 1

            elif entity_type == "organization":
                company = find_or_create_company(entity.get("name", "Unknown"))
                log.info("Company created/found: %s", company.get("id") if isinstance(company, dict) else company)
                summary["companies_processed"] += 1

            elif entity_type == "event":
                raw_date = entity.get("date", "")
                parsed_date = _parse_date(raw_date)
                if raw_date and not parsed_date:
                    summary["gaps"].append(f"when '{entity.get('name', 'this event')}' happens (couldn't parse '{raw_date}')")
                find_or_create_event(
                    name=entity.get("name", "Unknown event"),
                    type=entity.get("event_type"),
                    date=parsed_date,
                    location=entity.get("location"),
                    url=entity.get("url"),
                )
                summary["events_processed"] += 1

            elif entity_type == "opportunity":
                org = entity.get("organization") or entity.get("company")
                if org:
                    company = find_or_create_company(org)
                    find_or_create_opportunity(
                        company_id=company["id"],
                        stage=entity.get("stage", "signal"),
                    )
                    summary["opportunities_processed"] += 1

        except Exception:
            log.exception("Failed to apply resolution for entity: %s", entity.get("name"))

    return summary


def _fallback_process_entities(entities: list[dict]) -> None:
    """Legacy entity processing — used when Weaver fails."""
    try:
        from mothertree.entities import process_entities
        process_entities(entities)
    except Exception:
        log.exception("Fallback entity processing failed")


def _process_actions(actions: list[dict], user_name: str, user_id: str = None) -> list[dict]:
    """Process extracted actions — create interaction records.

    Returns a list of gaps (missing info) that should be clarified conversationally.
    """
    gaps = []
    try:
        from mothertree.graphql_client import find_or_create_contact, graphql
        for action in actions:
            if not isinstance(action, dict):
                continue
            summary = action.get("action") or action.get("what")
            if not summary:
                continue
            # Find or create a contact for this action
            contact_name = action.get("who") or action.get("person") or user_name
            contact = find_or_create_contact(full_name=contact_name)

            # Parse date — flag if unparseable
            raw_date = action.get("by_when") or action.get("date") or ""
            parsed_date = _parse_date(raw_date)
            if raw_date and not parsed_date:
                gaps.append(f"when '{summary}' should happen (couldn't parse '{raw_date}')")

            interaction_obj = {
                "type": "slack",
                "contactId": contact["id"],
                "summary": summary,
                "nextAction": summary,
                "nextActionDate": parsed_date,
                "sourceRole": "hunter",
            }
            if user_id:
                interaction_obj["userId"] = user_id
            graphql("""
            mutation($obj: InteractionInput!) {
                createInteraction(input: {interaction: $obj}) { interaction { id } }
            }
            """, {"obj": interaction_obj})
    except Exception:
        log.exception("Action processing failed")
    return gaps


def _assess_via_llm(user_message: str, assistant_response: str) -> dict:
    """Call LLM to independently assess whether actions should fire."""
    content = f"User: {user_message}\nAssistant: {assistant_response}"
    return llm_extract(content, ASSESS_PROMPT, model=EXTRACTION_MODEL)


def assess_actions(user_message: str, assistant_response: str) -> dict:
    """Dual-path safety net: independently assess whether actions should fire.

    Called from pipeline when action markers are present (to verify) and
    when absent (to catch missed ones).
    """
    try:
        return _assess_via_llm(user_message, assistant_response)
    except Exception:
        log.exception("Action assessment failed")
        return {"ci_save": False, "capture_signal": False}
