"""Import markdown roleplay material into cards and world books.

The corpus this targets follows a fixed authoring layout:

* a character prompt is one file per character and per variant, with sections
  separated by ``═`` rules and titled ``§1 最高信条`` (full) or ``一、最高信条``
  (condensed); opening scenes live in the 开场白 section as ``**A · 标题**``
  markers followed by ``>`` quoted lines;
* a world book is a long markdown document of ``##`` chapters, ``###`` sections
  and ``- **关键词**：说明`` bullets, where each bullet is one lorebook entry.

Anything that cannot be parsed losslessly falls back to a single whole-section
entry, so importing never drops corpus text. Keyword extraction is heuristic by
design: the report lists what was chosen and the dashboard can correct it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.core import logger

from .models import (
    BookEntry,
    CardVariant,
    CharacterCard,
    Greeting,
    PromptBlock,
    WorldBook,
)
from .store import RPStore
from .tokens import estimate_tokens

CARD_MARK = "角色扮演SystemPrompt"
FULL_VARIANT = "full"
LITE_VARIANT = "lite"
BASE_VARIANT = "base"
VARIANT_LABELS = {
    FULL_VARIANT: "无删减完美版",
    LITE_VARIANT: "精简高质量版",
    BASE_VARIANT: "单版本",
}
BOOK_NAME_RE = re.compile(r"世界书|设定集")
BOOK_SKIP_RE = re.compile(r"README|规范", re.IGNORECASE)
# Long sections are split so a single entry cannot exceed a world book budget.
MAX_ENTRY_CHARS = 2400

_SECTION_SEP = re.compile(r"^[═─—=]{6,}\s*$")
_SECTION_PREFIX = re.compile(r"^(?:§\s*\d+|[一二三四五六七八九十百]+、)\s*")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET_KEY = re.compile(r"^[-*]\s+\*\*([^*]{1,60})\*\*\s*[：:]\s*(.*)$")
_GREETING_MARK = re.compile(
    r"^\*\*\s*([0-9A-Za-z一二三四五六七八九十]+)\s*[·・.、\-—]?\s*([^*]{0,80})\*\*\s*$"
)
_BOLD_LABEL = re.compile(r"^\*\*([^*]{2,40})\*\*\s*[：:]?\s*$")
_PAREN_GROUP = re.compile(r"[（(]([^（）()]{1,80})[）)]")
_PAREN_PREFIX = re.compile(
    r"^(?:通称|又名|简称|别名|译名|英文名?|日文名?|简中|繁中)[：:·\s]?"
)
_PAREN_NOISE = re.compile(
    r"必须|不得|重要|补充|参考|原文|官方|档案|存档|说明|更新|实测|抓取|来源|数据"
    r"|新增|缺口|未核实|引用|玩家|自创|仅供|可信度|剧透|优先"
)
_CHAPTER_PREFIX = re.compile(
    r"^第[一二三四五六七八九十百零0-9]+章[之]?[一二三四五六七八九十百0-9]*\s*[·・.、\-—]?\s*"
)
_DECOR = re.compile(r"[★⚠〔〕]+")
_GROUP_CODE = re.compile(r"^[A-Za-z]\d{1,2}$")
_CONSTANT_TITLE = re.compile(r"译名|对照|自检|红线|使用约定|口径")


@dataclass
class ImportItem:
    """One file's outcome, for the report."""

    path: str
    kind: str
    detail: str
    entries: int = 0
    blocks: int = 0
    greetings: int = 0
    warning: str = ""


