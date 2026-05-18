#!/usr/bin/env bash
#
# WhisperType one-line installer.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mikkaarumugam/whispertype/main/scripts/install.sh | bash
#
# Or, if you want to read it before running it:
#   curl -fsSL https://raw.githubusercontent.com/mikkaarumugam/whispertype/main/scripts/install.sh -o install.sh
#   cat install.sh
#   bash install.sh
#
# This script:
#   1. Verifies you are on macOS with git, python3, and clang available.
#   2. Clones (or updates) the WhisperType repo at ~/whispertype.
#   3. Creates a Python virtual environment and installs the package.
#   4. Builds the macOS .app bundle and copies it to /Applications.
#   5. Opens the app and tells you what to do next for permissions.
#
# It will NOT auto-install Homebrew, Xcode Command Line Tools, or Python for you.
# Running install scripts that mutate your system globally is bad form; if you
# are missing one of those, the script tells you the single command to run.
#
set -euo pipefail

REPO_URL="https://github.com/mikkaarumugam/whispertype.git"
INSTALL_DIR="${WHISPERTYPE_DIR:-$HOME/whispertype}"
APP_NAME="WhisperType.app"

# --- Pretty printing -----------------------------------------------------

if [ -t 1 ] && command -v tput >/dev/null 2>&1; then
    BOLD="$(tput bold)"
    GREEN="$(tput setaf 2)"
    YELLOW="$(tput setaf 3)"
    RED="$(tput setaf 1)"
    RESET="$(tput sgr0)"
else
    BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

step()    { echo "${BOLD}${GREEN}==>${RESET} $*"; }
warn()    { echo "${BOLD}${YELLOW}!! ${RESET} $*"; }
die()     { echo "${BOLD}${RED}xx ${RESET} $*" >&2; exit 1; }

# --- Prerequisite checks -------------------------------------------------

step "WhisperType installer starting"

if [ "$(uname -s)" != "Darwin" ]; then
    die "WhisperType is macOS-only. Detected $(uname -s)."
fi

if ! command -v git >/dev/null 2>&1; then
    die "git is not installed. Run: xcode-select --install"
fi

if ! command -v python3 >/dev/null 2>&1; then
    die "python3 is not installed. Easiest fix: brew install python@3.13"
fi

# Verify Python is 3.10-3.13 (pyproject.toml constraint).
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PY_MAJOR="${PY_VER%.*}"
PY_MINOR="${PY_VER#*.}"
if [ "$PY_MAJOR" -ne 3 ] || [ "$PY_MINOR" -lt 10 ] || [ "$PY_MINOR" -gt 13 ]; then
    die "Python $PY_VER detected. WhisperType needs Python 3.10-3.13. Install with: brew install python@3.13"
fi
step "Using Python $PY_VER ($(command -v python3))"

if ! command -v clang >/dev/null 2>&1; then
    die "clang is not installed. The .app bundle uses a small native Obj-C launcher. Run: xcode-select --install"
fi

# --- Clone or update the repo -------------------------------------------

if [ -d "$INSTALL_DIR/.git" ]; then
    step "Existing checkout at $INSTALL_DIR — pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only
elif [ -e "$INSTALL_DIR" ]; then
    die "$INSTALL_DIR exists but is not a git checkout. Move or delete it, then re-run."
else
    step "Cloning $REPO_URL into $INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- Set up the Python virtual environment -------------------------------

if [ ! -d ".venv" ]; then
    step "Creating Python virtual environment in .venv/"
    python3 -m venv .venv
else
    step "Reusing existing .venv/"
fi

# Use the venv's pip / python directly; don't rely on `source activate`.
VENV_PY=".venv/bin/python"
VENV_PIP=".venv/bin/pip"

step "Upgrading pip in the venv"
"$VENV_PY" -m pip install --upgrade pip >/dev/null

step "Installing WhisperType and its dependencies"
if ! "$VENV_PIP" install -e . ; then
    warn "Install failed. If it complained about sounddevice / PortAudio, run:"
    warn "    brew install portaudio"
    warn "    cd $INSTALL_DIR && .venv/bin/pip install -e ."
    die "Aborting."
fi

# --- Build the .app bundle ----------------------------------------------

step "Building WhisperType.app"
.venv/bin/whispertype-build-app --repo-dir "$INSTALL_DIR" --output-dir dist

if [ ! -d "dist/$APP_NAME" ]; then
    die "Build did not produce dist/$APP_NAME. See output above."
fi

# --- Install to /Applications -------------------------------------------

step "Installing to /Applications (you may be prompted for your password)"
if [ -d "/Applications/$APP_NAME" ]; then
    # Remove the previous install so cp doesn't merge directories.
    if [ -w "/Applications/$APP_NAME" ]; then
        rm -rf "/Applications/$APP_NAME"
    else
        sudo rm -rf "/Applications/$APP_NAME"
    fi
fi
if [ -w "/Applications" ]; then
    cp -R "dist/$APP_NAME" "/Applications/$APP_NAME"
else
    sudo cp -R "dist/$APP_NAME" "/Applications/$APP_NAME"
fi

# Clean up the dist/ copy so Spotlight doesn't index two WhisperType.apps.
rm -rf "dist/$APP_NAME"

# --- Launch and print next steps ----------------------------------------

step "Opening WhisperType"
open "/Applications/$APP_NAME"

cat <<EOF

${BOLD}${GREEN}WhisperType is installed.${RESET}

You should see a ${BOLD}WT${RESET} item in your menu bar (top-right of your screen).

${BOLD}Grant permissions (one time):${RESET}
  1. Click ${BOLD}WT${RESET} → ${BOLD}Reset Permissions…${RESET}
  2. Drag ${BOLD}/Applications/$APP_NAME${RESET} into the Accessibility list that opens, toggle ON.
  3. Click ${BOLD}WT${RESET} → ${BOLD}Open Input Monitoring Settings${RESET}, toggle WhisperType ON.
  4. Click ${BOLD}WT${RESET} → ${BOLD}Quit WhisperType${RESET}, then reopen from /Applications.
  5. Hold ${BOLD}fn${RESET} once — macOS prompts for Microphone access. Click Allow.

After that: click into any app, hold ${BOLD}fn${RESET}, speak, release. Your transcribed text appears.

${BOLD}Source:${RESET} $INSTALL_DIR
${BOLD}Logs:${RESET}   tail -80 ~/Library/Logs/WhisperType/launcher.log

EOF
