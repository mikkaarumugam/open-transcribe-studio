# WhisperType

Free, local-first voice typing for macOS. Hold a key, speak, release, and the transcribed text is pasted into whatever app your cursor is already in.

I was paying for tools like Wispr Flow and Glaido every month. They are great, but I kept wondering if SaaS like this is starting to look optional now that you can vibecode the core feature locally in a weekend. So I built WhisperType to find out.

## What this is

The thing people actually pay for in those products is not file transcription. It is universal dictation. One hotkey, any app, instant text. That is what WhisperType does.

How it works:

1. Put your cursor in any app. Chrome, Gmail, Notion, Cursor, Claude, Slack, Telegram, Discord, whatever.
2. Hold `fn` (or any hotkey you set).
3. Speak.
4. Release the key.
5. WhisperType transcribes locally with open-source Whisper and pastes the cleaned text into the active app.

No paid API key. No account. No server. Your audio never leaves your machine.

## Current status

What works today:

- Global hold-to-dictate on macOS, runs from a real `.app` bundle so you can launch it from Spotlight or Finder like any normal Mac app.
- Configurable hotkey. Default is `fn` / Globe, change it any time from the menu bar via *Set hotkey…*. Your choice persists to `~/.config/whispertype/hotkey.txt`.
- Local microphone recording while the key is held.
- Local transcription with `faster-whisper`. Defaults to English so it does not hallucinate other languages. Model is configurable from the menu bar (tiny / base / small / medium / large-v3), persists to `~/.config/whispertype/model.txt`.
- Clipboard + Cmd+V paste into the active app.
- Menu bar shortcuts to the macOS permissions panes (*Open Accessibility Settings*, *Open Input Monitoring Settings*).
- Light cleanup: trims um/uh fillers, fixes spacing, capitalises, adds final punctuation.
- Temp recordings are deleted right after Whisper finishes, so nothing piles up on disk.
- Tests for the dictation controller, hotkey config, fn listener, and bundle builder.

## macOS permissions needed

WhisperType needs three macOS permissions:

- **Microphone**, to record your voice.
- **Accessibility**, to send Cmd+V into the active app.
- **Input Monitoring**, to detect the global hotkey.

If macOS does not prompt automatically, open **System Settings → Privacy & Security**. The `WT` menu also has direct shortcuts: *Open Accessibility Settings* and *Open Input Monitoring Settings*.

**Running from `dist/WhisperType.app` (recommended).** The bundle's native launcher owns the hotkey listener, so you only need to enable **WhisperType** in Accessibility and Input Monitoring. There is no separate "Python 3" row to worry about.

**Running from Terminal.** Grant the same permissions to whichever terminal you use (Terminal, iTerm, the Cursor or VS Code terminal, etc.).

**Heads-up: rebuilding the `.app` resets grants.** macOS ties permission grants to the binary's code signature, not the bundle ID. Every time you run `whispertype-build-app`, the signature changes and your previous grants stop applying, even though the app name and bundle ID are identical. To recover:

```bash
tccutil reset ListenEvent com.mikka.open-transcribe-studio.whispertype
tccutil reset Accessibility com.mikka.open-transcribe-studio.whispertype
```

Then reopen `dist/WhisperType.app` and re-enable WhisperType in both panes. A proper signing identity would fix this. Ad-hoc dev builds are why you keep hitting it.

## Privacy: what is stored locally

WhisperType is local-first. Nothing is uploaded anywhere. But two things do get written to your Mac while the app runs:

- **A log file** at `~/Library/Logs/WhisperType/launcher.log`. This includes diagnostic lines AND the transcribed text of what you said (so you can debug bad transcriptions). It is plain text. Read it with `tail -80 ~/Library/Logs/WhisperType/launcher.log`. Wipe it any time with `rm ~/Library/Logs/WhisperType/launcher.log`.
- **A temporary `.wav` recording per hotkey press**, written to the macOS temp folder (`/var/folders/.../T/whispertype-*.wav`) so Whisper can read it. WhisperType deletes each one as soon as transcription finishes. If you ever want to double-check nothing is sitting around, run `ls /var/folders/*/T/whispertype-*.wav 2>/dev/null` (no output = nothing there).

## Choosing a Whisper model

WhisperType uses [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper), which ships several model sizes. Bigger models are more accurate but slower and bigger on disk. For hotkey-style dictation (short clips, mostly clear English), **`base` is the sweet spot** and it is the default.

