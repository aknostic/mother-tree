#!/usr/bin/env python3
"""Mother Tree content ingestion CLI.

Usage:
  ingest foundation file <path>              # Single markdown file
  ingest foundation dir <path>               # All .md files in directory
  ingest foundation repo <path>              # All .md files in git repo
  ingest foundation url <url>                # Single web page
  ingest foundation sitemap <url> [--filter /path1 /path2]

  ingest narrative file <path>               # Single markdown file
  ingest narrative dir <path>                # All .md files in directory
  ingest narrative repo <path>               # All .md files in git repo
  ingest narrative url <url>                 # Single web page
  ingest narrative sitemap <url> [--filter /path1 /path2]

  ingest consolidate                          # Run Seth's consolidation pass
  ingest truncate [table ...]                 # Truncate CI tables (all if none specified)
  ingest stats                                # Show database counts

Same source can be ingested as both foundation and narrative — they extract
different things. Foundation extracts positioning (change, worldview, personas,
competitors). Narrative extracts insights (reframes for sales conversations).

Foundation: run after significant content changes.
Narrative: run on a recurring schedule to keep insights fresh.

Each invocation replaces records for that source and exits.
"""

import hashlib
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

from ingestion.extract import extract_foundation, extract_narrative
from ingestion.profile import classify_document, extract_profile, merge_elements
from ingestion.sources import fetch_page_content, fetch_sitemap_urls, filter_urls, read_repo_markdown
from ingestion.validate import (
    score_insights_multi_model,
    validate_change,
    validate_competitor,
    validate_insight,
    validate_persona,
    validate_worldview,
)
from mothertree.config import CONFIDENCE_AUTO_REJECT, GENERATION_MODEL
from mothertree.graphql_client import (
    check_ingestion_log,
    delete_by_source,
    get_persona_id_by_name,
    graphql,
    insert_change,
    insert_competitor,
    insert_insight,
    insert_persona,
    insert_proof_point,
    insert_worldview,
    update_ingestion_log,
)


def source_key(source_type: str, identifier: str) -> str:
    return f"{source_type}:{identifier}"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def should_skip(source: str, content: str) -> bool:
    """Check if this content has already been ingested unchanged."""
    h = content_hash(content)
    if check_ingestion_log(source, h):
        return True
    return False


def log_ingestion(source: str, content: str, stats: dict):
    """Record successful ingestion."""
    h = content_hash(content)
    update_ingestion_log(source, h, stats)


def process_foundation(content: str, source: str):
    """Extract and insert foundation records from content."""
    stats = {"change": 0, "worldview": 0, "personas": 0, "competitors": 0, "rejected": 0}

    # Replace per source
    for table in ("change", "worldview", "personas", "competitors"):
        deleted = delete_by_source(table, source)
        if deleted:
            print(f"  Replaced {deleted} {table}")

    try:
        records = extract_foundation(content)
    except Exception as e:
        print(f"  Extraction error: {e}")
        return stats

    for record in records:
        record_type = record.pop("type", None)
        if not record_type:
            continue

        try:
            if record_type == "change":
                validated, errors = validate_change(record)
                if errors:
                    print(f"  Validation ({record_type}): {errors}")
                if validated is None:
                    stats["rejected"] += 1
                    continue
                validated["source"] = source
                insert_change(validated)
                stats["change"] += 1

            elif record_type == "worldview":
                validated, errors = validate_worldview(record)
                if errors:
                    print(f"  Validation ({record_type}): {errors}")
                if validated is None:
                    stats["rejected"] += 1
                    continue
                persona_name = validated.pop("persona_name", None)
                if persona_name:
                    pid = get_persona_id_by_name(persona_name)
                    if pid:
                        validated["persona_id"] = pid
                validated["source"] = source
                insert_worldview(validated)
                stats["worldview"] += 1

            elif record_type == "persona":
                validated, errors = validate_persona(record)
                if errors:
                    print(f"  Validation ({record_type}): {errors}")
                if validated is None:
                    stats["rejected"] += 1
                    continue
                validated["source"] = source
                insert_persona(validated)
                stats["personas"] += 1

            elif record_type == "competitor":
                if "competitor_type" in record:
                    record["type"] = record.pop("competitor_type")
                validated, errors = validate_competitor(record)
                if errors:
                    print(f"  Validation ({record_type}): {errors}")
                if validated is None:
                    stats["rejected"] += 1
                    continue
                validated["source"] = source
                insert_competitor(validated)
                stats["competitors"] += 1

        except Exception as e:
            print(f"  Insert error ({record_type}): {e}")
            stats["rejected"] += 1

    # Also extract org profile elements from the same content
    try:
        profile_elements = extract_profile(content)
        if profile_elements:
            profile_stats = merge_elements(profile_elements)
            stats["profile"] = profile_stats
    except Exception as e:
        log.warning("Profile extraction failed: %s", e)

    return stats


