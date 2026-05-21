# Project Mother Tree: Aknostic Commercial Intelligence Platform

> *"A forest is much more than what you see." — Suzanne Simard*

> **Note (2026-03-31):** This is the original brainstorming document from the project's inception. Most architectural questions below have been answered — see [README.md](README.md) for current architecture, [docs/implementation-plan.md](docs/implementation-plan.md) for status, and [CLAUDE.md](CLAUDE.md) for the working context. Kept as historical record of the vision and the questions that shaped the design.

## The idea — beyond CRM

We are Aknostic (operating as 9apps B.V.), a European cloud-native and Kubernetes consultancy. Currently ~15 people, international team, based in the Netherlands. We do consultative selling — relationship-driven, networking-based, 1-2 new large clients per year per cell. LinkedIn Sales Navigator is our primary prospecting tool.

We are actively expanding across Europe following Eckard Wintzen's cell division model (BSO/Origin). This is not a vague aspiration — we have a v8 strategy document with a concrete cap table structure: cell entrepreneur (capped 25%), originating entrepreneur (fixed 5% seeding grant), team pool (10%), Group holding the remainder. First-generation cells start at Group 80% and mature to 65%. We are evaluating partnerships with Scaleway (broad European coverage) and STACKIT (DACH market penetration).

This means whatever we build is not a tool for a single small Dutch team. It's the sales infrastructure that every new Aknostic cell will inherit when it spins up — potentially in France, Germany, the Nordics, or elsewhere. It has to work across languages, markets, cultures, and semi-autonomous teams who share a brand and methodology but operate independently.

We want to explore whether we can build our sales operation on Claude Code (with skills, MCP, Chrome integration) and Cowork instead of adopting a SaaS CRM.

But this is bigger than a CRM replacement. What we're actually describing is a **commercial intelligence platform** — a system where sales, marketing, content, and opportunity detection are connected across the entire Aknostic group. Individual cells sell autonomously, but the group functions as a hive mind: every signal any cell picks up makes every other cell smarter.

This is a brainstorming session. We don't want a plan yet. We want to understand what's possible, what's hard, and what might not work at all.

## Why we're considering this

- We preach European digital sovereignty — using a Delaware-incorporated SaaS CRM (even a good one like Folk) creates a contradiction
- Our sales volume per cell is tiny — dozens of relationships, not thousands of leads
- We already use Claude Code and Cowork daily
- The closest CRM fit (Folk) has no mobile app, no self-hosting, and costs money for something we might be able to do better ourselves
- If this works, it becomes part of the "cell starter kit" — the operational package a new cell inherits
- It's a compelling story for our Clouds of Europe platform and our market positioning
- It proves our thesis: you can run a European business on European infrastructure with open tooling
- **The real opportunity:** a connected system where sales activities, content strategy, community signals, and market intelligence feed each other — something no off-the-shelf CRM does

## The hive mind concept

This is where the idea goes beyond CRM. A traditional CRM tracks contacts and deals. What we want is a system where the entire commercial operation is interconnected:

### Opportunity scanning
- Actively monitor signals that indicate a company might need us: regulatory deadlines (NIS2, DORA, EU Data Act), public cloud spending data, job postings for "cloud migration" or "Kubernetes" roles, leadership changes at target accounts
- When Cell-DACH spots a signal relevant to Cell-NL (e.g., a Dutch company opening a Berlin office), that insight flows across
- Clouds of Europe community activity as a signal source: who's reading what, who's attending events, what questions are being asked

### Content strategy feedback loop
- Sales conversations reveal what prospects care about — those themes should feed back into Clouds of Europe content planning
- If three prospects in one month ask about lock-in assessment, that's a signal to write the definitive lock-in guide
- Content performance (which articles get shared, which drive inbound conversations) should be visible alongside pipeline data
- The system should help identify content gaps: "we have no material addressing {topic} that keeps coming up in conversations"

### Reusable tools and accelerators
- A lock-in audit template/tool that any cell can deploy with a prospect — both as a sales accelerator and as a brand-building asset
- TCO comparison frameworks that get refined with each engagement
- Sovereignty assessment tools aligned with the EU Cloud Sovereignty Framework (SEAL levels)
- Each tool gets better as more cells use it and feed back learnings

