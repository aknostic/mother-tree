"""PostGraphile GraphQL client — shared across all Mother Tree components.

Migrated from Hasura on 2026-04-02. All queries use PostGraphile syntax.
Postgres functions handle JSONB appends, upserts, and semantic search.
"""

import json
import logging
import unicodedata
from datetime import UTC

import httpx

from mothertree.config import HASURA_ADMIN_SECRET, HASURA_URL

log = logging.getLogger(__name__)


def _headers():
    return {
        "Content-Type": "application/json",
        "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
    }


def graphql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = httpx.post(HASURA_URL, json=payload, headers=_headers(), timeout=60)
    if resp.status_code >= 400:
        # PostGraphile returns the real error in the body even on 4xx.
        # Surface it instead of letting raise_for_status() throw it away.
        body_repr = resp.text[:1000]
        try:
            errors = resp.json().get("errors")
            if errors:
                body_repr = json.dumps(errors)
        except ValueError:
            pass
        raise RuntimeError(f"GraphQL HTTP {resp.status_code}: {body_repr}")
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


# --- Ingestion ---

def check_ingestion_log(source: str, content_hash: str) -> bool:
    result = graphql("""
    query($source: String!) {
      ingestionLogBySource(source: $source) { contentHash }
    }
    """, {"source": source})
    existing = result.get("ingestionLogBySource")
    return existing and existing["contentHash"] == content_hash


def update_ingestion_log(source: str, content_hash: str, record_counts: dict):
    graphql("""
    mutation($source: String!, $hash: String!, $counts: JSON!) {
      upsertIngestionLog(input: {pSource: $source, pHash: $hash, pCounts: $counts}) {
        ingestionLog { source }
      }
    }
    """, {"source": source, "hash": content_hash, "counts": json.dumps(record_counts)})


def delete_by_source(table: str, source: str):
    result = graphql("""
    mutation($table: String!, $source: String!) {
      deleteBySourceFn(input: {pTable: $table, pSource: $source}) { integer }
    }
    """, {"table": table, "source": source})
    return result["deleteBySourceFn"]["integer"]


_DEDUP_FIELD = {
    "change": "statement",
    "worldview": "belief",
    "personas": "name",
    "competitors": "whenMentioned",
    "insights": "title",
}

# PostGraphile mutation names: createChange, createWorldview, createPersona, etc.
_PG_CREATE_NAMES = {
    "change": ("createChange", "change"),
    "worldview": ("createWorldview", "worldview"),
    "personas": ("createPersona", "persona"),
    "competitors": ("createCompetitor", "competitor"),
    "insights": ("createInsight", "insight"),
    "proof_points": ("createProofPoint", "proofPoint"),
    "signals": ("createSignal", "signal"),
    "organization": ("createOrganization", "organization"),
}

# PostGraphile list query names
_PG_LIST_NAMES = {
    "change": "allChangesList",
    "worldview": "allWorldviewsList",
    "personas": "allPersonasList",
    "competitors": "allCompetitorsList",
    "insights": "allInsightsList",
    "proof_points": "allProofPointsList",
    "signals": "allSignalsList",
    "organization": "allOrganizationsList",
}

# PostGraphile input type names
_PG_INPUT_NAMES = {
    "change": "ChangeInput",
    "worldview": "WorldviewInput",
    "personas": "PersonaInput",
    "competitors": "CompetitorInput",
    "insights": "InsightInput",
    "proof_points": "ProofPointInput",
    "signals": "SignalInput",
    "organization": "OrganizationInput",
}

_EMBEDDABLE_TABLES = {"insights", "organization", "change", "worldview", "personas", "competitors", "signals", "proof_points"}


