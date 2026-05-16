# Glaido research notes

Source checked:

- https://glaido.com/

## Corrected product understanding

Glaido is a universal dictation product, not mainly an upload transcription dashboard.

Core promise from the site:

- “Stop typing start talking.”
- “Speak naturally. Get clean, ready-to-send text in any app.”
- “Press one key. Start talking. Your words appear as clean, professional text instantly.”
- Works in apps like Gmail, GitHub, Notion, Telegram, WhatsApp, Slack, Linear, Cursor, Claude, Figma, Discord, Chrome.

## Feature we care about

The only feature in scope for this portfolio MVP:

Hold a key anywhere on macOS, speak, release the key, and have the cleaned transcript typed/pasted into the currently active app.

User requested the hold key should be `fn`:

- hold `fn` = record;
- release `fn` = stop, transcribe, paste.

## MVP interpretation

A free version can be built locally:

1. Global key listener detects `fn` down/up.
2. Microphone records while key is held.
3. Local Whisper transcribes the temporary audio file.
4. Lightweight cleanup improves raw transcript.
5. App copies text to clipboard and sends Cmd+V into the active app.

## macOS permission requirements

This workflow needs:

- Microphone permission.
- Accessibility permission for paste automation.
- Input Monitoring permission for global key capture.

## Known risk

macOS may not expose the physical `fn` / Globe key to all Python keyboard listener libraries. WhisperType defaults to `fn`, but keeps `--hold-key` configurable so we can test fallback mappings like `f18` on the actual Mac.
