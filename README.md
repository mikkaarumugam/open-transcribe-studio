# Open Transcribe Studio

A free, local-first transcription studio inspired by Glaido: upload audio/video or record from your mic, transcribe locally with open-source Whisper models, enrich the transcript, and export TXT, JSON, SRT, and VTT.

## Why this exists

Glaido is a paid API product for turning audio into structured data. From the current public docs/site, its core pattern is:

1. Capture audio from uploads, streams, or live mic input.
2. Transcribe audio across many languages.
3. Enrich transcripts with diarization, PII redaction, named entities, sentiment, chapterization, summarization, subtitles, and audio-to-LLM workflows.
4. Integrate through APIs, webhooks, SDKs, and downstream tools.

This portfolio project recreates the useful solo-user version for free: no paid API key, no SaaS dependency, and privacy-friendly local processing.

## MVP features

- Upload common audio/video files supported by ffmpeg/Whisper.
- Browser microphone recording with one-click upload.
- Local transcription through `faster-whisper`.
- Configurable model size: `tiny`, `base`, `small`, `medium`, `large-v3`.
- Automatic language detection from Whisper metadata.
- Segment timestamps.
- TXT, JSON, SRT, and VTT exports.
- Lightweight transcript intelligence:
  - extractive summary;
  - keywords;
  - email/phone PII redaction;
  - simple chapterization by transcript length.
- REST API for portfolio/demo integrations.

## Quick start

Requirements:

- Python 3.10-3.13
- ffmpeg installed on your machine

```bash
cd /opt/data/open-transcribe-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open: http://127.0.0.1:8000

First transcription downloads the selected Whisper model. Use `tiny` for fastest free CPU use.

## API

```bash
curl -F "file=@meeting.mp3" -F "model_size=tiny" http://127.0.0.1:8000/api/transcribe
```

Response includes transcript text, segments, summary, keywords, chapters, redacted text, and export download URLs.

## Tests

```bash
pytest -q
```

## Portfolio positioning

This is framed as an AI Product Manager portfolio build: take a real AI infra product, identify the user value chain, scope a free/local MVP, and ship a usable demo with clear tradeoffs.

## Not included yet

- True speaker diarization. A future free route is optional pyannote/community models, but setup is heavier and may require model terms acceptance.
- Real-time WebSocket streaming transcription. The current MVP records/upload batches from browser mic.
- LLM summarization. Current summary is local extractive logic to keep the project free.
