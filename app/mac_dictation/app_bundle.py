from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
from pathlib import Path


BUNDLE_IDENTIFIER = "com.mikka.open-transcribe-studio.whispertype"
BUNDLE_VERSION = "0.3.0"


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _c_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def render_launcher_script(
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> str:
    """Return a shell fallback launcher for non-macOS tests/dev environments."""
    quoted_repo = _single_quote(str(repo_dir))
    quoted_model = _single_quote(model)
    quoted_hold_key = _single_quote(hold_key)
    quoted_language = _single_quote(language)
    return f"""#!/bin/zsh
set -e
LOG_DIR="$HOME/Library/Logs/WhisperType"
LOG_FILE="$HOME/Library/Logs/WhisperType/launcher.log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1
echo "--- WhisperType launch $(date) ---"
REPO_DIR={quoted_repo}
if [ ! -d "$REPO_DIR" ]; then
  osascript -e "display alert \"WhisperType repo not found\" message \"The app was built for: $REPO_DIR. Rebuild it from the real open-transcribe-studio folder with: whispertype-build-app --repo-dir \\\"$PWD\\\" --model base --language en\""
  echo "repo path does not exist: $REPO_DIR"
  exit 1
fi
cd "$REPO_DIR"
echo "repo: $(pwd)"
if [ ! -x .venv/bin/python ]; then
  osascript -e 'display alert "WhisperType setup needed" message "Open Terminal, cd into the real open-transcribe-studio folder, then run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."'
  echo "missing .venv/bin/python in $(pwd)"
  exit 1
fi
source '.venv/bin/activate'
echo "python: $(.venv/bin/python --version)"
exec '.venv/bin/python' -m app.mac_dictation.cli --model {quoted_model} --hold-key {quoted_hold_key} --language {quoted_language} --menubar
"""


def render_native_launcher_source(
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> str:
    """Return C source for the real macOS CFBundleExecutable.

    Using a compiled executable avoids the AppleScript `do shell script` wrapper,
    which can cause macOS TCC microphone permission to attach to osascript/Python
    instead of the WhisperType.app bundle identity.
    """
    repo = _c_string(str(repo_dir))
    model_c = _c_string(model)
    hold_key_c = _c_string(hold_key)
    language_c = _c_string(language)
    return f'''#import <Cocoa/Cocoa.h>
#import <CoreGraphics/CoreGraphics.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t child_pid = -1;
static NSStatusItem *statusItem = nil;
static NSMenuItem *hotkeyDisplayItem = nil;
static NSMenuItem *modelDisplayItem = nil;
// The model submenu is rebuilt on every open via NSMenuDelegate so the menu
// always reflects what is currently on disk (and what is in the middle of
// downloading) without us having to poll.
static NSMenu *modelSubmenu = nil;
// Repo path baked into the bundle at build time. Stored at file scope so
// pickModel: can re-fork the Python worker (which lives in the repo's
// .venv) after the user picks a new model.
static const char *kRepoDir = "{repo}";

// Configurable Whisper model loaded from ~/.config/whispertype/model.txt.
// Falls back to the build-time default baked in below if the file is missing
// or contains a value we do not recognise.
static char current_model[64] = "{model_c}";
static const char *VALID_MODELS[] = {{ "tiny", "base", "small", "medium", "large-v3" }};
static const int VALID_MODELS_COUNT = 5;

// Status indicator: the Python worker writes one of {{idle, recording, transcribing, silence, error}}
// to ~/.config/whispertype/status.txt whenever the dictation state changes.
// The launcher polls this file via NSTimer and updates the WT menu bar title
// so the user sees something is happening instead of dead air during a slow
// transcription on the larger Whisper models.
static char current_status[32] = "idle";

// Hotkey detection lives in the launcher (not in the Python worker) so macOS
// Input Monitoring trust attaches to WhisperType.app — the bundle the user
// grants in System Settings — instead of
// /Library/Frameworks/Python.framework/.../python3.13, which is what
// .venv/bin/python actually resolves to.
static int fn_pipe_write_fd = -1;
static bool hotkey_is_down = false;
static CFMachPortRef fn_event_tap = NULL;

#define FN_KEYCODE_PRIMARY 63
#define FN_KEYCODE_GLOBE 179
#define ESC_KEYCODE 53

// Configurable hotkey loaded from ~/.config/whispertype/hotkey.txt.
// Defaults to fn/Globe when the file is missing or unreadable, so first launch
// matches WhisperType's documented behavior.
typedef struct {{
    int64_t keycode;
    uint64_t modifier_flags;   // CGEventFlags mask
    bool use_fn_flag;          // true → match via kCGEventFlagMaskSecondaryFn
    char label[64];
}} hotkey_config_t;

static hotkey_config_t current_hotkey = {{
    .keycode = FN_KEYCODE_GLOBE,
    .modifier_flags = 0,
    .use_fn_flag = true,
    .label = "fn",
}};

static void hotkey_config_path(char *out, size_t out_len) {{
    const char *home = getenv("HOME");
    if (!home) home = "";
    snprintf(out, out_len, "%s/.config/whispertype/hotkey.txt", home);
}}

static void load_hotkey_config_from_disk(void) {{
    char path[4096];
    hotkey_config_path(path, sizeof(path));
    FILE *f = fopen(path, "r");
    if (!f) {{
        printf("[WhisperType] hotkey config not found at %s; using default fn\\n", path);
        return;
    }}
    char line[256];
    int idx = 0;
    while (fgets(line, sizeof(line), f)) {{
        size_t len = strlen(line);
        while (len > 0 && (line[len - 1] == '\\n' || line[len - 1] == '\\r' || line[len - 1] == ' ')) {{
            line[--len] = '\\0';
        }}
        if (len == 0 || line[0] == '#') continue;
        switch (idx) {{
            case 0: current_hotkey.keycode = strtoll(line, NULL, 10); break;
            case 1: current_hotkey.modifier_flags = strtoull(line, NULL, 10); break;
            case 2: current_hotkey.use_fn_flag = (line[0] == '1' || line[0] == 't' || line[0] == 'T'); break;
            case 3:
                strncpy(current_hotkey.label, line, sizeof(current_hotkey.label) - 1);
                current_hotkey.label[sizeof(current_hotkey.label) - 1] = '\\0';
                break;
        }}
        idx++;
    }}
    fclose(f);
    printf("[WhisperType] hotkey config loaded: keycode=%lld flags=0x%llx use_fn=%d label=%s\\n",
        (long long)current_hotkey.keycode,
        (unsigned long long)current_hotkey.modifier_flags,
        current_hotkey.use_fn_flag ? 1 : 0,
        current_hotkey.label);
}}

static void save_hotkey_config_to_disk(void) {{
    const char *home = getenv("HOME");
    if (!home) return;
    char dir1[4096], dir2[4096], path[4096];
    snprintf(dir1, sizeof(dir1), "%s/.config", home);
    mkdir(dir1, 0755);
    snprintf(dir2, sizeof(dir2), "%s/.config/whispertype", home);
    mkdir(dir2, 0755);
    hotkey_config_path(path, sizeof(path));
    FILE *f = fopen(path, "w");
    if (!f) {{
        printf("[WhisperType] could not write hotkey config to %s: %s\\n", path, strerror(errno));
        return;
    }}
    fprintf(f, "%lld\\n%llu\\n%d\\n%s\\n",
        (long long)current_hotkey.keycode,
        (unsigned long long)current_hotkey.modifier_flags,
        current_hotkey.use_fn_flag ? 1 : 0,
        current_hotkey.label);
    fclose(f);
    printf("[WhisperType] hotkey config saved: %s\\n", current_hotkey.label);
}}

static bool model_is_valid(const char *name) {{
    for (int i = 0; i < VALID_MODELS_COUNT; i++) {{
        if (strcmp(name, VALID_MODELS[i]) == 0) return true;
    }}
    return false;
}}

static void model_config_path(char *out, size_t out_len) {{
    const char *home = getenv("HOME");
    if (!home) home = "";
    snprintf(out, out_len, "%s/.config/whispertype/model.txt", home);
}}

static void load_model_from_disk(void) {{
    char path[4096];
    model_config_path(path, sizeof(path));
    FILE *f = fopen(path, "r");
    if (!f) {{
        printf("[WhisperType] model config not found at %s; using default %s\\n", path, current_model);
        return;
    }}
    char line[128];
    if (fgets(line, sizeof(line), f) != NULL) {{
        size_t len = strlen(line);
        while (len > 0 && (line[len - 1] == '\\n' || line[len - 1] == '\\r' || line[len - 1] == ' ')) {{
            line[--len] = '\\0';
        }}
        if (model_is_valid(line)) {{
            strncpy(current_model, line, sizeof(current_model) - 1);
            current_model[sizeof(current_model) - 1] = '\\0';
            printf("[WhisperType] model config loaded: %s\\n", current_model);
        }} else {{
            printf("[WhisperType] model config %s is not recognised; falling back to %s\\n", line, current_model);
        }}
    }}
    fclose(f);
}}

static void save_model_to_disk(const char *model) {{
    if (!model_is_valid(model)) {{
        printf("[WhisperType] refusing to save unknown model: %s\\n", model);
        return;
    }}
    const char *home = getenv("HOME");
    if (!home) return;
    char dir1[4096], dir2[4096], path[4096];
    snprintf(dir1, sizeof(dir1), "%s/.config", home);
    mkdir(dir1, 0755);
    snprintf(dir2, sizeof(dir2), "%s/.config/whispertype", home);
    mkdir(dir2, 0755);
    model_config_path(path, sizeof(path));
    FILE *f = fopen(path, "w");
    if (!f) {{
        printf("[WhisperType] could not write model config to %s: %s\\n", path, strerror(errno));
        return;
    }}
    fprintf(f, "%s\\n", model);
    fclose(f);
    printf("[WhisperType] model config saved: %s\\n", model);
}}

static void status_file_path(char *out, size_t out_len) {{
    const char *home = getenv("HOME");
    if (!home) home = "";
    snprintf(out, out_len, "%s/.config/whispertype/status.txt", home);
}}

static bool read_status_from_disk(char *out, size_t out_len) {{
    char path[4096];
    status_file_path(path, sizeof(path));
    FILE *f = fopen(path, "r");
    if (!f) return false;
    if (fgets(out, (int)out_len, f) == NULL) {{
        fclose(f);
        return false;
    }}
    fclose(f);
    size_t len = strlen(out);
    while (len > 0 && (out[len - 1] == '\\n' || out[len - 1] == '\\r' || out[len - 1] == ' ')) {{
        out[--len] = '\\0';
    }}
    return len > 0;
}}

static NSString *menu_title_for_status(const char *status) {{
    if (strcmp(status, "recording") == 0)    return @"WT \u25CF";   // black circle
    if (strcmp(status, "transcribing") == 0) return @"WT\u2026";    // ellipsis
    if (strcmp(status, "error") == 0)        return @"WT !";
    return @"WT";
}}

// === Model download state ===
// A model is "downloaded" when faster-whisper / huggingface_hub has populated
// the snapshots/ subdir under the model's cache directory. Using snapshots/
// (and requiring it to be non-empty) avoids reporting a partially-downloaded
// model as ready \u2014 the parent directory exists before the blobs land.
static bool model_is_downloaded(const char *name) {{
    const char *home = getenv("HOME");
    if (!home) return false;
    char snapshots[4096];
    snprintf(snapshots, sizeof(snapshots),
        "%s/.cache/huggingface/hub/models--Systran--faster-whisper-%s/snapshots",
        home, name);
    DIR *d = opendir(snapshots);
    if (!d) return false;
    bool has_entry = false;
    struct dirent *entry;
    while ((entry = readdir(d)) != NULL) {{
        if (strcmp(entry->d_name, ".") == 0) continue;
        if (strcmp(entry->d_name, "..") == 0) continue;
        has_entry = true;
        break;
    }}
    closedir(d);
    return has_entry;
}}

static void download_lock_path(const char *name, char *out, size_t out_len) {{
    const char *home = getenv("HOME");
    if (!home) home = "";
    snprintf(out, out_len, "%s/.config/whispertype/downloading-%s.lock", home, name);
}}

// True if there is a live `download_model.py` helper currently fetching this
// model. The helper writes its PID into the lock file on start and removes
// the lock on exit; we double-check with `kill(pid, 0)` so a stale lock
// from a crashed helper does not block re-downloading.
static bool download_in_progress_for(const char *name) {{
    char path[4096];
    download_lock_path(name, path, sizeof(path));
    FILE *f = fopen(path, "r");
    if (!f) return false;
    char line[32];
    if (fgets(line, sizeof(line), f) == NULL) {{
        fclose(f);
        return false;
    }}
    fclose(f);
    pid_t pid = (pid_t)strtol(line, NULL, 10);
    if (pid <= 0) return false;
    if (kill(pid, 0) == 0) return true;
    if (errno == EPERM) return true;  // exists but we cannot signal it
    return false;
}}

static const char *model_size_label(const char *name) {{
    if (strcmp(name, "tiny") == 0)     return "75 MB";
    if (strcmp(name, "base") == 0)     return "150 MB";
    if (strcmp(name, "small") == 0)    return "480 MB";
    if (strcmp(name, "medium") == 0)   return "1.5 GB";
    if (strcmp(name, "large-v3") == 0) return "3.0 GB";
    return "";
}}

// Fork+exec the Python download helper. Returns the new pid or -1 on error.
// The child inherits the launcher's stdout/stderr (already redirected to
// ~/Library/Logs/WhisperType/launcher.log), and setsid() detaches it from
// the launcher so quitting WhisperType.app does not kill an in-flight
// download.
static int start_model_download(const char *name) {{
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {{
        setsid();
        const char *python = ".venv/bin/python";
        execl(
            python,
            python,
            "-m",
            "app.mac_dictation.download_model",
            "--model",
            name,
            (char *)NULL
        );
        fprintf(stderr, "failed to exec download helper: %s\\n", strerror(errno));
        _exit(127);
    }}
    return (int)pid;
}}

static void write_hotkey_event(const char *event) {{
    if (fn_pipe_write_fd < 0) return;
    char buf[16];
    int n = snprintf(buf, sizeof(buf), "%s\\n", event);
    if (n <= 0) return;
    ssize_t written = write(fn_pipe_write_fd, buf, (size_t)n);
    (void)written;
}}

static void set_hotkey_state(bool down_now) {{
    if (down_now && !hotkey_is_down) {{
        hotkey_is_down = true;
        write_hotkey_event("FN_DOWN");
    }} else if (!down_now && hotkey_is_down) {{
        hotkey_is_down = false;
        write_hotkey_event("FN_UP");
    }}
}}

static uint64_t relevant_modifier_mask(void) {{
    return (uint64_t)(kCGEventFlagMaskCommand
        | kCGEventFlagMaskShift
        | kCGEventFlagMaskControl
        | kCGEventFlagMaskAlternate);
}}

static CGEventRef hotkey_tap_callback(CGEventTapProxy proxy, CGEventType type, CGEventRef event, void *refcon) {{
    (void)proxy; (void)refcon;
    if (type == kCGEventTapDisabledByTimeout || type == kCGEventTapDisabledByUserInput) {{
        if (fn_event_tap) CGEventTapEnable(fn_event_tap, true);
        return event;
    }}
    int64_t keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
    CGEventFlags flags = CGEventGetFlags(event);

    if (current_hotkey.use_fn_flag) {{
        // fn/Globe path: pressed/released as a flagsChanged event with the
        // SecondaryFn flag bit. Some Apple keyboards omit the flag and instead
        // report keycode 63/179 with no flag — toggle in that case.
        if (type == kCGEventFlagsChanged) {{
            bool fn_down_now = (flags & kCGEventFlagMaskSecondaryFn) != 0;
            if (!fn_down_now && (keycode == FN_KEYCODE_PRIMARY || keycode == FN_KEYCODE_GLOBE)) {{
                fn_down_now = !hotkey_is_down;
            }}
            set_hotkey_state(fn_down_now);
        }} else if (type == kCGEventKeyDown) {{
            if (keycode == FN_KEYCODE_PRIMARY || keycode == FN_KEYCODE_GLOBE) {{
                set_hotkey_state(true);
            }}
        }} else if (type == kCGEventKeyUp) {{
            if (keycode == FN_KEYCODE_PRIMARY || keycode == FN_KEYCODE_GLOBE) {{
                set_hotkey_state(false);
            }}
        }}
        return event;
    }}

    // Regular keycode path: optionally with cmd/shift/ctrl/option modifiers.
    if (keycode != current_hotkey.keycode) return event;
    uint64_t mask = relevant_modifier_mask();
    uint64_t actual = (uint64_t)flags & mask;
    uint64_t expected = current_hotkey.modifier_flags & mask;

    if (type == kCGEventKeyDown) {{
        if (actual == expected) set_hotkey_state(true);
    }} else if (type == kCGEventKeyUp) {{
        // On key up the modifier may already be released; accept either.
        set_hotkey_state(false);
    }}
    return event;
}}

static void start_fn_event_tap(void) {{
    CGEventMask mask =
        CGEventMaskBit(kCGEventFlagsChanged)
        | CGEventMaskBit(kCGEventKeyDown)
        | CGEventMaskBit(kCGEventKeyUp);
    fn_event_tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask,
        hotkey_tap_callback,
        NULL
    );
    if (fn_event_tap == NULL) {{
        printf("[WhisperType] launcher could not create CGEventTap; grant Input Monitoring + Accessibility to WhisperType in System Settings > Privacy & Security, then quit and reopen WhisperType.\\n");
        return;
    }}
    CFRunLoopSourceRef source = CFMachPortCreateRunLoopSource(NULL, fn_event_tap, 0);
    CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes);
    CGEventTapEnable(fn_event_tap, true);
    printf("[WhisperType] launcher CGEventTap installed (bundle owns hotkey trust)\\n");
}}

// Forward declaration: pickModel: (defined below) needs to call this
// to swap the Python worker after a model change, but the definition
// lives further down beside start_python_worker.
static int restart_python_worker(void);

@interface WhisperTypeAppDelegate : NSObject <NSApplicationDelegate, NSMenuDelegate>
{{
    NSWindow *captureWindow;
    NSTextField *captureLabel;
    id captureMonitor;
}}
- (void)quitWhisperType:(id)sender;
- (void)setHotkey:(id)sender;
- (void)refreshHotkeyMenuLabel;
- (void)refreshModelMenuLabel;
- (void)pickModel:(id)sender;
- (void)downloadModel:(id)sender;
- (void)rebuildModelSubmenu;
- (void)openAccessibilitySettings:(id)sender;
- (void)openInputMonitoringSettings:(id)sender;
- (void)openMicrophoneSettings:(id)sender;
- (void)resetPermissions:(id)sender;
- (void)pollStatusIndicator:(NSTimer *)timer;
- (void)menuNeedsUpdate:(NSMenu *)menu;
@end

@implementation WhisperTypeAppDelegate

- (void)openAccessibilitySettings:(id)sender {{
    (void)sender;
    NSURL *url = [NSURL URLWithString:@"x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"];
    [[NSWorkspace sharedWorkspace] openURL:url];
}}

- (void)openInputMonitoringSettings:(id)sender {{
    (void)sender;
    NSURL *url = [NSURL URLWithString:@"x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"];
    [[NSWorkspace sharedWorkspace] openURL:url];
}}

- (void)openMicrophoneSettings:(id)sender {{
    (void)sender;
    NSURL *url = [NSURL URLWithString:@"x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"];
    [[NSWorkspace sharedWorkspace] openURL:url];
}}

// Runs `tccutil reset <bucket> <bundleID>` for all three permissions
// WhisperType needs, then opens the three System Settings panes so the
// user can re-grant in one go. This is the post-rebuild ritual: every
// time `whispertype-build-app` produces a fresh binary, macOS treats it
// as a new app (TCC binds grants to the code signature, not the bundle
// ID), so the previous grants stop applying. Clicking this menu item
// wipes the stale records and walks the user through re-granting.
- (void)resetPermissions:(id)sender {{
    (void)sender;
    NSAlert *confirm = [[NSAlert alloc] init];
    [confirm setMessageText:@"Reset WhisperType permissions?"];
    [confirm setInformativeText:@"This clears the macOS records of WhisperType's Microphone, Input Monitoring, and Accessibility grants, then opens each Settings pane so you can re-grant.\\n\\nUse this after rebuilding the app — macOS treats every new build as a different app for permission purposes, so the previous grants stop working.\\n\\nNo personal data is touched."];
    [confirm addButtonWithTitle:@"Reset and Reopen Settings"];
    [confirm addButtonWithTitle:@"Cancel"];
    NSModalResponse pick = [confirm runModal];
    if (pick != NSAlertFirstButtonReturn) {{
        return;
    }}

    const char *buckets[] = {{ "Microphone", "ListenEvent", "Accessibility" }};
    for (int i = 0; i < 3; i++) {{
        pid_t pid = fork();
        if (pid < 0) {{
            printf("[WhisperType] could not fork for tccutil %s: %s\\n", buckets[i], strerror(errno));
            continue;
        }}
        if (pid == 0) {{
            execl("/usr/bin/tccutil", "/usr/bin/tccutil",
                  "reset", buckets[i], "com.mikka.open-transcribe-studio.whispertype",
                  (char *)NULL);
            // execl returns only on failure.
            _exit(127);
        }}
        int status = 0;
        waitpid(pid, &status, 0);
        printf("[WhisperType] tccutil reset %s -> exit %d\\n", buckets[i], WEXITSTATUS(status));
    }}

    [self openMicrophoneSettings:nil];
    [self openInputMonitoringSettings:nil];
    [self openAccessibilitySettings:nil];

    NSAlert *next = [[NSAlert alloc] init];
    [next setMessageText:@"Permissions reset"];
    [next setInformativeText:@"Now toggle WhisperType ON in all three Settings panes: Microphone, Input Monitoring, and Accessibility.\\n\\nIf the Accessibility row still does not work after toggling, click WhisperType in the list and press the minus (–) button to remove it, then drag the .app back in.\\n\\nWhen you are done, quit WhisperType from the menu bar and reopen it from /Applications."];
    [next addButtonWithTitle:@"OK"];
    [next runModal];
}}

- (void)refreshHotkeyMenuLabel {{
    if (hotkeyDisplayItem != nil) {{
        NSString *title = [NSString stringWithFormat:@"Hotkey: %s", current_hotkey.label];
        [hotkeyDisplayItem setTitle:title];
    }}
}}

- (void)refreshModelMenuLabel {{
    if (modelDisplayItem != nil) {{
        NSString *title = [NSString stringWithFormat:@"Model: %s", current_model];
        [modelDisplayItem setTitle:title];
    }}
}}

- (void)pollStatusIndicator:(NSTimer *)timer {{
    (void)timer;
    char next[32] = "idle";
    if (!read_status_from_disk(next, sizeof(next))) {{
        // File missing or empty: treat as idle so the title resets after a
        // crash or before the Python worker has written anything.
        strncpy(next, "idle", sizeof(next) - 1);
    }}
    if (strcmp(next, current_status) == 0) return;
    strncpy(current_status, next, sizeof(current_status) - 1);
    current_status[sizeof(current_status) - 1] = '\\0';
    if (statusItem != nil) {{
        [statusItem.button setTitle:menu_title_for_status(current_status)];
    }}
}}

- (void)pickModel:(id)sender {{
    NSMenuItem *item = (NSMenuItem *)sender;
    NSString *nameAttr = [item representedObject];
    NSString *chosen = (nameAttr != nil) ? nameAttr : [item title];
    const char *cChosen = [chosen UTF8String];
    if (!model_is_valid(cChosen)) {{
        printf("[WhisperType] ignored unknown model from menu: %s\\n", cChosen);
        return;
    }}
    if (strcmp(cChosen, current_model) == 0) {{
        // Already on this model; no point restarting the worker.
        return;
    }}
    save_model_to_disk(cChosen);
    strncpy(current_model, cChosen, sizeof(current_model) - 1);
    current_model[sizeof(current_model) - 1] = '\\0';
    [self refreshModelMenuLabel];

    // Auto-restart the Python worker so the new model takes effect right
    // away. Without this, the menu would lie: it would claim the chosen
    // model is active when the worker still has the old model in RAM.
    int rc = restart_python_worker();
    if (rc != 0) {{
        NSAlert *fail = [[NSAlert alloc] init];
        [fail setMessageText:@"Could not switch model"];
        [fail setInformativeText:@"WhisperType saved your choice but could not restart the dictation worker. Quit and reopen WhisperType from the menu bar to apply the change. See ~/Library/Logs/WhisperType/launcher.log for details."];
        [fail addButtonWithTitle:@"OK"];
        [fail runModal];
        return;
    }}

    NSAlert *alert = [[NSAlert alloc] init];
    [alert setMessageText:[NSString stringWithFormat:@"Switching to %s", cChosen]];
    [alert setInformativeText:@"WhisperType is restarting its transcription worker with the new model. Wait a few seconds for the model to load before your first dictation (longer models like medium or large-v3 can take 10–20 seconds to load into RAM the first time)."];
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
}}

- (void)downloadModel:(id)sender {{
    NSMenuItem *item = (NSMenuItem *)sender;
    NSString *nameObj = [item representedObject];
    if (nameObj == nil) return;
    const char *name = [nameObj UTF8String];
    if (!model_is_valid(name)) {{
        printf("[WhisperType] ignored unknown model from download menu: %s\\n", name);
        return;
    }}
    if (model_is_downloaded(name)) {{
        printf("[WhisperType] %s already on disk, skipping download\\n", name);
        return;
    }}
    if (download_in_progress_for(name)) {{
        printf("[WhisperType] download already in progress for %s\\n", name);
        return;
    }}
    int pid = start_model_download(name);
    if (pid < 0) {{
        NSAlert *fail = [[NSAlert alloc] init];
        [fail setMessageText:@"Could not start download"];
        [fail setInformativeText:@"WhisperType could not launch the download helper. Check ~/Library/Logs/WhisperType/launcher.log for details."];
        [fail addButtonWithTitle:@"OK"];
        [fail runModal];
        return;
    }}
    printf("[WhisperType] download started: model=%s pid=%d\\n", name, pid);

    NSAlert *alert = [[NSAlert alloc] init];
    [alert setMessageText:[NSString stringWithFormat:@"Downloading %s", name]];
    [alert setInformativeText:[NSString stringWithFormat:
        @"%s is downloading in the background (about %s). You can keep using WhisperType with your current model.\\n\\nOpen this menu again later to check — the model will show a checkmark when it is ready.",
        name, model_size_label(name)]];
    [alert addButtonWithTitle:@"OK"];
    [alert runModal];
}}

- (void)rebuildModelSubmenu {{
    if (modelSubmenu == nil) return;
    [modelSubmenu removeAllItems];
    for (int i = 0; i < VALID_MODELS_COUNT; i++) {{
        const char *name = VALID_MODELS[i];
        NSString *nsName = [NSString stringWithUTF8String:name];
        NSMenuItem *item;
        // Order matters: a live download must always win over the
        // "on disk" check. huggingface_hub creates the snapshots dir
        // (which model_is_downloaded looks for) very early in the
        // download, well before the model blobs actually finish. If we
        // trusted model_is_downloaded first, the menu would lie during
        // any in-progress download and let the user pick a model that
        // is not actually ready, with no visible signal that they are
        // mid-download.
        if (download_in_progress_for(name)) {{
            NSString *title = [NSString stringWithFormat:@"%@ — Downloading…", nsName];
            item = [[NSMenuItem alloc] initWithTitle:title action:nil keyEquivalent:@""];
            [item setRepresentedObject:nsName];
            // action:nil + auto-enabling menu = visually disabled
        }} else if (model_is_downloaded(name)) {{
            item = [[NSMenuItem alloc] initWithTitle:nsName action:@selector(pickModel:) keyEquivalent:@""];
            [item setTarget:self];
            [item setRepresentedObject:nsName];
            if (strcmp(name, current_model) == 0) {{
                [item setState:NSControlStateValueOn];
            }}
        }} else {{
            NSString *title = [NSString stringWithFormat:@"%@ — Download (%s)", nsName, model_size_label(name)];
            item = [[NSMenuItem alloc] initWithTitle:title action:@selector(downloadModel:) keyEquivalent:@""];
            [item setTarget:self];
            [item setRepresentedObject:nsName];
        }}
        [modelSubmenu addItem:item];
    }}
}}

- (void)menuNeedsUpdate:(NSMenu *)menu {{
    // Re-stat the HuggingFace cache and the per-model lock files every time
    // the submenu opens, so the user always sees the truth (download done →
    // checkmark appears, download started → "Downloading…" appears) without
    // any background timers or IPC.
    if (menu == modelSubmenu) {{
        [self rebuildModelSubmenu];
    }}
}}

- (void)quitWhisperType:(id)sender {{
    (void)sender;
    if (child_pid > 0) {{
        kill(child_pid, SIGTERM);
    }}
    [NSApp terminate:nil];
}}

- (void)closeCaptureWindow {{
    if (captureMonitor != nil) {{
        [NSEvent removeMonitor:captureMonitor];
        captureMonitor = nil;
    }}
    if (captureWindow != nil) {{
        [captureWindow orderOut:nil];
        [captureWindow close];
        captureWindow = nil;
    }}
    captureLabel = nil;
}}

- (void)setHotkey:(id)sender {{
    (void)sender;
    if (captureWindow != nil) {{
        [captureWindow makeKeyAndOrderFront:nil];
        [NSApp activateIgnoringOtherApps:YES];
        return;
    }}
    NSRect frame = NSMakeRect(0, 0, 460, 180);
    captureWindow = [[NSWindow alloc]
        initWithContentRect:frame
                  styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable)
                    backing:NSBackingStoreBuffered
                      defer:NO];
    [captureWindow setTitle:@"Set WhisperType hotkey"];
    [captureWindow setLevel:NSFloatingWindowLevel];
    [captureWindow center];
    [captureWindow setReleasedWhenClosed:NO];

    captureLabel = [[NSTextField alloc] initWithFrame:NSMakeRect(20, 40, 420, 100)];
    [captureLabel setStringValue:@"Press the key you want to hold to dictate.\\n\\nUse ⌘ ⇧ ⌃ ⌥ as modifiers, fn for the Globe key.\\nPress Esc to cancel."];
    [captureLabel setEditable:NO];
    [captureLabel setBezeled:NO];
    [captureLabel setDrawsBackground:NO];
    [captureLabel setAlignment:NSTextAlignmentCenter];
    [captureLabel setLineBreakMode:NSLineBreakByWordWrapping];
    [[captureWindow contentView] addSubview:captureLabel];

    [captureWindow makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];

    // __block prevents the block from retaining self under MRR; the delegate
    // is owned by NSApp for the app lifetime, so there is no risk of dangling.
    __block WhisperTypeAppDelegate *blockSelf = self;
    captureMonitor = [NSEvent
        addLocalMonitorForEventsMatchingMask:(NSEventMaskKeyDown | NSEventMaskFlagsChanged)
        handler:^NSEvent *(NSEvent *event) {{
            WhisperTypeAppDelegate *strongSelf = blockSelf;
            if (strongSelf == nil) return event;
            unsigned short kc = event.keyCode;
            NSEventModifierFlags mods = event.modifierFlags;

            if (event.type == NSEventTypeKeyDown && kc == ESC_KEYCODE) {{
                [strongSelf closeCaptureWindow];
                return nil;
            }}

            uint64_t cg_flags = 0;
            if (mods & NSEventModifierFlagCommand) cg_flags |= kCGEventFlagMaskCommand;
            if (mods & NSEventModifierFlagShift) cg_flags |= kCGEventFlagMaskShift;
            if (mods & NSEventModifierFlagControl) cg_flags |= kCGEventFlagMaskControl;
            if (mods & NSEventModifierFlagOption) cg_flags |= kCGEventFlagMaskAlternate;

            bool is_fn = (mods & NSEventModifierFlagFunction) != 0
                          || kc == FN_KEYCODE_PRIMARY
                          || kc == FN_KEYCODE_GLOBE;

            if (event.type == NSEventTypeFlagsChanged) {{
                // Only capture fn/Globe from flagsChanged; ignore lone cmd/shift/etc.
                if (!is_fn) return event;
                current_hotkey.keycode = FN_KEYCODE_GLOBE;
                current_hotkey.modifier_flags = 0;
                current_hotkey.use_fn_flag = true;
                strncpy(current_hotkey.label, "fn", sizeof(current_hotkey.label) - 1);
                current_hotkey.label[sizeof(current_hotkey.label) - 1] = '\\0';
            }} else {{
                // KeyDown: real key, with optional modifier chord.
                current_hotkey.keycode = (int64_t)kc;
                current_hotkey.modifier_flags = cg_flags;
                current_hotkey.use_fn_flag = false;
                NSMutableString *lbl = [NSMutableString string];
                if (cg_flags & kCGEventFlagMaskControl) [lbl appendString:@"ctrl+"];
                if (cg_flags & kCGEventFlagMaskAlternate) [lbl appendString:@"opt+"];
                if (cg_flags & kCGEventFlagMaskShift) [lbl appendString:@"shift+"];
                if (cg_flags & kCGEventFlagMaskCommand) [lbl appendString:@"cmd+"];
                NSString *chars = [event charactersIgnoringModifiers];
                if (chars != nil && [chars length] > 0 && [chars characterAtIndex:0] >= 0x20 && [chars characterAtIndex:0] < 0x7F) {{
                    [lbl appendString:[chars lowercaseString]];
                }} else {{
                    [lbl appendFormat:@"key%d", (int)kc];
                }}
                const char *lblC = [lbl UTF8String];
                strncpy(current_hotkey.label, lblC, sizeof(current_hotkey.label) - 1);
                current_hotkey.label[sizeof(current_hotkey.label) - 1] = '\\0';
            }}

            save_hotkey_config_to_disk();
            [strongSelf refreshHotkeyMenuLabel];
            // The match callback uses current_hotkey on its next event, so the
            // change takes effect immediately without restarting the worker.
            set_hotkey_state(false);  // clear any stuck "down" state from the old hotkey
            [strongSelf closeCaptureWindow];
            return nil;
        }}];
}}
@end

static void ensure_log_dir(void) {{
    const char *home = getenv("HOME");
    if (!home) return;
    char library[4096];
    char logs[4096];
    char app_logs[4096];
    snprintf(library, sizeof(library), "%s/Library", home);
    snprintf(logs, sizeof(logs), "%s/Library/Logs", home);
    snprintf(app_logs, sizeof(app_logs), "%s/Library/Logs/WhisperType", home);
    mkdir(library, 0755);
    mkdir(logs, 0755);
    mkdir(app_logs, 0755);
}}

static void open_log(void) {{
    ensure_log_dir();
    const char *home = getenv("HOME");
    if (!home) return;
    char log_path[4096];
    snprintf(log_path, sizeof(log_path), "%s/Library/Logs/WhisperType/launcher.log", home);
    freopen(log_path, "a", stdout);
    freopen(log_path, "a", stderr);
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
}}

static int start_python_worker(const char *repo) {{
    const char *python = ".venv/bin/python";
    if (access(python, X_OK) != 0) {{
        fprintf(stderr, "missing executable .venv/bin/python in %s\\n", repo);
        return 1;
    }}

    int fn_pipe[2];
    if (pipe(fn_pipe) != 0) {{
        fprintf(stderr, "failed to create fn pipe: %s\\n", strerror(errno));
        return 1;
    }}

    child_pid = fork();
    if (child_pid < 0) {{
        fprintf(stderr, "failed to fork Python worker: %s\\n", strerror(errno));
        close(fn_pipe[0]);
        close(fn_pipe[1]);
        return 1;
    }}
    if (child_pid == 0) {{
        close(fn_pipe[1]);
        if (dup2(fn_pipe[0], STDIN_FILENO) < 0) {{
            fprintf(stderr, "failed to attach fn pipe to stdin: %s\\n", strerror(errno));
            _exit(1);
        }}
        close(fn_pipe[0]);

        char virtual_env[4096];
        char path_env[8192];
        const char *old_path = getenv("PATH");
        snprintf(virtual_env, sizeof(virtual_env), "%s/.venv", repo);
        setenv("VIRTUAL_ENV", virtual_env, 1);
        snprintf(path_env, sizeof(path_env), "%s/.venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:%s", repo, old_path ? old_path : "");
        setenv("PATH", path_env, 1);
        setenv("PYTHONUNBUFFERED", "1", 1);

        execl(
            python,
            python,
            "-m",
            "app.mac_dictation.cli",
            "--model",
            current_model,
            "--hold-key",
            "{hold_key_c}",
            "--language",
            "{language_c}",
            "--native-worker",
            (char *)NULL
        );
        fprintf(stderr, "failed to exec %s: %s\\n", python, strerror(errno));
        _exit(1);
    }}
    close(fn_pipe[0]);
    fn_pipe_write_fd = fn_pipe[1];
    int existing = fcntl(fn_pipe_write_fd, F_GETFD);
    if (existing >= 0) fcntl(fn_pipe_write_fd, F_SETFD, existing | FD_CLOEXEC);
    printf("[WhisperType] Python worker started: %d\\n", child_pid);
    return 0;
}}

// Kill the current Python worker, reap it, then fork a fresh one. Used after
// the user picks a new model so the change takes effect immediately without
// the user having to quit and reopen WhisperType. The launcher itself stays
// alive — only the child Python process holding the Whisper model in RAM
// gets restarted.
static int restart_python_worker(void) {{
    if (child_pid > 0) {{
        printf("[WhisperType] restarting Python worker (was pid %d)\\n", child_pid);
        kill(child_pid, SIGTERM);
        int status = 0;
        bool reaped = false;
        // Give the child up to ~3 seconds to exit gracefully.
        for (int i = 0; i < 30; i++) {{
            pid_t result = waitpid(child_pid, &status, WNOHANG);
            if (result == child_pid) {{ reaped = true; break; }}
            if (result < 0 && errno == ECHILD) {{ reaped = true; break; }}
            usleep(100000);  // 100ms
        }}
        if (!reaped) {{
            printf("[WhisperType] worker did not exit on SIGTERM, sending SIGKILL\\n");
            kill(child_pid, SIGKILL);
            waitpid(child_pid, &status, 0);
        }}
        child_pid = -1;
    }}
    if (fn_pipe_write_fd >= 0) {{
        close(fn_pipe_write_fd);
        fn_pipe_write_fd = -1;
    }}
    // The old worker is gone, so any in-flight FN_DOWN had no consumer.
    // Clear our local state so the new worker doesn't start out thinking
    // the hotkey is held.
    hotkey_is_down = false;
    return start_python_worker(kRepoDir);
}}

int main(int argc, char **argv) {{
    (void)argc;
    (void)argv;
    open_log();
    printf("--- WhisperType native launch ---\\n");
    if (chdir(kRepoDir) != 0) {{
        fprintf(stderr, "repo path does not exist or cannot be opened: %s: %s\\n", kRepoDir, strerror(errno));
        return 1;
    }}
    printf("repo: %s\\n", kRepoDir);

    @autoreleasepool {{
        NSApplication *app = [NSApplication sharedApplication];
        WhisperTypeAppDelegate *delegate = [[WhisperTypeAppDelegate alloc] init];
        [app setDelegate:delegate];
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];

        statusItem = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
        [statusItem.button setTitle:@"WT"];
        [statusItem.button setToolTip:@"WhisperType is running — hold fn to dictate"];

        load_hotkey_config_from_disk();
        load_model_from_disk();

        NSMenu *menu = [[NSMenu alloc] init];
        [menu addItemWithTitle:@"WhisperType running — hold hotkey to dictate" action:nil keyEquivalent:@""];
        NSString *hotkeyTitle = [NSString stringWithFormat:@"Hotkey: %s", current_hotkey.label];
        hotkeyDisplayItem = [[NSMenuItem alloc] initWithTitle:hotkeyTitle action:nil keyEquivalent:@""];
        [menu addItem:hotkeyDisplayItem];
        NSString *modelTitle = [NSString stringWithFormat:@"Model: %s", current_model];
        modelDisplayItem = [[NSMenuItem alloc] initWithTitle:modelTitle action:nil keyEquivalent:@""];
        [menu addItem:modelDisplayItem];
        [menu addItem:[NSMenuItem separatorItem]];
        NSMenuItem *setHotkeyItem = [[NSMenuItem alloc] initWithTitle:@"Set hotkey…" action:@selector(setHotkey:) keyEquivalent:@""];
        [setHotkeyItem setTarget:delegate];
        [menu addItem:setHotkeyItem];

        NSMenuItem *modelItem = [[NSMenuItem alloc] initWithTitle:@"Model" action:nil keyEquivalent:@""];
        modelSubmenu = [[NSMenu alloc] initWithTitle:@"Model"];
        // Setting the delegate makes menuNeedsUpdate: fire each time the user
        // opens the submenu, so we re-stat the HF cache and lock files and
        // rebuild the items reflecting fresh on-disk state.
        [modelSubmenu setDelegate:delegate];
        [delegate rebuildModelSubmenu];
        [modelItem setSubmenu:modelSubmenu];
        [menu addItem:modelItem];
        NSMenuItem *micItem = [[NSMenuItem alloc] initWithTitle:@"Open Microphone Settings" action:@selector(openMicrophoneSettings:) keyEquivalent:@""];
        [micItem setTarget:delegate];
        [menu addItem:micItem];
        NSMenuItem *settingsItem = [[NSMenuItem alloc] initWithTitle:@"Open Accessibility Settings" action:@selector(openAccessibilitySettings:) keyEquivalent:@""];
        [settingsItem setTarget:delegate];
        [menu addItem:settingsItem];
        NSMenuItem *inputMonItem = [[NSMenuItem alloc] initWithTitle:@"Open Input Monitoring Settings" action:@selector(openInputMonitoringSettings:) keyEquivalent:@""];
        [inputMonItem setTarget:delegate];
        [menu addItem:inputMonItem];
        NSMenuItem *resetItem = [[NSMenuItem alloc] initWithTitle:@"Reset Permissions…" action:@selector(resetPermissions:) keyEquivalent:@""];
        [resetItem setTarget:delegate];
        [menu addItem:resetItem];
        [menu addItem:[NSMenuItem separatorItem]];
        NSMenuItem *quitItem = [[NSMenuItem alloc] initWithTitle:@"Quit WhisperType" action:@selector(quitWhisperType:) keyEquivalent:@"q"];
        [quitItem setTarget:delegate];
        [menu addItem:quitItem];
        [statusItem setMenu:menu];
        printf("[WhisperType] native menu bar item ready: WT\\n");

        if (start_python_worker(kRepoDir) != 0) {{
            return 1;
        }}
        start_fn_event_tap();
        [NSTimer scheduledTimerWithTimeInterval:0.25
                                         target:delegate
                                       selector:@selector(pollStatusIndicator:)
                                       userInfo:nil
                                        repeats:YES];
        [app run];
    }}
    return 0;
}}
'''


def _write_info_plist(contents: Path) -> None:
    info = {
        "CFBundleName": "WhisperType",
        "CFBundleDisplayName": "WhisperType",
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleVersion": BUNDLE_VERSION,
        "CFBundleShortVersionString": BUNDLE_VERSION,
        "CFBundleExecutable": "WhisperType",
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "WhisperType records while you hold fn so it can transcribe speech locally.",
        "NSAppleEventsUsageDescription": "WhisperType may use local automation only to show setup alerts.",
        "NSInputMonitoringUsageDescription": "WhisperType watches the fn/Globe key so you can hold it to dictate.",
    }
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(info, handle)


def _prepare_bundle_dirs(app_path: Path) -> tuple[Path, Path, Path]:
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)
    _write_info_plist(contents)
    return contents, macos_dir, resources_dir


def _ad_hoc_codesign(app_path: Path) -> None:
    if platform.system() != "Darwin" or not shutil.which("codesign"):
        return
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
        check=True,
    )