def _to_camel(snake: str) -> str:
    """Convert snake_case to camelCase for PostGraphile."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _camel_keys(obj: dict) -> dict:
    """Convert all dict keys from snake_case to camelCase."""
    return {_to_camel(k): v for k, v in obj.items()}


def _insert_record(table: str, obj: dict) -> str:
    """Generic insert via PostGraphile createX mutation.
    Skips insert if a record with the same dedup field value already exists.
    Generates embedding for tables that support it."""
    clean = {k: v for k, v in obj.items() if v is not None}

    # Dedup check
    field = _DEDUP_FIELD.get(table)
    if field and field in clean:
        camel_field = _to_camel(field) if "_" in field else field
        list_name = _PG_LIST_NAMES[table]
        existing = graphql(
            f'query($val: String!) {{ {list_name}(condition: {{{camel_field}: $val}}, first: 1) {{ id }} }}',
            {"val": clean[field]},
        )
        if existing.get(list_name):
            return existing[list_name][0]["id"]

    # Insert
    create_name, result_field = _PG_CREATE_NAMES[table]
    input_name = _PG_INPUT_NAMES[table]
    camel_obj = _camel_keys(clean)
    result = graphql(
        f"mutation($obj: {input_name}!) {{ {create_name}(input: {{{result_field}: $obj}}) {{ {result_field} {{ id }} }} }}",
        {"obj": camel_obj},
    )
    record_id = result[create_name][result_field]["id"]

    # Generate embedding
    if table in _EMBEDDABLE_TABLES:
        try:
            embed_record(table, record_id, clean)
        except Exception:
            log.warning("Embedding failed for %s/%s", table, record_id)

    return record_id


def insert_change(obj: dict) -> str:
    return _insert_record("change", obj)


def insert_worldview(obj: dict) -> str:
    return _insert_record("worldview", obj)


def insert_persona(obj: dict) -> str:
    return _insert_record("personas", obj)


def insert_competitor(obj: dict) -> str:
    return _insert_record("competitors", obj)


def insert_proof_point(obj: dict) -> str:
    return _insert_record("proof_points", obj)


def insert_insight(obj: dict) -> str:
    return _insert_record("insights", obj)


# --- Embeddings and semantic search ---

def _embed_text_for_record(table: str, record: dict) -> str:
    """Build a text representation of a record for embedding."""
    if table == "insights":
        parts = [record.get("category", ""), record.get("reframe", "")]
        if record.get("evidence"):
            parts.append(record["evidence"])
        if record.get("trigger"):
            parts.append(record["trigger"])
        return " — ".join(p for p in parts if p)
    elif table == "change":
        return f"{record.get('statement', '')} {record.get('context', '')}".strip()
    elif table == "worldview":
        return f"{record.get('belief', '')} {record.get('pain', '')}".strip()
    elif table == "personas":
        parts = [record.get('name', ''), record.get('role', ''), record.get('profile', ''),
                 record.get('fears', ''), record.get('motivation', '')]
        return " ".join(p for p in parts if p).strip()
    elif table == "competitors":
        return f"{record.get('type', '')} {record.get('positioning', '')} {record.get('when_mentioned', '')}".strip()
    elif table == "organization":
        return record.get("content", "")
    elif table == "signals":
        return f"{record.get('content', '')} {record.get('source', '')}".strip()
    elif table == "proof_points":
        return f"{record.get('client', '')} {record.get('outcome', '')} {record.get('relevance', '')}".strip()
    return str(record)


_VECTOR_TABLES = {"insights", "organization", "change", "worldview", "personas", "competitors", "signals", "proof_points"}


def store_embedding(table: str, record_id: str, embedding: list[float]) -> None:
    """Store an embedding vector via Postgres function."""
    if table not in _VECTOR_TABLES:
        raise ValueError(f"Table {table} does not support embeddings")
    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
    graphql("""
    mutation($table: String!, $id: UUID!, $emb: String!) {
      storeEmbeddingFn(input: {pTable: $table, pId: $id, pEmbedding: $emb}) { clientMutationId }
    }
    """, {"table": table, "id": record_id, "emb": vec_str})


def embed_record(table: str, record_id: str, record: dict) -> None:
    """Generate and store an embedding for a record."""
    from mothertree.llm import embed
    text = _embed_text_for_record(table, record)
    if not text:
        return
    vector = embed(text)
    store_embedding(table, record_id, vector)


# PostGraphile search function names
_SEARCH_FN_NAMES = {
    "insights": "searchSimilarInsightsList",
    "change": "searchSimilarChangeList",
    "worldview": "searchSimilarWorldviewList",
    "personas": "searchSimilarPersonasList",
    "competitors": "searchSimilarCompetitorsList",
    "organization": "searchSimilarOrganizationList",
    "signals": "searchSimilarSignalsList",
    "proof_points": "searchSimilarProofPointsList",
}


def search_similar(table: str, query: str, limit: int = 10, threshold: float = 0.3) -> list[dict]:
    """Find records similar to a query using pgvector via Postgres function."""
    if table not in _SEARCH_FN_NAMES:
        raise ValueError(f"Table {table} does not support semantic search")
    from mothertree.llm import embed
    query_vec = embed(query)
    vec_str = "[" + ",".join(str(f) for f in query_vec) + "]"
    fn_name = _SEARCH_FN_NAMES[table]
    result = graphql(f"""
    query($emb: String!, $limit: Int!, $threshold: Float!) {{
      {fn_name}(queryEmbedding: $emb, maxResults: $limit, minThreshold: $threshold) {{
        id similarity
        {"category reframe evidence trigger confidence" if table == "insights"
         else "statement context confidence" if table == "change"
         else "belief pain confidence" if table == "worldview"
         else "name role profile confidence" if table == "personas"
         else "type positioning whenMentioned confidence" if table == "competitors"
         else "elementType content confidence" if table == "organization"
         else "source content createdAt" if table == "signals"
         else "client outcome duration relevance confidence" if table == "proof_points"
         else ""}
      }}
    }}
    """, {"emb": vec_str, "limit": limit, "threshold": threshold})
    rows = result.get(fn_name, [])
    # Convert camelCase back to snake_case for Python consumers
    return [_snake_keys(r) for r in rows]


def _snake_keys(obj: dict) -> dict:
    """Convert camelCase keys back to snake_case."""
    import re
    def to_snake(s):
        return re.sub(r'(?<=[a-z])(?=[A-Z])', '_', s).lower()
    return {to_snake(k): v for k, v in obj.items()}


def get_persona_id_by_name(name: str) -> str | None:
    result = graphql("""
    query($name: String!) {
      allPersonasList(filter: {name: {includesInsensitive: $name}}, first: 1) { id }
    }
    """, {"name": name})
    rows = result.get("allPersonasList", [])
    return rows[0]["id"] if rows else None


# --- Signals ---

def insert_signal(source: str, content: str, signal_type: str = "slack") -> str:
    result = graphql("""
    mutation($obj: SignalInput!) {
      createSignal(input: {signal: $obj}) { signal { id } }
    }
    """, {"obj": {"source": source, "content": content, "type": signal_type, "status": "new"}})
    signal_id = result["createSignal"]["signal"]["id"]
    try:
        embed_record("signals", signal_id, {"content": content, "source": source})
    except Exception:
        log.warning("Embedding failed for signal/%s", signal_id)
    return signal_id


def find_similar_signals(content: str, limit: int = 5) -> list[dict]:
    try:
        return search_similar("signals", content, limit=limit, threshold=0.3)
    except Exception:
        return []


# --- Signal threads ---

def create_signal_thread(signal_id: str, slack_thread_ts: str, slack_channel: str, messages: list, enrichment: dict = None) -> str:
    result = graphql("""
    mutation($obj: SignalThreadInput!) {
      createSignalThread(input: {signalThread: $obj}) { signalThread { id } }
    }
    """, {"obj": {
        "signalId": signal_id,
        "slackThreadTs": slack_thread_ts,
        "slackChannel": slack_channel,
        "messages": json.dumps(messages),
        "enrichment": json.dumps(enrichment) if enrichment else None,
        "status": "active",
    }})
    return result["createSignalThread"]["signalThread"]["id"]


def update_signal_thread(slack_thread_ts: str, messages: list, status: str = None):
    patch = {"messages": json.dumps(messages)}
    if status:
        patch["status"] = status
    graphql("""
    mutation($ts: String!, $patch: SignalThreadPatch!) {
      updateSignalThreadBySlackThreadTs(input: {slackThreadTs: $ts, signalThreadPatch: $patch}) {
        signalThread { id }
      }
    }
    """, {"ts": slack_thread_ts, "patch": patch})


def get_signal_thread(slack_thread_ts: str) -> dict | None:
    result = graphql("""
    query($ts: String!) {
      signalThreadBySlackThreadTs(slackThreadTs: $ts) {
        id signalId messages enrichment status
      }
    }
    """, {"ts": slack_thread_ts})
    row = result.get("signalThreadBySlackThreadTs")
    if row:
        return _snake_keys(row)
    return None


def get_active_threads_due_reminder() -> list[dict]:
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    result = graphql("""
    query($now: Datetime!) {
      allSignalThreadsList(filter: {
        status: {equalTo: "active"},
        remindAfter: {lessThanOrEqualTo: $now}
      }) {
        id signalId slackThreadTs slackChannel messages remindContext
      }
    }
    """, {"now": now})
    return [_snake_keys(r) for r in result.get("allSignalThreadsList", [])]


# --- Contacts ---

def find_or_create_contact(full_name: str, first_name: str = None, user_id: str = None, owner_user_id: str = None, is_team: bool = False, **kwargs) -> dict:
    result = graphql("""
    query($name: String!) {
      allContactsList(filter: {or: [{fullName: {includesInsensitive: $name}}, {name: {includesInsensitive: $name}}]}, first: 1) {
        id firstName fullName
      }
    }
    """, {"name": full_name})
    rows = result.get("allContactsList", [])
    if rows:
        return _snake_keys(rows[0])

    if not first_name:
        first_name = full_name.split()[0] if full_name else "?"

    obj = {
        "name": full_name,
        "fullName": full_name,
        "firstName": first_name,
        "isTeamMember": is_team,
    }
    if user_id:
        obj["userId"] = user_id
    if owner_user_id:
        obj["ownerUserId"] = owner_user_id
    camel_map = {"role": "role", "company_id": "companyId", "linkedin": "linkedin", "email": "email"}
    for k, ck in camel_map.items():
        if k in kwargs and kwargs[k]:
            obj[ck] = kwargs[k]

    result = graphql("""
    mutation($obj: ContactInput!) {
      createContact(input: {contact: $obj}) { contact { id firstName fullName } }
    }
    """, {"obj": obj})
    return _snake_keys(result["createContact"]["contact"])


def _normalize_name(name: str) -> str:
    """Normalize name for fuzzy matching: lowercase, strip diacritics."""
    normalized = unicodedata.normalize("NFD", name.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def search_contacts_fuzzy(name: str, company_id: str = None) -> dict | None:
    """Find an existing contact by fuzzy name match.

    Rules:
    - Exact match (normalized) always matches
    - Substring match requires name >= 4 chars AND same company
    - Returns the best match or None
    """
    normalized = _normalize_name(name)
    if company_id:
        result = graphql("""
        query($companyId: UUID!) {
            allContactsList(filter: {companyId: {equalTo: $companyId}}) {
                id name companyByCompanyId { id }
            }
        }
        """, {"companyId": company_id})
    else:
        result = graphql("""
        query { allContactsList { id name companyByCompanyId { id } } }
        """)

    contacts = result.get("allContactsList", [])
    for contact in contacts:
        existing_normalized = _normalize_name(contact["name"])
        if normalized == existing_normalized:
            return contact
        if len(normalized) >= 4 and company_id:
            if normalized in existing_normalized or existing_normalized in normalized:
                return contact
    return None


# --- Training ---

def fetch_foundation_for_chapter(chapter: int = None, tables: list[str] = None,
                                 query: str = None) -> dict:
    TABLE_QUERIES = {
        "change": "allChangesList(first: 15, orderBy: CONFIDENCE_DESC) { statement context }",
        "worldview": "allWorldviewsList(first: 15, orderBy: CONFIDENCE_DESC) { belief pain readinessSignal }",
        "personas": "allPersonasList(first: 10) { name role profile communication decisionCriteria }",
        "competitors": "allCompetitorsList(first: 15) { type positioning whenMentioned response }",
        "insights": "allInsightsList(first: 10, orderBy: CONFIDENCE_DESC) { category reframe evidence }",
    }

    # Map PostGraphile result keys back to snake_case table names
    TABLE_RESULT_KEYS = {
        "change": "allChangesList",
        "worldview": "allWorldviewsList",
        "personas": "allPersonasList",
        "competitors": "allCompetitorsList",
        "insights": "allInsightsList",
    }

    if tables is None:
        chapter_tables = {
            0: ["change"], 1: ["worldview", "personas"],
            2: ["personas"], 3: ["competitors"], 4: ["change"],
        }
        tables = chapter_tables.get(chapter, ["change"])

    # Semantic search when query is provided
    if query:
        try:
            result = {}
            for t in tables:
                if t not in TABLE_QUERIES:
                    continue
                similar = search_similar(t, query, limit=10, threshold=0.05)
                if similar:
                    result[t] = similar
            if result:
                return result
        except Exception:
            pass

    # Fallback: top-N by confidence
    query_parts = [TABLE_QUERIES[t] for t in tables if t in TABLE_QUERIES]
    if not query_parts:
        return {}
    raw = graphql(f"query {{ {' '.join(query_parts)} }}")
    # Remap keys from PostGraphile names to table names
    result = {}
    for t in tables:
        key = TABLE_RESULT_KEYS.get(t)
        if key and key in raw:
            result[t] = [_snake_keys(r) for r in raw[key]]
    return result


def insert_exercise(user_id: str, stage: int, chapter: int,
                    exercise_type: str, content: dict, source_tables: list) -> str:
    result = graphql("""
    mutation($obj: ExerciseInput!) {
      createExercise(input: {exercise: $obj}) { exercise { id } }
    }
    """, {"obj": {
        "userId": user_id, "stage": stage, "chapter": chapter,
        "exerciseType": exercise_type, "content": content,
        "sourceTables": source_tables,
    }})
    return result["createExercise"]["exercise"]["id"]


def insert_response(exercise_id: str, user_id: str, response: str,
                    question_index: int, correct: bool, feedback: str) -> str:
    result = graphql("""
    mutation($obj: ResponseInput!) {
      createResponse(input: {response: $obj}) { response { id } }
    }
    """, {"obj": {
        "exerciseId": exercise_id, "userId": user_id,
        "response": response, "questionIndex": question_index,
        "correct": correct, "feedback": feedback,
    }})
    return result["createResponse"]["response"]["id"]


def create_conversation(user_id: str, exercise_id: str,
                        stage: int, state: str,
                        current_question: int = -1) -> str:
    result = graphql("""
    mutation($obj: ConversationInput!) {
      createConversation(input: {conversation: $obj}) { conversation { id } }
    }
    """, {"obj": {
        "userId": user_id, "exerciseId": exercise_id,
        "stage": stage, "state": state,
        "currentQuestion": current_question,
    }})
    return result["createConversation"]["conversation"]["id"]


def get_active_conversation(user_id: str) -> dict | None:
    result = graphql("""
    query($uid: UUID!) {
      allConversationsList(
        condition: {userId: $uid, state: "waiting_response"},
        orderBy: CREATED_AT_DESC,
        first: 1
      ) {
        id state currentQuestion exerciseId stage
        exerciseByExerciseId { content }
      }
    }
    """, {"uid": user_id})
    convs = result["allConversationsList"]
    if not convs:
        return None
    c = convs[0]
    # Remap to match expected structure
    return {
        "id": c["id"],
        "state": c["state"],
        "current_question": c["currentQuestion"],
        "exercise_id": c["exerciseId"],
        "stage": c["stage"],
        "exercise": c.get("exerciseByExerciseId"),
    }


def update_conversation(conversation_id: str, **kwargs) -> None:
    patch = _camel_keys(kwargs)
    graphql("""
    mutation($id: UUID!, $patch: ConversationPatch!) {
      updateConversationById(input: {id: $id, conversationPatch: $patch}) {
        conversation { id }
      }
    }
    """, {"id": conversation_id, "patch": patch})


def cancel_stale_conversations(user_id: str) -> int:
    # PostGraphile doesn't support bulk conditional updates natively.
    # Fetch active conversations then update each one.
    result = graphql("""
    query($uid: UUID!) {
      allConversationsList(filter: {
        userId: {equalTo: $uid},
        state: {notEqualTo: "complete"},
        stage: {notEqualTo: -1}
      }) { id }
    }
    """, {"uid": user_id})
    convs = result.get("allConversationsList", [])
    for c in convs:
        update_conversation(c["id"], state="complete")
    return len(convs)


def advance_user(user_id: str, current_chapter: int = None,
                 current_stage: int = None) -> None:
    patch = {}
    if current_chapter is not None:
        patch["currentChapter"] = current_chapter
    if current_stage is not None:
        patch["currentStage"] = current_stage
    graphql("""
    mutation($id: UUID!, $patch: UserPatch!) {
      updateUserById(input: {id: $id, userPatch: $patch}) {
        user { id }
      }
    }
    """, {"id": user_id, "patch": patch})


def upsert_training_progress(user_id: str, area: str, score: float, **kwargs) -> None:
    last_refresher = kwargs.get("last_refresher")
    graphql("""
    mutation($uid: UUID!, $area: String!, $score: Float!, $lr: Datetime) {
      upsertTrainingProgressFn(input: {pUserId: $uid, pArea: $area, pScore: $score, pLastRefresher: $lr}) {
        trainingProgress { id }
      }
    }
    """, {"uid": user_id, "area": area, "score": score, "lr": last_refresher})


def get_training_progress(user_id: str) -> list[dict]:
    result = graphql("""
    query($uid: UUID!) {
      allTrainingProgressesList(condition: {userId: $uid}) {
        area score lastRefresher exercisesCompleted updatedAt
      }
    }
    """, {"uid": user_id})
    return [_snake_keys(r) for r in result["allTrainingProgressesList"]]


def get_responses_for_exercise(exercise_id: str) -> list[dict]:
    result = graphql("""
    query($eid: UUID!) {
      allResponsesList(condition: {exerciseId: $eid}) {
        correct questionIndex
      }
    }
    """, {"eid": exercise_id})
    return [_snake_keys(r) for r in result["allResponsesList"]]


def update_streak(user_id: str, streak: int) -> None:
    graphql("""
    mutation($id: UUID!, $patch: UserPatch!) {
      updateUserById(input: {id: $id, userPatch: $patch}) {
        user { id }
      }
    }
    """, {"id": user_id, "patch": {"streak": streak, "lastActivity": "now()"}})


# --- DM Conversations ---

def get_or_create_dm_conversation(user_id: str) -> dict:
    result = graphql("""
    query($uid: UUID!) {
      allConversationsList(
        filter: {userId: {equalTo: $uid}, stage: {equalTo: -1}},
        first: 1
      ) { id stage state messages }
    }
    """, {"uid": user_id})
    convs = result["allConversationsList"]
    if convs:
        return _snake_keys(convs[0])

    result = graphql("""
    mutation($obj: ConversationInput!) {
      createConversation(input: {conversation: $obj}) { conversation { id } }
    }
    """, {"obj": {
        "userId": user_id,
        "stage": -1,
        "state": "active",
        "messages": [],
        "currentQuestion": -1,
    }})
    return {
        "id": result["createConversation"]["conversation"]["id"],
        "stage": -1,
        "state": "active",
        "messages": [],
    }


def append_dm_message(conversation_id: str, role: str, content: str) -> None:
    from datetime import datetime
    ts = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: UUID!, $msg: JSON!) {
      appendConversationMessage(input: {pConversationId: $id, pMessage: $msg}) {
        conversation { id }
      }
    }
    """, {"id": conversation_id, "msg": {"role": role, "content": content, "ts": ts}})


def set_pending_ci_save(conversation_id: str, url: str) -> None:
    from datetime import datetime
    ts = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: UUID!, $msg: JSON!) {
      appendConversationMessage(input: {pConversationId: $id, pMessage: $msg}) {
        conversation { id }
      }
    }
    """, {"id": conversation_id, "msg": {
        "role": "system", "content": "pending_ci_save", "url": url, "ts": ts,
    }})


# --- Channel memory ---

def get_or_create_channel_memory(channel_id: str, channel_name: str = None) -> dict:
    result = graphql("""
    query($cid: String!) {
      channelMemoryByChannelId(channelId: $cid) { id channelId channelName messages }
    }
    """, {"cid": channel_id})
    row = result.get("channelMemoryByChannelId")
    if row:
        return _snake_keys(row)
    result = graphql("""
    mutation($obj: ChannelMemoryInput!) {
      createChannelMemory(input: {channelMemory: $obj}) {
        channelMemory { id channelId channelName messages }
      }
    }
    """, {"obj": {"channelId": channel_id, "channelName": channel_name}})
    return _snake_keys(result["createChannelMemory"]["channelMemory"])


def append_channel_message(channel_id: str, role: str, content: str, name: str = None) -> None:
    from datetime import datetime
    msg = {"role": role, "content": content, "ts": datetime.now(UTC).isoformat()}
    if name:
        msg["name"] = name
    graphql("""
    mutation($cid: String!, $msg: JSON!) {
      appendChannelMessage(input: {pChannelId: $cid, pMessage: $msg}) {
        channelMemory { id }
      }
    }
    """, {"cid": channel_id, "msg": msg})


def cap_channel_memory(memory_id: int, messages: list, max_messages: int = 200) -> None:
    if len(messages) <= max_messages:
        return
    trimmed = messages[-max_messages:]
    graphql("""
    mutation($id: Int!, $patch: ChannelMemoryPatch!) {
      updateChannelMemoryById(input: {id: $id, channelMemoryPatch: $patch}) {
        channelMemory { id }
      }
    }
    """, {"id": memory_id, "patch": {"messages": trimmed}})


# --- Thread memory ---

def get_or_create_thread_memory(thread_ts: str, channel_id: str, owner_user_id: str = None) -> dict:
    result = graphql("""
    query($ts: String!) {
      threadMemoryByThreadTs(threadTs: $ts) {
        id threadTs channelId messages remindAfter remindContext ownerUserId
      }
    }
    """, {"ts": thread_ts})
    row = result.get("threadMemoryByThreadTs")
    if row:
        if owner_user_id and not row.get("ownerUserId"):
            graphql("""
            mutation($id: Int!, $owner: UUID!) {
                updateThreadMemoryById(input: {
                    id: $id,
                    threadMemoryPatch: {ownerUserId: $owner}
                }) { threadMemory { id } }
            }
            """, {"id": row["id"], "owner": owner_user_id})
        return _snake_keys(row)
    obj = {"threadTs": thread_ts, "channelId": channel_id}
    if owner_user_id:
        obj["ownerUserId"] = owner_user_id
    result = graphql("""
    mutation($obj: ThreadMemoryInput!) {
      createThreadMemory(input: {threadMemory: $obj}) {
        threadMemory { id threadTs channelId messages remindAfter remindContext ownerUserId }
      }
    }
    """, {"obj": obj})
    return _snake_keys(result.get("createThreadMemory", {}).get("threadMemory", {}))


def append_thread_message(thread_ts: str, channel_id: str, role: str, content: str, name: str = None) -> None:
    from datetime import datetime
    get_or_create_thread_memory(thread_ts, channel_id)
    msg = {"role": role, "content": content, "ts": datetime.now(UTC).isoformat()}
    if name:
        msg["name"] = name
    graphql("""
    mutation($ts: String!, $cid: String!, $msg: JSON!) {
      appendThreadMessageFn(input: {pThreadTs: $ts, pChannelId: $cid, pMessage: $msg}) {
        threadMemory { id }
      }
    }
    """, {"ts": thread_ts, "cid": channel_id, "msg": msg})


# --- Organization profile ---

def get_organization_profile() -> list[dict]:
    result = graphql("""
    query {
      allOrganizationsList(orderBy: [ELEMENT_TYPE_ASC, CONFIDENCE_DESC]) {
        id elementType content confidence sourceCount
      }
    }
    """)
    return [_snake_keys(r) for r in result["allOrganizationsList"]]


def insert_organization_element(element: dict) -> str:
    clean = {k: v for k, v in element.items() if v is not None}
    camel = _camel_keys(clean)
    result = graphql("""
    mutation($obj: OrganizationInput!) {
      createOrganization(input: {organization: $obj}) { organization { id } }
    }
    """, {"obj": camel})
    record_id = result["createOrganization"]["organization"]["id"]
    try:
        embed_record("organization", record_id, clean)
    except Exception:
        log.warning("Embedding failed for organization/%s", record_id)
    return record_id


def delete_all_organization() -> int:
    # Fetch all IDs then delete one by one (PostGraphile has no bulk delete-all)
    result = graphql("{ allOrganizationsList { id } }")
    ids = [r["id"] for r in result.get("allOrganizationsList", [])]
    for oid in ids:
        graphql("""