def process_narrative(content: str, source: str):
    """Extract, score, and insert narrative insights and proof points from content."""
    stats = {"insights": 0, "proof_points": 0, "rejected": 0, "flagged": 0}

    deleted = delete_by_source("insights", source)
    if deleted:
        print(f"  Replaced {deleted} insights")
    deleted_pp = delete_by_source("proof_points", source)
    if deleted_pp:
        print(f"  Replaced {deleted_pp} proof points")

    try:
        raw = extract_narrative(content)
    except Exception as e:
        print(f"  Extraction error: {e}")
        return stats

    # Separate insights from proof points
    proof_points = [r for r in raw if r.get("type") == "proof_point"]
    insights_raw = [r for r in raw if r.get("type") != "proof_point"]

    # Process proof points (no multi-model scoring — these are factual)
    for pp in proof_points:
        pp.pop("type", None)
        if pp.get("outcome"):
            pp["source"] = source
            try:
                insert_proof_point(pp)
                stats["proof_points"] += 1
            except Exception as e:
                print(f"  Proof point insert error: {e}")

    valid = []
    for insight in insights_raw:
        insight.pop("type", None)  # remove "insight" type marker
        validated, errors = validate_insight(insight)
        if errors:
            print(f"  Validation: {errors}")
        if validated is None:
            stats["rejected"] += 1
            continue
        valid.append(validated)

    if not valid:
        return stats

    scored = score_insights_multi_model(valid)
    for insight in scored:
        if insight["confidence"] <= CONFIDENCE_AUTO_REJECT:
            stats["rejected"] += 1
            continue
        insight.pop("scores", None)
        insight.pop("triage_reason", None)
        insight["source"] = source
        if insight.get("flagged"):
            stats["flagged"] += 1
        try:
            insert_insight(insight)
            stats["insights"] += 1
        except Exception as e:
            print(f"  Insert error: {e}")
            stats["rejected"] += 1

    return stats


# --- Classified ingestion (single source for all commands) ---