### Adjacent opportunity detection
- When we're inside a client, we see adjacent problems: a team struggling with observability, a department that needs platform engineering training, a partner organization with similar challenges
- The system should help map these adjacencies and decide which cell (or future cell) is best positioned to pursue them
- Pattern recognition across cells: "every client in financial services asks about DORA compliance within 3 months — should we build a DORA-specific offering?"

### Network intelligence
- Our collective network is our most valuable asset. Across all cells, who do we know at which companies?
- Second-degree connections: Cell-NL knows the CTO, Cell-DACH knows the VP Engineering at the same company — do we know that?
- Event intelligence: who from our network is speaking at KubeCon, attending CloudNative Day, writing about sovereignty?
- Referral tracking: which relationships have generated introductions, and to whom?

## What we need from a "CRM" — the relationship layer

1. Capture contact information from LinkedIn (Sales Navigator profiles) with minimal friction
2. Store contacts, companies, interaction notes, and relationship context
3. Track where relationships stand (not a rigid pipeline — more like relationship temperature)
4. Remind us to follow up when conversations go cold
5. Brief us before calls/meetings with full context on a person or company
6. Weekly review of what happened and what needs attention
7. Team visibility — multiple people within a cell interact with the same contacts
8. Works when we're mobile (conferences, events, travel)
9. **Cell autonomy:** each cell can run its own sales operation independently
10. **Cross-cell awareness:** when relevant, cells can see if another cell has a relationship with someone (with consent, not by default)
11. **Cell bootstrapping:** a new cell entrepreneur gets a working system from day one — the sales methodology and tooling come with the cell, not with specific people
12. **Group visibility:** lightweight pipeline health data flows to Group for cap table governance, without micromanaging individual cells
13. **Multilingual:** works for international teams and across European markets

## What we need beyond CRM — the intelligence layer

14. **Signal ingestion:** monitor external sources (regulatory calendars, job boards, news, community activity) for opportunity signals
15. **Content-to-pipeline connection:** track which Clouds of Europe content drives conversations, and which conversations reveal content gaps
16. **Tool library:** maintain and improve reusable sales tools (lock-in audit, TCO framework, sovereignty assessment) that any cell can deploy
17. **Pattern recognition:** identify recurring themes across cells' pipelines — what are prospects asking about, what objections come up, what offerings are missing?
18. **Adjacent opportunity mapping:** when inside a client, map related problems and teams that could become separate engagements
19. **Network graph:** understand the collective Aknostic network across all cells — who knows whom, where the second-degree connections are, which relationships generate referrals
20. **Marketing rhythm integration:** content calendar, event pipeline, LinkedIn posting strategy should be informed by sales intelligence and vice versa

## Architectural questions to explore

### Chrome integration
- How exactly does Claude Code's Chrome integration work with LinkedIn? Can it read profile data from a Sales Navigator page reliably?
- What are the limitations? Does it work on any LinkedIn page or only specific layouts?
- Is this read-only page scraping, or does it use accessibility APIs / DOM parsing?
- How does this compare to what folkX does? What are we giving up?
- Rate limiting / detection risk — does LinkedIn detect this kind of page reading?
- Does the Chrome extension work alongside Sales Navigator's own Chrome extension?

