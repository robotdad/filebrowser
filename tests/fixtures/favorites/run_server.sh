#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_DIR"

export HOME="$REPO_DIR/.work/test-home"
export FILEBROWSER_DATA_DIR="$REPO_DIR/.work/test-data"
export FILEBROWSER_SECRET_KEY="fixture-only-dummy-signing-secret"
export FILEBROWSER_TERMINAL_ENABLED="false"
export FILEBROWSER_SECURE_COOKIES="false"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$REPO_DIR${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
FILEBROWSER_TEST_PORT="${FILEBROWSER_TEST_PORT:-58180}"

exec "$PYTHON_BIN" -m tests.fixtures.favorites.fixture_app \
  --host 127.0.0.1 \
  --port "$FILEBROWSER_TEST_PORT"