def ingest_classified(files: list[dict], force: bool = False, lens: str = "both") -> dict:
    """Classify each file and route to foundation, narrative, or both.

    lens: "foundation" — only extract foundation, skip narrative even for mixed/narrative docs
          "narrative"  — only extract narrative, skip foundation even for mixed/foundation docs
          "both"       — extract both (default)

    Returns combined totals for all extraction types.
    """
    totals = {
        "foundation": {"change": 0, "worldview": 0, "personas": 0, "competitors": 0, "rejected": 0},
        "narrative": {"insights": 0, "rejected": 0, "flagged": 0},
        "classification": {"foundation": 0, "narrative": 0, "mixed": 0, "irrelevant": 0, "unknown": 0, "skipped": 0},
    }
    total = len(files)
    for i, f in enumerate(files, 1):
        path = f.get("path", "unknown")

        # Skip unchanged — check the source key for the active lens
        f_source = source_key("foundation", path)
        n_source = source_key("narrative", path)
        skip_source = n_source if lens == "narrative" else f_source
        if not force and should_skip(skip_source, f["content"]):
            print(f"  [{i}/{total}] {path} — unchanged, skipping", flush=True)
            totals["classification"]["skipped"] += 1
            continue

        # Classify
        doc_type = classify_document(f["content"])
        print(f"  [{i}/{total}] {path} → {doc_type}", flush=True)
        totals["classification"][doc_type] = totals["classification"].get(doc_type, 0) + 1

        # Retry unknown classification once
        if doc_type == "unknown":
            doc_type = classify_document(f["content"])
            print(f"    retry → {doc_type}", flush=True)

        # Route — respect lens restriction
        do_foundation = lens in ("foundation", "both") and doc_type in ("foundation", "mixed")
        do_narrative = lens in ("narrative", "both") and doc_type in ("narrative", "mixed")

        if do_foundation:
            stats = process_foundation(f["content"], f_source)
            log_ingestion(f_source, f["content"], stats)
            for k in totals["foundation"]:
                totals["foundation"][k] += stats.get(k, 0)

        if do_narrative:
            stats = process_narrative(f["content"], n_source)
            log_ingestion(n_source, f["content"], stats)
            for k in totals["narrative"]:
                totals["narrative"][k] += stats.get(k, 0)

        # irrelevant and still-unknown: skip

    # Post-ingest consolidation
    if lens in ("foundation", "both"):
        any_foundation = totals["foundation"]["change"] + totals["foundation"]["worldview"] + totals["foundation"]["personas"] + totals["foundation"]["competitors"]
        if any_foundation > 0:
            print("\n  Consolidating foundation...", flush=True)
            cons = consolidate_foundation()
            print(f"  Consolidation: {cons}", flush=True)
            print("  Consolidating organization profile...", flush=True)
            profile_stats = consolidate_organization_profile()
            print(f"  Profile: {profile_stats}", flush=True)

    return totals


def _reassign_worldview_persona(old_persona_id: str, new_persona_id: str | None):
    """Reassign worldview rows from one persona to another (or null) before deletion."""
    result = graphql("""
    query($pid: UUID!) {
        allWorldviewsList(condition: {personaId: $pid}) { id }
    }
    """, {"pid": old_persona_id})
    rows = result.get("allWorldviewsList", [])
    for row in rows:
        graphql("""
        mutation($id: UUID!, $patch: WorldviewPatch!) {
            updateWorldviewById(input: {id: $id, worldviewPatch: $patch}) { worldview { id } }
        }
        """, {"id": row["id"], "patch": {"personaId": new_persona_id}})


