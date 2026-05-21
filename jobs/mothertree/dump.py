"""Database dump and restore — snapshot CI state between pipeline stages."""

import json

from mothertree.graphql_client import graphql

# Tables and their GraphQL queries for dumping
DUMP_QUERIES = {
    "change": ("allChangesList", "{ allChangesList { id statement context confidence source } }"),
    "worldview": ("allWorldviewsList", "{ allWorldviewsList { id personaId belief pain readinessSignal confidence source } }"),
    "personas": ("allPersonasList", "{ allPersonasList { id name role profile communication decisionCriteria objections howToReach confidence source } }"),
    "competitors": ("allCompetitorsList", "{ allCompetitorsList { id type positioning whenMentioned response confidence source } }"),
    "insights": ("allInsightsList", "{ allInsightsList { id category reframe evidence stakeholderLens trigger nextStep confidence source flagged } }"),
    "ingestion_log": ("allIngestionLogsList", "{ allIngestionLogsList { source contentHash recordCounts } }"),
    "organization": ("allOrganizationsList", "{ allOrganizationsList { id elementType content confidence sourceCount } }"),
}

# Map camelCase fields back to snake_case for dump compatibility
FIELD_REMAP = {
    "personaId": "persona_id",
    "readinessSignal": "readiness_signal",
    "decisionCriteria": "decision_criteria",
    "howToReach": "how_to_reach",
    "whenMentioned": "when_mentioned",
    "stakeholderLens": "stakeholder_lens",
    "nextStep": "next_step",
    "contentHash": "content_hash",
    "recordCounts": "record_counts",
    "elementType": "element_type",
    "sourceCount": "source_count",
}


def _remap_row(row: dict) -> dict:
    """Convert camelCase keys back to snake_case for dump files."""
    return {FIELD_REMAP.get(k, k): v for k, v in row.items()}

# FK-safe ordering
TRUNCATE_ORDER = ["insights", "worldview", "change", "personas", "competitors", "organization", "ingestion_log"]
RESTORE_ORDER = ["personas", "change", "worldview", "competitors", "insights", "organization", "ingestion_log"]
FK_TARGETS = {"personas"}  # Tables whose IDs are referenced by FKs

# PostGraphile delete/create mutation names per table
TABLE_MUTATIONS = {
    "change": ("allChangesList", "deleteChangeById", "change", "createChange", "Change"),
    "worldview": ("allWorldviewsList", "deleteWorldviewById", "worldview", "createWorldview", "Worldview"),
    "personas": ("allPersonasList", "deletePersonaById", "persona", "createPersona", "Persona"),
    "competitors": ("allCompetitorsList", "deleteCompetitorById", "competitor", "createCompetitor", "Competitor"),
    "insights": ("allInsightsList", "deleteInsightById", "insight", "createInsight", "Insight"),
    "organization": ("allOrganizationsList", "deleteOrganizationById", "organization", "createOrganization", "Organization"),
}

# ingestion_log uses source as PK, not UUID — handled separately

# Map snake_case fields to camelCase for restore mutations
RESTORE_FIELD_REMAP = {
    "persona_id": "personaId",
    "readiness_signal": "readinessSignal",
    "decision_criteria": "decisionCriteria",
    "how_to_reach": "howToReach",
    "when_mentioned": "whenMentioned",
    "stakeholder_lens": "stakeholderLens",
    "next_step": "nextStep",
    "content_hash": "contentHash",
    "record_counts": "recordCounts",
    "element_type": "elementType",
    "source_count": "sourceCount",
}


def _remap_restore_row(row: dict) -> dict:
    """Convert snake_case keys to camelCase for PostGraphile mutations."""
    return {RESTORE_FIELD_REMAP.get(k, k): v for k, v in row.items()}


def dump(output_path: str):
    """Dump all CI tables to a JSON file."""
    data = {}
    for table, (gql_name, query) in DUMP_QUERIES.items():
        try:
            result = graphql(query)
            rows = [_remap_row(r) for r in result.get(gql_name, [])]
            data[table] = rows
            print(f"  {table:20s} {len(rows):>5} records", flush=True)
        except Exception as e:
            print(f"  {table:20s} failed: {e}", flush=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nDumped to {output_path}", flush=True)


def restore(input_path: str):
    """Restore CI tables from a JSON dump file."""
    with open(input_path) as f:
        data = json.load(f)

    # Truncate in FK-safe order — fetch all keys then delete one by one
    for table in TRUNCATE_ORDER:
        if table not in data:
            continue
        try:
            if table == "ingestion_log":
                result = graphql("{ allIngestionLogsList { source } }")
                for row in result.get("allIngestionLogsList", []):
                    graphql("""
mutation($source: String!) {
    deleteIngestionLogBySource(input: {source: $source}) { ingestionLog { source } }
}
""", {"source": row["source"]})
            elif table in TABLE_MUTATIONS:
                query_name, del_mutation, del_result, _, _ = TABLE_MUTATIONS[table]
                ids_result = graphql(f"{{ {query_name} {{ id }} }}")
                for row in ids_result.get(query_name, []):
                    graphql(f"""
mutation($id: UUID!) {{
    {del_mutation}(input: {{id: $id}}) {{ {del_result} {{ id }} }}
}}
""", {"id": row["id"]})
        except Exception:
            pass  # Table may be empty

    # Restore in FK-safe order, preserving IDs for FK targets
    for table in RESTORE_ORDER:
        rows = data.get(table, [])
        if not rows:
            print(f"  {table:20s}     0 restored", flush=True)
            continue

        count = 0
        if table == "ingestion_log":
            for row in rows:
                obj = _remap_restore_row(row)
                try:
                    graphql("""
                    mutation($source: String!, $hash: String!, $counts: JSON!) {
                        upsertIngestionLog(input: {pSource: $source, pHash: $hash, pCounts: $counts}) {
                            ingestionLog { source }
                        }
                    }""", {
                        "source": obj.get("source", ""),
                        "hash": obj.get("contentHash", ""),
                        "counts": json.dumps(obj.get("recordCounts")) if obj.get("recordCounts") else "{}",
                    })
                    count += 1
                except Exception as e:
                    print(f"  {table:20s} insert failed: {e}", flush=True)
        elif table in TABLE_MUTATIONS:
            _, _, _, create_mutation, input_type = TABLE_MUTATIONS[table]
            for row in rows:
                if table in FK_TARGETS:
                    obj = {k: v for k, v in row.items() if v is not None}
                else:
                    obj = {k: v for k, v in row.items() if k != "id" and v is not None}
                obj = _remap_restore_row(obj)
                singular = create_mutation.replace("create", "").lower()
                try:
                    graphql(f"""mutation($object: {input_type}Input!) {{
                        {create_mutation}(input: {{{singular}: $object}}) {{ {singular} {{ id }} }}
                    }}""", {"object": obj})
                    count += 1
                except Exception as e:
                    print(f"  {table:20s} insert failed: {e}", flush=True)
        else:
            print(f"  {table:20s} no mutation mapping", flush=True)
            continue
        print(f"  {table:20s} {count:>5} restored", flush=True)
