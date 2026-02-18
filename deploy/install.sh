#!/bin/bash
set -euo pipefail

echo "=== File Browser Installer ==="

# --- Detect environment ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
USER="$(whoami)"
INSTALL_DIR="/opt/filebrowser"
CERT_DIR="/etc/ssl/tailscale"

# --- Detect Tailscale FQDN ---
echo "Detecting Tailscale FQDN..."
FQDN=$(tailscale status --json | python3 -c "import sys, json; print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")
echo "  FQDN: $FQDN"

CERT_PATH="$CERT_DIR/$FQDN.crt"
KEY_PATH="$CERT_DIR/$FQDN.key"

# --- Generate secret key (only if not already set) ---
SECRET_FILE="$INSTALL_DIR/.secret_key"
if [ -f "$SECRET_FILE" ]; then
    SECRET_KEY=$(cat "$SECRET_FILE")
    echo "  Using existing secret key"
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "  Generated new secret key"
fi

# --- Ensure PAM access ---
echo "Ensuring PAM access (shadow group)..."
if ! groups "$USER" | grep -q '\bshadow\b'; then
    sudo usermod -aG shadow "$USER"
    echo "  Added $USER to shadow group"
else
    echo "  $USER already in shadow group"
fi

# --- Install application ---
echo "Installing application to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER:$USER" "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' "$PROJECT_DIR/" "$INSTALL_DIR/"

# Save secret key
echo "$SECRET_KEY" > "$SECRET_FILE"
chmod 600 "$SECRET_FILE"

# --- Create venv and install ---
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

# --- Generate Tailscale cert ---
echo "Generating Tailscale certificate..."
sudo mkdir -p "$CERT_DIR"
sudo tailscale cert --cert-file "$CERT_PATH" --key-file "$KEY_PATH" "$FQDN"

# --- Install Caddy ---
if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    sudo apt-get update -qq && sudo apt-get install -y -qq caddy
else
    echo "Caddy already installed"
fi

# --- Write config files from templates ---
echo "Writing configuration files..."

sudo sed \
    -e "s|FILEBROWSER_FQDN|$FQDN|g" \
    -e "s|CERT_PATH|$CERT_PATH|g" \
    -e "s|KEY_PATH|$KEY_PATH|g" \
    "$INSTALL_DIR/deploy/Caddyfile.template" \
    | sudo tee /etc/caddy/Caddyfile > /dev/null

sudo sed \
    -e "s|FILEBROWSER_USER|$USER|g" \
    -e "s|FILEBROWSER_DIR|$INSTALL_DIR|g" \
    -e "s|FILEBROWSER_SECRET|$SECRET_KEY|g" \
    "$INSTALL_DIR/deploy/filebrowser.service" \
    | sudo tee /etc/systemd/system/filebrowser.service > /dev/null

sudo sed \
    -e "s|CERT_PATH|$CERT_PATH|g" \
    -e "s|KEY_PATH|$KEY_PATH|g" \
    -e "s|FILEBROWSER_FQDN|$FQDN|g" \
    "$INSTALL_DIR/deploy/tailscale-cert-renew.service" \
    | sudo tee /etc/systemd/system/tailscale-cert-renew.service > /dev/null

sudo cp "$INSTALL_DIR/deploy/tailscale-cert-renew.timer" \
    /etc/systemd/system/tailscale-cert-renew.timer

# --- Enable and start services ---
echo "Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable --now filebrowser
sudo systemctl enable --now caddy
sudo systemctl enable --now tailscale-cert-renew.timer

echo ""
echo "=== Installation complete ==="
echo "File Browser is running at: https://$FQDN"
echo ""
echo "To check status:"
echo "  sudo systemctl status filebrowser"
echo "  sudo systemctl status caddy"
