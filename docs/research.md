# Glaido research notes

Source pages checked:

- https://www.glaido.ai/
- https://www.glaido.ai/pricing
- https://docs.glaido.ai/chapters/introduction

## Product summary

Glaido positions itself as AI audio infrastructure for voice products. The homepage describes an end-to-end pipeline to record, transcribe, and enrich audio through one API, with multilingual support and EU data residency.

## Key product pattern

- Capture: uploads, live streams, real-time mic input, common audio formats, SDK/API access.
- Transcribe: accurate conversational speech-to-text, noisy/multilingual/jargon-heavy audio, speaker detection, 100+ languages.
- Enrich: audio-to-LLM, PII redaction, sentiment, entity detection, summarization/chapterization/subtitles in docs.
- Integrate: push enriched data to CRMs/databases/warehouses, webhooks, Zapier/native integrations.

## Pricing observation

The public pricing page showed async transcription at about $0.61/hr, real-time at about $0.75/hr, and 10 free hours monthly. This project avoids per-hour usage fees by using local open-source models.

## MVP interpretation

For a solo-user free tool, the highest value pieces are:

1. Local upload/mic capture.
2. Reliable transcription with timestamps.
3. Practical exports.
4. Basic transcript intelligence without paid APIs.
5. A clean web UI and API that demonstrates product thinking.