mutation($id: UUID!) {
    deleteOrganizationById(input: {id: $id}) { organization { id } }
}
""", {"id": oid})
    return len(ids)


def update_organization_element(element_id: str, updates: dict) -> None:
    patch = _camel_keys(updates)
    graphql("""
    mutation($id: UUID!, $patch: OrganizationPatch!) {
      updateOrganizationById(input: {id: $id, organizationPatch: $patch}) {
        organization { id }
      }
    }
    """, {"id": element_id, "patch": patch})


def get_thread_memory_or_signal_thread(thread_ts: str, channel_id: str) -> dict | None:
    result = graphql("""
    query($ts: String!) {
      threadMemoryByThreadTs(threadTs: $ts) {
        id threadTs channelId messages remindAfter remindContext
      }
    }
    """, {"ts": thread_ts})
    row = result.get("threadMemoryByThreadTs")
    if row:
        return _snake_keys(row)
    # Fallback: legacy signal_threads
    result = graphql("""
    query($ts: String!) {
      signalThreadBySlackThreadTs(slackThreadTs: $ts) {
        id messages enrichment status
      }
    }
    """, {"ts": thread_ts})
    st = result.get("signalThreadBySlackThreadTs")
    if st:
        messages = st["messages"] if isinstance(st["messages"], list) else json.loads(st["messages"])
        return {"thread_ts": thread_ts, "channel_id": channel_id, "messages": messages, "_legacy": True}


# --- Pulse scans ---

def get_due_reminders() -> list[dict]:
    """Get thread memories where remind_after has passed."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    result = graphql("""
    query($now: Datetime!) {
        allThreadMemoriesList(filter: {remindAfter: {lessThanOrEqualTo: $now}}) {
            id threadTs channelId messages remindAfter remindContext
            ownerUserId pulseNudgedAt
        }
    }
    """, {"now": now})
    return result.get("allThreadMemoriesList", [])


def get_stale_threads(days: int = 21) -> list[dict]:
    """Get thread memories not updated in `days` days, excluding scheduled reminders."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    result = graphql("""
    query($cutoff: Datetime!) {
        allThreadMemoriesList(filter: {
            updatedAt: {lessThan: $cutoff},
            remindAfter: {isNull: true}
        }) {
            id threadTs channelId ownerUserId updatedAt pulseNudgedAt
        }
    }
    """, {"cutoff": cutoff})
    return result.get("allThreadMemoriesList", [])


def get_stale_contacts_for_pulse() -> list[dict]:
    """Get warm/hot contacts past their temperature threshold."""
    result = graphql("""
    query {
        allContactsList(filter: {
            temperature: {in: ["hot", "warm"]}
        }) {
            id name role temperature lastContact ownerUserId pulseNudgedAt
            companyByCompanyId { name }
        }
    }
    """)
    return result.get("allContactsList", [])


def get_stale_opportunities() -> list[dict]:
    """Get opportunities for pipeline nudges."""
    result = graphql("""
    query {
        allOpportunitiesList(filter: {
            stage: {notEqualTo: "converted"}
        }) {
            id title stage ownerUserId updatedAt pulseNudgedAt notes
            companyByCompanyId { name }
            contactByContactId { name role }
        }
    }
    """)
    return result.get("allOpportunitiesList", [])


def mark_thread_pulse_nudged(thread_memory_id: int) -> None:
    """Set pulse_nudged_at to now on a thread_memory record."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: Int!, $now: Datetime!) {
        updateThreadMemoryById(input: {
            id: $id,
            threadMemoryPatch: {pulseNudgedAt: $now}
        }) { threadMemory { id } }
    }
    """, {"id": thread_memory_id, "now": now})


def clear_thread_remind_after(thread_memory_id: int) -> None:
    """Clear remind_after after a one-shot reminder fires."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: Int!, $now: Datetime!) {
        updateThreadMemoryById(input: {
            id: $id,
            threadMemoryPatch: {remindAfter: null, pulseNudgedAt: $now}
        }) { threadMemory { id } }
    }
    """, {"id": thread_memory_id, "now": now})


def mark_contact_pulse_nudged(contact_id: str) -> None:
    """Set pulse_nudged_at to now on a contact record."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: UUID!, $now: Datetime!) {
        updateContactById(input: {
            id: $id,
            contactPatch: {pulseNudgedAt: $now}
        }) { contact { id } }
    }
    """, {"id": contact_id, "now": now})


def mark_company_pulse_nudged(company_id: str) -> None:
    """Set pulse_nudged_at to now on a company record."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: UUID!, $now: Datetime!) {
        updateCompanyById(input: {
            id: $id,
            companyPatch: {pulseNudgedAt: $now}
        }) { company { id } }
    }
    """, {"id": company_id, "now": now})


def mark_opportunity_pulse_nudged(opportunity_id: str) -> None:
    """Set pulse_nudged_at to now on an opportunity record."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    graphql("""
    mutation($id: UUID!, $now: Datetime!) {
        updateOpportunityById(input: {
            id: $id,
            opportunityPatch: {pulseNudgedAt: $now}
        }) { opportunity { id } }
    }
    """, {"id": opportunity_id, "now": now})


def update_contact_owner(contact_id: str, user_id: str) -> None:
    """Set owner_user_id on a contact (follows activity — last engager owns)."""
    graphql("""
    mutation($id: UUID!, $owner: UUID!) {
        updateContactById(input: {
            id: $id,
            contactPatch: {ownerUserId: $owner}
        }) { contact { id } }
    }
    """, {"id": contact_id, "owner": user_id})
    return None


# --- Handbook delivery tracking ---

def has_help_been_delivered(user_id: str, help_key: str) -> bool:
    """Check if a help entry has been delivered to a user."""
    result = graphql("""
    query($uid: UUID!, $key: String!) {
        allHelpDeliveredsList(condition: {userId: $uid, helpKey: $key}) { id }
    }
    """, {"uid": user_id, "key": help_key})
    return len(result.get("allHelpDeliveredsList", [])) > 0


def record_help_delivered(user_id: str, help_key: str) -> None:
    """Record that a help entry was delivered to a user."""
    graphql("""
    mutation($obj: HelpDeliveredInput!) {
        createHelpDelivered(input: {helpDelivered: $obj}) {
            helpDelivered { id }
        }
    }
    """, {"obj": {"userId": user_id, "helpKey": help_key}})


# --- Debrief pending state ---

def set_pending_debrief(conversation_id: str, extraction: dict) -> None:
    """Store pending debrief extraction on a conversation record."""
    import json
    graphql("""
    mutation($id: UUID!, $patch: ConversationPatch!) {
        updateConversationById(input: {id: $id, conversationPatch: $patch}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id, "patch": {"pendingDebrief": json.dumps(extraction)}})


