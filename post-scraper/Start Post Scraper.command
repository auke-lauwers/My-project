#!/bin/bash
# Double-click to start Post Scraper on a Mac.
#
# First run: sets up Python packages and a private Chromium (a few minutes).
# Every run: starts the dashboard and opens it in your browser.
# Closing this Terminal window stops the dashboard.
#
# Your posts, accounts, settings and LinkedIn session are kept in
# ~/Library/Application Support/Post Scraper, so they survive downloading a
# newer version of this folder.

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$HOME/Library/Application Support/Post Scraper"
VENV="$DATA_DIR/.venv"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
fail() {
  printf "\n\033[31m%s\033[0m\n\n" "$1"
  read -r -p "Press Enter to close this window."
  exit 1
}

# Already running (from an earlier double-click)? Just open it.
for port in $(seq 8080 8090); do
  if curl -s --max-time 1 "http://127.0.0.1:$port/api/status" | grep -q scraped_accounts; then
    bold "Post Scraper is already running. Opening it."
    open "http://127.0.0.1:$port"
    exit 0
  fi
done

# Python 3.9 or newer. Plain macOS has a python3 that offers to install
# Apple's developer tools the first time it is used.
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PY" ]; then
  fail "Python isn't installed yet.
If a window popped up offering to install developer tools, click Install,
wait for it to finish, then double-click this file again.
Otherwise install Python from https://www.python.org/downloads/ and try again."
fi

mkdir -p "$DATA_DIR" || fail "Couldn't create $DATA_DIR"

# Python packages, in a private environment. Reinstalled when requirements change.
if [ ! -x "$VENV/bin/python" ]; then
  bold "First-time setup: creating a Python environment..."
  "$PY" -m venv "$VENV" || fail "Couldn't create the Python environment."
fi
REQ_HASH="$(shasum "$APP_DIR/requirements.txt" | cut -d' ' -f1)"
if [ "$(cat "$VENV/.requirements-hash" 2>/dev/null)" != "$REQ_HASH" ]; then
  bold "Installing packages (needs internet, about a minute)..."
  "$VENV/bin/python" -m pip install --quiet --upgrade pip &&
  "$VENV/bin/python" -m pip install --quiet -r "$APP_DIR/requirements.txt" ||
    fail "Package install failed. Check your internet connection and try again."
  echo "$REQ_HASH" > "$VENV/.requirements-hash"
  rm -f "$VENV/.chromium-installed"
fi
if [ ! -f "$VENV/.chromium-installed" ]; then
  bold "Downloading the browser the scraper uses (about 150 MB, one time)..."
  "$VENV/bin/python" -m playwright install chromium ||
    fail "Browser download failed. Check your internet connection and try again."
  touch "$VENV/.chromium-installed"
fi

# Starter account list on first run.
[ -f "$DATA_DIR/accounts.txt" ] || cp "$APP_DIR/accounts.txt" "$DATA_DIR/accounts.txt"

# First free port from 8080.
PORT=""
for port in $(seq 8080 8090); do
  if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then PORT=$port; break; fi
done
[ -n "$PORT" ] || fail "Ports 8080-8090 are all in use. Close some apps and try again."
URL="http://127.0.0.1:$PORT"

bold "Starting Post Scraper..."
cd "$DATA_DIR" || fail "Couldn't open $DATA_DIR"
PYTHONPATH="$APP_DIR" "$VENV/bin/python" -m postscraper serve --port "$PORT" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT INT TERM HUP

for _ in $(seq 1 40); do
  curl -s --max-time 1 -o /dev/null "$URL/api/status" && break
  kill -0 $SERVER 2>/dev/null || fail "The dashboard stopped while starting. See the messages above."
  sleep 0.25
done
open "$URL"

bold "Post Scraper is running at $URL"
echo "Your data is in: $DATA_DIR"
echo "Keep this window open while you use it. Close it (or press Ctrl+C) to stop."
wait $SERVER
