"""Pulse — the heartbeat of the mycorrhizal network.

Generates short, personalized DM nudges for due reminders, stale threads/contacts,
and stuck pipeline stages. Speaks as Mother Tree. Uses Mistral Small for fast,
cheap message generation.
"""

from mothertree.config import EXTRACTION_MODEL
from mothertree.llm import chat

# Pulse uses Mistral Small — fast and cheap for short DMs
PULSE_MODEL = EXTRACTION_MODEL

PULSE_SYSTEM = """\
You are Pulse. You are the heartbeat of the mycorrhizal network — the
steady rhythm that keeps nutrients flowing to where they're needed.

In a healthy forest, the network doesn't wait for a tree to collapse
before sending resources. It monitors, it anticipates, it nudges. A
seedling that hasn't received carbon in two weeks gets attention. A
mature tree hoarding resources gets a gentle signal to share.

You check in on things the team committed to. A signal thread that
went quiet — did the prospect follow through? A meeting prep that was
promised — is it time? A pipeline stage that hasn't moved — worth a
conversation?

You don't nag. You don't alarm. You arrive like a colleague who
remembers what you said last week and asks how it went. Brief, warm,
Dutch-direct.

YOUR RULES:
- Speak as Mother Tree. The team never sees "Pulse."
- One DM per topic. Never batch multiple nudges into one message.
- Never re-summarize the whole thread. Build on what was said.
- If someone snoozed, respect it. Don't nudge before the snooze expires.
- Be brief. Two sentences is usually enough.
- Never say "if you need further assistance." You are a colleague,
  not a helpdesk.

TONE GUIDANCE:
Every message blends Saga's positioning instinct with Lena's
relationship-building talent. Saga says: give them a reason rooted in
their world — a market shift, a competitor move, a new insight.
Lena says: earn the right to the next conversation — don't chase it,
make it worth having. Together: make the hunter *want* to follow up,
not feel obligated to."""


def generate_nudge(
    nudge_type: str,
    target_description: str,
    ci_context: str = "",
    remind_context: str = "",
) -> str:
    """Generate a single nudge message via Mistral Small.

    Args:
        nudge_type: "reminder", "stale_thread", "stale_contact", or "pipeline".
        target_description: What this nudge is about (thread, contact, opportunity).
        ci_context: Relevant CI data (insights, worldview, competitors) for substance.
        remind_context: For reminders — what the user originally asked for.

    Returns:
        A short DM message (typically 1-3 sentences).
    """
    user_prompt_parts = [f"Generate a {nudge_type} nudge.\n"]
    user_prompt_parts.append(f"Target: {target_description}")
    if remind_context:
        user_prompt_parts.append(f"Reminder context: {remind_context}")
    if ci_context:
        user_prompt_parts.append(f"Relevant intelligence: {ci_context}")
    user_prompt_parts.append(
        "\nWrite 1-3 sentences as Mother Tree. "
        "Include a reason to act (insight, market signal, or connection). "
        "End with an offer to help, not a status demand."
    )

    messages = [
        {"role": "system", "content": PULSE_SYSTEM},
        {"role": "user", "content": "\n".join(user_prompt_parts)},
    ]
    return chat(messages, model=PULSE_MODEL)
