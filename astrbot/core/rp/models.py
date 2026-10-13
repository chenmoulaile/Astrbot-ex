"""Data models of the roleplay engine: character cards and world books.

Everything here is plain, serializable data. Nothing in this package touches
AstrBot internals, so the engine can be unit tested and reused by the pipeline
hook, the dashboard service and the markdown importer alike.
"""

from __future__ import annotations

import re
import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .tokens import estimate_tokens

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def new_id(prefix: str) -> str:
    """Build a short, filesystem-safe identifier.

    Args:
        prefix: Human readable type tag, e.g. ``card`` or ``wb``.

    Returns:
        Identifier matching :data:`ID_RE`.
    """
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def validate_safe_id(value: str) -> str:
    """Validate an identifier that will be used as a file name stem.

    Args:
        value: Candidate identifier.

    Returns:
        The value unchanged.

    Raises:
        ValueError: If the value could escape the storage directory.
    """
    if not ID_RE.match(value) or ".." in value:
        raise ValueError(f"unsafe id: {value!r}")
    return value


class SelectiveLogic(str, Enum):
    """How secondary keywords gate an entry that already matched a keyword."""

    AND_ANY = "and_any"
    AND_ALL = "and_all"
    NOT_ANY = "not_any"
    NOT_ALL = "not_all"


class EntryPosition(str, Enum):
    """Where a matched world book entry is placed in the request."""

    SYSTEM_TOP = "system_top"
    SYSTEM_TAIL = "system_tail"
    HISTORY_DEPTH = "history_depth"


class Greeting(BaseModel):
    """One opening line a character can start a conversation with."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: new_id("gr"))
    title: str = ""
    content: str = ""

    @property
    def tokens(self) -> int:
        """Estimated token cost of the greeting body."""
        return estimate_tokens(self.content)


class PromptBlock(BaseModel):
    """A switchable section of a character prompt, e.g. ``§6 心理内核``."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: new_id("pb"))
    title: str = ""
    content: str = ""
    order: int = 100
    enabled: bool = True
    kind: str = "section"

    @property
    def tokens(self) -> int:
        """Estimated token cost when this block is enabled."""
        return estimate_tokens(self.content)


class CardVariant(BaseModel):
    """One complete writing of a character, e.g. full or condensed."""

    model_config = ConfigDict(extra="ignore")

    label: str = ""
    source_path: str = ""
    source_mtime: float = 0.0
    blocks: list[PromptBlock] = Field(default_factory=list)
    greetings: list[Greeting] = Field(default_factory=list)

    def prompt_text(self) -> str:
        """Join enabled blocks in order.

        Returns:
            The character prompt for this variant.
        """
        enabled = [b for b in self.blocks if b.enabled and b.content.strip()]
        enabled.sort(key=lambda b: (b.order, b.title))
        return "\n\n".join(b.content.rstrip() for b in enabled)

    @property
    def tokens(self) -> int:
        """Estimated token cost of the enabled blocks."""
        return estimate_tokens(self.prompt_text())


class CharacterCard(BaseModel):
    """A roleplay persona plus its world books and prompt variants."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: new_id("card"))
    name: str = ""
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    active_variant: str = "lite"
    variants: dict[str, CardVariant] = Field(default_factory=dict)
    world_book_ids: list[str] = Field(default_factory=list)
    persona_id: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        return validate_safe_id(value)

    def get_variant(self, variant: str | None = None) -> CardVariant | None:
        """Resolve a variant by key, falling back to the active one.

        Args:
            variant: Variant key such as ``lite``; None uses the active key.

        Returns:
            The variant, or None when the card holds no variants.
        """
        key = variant or self.active_variant
        if key in self.variants:
            return self.variants[key]
        for fallback in ("lite", "full", "base"):
            if fallback in self.variants:
                return self.variants[fallback]
        return next(iter(self.variants.values()), None)

    def prompt_text(self) -> str:
        """Prompt text of the active variant.

        Returns:
            Assembled prompt, empty string when no variant exists.
        """
        found = self.get_variant()
        return found.prompt_text() if found else ""

    @property
    def tokens(self) -> int:
        """Estimated token cost of the active variant."""
        found = self.get_variant()
        return found.tokens if found else 0


class BookEntry(BaseModel):
    """One triggerable knowledge entry of a world book."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: new_id("le"))
    comment: str = ""
    content: str = ""
    enabled: bool = True
    keywords: list[str] = Field(default_factory=list)
    secondary_keywords: list[str] = Field(default_factory=list)
    selective_logic: SelectiveLogic = SelectiveLogic.AND_ANY
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    constant: bool = False
    position: EntryPosition = EntryPosition.SYSTEM_TAIL
    depth: int = 0
    order: int = 100
    priority: int = 10
    cooldown_turns: int = 0
    tags: list[str] = Field(default_factory=list)
    source: str = ""

    @property
    def tokens(self) -> int:
        """Estimated token cost of the entry body."""
        return estimate_tokens(self.content)


class WorldBook(BaseModel):
    """A named collection of keyword-gated knowledge entries."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: new_id("wb"))
    name: str = ""
    description: str = ""
    enabled: bool = True
    global_scope: bool = False
    scan_depth: int = 2
    recursion_limit: int = 1
    token_budget: int = 2000
    entries: list[BookEntry] = Field(default_factory=list)
    source_path: str = ""

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        return validate_safe_id(value)

    def select_entries(self, ids: list[str]) -> list[BookEntry]:
        """Pick entries by id, keeping the stored order.

        Args:
            ids: Entry identifiers to select.

        Returns:
            Matching entries, unknown ids ignored.
        """
        wanted = set(ids)
        return [e for e in self.entries if e.id in wanted]
