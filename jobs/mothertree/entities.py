"""Entity extraction and enrichment from messages.

Finds people, organizations, opportunities, and events in messages
and creates or enriches their records in the central intelligence.
"""

import logging

from mothertree.graphql_client import (
    find_or_create_contact,
    graphql,
)

logger = logging.getLogger("mothertree")


def find_or_create_company(name: str, **kwargs) -> dict:
    """Find a company by name or create it."""
    result = graphql("""
    query($name: String!) {
      allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
    }
    """, {"name": name})
    rows = result.get("allCompaniesList", [])
    if rows:
        return rows[0]

    obj = {"name": name}
    for k in ("industry", "market"):
        if k in kwargs and kwargs[k]:
            obj[k] = kwargs[k]

    result = graphql("""
    mutation($object: CompanyInput!) {
      createCompany(input: {company: $object}) { company { id name } }
    }
    """, {"object": obj})
    logger.info(f"Created company: {name}")
    return result["createCompany"]["company"]


def find_or_create_opportunity(company_id: str, title: str = None, stage: str = "signal", contact_id: str = None) -> dict:
    """Find an active opportunity for a company or create one."""
    result = graphql("""
    query($company_id: UUID!) {
      allOpportunitiesList(
        filter: {companyId: {equalTo: $company_id}, stage: {notEqualTo: "converted"}},
        first: 1,
        orderBy: CREATED_AT_DESC
      ) {
        id stage title
      }
    }
    """, {"company_id": company_id})
    rows = result.get("allOpportunitiesList", [])
    if rows:
        return rows[0]

    obj = {"companyId": company_id, "stage": stage}
    if title:
        obj["title"] = title
    if contact_id:
        obj["contactId"] = contact_id

    result = graphql("""
    mutation($object: OpportunityInput!) {
      createOpportunity(input: {opportunity: $object}) { opportunity { id stage title } }
    }
    """, {"object": obj})
    logger.info(f"Created opportunity for company {company_id}: {title or 'untitled'}")
    return result["createOpportunity"]["opportunity"]


def find_or_create_event(name: str, **kwargs) -> dict:
    """Find an event by name or create it."""
    result = graphql("""
    query($name: String!) {
      allEventsList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
    }
    """, {"name": name})
    rows = result.get("allEventsList", [])
    if rows:
        return rows[0]

    obj = {"name": name}
    for k in ("type", "date", "location", "url"):
        if k in kwargs and kwargs[k]:
            obj[k] = kwargs[k]

    result = graphql("""
    mutation($object: EventInput!) {
      createEvent(input: {event: $object}) { event { id name } }
    }
    """, {"object": obj})
    logger.info(f"Created event: {name}")
    return result["createEvent"]["event"]


def process_entities(entities: list[dict]) -> dict:
    """Process extracted entities — create or enrich in the database.

    Returns a summary of what was created/found.
    """
    summary = {"contacts": [], "companies": [], "opportunities": [], "events": []}

    for entity in entities:
        entity_type = entity.get("type")

        if entity_type == "person":
            contact = find_or_create_contact(
                full_name=entity.get("name", "Unknown"),
                role=entity.get("role"),
            )
            summary["contacts"].append(contact)

            # If they have a company, create/find that too
            if entity.get("company"):
                company = find_or_create_company(entity["company"])
                summary["companies"].append(company)

        elif entity_type == "organization":
            company = find_or_create_company(entity.get("name", "Unknown"))
            summary["companies"].append(company)

            # If it's a prospect, ensure an opportunity exists
            rel = entity.get("relationship", "unknown")
            if rel in ("prospect", "unknown"):
                opp = find_or_create_opportunity(
                    company_id=company["id"],
                    stage_hint=entity.get("stage_hint", "signal"),
                )
                summary["opportunities"].append(opp)

        elif entity_type == "event":
            event = find_or_create_event(
                name=entity.get("name", "Unknown event"),
                type=entity.get("type"),
                date=entity.get("date"),
                location=entity.get("location"),
            )
            summary["events"].append(event)

        elif entity_type == "opportunity":
            if entity.get("company"):
                company = find_or_create_company(entity["company"])
                opp = find_or_create_opportunity(
                    company_id=company["id"],
                    stage=entity.get("stage_hint", "signal"),
                )
                summary["opportunities"].append(opp)

    return summary
