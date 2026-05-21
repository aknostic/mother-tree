#!/usr/bin/env python3
"""Mother Tree Slack bot.

Handles:
- Unified message pipeline for all channels, DMs, and threads
- Welcome DM on channel join
- Incoming trigger API for CronJob-driven training delivery

All commands go through the pipeline via DM or @mention. No slash commands.
Uses Socket Mode for development, HTTP mode for production.
"""

import logging
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from mothertree.config import SLACK_APP_TOKEN, SLACK_BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mothertree")

app = App(token=SLACK_BOT_TOKEN)


# --- Unified message handler ---

@app.message(re.compile(".*"))
def handle_message(message, say, client):
    """Route all messages through the unified pipeline."""
    channel = message.get("channel")
    channel_type = message.get("channel_type", "")
    text = message.get("text", "").strip()
    user_id = message.get("user", "")
    thread_ts = message.get("thread_ts")
    ts = message.get("ts")
    files = message.get("files", [])

    # Skip empty or bot messages
    if not text and not files:
        return
    if message.get("bot_id") or message.get("subtype") == "bot_message":
        return

    # Get user name
    try:
        user_info = client.users_info(user=user_id)
        user_name = user_info["user"].get("real_name", user_id)
    except Exception:
        user_name = user_id

    # Determine participant count
    if channel_type == "im":
        participant_count = 1
    else:
        try:
            info = client.conversations_info(channel=channel)
            participant_count = info["channel"].get("num_members", 2)
        except Exception:
            participant_count = 2  # assume group

    # Get bot user ID for @mention detection
    bot_user_id = None
    try:
        auth = client.auth_test()
        bot_user_id = auth["user_id"]
    except Exception:
        pass

    def respond(msg, **kwargs):
        if thread_ts:
            say(msg, thread_ts=thread_ts)
        elif channel_type != "im" and ts:
            say(msg, thread_ts=ts)  # first channel response starts a thread
        else:
            say(msg)

    # Extract text from file attachments (PDFs, text files)
    file_contents = _extract_file_contents(files, client) if files else []
    if file_contents and not text:
        text = "(shared files)"

    from bot.pipeline import handle_message as pipeline_handle
    pipeline_handle(
        text=text, user_slack_id=user_id, user_name=user_name,
        channel_id=channel, channel_type=channel_type,
        participant_count=participant_count,
        respond=respond, client=client,
        thread_ts=thread_ts, ts=ts, bot_user_id=bot_user_id,
        file_contents=file_contents,
    )


# --- File extraction ---

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _extract_file_contents(files: list[dict], client) -> list[dict]:
    """Download and extract text from Slack file attachments."""
    results = []
    for f in files[:3]:  # max 3 files
        filetype = f.get("filetype", "")
        name = f.get("name", "unknown")
        size = f.get("size", 0)
        url = f.get("url_private_download")
        if not url:
            continue
        if size and size > MAX_FILE_SIZE:
            logging.warning(f"Skipping {name}: {size} bytes exceeds {MAX_FILE_SIZE} limit")
            continue

        try:
            import httpx
            resp = httpx.get(url, headers={"Authorization": f"Bearer {client.token}"}, timeout=30)
            resp.raise_for_status()
            if len(resp.content) > MAX_FILE_SIZE:
                logging.warning(f"Skipping {name}: downloaded size exceeds limit")
                continue
            content_bytes = resp.content
            if content_bytes[:5] in (b'<!DOC', b'<html'):
                logging.warning(f"Got HTML instead of file for {name}")
                continue

            if filetype == "pdf":
                import io
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages[:20])
                    if text.strip():
                        results.append({"name": name, "content": text.strip()})
                except Exception as e:
                    logging.warning(f"PDF extraction failed for {name}: {e}")

            elif filetype in ("text", "markdown", "csv", "json"):
                text = content_bytes.decode("utf-8", errors="replace")[:10000]
                if text.strip():
                    results.append({"name": name, "content": text.strip()})

        except Exception as e:
            logging.warning(f"File download failed for {name}: {e}")

    return results


# --- Welcome on channel join ---

@app.event("member_joined_channel")
def handle_member_joined(event, client):
    """Send a one-time welcome DM when someone joins a channel with Mother Tree."""
    user_slack_id = event.get("user", "")
    if not user_slack_id:
        return

    # Resolve to Mother Tree user
    from mothertree.identity import resolve_user
    user = resolve_user(user_slack_id, client)
    if not user:
        return

    from mothertree.graphql_client import get_or_create_dm_conversation
    dm_conv = get_or_create_dm_conversation(user["id"])
    if dm_conv["messages"]:
        return  # already talked

    user_name = user.get("name", user_slack_id)

    from mothertree.graphql_client import append_dm_message
    client.chat_postMessage(
        channel=user_slack_id,
        text=(
            f"Hey {user_name}! I'm Mother Tree \u2014 the team's commercial intelligence.\n\n"
            "I can help you prepare for conversations, understand our market, "
            "and sharpen your thinking. I also run training on the methodology.\n\n"
            "What's your role?\n"
            "\u2022 *enroll hunter* \u2014 full sales choreography training\n"
            "\u2022 *enroll gatherer* \u2014 signal recognition from delivery work\n"
            "\u2022 *enroll farmer* \u2014 platform and methodology knowledge\n"
            "\u2022 *enroll citizen* \u2014 get inspired, one piece at a time\n\n"
            "Or just talk to me \u2014 I'm here either way."
        ),
    )
    append_dm_message(dm_conv["id"], role="assistant", content="Welcome message sent.")
    logger.info(f"Welcomed {user_name} on channel join")


# --- Entry point ---

def main():
    logger.info("Mother Tree bot starting...")
    from mothertree.config import ADMIN_EMAIL
    from mothertree.graphql_client import ensure_root_admin
    if ADMIN_EMAIL:
        ensure_root_admin(ADMIN_EMAIL)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
