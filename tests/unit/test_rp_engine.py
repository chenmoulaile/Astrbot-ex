"""Unit tests for the roleplay engine: tokens, store, matcher, builder, importer."""

from pathlib import Path

import pytest

from astrbot.core.rp.builder import (
    apply_history,
    begin_dialog_history,
    build_injection,
    compose_system_prompt,
    trace_of,
)
from astrbot.core.rp.importer import (
    clean_title,
    commit_import,
    extract_keywords,
    scan_corpus,
    variant_key_of,
)
from astrbot.core.rp.matcher import build_scan_texts, scan_books
from astrbot.core.rp.models import (
    BookEntry,
    CardVariant,
    CharacterCard,
    EntryPosition,
    Greeting,
    PromptBlock,
    SelectiveLogic,
    WorldBook,
    validate_safe_id,
)
from astrbot.core.rp.store import RPStore
from astrbot.core.rp.tokens import estimate_tokens

RULE = "═" * 40


def make_book(**kwargs) -> WorldBook:
    """Build a world book with one default entry list."""
    book = WorldBook(name="测试世界书", token_budget=kwargs.pop("token_budget", 3000))
    for key, value in kwargs.items():
        setattr(book, key, value)
    return book


def test_estimate_tokens_counts_cjk_and_latin() -> None:
    """CJK costs one token per character, latin about one per four."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("hello world") == 4
    assert estimate_tokens("你好 hello") == 4


def test_validate_safe_id_rejects_traversal() -> None:
    """Identifiers used as file names cannot escape the storage directory."""
    assert validate_safe_id("card_abc123") == "card_abc123"
    for bad in ("../x", "a/b", "", "..hidden", "x" * 70):
        with pytest.raises(ValueError):
            validate_safe_id(bad)


def test_matcher_keyword_variants() -> None:
    """Substring, case, whole word and regex matching all behave."""
    book = make_book()
    book.entries = [
        BookEntry(comment="子串", keywords=["面包店"], content="A" * 40),
        BookEntry(
            comment="敏感大小写",
            keywords=["Hina"],
            content="B" * 40,
            case_sensitive=True,
        ),
        BookEntry(comment="整词", keywords=["cat"], content="C" * 40, whole_word=True),
        BookEntry(
            comment="正则", keywords=["风纪.*委员"], content="D" * 40, regex=True
        ),
        BookEntry(comment="非法正则", keywords=["(["], content="E" * 40, regex=True),
    ]
    fired = {
        hit.entry.comment
        for hit in scan_books([book], message="面包店 the cat sat 风纪委员长").hits
    }
    assert fired == {"子串", "整词", "正则"}
    fired = {hit.entry.comment for hit in scan_books([book], message="hina 风纪").hits}
    assert fired == set()


def test_matcher_selective_logic_and_constant() -> None:
    """Secondary keywords gate an entry; constant entries always fire."""
    book = make_book()
    book.entries = [
        BookEntry(
            comment="常驻",
            keywords=[],
            content="X" * 40,
            constant=True,
            priority=40,
        ),
        BookEntry(
            comment="需要夜晚",
            keywords=["阳奈"],
            secondary_keywords=["夜晚", "天台"],
            selective_logic=SelectiveLogic.AND_ANY,
            content="Y" * 40,
        ),
        BookEntry(
            comment="排除工作",
            keywords=["阳奈"],
            secondary_keywords=["任务", "风纪"],
            selective_logic=SelectiveLogic.NOT_ANY,
            content="Z" * 40,
        ),
    ]
    assert len(scan_books([book], message="随便聊聊").hits) == 1
    fired = {
        h.entry.comment for h in scan_books([book], message="阳奈在夜晚的天台").hits
    }
    assert fired == {"常驻", "需要夜晚", "排除工作"}
    fired = {
        h.entry.comment for h in scan_books([book], message="阳奈在处理风纪任务").hits
    }
    assert fired == {"常驻"}


def test_matcher_budget_and_cooldown() -> None:
    """Low priority hits are trimmed first; cooldowns suppress recent entries."""
    book = make_book(token_budget=100, recursion_limit=0)
    book.entries = [
        BookEntry(comment="高", keywords=["猫"], content="描" * 80, priority=30),
        BookEntry(comment="低", keywords=["猫"], content="写" * 80, priority=5),
    ]
    result = scan_books([book], message="猫")
    assert [h.entry.comment for h in result.hits] == ["高"]
    assert [h.entry.comment for h in result.over_budget] == ["低"]

    cooled = make_book()
    cooled.entries = [
        BookEntry(comment="冷却", keywords=["猫"], content="K" * 20, cooldown_turns=2)
    ]
    entry = cooled.entries[0]
    assert len(scan_books([cooled], message="猫", turn_index=3).hits) == 1
    assert not scan_books(
        [cooled], message="猫", last_fired={entry.id: 1}, turn_index=2
    ).hits
    assert (
        len(
            scan_books(
                [cooled], message="猫", last_fired={entry.id: 0}, turn_index=3
            ).hits
        )
        == 1
    )


def test_matcher_recursion_pulls_chained_entries() -> None:
    """An entry mentioned only by another entry's text can fire once."""
    book = make_book(recursion_limit=1)
    book.entries = [
        BookEntry(comment="触发", keywords=["光环"], content="提到 禁忌清单", order=1),
        BookEntry(comment="连锁", keywords=["禁忌清单"], content="不得写血腥", order=2),
    ]
    first = scan_books([book], message="她头顶的光环很亮", turn_index=0)
    assert {h.entry.comment for h in first.hits} == {"触发", "连锁"}
    assert {h.entry.comment for h in first.hits if h.recursed} == {"连锁"}


