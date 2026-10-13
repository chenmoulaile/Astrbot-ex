"""Turn world book hits into prompt placements.

A scan tells *which* entries fired; this module decides *where* they go: ahead
of the persona instructions, behind them, or inside the history at a given
depth. The result is plain data so both the pipeline hook and the dashboard
preview can use the exact same assembly path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .matcher import MatchHit, ScanResult
from .models import EntryPosition, Greeting
from .tokens import estimate_tokens

_NO_SAVE_ROLE = "user"


@dataclass
class Placement:
    """One rendered fragment bound for a position."""

    position: EntryPosition
    text: str
    depth: int = 0
    hits: list[MatchHit] = field(default_factory=list)


@dataclass
class Injection:
    """Everything a request needs, ready to apply."""

    system_top: str = ""
    system_tail: str = ""
    placements: list[Placement] = field(default_factory=list)
    history_inserts: list[Placement] = field(default_factory=list)

    @property
    def injected_tokens(self) -> int:
        """Estimated cost of the injected material."""
        return estimate_tokens(self.system_top + self.system_tail) + sum(
            estimate_tokens(p.text) for p in self.history_inserts
        )


def render_block(book_name: str, hits: list[MatchHit], note: str) -> str:
    """Render one book's entries as a markdown block.

    Args:
        book_name: World book title, used as the block heading.
        hits: Entries that fired for this block.
        note: One-line framing sentence for the model.

    Returns:
        Markdown block text, empty string when hits is empty.
    """
    if not hits:
        return ""
    parts = [f"# 世界书 · {book_name}", f"> {note}", ""]
    for hit in hits:
        title = hit.entry.comment.strip() or "（未命名条目）"
        body = hit.entry.content.strip()
        if hit.keywords:
            parts.append(f"## {title}\n〔命中关键词：{'、'.join(hit.keywords)}〕")
        else:
            parts.append(f"## {title}")
        parts.append(body)
        parts.append("")
    return "\n".join(parts).rstrip()


def build_injection(
    result: ScanResult,
    *,
    top_note: str = "以下设定常驻生效，扮演时不得违背。",
    tail_note: str = "以下设定由本轮对话关键词触发，仅在相关时使用。",
) -> Injection:
    """Arrange scan hits into their configured positions.

    Args:
        result: Output of :func:`astrbot.core.rp.matcher.scan_books`.
        top_note: Framing line for entries placed above the persona.
        tail_note: Framing line for entries placed below the persona.

    Returns:
        Injection holding rendered text per position.
    """
    injection = Injection()
    grouped: dict[tuple[str, EntryPosition], list[MatchHit]] = {}
    for hit in result.hits:
        if hit.entry.position == EntryPosition.HISTORY_DEPTH:
            injection.history_inserts.append(
                Placement(
                    position=hit.entry.position,
                    text=render_block(hit.book_name, [hit], tail_note),
                    depth=max(0, hit.entry.depth),
                    hits=[hit],
                )
            )
            continue
        grouped.setdefault((hit.book_name, hit.entry.position), []).append(hit)
    for (book_name, position), hits in grouped.items():
        note = top_note if position == EntryPosition.SYSTEM_TOP else tail_note
        text = render_block(book_name, hits, note)
        injection.placements.append(Placement(position=position, text=text, hits=hits))
        if position == EntryPosition.SYSTEM_TOP:
            injection.system_top = f"{injection.system_top}\n\n{text}".strip()
        else:
            injection.system_tail = f"{injection.system_tail}\n\n{text}".strip()
    injection.history_inserts.sort(key=lambda p: p.depth)
    return injection


def compose_system_prompt(system_prompt: str, injection: Injection) -> str:
    """Place the rendered blocks around an existing system prompt.

    Args:
        system_prompt: The request's current system prompt.
        injection: Rendered world book material.

    Returns:
        The final system prompt.
    """
    parts = [injection.system_top, system_prompt, injection.system_tail]
    return "\n\n".join(part for part in parts if part and part.strip())


def apply_history(contexts: list[dict], injection: Injection) -> list[dict]:
    """Insert depth-placed entries into a copy of the history.

    Injected messages carry ``_no_save`` so AstrBot strips them before
    persisting the conversation, which keeps lore out of the stored history.

    Args:
        contexts: OpenAI format history, oldest first.
        injection: Rendered world book material.

    Returns:
        A new list when anything was injected, otherwise the original one.
    """
    if not injection.history_inserts:
        return contexts
    updated = list(contexts)
    for placement in injection.history_inserts:
        index = max(0, len(updated) - placement.depth)
        updated.insert(
            index,
            {
                "role": _NO_SAVE_ROLE,
                "content": placement.text,
                "_no_save": True,
            },
        )
    return updated


def begin_dialog_history(greeting: Greeting) -> list[dict]:
    """Render an opening line as transient history messages.

    Args:
        greeting: Selected opening scene.

    Returns:
        One assistant message tagged ``_no_save``.
    """
    return [
        {
            "role": "assistant",
            "content": greeting.content.strip(),
            "_no_save": True,
        }
    ]


def trace_of(injection: Injection) -> list[dict]:
    """Describe what will be injected, for logs and the dashboard preview.

    Args:
        injection: Rendered world book material.

    Returns:
        One record per hit with its book, position and cost.
    """
    records = []
    for placement in injection.placements + injection.history_inserts:
        for hit in placement.hits:
            records.append(
                {
                    "book": hit.book_name,
                    "entry": hit.entry.comment,
                    "position": placement.position.value,
                    "depth": placement.depth,
                    "keywords": hit.keywords,
                    "tokens": hit.tokens,
                    "recursed": hit.recursed,
                }
            )
    return records