def _write_native_launcher_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    _, macos_dir, resources_dir = _prepare_bundle_dirs(app_path)
    source = render_native_launcher_source(
        repo_dir=repo_dir,
        model=model,
        hold_key=hold_key,
        language=language,
    )
    source_path = resources_dir / "WhisperTypeLauncher.m"
    source_path.write_text(source)
    executable = macos_dir / "WhisperType"
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        raise RuntimeError(
            "Building the portfolio-grade macOS app requires clang. Install Apple Command Line Tools with: xcode-select --install"
        )
    subprocess.run(
        [
            clang,
            str(source_path),
            "-framework", "Cocoa",
            "-framework", "CoreGraphics",
            "-framework", "ApplicationServices",
            "-o", str(executable),
        ],
        check=True,
    )
    executable.chmod(executable.stat().st_mode | 0o755)
    _ad_hoc_codesign(app_path)
    return app_path


def _write_fallback_shell_app(
    app_path: Path,
    repo_dir: Path,
    model: str,
    hold_key: str,
    language: str,
) -> Path:
    _, macos_dir, _ = _prepare_bundle_dirs(app_path)
    launcher = macos_dir / "WhisperType"
    launcher.write_text(
        render_launcher_script(repo_dir=repo_dir, model=model, hold_key=hold_key, language=language)
    )
    launcher.chmod(launcher.stat().st_mode | 0o755)
    return app_path