def consolidate_foundation() -> dict:
    """Seth's consolidation pass — deduplicate and sharpen each foundation table.

    Runs after all documents are ingested. For each table, fetches all records,
    asks Seth to identify the sharpest unique set, then removes the rest.
    """
    from mothertree.llm import consolidate as llm_consolidate

    SETH_CONSOLIDATE = """You are Seth Godin reviewing foundation data for a consultative sales team.

Your job: consolidate. Remove duplicates, merge near-duplicates into the sharpest version,
and flag records that don't belong.

For each record, decide:
- KEEP: sharp, unique, specific. Worth having.
- REMOVE: duplicate, near-duplicate, or too vague. Index of the better version if it's a duplicate.

Be aggressive about removing redundancy. 5 sharp statements beat 20 vague ones.
But don't remove something just because it's similar — only if a better version exists.

Return JSON: {"decisions": [{"index": 0, "decision": "KEEP|REMOVE", "better_index": null, "reason": "..."}]}
For REMOVE decisions, set better_index to the index of the superior record this is a duplicate of (or null if just vague/irrelevant)."""

    stats = {"kept": 0, "removed": 0}

    BATCH_SIZE = 30  # Small enough for reliable JSON output

    TABLE_MAP = {
        "change": ("allChangesList", "CONFIDENCE_DESC"),
        "worldview": ("allWorldviewsList", "CONFIDENCE_DESC"),
        "personas": ("allPersonasList", "CONFIDENCE_DESC"),
        "competitors": ("allCompetitorsList", "CONFIDENCE_DESC"),
    }
    DELETE_MAP = {
        "change": ("deleteChangeById", "change"),
        "worldview": ("deleteWorldviewById", "worldview"),
        "personas": ("deletePersonaById", "persona"),
        "competitors": ("deleteCompetitorById", "competitor"),
    }
    for table, field in [("change", "statement"), ("worldview", "belief"), ("personas", "name"), ("competitors", "type")]:
        print(f"\n  Consolidating {table}...", flush=True)
        gql_name, order = TABLE_MAP[table]
        result = graphql(f"{{ {gql_name}(orderBy: {order}) {{ id {field} }} }}")
        rows = result.get(gql_name, [])
        if len(rows) <= 5:
            print(f"    {len(rows)} records — no consolidation needed", flush=True)
            stats["kept"] += len(rows)
            continue

        # Process in batches — each batch sees what was kept so far
        total_removed = 0
        kept_values = []  # Field values of records kept so far
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]
            items = "\n".join(f"[{i}] {r[field]}" for i, r in enumerate(batch))
            context = ""
            if kept_values:
                context = "\n\nALREADY KEPT (remove duplicates of these):\n" + "\n".join(f"- {v}" for v in kept_values)
            try:
                messages = [
                    {"role": "system", "content": SETH_CONSOLIDATE},
                    {"role": "user", "content": f"Consolidate these {len(batch)} {table} records:\n{items}{context}"},
                ]
                result = llm_consolidate(messages, model=GENERATION_MODEL)
                decisions = result.get("decisions", [])

                removed_indices = set()
                for d in decisions:
                    idx = d.get("index")
                    if d.get("decision") == "REMOVE" and idx is not None and idx < len(batch):
                        # Reassign worldview FKs before deleting a persona
                        if table == "personas":
                            better_idx = d.get("better_index")
                            target_id = batch[better_idx]["id"] if better_idx is not None and better_idx < len(batch) else None
                            _reassign_worldview_persona(batch[idx]["id"], target_id)
                        del_mutation, del_result = DELETE_MAP[table]
                        graphql(f"""
mutation($id: UUID!) {{
    {del_mutation}(input: {{id: $id}}) {{ {del_result} {{ id }} }}
}}
""", {"id": batch[idx]["id"]})
                        removed_indices.add(idx)
                total_removed += len(removed_indices)

                # Track kept values for cross-batch dedup
                for i, r in enumerate(batch):
                    if i not in removed_indices:
                        kept_values.append(r[field])

            except Exception as e:
                # On failure, assume all kept
                for r in batch:
                    kept_values.append(r[field])
                print(f"    Batch {batch_start // BATCH_SIZE + 1} failed: {e}", flush=True)

        kept = len(rows) - total_removed
        stats["removed"] += total_removed
        stats["kept"] += kept
        print(f"    {len(rows)} → {kept} ({total_removed} removed)", flush=True)

    return stats


