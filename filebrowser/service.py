"""Systemd service and Caddy configuration management for filebrowser."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _resolve_filebrowser_bin() -> str:
    """Resolve the filebrowser executable path."""
    fb_path = shutil.which("filebrowser")
    if fb_path:
        return fb_path
    return f"{sys.executable} -m filebrowser"


def _get_systemd_unit_path(user: bool = True) -> Path:
    """Get the systemd unit file path."""
    if user:
        return Path.home() / ".config" / "systemd" / "user" / "filebrowser.service"
    else:
        return Path("/etc/systemd/system/filebrowser.service")


def _get_caddy_config_path() -> Path:
    """Get the Caddy configuration snippet path."""
    return Path("/etc/caddy/conf.d/filebrowser.caddy")


def _detect_fqdn() -> str:
    """Detect the fully qualified domain name."""
    # Try Tailscale first
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        import json
        data = json.loads(result.stdout)
        fqdn = data.get("Self", {}).get("DNSName", "").rstrip(".")
        if fqdn:
            return fqdn
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    # Fall back to hostname -f
    try:
        result = subprocess.run(
            ["hostname", "-f"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        fqdn = result.stdout.strip()
        if fqdn:
            return fqdn
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return "localhost"


def _detect_tls() -> tuple[bool, Optional[str], Optional[str]]:
    """
    Detect available TLS certificates.
    
    Returns:
        (has_tls, cert_path, key_path)
    """
    fqdn = _detect_fqdn()
    
    # Try Tailscale cert
    tailscale_cert_dir = Path("/etc/ssl/tailscale")
    tailscale_cert = tailscale_cert_dir / f"{fqdn}.crt"
    tailscale_key = tailscale_cert_dir / f"{fqdn}.key"
    
    if tailscale_cert.exists() and tailscale_key.exists():
        return True, str(tailscale_cert), str(tailscale_key)
    
    # Try self-signed cert
    selfsigned_cert_dir = Path("/etc/ssl/self-signed")
    selfsigned_cert = selfsigned_cert_dir / f"{fqdn}.crt"
    selfsigned_key = selfsigned_cert_dir / f"{fqdn}.key"
    
    if selfsigned_cert.exists() and selfsigned_key.exists():
        return True, str(selfsigned_cert), str(selfsigned_key)
    
    return False, None, None


def _generate_systemd_unit(user: bool, port: int) -> str:
    """Generate systemd unit file content."""
    filebrowser_bin = _resolve_filebrowser_bin()
    
    # Get the directory containing the filebrowser binary for PATH
    if shutil.which("filebrowser"):
        bin_dir = str(Path(shutil.which("filebrowser")).parent)
    else:
        bin_dir = str(Path(sys.executable).parent)
    
    # Build a safe PATH
    safe_path = f"{bin_dir}:/usr/local/bin:/usr/bin:/bin"
    
    if user:
        return f"""[Unit]
Description=File Browser
After=network.target

[Service]
Type=simple
WorkingDirectory={Path.home()}
ExecStart={filebrowser_bin} serve --host 127.0.0.1 --port {port}
Restart=always
RestartSec=5
Environment=PATH={safe_path}
Environment=FILEBROWSER_SECRET_KEY_FILE={Path.home() / ".config" / "filebrowser" / "secret_key"}

[Install]
WantedBy=default.target
"""
    else:
        user_name = os.environ.get("SUDO_USER", os.environ.get("USER", "nobody"))
        return f"""[Unit]
Description=File Browser
After=network.target

[Service]
Type=simple
User={user_name}
WorkingDirectory=/opt/filebrowser
ExecStart={filebrowser_bin} serve --host 127.0.0.1 --port {port}
Restart=always
RestartSec=5
Environment=PATH={safe_path}
Environment=FILEBROWSER_SECRET_KEY_FILE={Path.home() / ".config" / "filebrowser" / "secret_key"}

