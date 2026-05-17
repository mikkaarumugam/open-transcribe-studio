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

@interface WhisperTypeAppDelegate : NSObject <NSApplicationDelegate>
{{
    NSWindow *captureWindow;
    NSTextField *captureLabel;
    id captureMonitor;
}}
- (void)quitWhisperType:(id)sender;
- (void)setHotkey:(id)sender;
- (void)refreshHotkeyMenuLabel;
- (void)openAccessibilitySettings:(id)sender;
@end

@implementation WhisperTypeAppDelegate

- (void)openAccessibilitySettings:(id)sender {{
    (void)sender;
    NSURL *url = [NSURL URLWithString:@"x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"];
    [[NSWorkspace sharedWorkspace] openURL:url];
}}

- (void)refreshHotkeyMenuLabel {{
    if (hotkeyDisplayItem != nil) {{
        NSString *title = [NSString stringWithFormat:@"Hotkey: %s", current_hotkey.label];
        [hotkeyDisplayItem setTitle:title];
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
            "{model_c}",
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

int main(int argc, char **argv) {{
    (void)argc;
    (void)argv;
    open_log();
    printf("--- WhisperType native launch ---\\n");
    const char *repo = "{repo}";
    if (chdir(repo) != 0) {{
        fprintf(stderr, "repo path does not exist or cannot be opened: %s: %s\\n", repo, strerror(errno));
        return 1;
    }}
    printf("repo: %s\\n", repo);

    @autoreleasepool {{
        NSApplication *app = [NSApplication sharedApplication];
        WhisperTypeAppDelegate *delegate = [[WhisperTypeAppDelegate alloc] init];
        [app setDelegate:delegate];
        [app setActivationPolicy:NSApplicationActivationPolicyAccessory];

        statusItem = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
        [statusItem.button setTitle:@"WT"];
        [statusItem.button setToolTip:@"WhisperType is running — hold fn to dictate"];

        load_hotkey_config_from_disk();

        NSMenu *menu = [[NSMenu alloc] init];
        [menu addItemWithTitle:@"WhisperType running — hold hotkey to dictate" action:nil keyEquivalent:@""];
        NSString *hotkeyTitle = [NSString stringWithFormat:@"Hotkey: %s", current_hotkey.label];
        hotkeyDisplayItem = [[NSMenuItem alloc] initWithTitle:hotkeyTitle action:nil keyEquivalent:@""];
        [menu addItem:hotkeyDisplayItem];
        [menu addItem:[NSMenuItem separatorItem]];
        NSMenuItem *setHotkeyItem = [[NSMenuItem alloc] initWithTitle:@"Set hotkey…" action:@selector(setHotkey:) keyEquivalent:@""];
        [setHotkeyItem setTarget:delegate];
        [menu addItem:setHotkeyItem];
        NSMenuItem *settingsItem = [[NSMenuItem alloc] initWithTitle:@"Open Accessibility Settings" action:@selector(openAccessibilitySettings:) keyEquivalent:@""];
        [settingsItem setTarget:delegate];
        [menu addItem:settingsItem];
        [menu addItem:[NSMenuItem separatorItem]];
        NSMenuItem *quitItem = [[NSMenuItem alloc] initWithTitle:@"Quit WhisperType" action:@selector(quitWhisperType:) keyEquivalent:@"q"];
        [quitItem setTarget:delegate];
        [menu addItem:quitItem];
        [statusItem setMenu:menu];
        printf("[WhisperType] native menu bar item ready: WT\\n");

        if (start_python_worker(repo) != 0) {{
            return 1;
        }}
        start_fn_event_tap();
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