### Data storage
- What's the right format? Markdown? JSON? SQLite? A mix?
- Git repo vs local database vs self-hosted API (Twenty's API, for instance)?
- How do we handle multi-user? Git merge conflicts on contact files are ugly.
- What's the backup/sync story? We want this on Scaleway, not just laptops.
- How do we handle search across hundreds of contacts efficiently?

### Multi-cell architecture
- Each cell is semi-autonomous. Does each cell get its own CRM instance, or is there a shared fabric?
- A contact might be relevant to multiple cells (e.g., a multinational CTO with divisions in NL and DACH). How do we handle cross-cell visibility without creating a surveillance tool?
- The Group needs some visibility into pipeline health across cells (for the cap table maturity model and revenue tracking). What's the minimum data that flows up?
- When a new cell spins up, what's the bootstrapping experience? Can a cell entrepreneur get a working sales system on day one?
- The Wintzen model values autonomy. Can we design this so each cell can customize their workflow while sharing a common backbone?
- Do cells share a contact database, or do they federate? What happens when Cell-NL introduces a contact to Cell-DACH — how is that handoff tracked?

### International and multilingual considerations
- We are an international team today. Cells will operate in local languages (German for DACH, French for France, etc.)
- Contact notes might be in Dutch, English, or the local market language. How does Claude handle querying across languages?
- LinkedIn profiles are in various languages. Does Chrome capture handle non-Latin scripts if we expand further?
- Legal/compliance: different EU markets have different norms around contact data storage. GDPR applies everywhere, but local interpretations vary. Is file-based storage with Git audit trail actually better for compliance than a SaaS CRM?
- Sales methodology might need local adaptation. Dutch directness doesn't work in every market. Can the skill encode market-specific norms?

### Claude Code skills vs MCP vs Cowork
- What's the right boundary between a skill, an MCP server, and a Cowork task?
- A skill has SKILL.md instructions — but can it maintain state across sessions?
- Should the "CRM" be an MCP server that Claude Code (and Cowork) connect to?
- Could we build a lightweight API (FastAPI on Scaleway) that acts as the CRM backend, with Claude as the interface?
- How does Cowork's scheduled tasks work for daily/weekly automations?

### The hive mind architecture
- This is fundamentally a data integration problem. How do we connect: contact data, interaction logs, Clouds of Europe analytics, content calendar, event pipeline, regulatory calendars, job board signals, LinkedIn activity, email threads, Mattermost conversations?
- Do we build one monolithic system, or a set of loosely coupled services that Claude orchestrates?
- Where does the intelligence actually live? In the data (embeddings, structured queries), or in Claude's ability to reason across sources on demand?
- Is this a "data warehouse for sales" with Claude as the query layer? Or is it more like a set of agents that proactively surface insights?
- How do we handle the Clouds of Europe feedback loop technically? The platform runs on its own infrastructure — how does community engagement data flow into the commercial intelligence layer?
- Regulatory signal monitoring: do we build scrapers, use RSS, subscribe to institutional newsletters, or rely on Claude's web search at query time?
- How do reusable tools (lock-in audit, TCO calculator, sovereignty assessment) get versioned, improved, and shared across cells? Are they in a Git repo? A skill library?

### The knowledge graph problem
- What we're really describing is a knowledge graph of relationships, companies, interactions, signals, content, and tools — with cells as the organizational overlay
- Do we need an actual graph database (Neo4j, self-hosted on Scaleway)? Or can Claude navigate structured files effectively enough?
- How do we model second-degree relationships and cross-cell network overlaps?
- When the graph grows (5 cells × 50 contacts × years of interactions), does the approach still work within Claude's context limitations?
- Is there an open-source knowledge graph tool that fits our sovereignty requirements?

### Mobile
- This is a genuine problem. Claude Code doesn't run on phones.
- At a conference, I meet someone and need to capture them immediately.
- Options: just use the LinkedIn app and capture later? Voice memo? Quick note in Mattermost that gets processed later?
- Is "capture on mobile" important enough to kill this whole approach?

### Email integration
- We run Stalwart (self-hosted email). Can we connect via IMAP?
- Should the CRM auto-ingest email threads with known contacts?
- Or is that over-engineering for our volume?

### Intelligence layer
- How much context can Claude Code hold about our full contact database?
- If we have 200 contacts with notes, does that exceed context windows?
- Do we need a retrieval / embedding layer, or can we get away with file search?
- How good is Claude at generating the kind of briefings we'd want before a call?

### Comparison with Folk
- Folk costs ~€1,200/year for our team — but multiply that by cells. 5 cells = €6,000/year, 10 cells = €12,000/year. Still not expensive, but the sovereignty argument compounds.
- Folk gives us: LinkedIn capture (folkX), contact enrichment, follow-up reminders, email sync, team workspace
- Folk does NOT give us: cross-cell visibility, cell bootstrapping, methodology encoding, data sovereignty
- What would we gain by building our own: sovereignty, customization, methodology-native, cell starter kit, proof of concept for clients
- What would we lose: frictionless LinkedIn capture, polished UI, someone else maintaining it
- Is the honest answer "use Folk for Cell-NL now while we prototype something better for Cell-2"?
- Or does the Wintzen model actually argue for letting each cell choose their own tools, and only standardizing the methodology?

## Risks and failure modes

- **Over-engineering:** We spend weeks building a platform instead of selling
- **Adoption failure:** It's too clunky, we stop using it, relationships fall through cracks
- **Mobile gap:** We can't capture contacts at events, which is when capture matters most
- **Context limits:** Claude can't hold enough contact data to be useful
- **LinkedIn detection:** Our profiles get flagged for automated access
- **Yak shaving:** We're a consultancy, not a CRM company — is this a distraction?
- **Premature scaling:** We design for 10 cells when we currently have 1 — and the complexity kills adoption before it starts
- **Cell resistance:** Future cell entrepreneurs might not want our tooling — they might prefer their own CRM. Does the Wintzen model even allow us to mandate this?
- **Knowledge concentration:** If only the founding team understands the system, it doesn't transfer to new cells. A platform that requires Claude Code fluency is a platform that requires a specific skillset.
- **Anthropic dependency:** We're replacing SaaS vendor dependency with AI vendor dependency. Claude Code is not self-hostable. Is this actually more sovereign, or just a different kind of lock-in?
- **Scope creep into product:** The line between "our internal commercial platform" and "a product we could sell" is blurry. Are we accidentally becoming a software company? Is that bad, or is it an opportunity (and a new cell)?
- **Hive mind vs surveillance:** There's a fine line between "the group gets smarter collectively" and "Group HQ monitors what every cell is doing." The Wintzen model works because cells feel autonomous. If the intelligence platform feels like reporting infrastructure, cell entrepreneurs will resist or game it.
- **Data gravity:** Once we build this and fill it with years of relationships and intelligence, we're locked into whatever architecture we chose. What's the migration path if the approach doesn't scale?

## What I want from this brainstorming session

1. Honest assessment of which parts are easy, which are hard, and which might be impossible
2. Exploration of the Chrome + Claude Code integration specifically — what can it actually do on a LinkedIn page today?
3. Architectural options we haven't considered — especially for the multi-cell federation problem and the intelligence layer
4. A clear-eyed comparison: is this genuinely better than Folk + Cowork, or are we rationalizing a build because we're engineers?
5. Decision framework: what would we need to see in a 1-week prototype to commit to building vs buying?
6. The Wintzen question: should the platform be part of the cell infrastructure (standardized), or part of the cell's autonomy (each cell chooses)? What does the BSO/Origin playbook tell us about how operational tooling was handled across cells?
7. The Anthropic dependency question: are we actually improving our sovereignty posture, or just trading one vendor dependency for another? What's the exit strategy if Claude Code becomes unavailable or unaffordable?
8. The "cell starter kit" question: what's the minimum viable sales infrastructure a new cell entrepreneur needs on day one? Is it a tool, a methodology document, a set of templates, or all three?
9. The scope question: is this a CRM project, or is it the commercial operations layer of the Aknostic platform — the "dreamstack for sales" equivalent of what we're already building for infra with Stalwart + Nextcloud + Authentik on Scaleway?
10. The hive mind question: what's the right balance between collective intelligence and cell autonomy? How do you build a system where cells benefit from sharing without feeling surveilled? What data should flow up to Group, what should flow sideways between cells, and what stays private within a cell?
11. The content flywheel question: Clouds of Europe is both a marketing platform and a community. How technically do we connect community engagement signals to the commercial intelligence layer? What does the feedback loop from sales conversations to content strategy actually look like as an architecture?
12. The tooling question: the lock-in audit, TCO calculator, sovereignty assessment — are these features of the platform, standalone tools, or Clouds of Europe content pieces that happen to be interactive? Where do they live?
13. The product question: at what point does "our internal commercial platform" become something we offer to other European consultancies as a product or as an open-source project? Is that a distraction, or is it the seed of a future cell?