def test_build_scan_texts_uses_history_depth() -> None:
    """Only the requested number of recent, visible turns is scanned."""
    contexts = [
        {"role": "user", "content": "第一句 面包"},
        {"role": "assistant", "content": "第二句 贝果"},
        {"role": "user", "content": "第三句 猫"},
        {"role": "system", "content": "系统 不该被扫描"},
        {"role": "user", "content": "隐藏", "_no_save": True},
    ]
    texts = build_scan_texts("当前消息", contexts, 2)
    assert texts == ["当前消息", "第二句 贝果", "第三句 猫"]


def test_builder_positions_and_history_injection() -> None:
    """Positions place lore above, below or inside the history."""
    book = make_book()
    book.entries = [
        BookEntry(
            comment="红线",
            content="不得写露骨",
            constant=True,
            position=EntryPosition.SYSTEM_TOP,
            priority=40,
        ),
        BookEntry(
            comment="场景",
            keywords=["天台"],
            content="傍晚的天台",
            position=EntryPosition.SYSTEM_TAIL,
        ),
        BookEntry(
            comment="深挂",
            keywords=["猫"],
            content="店里的猫叫小麦",
            position=EntryPosition.HISTORY_DEPTH,
            depth=1,
        ),
    ]
    result = scan_books([book], message="天台上有猫")
    injection = build_injection(result)
    final = compose_system_prompt("# Persona Instructions\n她是阳奈", injection)
    assert final.index("红线") < final.index("Persona") < final.index("场景")
    history = apply_history(
        [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"}],
        injection,
    )
    assert history[0]["content"] == "u1"
    assert history[1]["_no_save"] is True and "小麦" in history[1]["content"]
    assert history[2]["content"] == "a1"
    trace = trace_of(injection)
    assert {item["entry"] for item in trace} == {"红线", "场景", "深挂"}
    assert {item["position"] for item in trace} == {
        "system_top",
        "system_tail",
        "history_depth",
    }
    dialogs = begin_dialog_history(Greeting(title="A", content="（卷帘门响了。）"))
    assert dialogs[0]["role"] == "assistant" and dialogs[0]["_no_save"] is True


def test_builder_trace_reports_every_hit() -> None:
    """Grouped blocks still report one trace record per entry."""
    book = make_book()
    book.entries = [
        BookEntry(comment="第一条", keywords=["天台"], content="A" * 30, order=1),
        BookEntry(comment="第二条", keywords=["天台"], content="B" * 30, order=2),
        BookEntry(comment="第三条", keywords=["天台"], content="C" * 30, order=3),
    ]
    result = scan_books([book], message="傍晚的天台")
    trace = trace_of(build_injection(result))
    assert [item["entry"] for item in trace] == ["第一条", "第二条", "第三条"]
    assert sum(item["tokens"] for item in trace) == sum(
        hit.tokens for hit in result.hits
    )


def test_character_card_variant_and_prompt_order() -> None:
    """Variant lookup falls back sensibly and disabled blocks drop out."""
    card = CharacterCard(name="阳奈", active_variant="lite")
    card.variants = {
        "lite": CardVariant(
            label="精简",
            blocks=[
                PromptBlock(title="二、身份", content="B", order=20),
                PromptBlock(title="一、信条", content="A", order=10),
                PromptBlock(title="三、禁用", content="C", order=30, enabled=False),
            ],
        )
    }
    assert card.get_variant("missing").label == "精简"
    assert card.prompt_text() == "A\n\nB"
    assert card.tokens == 2


def _write_corpus(root: Path) -> None:
    """Create a miniature corpus following the authoring layout."""
    characters = root / "角色"
    characters.mkdir(parents=True)
    full = "\n".join(
        [
            "# 角色扮演协议 · 白瀬（完美版）",
            "你现在完全扮演 **白瀬**。",
            RULE,
            "§1 最高信条",
            RULE,
            "- 先照顾身体，再处理情绪。",
            RULE,
            "§2 开场白（任选）",
            RULE,
            "**A · 相遇**",
            "> （卷帘门拉下一半。）",
            "> 欢迎回来。",
            "**B · 收摊**",
            "> 今天来得早。",
        ]
    )
    lite = "\n".join(
        [
            "# 角色扮演协议 · 白瀬（精简版）",
            RULE,
            "一、最高信条",
            RULE,
            "- 先照顾身体。",
            RULE,
            "二、开场白",
            RULE,
            "**A · 相遇**",
            "> 欢迎回来。",
        ]
    )
    (characters / "白瀬_角色扮演SystemPrompt_无删减完美版.md").write_text(
        full, encoding="utf-8"
    )
    (characters / "白瀬_角色扮演SystemPrompt_精简高质量版.md").write_text(
        lite, encoding="utf-8"
    )
    # A stray rule inside a body must not desynchronise the remaining sections.
    stray = full.replace(
        "- 先照顾身体，再处理情绪。", "- 先照顾身体。\n" + RULE + "\n- 再处理情绪。"
    )
    (characters / "白瀬_角色扮演SystemPrompt_无删减完美版.md").write_text(
        stray, encoding="utf-8"
    )
    book = "\n".join(
        [
            "# 灯港市 · 世界书",
            "> 译名口径：日文 / 简中。",
            "## 第一章 地点",
            "- **灯港商店街（とうこう商店街）**：白瀬面包店在此。",
            "- **河堤**：傍晚跑步路线。",
            "## 第二章 扮演自检清单",
            "不得写露骨描写。",
            "对照表：" + "、".join(f"条目{i}" for i in range(300)),
        ]
    )
    (root / "灯港_世界书.md").write_text(book, encoding="utf-8")


@pytest.mark.asyncio
async def test_scan_and_commit_corpus(tmp_path: Path) -> None:
    """A corpus scan yields structured cards and books, and re-imports merge."""
    _write_corpus(tmp_path)
    scan = scan_corpus(tmp_path)
    assert len(scan.cards) == 1
    card = next(iter(scan.cards.values()))
    assert card.name == "白瀬"
    assert card.active_variant == "lite"
    assert set(card.variants) == {"full", "lite"}
    titles = [block.title for block in card.variants["full"].blocks]
    assert "最高信条" in titles
    assert len(card.variants["full"].greetings) == 2
    assert card.variants["full"].greetings[0].content.startswith("（卷帘门")
    assert card.world_book_ids and len(card.world_book_ids) == 1

    book = next(iter(scan.books.values()))
    shop = next(
        entry for entry in book.entries if entry.comment.startswith("灯港商店街")
    )
    assert "灯港商店街" in shop.keywords
    assert "とうこう商店街" in shop.keywords
    constant = [entry for entry in book.entries if entry.constant]
    assert {entry.comment for entry in constant} == {
        "使用约定与译名口径",
        "扮演自检清单",
    }

    store = RPStore(root=tmp_path / "data")
    await store.initialize()
    await commit_import(store, scan)
    assert len(store.list_cards()) == 1
    assert len(store.list_books()) == 1
    assert store.get_card(card.id).persona_id is None

    # User edits survive a re-import: a block toggle and a persona binding.
    stored = store.get_card(card.id)
    stored.persona_id = "persona_1"
    for block in stored.variants["full"].blocks:
        if block.title == "最高信条":
            block.enabled = False
    await store.save_card(stored)
    await commit_import(store, scan_corpus(tmp_path))
    reopened = RPStore(root=tmp_path / "data")
    await reopened.initialize()
    again = reopened.get_card(card.id)
    assert again.persona_id == "persona_1"
    assert [
        b.enabled for b in again.variants["full"].blocks if b.title == "最高信条"
    ] == [False]
    assert len(reopened.list_books()) == 1


@pytest.mark.asyncio
async def test_store_roundtrip_and_cascade(tmp_path: Path) -> None:
    """Books are removable with their card references, and entries upsert."""
    store = RPStore(root=tmp_path / "data")
    await store.initialize()
    book = make_book()
    await store.save_book(book)
    card = CharacterCard(name="阳奈", world_book_ids=[book.id])
    await store.save_card(card)
    assert store.find_card_by_persona(None) is None
    entry = BookEntry(comment="新增", keywords=["猫"], content="猫")
    await store.upsert_entry(book.id, entry)
    assert store.get_book(book.id).entries[0].id == entry.id
    entry.content = "猫叫小麦"
    await store.upsert_entry(book.id, entry)
    assert store.get_book(book.id).entries[0].content == "猫叫小麦"
    assert await store.delete_entry(book.id, entry.id) is True
    assert await store.delete_entry(book.id, entry.id) is False

    await store.delete_book(book.id)
    assert store.get_book(book.id) is None
    assert store.get_card(card.id).world_book_ids == []

    second = make_book()
    second.global_scope = True
    await store.save_book(second)
    await store.save_card(
        CharacterCard(id="card_x", name="星", world_book_ids=[second.id])
    )
    bound = await store.books_for_card(store.get_card("card_x"))
    assert [b.id for b in bound] == [second.id]
    assert [b.id for b in await store.books_for_card(None)] == [second.id]


def test_keyword_extraction_from_headings() -> None:
    """Parenthetical aliases and group codes are handled."""
    keywords = extract_keywords(
        "格赫娜学园（ゲヘナ / Gehenna，简中：歌赫娜学院；通称格黑娜）★日奈所属"
    )
    assert keywords[0] == "格赫娜学园"
    assert {"ゲヘナ", "Gehenna", "歌赫娜学院", "格黑娜"} <= set(keywords)
    assert "简中" not in " ".join(keywords)
    assert extract_keywords("A1 白瀬みなも（しらせ みなも）")[:2] == [
        "A1 白瀬みなも",
        "白瀬みなも",
    ]
    assert (
        clean_title("第六章之二 · 小鸟游星野（たかなしホシノ）")
        == "小鸟游星野（たかなしホシノ）"
    )
    assert clean_title("第四章 空崎阳奈条目（★官方档案）") == "空崎阳奈条目"
    assert variant_key_of("白瀬_角色扮演SystemPrompt_无删减完美版") == "full"
    assert variant_key_of("白瀬_角色扮演SystemPrompt_精简高质量版") == "lite"
    assert variant_key_of("白瀬_角色扮演SystemPrompt") == "base"
