"""Dashboard service for the roleplay engine.

Exposes cards, world books, corpus import and a prompt build preview. The card
store is the source of truth for a character's text; an AstrBot persona is kept
in sync as its projection so conversations and every platform pick it up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.rp import (
    BookEntry,
    CardVariant,
    CharacterCard,
    PromptBlock,
    WorldBook,
    apply_history,
    build_injection,
    compose_system_prompt,
    estimate_tokens,
    get_rp_store,
    keyword_hit,
    scan_books,
    secondary_gate,
    trace_of,
)
from astrbot.core.rp.importer import commit_import, scan_corpus
from astrbot.core.rp.link import sync_card_persona, unsync_card_persona
from astrbot.core.star.context import Context

CARD_FIELDS = {
    "name",
    "summary",
    "tags",
    "enabled",
    "active_variant",
    "world_book_ids",
}
BOOK_FIELDS = {
    "name",
    "description",
    "enabled",
    "global_scope",
    "scan_depth",
    "recursion_limit",
    "token_budget",
}
ENTRY_FIELDS = {
    "id",
    "comment",
    "content",
    "enabled",
    "keywords",
    "secondary_keywords",
    "selective_logic",
    "case_sensitive",
    "whole_word",
    "regex",
    "constant",
    "position",
    "depth",
    "order",
    "priority",
    "cooldown_turns",
    "tags",
}


class RPServiceError(Exception):
    pass


class RPService:
    """Roleplay operations behind ``/api/rp``."""

    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.context: Context = core_lifecycle.star_context
        self.store = get_rp_store()

    async def _ready(self) -> None:
        await self.store.initialize()

    def _card_view(self, card: CharacterCard, detail: bool) -> dict[str, Any]:
        """Serialize a card, dropping heavy text unless detail is requested.

        Args:
            card: Character card.
            detail: Include block and greeting bodies.

        Returns:
            JSON-ready dictionary.
        """
        variants: dict[str, Any] = {}
        for key, variant in card.variants.items():
            blocks = [
                {
                    "id": block.id,
                    "title": block.title,
                    "order": block.order,
                    "enabled": block.enabled,
                    "kind": block.kind,
                    "tokens": block.tokens,
                    "chars": len(block.content),
                    **({"content": block.content} if detail else {}),
                }
                for block in variant.blocks
            ]
            variants[key] = {
                "label": variant.label,
                "source_path": variant.source_path,
                "tokens": variant.tokens,
                "blocks": blocks,
                "greetings": [
                    {
                        "id": greeting.id,
                        "title": greeting.title,
                        "tokens": greeting.tokens,
                        **({"content": greeting.content} if detail else {}),
                    }
                    for greeting in variant.greetings
                ],
            }
        return {
            "id": card.id,
            "name": card.name,
            "summary": card.summary,
            "tags": card.tags,
            "enabled": card.enabled,
            "active_variant": card.active_variant,
            "persona_id": card.persona_id,
            "world_book_ids": card.world_book_ids,
            "tokens": card.tokens,
            "variants": variants,
        }

    async def overview(self) -> dict[str, Any]:
        """Counts and storage location shown at the top of the RP pages."""
        await self._ready()
        cards = self.store.list_cards()
        books = self.store.list_books()
        return {
            "cards": len(cards),
            "books": len(books),
            "entries": sum(len(book.entries) for book in books),
            "bound": len([card for card in cards if card.persona_id]),
            "storage": str(self.store.root),
            "total_tokens": sum(card.tokens for card in cards),
        }

    async def list_cards(self, data: object) -> dict[str, Any]:
        """Cards in summary form.

        Args:
            data: Payload with an optional ``keyword``.

        Returns:
            ``{"cards": [...], "total": n}``.
        """
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        keyword = str(payload.get("keyword", ""))
        cards = self.store.search_cards(keyword)
        return {
            "cards": [self._card_view(card, False) for card in cards],
            "total": len(cards),
        }

    async def card_detail(self, data: object) -> dict[str, Any]:
        """One card with every block and greeting body included."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        card = self.store.get_card(str(payload.get("card_id", "")))
        if card is None:
            raise RPServiceError("角色卡不存在")
        return self._card_view(card, True)

    async def save_card(self, data: object) -> dict[str, Any]:
        """Update card fields, block toggles, block bodies and book bindings.

        Args:
            data: Payload with ``card_id`` plus any of ``card`` (field dict),
                ``variant`` (key, defaults to the active one) and ``blocks``
                (list of partial block updates).

        Returns:
            The refreshed card view.
        """
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        card = self.store.get_card(str(payload.get("card_id", "")))
        if card is None:
            raise RPServiceError("角色卡不存在")
        changes = payload.get("card") or {}
        if isinstance(changes, dict):
            for key, value in changes.items():
                if key in CARD_FIELDS:
                    setattr(card, key, value)
        variant_key = str(payload.get("variant") or card.active_variant)
        variant = card.variants.get(variant_key)
        if variant is None:
            raise RPServiceError(f"版本不存在：{variant_key}")
        updates = payload.get("blocks") or []
        if isinstance(updates, list):
            by_id = {block.id: block for block in variant.blocks}
            for item in updates:
                if not isinstance(item, dict):
                    continue
                block = by_id.get(str(item.get("id", "")))
                if block is None:
                    continue
                for field in ("title", "content", "kind", "order"):
                    if field in item:
                        setattr(block, field, item[field])
                if "enabled" in item:
                    block.enabled = bool(item["enabled"])
        await self.store.save_card(card)
        persona_id = await sync_card_persona(
            self.context.persona_manager, self.store, card
        )
        return {"card": self._card_view(card, True), "persona_id": persona_id}

    async def create_card(self, data: object) -> dict[str, Any]:
        """Create an empty card so a prompt can be written from the UI."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        name = str(payload.get("name", "")).strip()
        if not name:
            raise RPServiceError("角色卡名称不能为空")
        card = CharacterCard(
            name=name,
            summary=str(payload.get("summary", "")),
            active_variant="base",
            variants={
                "base": CardVariant(
                    label=str(payload.get("label") or "自定义"),
                    blocks=[PromptBlock(title="角色设定", content="", order=10)],
                )
            },
        )
        await self.store.save_card(card)
        return self._card_view(card, True)

    async def delete_card(self, data: object) -> dict[str, Any]:
        """Remove a card together with its persona projection."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        card = self.store.get_card(str(payload.get("card_id", "")))
        if card is None:
            raise RPServiceError("角色卡不存在")
        await unsync_card_persona(self.context.persona_manager, card)
        await self.store.delete_card(card.id)
        return {"deleted": card.id}

    async def bind_card(self, data: object) -> dict[str, Any]:
        """Bind a card to a conversation, addressed by unified message origin.

        Args:
            data: Payload with ``umo`` and ``card_id``; an empty card_id clears.

        Returns:
            The bound persona id, or None when cleared.
        """
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        umo = str(payload.get("umo", "")).strip()
        if len(umo.split(":")) != 3:
            raise RPServiceError("会话标识应为 platform:类型:会话ID 三段式")
        card_id = str(payload.get("card_id", "")).strip()
        persona_id = None
        if card_id:
            card = self.store.get_card(card_id)
            if card is None:
                raise RPServiceError("角色卡不存在")
            persona_id = await sync_card_persona(
                self.context.persona_manager, self.store, card
            )
        await self.context.conversation_manager.update_conversation(
            umo, persona_id=persona_id
        )
        return {"umo": umo, "persona_id": persona_id}

    async def list_books(self) -> dict[str, Any]:
        """World books in summary form."""
        await self._ready()
        books = self.store.list_books()
        return {
            "books": [
                {
                    "id": book.id,
                    "name": book.name,
                    "description": book.description,
                    "enabled": book.enabled,
                    "global_scope": book.global_scope,
                    "scan_depth": book.scan_depth,
                    "recursion_limit": book.recursion_limit,
                    "token_budget": book.token_budget,
                    "source_path": book.source_path,
                    "entries": len(book.entries),
                    "constants": len(
                        [entry for entry in book.entries if entry.constant]
                    ),
                }
                for book in books
            ],
            "total": len(books),
        }

    async def book_detail(self, data: object) -> dict[str, Any]:
        """One world book with all entries included."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        book = self.store.get_book(str(payload.get("book_id", "")))
        if book is None:
            raise RPServiceError("世界书不存在")
        view = book.model_dump(mode="json")
        for entry in view["entries"]:
            entry["tokens"] = estimate_tokens(entry["content"])
        return view

    async def save_book(self, data: object) -> dict[str, Any]:
        """Update world book settings, or create one when the id is new."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        book_id = str(payload.get("book_id", "")).strip()
        book = self.store.get_book(book_id) if book_id else WorldBook()
        if book is None:
            book = WorldBook(id=book_id)
        changes = payload.get("book") or payload
        if isinstance(changes, dict):
            for key, value in changes.items():
                if key in BOOK_FIELDS:
                    setattr(book, key, value)
        if not book.name.strip():
            raise RPServiceError("世界书名称不能为空")
        await self.store.save_book(book)
        return {"id": book.id, "name": book.name, "entries": len(book.entries)}

    async def delete_book(self, data: object) -> dict[str, Any]:
        """Remove a world book and every card reference to it."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        book_id = str(payload.get("book_id", ""))
        if not await self.store.delete_book(book_id):
            raise RPServiceError("世界书不存在")
        return {"deleted": book_id}

    async def save_entry(self, data: object) -> dict[str, Any]:
        """Insert or update one world book entry."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        book_id = str(payload.get("book_id", ""))
        book = self.store.get_book(book_id)
        if book is None:
            raise RPServiceError("世界书不存在")
        raw = payload.get("entry") or {}
        if not isinstance(raw, dict):
            raise RPServiceError("条目格式不正确")
        entry = (
            next(
                (item for item in book.entries if item.id == raw.get("id")),
                None,
            )
            or BookEntry()
        )
        for key, value in raw.items():
            if key in ENTRY_FIELDS:
                setattr(entry, key, value)
        if not entry.content.strip():
            raise RPServiceError("条目内容不能为空")
        await self.store.upsert_entry(book_id, entry)
        return {
            "id": entry.id,
            "book_id": book_id,
            "tokens": entry.tokens,
            "keywords": entry.keywords,
        }

    async def delete_entry(self, data: object) -> dict[str, Any]:
        """Remove one entry from a world book."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        book_id = str(payload.get("book_id", ""))
        entry_id = str(payload.get("entry_id", ""))
        if not await self.store.delete_entry(book_id, entry_id):
            raise RPServiceError("条目不存在")
        return {"deleted": entry_id}

    async def test_entry(self, data: object) -> dict[str, Any]:
        """Try an entry's keywords against a sample text without storing it."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        raw = payload.get("entry") or {}
        fields = {
            key: value
            for key, value in raw.items()
            if key in ENTRY_FIELDS and key != "id"
        }
        fields.setdefault("content", "x")
        entry = BookEntry(**fields)
        sample = str(payload.get("text", ""))
        texts = [sample]
        matched = [
            keyword
            for keyword in entry.keywords
            if keyword.strip() and keyword_hit(keyword, texts, entry)
        ]
        secondary_matched = [
            keyword
            for keyword in entry.secondary_keywords
            if keyword.strip() and keyword_hit(keyword, texts, entry)
        ]
        fires = bool(entry.constant or matched) and secondary_gate(entry, texts)
        return {
            "matched": matched,
            "secondary_matched": secondary_matched,
            "fires": fires,
        }

    async def import_scan(self, data: object) -> dict[str, Any]:
        """Preview a corpus directory without writing anything."""
        payload = data if isinstance(data, dict) else {}
        path = str(payload.get("path", "")).strip()
        if not path:
            raise RPServiceError("请填写语料目录")
        scan = scan_corpus(Path(path))
        return {
            "summary": scan.report.summary(),
            "warnings": scan.report.warnings,
            "items": [item.__dict__ for item in scan.report.items],
            "cards": len(scan.cards),
            "books": len(scan.books),
            "entries": sum(len(book.entries) for book in scan.books.values()),
        }

    async def import_commit(self, data: object) -> dict[str, Any]:
        """Import a corpus directory and refresh persona projections."""
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        path = str(payload.get("path", "")).strip()
        if not path:
            raise RPServiceError("请填写语料目录")
        scan = scan_corpus(Path(path))
        if not scan.cards and not scan.books:
            raise RPServiceError("目录中没有可导入的角色卡或世界书")
        report = await commit_import(self.store, scan)
        synced = 0
        for card in scan.cards.values():
            await sync_card_persona(self.context.persona_manager, self.store, card)
            synced += 1
        return {
            "summary": report.summary(),
            "warnings": report.warnings,
            "synced_personas": synced,
        }

    async def build_preview(self, data: object) -> dict[str, Any]:
        """Assemble the prompt a conversation would send to the model.

        Args:
            data: Payload with ``card_id`` and an optional sample ``message``.

        Returns:
            Final system prompt, history, injection trace and token estimates.
        """
        await self._ready()
        payload = data if isinstance(data, dict) else {}
        card_id = str(payload.get("card_id", ""))
        card = self.store.get_card(card_id) if card_id else None
        if card_id and card is None:
            raise RPServiceError("角色卡不存在")
        message = str(payload.get("message", ""))
        scan_message = f"{message}\n{card.name}" if card else message
        history = [
            item for item in (payload.get("history") or []) if isinstance(item, dict)
        ]
        books = await self.store.books_for_card(card)
        off = {str(book_id) for book_id in (payload.get("books_off") or [])}
        books = [book for book in books if book.id not in off]
        result = scan_books(books, message=scan_message, contexts=history)
        injection = build_injection(result)
        persona_prompt = (
            f"# Persona Instructions\n\n{card.prompt_text()}\n" if card else ""
        )
        system_prompt = compose_system_prompt(persona_prompt, injection)
        contexts = apply_history(history, injection)
        return {
            "system_prompt": system_prompt,
            "system_tokens": estimate_tokens(system_prompt),
            "card_tokens": card.tokens if card else 0,
            "injected_tokens": injection.injected_tokens,
            "trace": trace_of(injection),
            "skipped": [
                {"entry": hit.entry.comment, "tokens": hit.tokens}
                for hit in result.over_budget
            ],
            "history": [
                {
                    "role": item.get("role"),
                    "content": str(item.get("content", ""))[:400],
                    "injected": bool(item.get("_no_save")),
                }
                for item in contexts
            ],
            "books": [book.name for book in books],
        }

    async def platforms(self) -> dict[str, Any]:
        """Configured platforms, so the relay panel can offer targets."""
        configured = self.context.get_config().get("platforms", [])
        running = {
            platform.meta().id
            for platform in self.context.platform_manager.platform_insts
        }
        views = []
        for item in configured if isinstance(configured, list) else []:
            if not isinstance(item, dict):
                continue
            views.append(
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "name": item.get("name") or item.get("id"),
                    "enable": bool(item.get("enable", True)),
                    "active": item.get("id") in running,
                }
            )
        return {
            "platforms": views,
            "message_types": [member.value for member in MessageType],
        }

    async def send(self, data: object) -> dict[str, Any]:
        """Send a message through a platform, e.g. to a QQ friend or group.

        Args:
            data: Payload with ``platform_id``, ``message_type``, ``target``
                and ``text``.

        Returns:
            Whether a platform instance accepted the message.

        Raises:
            RPServiceError: On missing arguments or no matching platform.
        """
        payload = data if isinstance(data, dict) else {}
        platform_id = str(payload.get("platform_id", "")).strip()
        message_type = str(payload.get("message_type", "")).strip()
        target = str(payload.get("target", "")).strip()
        text = str(payload.get("text", "")).strip()
        if not (platform_id and target and text):
            raise RPServiceError("需要平台、目标与正文")
        try:
            kind = MessageType(message_type or MessageType.FRIEND_MESSAGE.value)
        except ValueError as exc:
            raise RPServiceError(f"会话类型不合法：{message_type}") from exc
        umo = f"{platform_id}:{kind.value}:{target}"
        sent = await self.context.send_message(umo, MessageChain([Plain(text=text)]))
        if not sent:
            raise RPServiceError("没有找到对应的平台，或该平台不支持主动发送")
        return {"sent": True, "umo": umo}