[Install]
WantedBy=multi-user.target
"""


def _generate_caddy_config(port: int, caddy_port: int, frontdoor_port: int) -> str:
    """Generate Caddy configuration snippet."""
    fqdn = _detect_fqdn()
    has_tls, cert_path, key_path = _detect_tls()
    
    if has_tls:
        return f"""{fqdn}:{caddy_port} {{
    tls {cert_path} {key_path}

    # Terminal WebSocket: Caddy 2.6 cannot proxy WebSocket connections through
    # forward_auth — bypass auth for terminal and let filebrowser authenticate
    # via its own session cookie instead. handle blocks enforce route ordering.
    handle /api/terminal* {{
        reverse_proxy localhost:{port}
    }}

    # All other requests: authenticate via frontdoor
    handle {{
        forward_auth localhost:{frontdoor_port} {{
            uri /api/auth/validate
            copy_headers X-Authenticated-User
        }}

        reverse_proxy localhost:{port}
    }}
}}
"""
    else:
        return f"""http://{fqdn}:{caddy_port} {{
    # Terminal WebSocket: Caddy 2.6 cannot proxy WebSocket connections through
    # forward_auth — bypass auth for terminal and let filebrowser authenticate
    # via its own session cookie instead. handle blocks enforce route ordering.
    handle /api/terminal* {{
        reverse_proxy localhost:{port}
    }}

    # All other requests: authenticate via frontdoor
    handle {{
        forward_auth localhost:{frontdoor_port} {{
            uri /api/auth/validate
            copy_headers X-Authenticated-User
        }}

        reverse_proxy localhost:{port}
    }}
}}
"""


def _ensure_secret_key() -> None:
    """Ensure secret key exists in config directory."""
    from filebrowser.config import settings
    
    config_dir = settings.data_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    
    secret_key_file = config_dir / "secret_key"
    if not secret_key_file.exists():
        import secrets
        secret_key = secrets.token_hex(32)
        secret_key_file.write_text(secret_key)
        secret_key_file.chmod(0o600)
        print(f"Generated new secret key at {secret_key_file}")
    else:
        print(f"Using existing secret key from {secret_key_file}")


def _systemctl(args: list[str], user: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """Run systemctl command."""
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd.extend(args)
    
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def service_install(user: bool = True, port: int = 58080, 
                   caddy_port: int = 8447, frontdoor_port: int = 8420) -> int:
    """Install systemd service and Caddy configuration."""
    print("Installing filebrowser service...")
    
    # Ensure secret key exists
    _ensure_secret_key()
    
    # Generate and write systemd unit
    unit_path = _get_systemd_unit_path(user)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    
    unit_content = _generate_systemd_unit(user, port)
    unit_path.write_text(unit_content)
    unit_path.chmod(0o644)
    print(f"Wrote systemd unit to {unit_path}")
    
    # Generate Caddy config
    caddy_config_path = _get_caddy_config_path()
    caddy_config = _generate_caddy_config(port, caddy_port, frontdoor_port)
    
    # Write Caddy config (may require sudo)
    try:
        caddy_config_path.parent.mkdir(parents=True, exist_ok=True)
        caddy_config_path.write_text(caddy_config)
        print(f"Wrote Caddy config to {caddy_config_path}")
    except PermissionError:
        print(f"Writing Caddy config requires root privileges.")
        print(f"Please run the following command manually:")
        print(f"  sudo tee {caddy_config_path} > /dev/null <<'EOF'")
        print(caddy_config)
        print("EOF")
        print(f"  sudo systemctl reload caddy")
    
    # Reload systemd and enable service
    try:
        _systemctl(["daemon-reload"], user=user)
        _systemctl(["enable", "filebrowser.service"], user=user)
        print("Enabled filebrowser service")
    except subprocess.CalledProcessError as e:
        print(f"Error enabling service: {e}", file=sys.stderr)
        return 1
    
    # Check PAM access (shadow group)
    user_name = os.environ.get("USER", "")
    if user_name:
        try:
            result = subprocess.run(["groups", user_name], capture_output=True, text=True, check=True)
            if "shadow" not in result.stdout:
                print(f"\nWarning: User {user_name} is not in the 'shadow' group.")
                print(f"PAM authentication may not work. To fix, run:")
                print(f"  sudo usermod -aG shadow {user_name}")
                print(f"Then log out and back in for the change to take effect.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    
    print("\nService installed successfully!")
    print(f"To start: filebrowser service start")
    print(f"To check status: filebrowser service status")
    
    return 0


def service_uninstall() -> int:
    """Uninstall systemd service and Caddy configuration."""
    print("Uninstalling filebrowser service...")
    
    # Try both user and system units
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            try:
                _systemctl(["stop", "filebrowser.service"], user=user, check=False)
                _systemctl(["disable", "filebrowser.service"], user=user, check=False)
                unit_path.unlink()
                _systemctl(["daemon-reload"], user=user)
                print(f"Removed systemd unit from {unit_path}")
            except Exception as e:
                print(f"Error removing unit: {e}", file=sys.stderr)
    
    # Remove Caddy config
    caddy_config_path = _get_caddy_config_path()
    if caddy_config_path.exists():
        try:
            caddy_config_path.unlink()
            print(f"Removed Caddy config from {caddy_config_path}")
            subprocess.run(["sudo", "systemctl", "reload", "caddy"], check=False)
        except PermissionError:
            print(f"Removing Caddy config requires root privileges.")
            print(f"Please run: sudo rm {caddy_config_path}")
            print(f"Then run: sudo systemctl reload caddy")
    
    print("Service uninstalled successfully!")
    return 0


def service_start() -> int:
    """Start the filebrowser service."""
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            try:
                _systemctl(["start", "filebrowser.service"], user=user)
                print("Service started successfully!")
                return 0
            except subprocess.CalledProcessError as e:
                print(f"Error starting service: {e.stderr}", file=sys.stderr)
                return 1
    
    print("Error: Service not installed. Run 'filebrowser service install' first.", file=sys.stderr)
    return 1


def service_stop() -> int:
    """Stop the filebrowser service."""
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            try:
                _systemctl(["stop", "filebrowser.service"], user=user, check=False)
                print("Service stopped")
                return 0
            except subprocess.CalledProcessError:
                pass
    
    # Not an error if service not found during stop
    return 0


def service_restart() -> int:
    """Restart the filebrowser service."""
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            try:
                _systemctl(["restart", "filebrowser.service"], user=user)
                print("Service restarted successfully!")
                return 0
            except subprocess.CalledProcessError as e:
                print(f"Error restarting service: {e.stderr}", file=sys.stderr)
                return 1
    
    print("Error: Service not installed. Run 'filebrowser service install' first.", file=sys.stderr)
    return 1


def service_status() -> int:
    """Show the filebrowser service status."""
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            try:
                result = _systemctl(["status", "filebrowser.service"], user=user, check=False)
                print(result.stdout)
                return result.returncode
            except subprocess.CalledProcessError as e:
                print(e.stderr, file=sys.stderr)
                return 1
    
    print("Service not installed", file=sys.stderr)
    return 3


def service_logs(follow: bool = False, lines: int = 50) -> int:
    """Show the filebrowser service logs."""
    for user in [True, False]:
        unit_path = _get_systemd_unit_path(user)
        if unit_path.exists():
            cmd = ["journalctl"]
            if user:
                cmd.append("--user")
            cmd.extend(["-u", "filebrowser.service", "-n", str(lines)])
            if follow:
                cmd.append("-f")
            
            try:
                subprocess.run(cmd, check=True)
                return 0
            except subprocess.CalledProcessError as e:
                return e.returncode
    
    print("Service not installed", file=sys.stderr)
    return 1