def get_pending_debrief(conversation_id: str) -> dict | None:
    """Get pending debrief from conversation, if any."""
    result = graphql("""
    query($id: UUID!) {
        conversationById(id: $id) { pendingDebrief }
    }
    """, {"id": conversation_id})
    conv = result.get("conversationById", {})
    pending = conv.get("pendingDebrief")
    if pending:
        import json
        return json.loads(pending) if isinstance(pending, str) else pending
    return None


def clear_pending_debrief(conversation_id: str) -> None:
    """Clear pending debrief after approval/skip."""
    graphql("""
    mutation($id: UUID!) {
        updateConversationById(input: {id: $id, conversationPatch: {pendingDebrief: null}}) {
            conversation { id }
        }
    }
    """, {"id": conversation_id})


# --- Enrollment approval ---

def create_enrollment_request(user_id: str, role: str) -> dict:
    """Create a pending enrollment request."""
    result = graphql("""
    mutation($obj: EnrollmentRequestInput!) {
        createEnrollmentRequest(input: {enrollmentRequest: $obj}) {
            enrollmentRequest { id userId requestedRole }
        }
    }
    """, {"obj": {"userId": user_id, "requestedRole": role}})
    return result.get("createEnrollmentRequest", {}).get("enrollmentRequest")


def get_pending_enrollment_requests() -> list[dict]:
    """Get all pending enrollment requests."""
    result = graphql("""
    query {
        allEnrollmentRequestsList(condition: {status: "pending"}) {
            id userId requestedRole createdAt
        }
    }
    """)
    return result.get("allEnrollmentRequestsList", [])


