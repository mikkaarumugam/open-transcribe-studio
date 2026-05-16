from __future__ import annotations

from pathlib import Path

from app.models import Segment, TranscriptResult


def format_timestamp(seconds: float, sep: str = ",") -> str:
    seconds = max(0.0, float(seconds))
    millis = int(round((seconds - int(seconds)) * 1000))
    total_seconds = int(seconds)
    if millis == 1000:
        total_seconds += 1
        millis = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def to_srt(segments: list[Segment]) -> str:
    blocks = []
    for idx, segment in enumerate(segments, start=1):
        blocks.append(
            f"{idx}\n"
            f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n"
            f"{segment.text.strip()}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: list[Segment]) -> str:
    body = []
    for segment in segments:
        body.append(
            f"{format_timestamp(segment.start, sep='.')} --> {format_timestamp(segment.end, sep='.')}\n"
            f"{segment.text.strip()}"
        )
    return "WEBVTT\n\n" + "\n\n".join(body) + ("\n" if body else "")


def write_exports(result: TranscriptResult, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / result.job_id
    paths = {
        "txt": base.with_suffix(".txt"),
        "json": base.with_suffix(".json"),
        "srt": base.with_suffix(".srt"),
        "vtt": base.with_suffix(".vtt"),
    }
    paths["txt"].write_text(result.text, encoding="utf-8")
    paths["json"].write_text(result.model_dump_json(indent=2), encoding="utf-8")
    paths["srt"].write_text(to_srt(result.segments), encoding="utf-8")
    paths["vtt"].write_text(to_vtt(result.segments), encoding="utf-8")
    return {kind: str(path) for kind, path in paths.items()}