| Model | Disk | Speed on a Mac | Accuracy | When to pick it |
|---|---|---|---|---|
| `tiny` | ~75 MB | fastest | weakest | Smoke-testing setup only. Will mishear short or accented speech. |
| **`base`** | ~150 MB | fast | decent | **Default.** Good for clear English dictation on a typical Mac. |
| `small` | ~480 MB | slower | noticeably better | Bump to this if `base` keeps mishearing your accent, common words, or background noise. |
| `medium` | ~1.5 GB | slow | strong | Overkill for short dictation. Useful if your audio is long or hard. |
| `large-v3` | ~3 GB | slowest | best | Way overkill for hotkey dictation. Adds seconds of delay per phrase. |

### Change the model from the menu bar

Click `WT` → *Model* → pick one. WhisperType saves your choice to `~/.config/whispertype/model.txt` and shows an alert telling you to quit and reopen the app for the new model to take effect.

**First time you pick a new model, Whisper will download it.** This is a one-time cost per model, cached under `~/.cache/huggingface/`. Plan for a few minutes on the bigger ones (`small` ≈ 480 MB, `medium` ≈ 1.5 GB, `large-v3` ≈ 3 GB).

You can also pick a model at the command line when running from Terminal, or when building the `.app`:

```bash
whispertype --model small
.venv/bin/whispertype-build-app --model small
```

The CLI flag controls the *initial default*; the menu choice overrides it on next launch.

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

## Run the dictation tool

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

When you run from the `.app` bundle (recommended), this fallback is not needed. The bundle's native launcher detects `fn` / Globe directly, and any other hotkey can be set from the menu.

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

If `WT` appears in the menu bar but pressing the hotkey does nothing and the log does not show `fn down`, the usual cause is that grants reset after a rebuild. See the `tccutil reset` instructions in the macOS permissions section above, then quit and reopen the app.

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

## Product roadmap

Next things I want to add:

- A visible recording indicator so you know it heard you.
- Optional silence auto-stop, so you don't have to hold the key.
- Local text cleanup presets (raw transcript, polished message, email style, coding prompt).
- A stable signing identity so permission grants survive rebuilds.
- A short demo video.

## Why I built this

I was paying for Wispr Flow and trying Glaido on the side. Both are good. Both cost money every month. And both have the same core feature: hold a key, talk, get clean text wherever your cursor is.

I kept asking myself: now that I can vibecode a working version of that core feature in a weekend with AI tools, is monthly SaaS for this kind of thing still the right shape? Or has the unit economics quietly flipped, where the paid version has to start justifying itself against a free local one that runs on your own machine?

I built WhisperType to find out. Not to replace any of those products, just to test the thesis with my own hands.

## What this is meant to show

I am going for AI product roles, so I want to be upfront: this is vibecoded. I am not the engineer who hand-wrote it. The thing I am demonstrating is not "I can code". It is the modern product job:

- Take a paid product's core job and identify the one feature people actually pay for.
- Scope it down to an MVP you can actually ship.
- Direct an AI to build it, and verify it works on real hardware before calling anything done.
- Make honest tradeoffs and put the rough edges in the README, not hide them.

A few product calls I made along the way:

- **Picked the core job.** These products do many things; voice-typing-anywhere is the one users pay for. Everything else got cut.
- **Local over cloud.** No API keys, no accounts, no server. The tradeoff is a one-time model download and slower transcription on small Macs. Worth it for free and private.
- **Started with `fn` only, then realised the real requirement was "the user picks their own hotkey".** Reframed the scope mid-build and added the menu bar capture UI.
- **Kept Terminal mode as an escape hatch.** When the bundled `.app` had permissions issues, I shipped both paths instead of waiting for a perfect fix.
- **Named the rough edges.** TCC grants reset on rebuild because of ad-hoc signing. That's documented above, not buried.

How I actually work with AI to ship things:

- I describe the user-facing goal. The AI proposes architecture. I verify end-to-end and push back when the diagnosis is wrong. (Example: a "fixed" version still wasn't catching `fn` events. The AI was confident the code was right; I caught that the `.app` bundle had not been rebuilt, so the new Python code was running against a stale Obj-C launcher.)
- I learn just enough of the platform vocabulary (macOS permissions, code signing, why permissions don't transfer across binaries) to spot when the AI is solving the wrong problem.
- Tests exist for the parts I needed confidence in. Not because I wrote them, but because I asked for them and read the assertions before merging.

## What this is not

Not a competitor to any paid dictation tool. Not a polished consumer product. Not a claim that AI tools make this effortless. They don't. The work is in the spec, the verification, and the judgement calls.