def consolidate_insights() -> dict:
    """Lawrence's consolidation pass — deduplicate insights per category.

    For each category, fetches all insights, asks Lawrence to identify
    the sharpest unique set, then removes the rest.
    """
    from mothertree.llm import consolidate as llm_consolidate

    LAWRENCE_CONSOLIDATE = """You are Lawrence Miller, a consultative selling expert reviewing sales insights.

Your job: consolidate. Remove duplicates and near-duplicates, keeping only the sharpest version of each insight.

Two insights are duplicates if they make the same core reframe — even if the wording differs or the source is different.
Keep the version with the stronger evidence, more specific trigger, or more actionable next step.

For each record, decide:
- KEEP: unique reframe, strong evidence, actionable. Worth having in a hunter's toolkit.
- REMOVE: says the same thing as another insight, or too generic to use in a real conversation.

Return JSON: {"decisions": [{"index": 0, "decision": "KEEP|REMOVE", "better_index": null, "reason": "..."}]}
For REMOVE decisions, set better_index to the index of the superior record this is a duplicate of (or null if just weak)."""

    BATCH_SIZE = 20  # Smaller batches — insights are longer than foundation records

    # Get categories
    result = graphql("{ allInsightsList { id category reframe } }")
    all_insights = result.get("allInsightsList", [])

    categories = {}
    for ins in all_insights:
        cat = ins.get("category", "unknown")
        categories.setdefault(cat, []).append(ins)

    stats = {"kept": 0, "removed": 0}

    for cat, rows in sorted(categories.items()):
        print(f"\n  Consolidating insights/{cat} ({len(rows)})...", flush=True)
        if len(rows) <= 5:
            print(f"    {len(rows)} records — no consolidation needed", flush=True)
            stats["kept"] += len(rows)
            continue

        total_removed = 0
        kept_values = []
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]
            items = "\n".join(f"[{i}] {r['reframe'][:200]}" for i, r in enumerate(batch))
            context = ""
            if kept_values:
                context = "\n\nALREADY KEPT (remove duplicates of these):\n" + "\n".join(f"- {v}" for v in kept_values[-30:])
            try:
                messages = [
                    {"role": "system", "content": LAWRENCE_CONSOLIDATE},
                    {"role": "user", "content": f"Consolidate these {len(batch)} '{cat}' insights:\n{items}{context}"},
                ]
                result = llm_consolidate(messages, model=GENERATION_MODEL)
                decisions = result.get("decisions", [])

                removed_indices = set()
                for d in decisions:
                    idx = d.get("index")
                    if d.get("decision") == "REMOVE" and idx is not None and idx < len(batch):
                        graphql("""
mutation($id: UUID!) {
    deleteInsightById(input: {id: $id}) { insight { id } }
}
""", {"id": batch[idx]["id"]})
                        removed_indices.add(idx)
                total_removed += len(removed_indices)

                for i, r in enumerate(batch):
                    if i not in removed_indices:
                        kept_values.append(r["reframe"][:200])

            except Exception as e:
                for r in batch:
                    kept_values.append(r["reframe"][:200])
                print(f"    Batch {batch_start // BATCH_SIZE + 1} failed: {e}", flush=True)

        kept = len(rows) - total_removed
        stats["removed"] += total_removed
        stats["kept"] += kept
        print(f"    {len(rows)} → {kept} ({total_removed} removed)", flush=True)

    return stats


def consolidate_organization_profile() -> dict:
    """Consolidate organization profile elements after foundation consolidation.

    Fetches all raw profile elements, runs Seth's consolidation,
    replaces stale entries with consolidated ones.
    """
    from ingestion.profile import consolidate_profile, merge_elements
    from mothertree.graphql_client import delete_all_organization, get_organization_profile

    stats = {"consolidated": 0, "skipped": False}
    elements = get_organization_profile()
    if not elements:
        print("  No profile elements to consolidate")
        stats["skipped"] = True
        return stats

    # Convert from GraphQL camelCase to consolidate_profile's expected format
    normalized = [{"type": e.get("element_type", ""), "content": e.get("content", "")} for e in elements]
    consolidated = consolidate_profile(normalized)
    if consolidated:
        delete_all_organization()
        merge_stats = merge_elements(consolidated)
        stats["consolidated"] = merge_stats.get("inserted", 0)
        print(f"  Profile: {stats['consolidated']} consolidated elements")
    return stats


def cmd_foundation_repo(path: str, force: bool = False):
    """Ingest all .md files in a git repo — foundation lens only."""
    files = read_repo_markdown(path)
    print(f"Ingestion repo: {path} ({len(files)} files)", flush=True)
    totals = ingest_classified(files, force=force, lens="foundation")
    print(f"\nClassification: {totals['classification']}", flush=True)
    print(f"Foundation: {totals['foundation']}", flush=True)
    print(f"Narrative: {totals['narrative']}", flush=True)


def cmd_foundation_url(url: str, force: bool = False):
    """Ingest a single web page — foundation lens only."""
    print(f"Ingestion URL: {url}", flush=True)
    content = fetch_page_content(url)
    if not content:
        print("  No content found")
        sys.exit(1)
    files = [{"path": url, "content": content}]
    totals = ingest_classified(files, force=force, lens="foundation")
    print(f"\nClassification: {totals['classification']}", flush=True)
    print(f"Foundation: {totals['foundation']}", flush=True)
    print(f"Narrative: {totals['narrative']}", flush=True)


