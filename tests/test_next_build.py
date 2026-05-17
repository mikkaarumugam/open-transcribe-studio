from pathlib import Path
import plistlib

from app.mac_dictation.app_bundle import (
    BUNDLE_IDENTIFIER,
    build_app_bundle,
    render_launcher_script,
    render_native_launcher_source,
)
from app.mac_dictation.whisper import LocalWhisperTranscriber


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisperModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return [FakeSegment(" hello "), FakeSegment("world ")], object()


def test_local_whisper_forces_english_by_default():
    model = FakeWhisperModel()
    transcriber = LocalWhisperTranscriber(model_size="tiny")
    transcriber._model = model

    text = transcriber.transcribe("/tmp/audio.wav")

    assert text == "hello world"
    assert model.calls == [
        (
            "/tmp/audio.wav",
            {"beam_size": 5, "vad_filter": False, "language": "en", "task": "transcribe"},
        )
    ]


def test_local_whisper_can_disable_language_for_auto_detect():
    model = FakeWhisperModel()
    transcriber = LocalWhisperTranscriber(model_size="tiny", language="auto")
    transcriber._model = model

    transcriber.transcribe("/tmp/audio.wav")

    assert "language" not in model.calls[0][1]
    assert model.calls[0][1]["task"] == "transcribe"


def test_launcher_script_runs_python_module_from_repo_venv_without_terminal():
    launcher = render_launcher_script(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="tiny",
        hold_key="fn",
        language="en",
    )

    assert "REPO_DIR='/Users/mikka/open-transcribe-studio'" in launcher
    assert "repo path does not exist: $REPO_DIR" in launcher
    assert "LOG_FILE=\"$HOME/Library/Logs/WhisperType/launcher.log\"" in launcher
    assert "source '.venv/bin/activate'" in launcher
    assert "exec '.venv/bin/python' -m app.mac_dictation.cli --model 'tiny' --hold-key 'fn' --language 'en' --menubar" in launcher


def test_native_launcher_execs_repo_python_without_applescript_wrapper():
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    # The repo path used to live in main() as a local; it's now a file-scope
    # static (kRepoDir) so pickModel: can restart the worker after a swap.
    assert 'static const char *kRepoDir = "/Users/mikka/open-transcribe-studio";' in source
    assert 'execl(' in source
    assert '".venv/bin/python"' in source
    assert '"app.mac_dictation.cli"' in source
    assert '"--native-worker"' in source
    assert '"--menubar"' not in source
    assert 'printf("--- WhisperType native launch ---\\n");' in source
    assert "NSStatusItem *statusItem" in source
    assert 'setTitle:@"WT"' in source
    assert 'do shell script' not in source
    assert 'osascript' not in source


def test_native_launcher_supports_configurable_hotkey_with_capture_ui():
    # The end-user goal: hotkey is configurable from the menu bar, persisted to
    # ~/.config/whispertype/hotkey.txt, and re-read on launch. Match logic
    # branches between the fn/Globe flag and arbitrary keycode+modifier chords.
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    # Config load/save
    assert "load_hotkey_config_from_disk" in source
    assert "save_hotkey_config_to_disk" in source
    assert ".config/whispertype/hotkey.txt" in source

    # Generalized match: keycode + modifier flags, plus fn/Globe special case.
    assert "current_hotkey.keycode" in source
    assert "current_hotkey.modifier_flags" in source
    assert "current_hotkey.use_fn_flag" in source
    assert "kCGEventFlagMaskCommand" in source
    assert "kCGEventFlagMaskShift" in source

    # Menu bar UI
    assert "Set hotkey" in source
    assert "setHotkey:" in source
    assert "addLocalMonitorForEventsMatchingMask" in source
    assert "NSEventMaskKeyDown" in source
    assert "NSEventMaskFlagsChanged" in source

    # Menu shows the current hotkey label and is refreshed after capture.
    assert "Hotkey: %s" in source
    assert "refreshHotkeyMenuLabel" in source


def test_native_launcher_polls_status_file_and_updates_menu_bar_title():
    # End-user goal: the WT menu bar icon shows whether WhisperType is
    # recording / transcribing / idle so the user has feedback during a
    # slow Whisper model run instead of dead air.
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert "read_status_from_disk" in source
    assert ".config/whispertype/status.txt" in source
    assert "menu_title_for_status" in source
    assert "pollStatusIndicator:" in source
    assert "scheduledTimerWithTimeInterval:0.25" in source
    # Distinct titles for the three meaningful states.
    assert '@"WT \u25CF"' in source  # recording (black circle)
    assert '@"WT\u2026"' in source   # transcribing (ellipsis)
    assert '@"WT !"' in source       # error


def test_native_launcher_supports_configurable_whisper_model_via_menu():
    # End-user goal: pick the Whisper model from the menu bar.
    # Saved to ~/.config/whispertype/model.txt, read on launch, and
    # the launcher passes it to --model when execing Python.
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert "load_model_from_disk" in source
    assert "save_model_to_disk" in source
    assert ".config/whispertype/model.txt" in source
    assert "current_model" in source
    assert 'VALID_MODELS' in source
    assert '"tiny"' in source and '"small"' in source and '"medium"' in source and '"large-v3"' in source

    assert '"--model",\n            current_model' in source

    assert "pickModel:" in source
    assert "Model: %s" in source
    assert "refreshModelMenuLabel" in source
    # Picking a model now auto-restarts the Python worker so the menu and
    # the actually-loaded model can never disagree. The user does not have
    # to quit and reopen the app to apply the change.
    assert "restart_python_worker" in source
    assert "Switching to %s" in source
    assert "Model will change after restart" not in source

    # Restart implementation details: SIGTERM with bounded wait, SIGKILL
    # fallback so a wedged worker can't block the swap forever.
    assert "kill(child_pid, SIGTERM)" in source
    assert "SIGKILL" in source


