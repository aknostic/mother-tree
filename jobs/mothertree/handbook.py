"""Handbook — role-aware feature documentation for help, onboarding, and contextual tips.

Loads markdown files with YAML frontmatter from a directory. Each file is one
feature or concept. The bot uses this for:
1. Contextual tips (first-encounter, by trigger)
2. Help command (role-filtered, grouped by topic)
3. Onboarding sequence (ordered entries for new users)
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import frontmatter

log = logging.getLogger(__name__)


@dataclass
class HandbookEntry:
    key: str
    roles: list[str]
    trigger: str | None
    onboarding: bool
    onboarding_order: int | None
    topic: str
    summary: str
    content: str


class Handbook:
    """In-memory index of handbook entries, loaded from markdown files."""

    def __init__(self, directory: str = None):
        self.entries: dict[str, HandbookEntry] = {}
        self._by_trigger: dict[str, HandbookEntry] = {}
        if directory:
            self.load(directory)

    def load(self, directory: str) -> None:
        """Load all .md files from directory."""
        path = Path(directory)
        if not path.is_dir():
            log.warning("Handbook directory not found: %s", directory)
            return
        for md_file in sorted(path.glob("*.md")):
            try:
                post = frontmatter.load(str(md_file))
                entry = HandbookEntry(
                    key=post["key"],
                    roles=post.get("roles", []),
                    trigger=post.get("trigger"),
                    onboarding=post.get("onboarding", False),
                    onboarding_order=post.get("onboarding_order"),
                    topic=post.get("topic", "general"),
                    summary=post.get("summary", ""),
                    content=post.content,
                )
                self.entries[entry.key] = entry
                if entry.trigger:
                    self._by_trigger[entry.trigger] = entry
            except Exception:
                log.exception("Failed to load handbook entry: %s", md_file)

    def for_role(self, role: str) -> list[HandbookEntry]:
        """Get all entries visible to a role."""
        return [e for e in self.entries.values() if role in e.roles]

    def by_trigger(self, trigger: str) -> HandbookEntry | None:
        """Get the entry for a specific trigger."""
        return self._by_trigger.get(trigger)

    def onboarding_sequence(self, role: str) -> list[HandbookEntry]:
        """Get onboarding entries for a role, sorted by order."""
        entries = [e for e in self.entries.values()
                   if e.onboarding and role in e.roles]
        return sorted(entries, key=lambda e: 999 if e.onboarding_order is None else e.onboarding_order)

    def grouped_by_topic(self, role: str) -> dict[str, list[HandbookEntry]]:
        """Get entries grouped by topic for a role."""
        groups: dict[str, list[HandbookEntry]] = {}
        for entry in self.for_role(role):
            groups.setdefault(entry.topic, []).append(entry)
        return groups
