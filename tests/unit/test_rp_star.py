"""Integration tests for the rp_engine builtin star.

The star runs against a mocked Context and a stubbed session store, so the
persona -> card -> world book injection path is verified without starting
AstrBot or reaching any platform.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrbot.core.provider.entities import Conversation, ProviderRequest
from astrbot.core.rp import (
    BookEntry,
    CardVariant,
    CharacterCard,
    Greeting,
    PromptBlock,
    WorldBook,
    get_rp_store,
)

UMO = "aiocqhttp:GroupMessage:12345"
PERSONA = "# Persona Instructions\n\n你是白瀬。\n"


def build_fixtures() -> tuple[WorldBook, CharacterCard]:
    """Create a card and a world book for the tests.

    Returns:
        The book and the card, already linked.
    """
    book = WorldBook(name="灯港市", token_budget=3000)
    book.entries = [
        BookEntry(
            comment="常驻红线", content="不得写露骨描写。", constant=True, priority=40
        ),
        BookEntry(
            comment="面包店",
            keywords=["面包"],
            content="白瀬在灯港商店街开面包店。",
            priority=20,
        ),
    ]
    card = CharacterCard(
        name="白瀬",
        persona_id="rp_card_test",
        world_book_ids=[book.id],
        active_variant="lite",
        variants={
            "lite": CardVariant(
                label="精简",
                blocks=[PromptBlock(title="身份", content="你是白瀬。", order=10)],
            )
        },
    )
    return book, card


@pytest.fixture
def store(tmp_path: Path):
    """An RP store pointed at a temporary directory."""
    rp_store = get_rp_store()
    rp_store.root = tmp_path
    rp_store.card_dir = tmp_path / "cards"
    rp_store.book_dir = tmp_path / "worldbooks"
    rp_store._cards = {}
    rp_store._books = {}
    rp_store._loaded = False
    book, card = build_fixtures()

    async def seed() -> None:
        await rp_store.save_book(book)
        await rp_store.save_card(card)

    asyncio.run(seed())
    rp_store._loaded = True
    return rp_store


@pytest.fixture
def star(monkeypatch, store):
    """The builtin star with a stubbed session store."""
    import astrbot.builtin_stars.rp_engine.main as star_module

    sessions: dict[str, dict] = {}

    async def session_get(umo: str, key: str, default=None):
        return sessions.get(f"{umo}:{key}", default)

    async def session_put(umo: str, key: str, value) -> None:
        sessions[f"{umo}:{key}"] = value

    monkeypatch.setattr(star_module.sp, "session_get", session_get)
    monkeypatch.setattr(star_module.sp, "session_put", session_put)
    instance = star_module.RPRoleplay(
        MagicMock(), {"enable": True, "include_card_name": True}
    )
    instance.sessions = sessions
    instance.store = store
    return instance


def make_event(message: str) -> MagicMock:
    """A minimal message event stub."""
    event = MagicMock()
    event.unified_msg_origin = UMO
    event.get_message_str.return_value = message
    return event


def make_request(persona_id: str | None) -> ProviderRequest:
    """A provider request bound to a persona."""
    request = ProviderRequest(prompt="想吃贝果", contexts=[])
    request.system_prompt = PERSONA
    request.conversation = Conversation(
        platform_id="aiocqhttp",
        user_id="1",
        cid="c1",
        history="[]",
        persona_id=persona_id,
    )
    return request


@pytest.mark.asyncio
async def test_injects_constant_and_keyword_lore(star, store) -> None:
    """A bound persona pulls its card's constant and matched entries."""
    request = make_request("rp_card_test")
    await star.decorate_request(make_event("她店里的面包刚出炉"), request)

    assert "不得写露骨描写" in request.system_prompt
    assert "灯港商店街" in request.system_prompt
    assert request.system_prompt.index(
        "Persona Instructions"
    ) < request.system_prompt.index("# 世界书")
    trace = star.sessions[f"{UMO}:rp_engine"]["trace"]
    assert {item["entry"] for item in trace} == {"常驻红线", "面包店"}
    assert star.sessions[f"{UMO}:rp_engine"]["turn"] == 1


@pytest.mark.asyncio
async def test_cooldown_suppresses_a_recent_entry(star, store) -> None:
    """An entry with a cooldown stays quiet for the configured turns."""
    book = store.list_books()[0]
    book.entries[1].cooldown_turns = 2

    first = make_request("rp_card_test")
    await star.decorate_request(make_event("面包"), first)
    assert "面包店" in {
        item["entry"] for item in star.sessions[f"{UMO}:rp_engine"]["trace"]
    }

    second = make_request("rp_card_test")
    await star.decorate_request(make_event("面包"), second)
    assert "灯港商店街开面包店" not in second.system_prompt
    assert "不得写露骨描写" in second.system_prompt


@pytest.mark.asyncio
async def test_muted_book_and_disabled_engine(star, store) -> None:
    """A session-muted book and a disabled engine both stop injecting."""
    book_id = store.list_cards()[0].world_book_ids[0]
    star.sessions[f"{UMO}:rp_engine"] = {"books_off": [book_id]}

    request = make_request("rp_card_test")
    await star.decorate_request(make_event("面包"), request)
    assert "灯港商店街" not in request.system_prompt

    star.config["enable"] = False
    request2 = make_request("rp_card_test")
    await star.decorate_request(make_event("面包"), request2)
    assert request2.system_prompt == PERSONA


@pytest.mark.asyncio
async def test_global_book_applies_without_a_card(star, store) -> None:
    """Global books fire even when the conversation has no card."""
    book = store.list_books()[0]
    book.global_scope = True
    await store.save_book(book)

    request = make_request(None)
    await star.decorate_request(make_event("她的面包"), request)
    assert "灯港商店街" in request.system_prompt


@pytest.mark.asyncio
async def test_greeting_seeds_an_empty_conversation(star, store) -> None:
    """A selected opening scene becomes a transient assistant message."""
    card = store.list_cards()[0]
    variant = card.get_variant()
    variant.greetings = [
        Greeting(id="g1", title="相遇", content="（卷帘门拉下一半。）")
    ]
    await store.save_card(card)
    star.sessions[f"{UMO}:rp_engine"] = {"greeting": "g1"}

    request = make_request("rp_card_test")
    request.contexts = []
    await star.decorate_request(make_event("你好"), request)
    assert request.contexts[0]["role"] == "assistant"
    assert request.contexts[0]["_no_save"] is True
    assert "卷帘门" in request.contexts[0]["content"]


def test_world_book_hook_runs_last() -> None:
    """The lore hook must be ordered after companion-style plugin hooks."""
    import astrbot.builtin_stars.rp_engine.main as star_module
    from astrbot.core.star.star_handler import EventType, star_handlers_registry

    ours = [
        handler
        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.OnLLMRequestEvent, only_activated=False
        )
        if handler.handler_module_path == star_module.__name__
        and handler.handler_name == "decorate_request"
    ]
    assert len(ours) == 1
    # 我会永远陪着你 registers down to -260000; ours must stay behind all of them.
    assert ours[0].extras_configs["priority"] == -1_000_000
