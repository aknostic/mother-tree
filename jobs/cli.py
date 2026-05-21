#!/usr/bin/env python3
"""Mother Tree CLI.

Usage:
  mothertree ask <question>                # Ask Mother Tree
  mothertree ask saga <question>            # Ask Saga (positioning strategist)
  mothertree ask lena <question>            # Ask Lena (consultative diagnostician)
  mothertree ask trainer [topic]           # Ask the trainer

  mothertree ingest foundation file <path>
  mothertree ingest foundation dir <path>
  mothertree ingest foundation repo <path>
  mothertree ingest foundation url <url>
  mothertree ingest foundation sitemap <url> [--filter /path1 /path2]

  mothertree ingest narrative file <path>
  mothertree ingest narrative dir <path>
  mothertree ingest narrative repo <path>
  mothertree ingest narrative url <url>
  mothertree ingest narrative sitemap <url> [--filter /path1 /path2]

  mothertree ingest consolidate            # Run Saga's consolidation pass
  mothertree ingest truncate               # Truncate all CI tables
  mothertree ingest stats                  # Ingestion database counts

  mothertree dump <path>                   # Dump all tables to JSON
  mothertree restore <path>                # Restore all tables from JSON dump

  mothertree bot                           # Start Slack bot
  mothertree train deliver                 # Run daily training delivery
  mothertree train enroll <email> <name> <role>  # Enroll a user
  mothertree train status <email>          # Check enrollment status
  mothertree rhythm weekly                  # Weekly pipeline review
  mothertree rhythm weekly                 # Weekly pipeline review
  mothertree rhythm monthly                # Monthly retrospective
  mothertree rhythm calendar               # Calendar sync (prep + debrief)
  mothertree pulse scan                    # Run Pulse scanner (due reminders + stale + pipeline)
  mothertree calendar set <email> <ical_url>   # Set a user's calendar URL
  mothertree brief <query>                   # Cross-table briefing on a topic, company, or person
  mothertree pipeline [name|email]           # Pipeline review — global or scoped to a user
  mothertree profile                        # Show current organization profile
  mothertree profile consolidate            # Consolidate profile elements
  mothertree embed backfill [table]         # Generate embeddings for existing records
  mothertree stats                         # Database counts

Flags:
  --force    Re-ingest even if content unchanged
"""

import os
import sys

