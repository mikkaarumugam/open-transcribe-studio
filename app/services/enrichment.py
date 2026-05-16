from __future__ import annotations

import re
from collections import Counter

from app.models import Chapter, Segment

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was", "were",
    "from", "have", "has", "had", "but", "not", "can", "will", "would", "there", "their",
    "about", "into", "they", "them", "our", "out", "what", "when", "then", "than", "also",
    "just", "like", "yeah", "okay", "right", "really", "because", "been", "being", "it's",
}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")


def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    return PHONE_RE.sub("[PHONE_REDACTED]", text)


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    words = [w.lower().strip("'-") for w in WORD_RE.findall(text)]
    useful = [w for w in words if w not in STOPWORDS and len(w) > 2]
    counts = Counter(useful)
    return [word for word, _ in counts.most_common(limit)]


def summarize_text(text: str, max_sentences: int = 4) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    sentences = [s.strip() for s in SENTENCE_RE.split(clean) if s.strip()]
    if len(sentences) <= max_sentences:
        return clean
    keywords = set(extract_keywords(clean, limit=20))
    scored: list[tuple[int, int, str]] = []
    for idx, sentence in enumerate(sentences):
        score = sum(1 for word in WORD_RE.findall(sentence.lower()) if word in keywords)
        scored.append((score, -idx, sentence))
    selected = sorted(scored, reverse=True)[:max_sentences]
    ordered = [sentence for _, neg_idx, sentence in sorted(selected, key=lambda item: -item[1])]
    return " ".join(ordered)


def make_chapters(segments: list[Segment], target_chapters: int = 4) -> list[Chapter]:
    if not segments:
        return []
    chunk_size = max(1, round(len(segments) / target_chapters))
    chapters: list[Chapter] = []
    for i in range(0, len(segments), chunk_size):
        chunk = segments[i : i + chunk_size]
        text = " ".join(segment.text.strip() for segment in chunk).strip()
        keywords = extract_keywords(text, limit=3)
        title = " / ".join(keywords).title() if keywords else f"Chapter {len(chapters) + 1}"
        chapters.append(
            Chapter(
                title=title,
                start=chunk[0].start,
                end=chunk[-1].end,
                summary=summarize_text(text, max_sentences=2),
            )
        )
    return chapters