def build_app_bundle(
    output_dir: Path,
    repo_dir: Path,
    model: str = "base",
    hold_key: str = "fn",
    language: str = "en",
) -> Path:
    """Create a macOS app bundle that starts WhisperType without Terminal."""
    output_dir.mkdir(parents=True, exist_ok=True)
    app_path = output_dir / "WhisperType.app"
    if app_path.exists():
        shutil.rmtree(app_path)

    if platform.system() == "Darwin":
        return _write_native_launcher_app(
            app_path=app_path,
            repo_dir=repo_dir,
            model=model,
            hold_key=hold_key,
            language=language,
        )

    return _write_fallback_shell_app(
        app_path=app_path,
        repo_dir=repo_dir,
        model=model,
        hold_key=hold_key,
        language=language,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a local WhisperType.app launcher")
    parser.add_argument("--output-dir", default="dist", help="Directory where WhisperType.app is written")
    parser.add_argument("--repo-dir", default=".", help="Path to this repository on your Mac")
    parser.add_argument("--model", default="base", help="Whisper model used by the app. Default: base for better dictation accuracy.")
    parser.add_argument("--hold-key", default="fn", help="Hold key used by the app")
    parser.add_argument("--language", default="en", help="Language code, or auto for detection")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    repo_dir = Path(args.repo_dir).expanduser().resolve()
    app_path = build_app_bundle(
        output_dir=output_dir,
        repo_dir=repo_dir,
        model=args.model,
        hold_key=args.hold_key,
        language=args.language,
    )
    print(f"Built {app_path}")


if __name__ == "__main__":
    main()