@dataclass
class ImportReport:
    """Summary of a corpus scan or commit."""

    items: list[ImportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cards: int = 0
    files: int = 0

    @property
    def card_files(self) -> int:
        """Number of character prompt files read."""
        return self.files or len([i for i in self.items if i.kind.startswith("card")])

    @property
    def card_count(self) -> int:
        """Number of distinct character cards produced."""
        return self.cards or len([i for i in self.items if i.kind.startswith("card")])

    @property
    def book_count(self) -> int:
        """Number of world books read."""
        return len([i for i in self.items if i.kind == "worldbook"])

    @property
    def entry_count(self) -> int:
        """Total world book entries created."""
        return sum(i.entries for i in self.items)

    def summary(self) -> str:
        """One line describing the scan, safe to show in a UI or a log.

        Returns:
            Counts of files, cards, books, entries and warnings.
        """
        return (
            f"{self.card_files} 份角色卡文本 → {self.card_count} 张角色卡，"
            f"{self.book_count} 本世界书，{self.entry_count} 条条目，"
            f"{len(self.warnings)} 条提示"
        )


def stable_id(prefix: str, *parts: str) -> str:
    """Build a deterministic id so re-imports update instead of duplicating.

    Args:
        prefix: Human readable type tag.
        parts: Values that identify the object.

    Returns:
        Identifier accepted by :mod:`astrbot.core.rp.models`.
    """
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def clean_title(title: str) -> str:
    """Strip decorations from a heading or section title.

    Args:
        title: Raw title text.

    Returns:
        Title without star or warning annotations, trailing markers and without
        chapter numbering.
    """
    text = _DECOR.sub("", title.split("★")[0].split("⚠")[0]).strip()
    # Cutting at a ★ marker can leave a dangling parenthesis behind.
    text = re.sub(r"[（(]+$", "", text)
    text = _CHAPTER_PREFIX.sub("", text).strip(" ·・.、-—")
    return text


def extract_keywords(title: str) -> list[str]:
    """Derive lorebook keywords from a heading.

    The leading term is the heading body itself; anything inside parentheses is
    treated as an alias list, which is how the corpus writes Japanese names,
    romaji and alternative translations.

    Args:
        title: Raw heading text.

    Returns:
        Ordered, de-duplicated keywords, at most twelve.
    """
    raw = _DECOR.sub("", title.split("★")[0].split("⚠")[0]).strip()
    groups = [match.group(1) for match in _PAREN_GROUP.finditer(raw)]
    body = _PAREN_GROUP.sub("", raw).strip()
    body = _CHAPTER_PREFIX.sub("", body).strip(" ·・.、-—")
    keywords: list[str] = []
    if len(body) >= 2:
        keywords.append(body)
        for segment in re.split(r"[·・\s]+", body):
            piece = segment.strip(" （）()")
            if not 2 <= len(piece) < len(body):
                continue
            if _GROUP_CODE.match(piece) or _PAREN_NOISE.search(piece):
                continue
            keywords.append(piece)
    for group in groups:
        for candidate in re.split(r"[／/、,，;；]", group):
            candidate = _PAREN_PREFIX.sub("", candidate.strip())
            candidate = _DECOR.sub("", candidate).strip(" ：:\"'“”")
            if len(candidate) < 2 or len(candidate) > 30:
                continue
            if _PAREN_NOISE.search(candidate):
                continue
            keywords.append(candidate)
    unique: list[str] = []
    for keyword in keywords:
        if keyword not in unique:
            unique.append(keyword)
    return unique[:12]


def _is_title_like(chunk: str) -> bool:
    """Decide whether a chunk between rules is a section title.

    Args:
        chunk: Chunk text.

    Returns:
        True when the chunk reads as a heading rather than prose.
    """
    text = chunk.strip()
    if not text or len(text) > 60 or "\n" in text.strip("\n"):
        return False
    if text.startswith((">", "|", "-", "*", "#", "(", "（")):
        return False
    return True


def _split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a character prompt into its delimited sections.

    The authoring layout wraps every section title in a pair of rule lines::

        ═══════
        §1 最高信条
        ═══════
        body...

    Cutting on the rules therefore yields chunks that alternate title, body,
    title, body. The loop consumes pairs and re-syncs by itself when a stray
    rule appears inside a body.

    Args:
        text: Whole file content.

    Returns:
        Preamble text, then ``(raw_title, body)`` pairs in document order. An
        empty list when the file does not carry section rules.
    """
    lines = text.splitlines()
    separators = [i for i, line in enumerate(lines) if _SECTION_SEP.match(line)]
    if len(separators) < 2:
        return text, []
    preamble = "\n".join(lines[: separators[0]]).strip()
    chunks: list[str] = []
    bounds = separators + [len(lines)]
    for left, right in zip(separators, bounds[1:]):
        chunk = "\n".join(lines[left + 1 : right]).strip()
        if chunk:
            chunks.append(chunk)
    sections: list[tuple[str, str]] = []
    cursor = 0
    while cursor < len(chunks):
        current = chunks[cursor]
        following = chunks[cursor + 1] if cursor + 1 < len(chunks) else ""
        if _is_title_like(current) and not _is_title_like(following):
            sections.append((current, following))
            cursor += 2
            continue
        sections.append(("", current))
        cursor += 1
    return preamble, [(title, body) for title, body in sections if title or body]


def _split_greetings(body: str) -> list[Greeting]:
    """Split an opening-scene section into greetings.

    Args:
        body: Section text.

    Returns:
        Greetings, one per marker, with ``>`` quoting removed.
    """
    lines = body.splitlines()
    markers = [
        (i, match)
        for i, line in enumerate(lines)
        if (match := _GREETING_MARK.match(line.strip()))
    ]
    if not markers:
        return [Greeting(title="开场白", content=body.strip())] if body.strip() else []
    greetings: list[Greeting] = []
    for index, (start, match) in enumerate(markers):
        stop = markers[index + 1][0] if index + 1 < len(markers) else len(lines)
        quoted = [
            line[2:] if line.startswith("> ") else line.strip()
            for line in lines[start + 1 : stop]
            if line.strip()
        ]
        title = clean_title(f"{match.group(1)} {match.group(2)}")
        content = "\n".join(quoted).strip()
        if content:
            greetings.append(Greeting(title=title, content=content))
    return greetings


def _first_heading(text: str, default: str) -> str:
    """Read the first markdown heading as a display name.

    Args:
        text: File content.
        default: Fallback when the file has no heading.

    Returns:
        Cleaned heading text.
    """
    for line in text.splitlines():
        matched = _HEADING.match(line.strip())
        if matched:
            return matched.group(2).strip()
    return default


def variant_key_of(file_stem: str) -> str:
    """Classify a character file as full, condensed or unlabeled.

    Args:
        file_stem: File name without extension.

    Returns:
        :data:`FULL_VARIANT`, :data:`LITE_VARIANT` or :data:`BASE_VARIANT`.
    """
    if VARIANT_LABELS[FULL_VARIANT] in file_stem:
        return FULL_VARIANT
    if VARIANT_LABELS[LITE_VARIANT] in file_stem:
        return LITE_VARIANT
    return BASE_VARIANT


def parse_card_file(path: Path) -> tuple[str, str, CardVariant, str, str]:
    """Parse one character prompt file.

    Args:
        path: Markdown file of a single variant.

    Returns:
        Character name, variant key, the parsed variant, a one-line identity
        summary from the preamble, and a warning that is empty when the file
        matched the expected layout.
    """
    text = path.read_text(encoding="utf-8")
    key = variant_key_of(path.stem)
    name = clean_title(path.stem.split(CARD_MARK)[0].strip("_- ")) or path.stem[:40]
    preamble, sections = _split_sections(text)
    blocks: list[PromptBlock] = []
    greetings: list[Greeting] = []
    warning = ""
    if not sections:
        blocks.append(
            PromptBlock(
                id=stable_id("pb", str(path), key, "全文", "10"),
                title=clean_title(_first_heading(text, path.stem)),
                content=text.strip(),
                order=10,
            )
        )
        warning = f"{path.name}: 未找到章节分隔线，整篇作为单个提示块导入"
        logger.warning(f"[rp importer] {warning}")
    else:
        opening = "\n".join(line for line in preamble.splitlines() if line.strip())
        if opening:
            blocks.append(
                PromptBlock(
                    id=stable_id("pb", str(path), key, "opening"),
                    title=clean_title(_first_heading(opening, "身份定位"))[:60],
                    content=opening,
                    order=0,
                    kind="opening",
                )
            )
    order = 0
    for raw_title, body in sections:
        if not body:
            continue
        clean = clean_title(_SECTION_PREFIX.sub("", raw_title).strip() or raw_title)
        if "开场白" in clean:
            greetings.extend(_split_greetings(body))
            continue
        order += 10
        blocks.append(
            PromptBlock(
                id=stable_id("pb", str(path), key, clean, str(order)),
                title=clean or f"段落 {order}",
                content=f"{raw_title}\n\n{body}" if raw_title else body,
                order=order,
            )
        )
    summary = ""
    for line in preamble.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "---")):
            continue
        stripped = stripped.lstrip(">*-+ ").strip()
        candidate = clean_title(stripped)
        if len(candidate) < 6:
            continue
        summary = candidate[:200]
        break
    variant = CardVariant(
        label=VARIANT_LABELS[key],
        source_path=str(path),
        source_mtime=path.stat().st_mtime,
        blocks=blocks,
        greetings=greetings,
    )
    return name, key, variant, summary, warning


def _collect_bullets(body: str) -> list[tuple[str, str]] | None:
    """Read a chapter body as a bullet list, refusing partial matches.

    Args:
        body: Section text.

    Returns:
        ``(key, content)`` pairs when every top level line is a bullet,
        otherwise None so the caller keeps the section whole.
    """
    lines = body.splitlines()
    first = next((line for line in lines if line.strip()), "")
    if not _BULLET_KEY.match(first.strip()):
        return None
    bullets: list[tuple[str, list[str]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if bullets:
                bullets[-1][1].append("")
            continue
        matched = _BULLET_KEY.match(stripped)
        if matched and not line.startswith((" ", "\t")):
            bullets.append((matched.group(1), [matched.group(2)]))
            continue
        if not bullets:
            return None
        if line.startswith((" ", "\t")):
            bullets[-1][1].append(line.strip())
            continue
        if stripped.startswith(("-", "*")):
            bullets[-1][1].append(stripped.lstrip("-*").strip())
            continue
        return None
    if len(bullets) < 2:
        return None
    return [(key, "\n".join(parts).strip()) for key, parts in bullets]


def _priority(constant: bool, content: str) -> int:
    """Rank an entry so the budget keeps what matters most.

    Short constant entries are framing rules and stay on top. A constant entry
    that is too long is reference material, so it yields to entries that
    actually matched the current turn.

    Args:
        constant: Whether the entry is always injected.
        content: Entry body.

    Returns:
        Priority value used by the world book budget trim.
    """
    if constant:
        return 40 if estimate_tokens(content) <= 800 else 15
    return 20 if len(content) < 400 else 25


def _split_oversized(body: str, limit: int) -> list[tuple[str, str]]:
    """Break a long section into label-headed parts.

    Prefer the corpus's own ``**小标题**`` markers; fall back to fixed-size
    paragraph chunks so no budget ends up smaller than a single entry.

    Args:
        body: Section text.
        limit: Maximum characters per part.

    Returns:
        ``(label, text)`` parts, at least one.
    """
    lines = body.splitlines()
    marks = [
        (i, match.group(1))
        for i, line in enumerate(lines)
        if (match := _BOLD_LABEL.match(line.strip()))
    ]
    if len(marks) >= 2:
        parts: list[tuple[str, str]] = []
        head = "\n".join(lines[: marks[0][0]]).strip()
        if head:
            parts.append(("", head))
        for index, (start, label) in enumerate(marks):
            stop = marks[index + 1][0] if index + 1 < len(marks) else len(lines)
            chunk = "\n".join(lines[start:stop]).strip()
            if chunk:
                parts.append((label, chunk))
        if len(parts) >= 2:
            return parts
    parts = []
    buffer: list[str] = []
    size = 0
    for line in lines:
        buffer.append(line)
        size += len(line)
        if size >= limit:
            parts.append(("", "\n".join(buffer).strip()))
            buffer, size = [], 0
    if buffer:
        parts.append(("", "\n".join(buffer).strip()))
    return [part for part in parts if part[1]] or [("", body.strip())]


def parse_world_book(path: Path, collection: str) -> tuple[WorldBook, ImportItem]:
    """Parse one world book markdown file into entries.

    Args:
        path: Markdown file holding a setting compendium.
        collection: Directory name the book belongs to.

    Returns:
        The book and its report item.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    name = clean_title(_first_heading(text, path.stem)).split("——")[0].strip()
    book = WorldBook(
        id=stable_id("wb", collection, path.name),
        name=(name or path.stem)[:80],
        description=f"导入自 {path.name}",
        source_path=str(path),
        scan_depth=3,
        recursion_limit=1,
        token_budget=3000,
    )
    headings = [
        (i, len(match.group(1)), match.group(2))
        for i, line in enumerate(lines)
        if (match := _HEADING.match(line))
    ]
    used: dict[str, int] = {}
    body_start = headings[1][0] if len(headings) > 1 else len(lines)
    preamble = "\n".join(
        line
        for line in lines[:body_start]
        if line.strip() and not line.lstrip().startswith(("#", "---"))
    ).strip()
    if preamble:
        book.entries.append(
            BookEntry(
                id=stable_id("le", str(path), "preamble"),
                comment="使用约定与译名口径",
                content=preamble,
                constant=True,
                priority=40,
                tags=[collection],
                source=path.name,
            )
        )
    # The first heading names the document; every later one opens an entry.
    for position in range(1, len(headings)):
        start, level, title = headings[position]
        stop = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start + 1 : stop]).strip("\n").strip()
        if not body:
            continue
        clean = clean_title(title) or f"条目 {start}"
        suffix = used.get(clean, 0)
        used[clean] = suffix + 1
        keywords = extract_keywords(title)
        if level > 2:
            parent = next(
                (t for _, tl, t in reversed(headings[:position]) if tl <= 2), ""
            )
            for keyword in extract_keywords(parent):
                if keyword not in keywords:
                    keywords.append(keyword)
        constant = bool(_CONSTANT_TITLE.search(clean))
        bullets = _collect_bullets(body)
        heading_line = lines[start].strip()
        if bullets:
            for order, (key, content) in enumerate(bullets):
                entry_key = clean_title(key)
                book.entries.append(
                    BookEntry(
                        id=stable_id("le", str(path), entry_key, str(order)),
                        comment=entry_key,
                        content=f"{heading_line}\n\n**{entry_key}**：{content}".strip(),
                        keywords=(extract_keywords(key) or keywords)[:12],
                        constant=constant,
                        priority=_priority(constant, content),
                        order=100 + order,
                        tags=[collection],
                        source=path.name,
                    )
                )
            continue
        parts = (
            _split_oversized(body, MAX_ENTRY_CHARS)
            if len(body) > MAX_ENTRY_CHARS
            else [("", body)]
        )
        for order, (label, chunk) in enumerate(parts):
            comment = (
                clean
                if len(parts) == 1
                else f"{clean} · {label or f'第{order + 1}部分'}"
            )
            content = (
                chunk
                if chunk.startswith(heading_line)
                else f"{heading_line}\n\n{chunk}"
            )
            book.entries.append(
                BookEntry(
                    id=stable_id("le", str(path), clean, str(suffix), str(order)),
                    comment=comment[:120],
                    content=content,
                    keywords=keywords[:12],
                    constant=constant,
                    priority=_priority(constant, chunk),
                    order=100 + position * 10 + order,
                    tags=[collection],
                    source=path.name,
                )
            )
    if not book.entries:
        book.entries.append(
            BookEntry(
                id=stable_id("le", str(path), "whole"),
                comment=book.name,
                content=text.strip(),
                keywords=extract_keywords(book.name),
                priority=40,
                tags=[collection],
                source=path.name,
            )
        )
    item = ImportItem(
        path=str(path),
        kind="worldbook",
        detail=book.name,
        entries=len(book.entries),
    )
    if len(headings) < 2:
        item.warning = f"{path.name}: 标题结构不足，整篇作为常驻条目"
    return book, item


