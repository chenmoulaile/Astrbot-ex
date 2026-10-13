"""JSON persistence for character cards and world books.

One file per card and per book under ``data/rp``, so the corpus stays
hand-editable and diffable. Loading is forgiving: a broken file is logged and
skipped instead of taking the whole engine down.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import aiofiles

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .models import BookEntry, CharacterCard, WorldBook


class RPStore:
    """In-memory registry of cards and world books backed by JSON files."""

    def __init__(self, root: Path | str | None = None) -> None:
        """Create a store.

        Args:
            root: Storage directory. Defaults to ``<AstrBot data>/rp``.
        """
        base = Path(str(root)) if root else Path(get_astrbot_data_path()) / "rp"
        self.root = base
        self.card_dir = base / "cards"
        self.book_dir = base / "worldbooks"
        self._cards: dict[str, CharacterCard] = {}
        self._books: dict[str, WorldBook] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def initialize(self) -> None:
        """Load every card and book from disk. Safe to call repeatedly."""
        async with self._lock:
            if self._loaded:
                return
            self._cards = {}
            self._books = {}
            for path in sorted(self.card_dir.glob("*.json")):
                try:
                    card = CharacterCard.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                    self._cards[card.id] = card
                except Exception as exc:
                    logger.warning(f"[rp] skipped broken card {path.name}: {exc}")
                    continue
            for path in sorted(self.book_dir.glob("*.json")):
                try:
                    book = WorldBook.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                    self._books[book.id] = book
                except Exception as exc:
                    logger.warning(f"[rp] skipped broken world book {path.name}: {exc}")
                    continue
            self._loaded = True
            logger.info(
                f"[rp] loaded {len(self._cards)} cards, {len(self._books)} world books"
            )

    async def reload(self) -> None:
        """Drop the cache and read the whole directory again."""
        self._loaded = False
        await self.initialize()

    def list_cards(self) -> list[CharacterCard]:
        """All cards, sorted by name then id.

        Returns:
            Card list with a stable ordering for the dashboard.
        """
        return sorted(self._cards.values(), key=lambda c: (c.name, c.id))

    def get_card(self, card_id: str) -> CharacterCard | None:
        """Look a card up by id."""
        return self._cards.get(card_id)

    def find_card_by_persona(self, persona_id: str | None) -> CharacterCard | None:
        """Find the card bound to an AstrBot persona.

        Args:
            persona_id: Persona identifier, may be None.

        Returns:
            The matching card, or None when no card claims that persona.
        """
        if not persona_id:
            return None
        for card in self._cards.values():
            if card.persona_id == persona_id:
                return card
        return None

    def search_cards(self, keyword: str) -> list[CharacterCard]:
        """Match cards by name, id or tag, case-insensitively.

        Args:
            keyword: Substring to look for; empty matches everything.

        Returns:
            Matching cards in list order.
        """
        needle = keyword.strip().lower()
        cards = self.list_cards()
        if not needle:
            return cards
        return [
            c
            for c in cards
            if needle in c.name.lower()
            or needle == c.id.lower()
            or any(needle in tag.lower() for tag in c.tags)
        ]

    async def save_card(self, card: CharacterCard) -> CharacterCard:
        """Insert or replace a card and persist it.

        Args:
            card: Card to store.

        Returns:
            The stored card.
        """
        self._cards[card.id] = card
        await self._write_json(
            self.card_dir / f"{card.id}.json",
            card.model_dump(mode="json"),
        )
        return card

    async def delete_card(self, card_id: str) -> bool:
        """Remove a card and its file.

        Args:
            card_id: Card identifier.

        Returns:
            True when something was deleted.
        """
        existed = self._cards.pop(card_id, None) is not None
        path = self.card_dir / f"{card_id}.json"
        if path.exists():
            path.unlink()
            existed = True
        return existed

    def list_books(self) -> list[WorldBook]:
        """All world books, sorted by name then id."""
        return sorted(self._books.values(), key=lambda b: (b.name, b.id))

    def get_book(self, book_id: str) -> WorldBook | None:
        """Look a world book up by id."""
        return self._books.get(book_id)

    async def save_book(self, book: WorldBook) -> WorldBook:
        """Insert or replace a world book and persist it."""
        self._books[book.id] = book
        await self._write_json(
            self.book_dir / f"{book.id}.json",
            book.model_dump(mode="json"),
        )
        return book

    async def delete_book(self, book_id: str) -> bool:
        """Remove a world book, its file, and card references to it."""
        existed = self._books.pop(book_id, None) is not None
        path = self.book_dir / f"{book_id}.json"
        if path.exists():
            path.unlink()
            existed = True
        for card in [c for c in self._cards.values() if book_id in c.world_book_ids]:
            card.world_book_ids = [i for i in card.world_book_ids if i != book_id]
            await self.save_card(card)
        return existed

    async def upsert_entry(self, book_id: str, entry: BookEntry) -> BookEntry:
        """Insert or replace one entry inside a world book.

        Args:
            book_id: Parent world book id.
            entry: Entry to store; replaces the entry with the same id.

        Returns:
            The stored entry.

        Raises:
            KeyError: If the world book does not exist.
        """
        book = self._books.get(book_id)
        if book is None:
            raise KeyError(f"world book not found: {book_id}")
        for index, current in enumerate(book.entries):
            if current.id == entry.id:
                book.entries[index] = entry
                break
        else:
            book.entries.append(entry)
        await self.save_book(book)
        return entry

    async def delete_entry(self, book_id: str, entry_id: str) -> bool:
        """Remove one entry from a world book.

        Args:
            book_id: Parent world book id.
            entry_id: Entry to remove.

        Returns:
            True when the entry existed.

        Raises:
            KeyError: If the world book does not exist.
        """
        book = self._books.get(book_id)
        if book is None:
            raise KeyError(f"world book not found: {book_id}")
        kept = [e for e in book.entries if e.id != entry_id]
        if len(kept) == len(book.entries):
            return False
        book.entries = kept
        await self.save_book(book)
        return True

    async def books_for_card(self, card: CharacterCard | None) -> list[WorldBook]:
        """Books that apply to a request.

        Args:
            card: Active card, or None for a conversation without one.

        Returns:
            Enabled books: the card's own first, then global books.
        """
        books: list[WorldBook] = []
        seen: set[str] = set()
        if card is not None:
            for book_id in card.world_book_ids:
                book = self._books.get(book_id)
                if book and book.enabled and book.id not in seen:
                    seen.add(book.id)
                    books.append(book)
        for book in sorted(self._books.values(), key=lambda b: (b.name, b.id)):
            if book.enabled and book.global_scope and book.id not in seen:
                seen.add(book.id)
                books.append(book)
        return books

    async def _write_json(self, path: Path, payload: dict) -> None:
        """Write JSON atomically through a temporary sibling file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        async with aiofiles.open(tmp, "w", encoding="utf-8") as handle:
            await handle.write(text)
        os.replace(tmp, path)


_store: RPStore | None = None


def get_rp_store() -> RPStore:
    """The process-wide RP store.

    Returns:
        Shared store instance, created on first call.
    """
    global _store
    if _store is None:
        _store = RPStore()
    return _store
