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
- Native macOS `.app` bundle whose tiny Obj-C launcher owns the hotkey event tap, so Input Monitoring trust binds to WhisperType itself (not the Python framework).
- Configurable hotkey: default is `fn` / Globe, change it any time from the menu bar via *Set hotkey…*; persists to `~/.config/whispertype/hotkey.txt`.
- Local microphone recording while the key is held.
- Local transcription with `faster-whisper`, forced to English by default to avoid wrong-language hallucinations.
- Clipboard + Cmd+V paste into the active macOS app.
- Menu-bar shortcuts to the macOS permissions panes (*Open Accessibility Settings*, *Open Input Monitoring Settings*).
- Lightweight cleanup: removes common fillers like “um/uh”, trims spaces, capitalizes, and adds final punctuation.
- Tests for the dictation controller, hotkey config, fn listener, and bundle builder.
- Original web transcription studio still exists as a secondary demo/API, but the main product direction is now universal voice typing.

## macOS permissions needed

WhisperType needs three macOS permissions:

- **Microphone** — to record speech.
- **Accessibility** — to simulate Cmd+V into the active app.
- **Input Monitoring** — to detect the global hold key.

If macOS does not prompt automatically, open **System Settings → Privacy & Security**. The `WT` menu has shortcuts: *Open Accessibility Settings* and *Open Input Monitoring Settings*.

**Running from `dist/WhisperType.app` (recommended).** The bundle's native launcher owns the hotkey listener, so you only need to enable **WhisperType** in Accessibility and Input Monitoring — there is no separate "Python 3" row to worry about.

**Running from Terminal.** Grant the same permissions to whichever terminal you use (Terminal, iTerm, the Cursor or VS Code terminal, etc.).

**Heads-up: rebuilding the `.app` resets grants.** macOS binds permission grants to the binary's code signature, not the bundle ID. Every time you run `whispertype-build-app`, the signature changes and your previous grants stop applying — even though the app name and bundle ID are identical. To recover:

```bash
tccutil reset ListenEvent com.mikka.open-transcribe-studio.whispertype
tccutil reset Accessibility com.mikka.open-transcribe-studio.whispertype
```

Then reopen `dist/WhisperType.app` and re-enable WhisperType in both panes. A stable signing identity would fix this; ad-hoc-signed dev builds are why you keep hitting it.

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

### Terminal-mode fallback

If you are running from Terminal (not the `.app`) and `fn` is not detected, first inspect what macOS exposes:

```bash
python scripts/detect_keys.py
```

Press `fn` / Globe and look at the printed `normalised=` value. Then run with that value:

```bash
whispertype --model tiny --hold-key f18
```

Or try another key name that your keyboard listener can see. On Mikka's Mac, `fn` / Globe has shown up as raw `<179>`:

```bash
whispertype --model tiny --hold-key '<179>'
```

When you run from the `.app` bundle (recommended), this fallback is not needed — the bundle's native launcher detects `fn` / Globe directly, and any other hotkey can be set from the menu.

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

When the hotkey is healthy, the log should include lines like:

```text
[WhisperType] launcher CGEventTap installed (bundle owns hotkey trust)
[WhisperType] fn down
[WhisperType] fn up
```

If `WT` appears in the menu bar but pressing the hotkey does nothing and the log does not show `fn down`, the most common cause is that grants reset after a rebuild — see the `tccutil reset` instructions in the macOS permissions section above, then quit and reopen the app.

### Change the hotkey

Click `WT` in the menu bar → *Set hotkey…*, then press the key or combo you want. The choice persists across launches.

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

- Add a visible recording indicator.
- Add silence auto-stop as an optional mode.
- Add local text cleanup presets:
  - raw transcript;
  - polished message;
  - email style;
  - coding prompt style.
- Stable signing identity so permission grants survive rebuilds.
- Demo GIF and portfolio case study.

## Portfolio angle

Honest framing: this project is **vibecoded**. I am not the engineer who hand-wrote it. I'm the product person who decided what to build, what to cut, when to push back on the AI's suggestions, and when to verify on real hardware before calling something "done." I'm posting it under that framing on purpose — I'm going for AI product roles, and pretending I wrote every line would miss the point.

**The product decisions I made**

- **Picked the core job.** Glaido does many things; voice-typing-anywhere is the one users pay for. Everything else got cut.
- **Local over cloud.** No API keys, no accounts, no server. The tradeoff is slower transcription and a one-time model download — accepted, because it makes the tool free and private by default.
- **Started with `fn`-only, then realised the real requirement was "the user picks their own hotkey."** Reframed the scope mid-build and added a menu-bar capture UI with on-disk persistence.
- **Kept Terminal mode as an escape hatch.** When the bundled `.app` had permissions issues, I shipped both paths instead of waiting for a perfect fix.
- **Named the rough edges instead of hiding them.** TCC grants reset on rebuild because of ad-hoc signing — that limitation is in the README, not buried.

**How I worked with AI to ship it**

- I describe the user-facing goal; the AI proposes architecture; I verify it end-to-end and push back when the diagnosis is wrong. (Example: a "fixed" version still wasn't catching `fn` events — I caught that the `.app` bundle hadn't been rebuilt, so the new Python code was running against a stale Obj-C launcher.)
- I learned just enough vocabulary of the platform constraints (macOS TCC, code signing, why permissions don't transfer across binaries) to spot when the AI was solving the wrong problem.
- Tests exist for the parts I needed confidence in — not because I wrote them, but because I asked for them and read the assertions before merging.

**What this is meant to demonstrate**

Not "I can code." The thing I'm trying to show is the modern PM job: *take a paid product's core job, scope an MVP, direct an AI to build it, verify it works on real hardware, and ship it with honest tradeoffs.* The artefact is real (it runs, my microphone is hot, the text appears) but the value of the project is the process, not the source code.

**What this is not**

A Glaido competitor. A polished consumer product. A demonstration of my engineering ability. A claim that AI tools made it effortless — they didn't; the work was in the spec, the verification, and the judgement calls.