def test_native_launcher_shows_per_model_downloaded_state_in_submenu():
    # End-user goal: opening the Model submenu shows which models are already
    # on disk, which are mid-download (lock file + live PID), and which still
    # need to be downloaded. The submenu rebuilds on open via NSMenuDelegate
    # so it always reflects fresh on-disk state — no background polling.
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    # C helpers that read disk state.
    assert "model_is_downloaded" in source
    assert "models--Systran--faster-whisper-" in source
    assert "snapshots" in source
    assert "download_in_progress_for" in source
    assert "downloading-%s.lock" in source
    # Stale lock detection so a crashed helper does not block re-download.
    assert "kill(pid, 0)" in source
    # Human-readable sizes for the "Download (X GB)" labels.
    assert "model_size_label" in source
    assert '"1.5 GB"' in source
    assert '"3.0 GB"' in source

    # Background fork of the Python helper. setsid() detaches the child
    # so quitting WhisperType.app doesn't kill an in-flight download.
    assert "start_model_download" in source
    assert '"app.mac_dictation.download_model"' in source
    assert "setsid()" in source

    # Obj-C menu wiring: rebuild on open, three distinct item states.
    assert "rebuildModelSubmenu" in source
    assert "NSMenuDelegate" in source
    assert "menuNeedsUpdate:" in source
    assert "downloadModel:" in source
    assert "Downloading…" in source
    assert "Download (%s)" in source

    # Within rebuildModelSubmenu, the in-progress check must be evaluated
    # before the on-disk check. huggingface_hub creates the snapshots dir
    # early in a download (before blobs land), so model_is_downloaded
    # returns true during an in-flight download. If the menu trusted that
    # first, the user would see "ready" for a model that is actually
    # still downloading, and clicking it would silently wedge dictation
    # for several minutes while the download finishes and the worker
    # loads the model. The lock file is the source of truth during a
    # download — once the helper exits, it removes the lock, then
    # model_is_downloaded takes over.
    # Match the implementation, not the @interface forward declaration:
    # the impl line ends with "{" while the forward decl ends with ";".
    rebuild_start = source.index("- (void)rebuildModelSubmenu {")
    # The next method implementation after rebuildModelSubmenu is
    # menuNeedsUpdate:, which marks the end of the rebuild body.
    rebuild_end = source.index("- (void)menuNeedsUpdate:(NSMenu *)menu {", rebuild_start)
    rebuild_body = source[rebuild_start:rebuild_end]
    in_progress_pos = rebuild_body.index("download_in_progress_for(name)")
    downloaded_pos = rebuild_body.index("model_is_downloaded(name)")
    assert in_progress_pos < downloaded_pos, (
        "rebuildModelSubmenu must check download_in_progress_for(name) "
        "BEFORE model_is_downloaded(name) — otherwise the menu shows a "
        "model as 'ready' while it is actually still downloading."
    )


def test_native_launcher_owns_fn_event_tap_so_trust_attaches_to_bundle():
    # macOS TCC binds Input Monitoring trust to the binary that calls
    # CGEventTapCreate. The bundle must own that call so the user's grant
    # of "WhisperType" actually authorises the fn key listener (instead of
    # /Library/Frameworks/Python.framework/.../python3.13, which is what
    # .venv/bin/python resolves to).
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert "CGEventTapCreate(" in source
    assert "kCGEventFlagMaskSecondaryFn" in source
    assert "pipe(fn_pipe)" in source
    assert "dup2(fn_pipe[0], STDIN_FILENO)" in source
    assert 'write_hotkey_event("FN_DOWN")' in source
    assert 'write_hotkey_event("FN_UP")' in source
    assert "start_fn_event_tap();" in source


def test_native_launcher_source_has_valid_c_string_escapes():
    source = render_native_launcher_source(
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert 'printf("--- WhisperType native launch ---\\n");' in source
    assert 'fprintf(stderr, "repo path does not exist or cannot be opened: %s: %s\\n", kRepoDir, strerror(errno));' in source
    assert 'printf("repo: %s\\n", kRepoDir);' in source
    assert 'fprintf(stderr, "missing executable .venv/bin/python in %s\\n", repo);' in source
    assert 'fprintf(stderr, "failed to exec %s: %s\\n", python, strerror(errno));' in source


def test_build_app_bundle_writes_macos_app_structure(tmp_path):
    app_path = build_app_bundle(
        output_dir=tmp_path,
        repo_dir=Path("/Users/mikka/open-transcribe-studio"),
        model="base",
        hold_key="fn",
        language="en",
    )

    assert app_path == tmp_path / "WhisperType.app"
    info_plist = app_path / "Contents" / "Info.plist"
    assert info_plist.exists()
    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleIdentifier"] == BUNDLE_IDENTIFIER
    assert info["NSMicrophoneUsageDescription"]
    launcher = app_path / "Contents" / "MacOS" / "WhisperType"
    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111
    # On Darwin the launcher is a compiled Obj-C binary; the rendered source
    # is stashed alongside it in Resources. On non-Darwin it is a shell script.
    source_file = app_path / "Contents" / "Resources" / "WhisperTypeLauncher.m"
    if source_file.exists():
        assert '"--model"' in source_file.read_text()
    else:
        assert "--model 'base'" in launcher.read_text()
