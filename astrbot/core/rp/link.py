"""Bridge between character cards and AstrBot personas.

A card owns its text; an AstrBot persona is a *projection* of that text, so the
whole existing persona machinery keeps working: the dashboard lists cards as
personas, conversations bind to them, and every platform picks them up. The
projection is refreshed whenever the card changes.
"""

from __future__ import annotations

from .models import CharacterCard
from .store import RPStore


def persona_id_for(card: CharacterCard) -> str:
    """Deterministic persona id of a card.

    Args:
        card: Character card.

    Returns:
        Existing binding, or the id a new binding would use.
    """
    return card.persona_id or f"rp_{card.id}"


async def sync_card_persona(persona_mgr, store: RPStore, card: CharacterCard) -> str:
    """Create or refresh the persona that carries a card's prompt.

    Args:
        persona_mgr: An initialised ``PersonaManager``.
        store: RP store owning the card.
        card: Card to project.

    Returns:
        The persona id bound to the card.
    """
    pid = persona_id_for(card)
    prompt = card.prompt_text()
    try:
        existing = await persona_mgr.get_persona(pid)
    except ValueError:
        existing = None
    if existing is None:
        await persona_mgr.create_persona(
            persona_id=pid,
            system_prompt=prompt,
            begin_dialogs=[],
        )
    else:
        await persona_mgr.update_persona(pid, system_prompt=prompt)
    card.persona_id = pid
    await store.save_card(card)
    return pid


async def unsync_card_persona(persona_mgr, card: CharacterCard) -> None:
    """Delete the persona projection of a card.

    Args:
        persona_mgr: An initialised ``PersonaManager``.
        card: Card whose persona should go away; a missing persona is ignored.
    """
    if not card.persona_id:
        return
    try:
        await persona_mgr.delete_persona(card.persona_id)
    except ValueError:
        pass
