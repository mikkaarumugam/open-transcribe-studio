from __future__ import annotations

import threading


def show_microphone_denied_alert() -> None:
    try:
        import subprocess

        subprocess.run(
            [
                "osascript",
                "-e",
                'display alert "WhisperType microphone blocked" message "macOS denied microphone access for the app runtime. For now, run WhisperType from Terminal where the mic is authorized, or reset Microphone privacy and relaunch WhisperType." as critical',
            ],
            check=False,
        )
    except Exception:
        pass


def show_input_monitoring_denied_alert() -> None:
    """Tell the user when the fn/global-key listener cannot start.

    This is intentionally best-effort: the real diagnostic is still written to
    ~/Library/Logs/WhisperType/launcher.log, but a silent background worker
    crash makes the app feel dead from the menu bar.
    """
    try:
        import subprocess

        subprocess.run(
            [
                "osascript",
                "-e",
                'display alert "WhisperType fn key blocked" message "WhisperType can show WT, but macOS is blocking the background fn-key listener. Open System Settings → Privacy & Security → Accessibility and Input Monitoring, then allow WhisperType and Python 3. Quit and reopen WhisperType after changing permissions." as critical',
            ],
            check=False,
        )
    except Exception:
        pass


def show_open_accessibility_settings_alert() -> None:
    """Open the macOS Privacy settings page for global-key permissions."""
    try:
        import subprocess

        subprocess.run(
            [
                "osascript",
                "-e",
                'display alert "WhisperType needs Accessibility" message "The menu-bar app is running, but macOS is not sending fn/Globe events to the background worker. Open Accessibility settings, add WhisperType.app and Python.app/Python 3, enable them, then quit and reopen WhisperType." buttons {"Open Settings", "Cancel"} default button "Open Settings"',
            ],
            check=False,
        )
        subprocess.run(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ],
            check=False,
        )
    except Exception:
        pass


def request_microphone_permission(timeout_seconds: float = 10.0) -> bool | None:
    """Ask macOS for microphone access for the current process if possible.

    Returns True/False when AVFoundation is available and responds, or None when
    running outside macOS/PyObjC where the permission API is unavailable.
    """
    try:
        import AVFoundation  # type: ignore[import-not-found]
    except Exception:
        return None

    media_type = AVFoundation.AVMediaTypeAudio
    status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(media_type)
    authorized = getattr(AVFoundation, "AVAuthorizationStatusAuthorized", 3)
    denied = getattr(AVFoundation, "AVAuthorizationStatusDenied", 2)
    restricted = getattr(AVFoundation, "AVAuthorizationStatusRestricted", 1)

    if status == authorized:
        print("[WhisperType] macOS microphone permission already authorized", flush=True)
        return True
    if status in {denied, restricted}:
        print(
            "[WhisperType] macOS microphone permission is denied/restricted for this runtime",
            flush=True,
        )
        return False

    event = threading.Event()
    result = {"granted": False}

    def completion(granted: bool) -> None:  # pragma: no cover - macOS callback
        result["granted"] = bool(granted)
        event.set()

    print("[WhisperType] requesting macOS microphone permission", flush=True)
    AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        media_type,
        completion,
    )
    event.wait(timeout_seconds)
    print(f"[WhisperType] macOS microphone permission granted: {result['granted']}", flush=True)
    return bool(result["granted"])
