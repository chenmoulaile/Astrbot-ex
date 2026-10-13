"""Roleplay engine: character cards, world books and prompt assembly.

The package is deliberately independent of AstrBot's pipeline. It produces data
that a star or a dashboard service applies to a request, which keeps the engine
testable on its own and cheap to keep in sync with upstream.
"""

from .builder import (
    Injection,
    Placement,
    apply_history,
    begin_dialog_history,
    build_injection,
    compose_system_prompt,
    trace_of,
)
from .importer import (
    CorpusScan,
    ImportItem,
    ImportReport,
    commit_import,
    scan_corpus,
)
from .matcher import (
    MatchHit,
    ScanResult,
    build_scan_texts,
    keyword_hit,
    scan_books,
    secondary_gate,
)
from .models import (
    BookEntry,
    CardVariant,
    CharacterCard,
    EntryPosition,
    Greeting,
    PromptBlock,
    SelectiveLogic,
    WorldBook,
)
from .store import RPStore, get_rp_store
from .tokens import estimate_tokens

__all__ = [
    "BookEntry",
    "CardVariant",
    "CharacterCard",
    "CorpusScan",
    "EntryPosition",
    "Greeting",
    "ImportItem",
    "ImportReport",
    "Injection",
    "MatchHit",
    "keyword_hit",
    "secondary_gate",
    "Placement",
    "PromptBlock",
    "RPStore",
    "ScanResult",
    "SelectiveLogic",
    "WorldBook",
    "apply_history",
    "begin_dialog_history",
    "build_injection",
    "build_scan_texts",
    "commit_import",
    "compose_system_prompt",
    "estimate_tokens",
    "get_rp_store",
    "scan_books",
    "scan_corpus",
    "trace_of",
]
