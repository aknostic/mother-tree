# How Mother Tree Works in Slack

Mother Tree is a conversational participant. In DMs, just talk. In channels, @mention her. She listens to every channel she's in — speaks when useful, stays quiet otherwise.

## Talking to Mother Tree

### In DMs

Just message her directly. No prefix needed. She always responds.

### In channels

Mention her: `@Mother Tree what's our positioning for KPN?`

She also responds when she has something useful to add to the conversation — you don't always need to mention her.

### Training (DM only)

Training commands only work in DMs — in channels, words like "next" and "go" are normal conversation.

- `enroll hunter` / `enroll gatherer` / `enroll farmer` / `enroll citizen` — start training
- `status` — your progress
- `next` — next training chapter
- `go` — start exercises after reading instruction
- `practice [topic]` — drill a specific area (promise, worldview, audience, difference, services)
- A, B, or C — answer exercise questions

Citizens don't get formal training — they get inspired, one piece at a time.

### Personas

Works everywhere (DM and channels):

- `ask saga <question>` — positioning strategy ([Saga](inspirations.md) — positioning strategist)
- `ask lena <question>` — consultative diagnosis ([Lena](inspirations.md) — consultative diagnostician)
- `ask trainer <question>` — both perspectives synthesized
- Or naturally: "what would Lena say about this?"

### Admin commands (DM only, admin users only)

- `make admin <email>` — grant admin privileges
- `remove admin <email>` — revoke admin (can't remove root)
- `enroll <email> as <role>` — directly enroll someone
- `pending` — list pending enrollment requests

### Other commands

- `status` — your progress
- `progress` — team training overview
- `help` — how to interact

## How she decides when to speak in channels

A fast triage step checks each message. She responds when: someone asks a direct question, requests help, or she has something useful to add. She stays quiet during: small talk between colleagues, reactions, conversations she'd just be interrupting.

In DMs she always responds.

## Who's talking

Mother Tree has three visible voices:

- **Mother Tree** — the default. The Librarian. Conversational, practical, draws on everything in the central intelligence. Most of what you hear is Mother Tree.
- **Saga** — positioning strategy. Thinks in terms of change, worldview, smallest viable audience. Activated by `ask saga` or when the conversation is about positioning.
- **Lena** — consultative diagnosis. Thinks in terms of reframes, qualification, conversation choreography. Activated by `ask lena` or when you're preparing for a meeting.
- **Trainer** — both perspectives synthesized. Activated by `ask trainer`.

Behind the scenes, invisible characters do background work:

- **Spotter** — extracts entities, signals, actions, and sales stage from conversations
- **Weaver** — resolves extracted entities into the relationship graph (contacts, companies, deduplication)

## Signal capture

When someone shares commercial intelligence — a prospect, a meeting, a market event — Mother Tree notices and captures it in the background. She extracts entities (people, companies, events), actions (next steps, commitments), and qualification (which stage of the sales process this suggests).

She does this from any conversation in any channel, not just a designated signals channel. The conversation is the enrichment — no separate signal capture step.

## URLs

When someone shares a URL (up to 3 per message), Mother Tree fetches the content and uses it in the conversation. In a DM she might offer to save it to the central intelligence. In a channel she uses it contextually.

## Thread conversations

When Mother Tree responds in a channel, follow-ups continue in a thread. She remembers thread context. Threads can have follow-up reminders — she'll check back when appropriate.

## CLI commands

For farmers and operators. Entry point: `jobs/cli.py` (run via `uv run python -m cli` or as container entrypoint).

```bash
# Content ingestion
mothertree ingest foundation {sitemap,repo,file,dir,url} <source>   # Saga lens
mothertree ingest narrative {sitemap,repo,file,dir,url} <source>    # Lena lens
mothertree ingest consolidate                            # LLM-driven dedup + org profile synthesis
mothertree ingest truncate {change,worldview,personas,competitors,insights}  # Clear a table

# Database management
mothertree dump <path>      # Dump all CI tables to JSON
mothertree restore <path>   # Restore from dump

# Training management
mothertree train enroll <email> <name> <role>   # Enroll a user
mothertree train status <email>                  # Show enrollment status

# Admin management
mothertree admin add <email>     # Grant admin privileges
mothertree admin remove <email>  # Revoke admin privileges
mothertree admin list            # List all admins
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `SLACK_BOT_TOKEN` | Bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | App-level token for Socket Mode (`xapp-...`) |
| `HASURA_URL` | GraphQL endpoint |
| `HASURA_ADMIN_SECRET` | Hasura admin secret |
| `SCALEWAY_AI_API_KEY` | Scaleway Generative APIs key |
| `ADMIN_EMAIL` | Root admin email (seeded on startup) |
| `ORGANIZATION_NAME` | Organization name for profile extraction |