# Add jobs/ to path so mothertree package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "ask":
        from mothertree.ask import parse_ask_args
        persona, question = parse_ask_args(args[1:])
        if not persona and not question:
            print("Usage: mothertree ask <question>")
            print("       mothertree ask saga <question>")
            print("       mothertree ask lena <question>")
            print("       mothertree ask trainer [topic]")
            sys.exit(0)
        user_name = os.environ.get("USER", "you")
        # Route through character modules — same code as Slack bot
        if persona == "saga":
            from bot.characters.saga import respond
            print(respond(question=question, history=[], user_name=user_name))
        elif persona == "lena":
            from bot.characters.lena import respond
            print(respond(question=question, history=[], user_name=user_name))
        elif persona == "trainer":
            from mothertree.ask import ask
            print(ask("trainer", question, user_name=user_name))
        else:
            from bot.characters.mother_tree import respond
            print(respond(question=question, history=[], user_name=user_name))

    elif cmd == "brief":
        if len(args) < 2:
            print("Usage: mothertree brief <query>")
            print("Example: mothertree brief KPN")
            print("         mothertree brief 'NIS2 compliance'")
            sys.exit(1)
        query = " ".join(args[1:])
        from mothertree.intelligence import gather_brief, synthesize_brief
        data = gather_brief(query)
        print(synthesize_brief(data, query))

    elif cmd == "pipeline":
        from mothertree.intelligence import (
            AmbiguousUserError,
            gather_pipeline,
            resolve_user,
            synthesize_pipeline,
        )
        target = args[1] if len(args) > 1 else None
        if target:
            try:
                user = resolve_user(target)
            except AmbiguousUserError as e:
                print(f"Multiple users match '{target}':")
                for m in e.matches:
                    print(f"  - {m.get('name', '?')} <{m.get('email', '?')}>")
                sys.exit(1)
            if not user:
                print(f"No user found matching '{target}'")
                sys.exit(1)
            data = gather_pipeline(user_id=user["id"], target_name=user.get("name"))
            scope = "other"
        else:
            data = gather_pipeline()
            scope = "global"
        print(synthesize_pipeline(data, scope=scope))

    elif cmd == "ingest":
        from ingestion.ingest import main as ingest_main
        sys.argv = ["ingest"] + args[1:]
        ingest_main()

    elif cmd == "bot":
        from bot.bot import main as bot_main
        bot_main()

    elif cmd == "train":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "deliver":
            from training.deliver import main as deliver_main
            deliver_main()
        elif subcmd == "enroll":
            if len(args) < 5:
                print("Usage: mothertree train enroll <email> <name> <role>")
                print("Roles: hunter, gatherer, farmer, citizen")
                sys.exit(1)
            from training.operations import enroll
            result = enroll(args[2], args[3], args[4])
            print(result)
        elif subcmd == "status":
            if len(args) < 3:
                print("Usage: mothertree train status <email>")
                sys.exit(1)
            from mothertree.graphql_client import get_user_by_email
            user = get_user_by_email(args[2])
            if not user:
                print(f"No user found for {args[2]}")
            else:
                print(f"  Role:    {user.get('role')}")
                print(f"  Stage:   {user.get('currentStage')}")
                print(f"  Chapter: {user.get('currentChapter')}")
                print(f"  Streak:  {user.get('streak', 0)} days")
        elif subcmd == "pending":
            from mothertree.graphql_client import get_pending_enrollment_requests
            pending = get_pending_enrollment_requests()
            if not pending:
                print("No pending enrollment requests.")
            else:
                for req in pending:
                    print(f"  User {req['userId']} wants to enroll as {req['requestedRole']} — {req['createdAt'][:10]}")
        else:
            sys.argv = ["train"] + args[1:]
            from training.generate import main as gen_main
            gen_main()

    elif cmd in ("rhythm", "discipline"):
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "weekly":
            from discipline.weekly_review import main as weekly_main
            weekly_main()
        elif subcmd == "monthly":
            from discipline.monthly_retro import main as monthly_main
            monthly_main()
        elif subcmd == "calendar":
            from discipline.calendar_sync import main as calendar_main
            calendar_main()
        elif subcmd == "pulse":
            from pulse.scanner import run_scan
            run_scan()
        elif subcmd == "qbr":
            from discipline.qbr_review import main as qbr_main
            qbr_main()
        else:
            print("Usage: mothertree rhythm weekly|monthly|calendar|pulse|qbr")

    elif cmd == "accounts":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "list":
            from mothertree.graphql_client import get_accounts_with_plans
            accounts = get_accounts_with_plans()
            if not accounts:
                print("No account plans.")
            else:
                for a in accounts:
                    co = a.get("companyByCompanyId", {})
                    print(f"  {co.get('name', '?')} — QBR: {a.get('nextQbr', 'not set')}")
        elif subcmd == "review":
            if len(args) < 3:
                print("Usage: mothertree accounts review <company>")
                sys.exit(1)
            company_name = " ".join(args[2:])
            from mothertree.graphql_client import graphql
            result = graphql("""
            query($name: String!) {
                allCompaniesList(filter: {name: {includesInsensitive: $name}}, first: 1) { id name }
            }
            """, {"name": company_name})
            companies = result.get("allCompaniesList", [])
            if not companies:
                print(f"No company found matching '{company_name}'")
            else:
                from discipline.qbr_review import synthesize_qbr
                print(synthesize_qbr(companies[0]["id"], companies[0]["name"]))
        elif subcmd == "qbr":
            from discipline.qbr_review import main as qbr_main
            qbr_main()
        else:
            print("Usage: mothertree accounts {list|review|qbr}")

    elif cmd == "pulse":
        subcmd = args[1] if len(args) > 1 else "scan"
        if subcmd == "scan":
            from pulse.scanner import run_scan
            run_scan()
        else:
            print("Usage: mothertree pulse scan")

    elif cmd == "admin":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "add":
            if len(args) < 3:
                print("Usage: mothertree admin add <email>")
                sys.exit(1)
            from mothertree.graphql_client import add_admin
            add_admin(args[2], granted_by="cli")
            print(f"Admin granted: {args[2]}")
        elif subcmd == "remove":
            if len(args) < 3:
                print("Usage: mothertree admin remove <email>")
                sys.exit(1)
            from mothertree.config import ADMIN_EMAIL
            if args[2].lower() == ADMIN_EMAIL.lower():
                print("Cannot remove root admin.")
                sys.exit(1)
            from mothertree.graphql_client import remove_admin
            remove_admin(args[2])
            print(f"Admin revoked: {args[2]}")
        elif subcmd == "list":
            from mothertree.graphql_client import get_all_admins
            admins = get_all_admins()
            if not admins:
                print("No admins configured.")
            else:
                for a in admins:
                    print(f"  {a['email']} (granted by {a['grantedBy']})")
        else:
            print("Usage: mothertree admin {add|remove|list}")

    elif cmd == "calendar":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "set" and len(args) >= 4:
            email = args[2]
            ical_url = args[3]
            try:
                from mothertree.graphql_client import get_user_by_email, update_user_profile
                user = get_user_by_email(email)
                if not user:
                    print(f"No user found for {email}")
                else:
                    update_user_profile(user["id"], calendar_url=ical_url)
                    print(f"Calendar URL set for {email}")
            except Exception as e:
                print(f"Failed: {e}")
        else:
            print("Usage: mothertree calendar set <email> <ical_url>")

    elif cmd == "dump":
        if len(args) < 2:
            print("Usage: mothertree dump <path>")
            sys.exit(1)
        from mothertree.dump import dump
        dump(args[1])

    elif cmd == "restore":
        if len(args) < 2:
            print("Usage: mothertree restore <path>")
            sys.exit(1)
        from mothertree.dump import restore
        restore(args[1])


    elif cmd == "profile":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "consolidate":
            import logging
            logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
            from ingestion.profile import consolidate_profile, fetch_organization_profile, merge_elements
            from mothertree.graphql_client import delete_all_organization, get_organization_profile
            elements = get_organization_profile()
            print(f"  {len(elements)} elements before consolidation")
            consolidated = consolidate_profile(elements)
            delete_all_organization()
            stats = merge_elements(consolidated)
            print(f"  Consolidated: {stats}")
            print(fetch_organization_profile())
        else:
            from ingestion.profile import fetch_organization_profile
            profile = fetch_organization_profile()
            if profile:
                print(profile)
            else:
                print("  No organization profile yet. Run foundation ingestion to build one.")

    elif cmd == "embed":
        subcmd = args[1] if len(args) > 1 else ""
        if subcmd == "backfill":
            import logging
            logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
            table = args[2] if len(args) > 2 else None
            tables = [table] if table else ["insights", "change", "worldview", "personas", "competitors"]
            from mothertree.graphql_client import embed_record, graphql
            TABLE_GQL = {
                "insights": "allInsightsList",
                "change": "allChangesList",
                "worldview": "allWorldviewsList",
                "personas": "allPersonasList",
                "competitors": "allCompetitorsList",
            }
            BY_PK_GQL = {
                "insights": "insightById",
                "change": "changeById",
                "worldview": "worldviewById",
                "personas": "personaById",
                "competitors": "competitorById",
            }
            for t in tables:
                gql_list = TABLE_GQL.get(t, t)
                # Fetch all records (embedding filter not available via PostGraphile)
                field_map = {"insights": "reframe", "change": "statement", "worldview": "belief",
                             "personas": "name", "competitors": "type"}
                f = field_map.get(t, "id")
                rows = graphql(f"{{ {gql_list} {{ id {f} }} }}")
                records = rows.get(gql_list, [])
                print(f"  {t}: {len(records)} records to embed")
                by_pk = BY_PK_GQL.get(t, f"{t}ById")
                for i, rec in enumerate(records):
                    # Fetch full record for embedding text
                    detail_fields = {
                        "insights": "id category reframe evidence trigger",
                        "change": "id statement context",
                        "worldview": "id belief pain",
                        "personas": "id name role profile",
                        "competitors": "id type positioning whenMentioned",
                    }
                    fields = detail_fields.get(t, "id")
                    full = graphql(f"""
query($id: UUID!) {{
    {by_pk}(id: $id) {{ {fields} }}
}}
""", {"id": rec["id"]})
                    record = full.get(by_pk, {})
                    # Remap whenMentioned back to when_mentioned for embed_record
                    if "whenMentioned" in record:
                        record["when_mentioned"] = record.pop("whenMentioned")
                    if record:
                        try:
                            embed_record(t, rec["id"], record)
                            if (i + 1) % 10 == 0:
                                print(f"    {t}: {i + 1}/{len(records)}")
                        except Exception as e:
                            print(f"    WARN: {t}/{rec['id']}: {e}")
                print(f"  {t}: done")
        else:
            print("Usage: mothertree embed backfill [table]")
            print("Tables: insights, change, worldview, personas, competitors")

    elif cmd == "stats":
        from mothertree.graphql_client import graphql
        result = graphql("""
        {
          allChanges { totalCount }
          allWorldviews { totalCount }
          allPersonas { totalCount }
          allCompetitors { totalCount }
          allInsights { totalCount }
          allContacts { totalCount }
          allSignals { totalCount }
          allSignalThreads { totalCount }
          allEnrollments { totalCount }
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
            "allSignalThreads": "signal_threads",
            "allEnrollments": "enrollment",
        }
        for key, data in result.items():
            name = TABLE_LABELS.get(key, key)
            count = data["totalCount"]
            print(f"  {name:20s} {count:>5}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
