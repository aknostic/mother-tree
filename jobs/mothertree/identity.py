"""Identity resolution — maps Slack users to Mother Tree users via channel_links.

First contact flow:
1. Check channel_links for existing mapping
2. If not found, look up email from Slack API
3. If email matches existing user, verify names are consistent, then link
4. If no user found, auto-create as citizen

Step 3's name consistency check exists because of a historical incident in
which a legacy ADMIN_SLACK_ID env var was set to the wrong person's Slack ID
and a migration silently linked it to a user record keyed by a different
email. Without the check, four weeks of weekly briefings went to the wrong
person before anyone noticed.
"""

import logging
import re

import mothertree.graphql_client as gql

log = logging.getLogger(__name__)


def _tokens(name: str) -> set[str]:
    """Lower-cased word tokens from a name, alphanumeric only."""
    return {t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t}


def _names_consistent(slack_real_name: str, user_name: str) -> bool:
    """True when the two names share at least one substantive token.

    Handles the common "Jurg" vs "Jurg van Vliet" case (matches on "jurg")
    and rejects "Matthijs Bosman" vs "Jurg" (no shared tokens).
    """
    a = _tokens(slack_real_name)
    b = _tokens(user_name)
    if not a or not b:
        # If either name is empty, we can't verify — refuse rather than guess.
        return False
    return bool(a & b)


def resolve_user(slack_user_id: str, client) -> dict | None:
    """Resolve Slack user to Mother Tree user. Auto-creates citizens."""
    # 1. Check channel_links (fast path)
    link = gql.get_channel_link("slack", slack_user_id)
    if link:
        return gql.get_user(link["userId"])

    # 2. Look up email from Slack
    try:
        info = client.users_info(user=slack_user_id)
    except Exception:
        log.exception("Failed to look up Slack user %s", slack_user_id)
        return None

    profile = info.get("user", {}).get("profile", {})
    email = profile.get("email")
    name = info.get("user", {}).get("real_name", "Unknown")

    if not email:
        return None  # Bot or service account — no email

    email = email.lower()

    # 3. Check users by email
    user = gql.get_user_by_email(email)
    if user:
        # Existing user — sanity-check names before linking. Prevents the
        # silent mis-binding described in the module docstring.
        if not _names_consistent(name, user.get("name", "")):
            log.warning(
                "Refusing to link Slack %s (real_name=%r, email=%s) to user "
                "%s (name=%r): names share no tokens. Investigate.",
                slack_user_id, name, email, user["id"], user.get("name"),
            )
            return None
    else:
        # Auto-create as citizen
        user = gql.create_user(email=email, name=name, role="citizen")
        log.info("Auto-created citizen: %s (%s)", email, name)

    # 4. Link channel
    gql.create_channel_link(user["id"], "slack", slack_user_id)
    log.info("Linked Slack %s → %s", slack_user_id, email)
    return user
