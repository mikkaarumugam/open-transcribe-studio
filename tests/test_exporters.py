from app.models import Segment
from app.services.exporters import format_timestamp, to_srt, to_vtt


def test_format_timestamp_rounds_milliseconds():
    assert format_timestamp(65.4321) == "00:01:05,432"
    assert format_timestamp(3661.9999) == "01:01:02,000"


def test_to_srt_formats_numbered_blocks():
    segments = [Segment(id=0, start=0, end=1.5, text="Hello world")]
    expected = "1\n00:00:00,000 --> 00:00:01,500\nHello world\n"
    assert to_srt(segments) == expected


def test_to_vtt_starts_with_header():
    segments = [Segment(id=0, start=0, end=1, text="Hello")]
    assert to_vtt(segments).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.000")
