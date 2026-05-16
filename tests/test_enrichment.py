from app.models import Segment
from app.services.enrichment import extract_keywords, make_chapters, redact_pii, summarize_text


def test_redact_pii_masks_email_and_phone():
    text = "Email me at mikka@example.com or call +44 7700 900123 tomorrow."
    redacted = redact_pii(text)
    assert "mikka@example.com" not in redacted
    assert "+44 7700 900123" not in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert "[PHONE_REDACTED]" in redacted


def test_extract_keywords_prefers_repeated_meaningful_words():
    text = "Transcription transcription audio product product product meeting notes."
    assert extract_keywords(text, limit=2) == ["product", "transcription"]


def test_summarize_text_keeps_short_text_unchanged():
    text = "This is one sentence. This is another sentence."
    assert summarize_text(text) == text


def test_make_chapters_groups_segments():
    segments = [
        Segment(id=0, start=0, end=10, text="Product discovery interview about audio workflows."),
        Segment(id=1, start=10, end=20, text="Users need accurate transcripts and exports."),
        Segment(id=2, start=20, end=30, text="Portfolio demo should show product thinking."),
        Segment(id=3, start=30, end=40, text="Next steps include diarization and live streaming."),
    ]
    chapters = make_chapters(segments, target_chapters=2)
    assert len(chapters) == 2
    assert chapters[0].start == 0
    assert chapters[-1].end == 40
