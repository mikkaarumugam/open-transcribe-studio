from __future__ import annotations

import threading


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
