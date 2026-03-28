#!/bin/bash
set -euo pipefail

echo "=== File Browser Installer ==="

# --- Detect environment ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# When run via sudo, whoami returns root. Use SUDO_USER to get the real user.
USER="${SUDO_USER:-$(whoami)}"
INSTALL_DIR="/opt/filebrowser"
CADDY_PORT=8447
FRONTDOOR_PORT=8420
HTTPS=false

# --- Detect FQDN (Tailscale preferred, hostname -f fallback) ---
echo "Detecting FQDN..."
FQDN=""

# Try Tailscale first
if command -v tailscale &>/dev/null; then
    FQDN=$(tailscale status --json 2>/dev/null \
        | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['Self']['DNSName'].rstrip('.'))" \
        2>/dev/null) || true
fi

# Fall back to hostname -f if Tailscale didn't provide an FQDN
if [ -z "$FQDN" ]; then
    FQDN=$(hostname -f 2>/dev/null) || true
fi

echo "  FQDN: $FQDN"

# Validate FQDN before use in config generation
if [ -z "$FQDN" ] || [[ "$FQDN" =~ [^a-zA-Z0-9.\-] ]]; then
    echo "ERROR: Invalid or empty FQDN detected: '$FQDN'" >&2
    exit 1
fi

# --- Generate secret key (idempotent: read from filebrowser.env if exists) ---
echo "Setting up secret key..."
ENV_FILE="$INSTALL_DIR/filebrowser.env"
if [ -f "$ENV_FILE" ]; then
    SECRET_KEY=$(grep '^FILEBROWSER_SECRET_KEY=' "$ENV_FILE" | cut -d= -f2-)
    echo "  Using existing secret key"
else
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "  Generated new secret key"
fi

# --- Pick internal port (idempotent) ---
PORT_FILE="$INSTALL_DIR/.port"
if [ -f "$PORT_FILE" ]; then
    PORT=$(cat "$PORT_FILE")
    echo "  Using existing internal port $PORT"
else
    PORT=58080
    echo "  Using default internal port $PORT"
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

# Save port
echo "$PORT" > "$PORT_FILE"
chmod 600 "$PORT_FILE"

# --- Create venv and install ---
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet "$INSTALL_DIR"

# --- Install Caddy ---
# Install before the TLS cert section: the cert key requires root:caddy
# ownership, and the 'caddy' group only exists after Caddy is installed.
if ! command -v caddy &>/dev/null; then
    echo "Installing Caddy..."
    apt-get update -qq && apt-get install -y -qq caddy
else
    echo "Caddy already installed"
fi

# --- Three-tier TLS provisioning ---
# Tier 1: Tailscale cert (requires paid plan)
# Tier 2: Self-signed cert (HTTPS with browser warning)
# Tier 3: HTTP fallback (Tailscale encrypts in transit)
echo "Attempting TLS certificate provisioning..."
CERT_DIR="/etc/ssl/tailscale"
CERT_PATH="$CERT_DIR/$FQDN.crt"
KEY_PATH="$CERT_DIR/$FQDN.key"
mkdir -p "$CERT_DIR"
if command -v tailscale &>/dev/null && tailscale cert --cert-file "$CERT_PATH" --key-file "$KEY_PATH" "$FQDN" 2>/dev/null; then
    echo "  Tier 1: Tailscale certificate obtained (HTTPS enabled)"
    chown root:caddy "$KEY_PATH"
    chmod 640 "$KEY_PATH"
    HTTPS=true
else
    CERT_DIR="/etc/ssl/self-signed"
    CERT_PATH="/etc/ssl/self-signed/$FQDN.crt"
    KEY_PATH="/etc/ssl/self-signed/$FQDN.key"
    mkdir -p "$CERT_DIR"
    if openssl req -x509 -newkey rsa:2048 -days 3650 -nodes -subj "/CN=$FQDN" \
        -keyout "$KEY_PATH" -out "$CERT_PATH" 2>/dev/null; then
        echo "  Tier 2: Self-signed certificate generated (HTTPS enabled)"
        chown root:caddy "$KEY_PATH"
        chmod 640 "$KEY_PATH"
        HTTPS=true
    else
        echo "  Tier 3: TLS unavailable -- falling back to HTTP"
        echo "  Note: HTTP traffic is unencrypted. Only use this on a trusted LAN or Tailscale tailnet."
    fi
fi

# --- Write conf.d snippet (filebrowser does NOT own the main Caddyfile) ---
echo "Writing Caddy conf.d snippet..."
mkdir -p /etc/caddy/conf.d
if [ "$HTTPS" = true ]; then
    sed \
        -e "s|FILEBROWSER_FQDN|$FQDN|g" \
        -e "s|CERT_PATH|$CERT_PATH|g" \
        -e "s|KEY_PATH|$KEY_PATH|g" \
        -e "s|FILEBROWSER_CADDY_PORT|$CADDY_PORT|g" \
        -e "s|FRONTDOOR_PORT|$FRONTDOOR_PORT|g" \
        -e "s|FILEBROWSER_PORT|$PORT|g" \
        "$INSTALL_DIR/deploy/filebrowser.caddy.template" \
        > /etc/caddy/conf.d/filebrowser.caddy
else
    sed \
        -e "s|FILEBROWSER_FQDN|$FQDN|g" \
        -e "s|FILEBROWSER_CADDY_PORT|$CADDY_PORT|g" \
        -e "s|FRONTDOOR_PORT|$FRONTDOOR_PORT|g" \
        -e "s|FILEBROWSER_PORT|$PORT|g" \
        "$INSTALL_DIR/deploy/filebrowser.caddy.http.template" \
        > /etc/caddy/conf.d/filebrowser.caddy
fi

# --- Write environment file ---
echo "Writing environment file..."
(umask 177; cat > "$ENV_FILE" <<EOF
FILEBROWSER_SECRET_KEY=$SECRET_KEY
FILEBROWSER_SECURE_COOKIES=$HTTPS
EOF
)

# --- Write systemd unit ---
echo "Installing systemd unit..."
# Values are delivered via EnvironmentFile=/opt/filebrowser/filebrowser.env -- not injected inline.
# Unit file is created atomically with restrictive permissions (umask 177 = mode 0600).
(umask 177; sed \
    -e "s|FILEBROWSER_USER|$USER|g" \
    -e "s|FILEBROWSER_DIR|$INSTALL_DIR|g" \
    -e "s|FILEBROWSER_PORT|$PORT|g" \
    "$INSTALL_DIR/deploy/filebrowser.service" \
    > /etc/systemd/system/filebrowser.service)
chmod 600 /etc/systemd/system/filebrowser.service

# --- Enable and start services ---
echo "Starting services..."
systemctl daemon-reload
systemctl enable filebrowser
systemctl restart filebrowser
systemctl reload caddy

echo ""
echo "=== Installation complete ==="
if [ "$HTTPS" = true ]; then
    echo "File Browser is running at: https://$FQDN:$CADDY_PORT"
else
    echo "File Browser is running at: http://$FQDN:$CADDY_PORT"
fi
echo ""
echo "To check status:"
echo "  systemctl status filebrowser"
echo "  systemctl status caddy"
