"""Action and content marker parsing + user input sanitization."""
import re

_ACTION_RE = re.compile(r'\[ACTION:(\w+)\]')
_CONTENT_RE = re.compile(r'\[CONTENT:(\w+)\]')


def sanitize_user_input(text: str) -> str:
    """Escape action and content marker patterns in user input to prevent injection."""
    return text.replace("[ACTION:", "[action:").replace("[CONTENT:", "[content:")


def extract_action_markers(text: str) -> tuple[list[str], str]:
    """Extract [ACTION:*] markers from LLM response.

    Returns (list of action names, cleaned text with markers removed).
    """
    actions = _ACTION_RE.findall(text)
    clean = _ACTION_RE.sub("", text).strip()
    clean = re.sub(r'  +', ' ', clean)
    return actions, clean


def extract_content_markers(text: str) -> tuple[list[str], str]:
    """Extract [CONTENT:*] markers from LLM response.

    Returns (list of content types, cleaned text with markers removed).
    """
    markers = _CONTENT_RE.findall(text)
    clean = _CONTENT_RE.sub("", text).strip()
    return markers, clean
