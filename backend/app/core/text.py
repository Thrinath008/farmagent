"""Input sanitization for free text stored or forwarded to the model."""

import unicodedata


def clean_text(value: str) -> str:
    """Strip control characters (keeping newlines and tabs) and surrounding whitespace."""
    kept = (ch for ch in value if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    return "".join(kept).strip()