def cmd_foundation_sitemap(url: str, filters: list[str] = None, force: bool = False):
    """Ingest all pages from a sitemap — classify and route."""
    urls = fetch_sitemap_urls(url)
    if filters:
        urls = filter_urls(urls, filters)
    print(f"Ingestion sitemap: {url} ({len(urls)} URLs)", flush=True)
    # Fetch all pages first, then classify and route
    files = []
    total = len(urls)
    for i, entry in enumerate(urls, 1):
        page_url = entry["url"]
        print(f"  [{i}/{total}] Fetching {page_url}...", flush=True)
        content = fetch_page_content(page_url)
        if not content:
            print("    no content, skipped", flush=True)
            continue
        files.append({"path": page_url, "content": content})
    print(f"  Fetched {len(files)} pages, classifying and extracting...", flush=True)
    totals = ingest_classified(files, force=force, lens="foundation")
    print(f"\nClassification: {totals['classification']}", flush=True)
    print(f"Foundation: {totals['foundation']}", flush=True)
    print(f"Narrative: {totals['narrative']}", flush=True)


def cmd_foundation_file(path: str, force: bool = False):
    """Ingest a single file — foundation lens only."""
    p = Path(path)
    if not p.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    content = p.read_text(encoding="utf-8")
    files = [{"path": str(p.resolve()), "content": content}]
    totals = ingest_classified(files, force=force, lens="foundation")
    print(f"\nClassification: {totals['classification']}", flush=True)
    print(f"Foundation: {totals['foundation']}", flush=True)
    print(f"Narrative: {totals['narrative']}", flush=True)


def cmd_foundation_dir(path: str, force: bool = False):
    """Ingest all .md files in a directory — foundation lens only."""
    p = Path(path)
    if not p.is_dir():
        print(f"Not a directory: {path}")
        sys.exit(1)
    md_files = sorted(p.glob("*.md"))
    files = []
    for f in md_files:
        content = f.read_text(encoding="utf-8")
        if len(content) >= 100:
            files.append({"path": str(f.resolve()), "content": content})
    print(f"Ingestion dir: {p} ({len(files)} files)", flush=True)
    totals = ingest_classified(files, force=force, lens="foundation")
    print(f"\nClassification: {totals['classification']}", flush=True)
    print(f"Foundation: {totals['foundation']}", flush=True)
    print(f"Narrative: {totals['narrative']}", flush=True)


# Narrative commands — no classification, process everything as narrative.
# Foundation data already exists and is used as context by the narrative prompt.

def cmd_narrative_file(path: str, force: bool = False):
    """Ingest a single file as narrative."""
    p = Path(path)
    if not p.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    content = p.read_text(encoding="utf-8")
    source = source_key("narrative", str(p.resolve()))
    if not force and should_skip(source, content):
        print(f"  {p.name} — unchanged, skipping", flush=True)
        return
    print(f"  {p.name}...", flush=True)
    stats = process_narrative(content, source)
    log_ingestion(source, content, stats)
    print(f"  {stats}", flush=True)


def cmd_narrative_dir(path: str, force: bool = False):
    """Ingest all .md files in a directory as narrative."""
    p = Path(path)
    if not p.is_dir():
        print(f"Not a directory: {path}")
        sys.exit(1)
    md_files = sorted(p.glob("*.md"))
    files = [(f, f.read_text(encoding="utf-8")) for f in md_files if f.stat().st_size >= 100]
    total = len(files)
    print(f"Narrative dir: {p} ({total} files)", flush=True)
    totals = {"insights": 0, "rejected": 0, "flagged": 0, "skipped": 0}
    for i, (f, content) in enumerate(files, 1):
        source = source_key("narrative", str(f.resolve()))
        if not force and should_skip(source, content):
            print(f"  [{i}/{total}] {f.name} — unchanged, skipping", flush=True)
            totals["skipped"] += 1
            continue
        print(f"  [{i}/{total}] {f.name}...", flush=True)
        stats = process_narrative(content, source)
        log_ingestion(source, content, stats)
        for k in ("insights", "rejected", "flagged"):
            totals[k] += stats.get(k, 0)
    print(f"\nTotal: {totals}", flush=True)


