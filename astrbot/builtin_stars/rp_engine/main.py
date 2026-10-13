from __future__ import annotations

import copy

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core import logger
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.rp import (
    CharacterCard,
    apply_history,
    begin_dialog_history,
    build_injection,
    compose_system_prompt,
    get_rp_store,
    scan_books,
    trace_of,
)
from astrbot.core.rp.importer import commit_import, scan_corpus
from astrbot.core.rp.link import sync_card_persona, unsync_card_persona
from astrbot.core.star.filter.command import GreedyStr

STATE_KEY = "rp_engine"
DEFAULT_STATE: dict = {
    "books_off": [],
    "last_fired": {},
    "turn": 0,
    "trace": [],
    "skipped": [],
    "greeting": "",
}


class RPRoleplay(star.Star):
    """Character cards, world books and corpus import for every platform."""

    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        self.context = context
        self.config = config or {}
        self.store = get_rp_store()

    async def initialize(self) -> None:
        await self.store.initialize()

    async def _state(self, umo: str) -> dict:
        """Read per-session roleplay state, seeded with current defaults."""
        stored = await sp.session_get(umo, STATE_KEY, None)
        state = copy.deepcopy(DEFAULT_STATE)
        if isinstance(stored, dict):
            state.update({key: value for key, value in stored.items() if key in state})
        return state

    async def _save_state(self, umo: str, state: dict) -> None:
        await sp.session_put(umo, STATE_KEY, state)

    def _card_of_request(self, req: ProviderRequest) -> CharacterCard | None:
        """Card bound to the persona of an outgoing LLM request."""
        if req.conversation is None:
            return None
        return self.store.find_card_by_persona(req.conversation.persona_id)

    async def _card_of_session(self, event: AstrMessageEvent) -> CharacterCard | None:
        """Card bound to the conversation currently active for this session."""
        umo = event.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not cid:
            return None
        conversation = await self.context.conversation_manager.get_conversation(
            umo, cid
        )
        if conversation is None:
            return None
        return self.store.find_card_by_persona(conversation.persona_id)

    # Run after every plugin that composes the prompt: companion-style plugins
    # register hooks from +230000 down to -260000, and hooks run in descending
    # priority order, so a very negative value keeps our lore at the end of the
    # final request instead of letting a later hook trim it away.
    @filter.on_llm_request(priority=-1_000_000)
    async def decorate_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """Add keyword-matched world book lore and the chosen opening scene."""
        card = self._card_of_request(req)
        state = await self._state(event.unified_msg_origin)

        if not req.contexts and state["greeting"] and card is not None:
            variant = card.get_variant()
            greeting = next(
                (
                    item
                    for item in (variant.greetings if variant else [])
                    if item.id == state["greeting"]
                ),
                None,
            )
            if greeting is not None:
                req.contexts = begin_dialog_history(greeting)

        if not self.config.get("enable", True):
            return
        if card is None and not self.config.get("apply_without_card", True):
            return
        books = await self.store.books_for_card(card)
        off = set(state["books_off"])
        books = [book for book in books if book.id not in off]
        if not books:
            return

        message = event.get_message_str() or ""
        if card is not None and self.config.get("include_card_name", True):
            message = f"{message}\n{card.name}"
        result = scan_books(
            books,
            message=message,
            contexts=req.contexts,
            last_fired=state["last_fired"],
            turn_index=state["turn"],
        )
        cap = int(self.config.get("global_token_cap", 4000) or 0)
        if cap > 0:
            kept = []
            dropped = list(result.over_budget)
            spent = 0
            for hit in sorted(
                result.hits, key=lambda item: (-item.entry.priority, item.entry.order)
            ):
                if spent + hit.tokens > cap:
                    dropped.append(hit)
                    continue
                spent += hit.tokens
                kept.append(hit)
            result.hits, result.over_budget = kept, dropped

        injection = build_injection(result)
        if not (
            injection.system_top or injection.system_tail or injection.history_inserts
        ):
            return

        req.system_prompt = compose_system_prompt(req.system_prompt, injection)
        req.contexts = apply_history(req.contexts, injection)
        state["turn"] += 1
        for hit in result.hits:
            state["last_fired"][hit.entry.id] = state["turn"]
        if len(state["last_fired"]) > 800:
            floor = state["turn"] - 64
            state["last_fired"] = {
                key: value
                for key, value in state["last_fired"].items()
                if value >= floor
            }
        state["trace"] = trace_of(injection)
        state["skipped"] = [
            {"entry": hit.entry.comment, "tokens": hit.tokens}
            for hit in result.over_budget
        ]
        await self._save_state(event.unified_msg_origin, state)
        if self.config.get("trace_in_log", False):
            names = "、".join(hit.entry.comment for hit in result.hits)
            logger.info(f"[rp] injected {len(result.hits)} entries: {names}")

    @filter.command("rp")
    async def cmd_status(self, event: AstrMessageEvent):
        """查看当前角色卡、世界书与注入状态"""
        card = await self._card_of_session(event)
        state = await self._state(event.unified_msg_origin)
        books = await self.store.books_for_card(card)
        lines = []
        if card is None:
            lines.append(
                "当前会话未绑定角色卡。用 /卡 名字 绑定，或在网页端「角色扮演」里管理。"
            )
        else:
            variant = card.get_variant()
            lines.append(
                f"角色卡：{card.name}（版本 {card.active_variant}，"
                f"{len(variant.blocks) if variant else 0} 个提示块，约 {card.tokens} tokens）"
            )
            if card.summary:
                lines.append(f"定位：{card.summary}")
        active = [book for book in books if book.id not in set(state["books_off"])]
        lines.append(
            f"世界书：{len(active)}/{len(books)} 本生效，"
            f"共 {sum(len(book.entries) for book in active)} 条条目"
        )
        skipped = (
            f"，因超出预算跳过 {len(state['skipped'])} 条" if state["skipped"] else ""
        )
        lines.append(f"上次注入：{len(state['trace'])} 条{skipped}")
        lines.append("指令：/卡 /变体 /块 /世书 /开场 /lore /导入")
        yield event.plain_result("\n".join(lines))

    @filter.command("卡")
    async def cmd_card(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """列出或切换角色卡：/卡 名字"""
        cards = self.store.list_cards()
        keyword = (argument or "").strip()
        if not cards:
            yield event.plain_result("还没有角色卡，先用 /导入 <目录> 导入语料。")
            return
        if not keyword:
            current = await self._card_of_session(event)
            lines = ["角色卡列表："]
            for index, card in enumerate(cards[:25], start=1):
                mark = "★" if current and current.id == card.id else "　"
                lines.append(
                    f"{mark} {index}. {card.name}"
                    f"（{len(card.variants)} 版本，{card.tokens} tokens，"
                    f"世界书 {len(card.world_book_ids)}）"
                )
            if len(cards) > 25:
                lines.append(f"… 另有 {len(cards) - 25} 张，可在网页端检索")
            lines.append("用 /卡 名字 绑定到当前会话。")
            yield event.plain_result("\n".join(lines))
            return
        matched = self.store.search_cards(keyword)
        if not matched:
            yield event.plain_result(f"没有找到角色卡「{keyword}」。")
            return
        if len(matched) > 1:
            names = "、".join(card.name for card in matched[:12])
            yield event.plain_result(
                f"「{keyword}」匹配到多张：{names}。请再说得具体些。"
            )
            return
        card = matched[0]
        persona_id = await sync_card_persona(
            self.context.persona_manager, self.store, card
        )
        await self.context.conversation_manager.update_conversation(
            event.unified_msg_origin, persona_id=persona_id
        )
        state = await self._state(event.unified_msg_origin)
        state["greeting"] = ""
        await self._save_state(event.unified_msg_origin, state)
        yield event.plain_result(
            f"已绑定角色卡：{card.name}（约 {card.tokens} tokens）。"
            "下一条消息生效；用 /重置 可清空当前上下文。"
        )

    @filter.command("变体")
    async def cmd_variant(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """切换角色卡的书写版本：/变体 lite"""
        card = await self._card_of_session(event)
        if card is None:
            yield event.plain_result("当前会话没有绑定角色卡，先用 /卡 名字 绑定。")
            return
        listing = "、".join(
            f"{key}（{variant.label}，约 {variant.tokens} tokens）"
            for key, variant in card.variants.items()
        )
        wanted = (argument or "").strip()
        if not wanted:
            yield event.plain_result(
                f"当前版本：{card.active_variant}。可用版本：{listing}"
            )
            return
        if wanted not in card.variants:
            yield event.plain_result(f"没有版本「{wanted}」。可用版本：{listing}")
            return
        card.active_variant = wanted
        await self.store.save_card(card)
        await sync_card_persona(self.context.persona_manager, self.store, card)
        yield event.plain_result(
            f"已切换版本为 {wanted}（约 {card.tokens} tokens），提示词已同步到人格。"
        )

    @filter.command("块")
    async def cmd_blocks(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """列出或开关提示块：/块 3"""
        card = await self._card_of_session(event)
        variant = card.get_variant() if card else None
        if variant is None:
            yield event.plain_result("当前会话没有绑定角色卡，先用 /卡 名字 绑定。")
            return
        wanted = (argument or "").strip()
        if not wanted:
            lines = [f"「{card.name} · {variant.label}」提示块："]
            for index, block in enumerate(variant.blocks, start=1):
                mark = "●" if block.enabled else "○"
                lines.append(f"{mark} {index}. {block.title}（{block.tokens} tokens）")
            lines.append("用 /块 序号 开关某一块，关闭后立即同步到人格。")
            yield event.plain_result("\n".join(lines))
            return
        if not wanted.isdigit() or not 1 <= int(wanted) <= len(variant.blocks):
            yield event.plain_result(f"序号应为 1-{len(variant.blocks)}。")
            return
        block = variant.blocks[int(wanted) - 1]
        block.enabled = not block.enabled
        await self.store.save_card(card)
        await sync_card_persona(self.context.persona_manager, self.store, card)
        action = "启用" if block.enabled else "关闭"
        yield event.plain_result(
            f"已{action}：{block.title}，角色卡现为约 {card.tokens} tokens。"
        )

    @filter.command("世书")
    async def cmd_books(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """列出或开关世界书：/世书 2"""
        card = await self._card_of_session(event)
        books = await self.store.books_for_card(card)
        state = await self._state(event.unified_msg_origin)
        wanted = (argument or "").strip()
        if wanted.isdigit():
            index = int(wanted)
            if not 1 <= index <= len(books):
                yield event.plain_result(f"序号应为 1-{len(books)}。")
                return
            book = books[index - 1]
            if book.id in state["books_off"]:
                state["books_off"].remove(book.id)
                action = "启用"
            else:
                state["books_off"].append(book.id)
                action = "暂停"
            await self._save_state(event.unified_msg_origin, state)
            yield event.plain_result(f"已{action}世界书：{book.name}")
            return
        if not books:
            yield event.plain_result(
                "当前没有可用的世界书。先在网页端导入语料，或把某本世界书设为「全局」。"
            )
            return
        off = set(state["books_off"])
        lines = ["当前会话的世界书："]
        for index, book in enumerate(books, start=1):
            mark = "●" if book.id not in off else "○"
            scope = "，全局" if book.global_scope else ""
            lines.append(
                f"{mark} {index}. {book.name}（{len(book.entries)} 条，"
                f"预算 {book.token_budget} tokens{scope}）"
            )
        lines.append("用 /世书 序号 在本会话开关。")
        yield event.plain_result("\n".join(lines))

    @filter.command("开场")
    async def cmd_greeting(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """选用或清除开场白：/开场 2"""
        card = await self._card_of_session(event)
        variant = card.get_variant() if card else None
        if variant is None or not variant.greetings:
            yield event.plain_result("当前角色卡没有可用的开场白。")
            return
        wanted = (argument or "").strip()
        state = await self._state(event.unified_msg_origin)
        if wanted in ("清", "clear", "0"):
            state["greeting"] = ""
            await self._save_state(event.unified_msg_origin, state)
            yield event.plain_result("已清除开场白。")
            return
        if not wanted:
            lines = [f"「{card.name}」开场白："]
            for index, greeting in enumerate(variant.greetings, start=1):
                lines.append(f"{index}. {greeting.title}")
            lines.append("用 /开场 序号 选用；清空历史后的第一条消息会带上它。")
            yield event.plain_result("\n".join(lines))
            return
        if not wanted.isdigit() or not 1 <= int(wanted) <= len(variant.greetings):
            yield event.plain_result(f"序号应为 1-{len(variant.greetings)}。")
            return
        chosen = variant.greetings[int(wanted) - 1]
        state["greeting"] = chosen.id
        await self._save_state(event.unified_msg_origin, state)
        yield event.plain_result(
            f"已选用开场白：{chosen.title}。用 /重置 开一段新对话即可看到。"
        )

    @filter.command("lore")
    async def cmd_lore(self, event: AstrMessageEvent):
        """查看上一次注入的世界书条目"""
        state = await self._state(event.unified_msg_origin)
        if not state["trace"]:
            yield event.plain_result("上一次请求没有注入任何世界书条目。")
            return
        lines = [f"上次注入 {len(state['trace'])} 条："]
        for item in state["trace"][:12]:
            keywords = "、".join(item["keywords"]) or "常驻"
            lines.append(
                f"· [{item['book']}] {item['entry']}（{item['tokens']} tokens，"
                f"{item['position']}，命中：{keywords}）"
            )
        if state["skipped"]:
            names = "、".join(
                f"{item['entry']}({item['tokens']})" for item in state["skipped"][:6]
            )
            lines.append(f"因预算跳过：{names}")
        yield event.plain_result("\n".join(lines))

    @filter.command("导入")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_import(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """导入语料目录（管理员）：/导入 E:\\Prompt"""
        path = (argument or "").strip() or str(
            self.config.get("default_corpus_path", "")
        ).strip()
        if not path:
            yield event.plain_result(
                "请给出语料目录，例如 /导入 E:\\SublimeTextzip\\Prompt，"
                "也可以在插件配置里填 default_corpus_path。"
            )
            return
        scan = scan_corpus(path)
        if not scan.cards and not scan.books:
            yield event.plain_result(
                "；".join([f"目录没有可导入的内容：{path}", *scan.report.warnings[:3]])
            )
            return
        report = await commit_import(self.store, scan)
        for card in scan.cards.values():
            await sync_card_persona(self.context.persona_manager, self.store, card)
        lines = [
            f"导入完成：{report.card_count} 个角色卡文件 → {len(scan.cards)} 张卡，"
            f"{report.book_count} 本世界书 / {report.entry_count} 条条目",
            f"已同步 {len(scan.cards)} 张卡的人格提示词。",
        ]
        if report.warnings:
            lines.append("提示：" + "；".join(report.warnings[:5]))
        lines.append("现在可以 /卡 名字 绑定角色。")
        yield event.plain_result("\n".join(lines))

    @filter.command("删卡")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_delete(self, event: AstrMessageEvent, argument: GreedyStr = ""):
        """删除角色卡与其人格投影（管理员）：/删卡 名字"""
        keyword = (argument or "").strip()
        matched = self.store.search_cards(keyword) if keyword else []
        if len(matched) != 1:
            yield event.plain_result("请给出准确的卡名：/删卡 名字")
            return
        card = matched[0]
        await unsync_card_persona(self.context.persona_manager, card)
        await self.store.delete_card(card.id)
        yield event.plain_result(f"已删除角色卡：{card.name}")
