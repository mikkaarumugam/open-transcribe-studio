from app.models import Segment
from app.services.transcription import build_result


def test_build_result_adds_enrichment_fields():
    result = build_result(
        filename="demo.wav",
        language="en",
        duration=12.0,
        text="Contact me at user@example.com. This product transcribes audio for portfolio demos.",
        segments=[Segment(id=0, start=0, end=12, text="Contact me at user@example.com. This product transcribes audio for portfolio demos.")],
    )
    assert result.filename == "demo.wav"
    assert result.language == "en"
    assert "[EMAIL_REDACTED]" in result.redacted_text
    assert "product" in result.keywords
    assert result.chapters