def cmd_narrative_repo(path: str, force: bool = False):
    """Ingest all .md files in a git repo as narrative."""
    files = read_repo_markdown(path)
    total = len(files)
    print(f"Narrative repo: {path} ({total} files)", flush=True)
    totals = {"insights": 0, "rejected": 0, "flagged": 0, "skipped": 0}
    for i, f in enumerate(files, 1):
        source = source_key("narrative", f["path"])
        if not force and should_skip(source, f["content"]):
            print(f"  [{i}/{total}] {f['path']} — unchanged, skipping", flush=True)
            totals["skipped"] += 1
            continue
        print(f"  [{i}/{total}] {f['path']}...", flush=True)
        stats = process_narrative(f["content"], source)
        log_ingestion(source, f["content"], stats)
        for k in ("insights", "rejected", "flagged"):
            totals[k] += stats.get(k, 0)
    print(f"\nTotal: {totals}", flush=True)


def cmd_narrative_url(url: str, force: bool = False):
    """Ingest a single web page as narrative."""
    print(f"Narrative URL: {url}", flush=True)
    content = fetch_page_content(url)
    if not content:
        print("  No content found")
        sys.exit(1)
    source = source_key("narrative", url)
    if not force and should_skip(source, content):
        print("  Unchanged, skipping", flush=True)
        return
    stats = process_narrative(content, source)
    log_ingestion(source, content, stats)
    print(f"  {stats}", flush=True)


def cmd_narrative_sitemap(url: str, filters: list[str] = None, force: bool = False):
    """Ingest all pages from a sitemap as narrative."""
    urls = fetch_sitemap_urls(url)
    if filters:
        urls = filter_urls(urls, filters)
    total = len(urls)
    print(f"Narrative sitemap: {url} ({total} URLs)", flush=True)
    totals = {"insights": 0, "rejected": 0, "flagged": 0, "skipped": 0}
    for i, entry in enumerate(urls, 1):
        page_url = entry["url"]
        content = fetch_page_content(page_url)
        if not content:
            print(f"  [{i}/{total}] {page_url} — no content, skipped", flush=True)
            continue
        source = source_key("narrative", page_url)
        if not force and should_skip(source, content):
            print(f"  [{i}/{total}] {page_url} — unchanged, skipping", flush=True)
            totals["skipped"] += 1
            continue
        print(f"  [{i}/{total}] {page_url}...", flush=True)
        stats = process_narrative(content, source)
        log_ingestion(source, content, stats)
        for k in ("insights", "rejected", "flagged"):
            totals[k] += stats.get(k, 0)
    print(f"\nTotal: {totals}", flush=True)


def cmd_truncate():
    """Truncate CI tables by fetching all IDs then deleting one by one.

    If table names are passed as CLI args, only truncate those.
    Otherwise truncate all tables in FK-safe order.
    """
    # Tables with UUID primary key: (list_query, delete_mutation, result_field)
    TABLE_TRUNCATE = {
        "insights": ("allInsightsList", "deleteInsightById", "insight"),
        "worldview": ("allWorldviewsList", "deleteWorldviewById", "worldview"),
        "change": ("allChangesList", "deleteChangeById", "change"),
        "personas": ("allPersonasList", "deletePersonaById", "persona"),
        "competitors": ("allCompetitorsList", "deleteCompetitorById", "competitor"),
        "organization": ("allOrganizationsList", "deleteOrganizationById", "organization"),
    }
    # FK-safe default order
    DEFAULT_ORDER = ["insights", "worldview", "change", "personas", "competitors", "organization", "ingestion_log"]

    requested = sys.argv[2:] if len(sys.argv) > 2 else DEFAULT_ORDER
    known = set(TABLE_TRUNCATE.keys()) | {"ingestion_log"}
    unknown = [t for t in requested if t not in known]
    if unknown:
        print(f"Unknown tables: {', '.join(unknown)}")
        print(f"Available: {', '.join(DEFAULT_ORDER)}")
        sys.exit(1)

    for table in requested:
        try:
            if table == "ingestion_log":
                _truncate_ingestion_log()
            else:
                query_name, del_mutation, del_result = TABLE_TRUNCATE[table]
                result = graphql(f"{{ {query_name} {{ id }} }}")
                rows = result.get(query_name, [])
                for row in rows:
                    graphql(f"""
mutation($id: UUID!) {{
    {del_mutation}(input: {{id: $id}}) {{ {del_result} {{ id }} }}
}}
""", {"id": row["id"]})
                print(f"  {table:20s} {len(rows)} deleted", flush=True)
        except Exception as e:
            print(f"  {table:20s} ERROR: {e}", flush=True)