def resolve_enrollment_request(request_id: str, status: str, approved_by: str = None) -> None:
    """Resolve an enrollment request (approve/reject)."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    patch = {"status": status, "resolvedAt": now}
    if approved_by:
        patch["approvedBy"] = approved_by
    graphql("""
    mutation($id: UUID!, $patch: EnrollmentRequestPatch!) {
        updateEnrollmentRequestById(input: {id: $id, enrollmentRequestPatch: $patch}) {
            enrollmentRequest { id }
        }
    }
    """, {"id": request_id, "patch": patch})


def get_expired_enrollment_requests(hours: int = 48) -> list[dict]:
    """Get pending requests older than `hours` hours."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    result = graphql("""
    query($cutoff: Datetime!) {
        allEnrollmentRequestsList(filter: {
            status: {equalTo: "pending"},
            createdAt: {lessThan: $cutoff}
        }) { id userId createdAt }
    }
    """, {"cutoff": cutoff})
    return result.get("allEnrollmentRequestsList", [])


# --- Profile collection ---

def update_user_profile(user_id: str, **fields) -> None:
    """Update user record with profile fields."""
    patch = {k: v for k, v in fields.items() if v is not None}
    if not patch:
        return
    camel_patch = {}
    for k, v in patch.items():
        parts = k.split("_")
        camel = parts[0] + "".join(p.title() for p in parts[1:])
        camel_patch[camel] = v
    graphql("""
    mutation($id: UUID!, $patch: UserPatch!) {
        updateUserById(input: {id: $id, userPatch: $patch}) {
            user { id }
        }
    }
    """, {"id": user_id, "patch": camel_patch})


# --- User identity ---

def get_user(user_id: str) -> dict | None:
    """Get user by UUID."""
    result = graphql("""
    query($id: UUID!) {
        userById(id: $id) {
            id email name role currentStage currentChapter active
            streak lastActivity calendarUrl phone workingDays
        }
    }
    """, {"id": user_id})
    return result.get("userById")


def get_user_by_email(email: str) -> dict | None:
    """Get user by email (normalized to lowercase)."""
    result = graphql("""
    query($email: String!) {
        allUsersList(condition: {email: $email}, first: 1) {
            id email name role currentStage currentChapter active
            streak lastActivity calendarUrl
        }
    }
    """, {"email": email.lower()})
    users = result.get("allUsersList", [])
    return users[0] if users else None


def create_user(email: str, name: str, role: str) -> dict:
    """Create a new user."""
    result = graphql("""
    mutation($obj: UserInput!) {
        createUser(input: {user: $obj}) {
            user { id email name role currentStage currentChapter }
        }
    }
    """, {"obj": {"email": email.lower(), "name": name, "role": role}})
    return result.get("createUser", {}).get("user")


def get_active_users() -> list[dict]:
    """Get all active users (replaces get_active_enrollments)."""
    result = graphql("""
    query {
        allUsersList(condition: {active: true}) {
            id email name role currentStage currentChapter
            streak lastActivity calendarUrl
        }
    }
    """)
    return result.get("allUsersList", [])


def update_user_role(user_id: str, role: str) -> None:
    """Update a user's role."""
    graphql("""
    mutation($id: UUID!, $patch: UserPatch!) {
        updateUserById(input: {id: $id, userPatch: $patch}) {
            user { id }
        }
    }
    """, {"id": user_id, "patch": {"role": role}})


