"""Training curriculum — role-specific stages, chapters, and trainers.

Each role has its own path. Each chapter specifies a trainer (seth, lawrence,
mother_tree) and which CI tables provide source data.
"""

CURRICULA = {
    "hunter": {
        0: {
            "name": "The Foundation",
            "chapters": {
                0: {"name": "The Promise", "tables": ["change"], "trainer": "seth",
                    "purpose": "What transformation do we offer? Not what we do — what the customer becomes."},
                1: {"name": "The Worldview", "tables": ["worldview", "personas"], "trainer": "seth",
                    "purpose": "What does our audience already believe? These beliefs make them ready."},
                2: {"name": "The Audience", "tables": ["personas"], "trainer": "seth",
                    "purpose": "Who specifically? Not everyone. Specific people with specific concerns."},
            },
        },
        1: {
            "name": "The Offering",
            "chapters": {
                0: {"name": "The Services", "tables": ["change"], "trainer": "seth",
                    "purpose": "Assess, Build, Operate, Transfer — the journey from dependent to independent. What each phase delivers."},
                1: {"name": "The Value Case", "tables": ["change", "insights"], "trainer": "lawrence",
                    "purpose": "How to talk about cost without leading with a number. This isn't an expense, it's a cost reduction."},
            },
        },
        2: {
            "name": "The Conversation",
            "chapters": {
                0: {"name": "The Consultative Conversation", "tables": ["personas", "insights"], "trainer": "lawrence",
                    "purpose": "First impression, probing, diagnosis, co-creation. Selling as shared problem-solving."},
                1: {"name": "Objection Handling", "tables": ["competitors", "insights"], "trainer": "lawrence",
                    "purpose": "Handle pushback with empathy, not argument. Every objection is a signal."},
                2: {"name": "Closing and Service", "tables": ["insights", "personas"], "trainer": "lawrence",
                    "purpose": "Close naturally, then service the sale. The easiest sale is the next one."},
            },
        },
        3: {
            "name": "The Difference",
            "chapters": {
                0: {"name": "Competitive Positioning", "tables": ["competitors"], "trainer": "seth",
                    "purpose": "How we differentiate vs alternatives — the status quo they leave behind."},
                1: {"name": "Selling Against Alternatives", "tables": ["competitors", "insights"], "trainer": "lawrence",
                    "purpose": "What to say when they mention a competitor in conversation."},
                2: {"name": "Storytelling with Evidence", "tables": ["insights", "change"], "trainer": "seth",
                    "purpose": "Which story to tell when. Using case studies and insights to make the change real."},
            },
        },
        4: {
            "name": "The Hunt",
            "chapters": {
                0: {"name": "Signal Recognition", "tables": ["insights", "worldview"], "trainer": "lawrence",
                    "purpose": "Spotting opportunities at conferences, on LinkedIn, in conversations. What to listen for."},
                1: {"name": "Meeting Prep", "tables": ["personas", "competitors", "insights"], "trainer": "lawrence",
                    "purpose": "Prepare for a real conversation — research the person, find the angle, draft the opening."},
                2: {"name": "Debrief", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "After the meeting — what happened, what signals did you capture, what's the next move."},
            },
        },
    },
    "gatherer": {
        0: {
            "name": "The Change",
            "chapters": {
                0: {"name": "Who We Are", "tables": ["change"], "trainer": "seth",
                    "purpose": "Brief: the transformation we offer. Enough to recognize it."},
                1: {"name": "Who It's For", "tables": ["personas"], "trainer": "seth",
                    "purpose": "The buyers. So you know who matters when you're in a delivery meeting."},
            },
        },
        1: {
            "name": "Signal Recognition",
            "chapters": {
                0: {"name": "What's a Signal", "tables": ["insights", "worldview"], "trainer": "lawrence",
                    "purpose": "When someone mentions cost pressure, lock-in, or compliance — that's a signal."},
                1: {"name": "Listening for Pain", "tables": ["worldview"], "trainer": "lawrence",
                    "purpose": "The pain is rarely stated directly. Here's what to listen for."},
                2: {"name": "Context Matters", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "A CTO complaining about costs means something different than a developer."},
            },
        },
        2: {
            "name": "The Conversation",
            "chapters": {
                0: {"name": "The Follow-Up", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "Tell me more about that — how to ask without selling."},
                1: {"name": "Knowing Your Limits", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "When to listen, when to ask, when to stop and hand off."},
            },
        },
        3: {
            "name": "The Handoff",
            "chapters": {
                0: {"name": "Sharing a Signal", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "How to tell Mother Tree what you noticed — natural conversation, not a form."},
                1: {"name": "Building Together", "tables": ["personas", "insights"], "trainer": "mother_tree",
                    "purpose": "Mother Tree asks follow-up questions to structure the signal."},
                2: {"name": "Looping In", "tables": ["personas"], "trainer": "mother_tree",
                    "purpose": "When and how to bring a hunter into the conversation."},
            },
        },
        4: {
            "name": "Stories",
            "chapters": {
                0: {"name": "Delivery as Soil", "tables": ["change", "insights"], "trainer": "seth",
                    "purpose": "Your delivery work creates awareness. How client success becomes the next story."},
                1: {"name": "The Narrative", "tables": ["insights"], "trainer": "seth",
                    "purpose": "How to frame what you did as evidence for the change we offer."},
            },
        },
    },
    "farmer": {
        0: {
            "name": "The Change",
            "chapters": {
                0: {"name": "Who We Are", "tables": ["change"], "trainer": "seth",
                    "purpose": "Brief: what the organization does."},
                1: {"name": "Who It's For", "tables": ["personas"], "trainer": "seth",
                    "purpose": "The people the platform ultimately serves."},
            },
        },
        1: {
            "name": "The Hunter's World",
            "chapters": {
                0: {"name": "Before the Meeting", "tables": ["personas", "competitors"], "trainer": "lawrence",
                    "purpose": "What a hunter goes through before a first conversation."},
                1: {"name": "In the Room", "tables": ["insights", "personas"], "trainer": "lawrence",
                    "purpose": "What happens in a consultative conversation. Why the prep has to be right."},
                2: {"name": "After the Meeting", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "What a hunter needs from the platform — debrief, signal capture, next steps."},
            },
        },
        2: {
            "name": "The Gatherer's World",
            "chapters": {
                0: {"name": "Spotting a Signal", "tables": ["worldview", "insights"], "trainer": "lawrence",
                    "purpose": "What it feels like to notice something in a delivery meeting."},
                1: {"name": "The Awkward Moment", "tables": ["personas"], "trainer": "lawrence",
                    "purpose": "The gatherer heard something. They're not a salesperson. What do they need?"},
                2: {"name": "The Handoff", "tables": ["insights"], "trainer": "lawrence",
                    "purpose": "What the platform should do when a gatherer shares a signal."},
            },
        },
        3: {
            "name": "The Platform",
            "chapters": {
                0: {"name": "What Mother Tree Does", "tables": ["change", "personas"], "trainer": "mother_tree",
                    "purpose": "How the platform serves hunters and gatherers day-to-day."},
                1: {"name": "What Good Looks Like", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "When the platform is working well, this is what the team experiences."},
            },
        },
        4: {
            "name": "Quality",
            "chapters": {
                0: {"name": "Assessing Quality", "tables": ["insights", "change"], "trainer": "mother_tree",
                    "purpose": "How to evaluate what Mother Tree extracts and generates."},
                1: {"name": "Improving the System", "tables": ["change"], "trainer": "mother_tree",
                    "purpose": "How to feed corrections back, tune the pipeline, improve outcomes."},
            },
        },
    },
    "citizen": {
        0: {
            "name": "See the Change",
            "chapters": {
                0: {"name": "The Change", "tables": ["change"], "trainer": "seth",
                    "purpose": "What the organization does and why it matters. One idea at a time."},
            },
        },
        1: {
            "name": "See the Worldview",
            "chapters": {
                0: {"name": "The Worldview", "tables": ["worldview"], "trainer": "seth",
                    "purpose": "What the people we help believe. One belief at a time."},
            },
        },
        2: {
            "name": "See the Signals",
            "chapters": {
                0: {"name": "Noticing", "tables": ["insights"], "trainer": "mother_tree",
                    "purpose": "Start noticing things in your own work that connect to the mission."},
            },
        },
        3: {
            "name": "Become a Gatherer",
            "chapters": {
                0: {"name": "Transition", "tables": [], "trainer": "mother_tree",
                    "purpose": "You've been noticing signals naturally. Want to enroll as a gatherer?"},
            },
        },
    },
}


def get_stages(role: str) -> dict:
    """Get all stages for a role. Raises KeyError for unknown roles."""
    return CURRICULA[role]


def get_chapters(role: str, stage: int) -> dict:
    """Get all chapters for a role's stage."""
    return CURRICULA[role][stage]["chapters"]


def get_chapter(role: str, stage: int, chapter: int) -> dict:
    """Get a specific chapter: name, tables, trainer, purpose."""
    return CURRICULA[role][stage]["chapters"][chapter]


def get_total_chapters(role: str, stage: int) -> int:
    """Get the number of chapters in a stage."""
    return len(CURRICULA[role][stage]["chapters"])


def get_stage_name(role: str, stage: int) -> str:
    """Get the name of a stage."""
    return CURRICULA[role][stage]["name"]


def is_citizen_role(role: str) -> bool:
    """Citizens get inspiration, not exercises."""
    return role == "citizen"
