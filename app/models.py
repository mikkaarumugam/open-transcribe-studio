from __future__ import annotations

from pydantic import BaseModel, Field


class Segment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class Chapter(BaseModel):
    title: str
    start: float
    end: float
    summary: str


class TranscriptResult(BaseModel):
    job_id: str
    filename: str
    language: str | None = None
    duration: float | None = None
    text: str
    redacted_text: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