def set_user_snooze(user_id: str, until: str) -> None:
    """Set snooze until a specific time for a user."""
    graphql("""
    mutation($id: UUID!, $until: Datetime!) {
        updateUserById(input: {id: $id, userPatch: {snoozedUntil: $until}}) {
            user { id }
        }
    }
    """, {"id": user_id, "until": until})


def clear_user_snooze(user_id: str) -> None:
    """Clear snooze for a user."""
    graphql("""
    mutation($id: UUID!) {
        updateUserById(input: {id: $id, userPatch: {snoozedUntil: null}}) {
            user { id }
        }
    }
    """, {"id": user_id})


def is_user_snoozed(user_id: str) -> bool:
    """Check if a user is currently snoozed."""
    from datetime import UTC, datetime
    result = graphql("""
    query($id: UUID!) {
        userById(id: $id) { snoozedUntil }
    }
    """, {"id": user_id})
    user = result.get("userById")
    if not user or not user.get("snoozedUntil"):
        return False
    snoozed_until = datetime.fromisoformat(user["snoozedUntil"])
    if snoozed_until.tzinfo is None:
        snoozed_until = snoozed_until.replace(tzinfo=UTC)
    return datetime.now(UTC) < snoozed_until


# --- Channel links ---

def get_channel_link(channel_type: str, channel_user_id: str) -> dict | None:
    """Look up a channel link."""
    result = graphql("""
    query($type: String!, $uid: String!) {
        allChannelLinksList(condition: {channelType: $type, channelUserId: $uid}, first: 1) {
            id userId channelType channelUserId
        }
    }
    """, {"type": channel_type, "uid": channel_user_id})
    links = result.get("allChannelLinksList", [])
    return links[0] if links else None


def create_channel_link(user_id: str, channel_type: str, channel_user_id: str) -> None:
    """Create a channel link mapping."""
    graphql("""
    mutation($obj: ChannelLinkInput!) {
        createChannelLink(input: {channelLink: $obj}) {
            channelLink { id }
        }
    }
    """, {"obj": {"userId": user_id, "channelType": channel_type, "channelUserId": channel_user_id}})


def get_slack_user_id(user_id: str) -> str | None:
    """Reverse lookup: user_id → Slack channel_user_id for DM sending.

    The database has a UNIQUE(user_id, channel_type) constraint so this returns
    at most one row. ORDER BY linked_at DESC is defence in depth in case the
    constraint is ever loosened — most recent link wins.
    """
    result = graphql("""
    query($uid: UUID!, $type: String!) {
        allChannelLinksList(
            condition: {userId: $uid, channelType: $type},
            orderBy: LINKED_AT_DESC,
            first: 1
        ) {
            channelUserId
        }
    }
    """, {"uid": user_id, "type": "slack"})
    links = result.get("allChannelLinksList", [])
    return links[0]["channelUserId"] if links else None


# --- Admin management ---

def is_admin(email: str) -> bool:
    """Check if email is an admin."""
    result = graphql("""
    query($email: String!) {
        allAdminsList(condition: {email: $email}) { email }
    }
    """, {"email": email.lower()})
    return len(result.get("allAdminsList", [])) > 0


def add_admin(email: str, granted_by: str) -> None:
    """Grant admin privileges."""
    graphql("""
    mutation($obj: AdminInput!) {
        createAdmin(input: {admin: $obj}) { admin { id } }
    }
    """, {"obj": {"email": email.lower(), "grantedBy": granted_by}})


def remove_admin(email: str) -> None:
    """Revoke admin privileges."""
    result = graphql("""
    query($email: String!) {
        allAdminsList(condition: {email: $email}) { id }
    }
    """, {"email": email.lower()})
    admins = result.get("allAdminsList", [])
    if admins:
        graphql("""
        mutation($id: UUID!) {
            deleteAdminById(input: {id: $id}) { admin { id } }
        }
        """, {"id": admins[0]["id"]})


def get_all_admins() -> list[dict]:
    """List all admins."""
    result = graphql("""
    query { allAdminsList { email grantedBy grantedAt } }
    """)
    return result.get("allAdminsList", [])


def ensure_root_admin(email: str) -> None:
    """Ensure root admin exists in admins table."""
    if not email:
        return
    if not is_admin(email):
        add_admin(email, granted_by="system")


# --- Account plans ---