@dataclass
class CorpusScan:
    """Result of reading a corpus directory."""

    cards: dict[str, CharacterCard] = field(default_factory=dict)
    books: dict[str, WorldBook] = field(default_factory=dict)
    report: ImportReport = field(default_factory=ImportReport)


def scan_corpus(root: Path | str) -> CorpusScan:
    """Read a markdown corpus without writing anything.

    Args:
        root: Directory holding the roleplay material.

    Returns:
        Cards and world books keyed by stable ids, plus the report.
    """
    scan = CorpusScan()
    base = Path(str(root)).expanduser()
    if not base.is_dir():
        scan.report.warnings.append(f"目录不存在：{base}")
        return scan
    base = base.resolve()
    card_dirs: dict[str, Path] = {}
    book_dirs: dict[Path, list[str]] = {}
    for path in sorted(base.rglob("*.md")):
        relative = path.relative_to(base)
        if any(part.startswith(".") for part in relative.parts):
            continue
        # One collection per top level directory, used as the card tag.
        collection = relative.parts[0] if len(relative.parts) > 1 else base.name
        tags = [collection]
        if path.parent != base and path.parent.name != collection:
            tags.append(path.parent.name)
        if CARD_MARK in path.name:
            name, key, variant, summary, warning = parse_card_file(path)
            card_id = stable_id("card", collection, name)
            card = scan.cards.get(card_id) or CharacterCard(
                id=card_id, name=name, summary=summary, tags=list(tags)
            )
            final_key = key
            while final_key in card.variants:
                final_key = f"{key}_{len(card.variants) + 1}"
            if final_key != key:
                variant.label = path.stem.split(CARD_MARK)[-1].strip("_- ") or path.stem
                scan.report.warnings.append(
                    f"{path.name}: 与已有变体同名，按 {final_key} 单独保留"
                )
            card.variants[final_key] = variant
            if not card.summary:
                card.summary = variant.blocks[0].title if variant.blocks else ""
            card.tags = list(dict.fromkeys([*card.tags, *tags]))
            scan.cards[card_id] = card
            card_dirs.setdefault(card_id, path.parent)
            if warning:
                scan.report.warnings.append(warning)
            scan.report.items.append(
                ImportItem(
                    path=str(path),
                    kind=f"card:{final_key}",
                    detail=name,
                    blocks=len(variant.blocks),
                    greetings=len(variant.greetings),
                )
            )
            continue
        if not BOOK_NAME_RE.search(path.stem) or BOOK_SKIP_RE.search(path.stem):
            continue
        book, item = parse_world_book(path, collection)
        scan.books[book.id] = book
        book_dirs.setdefault(path.parent, []).append(book.id)
        scan.report.items.append(item)
        if item.warning:
            scan.report.warnings.append(item.warning)
    for card_id, card in scan.cards.items():
        # Bind the books stored in the card's own directory and every directory
        # above it, so pointing at a sub-folder still attaches its setting books.
        directory = card_dirs.get(card_id, base)
        chain: list[Path] = [directory]
        for parent in directory.parents:
            chain.append(parent)
            if parent == base:
                break
        card.world_book_ids = [
            book.id for current in chain for book.id in book_dirs.get(current, [])
        ]
        # Prefer the condensed writing as default: it is the one that fits a
        # chat context next to the history, and it stays switchable per card.
        if "lite" in card.variants:
            card.active_variant = "lite"
        elif "full" in card.variants:
            card.active_variant = "full"
        else:
            card.active_variant = max(
                card.variants, key=lambda key: len(card.variants[key].blocks)
            )
    if not scan.cards and not scan.books:
        scan.report.warnings.append(
            f"未在 {base} 找到角色卡或世界书（角色卡文件名需含 {CARD_MARK}）"
        )
    scan.report.files = len(
        [item for item in scan.report.items if item.kind.startswith("card")]
    )
    scan.report.cards = len(scan.cards)
    return scan


