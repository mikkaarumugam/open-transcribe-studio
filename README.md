# WhisperType

Free, local-first voice typing for macOS inspired by Glaido's core workflow: hold a key, speak, release, and the transcribed text is pasted into whatever app your cursor is already in.

## What this is

Glaido's main value proposition is not just file transcription. It is universal dictation: one hotkey, any app, ready-to-send text. WhisperType is the free/open-source version of that core idea.

MVP behavior:

1. Put your cursor in any app: Chrome, Gmail, Notion, Cursor, Claude, Slack, Telegram, Discord, etc.
2. Hold `fn`.
3. Speak.
4. Release `fn`.
5. WhisperType transcribes locally with open-source Whisper and pastes the cleaned text into the active app.

No paid API key. No SaaS account. No server required.

## Current status

Built:

- macOS-oriented global hold-to-dictate CLI.
- Default hold key: `fn`.
- Local microphone recording while the key is held.
- Local transcription with `faster-whisper`.
- Clipboard + Cmd+V paste into the active macOS app.
- Lightweight cleanup: removes common fillers like “um/uh”, trims spaces, capitalizes, and adds final punctuation.
- Tests for the dictation controller and cleanup behavior.
- Original web transcription studio still exists as a secondary demo/API, but the main product direction is now universal voice typing.

Important caveat:

macOS can be inconsistent about exposing the physical `fn` / Globe key to generic Python keyboard listeners. WhisperType now uses native macOS Quartz modifier-flag detection for the default `fn` mode, because testing showed `pynput` may only report `fn` as a release-only raw key like `<63>`. If native `fn` detection still fails, run with `--hold-key f18` or another fallback key while we iterate.

## macOS permissions needed

When running this on your Mac, macOS may ask for:

- Microphone permission: to record speech.
- Accessibility permission: to simulate Cmd+V into the active app.
- Input Monitoring permission: to detect the global hold key.

If it does not prompt automatically, open:

System Settings → Privacy & Security

Then grant permissions to the terminal app you use, for example:

- Terminal
- iTerm
- Cursor terminal
- VS Code terminal

## Install on your Mac

```bash
git clone https://github.com/mikkaarumugam/open-transcribe-studio.git
cd open-transcribe-studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

If `sounddevice` complains, install PortAudio:

```bash
brew install portaudio
pip install -e '.[dev]'
```

## Run the Glaido-style dictation tool

Fastest model, best for testing:

```bash
cd open-transcribe-studio
source .venv/bin/activate
whispertype --model tiny
```

Then:

1. Click into any text box in any app.
2. Hold `fn`.
3. Speak.
4. Release `fn`.
5. Wait for transcription.
6. Text should paste into the active app.

If `fn` is not detected, first inspect what macOS exposes:

```bash
python scripts/detect_keys.py
```

Press `fn` / Globe and look at the printed `normalised=` value. Then run with that value:

```bash
whispertype --model tiny --hold-key f18
```

Or try another key name that your keyboard listener can see.

## Run tests

```bash
pytest -q
```

## Optional: old web transcription demo

The earlier upload/recording web demo still runs:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

But the main portfolio direction is now WhisperType: voice typing anywhere on macOS.

## Product roadmap

Next steps:

- Confirm real `fn` key behavior on Mikka's Mac.
- Add setup checker for macOS permissions.
- Add a visible recording indicator.
- Add silence auto-stop as an optional mode.
- Add local text cleanup presets:
  - raw transcript;
  - polished message;
  - email style;
  - coding prompt style.
- Package as a macOS menubar app.
- Add demo GIF and portfolio case study.

## Portfolio angle

This project demonstrates taking a paid AI-product workflow, identifying the highest-value feature, and rebuilding a useful free/local MVP with clear tradeoffs:

- Glaido: polished paid universal dictation product.
- WhisperType: free local-first proof-of-concept focused on the same core user job: speak instead of type anywhere.