def get_account_plan(company_id: str) -> dict | None:
    """Get account plan for a company."""
    result = graphql("""
    query($cid: UUID!) {
        allAccountPlansList(condition: {companyId: $cid}, first: 1) {
            id companyId whiteSpace expansionTriggers strategy
            qbrNotes qbrAt nextQbr createdAt updatedAt
        }
    }
    """, {"cid": company_id})
    plans = result.get("allAccountPlansList", [])
    return plans[0] if plans else None


def create_account_plan(company_id: str, **fields) -> dict:
    """Create an account plan for a company."""
    obj = {"companyId": company_id}
    field_map = {
        "white_space": "whiteSpace", "expansion_triggers": "expansionTriggers",
        "strategy": "strategy", "next_qbr": "nextQbr",
    }
    for k, v in fields.items():
        if v is not None and k in field_map:
            obj[field_map[k]] = v
    result = graphql("""
    mutation($obj: AccountPlanInput!) {
        createAccountPlan(input: {accountPlan: $obj}) {
            accountPlan { id companyId }
        }
    }
    """, {"obj": obj})
    return result.get("createAccountPlan", {}).get("accountPlan")


def update_account_plan(plan_id: str, **fields) -> None:
    """Update an account plan."""
    field_map = {
        "white_space": "whiteSpace", "expansion_triggers": "expansionTriggers",
        "strategy": "strategy", "qbr_notes": "qbrNotes", "qbr_at": "qbrAt",
        "next_qbr": "nextQbr",
    }
    patch = {}
    for k, v in fields.items():
        if k in field_map:
            patch[field_map[k]] = v
    if not patch:
        return
    graphql("""
    mutation($id: UUID!, $patch: AccountPlanPatch!) {
        updateAccountPlanById(input: {id: $id, accountPlanPatch: $patch}) {
            accountPlan { id }
        }
    }
    """, {"id": plan_id, "patch": patch})


def get_due_qbrs() -> list[dict]:
    """Get account plans with QBR due (next_qbr <= now)."""
    from datetime import datetime
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    result = graphql("""
    query($now: Date!) {
        allAccountPlansList(filter: {nextQbr: {lessThanOrEqualTo: $now}}) {
            id companyId whiteSpace strategy qbrNotes nextQbr
            companyByCompanyId { id name services ownerUserId }
        }
    }
    """, {"now": now})
    return result.get("allAccountPlansList", [])


def get_accounts_with_plans() -> list[dict]:
    """Get all companies that have account plans."""
    result = graphql("""
    query {
        allAccountPlansList {
            id companyId whiteSpace strategy nextQbr
            companyByCompanyId { id name clientSince services ownerUserId }
        }
    }
    """)
    return result.get("allAccountPlansList", [])


# --- Company client fields ---

def update_company_client_fields(company_id: str, **fields) -> None:
    """Update client-specific fields on a company."""
    field_map = {
        "client_since": "clientSince", "contract_value": "contractValue",
        "services": "services", "owner_user_id": "ownerUserId",
    }
    patch = {}
    for k, v in fields.items():
        if k in field_map:
            patch[field_map[k]] = v
    if not patch:
        return
    graphql("""
    mutation($id: UUID!, $patch: CompanyPatch!) {
        updateCompanyById(input: {id: $id, companyPatch: $patch}) {
            company { id }
        }
    }
    """, {"id": company_id, "patch": patch})


def get_client_companies() -> list[dict]:
    """Get companies that are active clients (client_since is set)."""
    result = graphql("""
    query {
        allCompaniesList(filter: {clientSince: {isNull: false}}) {
            id name clientSince contractValue services ownerUserId
        }
    }
    """)
    return result.get("allCompaniesList", [])


# --- Engagement service meetings ---

def get_due_service_meetings() -> list[dict]:
    """Get engagements with service meetings due (next_service_meeting <= now)."""
    from datetime import datetime
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    result = graphql("""
    query($now: Date!) {
        allEngagementsList(filter: {
            nextServiceMeeting: {lessThanOrEqualTo: $now},
            status: {equalTo: "active"}
        }) {
            id title ownerUserId nextServiceMeeting lastServiceMeeting
            companyByCompanyId { id name }
        }
    }
    """, {"now": now})
    return result.get("allEngagementsList", [])


def update_service_meeting(engagement_id: str, notes: str = None, next_date: str = None) -> None:
    """Update service meeting state on an engagement."""
    from datetime import datetime
    patch = {"lastServiceMeeting": datetime.now(UTC).isoformat()}
    if notes:
        patch["serviceMeetingNotes"] = notes
    if next_date:
        patch["nextServiceMeeting"] = next_date
    graphql("""
    mutation($id: UUID!, $patch: EngagementPatch!) {
        updateEngagementById(input: {id: $id, engagementPatch: $patch}) {
            engagement { id }
        }
    }
    """, {"id": engagement_id, "patch": patch})


# --- Reminders ---

def create_reminder(creator_user_id: str, target_user_id: str, remind_at: str, context: str) -> dict:
    """Create a reminder to nudge a user at a specific time."""
    result = graphql("""
    mutation($obj: ReminderInput!) {
        createReminder(input: {reminder: $obj}) {
            reminder { id remindAt targetUserId context }
        }
    }
    """, {"obj": {
        "creatorUserId": creator_user_id,
        "targetUserId": target_user_id,
        "remindAt": remind_at,
        "context": context,
    }})
    return result.get("createReminder", {}).get("reminder")


def get_due_user_reminders() -> list[dict]:
    """Get pending reminders that are due."""
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
    result = graphql("""
    query($now: Datetime!) {
        allRemindersList(filter: {
            remindAt: {lessThanOrEqualTo: $now},
            status: {equalTo: "pending"}
        }) {
            id creatorUserId targetUserId remindAt context
            userByCreatorUserId { name }
        }
    }
    """, {"now": now})
    return result.get("allRemindersList", [])


def mark_reminder_delivered(reminder_id: str) -> None:
    """Mark a reminder as delivered."""
    graphql("""
    mutation($id: UUID!) {
        updateReminderById(input: {id: $id, reminderPatch: {status: "delivered"}}) {
            reminder { id }
        }
    }
    """, {"id": reminder_id})


def find_user_by_name(name: str) -> dict | None:
    """Find a user by name (case-insensitive partial match)."""
    result = graphql("""
    query($name: String!) {
        allUsersList(filter: {name: {includesInsensitive: $name}}, first: 1) {
            id email name role active
        }
    }
    """, {"name": name})
    users = result.get("allUsersList", [])
    return users[0] if users else None
