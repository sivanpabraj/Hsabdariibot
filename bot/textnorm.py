"""Normalize Telegram/Persian button text for reliable matching."""

from __future__ import annotations

import re
import unicodedata

# Zero-width / directional / variation selectors Telegram may inject
_STRIP_CHARS = dict.fromkeys(
    map(
        ord,
        (
            "\u200c"  # ZWNJ
            "\u200d"  # ZWJ
            "\u200e"  # LTR mark
            "\u200f"  # RTL mark
            "\ufeff"  # BOM / ZWNBSP
            "\ufe0e"  # text variation selector
            "\ufe0f"  # emoji variation selector
        ),
    ),
    None,
)

# Arabic letter forms → Persian equivalents users/clients sometimes send
_ARABIC_TO_PERSIAN = str.maketrans(
    {
        "ك": "ک",  # Arabic kaf → Persian kaf
        "ي": "ی",  # Arabic yeh → Persian yeh
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "ئ": "ی",
    }
)

_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    """Normalize user/button text so Persian reply-keyboard labels match reliably."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_STRIP_CHARS)
    text = text.translate(_ARABIC_TO_PERSIAN)
    text = _SPACE_RE.sub(" ", text).strip()
    return text
