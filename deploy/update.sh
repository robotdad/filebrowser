#!/bin/bash
set -euo pipefail

cat <<'EOF'
=== File Browser Update (DEPRECATED) ===

This legacy updater is deprecated. If you installed via uv tool, use:

    filebrowser upgrade

To continue with the legacy update, press Enter.
To abort, press Ctrl+C.
EOF
read -r

echo "=== File Browser Update ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/filebrowser"

if [ ! -d "$INSTALL_DIR/.venv" ]; then
    echo "ERROR: $INSTALL_DIR not found. Run deploy/install.sh first."
    exit 1
fi

echo "Syncing code to $INSTALL_DIR..."
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
    "$PROJECT_DIR/" "$INSTALL_DIR/"

echo "Reinstalling package..."
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade "$INSTALL_DIR"

echo "Restarting service..."
systemctl restart filebrowser
systemctl status filebrowser --no-pager -l

echo ""
echo "=== Update complete ==="
