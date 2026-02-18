#!/bin/bash
set -euo pipefail

echo "=== File Browser Installer ==="

# --- Detect environment ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# When run via sudo, whoami returns root. Use SUDO_USER to get the real user.
USER="${SUDO_USER:-$(whoami)}"
INSTALL_DIR="/opt/filebrowser"
CERT_DIR="/etc/ssl/tailscale"
HTTPS=false

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
    usermod -aG shadow "$USER"
    echo "  Added $USER to shadow group"
else
    echo "  $USER already in shadow group"
fi

# --- Install application ---
echo "Installing application to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
chown "$USER:$USER" "$INSTALL_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' "$PROJECT_DIR/" "$INSTALL_DIR/"

# Save secret key
echo "$SECRET_KEY" > "$SECRET_FILE"
chmod 600 "$SECRET_FILE"

# --- Create venv and install ---
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

# --- Try to generate Tailscale cert (requires paid plan) ---
echo "Attempting Tailscale certificate generation..."
mkdir -p "$CERT_DIR"
if tailscale cert --cert-file "$CERT_PATH" --key-file "$KEY_PATH" "$FQDN" 2>/dev/null; then
    echo "  Certificate generated (HTTPS enabled)"
    HTTPS=true
else
    echo "  Certificate unavailable (free Tailscale plan) -- using HTTP"
    echo "  Note: Tailscale encrypts traffic between devices, so HTTP is safe on your tailnet"
fi

# --- Install Caddy ---
if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    apt-get update -qq && apt-get install -y -qq caddy
else
    echo "Caddy already installed"
fi

# --- Write config files from templates ---
echo "Writing configuration files..."

if [ "$HTTPS" = true ]; then
    sed \
        -e "s|FILEBROWSER_FQDN|$FQDN|g" \
        -e "s|CERT_PATH|$CERT_PATH|g" \
        -e "s|KEY_PATH|$KEY_PATH|g" \
        "$INSTALL_DIR/deploy/Caddyfile.template" \
        > /etc/caddy/Caddyfile
else
    cp "$INSTALL_DIR/deploy/Caddyfile.http.template" /etc/caddy/Caddyfile
fi

sed \
    -e "s|FILEBROWSER_USER|$USER|g" \
    -e "s|FILEBROWSER_DIR|$INSTALL_DIR|g" \
    -e "s|FILEBROWSER_SECRET|$SECRET_KEY|g" \
    -e "s|FILEBROWSER_HTTPS_ENABLED|$HTTPS|g" \
    "$INSTALL_DIR/deploy/filebrowser.service" \
    > /etc/systemd/system/filebrowser.service

# --- Enable and start services ---
echo "Starting services..."
systemctl daemon-reload
systemctl enable filebrowser
systemctl restart filebrowser
systemctl enable caddy
systemctl restart caddy

if [ "$HTTPS" = true ]; then
    sed \
        -e "s|CERT_PATH|$CERT_PATH|g" \
        -e "s|KEY_PATH|$KEY_PATH|g" \
        -e "s|FILEBROWSER_FQDN|$FQDN|g" \
        "$INSTALL_DIR/deploy/tailscale-cert-renew.service" \
        > /etc/systemd/system/tailscale-cert-renew.service
    cp "$INSTALL_DIR/deploy/tailscale-cert-renew.timer" \
        /etc/systemd/system/tailscale-cert-renew.timer
    systemctl enable --now tailscale-cert-renew.timer
fi

echo ""
echo "=== Installation complete ==="
if [ "$HTTPS" = true ]; then
    echo "File Browser is running at: https://$FQDN"
else
    HOSTNAME=$(echo "$FQDN" | cut -d. -f1)
    echo "File Browser is running at: http://$HOSTNAME/"
    echo "(or http://$FQDN/)"
fi
echo ""
echo "To check status:"
echo "  systemctl status filebrowser"
echo "  systemctl status caddy"
