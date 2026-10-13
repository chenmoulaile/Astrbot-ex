"""Heuristic token estimation for mixed CJK and latin prompt text.

CJK characters cost roughly one token each, latin runs cost roughly one token
per four characters. This avoids pulling in a tokenizer model (which needs a
network download at first use) while staying close enough to real budgets for
prompt assembly decisions.
"""

from __future__ import annotations

_CJK_RANGES = (
    (0x2E80, 0x303F),  # radicals, punctuation, kana
    (0x3040, 0x30FF),  # hiragana, katakana
    (0x3100, 0x312F),  # bopomofo
    (0x3400, 0x4DBF),  # ideographs ext a
    (0x4E00, 0x9FFF),  # ideographs
    (0xAC00, 0xD7AF),  # hangul syllables
    (0xF900, 0xFAFF),  # ideographs compatibility
    (0x20000, 0x2FA1F),  # ideographs ext b and beyond
)

_LATIN_BREAKS = " \t\r\n　"


def _is_cjk(char: str) -> bool:
    """Check whether a character belongs to a CJK width block.

    Args:
        char: Single character.

    Returns:
        True when the character is counted as one token by itself.
    """
    code = ord(char)
    for low, high in _CJK_RANGES:
        if low <= code <= high:
            return True
    return False


def estimate_tokens(text: str) -> int:
    """Estimate the token count of a prompt fragment.

    Args:
        text: Prompt text, any mix of CJK and latin.

    Returns:
        Estimated token count, never negative.
    """
    if not text:
        return 0
    total = 0
    run = 0
    for char in text:
        if _is_cjk(char) or char in _LATIN_BREAKS:
            total += (run + 3) // 4
            run = 0
            if _is_cjk(char):
                total += 1
        else:
            run += 1
    total += (run + 3) // 4
    return total
