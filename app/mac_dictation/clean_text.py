from __future__ import annotations

import re

FILLER_RE = re.compile(r"\b(?:um|uh|erm|ah|like|you know)\b[,. ]*", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")


def clean_dictation_text(text: str) -> str:
    """Small free cleanup pass for dictated text.

    This avoids paid LLM cleanup in the MVP while still making pasted text
    feel more ready-to-send than raw Whisper output.
    """
    cleaned = FILLER_RE.sub("", text or "")
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned
