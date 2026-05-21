"""Central intelligence data access — single path to CI tables.

This module composes raw GraphQL queries (from graphql_client) into meaningful
data bundles. Callers (bot handlers, CLI commands, cronjobs) should invoke the
`gather_*` functions here instead of hitting GraphQL directly.

Principles (see CLAUDE.md → Code principles):
- Single path to CI data — every CI query goes through this module.
- Gather and synthesize are separate — `gather_*` functions return plain dicts,
  never formatted strings. No LLM calls here.
- Deterministic formatters (like `format_context_for_prompt`) are NOT synthesis;
  they are mechanical prompt-text builders and live alongside gather helpers.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from mothertree.graphql_client import get_organization_profile, graphql, search_similar
from mothertree.llm import generate

# Tables searched semantically when a query is provided.
# Each tuple is (table_name, human_label).
_SEMANTIC_TABLES = [
    ("change", "Change"),
    ("worldview", "Worldview"),
    ("competitors", "Competitors"),
    ("insights", "Insights"),
    ("proof_points", "Proof Points"),
]


# Organization profile rendering — order and label mapping for the top-of-prompt
# "ORGANIZATION PROFILE:" block.
_ORG_PROFILE_ORDER = ("identity", "change", "audience", "competitor_category")
_ORG_PROFILE_LABELS = {
    "identity": "Identity",
    "change": "Change",
    "audience": "Audience",
    "competitor_category": "Competes with",
}


def gather_context(query: str | None = None, top_n: int = 5) -> dict:
    """Gather CI context for character conversation prompts.

    Returns a plain dict with all CI tables; does NOT format the data.
    Callers (or `format_context_for_prompt`) are responsible for turning this
    into prompt text.

    Args:
        query: Optional — if set, also runs semantic search across CI tables
            and returns results under `semantic_results`.
        top_n: Max records per table (foundation + narrative top-N queries).

    Returns:
        {
            "changes": [...],
            "worldviews": [...],
            "personas": [...],
            "competitors": [...],
            "contacts": [...],
            "signals": [...],
            "proof_points": [...],
            "insights": [...],
            "organization": [...],
            "semantic_results": [{"table": str, "label": str, "results": [...]}] | None,
        }
    """
    data = graphql(
        """
        query($top_n: Int!) {
          allChangesList(first: $top_n, orderBy: CONFIDENCE_DESC) {
            id statement context confidence
          }
          allWorldviewsList(first: $top_n, orderBy: CONFIDENCE_DESC) {
            id belief pain confidence
          }
          allPersonasList(first: $top_n) {
            id name role profile
          }
          allCompetitorsList(first: $top_n) {
            id type positioning
          }
          allContactsList(first: $top_n, orderBy: UPDATED_AT_DESC) {
            id name role temperature
          }
          allSignalsList(first: $top_n, orderBy: CREATED_AT_DESC) {
            id content source createdAt
          }
          allProofPointsList(first: $top_n, orderBy: CONFIDENCE_DESC) {
            id outcome
          }
          allInsightsList(first: $top_n, orderBy: CONFIDENCE_DESC) {
            id category reframe evidence
          }
        }
        """,
        {"top_n": top_n},
    )

    # Organization profile comes from its own helper (it applies its own ordering).
    organization = get_organization_profile()

    result = {
        "changes": data.get("allChangesList", []),
        "worldviews": data.get("allWorldviewsList", []),
        "personas": data.get("allPersonasList", []),
        "competitors": data.get("allCompetitorsList", []),
        "contacts": data.get("allContactsList", []),
        "signals": data.get("allSignalsList", []),
        "proof_points": data.get("allProofPointsList", []),
        "insights": data.get("allInsightsList", []),
        "organization": organization,
        "semantic_results": None,
    }

    if query:
        result["semantic_results"] = _gather_semantic(query, limit=top_n)

    return result


def _gather_semantic(query: str, limit: int = 5) -> list[dict]:
    """Run semantic search across CI tables in parallel.

    Returns a list of {"table", "label", "results"} dicts, one per table
    that had matches. Tables with no matches are omitted.
    """

    def _search(entry):
        table, label = entry
        try:
            results = search_similar(table, query, limit=limit, threshold=0.1)
        except Exception:
            results = []
        return {"table": table, "label": label, "results": results}

    with ThreadPoolExecutor(max_workers=len(_SEMANTIC_TABLES)) as pool:
        sections = list(pool.map(_search, _SEMANTIC_TABLES))

    return [s for s in sections if s["results"]]


# ---------------------------------------------------------------------------
# Prompt formatting — deterministic, no LLM calls.
# ---------------------------------------------------------------------------

def _format_org_profile(elements: list[dict]) -> str:
    """Format the organization profile block for prompt injection."""
    if not elements:
        return ""

    by_type: dict[str, list[str]] = {}
    for e in elements:
        element_type = e.get("element_type") or e.get("elementType")
        content = e.get("content")
        if not element_type or not content:
            continue
        by_type.setdefault(element_type, []).append(content)

    lines = []
    for element_type in _ORG_PROFILE_ORDER:
        items = by_type.get(element_type, [])
        if items:
            label = _ORG_PROFILE_LABELS[element_type]
            lines.append(f"- {label}: {'; '.join(items)}")

    if not lines:
        return ""
    return "ORGANIZATION PROFILE:\n" + "\n".join(lines)


def _format_similarity(value) -> str:
    """Format a similarity score (stored as a Decimal/string/float) as a percentage."""
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "?"


def _format_semantic_section(section: dict) -> str | None:
    """Render one semantic_results entry as a '{Label} (relevant):' block."""
    table = section.get("table")
    label = section.get("label", table or "Results")
    results = section.get("results") or []
    if not results:
        return None

    lines: list[str] = []
    for r in results:
        sim = _format_similarity(r.get("similarity"))
        if table == "change":
            body = r.get("statement", "")
            lines.append(f"- {body} ({sim})")
        elif table == "worldview":
            body = r.get("belief", "")
            lines.append(f"- {body} ({sim})")
        elif table == "competitors":
            body = f"vs {r.get('type', '')}: {r.get('positioning', '')}"
            lines.append(f"- {body} ({sim})")
        elif table == "insights":
            body = f"[{r.get('category', '')}] {r.get('reframe', '')}"
            lines.append(f"- {body} ({sim})")
        elif table == "proof_points":
            body = r.get("outcome", "")
            lines.append(f"- {body} ({sim})")
        else:
            lines.append(f"- {r} ({sim})")

    return f"{label} (relevant):\n" + "\n".join(lines)


def format_context_for_prompt(ctx: dict) -> str:
    """Format a gather_context() result as prompt text (deterministic, no LLM).

    Used by bot characters and ask_with_history to inject CI data into
    system prompts. This is NOT synthesis — it's mechanical formatting.

    The output mirrors the historical ``fetch_context()`` format so downstream
    prompt assertions continue to hold:

    - Optional ``ORGANIZATION PROFILE:`` block at the top
    - ``Change:``, ``Worldview:``, ``Personas:``, ``Competitors:`` sections
    - ``Known Contacts:`` and ``Recent Signals:`` sections
    - ``Insights:`` section when no query was run
    - ``{Label} (relevant):`` sections when semantic search returned hits
    """
    parts: list[str] = []

    org_block = _format_org_profile(ctx.get("organization") or [])
    if org_block:
        parts.append(org_block)

    changes = ctx.get("changes") or []
    parts.append(
        "Change:\n" + "\n".join(f"- {c.get('statement', '')}" for c in changes)
    )

    worldviews = ctx.get("worldviews") or []
    parts.append(
        "Worldview:\n" + "\n".join(f"- {w.get('belief', '')}" for w in worldviews)
    )

    personas = ctx.get("personas") or []
    parts.append(
        "Personas:\n"
        + "\n".join(f"- {p.get('name', '')} ({p.get('role', '')})" for p in personas)
    )

    competitors = ctx.get("competitors") or []
    parts.append(
        "Competitors:\n"
        + "\n".join(
            f"- vs {c.get('type', '')}: {c.get('positioning', '')}" for c in competitors
        )
    )

    contacts = ctx.get("contacts") or []
    parts.append(
        "Known Contacts:\n"
        + "\n".join(
            f"- {c.get('name', '')} ({c.get('role') or 'unknown role'})"
            for c in contacts
        )
    )

    signals = ctx.get("signals") or []
    parts.append(
        "Recent Signals:\n"
        + "\n".join(
            f"- [{s.get('source', '')}] {s.get('content', '')}" for s in signals
        )
    )

    semantic_results = ctx.get("semantic_results")
    if semantic_results:
        for section in semantic_results:
            rendered = _format_semantic_section(section)
            if rendered:
                parts.append(rendered)
    else:
        insights = ctx.get("insights") or []
        parts.append(
            "Insights:\n"
            + "\n".join(
                f"- [{i.get('category', '')}] {i.get('reframe', '')}" for i in insights
            )
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Pipeline — opportunities, signals, interactions, contacts, training.
# ---------------------------------------------------------------------------

def gather_pipeline(
    user_id: str | None = None,
    days: int = 7,
    counts_only: bool = False,
    scope: str | None = None,
    target_name: str | None = None,
) -> dict:
    """Gather pipeline state — opportunities, signals, interactions, contacts, training.

    Args:
        user_id: Scope to this user's owned items. None = global.
        days: Lookback window for signals and interactions.
        counts_only: If True, return totalCount per table instead of full lists.
                     Used by monthly retro which synthesizes from aggregates.
        scope: "global" | "personal" | "other". If None, defaults to "global"
            when user_id is None, else "personal". Callers that know the
            caller's identity (e.g. bot dispatcher asking about someone else)
            should pass scope explicitly.
        target_name: Name of the scoped user, if applicable. Passed through to
            the return dict for synthesis (third-person rendering).

    Returns:
        {
            "opportunities": [...],
            "total_opportunities": int (counts_only only — global totalCount, unfiltered),
            "signals": [...] or int (counts_only),
            "interactions": [...] or int (counts_only),
            "contacts": [...] or int (counts_only),
            "training": [...],
            "scope": "global" | "personal" | "other",
            "target_name": str | None,
        }
    """
    now = datetime.now(UTC)
    cutoff = (now - timedelta(days=days)).isoformat()

    if scope is None:
        scope = "global" if user_id is None else "personal"

    if counts_only:
        data = graphql(
            """
            query($cutoff: Datetime!) {
              allOpportunities { totalCount }
              allOpportunitiesList(filter: {updatedAt: {greaterThanOrEqualTo: $cutoff}}) {
                id stage title ownerUserId
                companyByCompanyId { name }
              }
              recentSignals: allSignals(filter: {createdAt: {greaterThanOrEqualTo: $cutoff}}) { totalCount }
              recentInteractions: allInteractions(filter: {date: {greaterThanOrEqualTo: $cutoff}}) { totalCount }
              warmHotContacts: allContacts(filter: {temperature: {in: ["warm", "hot"]}}) { totalCount }
              allUsersList(condition: {active: true}) {
                id name role currentStage currentChapter streak
              }
            }
            """,
            {"cutoff": cutoff},
        )

        opps = data.get("allOpportunitiesList", []) or []
        if user_id is not None:
            opps = [o for o in opps if o.get("ownerUserId") == user_id]

        return {
            "opportunities": opps,
            "total_opportunities": (data.get("allOpportunities") or {}).get("totalCount", 0),
            "signals": (data.get("recentSignals") or {}).get("totalCount", 0),
            "interactions": (data.get("recentInteractions") or {}).get("totalCount", 0),
            "contacts": (data.get("warmHotContacts") or {}).get("totalCount", 0),
            "training": data.get("allUsersList", []) or [],
            "scope": scope,
            "target_name": target_name,
        }

    data = graphql(
        """
        query($cutoff: Datetime!) {
          allOpportunitiesList(orderBy: STAGE_ASC) {
            id stage title notes nextAction nextActionDate ownerUserId
            companyByCompanyId { name }
            contactByContactId { name }
          }
          allSignalsList(filter: {createdAt: {greaterThanOrEqualTo: $cutoff}}, orderBy: CREATED_AT_DESC) {
            id content source createdAt
          }
          allInteractionsList(filter: {date: {greaterThanOrEqualTo: $cutoff}}, orderBy: DATE_DESC) {
            id type summary date
            contactByContactId { name }
          }
          allUsersList(condition: {active: true}) {
            id name role currentStage currentChapter streak
          }
          allContactsList(filter: {temperature: {in: ["warm", "hot"]}}, first: 20) {
            id name temperature lastContact ownerUserId
            companyByCompanyId { name }
          }
        }
        """,
        {"cutoff": cutoff},
    )

    opportunities = data.get("allOpportunitiesList", []) or []
    signals = data.get("allSignalsList", []) or []
    interactions = data.get("allInteractionsList", []) or []
    contacts = data.get("allContactsList", []) or []
    training = data.get("allUsersList", []) or []

    # Python-side user filtering. Keeps the function schema-tolerant: if
    # ownerUserId isn't populated for a row, it's filtered out for scoped calls.
    if user_id is not None:
        opportunities = [o for o in opportunities if o.get("ownerUserId") == user_id]
        contacts = [c for c in contacts if c.get("ownerUserId") == user_id]

    return {
        "opportunities": opportunities,
        "signals": signals,
        "interactions": interactions,
        "contacts": contacts,
        "training": training,
        "scope": scope,
        "target_name": target_name,
    }


def _summarize_signals(signals: list[dict]) -> str:
    """Group and deduplicate signals into a readable summary."""
    if not signals:
        return "No new signals this week."

    by_source: dict[str, list[str]] = {}
    for s in signals:
        source = s.get("source", "unknown")
        person = source.replace("slack:", "") if source else "unknown"
        by_source.setdefault(person, []).append((s.get("content") or "")[:150])

    parts = []
    for person, contents in by_source.items():
        unique = list(dict.fromkeys(contents))[:3]
        if len(unique) == 1:
            parts.append(f"- {person}: {unique[0]}")
        else:
            parts.append(f"- {person} ({len(contents)} signals):")
            for c in unique:
                parts.append(f"  - {c[:100]}")
    return "\n".join(parts)


def _summarize_interactions(interactions: list[dict]) -> str:
    """Group interactions by contact instead of listing individually."""
    if not interactions:
        return "No logged interactions this week."

    by_contact: dict[str, list[dict]] = {}
    for i in interactions:
        contact = (i.get("contactByContactId") or {}).get("name", "?")
        by_contact.setdefault(contact, []).append({
            "type": i.get("type", "?"),
            "date": (i.get("date") or "")[:10],
            "summary": (i.get("summary") or "")[:80],
        })

    parts = []
    for contact, ints in by_contact.items():
        if len(ints) == 1:
            rec = ints[0]
            parts.append(f"- {contact}: {rec['type']} ({rec['date']})")
        else:
            parts.append(f"- {contact}: {len(ints)} interactions")
    return "\n".join(parts)


def _summarize_training(enrollments: list[dict]) -> str:
    """Human-readable training progress."""
    if not enrollments:
        return "No one enrolled yet."

    # Lazy import: avoid coupling mothertree.intelligence to training/ since the
    # dependency arrow goes training → mothertree, not the other way around.
    from training.curriculum import get_stage_name, get_stages, get_total_chapters

    parts = []
    for e in enrollments:
        name = e.get("name", "?")
        role = e.get("role", "?")
        stage = e.get("currentStage", 0) or 0
        chapter = e.get("currentChapter", 0) or 0
        streak = e.get("streak") or 0
        try:
            total_stages = len(get_stages(role))
        except Exception:
            total_stages = 0

        if stage == 0 and chapter == 0:
            status = "hasn't started yet"
        elif total_stages and stage >= total_stages:
            status = "completed the program"
        else:
            try:
                stage_name = get_stage_name(role, stage)
                total_ch = get_total_chapters(role, stage)
                status = f"in *{stage_name}* (chapter {chapter + 1}/{total_ch})"
            except Exception:
                status = f"stage {stage}, chapter {chapter + 1}"

        streak_str = f", {streak}-day streak" if streak > 0 else ""
        parts.append(f"- {name} ({role}): {status}{streak_str}")

    return "\n".join(parts)


def _format_pipeline_data(data: dict) -> str:
    """Render a gather_pipeline() result as a readable prompt body.

    Handles both the full-list shape and the counts_only shape (ints).
    Deterministic — no LLM calls.
    """
    opps = data.get("opportunities") or []
    signals = data.get("signals")
    interactions = data.get("interactions")
    contacts = data.get("contacts")
    training = data.get("training") or []

    # Pipeline summary
    if opps:
        pipeline_lines = []
        for o in opps:
            company = (o.get("companyByCompanyId") or {}).get("name", "?")
            pipeline_lines.append(
                f"- {company} ({o.get('stage', '?')}): {o.get('title', '')} "
                f"-> next: {o.get('nextAction', 'none')} by {o.get('nextActionDate', '?')}"
            )
        pipeline_text = "\n".join(pipeline_lines)
    else:
        pipeline_text = "No active opportunities tracked."

    # Signals — int (counts_only) or list
    if isinstance(signals, int):
        signal_count = signals
        signal_summary = f"{signals} signal(s) in window."
    else:
        signals_list = signals or []
        signal_count = len(signals_list)
        signal_summary = _summarize_signals(signals_list)

    # Interactions — int (counts_only) or list
    if isinstance(interactions, int):
        interaction_count = interactions
        interaction_summary = f"{interactions} interaction(s) in window."
    else:
        interactions_list = interactions or []
        interaction_count = len(interactions_list)
        interaction_summary = _summarize_interactions(interactions_list)

    # Contacts — int (counts_only) or list
    if isinstance(contacts, int):
        contacts_text = f"{contacts} warm/hot contact(s)."
    else:
        contacts_list = contacts or []
        if contacts_list:
            contact_lines = []
            for c in contacts_list:
                company = (c.get("companyByCompanyId") or {}).get("name", "")
                company_str = f" at {company}" if company else ""
                contact_lines.append(
                    f"- {c.get('name', '?')}{company_str} ({c.get('temperature', '?')})"
                )
            contacts_text = "\n".join(contact_lines)
        else:
            contacts_text = "No warm or hot contacts."

    training_summary = _summarize_training(training)

    return (
        f"PIPELINE:\n{pipeline_text}\n\n"
        f"SIGNALS ({signal_count}):\n{signal_summary}\n\n"
        f"INTERACTIONS ({interaction_count}):\n{interaction_summary}\n\n"
        f"WARM/HOT CONTACTS:\n{contacts_text}\n\n"
        f"TRAINING:\n{training_summary}"
    )


# Scope-aware system prompts for synthesize_pipeline.
_PIPELINE_SYSTEM_PROMPTS = {
    "global": (
        "You are Mother Tree writing the Monday morning briefing for a consultative sales team. "
        "Be direct and actionable. Structure as:\n"
        "1. *This week's priorities* — 2-3 specific actions with names and companies\n"
        "2. *Pipeline* — where each opportunity stands, what needs to happen\n"
        "3. *Signals* — what came in, grouped by opportunity (not raw messages)\n"
        "4. *Team* — training progress, who needs a nudge\n\n"
        "Keep it under 300 words. Lead with what matters. Skip anything with no action. "
        "Use Slack formatting (*bold*, bullets). "
        "End with one question that prompts the team to share what they're working on this week."
    ),
    "personal": (
        "You are Mother Tree coaching one hunter on their pipeline. "
        "Address them directly in second person (you, your). Warm but direct — this is coaching, not a report. "
        "Structure as:\n"
        "1. *Your deals* — where each opportunity stands, what you need to do next\n"
        "2. *What needs your attention* — stalled deals, overdue next actions\n"
        "3. *Suggested actions* — 2-3 specific moves for this week\n\n"
        "Keep it under 250 words. Lead with what matters most to you right now. "
        "Use Slack formatting (*bold*, bullets). "
        "End with one question that invites a reply."
    ),
    "other": (
        "You are Mother Tree summarising a teammate's pipeline for someone else on the team. "
        "Use third person — refer to the owner by name throughout. "
        "Tone is observational and supportive, not judgemental. Structure as:\n"
        "1. *{name}'s deals* — where each opportunity stands\n"
        "2. *Where {name} might need support* — stalled deals, overdue next actions\n"
        "3. *How you could help* — 1-2 specific ways to support them\n\n"
        "Keep it under 250 words. Use Slack formatting (*bold*, bullets). "
        "End with a question that invites the reader to reach out."
    ),
}


def synthesize_pipeline(
    data: dict,
    scope: str = "global",
    model: str | None = None,
    on_chunk=None,
) -> str:
    """Generate narrative pipeline review from a gather_pipeline() dict.

    Args:
        data: Output of gather_pipeline(). Must contain "scope"/"target_name"
            keys if synthesizer needs them (caller may also pass scope/target
            via parameters).
        scope: "global" | "personal" | "other". Drives system prompt choice.
        model: Optional override for the generation model.
        on_chunk: Optional streaming callback. If provided, streams chunks via
            chat_conversation; otherwise a single generate() call.

    Returns:
        Narrative review text.
    """
    system = _PIPELINE_SYSTEM_PROMPTS.get(scope, _PIPELINE_SYSTEM_PROMPTS["global"])

    target_name = data.get("target_name")
    if scope == "other" and target_name:
        system = system.replace("{name}", target_name)
        system = (
            f"{system}\n\n"
            f"The hunter you are describing is named {target_name}. "
            f"Refer to them by name."
        )
    else:
        # Strip {name} placeholders for global/personal prompts (not expected,
        # but guards against misuse).
        system = system.replace("{name}", target_name or "they")

    body = _format_pipeline_data(data)
    user_prompt = f"Pipeline data:\n{body}"

    if on_chunk is not None:
        # Stream via chat_conversation — same model pathway, streaming enabled.
        from mothertree.llm import chat_conversation
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        return chat_conversation(messages, model=model, on_chunk=on_chunk)

    if model is not None:
        return generate(system, user_prompt, model=model)
    return generate(system, user_prompt)


# ---------------------------------------------------------------------------
# Cronjob-only synthesis — weekly briefing + monthly retrospective.
# No streaming: cronjobs deliver complete messages, not chat UI.
# ---------------------------------------------------------------------------


def synthesize_weekly(data: dict, model: str | None = None) -> str:
    """Monday morning briefing for the whole team (cronjob entry point).

    Thin alias for ``synthesize_pipeline(data, scope="global")`` — kept as a
    distinct named function so the weekly cronjob has a clean entry point
    without a streaming parameter. Under 300 words, Slack formatting.
    """
    return synthesize_pipeline(data, scope="global", model=model)


_MONTHLY_SYSTEM_PROMPT = (
    "You are Mother Tree writing a monthly retrospective for a consultative sales team. "
    "Be direct, honest, actionable. Highlight what's working, what needs attention, "
    "and one specific thing to focus on next month. 200 words max."
)


def synthesize_monthly(data: dict, model: str | None = None) -> str:
    """Monthly retrospective (cronjob entry point).

    Takes a ``gather_pipeline(days=30, counts_only=True)`` dict and produces
    a retrospective-style narrative (different tone from the weekly briefing:
    reflective, not priority-driving). No streaming.
    """
    body = _format_pipeline_data(data)
    user_prompt = f"Monthly data:\n{body}"

    if model is not None:
        return generate(_MONTHLY_SYSTEM_PROMPT, user_prompt, model=model)
    return generate(_MONTHLY_SYSTEM_PROMPT, user_prompt)


# ---------------------------------------------------------------------------
# Meeting context — CI data for calendar events (prep + debrief).
# ---------------------------------------------------------------------------


def gather_meeting_context(event: dict) -> dict:
    """Gather CI context relevant to a calendar event.

    Looks up each attendee by name in contacts, then runs semantic search
    on insights, changes, and proof_points using meeting title + attendee
    names as the query. Returns plain dicts — no formatted strings, no
    LLM calls.

    Args:
        event: ``{"title": str, "attendees": [str], "date": str, ...}``.

    Returns:
        ``{"event": event, "attendee_contacts": [...], "insights": [...],
           "changes": [...], "proof_points": [...]}``.
    """
    title = event.get("title") or event.get("summary") or ""
    attendees = event.get("attendees") or []

    query = title
    if attendees:
        query = f"{title} {' '.join(attendees[:3])}".strip()

    # Per-attendee contact lookup (parameterized, up to 5).
    attendee_contacts: list[dict] = []
    for name in attendees[:5]:
        try:
            result = graphql(
                """
                query($name: String!) {
                  allContactsList(filter: {name: {includesInsensitive: $name}}, first: 1) {
                    id name role temperature notes
                    companyByCompanyId { name industry }
                  }
                }
                """,
                {"name": name},
            )
            attendee_contacts.extend(result.get("allContactsList", []) or [])
        except Exception:
            pass

    # Semantic search for meeting-relevant CI.
    def _semantic(table: str, limit: int) -> list[dict]:
        if not query:
            return []
        try:
            return search_similar(table, query, limit=limit, threshold=0.1) or []
        except Exception:
            return []

    return {
        "event": event,
        "attendee_contacts": attendee_contacts,
        "insights": _semantic("insights", 5),
        "changes": _semantic("change", 3),
        "proof_points": _semantic("proof_points", 3),
    }


# ---------------------------------------------------------------------------
# Training state — per-user progress + curriculum position.
# ---------------------------------------------------------------------------


def gather_training_state(user_id: str) -> dict:
    """Fetch a user's training state: record, progress, curriculum position.

    Returns plain dicts — no LLM calls. ``curriculum_position`` is a
    human-readable string (e.g. "The Foundation, chapter 2 of 4"). When the
    curriculum lookup fails (unknown role, bad stage index), falls back to
    "Stage {stage}, chapter {chapter}".
    """
    data = graphql(
        """
        query($id: UUID!) {
          userById(id: $id) {
            id name role email currentStage currentChapter streak
          }
          allTrainingProgressesList(condition: {userId: $id}) {
            area score lastSeenAt
          }
        }
        """,
        {"id": user_id},
    )

    user = data.get("userById") or {}
    progress = data.get("allTrainingProgressesList", []) or []

    stage = user.get("currentStage") or 0
    chapter = user.get("currentChapter") or 0
    streak = user.get("streak") or 0
    role = user.get("role") or ""

    # Lazy import: dependency arrow is training -> mothertree, not the other
    # way around. Mirrors the pattern in _summarize_training().
    curriculum_position = f"Stage {stage}, chapter {chapter}"
    try:
        from training.curriculum import get_stage_name, get_total_chapters

        stage_name = get_stage_name(role, stage)
        total = get_total_chapters(role, stage)
        curriculum_position = f"{stage_name}, chapter {chapter + 1} of {total}"
    except Exception:
        pass

    return {
        "user": user,
        "progress": progress,
        "current_stage": stage,
        "current_chapter": chapter,
        "streak": streak,
        "curriculum_position": curriculum_position,
    }


# ---------------------------------------------------------------------------
# Account — company + contacts + opportunities + engagements + plan.
# ---------------------------------------------------------------------------


def gather_account(
    company_name: str | None = None,
    company_id: str | None = None,
) -> dict:
    """Gather all account-level data for one company.

    Accepts either ``company_name`` (resolved via case-insensitive match) or
    ``company_id`` (UUID). Raises ``ValueError`` if neither is supplied.
    Returns plain dicts — no LLM calls.

    The returned dict includes ``engagements`` in addition to the spec's
    core fields because the QBR caller needs them and the shape stays
    strictly additive.

    Returns:
        ``{"company": {...}, "contacts": [...], "opportunities": [...],
           "interactions": [...], "signals": [...],
           "account_plan": {...} | None, "engagements": [...]}``.
    """
    if company_id is None and company_name is None:
        raise ValueError("gather_account requires company_id or company_name")

    # Resolve name -> id if needed.
    if company_id is None:
        lookup = graphql(
            """
            query($name: String!) {
              allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) {
                id name
              }
            }
            """,
            {"name": company_name},
        )
        matches = lookup.get("allCompaniesList", []) or []
        if not matches:
            return {
                "company": None,
                "contacts": [],
                "opportunities": [],
                "interactions": [],
                "signals": [],
                "account_plan": None,
                "engagements": [],
            }
        company_id = matches[0]["id"]

    data = graphql(
        """
        query($cid: UUID!) {
          companyById(id: $cid) {
            id name industry market notes ownerUserId
          }
          allContactsList(condition: {companyId: $cid}) {
            id name role temperature notes lastContact
          }
          allOpportunitiesList(condition: {companyId: $cid}) {
            id stage title notes nextAction nextActionDate ownerUserId
          }
          allInteractionsList(
            filter: {contactByContactId: {companyId: {equalTo: $cid}}},
            first: 20,
            orderBy: DATE_DESC
          ) {
            id type summary date
            contactByContactId { name }
          }
          allSignalsList(
            filter: {companyByCompanyId: {id: {equalTo: $cid}}},
            first: 20,
            orderBy: CREATED_AT_DESC
          ) {
            id content source createdAt
          }
          allAccountPlansList(condition: {companyId: $cid}, first: 1) {
            id qbrNotes qbrAt nextQbr
          }
          allEngagementsList(condition: {companyId: $cid}) {
            id title status type serviceMeetingNotes
          }
        }
        """,
        {"cid": company_id},
    )

    plans = data.get("allAccountPlansList", []) or []
    return {
        "company": data.get("companyById"),
        "contacts": data.get("allContactsList", []) or [],
        "opportunities": data.get("allOpportunitiesList", []) or [],
        "interactions": data.get("allInteractionsList", []) or [],
        "signals": data.get("allSignalsList", []) or [],
        "account_plan": plans[0] if plans else None,
        "engagements": data.get("allEngagementsList", []) or [],
    }


# ---------------------------------------------------------------------------
# User resolution — fuzzy lookup with explicit ambiguity signalling.
# ---------------------------------------------------------------------------


class AmbiguousUserError(Exception):
    """Raised when resolve_user finds multiple matches — caller should ask for clarification."""

    def __init__(self, matches: list[dict]):
        self.matches = matches
        names = ", ".join(m.get("name", m.get("email", "?")) for m in matches)
        super().__init__(f"Ambiguous user reference — matches: {names}")


def resolve_user(name_or_email: str) -> dict | None:
    """Resolve a user by email (exact) or partial name (case-insensitive).

    Returns:
        - Single match: the user dict.
        - No match: ``None``.
        - Multiple matches: raises :class:`AmbiguousUserError` with matches.

    Uses a parameterized GraphQL query — ``name_or_email`` is never
    interpolated via f-strings.
    """
    q = (name_or_email or "").strip()
    if not q:
        return None

    if "@" in q:
        result = graphql(
            """
            query($q: String!) {
              allUsersList(condition: {email: $q}, first: 5) {
                id email name role active currentStage currentChapter streak
              }
            }
            """,
            {"q": q.lower()},
        )
    else:
        result = graphql(
            """
            query($q: String!) {
              allUsersList(filter: {name: {includesInsensitive: $q}}, first: 5) {
                id email name role active currentStage currentChapter streak
              }
            }
            """,
            {"q": q},
        )

    matches = result.get("allUsersList", []) or []
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    raise AmbiguousUserError(matches)


# ---------------------------------------------------------------------------
# Brief — cross-table semantic + text search on a query.
# ---------------------------------------------------------------------------

# Tables searched semantically for brief.
# Each tuple is (table_name, result_key_in_return_dict).
_BRIEF_SEMANTIC_TABLES = [
    ("change", "changes"),
    ("worldview", "worldviews"),
    ("competitors", "competitors"),
    ("insights", "insights"),
    ("proof_points", "proof_points"),
]


def gather_brief(query: str) -> dict:
    """Cross-table semantic + text search on a free-form query.

    Combines:
    - Text search (via GraphQL `includesInsensitive`) across contacts,
      companies, signals, and interactions.
    - Semantic search (via pgvector cosine distance) across change,
      worldview, competitors, insights, and proof_points.

    No LLM calls here — returns plain dicts per table. Synthesize with
    :func:`synthesize_brief`.

    Args:
        query: Free-form text, e.g. a company name, topic, or person.

    Returns:
        {
            "query": str,
            "contacts": [...],        # name/role/notes text matches
            "companies": [...],       # name/industry/notes text matches
            "signals": [...],         # content text matches
            "interactions": [...],    # summary text matches
            "changes": [...],         # semantic matches
            "worldviews": [...],      # semantic matches
            "competitors": [...],     # semantic matches
            "insights": [...],        # semantic matches
            "proof_points": [...],    # semantic matches
        }
    """
    result = {
        "query": query,
        "contacts": [],
        "companies": [],
        "signals": [],
        "interactions": [],
        "changes": [],
        "worldviews": [],
        "competitors": [],
        "insights": [],
        "proof_points": [],
    }

    # Text search across relational tables. Parameterized — never interpolate.
    try:
        text_data = graphql(
            """
            query($q: String!) {
              allContactsList(filter: {or: [{name: {includesInsensitive: $q}}, {notes: {includesInsensitive: $q}}, {role: {includesInsensitive: $q}}]}, first: 10) {
                name role notes temperature lastContact
                companyByCompanyId { name industry }
              }
              allCompaniesList(filter: {or: [{name: {includesInsensitive: $q}}, {industry: {includesInsensitive: $q}}, {notes: {includesInsensitive: $q}}]}, first: 5) {
                name industry market notes
              }
              allSignalsList(filter: {content: {includesInsensitive: $q}}, first: 10, orderBy: CREATED_AT_DESC) {
                content source createdAt
              }
              allInteractionsList(filter: {summary: {includesInsensitive: $q}}, first: 10, orderBy: DATE_DESC) {
                summary type date nextAction
                contactByContactId { name }
              }
            }
            """,
            {"q": query},
        )
        result["contacts"] = text_data.get("allContactsList", []) or []
        result["companies"] = text_data.get("allCompaniesList", []) or []
        result["signals"] = text_data.get("allSignalsList", []) or []
        result["interactions"] = text_data.get("allInteractionsList", []) or []
    except Exception:
        # Swallow — leave text tables as empty lists.
        pass

    # Semantic search across CI tables in parallel.
    def _search(entry):
        table, key = entry
        try:
            hits = search_similar(table, query, limit=5, threshold=0.1)
        except Exception:
            hits = []
        return key, hits

    with ThreadPoolExecutor(max_workers=len(_BRIEF_SEMANTIC_TABLES)) as pool:
        for key, hits in pool.map(_search, _BRIEF_SEMANTIC_TABLES):
            result[key] = hits or []

    return result


def _format_brief_data(data: dict) -> str:
    """Render a gather_brief() result as a readable prompt body.

    Deterministic — no LLM calls. Sections are omitted when empty.
    """
    sections: list[str] = []

    contacts = data.get("contacts") or []
    if contacts:
        lines = []
        for c in contacts:
            company = c.get("companyByCompanyId") or {}
            company_str = f" at {company['name']}" if company.get("name") else ""
            lines.append(
                f"- {c.get('name', '?')} ({c.get('role') or 'unknown'}){company_str} "
                f"— {c.get('temperature', 'cold')}"
            )
            notes = c.get("notes")
            if notes:
                lines.append(f"  Notes: {notes[:200]}")
        sections.append("Contacts:\n" + "\n".join(lines))

    companies = data.get("companies") or []
    if companies:
        sections.append(
            "Companies:\n"
            + "\n".join(
                f"- {co.get('name', '?')} ({co.get('industry') or 'unknown'}) "
                f"{(co.get('notes') or '')[:150]}"
                for co in companies
            )
        )

    signals = data.get("signals") or []
    if signals:
        sections.append(
            "Recent signals:\n"
            + "\n".join(
                f"- [{s.get('source', '?')}] {(s.get('content') or '')[:150]}"
                for s in signals
            )
        )

    interactions = data.get("interactions") or []
    if interactions:
        sections.append(
            "Interactions:\n"
            + "\n".join(
                f"- {(i.get('date') or '')[:10]} {i.get('type', '?')}: "
                f"{(i.get('summary') or '')[:150]}"
                for i in interactions
            )
        )

    # Semantic sections.
    semantic_blocks = [
        ("changes", "Relevant change statements", lambda r: r.get("statement", "")),
        ("worldviews", "Relevant worldviews", lambda r: r.get("belief", "")),
        (
            "competitors",
            "Relevant competitive positioning",
            lambda r: f"vs {r.get('type', '')}: {r.get('positioning', '')}",
        ),
        (
            "insights",
            "Relevant insights",
            lambda r: f"[{r.get('category', '')}] {r.get('reframe', '')}",
        ),
        ("proof_points", "Relevant proof points", lambda r: r.get("outcome", "")),
    ]
    for key, label, fmt in semantic_blocks:
        items = data.get(key) or []
        if items:
            sections.append(
                f"{label}:\n"
                + "\n".join(
                    f"- {fmt(r)} ({_format_similarity(r.get('similarity'))})"
                    for r in items
                )
            )

    return "\n\n".join(sections)


_BRIEF_SYSTEM_PROMPT = (
    "You are Mother Tree providing a briefing on '{query}'. "
    "Synthesize what we know across contacts, companies, signals, interactions, "
    "change statements, worldviews, competitive positioning, insights, and proof points. "
    "Be concise and actionable. Lead with what matters most for a consultative sales "
    "conversation. If a section is empty, omit it — don't say 'we have no data on X'. "
    "Use Slack formatting (*bold*, bullets)."
)


def synthesize_brief(
    data: dict,
    query: str,
    model: str | None = None,
    on_chunk=None,
) -> str:
    """Generate a narrative briefing from a gather_brief() dict.

    Args:
        data: Output of gather_brief(query).
        query: The original query string — used in the system prompt and the
            empty-data short-circuit.
        model: Optional override for the generation model.
        on_chunk: Optional streaming callback. If provided, streams chunks via
            chat_conversation; otherwise a single generate() call.

    Returns:
        Briefing text. Returns a short "no information found" message without
        calling the LLM when every result list in ``data`` is empty.
    """
    # Short-circuit when nothing was found — save tokens and respond fast.
    result_keys = (
        "contacts",
        "companies",
        "signals",
        "interactions",
        "changes",
        "worldviews",
        "competitors",
        "insights",
        "proof_points",
    )
    if not any(data.get(k) for k in result_keys):
        return f"No information found for '{query}'."

    system = _BRIEF_SYSTEM_PROMPT.format(query=query)
    body = _format_brief_data(data)
    user_prompt = f"Briefing query: {query}\n\nData:\n{body}"

    if on_chunk is not None:
        from mothertree.llm import chat_conversation
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        return chat_conversation(messages, model=model, on_chunk=on_chunk)

    if model is not None:
        return generate(system, user_prompt, model=model)
    return generate(system, user_prompt)