def _truncate_ingestion_log():
    """Truncate ingestion_log — uses source as PK, not UUID."""
    result = graphql("{ allIngestionLogsList { source } }")
    rows = result.get("allIngestionLogsList", [])
    for row in rows:
        graphql("""
mutation($source: String!) {
    deleteIngestionLogBySource(input: {source: $source}) { ingestionLog { source } }
}
""", {"source": row["source"]})
    print(f"  {'ingestion_log':20s} {len(rows)} deleted", flush=True)


def cmd_stats():
    """Show current database counts."""
    result = graphql("""
    {
      allChanges { totalCount }
      allWorldviews { totalCount }
      allPersonas { totalCount }
      allCompetitors { totalCount }
      allInsights { totalCount }
      allContacts { totalCount }
      allSignals { totalCount }
      allInteractions { totalCount }
    }
    """)
    TABLE_LABELS = {
        "allChanges": "change",
        "allWorldviews": "worldview",
        "allPersonas": "personas",
        "allCompetitors": "competitors",
        "allInsights": "insights",
        "allContacts": "contacts",
        "allSignals": "signals",
        "allInteractions": "interactions",
    }
    for key, data in result.items():
        name = TABLE_LABELS.get(key, key)
        count = data["totalCount"]
        print(f"  {name:20s} {count:>5}")


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "stats":
        cmd_stats()
        return

    if cmd == "consolidate":
        print("Seth consolidation pass...", flush=True)
        cons = consolidate_foundation()
        print(f"Consolidation: {cons}", flush=True)
        print("Organization profile consolidation...", flush=True)
        profile_stats = consolidate_organization_profile()
        print(f"Profile: {profile_stats}", flush=True)
        print("Lawrence consolidation pass (insights)...", flush=True)
        insight_stats = consolidate_insights()
        print(f"Insights: {insight_stats}", flush=True)
        return

    if cmd == "truncate":
        cmd_truncate()
        return

    if len(args) < 3:
        print(__doc__)
        sys.exit(1)

    source_type = args[0]  # foundation | narrative
    mode = args[1]         # file | dir | repo | url | sitemap
    target = args[2]       # path or URL

    # Parse flags
    force = "--force" in args
    filters = None
    if "--filter" in args:
        filter_idx = args.index("--filter")
        filters = [a for a in args[filter_idx + 1:] if not a.startswith("--")]

    if source_type == "foundation":
        if mode == "file":
            cmd_foundation_file(target, force)
        elif mode == "dir":
            cmd_foundation_dir(target, force)
        elif mode == "repo":
            cmd_foundation_repo(target, force)
        elif mode == "url":
            cmd_foundation_url(target, force)
        elif mode == "sitemap":
            cmd_foundation_sitemap(target, filters, force)
        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)

    elif source_type == "narrative":
        if mode == "file":
            cmd_narrative_file(target, force)
        elif mode == "dir":
            cmd_narrative_dir(target, force)
        elif mode == "repo":
            cmd_narrative_repo(target, force)
        elif mode == "url":
            cmd_narrative_url(target, force)
        elif mode == "sitemap":
            cmd_narrative_sitemap(target, filters, force)
        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)

    else:
        print(f"Unknown source type: {source_type}")
        sys.exit(1)


if __name__ == "__main__":
    main()
