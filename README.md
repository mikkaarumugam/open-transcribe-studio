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
- Local transcription with `faster-whisper`, forced to English by default to avoid wrong-language hallucinations.
- Clipboard + Cmd+V paste into the active macOS app.
- Optional macOS menu bar mode plus a free local `.app` launcher so Terminal does not need to stay open.
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

When running from Terminal, grant permissions to the terminal app you use, for example:

- Terminal
- iTerm
- Cursor terminal
- VS Code terminal

When running `dist/WhisperType.app`, macOS may show separate permission rows for `WhisperType` and `Python 3`. For the current free Python-powered prototype, grant Input Monitoring and Accessibility to both if `fn` is not detected or paste does not work. After changing permissions, quit `WT` from the menu bar and reopen `dist/WhisperType.app`.

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

WhisperType now forces English transcription by default:

```bash
whispertype --model tiny --language en
```

If you want Whisper to auto-detect language instead:

```bash
whispertype --model tiny --language auto
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

On Mikka's current Mac, `fn` / Globe has been seen as raw `<179>`, so this is the fastest fallback to try:

```bash
whispertype --model tiny --hold-key '<179>'
```

## Run as a menu bar app without Terminal

Once the normal `whispertype --model tiny` command works in Terminal, build the local app launcher:

```bash
cd open-transcribe-studio
source .venv/bin/activate
whispertype-build-app --repo-dir "$PWD" --model tiny --language en
open dist/WhisperType.app
```

If double-clicking does not show `WT`, rebuild the app after pulling updates. The builder creates a tiny native macOS launcher that owns the `WT` menu-bar item and starts the Python dictation worker in the background.

```bash
cd open-transcribe-studio
git pull
source .venv/bin/activate
pip install -e .
whispertype-build-app --repo-dir "$PWD" --model tiny --language en
open dist/WhisperType.app
```

The app writes launch errors here:

```text
~/Library/Logs/WhisperType/launcher.log
```

To inspect it:

```bash
tail -80 ~/Library/Logs/WhisperType/launcher.log
```

When `fn` detection is healthy, the log should include:

```text
[WhisperType] native macOS fn event tap is running
[WhisperType] fn down
[WhisperType] fn up
```

If `WT` appears but pressing `fn` does nothing and the log does not show `fn down`, re-check Input Monitoring and Accessibility for both `WhisperType` and `Python 3`, then quit and reopen the app.

For faster local debugging, use the one-command restart loop instead of repeatedly copying the full rebuild block:

```bash
whispertype-dev-restart --hold-key '<179>'
```

It pulls, reinstalls, kills old app/Python workers, rebuilds, opens `WhisperType.app`, and prints the latest launcher log. Use `--no-pull --no-install` when only testing local code changes.

What this does:

- launches WhisperType as a normal macOS menu bar app;
- shows a small `WT` item in the menu bar;
- keeps listening for hold-`fn` dictation while Terminal is closed;
- lets you quit from the menu bar.

CPU note: idle usage should be very low because it is only listening for key events. CPU spikes happen after you release `fn`, while Whisper transcribes the recorded audio locally.

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
- Add demo GIF and portfolio case study.

## Portfolio angle

This project demonstrates taking a paid AI-product workflow, identifying the highest-value feature, and rebuilding a useful free/local MVP with clear tradeoffs:

- Glaido: polished paid universal dictation product.
- WhisperType: free local-first proof-of-concept focused on the same core user job: speak instead of type anywhere.
