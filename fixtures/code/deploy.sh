#!/usr/bin/env bash
# deploy.sh — Bash fixture for CodeMirror syntax highlighting test.
# Note: .sh files have no CodeMirror language highlight in this app —
# they fall through the backend content-sniff path to the plain-text
# code editor. Open Source tab to verify plain highlighting applies.
#
# Exercises: shebang, set flags, functions, loops, arrays, conditionals,
# here-doc, parameter expansion, trap, tee.

set -euo pipefail

# ---- Configuration ----
APP_NAME="${APP_NAME:-filebrowser}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/${APP_NAME}}"
VENV_DIR="${DEPLOY_DIR}/.venv"
PORT="${PORT:-58080}"
LOG_FILE="/var/log/${APP_NAME}.log"
SYSTEMD_UNIT="/etc/systemd/system/${APP_NAME}.service"

# ---- Helpers ----

log() {
  local level="$1"; shift
  printf "[%s] [%s] %s\n" "$(date -Iseconds)" "${level}" "$*" | tee -a "${LOG_FILE}"
}

info()  { log "INFO"  "$@"; }
warn()  { log "WARN"  "$@"; }
error() { log "ERROR" "$@"; }

require_cmd() {
  local cmd
  for cmd in "$@"; do
    if ! command -v "${cmd}" &>/dev/null; then
      error "Required command not found: ${cmd}"
      exit 1
    fi
  done
}

# ---- Steps ----

check_prerequisites() {
  info "Checking prerequisites..."
  require_cmd python3 pip git systemctl
  if [[ "$(python3 --version 2>&1)" < "Python 3.11" ]]; then
    error "Python 3.11+ required"
    exit 1
  fi
  info "Prerequisites OK"
}

install_app() {
  info "Installing ${APP_NAME} to ${DEPLOY_DIR}..."
  mkdir -p "${DEPLOY_DIR}"

  python3 -m venv "${VENV_DIR}"
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"

  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt

  info "Install complete"
}

write_systemd_unit() {
  info "Writing systemd unit to ${SYSTEMD_UNIT}..."
  cat > "${SYSTEMD_UNIT}" <<EOF
[Unit]
Description=${APP_NAME} web file browser
After=network.target

[Service]
Type=simple
WorkingDirectory=${DEPLOY_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn filebrowser.main:app --host 127.0.0.1 --port ${PORT}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
}

reload_and_start() {
  info "Enabling and starting service..."
  systemctl daemon-reload
  systemctl enable --now "${APP_NAME}.service"
  systemctl is-active "${APP_NAME}.service" && info "Service is running" || {
    error "Service failed to start"; journalctl -u "${APP_NAME}.service" -n 20; exit 1
  }
}

# ---- Cleanup on failure ----

cleanup() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    warn "Deploy failed (exit ${rc}) — check ${LOG_FILE}"
  fi
}
trap cleanup EXIT

# ---- Main ----

main() {
  local steps=("check_prerequisites" "install_app" "write_systemd_unit" "reload_and_start")
  for step in "${steps[@]}"; do
    info "--- Step: ${step} ---"
    "${step}"
  done
  info "Deployment of ${APP_NAME} complete on port ${PORT}"
}

main "$@"
