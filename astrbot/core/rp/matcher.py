"""Keyword matching engine for world books.

Matching follows the conventions established by lorebook tools: primary
keywords fire with OR semantics, secondary keywords gate the result through a
selective logic, constant entries are always present, and each book has its own
token budget that trims the lowest priority hits first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from astrbot.core import logger

from .models import BookEntry, SelectiveLogic, WorldBook

_ASCII_ONLY = re.compile(r"^[\x00-\x7F]+$")


@lru_cache(maxsize=512)
def _compile(pattern: str, ignore_case: bool) -> re.Pattern | None:
    """Compile a cached regex, tolerating a bad author-provided pattern.

    Args:
        pattern: Regex source.
        ignore_case: Whether to fold case.

    Returns:
        Compiled pattern, or None when the source is invalid.
    """
    try:
        return re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        logger.warning(f"[rp] invalid world book regex {pattern!r}: {exc}")
        return None


def keyword_hit(keyword: str, texts: list[str], entry: BookEntry) -> bool:
    """Test one keyword against the scanned texts.

    Args:
        keyword: Primary or secondary keyword.
        texts: Scan targets, usually the message plus recent turns.
        entry: Owner of the keyword, source of the matching flags.

    Returns:
        True when the keyword is present.
    """
    needle = keyword.strip()
    if not needle:
        return False
    ignore_case = not entry.case_sensitive
    if entry.regex:
        compiled = _compile(needle, ignore_case)
    elif entry.whole_word and _ASCII_ONLY.match(needle):
        compiled = _compile(
            rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])",
            ignore_case,
        )
    else:
        compiled = _compile(re.escape(needle), ignore_case)
    return any(bool(compiled and compiled.search(text)) for text in texts)


def secondary_gate(entry: BookEntry, texts: list[str]) -> bool:
    """Apply the selective logic of an entry.

    Args:
        entry: Entry whose secondary keywords are tested.
        texts: Scan targets.

    Returns:
        True when the entry is allowed to fire.
    """
    secondary = [k for k in entry.secondary_keywords if k.strip()]
    if not secondary:
        return True
    found = [k for k in secondary if keyword_hit(k, texts, entry)]
    logic = entry.selective_logic
    if logic == SelectiveLogic.AND_ANY:
        return bool(found)
    if logic == SelectiveLogic.AND_ALL:
        return len(found) == len(secondary)
    if logic == SelectiveLogic.NOT_ANY:
        return not found
    return len(found) < len(secondary)


@dataclass
class MatchHit:
    """An entry that fired during a scan."""

    entry: BookEntry
    book_id: str
    book_name: str
    keywords: list[str] = field(default_factory=list)
    recursed: bool = False

    @property
    def tokens(self) -> int:
        """Estimated token cost carried by this hit."""
        return self.entry.tokens


@dataclass
class ScanResult:
    """Outcome of scanning a set of world books."""

    hits: list[MatchHit] = field(default_factory=list)
    over_budget: list[MatchHit] = field(default_factory=list)
    scanned_texts: list[str] = field(default_factory=list)

    @property
    def injected_tokens(self) -> int:
        """Total estimated cost of the hits that will be injected."""
        return sum(hit.tokens for hit in self.hits)

    @property
    def fired_entry_ids(self) -> list[str]:
        """Ids of the entries that survived the budget trim."""
        return [hit.entry.id for hit in self.hits]


def build_scan_texts(message: str, contexts: list[dict], scan_depth: int) -> list[str]:
    """Collect the texts a world book scans.

    Args:
        message: The incoming user message.
        contexts: OpenAI format history, oldest first.
        scan_depth: How many recent history turns to include.

    Returns:
        Message first, then the last ``scan_depth`` readable turns.
    """
    texts = [message] if message and message.strip() else []
    if scan_depth <= 0:
        return texts
    recent: list[str] = []
    for item in reversed(contexts or []):
        if len(recent) >= scan_depth:
            break
        if item.get("_no_save") or item.get("role") not in ("user", "assistant"):
            continue
        content = item.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if isinstance(content, str) and content.strip():
            recent.append(content)
    texts.extend(reversed(recent))
    return texts


def scan_books(
    books: list[WorldBook],
    *,
    message: str = "",
    contexts: list[dict] | None = None,
    last_fired: dict[str, int] | None = None,
    turn_index: int = 0,
) -> ScanResult:
    """Scan world books and return the entries to inject.

    Args:
        books: World books in application order, each with its own budget.
        message: Current user message.
        contexts: Conversation history in OpenAI format.
        last_fired: Turn index per entry id, used to honour cooldowns.
        turn_index: Monotonic counter of the current turn.

    Returns:
        Surviving hits, budget rejects and the scanned texts.
    """
    contexts = contexts or []
    last_fired = last_fired or {}
    result = ScanResult()
    for book in books:
        texts = build_scan_texts(message, contexts, book.scan_depth)
        result.scanned_texts.extend(texts)
        fired: dict[str, MatchHit] = {}
        candidates = [e for e in book.entries if e.enabled]
        for passed in range(max(1, book.recursion_limit + 1)):
            fresh: list[str] = []
            for entry in candidates:
                if entry.id in fired:
                    continue
                if entry.cooldown_turns > 0:
                    previous = last_fired.get(entry.id)
                    if (
                        previous is not None
                        and turn_index - previous < entry.cooldown_turns
                    ):
                        continue
                matched = [
                    kw
                    for kw in entry.keywords
                    if kw.strip() and keyword_hit(kw, texts, entry)
                ]
                if not entry.constant and not matched:
                    continue
                if not secondary_gate(entry, texts):
                    continue
                fired[entry.id] = MatchHit(
                    entry=entry,
                    book_id=book.id,
                    book_name=book.name,
                    keywords=matched,
                    recursed=passed > 0,
                )
                fresh.append(entry.content)
            if not fresh:
                break
            texts = texts + [c for c in fresh if c.strip()]
        ordered = sorted(
            fired.values(),
            key=lambda h: (-h.entry.priority, h.entry.order, h.entry.comment),
        )
        spent = 0
        for hit in ordered:
            if spent + hit.tokens > book.token_budget:
                result.over_budget.append(hit)
                continue
            spent += hit.tokens
            result.hits.append(hit)
    return result