async def commit_import(store: RPStore, scan: CorpusScan) -> ImportReport:
    """Persist a scan, preserving user edits the importer cannot know.

    Args:
        store: Destination store.
        scan: Output of :func:`scan_corpus`.

    Returns:
        A report describing what was written.
    """
    report = ImportReport(
        warnings=list(scan.report.warnings),
        cards=scan.report.cards,
        files=scan.report.files,
    )
    for book in scan.books.values():
        existing = store.get_book(book.id)
        if existing:
            book.enabled = existing.enabled
            book.global_scope = existing.global_scope
            book.token_budget = existing.token_budget
            book.scan_depth = existing.scan_depth
            book.recursion_limit = existing.recursion_limit
        await store.save_book(book)
        report.items.append(
            ImportItem(
                path=book.source_path,
                kind="worldbook",
                detail=book.name,
                entries=len(book.entries),
            )
        )
    for card in scan.cards.values():
        existing = store.get_card(card.id)
        if existing:
            card.enabled = existing.enabled
            card.persona_id = existing.persona_id
            card.tags = list(dict.fromkeys([*existing.tags, *card.tags]))
            kept = [
                i
                for i in existing.world_book_ids
                if i in scan.books or store.get_book(i)
            ]
            card.world_book_ids = kept or card.world_book_ids
            if existing.active_variant in card.variants:
                card.active_variant = existing.active_variant
            for key, variant in card.variants.items():
                previous = existing.variants.get(key)
                if not previous:
                    continue
                flags = {block.title: block.enabled for block in previous.blocks}
                for block in variant.blocks:
                    if block.title in flags:
                        block.enabled = flags[block.title]
        await store.save_card(card)
        variant = card.get_variant()
        report.items.append(
            ImportItem(
                path=variant.source_path if variant else "",
                kind="card",
                detail=card.name,
                blocks=len(variant.blocks) if variant else 0,
                greetings=len(variant.greetings) if variant else 0,
            )
        )
    return report
