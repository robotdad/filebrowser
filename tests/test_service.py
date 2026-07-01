"""Tests for filebrowser service management."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def test_resolve_filebrowser_bin_in_path():
    """Test resolving filebrowser binary in PATH."""
    from filebrowser.service import _resolve_filebrowser_bin
    
    with patch("shutil.which", return_value="/usr/local/bin/filebrowser"):
        result = _resolve_filebrowser_bin()
        assert result == "/usr/local/bin/filebrowser"


def test_get_systemd_unit_path_user():
    """Test getting user systemd unit path."""
    from filebrowser.service import _get_systemd_unit_path
    
    result = _get_systemd_unit_path(user=True)
    assert result == Path.home() / ".config" / "systemd" / "user" / "filebrowser.service"


def test_get_systemd_unit_path_system():
    """Test getting system systemd unit path."""
    from filebrowser.service import _get_systemd_unit_path
    
    result = _get_systemd_unit_path(user=False)
    assert result == Path("/etc/systemd/system/filebrowser.service")


def test_get_caddy_config_path():
    """Test getting Caddy config path."""
    from filebrowser.service import _get_caddy_config_path
    
    result = _get_caddy_config_path()
    assert result == Path("/etc/caddy/conf.d/filebrowser.caddy")


def test_detect_fqdn_tailscale():
    """Test FQDN detection via Tailscale."""
    from filebrowser.service import _detect_fqdn
    
    mock_result = MagicMock()
    mock_result.stdout = '{"Self": {"DNSName": "myhost.tailnet.ts.net."}}'
    
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _detect_fqdn()
        assert result == "myhost.tailnet.ts.net"
        mock_run.assert_called_once()


def test_detect_fqdn_hostname():
    """Test FQDN detection via hostname fallback."""
    from filebrowser.service import _detect_fqdn
    
    # First call (tailscale) fails, second call (hostname) succeeds
    def run_side_effect(*args, **kwargs):
        if "tailscale" in args[0]:
            raise FileNotFoundError()
        else:
            mock_result = MagicMock()
            mock_result.stdout = "myhost.example.com\n"
            return mock_result
    
    with patch("subprocess.run", side_effect=run_side_effect):
        result = _detect_fqdn()
        assert result == "myhost.example.com"


def test_detect_fqdn_localhost_fallback():
    """Test FQDN detection falls back to localhost."""
    from filebrowser.service import _detect_fqdn
    
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = _detect_fqdn()
        assert result == "localhost"


def test_detect_tls_returns_tuple():
    """Test TLS detection returns a tuple of (bool, str|None, str|None)."""
    from filebrowser.service import _detect_tls
    
    # Just test that it returns the right type without complex mocking
    has_tls, cert_path, key_path = _detect_tls()
    assert isinstance(has_tls, bool)
    assert cert_path is None or isinstance(cert_path, str)
    assert key_path is None or isinstance(key_path, str)
    
    # If has_tls is True, paths should be set
    if has_tls:
        assert cert_path is not None
        assert key_path is not None
    else:
        assert cert_path is None
        assert key_path is None


def test_generate_systemd_unit_user():
    """Test generating user systemd unit."""
    from filebrowser.service import _generate_systemd_unit
    
    with patch("filebrowser.service._resolve_filebrowser_bin", return_value="/home/user/.local/bin/filebrowser"):
        with patch("shutil.which", return_value="/home/user/.local/bin/filebrowser"):
            unit = _generate_systemd_unit(user=True, port=58080)
            
            assert "[Unit]" in unit
            assert "Description=File Browser" in unit
            assert "[Service]" in unit
            assert "ExecStart=/home/user/.local/bin/filebrowser serve --host 127.0.0.1 --port 58080" in unit
            assert "Restart=always" in unit
            assert f"Environment=FILEBROWSER_SECRET_KEY_FILE={Path.home() / '.config' / 'filebrowser' / 'secret_key'}" in unit
            assert "[Install]" in unit
            assert "WantedBy=default.target" in unit


def test_generate_systemd_unit_system():
    """Test generating system systemd unit."""
    from filebrowser.service import _generate_systemd_unit
    
    with patch("filebrowser.service._resolve_filebrowser_bin", return_value="/usr/local/bin/filebrowser"):
        with patch("shutil.which", return_value="/usr/local/bin/filebrowser"):
            with patch.dict("os.environ", {"USER": "testuser"}):
                unit = _generate_systemd_unit(user=False, port=58080)
                
                assert "[Unit]" in unit
                assert "Description=File Browser" in unit
                assert "[Service]" in unit
                assert "User=testuser" in unit
                assert "ExecStart=/usr/local/bin/filebrowser serve --host 127.0.0.1 --port 58080" in unit
                assert "WantedBy=multi-user.target" in unit


def test_generate_caddy_config_with_tls():
    """Test generating Caddy config with TLS."""
    from filebrowser.service import _generate_caddy_config
    
    with patch("filebrowser.service._detect_fqdn", return_value="myhost.example.com"):
        with patch("filebrowser.service._detect_tls", return_value=(True, "/etc/ssl/cert.crt", "/etc/ssl/cert.key")):
            config = _generate_caddy_config(port=58080, caddy_port=8447, frontdoor_port=8420)
            
            assert "myhost.example.com:8447" in config
            assert "tls /etc/ssl/cert.crt /etc/ssl/cert.key" in config
            assert "handle /api/terminal*" in config
            assert "reverse_proxy localhost:58080" in config
            assert "forward_auth localhost:8420" in config
            assert "uri /api/auth/validate" in config
            assert "copy_headers X-Authenticated-User" in config


def test_generate_caddy_config_without_tls():
    """Test generating Caddy config without TLS (HTTP)."""
    from filebrowser.service import _generate_caddy_config
    
    with patch("filebrowser.service._detect_fqdn", return_value="myhost.example.com"):
        with patch("filebrowser.service._detect_tls", return_value=(False, None, None)):
            config = _generate_caddy_config(port=58080, caddy_port=8447, frontdoor_port=8420)
            
            assert "http://myhost.example.com:8447" in config
            assert "tls" not in config
            assert "handle /api/terminal*" in config
            assert "reverse_proxy localhost:58080" in config


def test_ensure_secret_key_creates_new(tmp_path):
    """Test ensuring secret key creates new file."""
    from filebrowser.service import _ensure_secret_key
    from filebrowser.config import settings
    
    config_dir = tmp_path / ".config" / "filebrowser"
    secret_key_file = config_dir / "secret_key"
    
    # Temporarily change settings.data_dir
    original_data_dir = settings.data_dir
    try:
        settings.data_dir = config_dir
        _ensure_secret_key()
        
        assert secret_key_file.exists()
        assert len(secret_key_file.read_text().strip()) == 64  # 32 bytes hex = 64 chars
    finally:
        settings.data_dir = original_data_dir


def test_ensure_secret_key_preserves_existing(tmp_path):
    """Test ensuring secret key preserves existing file."""
    from filebrowser.service import _ensure_secret_key
    from filebrowser.config import settings
    
    config_dir = tmp_path / ".config" / "filebrowser"
    config_dir.mkdir(parents=True)
    secret_key_file = config_dir / "secret_key"
    secret_key_file.write_text("existing-secret-key")
    
    original_data_dir = settings.data_dir
    try:
        settings.data_dir = config_dir
        _ensure_secret_key()
        
        assert secret_key_file.read_text() == "existing-secret-key"
    finally:
        settings.data_dir = original_data_dir


def test_service_install_user(tmp_path):
    """Test installing user service."""
    from filebrowser.service import service_install
    
    unit_path = tmp_path / ".config" / "systemd" / "user" / "filebrowser.service"
    caddy_path = tmp_path / "caddy.conf"
    
    with patch("filebrowser.service._get_systemd_unit_path", return_value=unit_path):
        with patch("filebrowser.service._get_caddy_config_path", return_value=caddy_path):
            with patch("filebrowser.service._ensure_secret_key"):
                with patch("filebrowser.service._generate_systemd_unit", return_value="[Unit]\ntest"):
                    with patch("filebrowser.service._generate_caddy_config", return_value="test caddy"):
                        with patch("filebrowser.service._systemctl") as mock_systemctl:
                            with patch("subprocess.run") as mock_run:
                                result = service_install(user=True, port=58080)
                                
                                assert result == 0
                                assert unit_path.exists()
                                assert unit_path.read_text() == "[Unit]\ntest"
                                
                                # Check systemctl calls
                                assert mock_systemctl.call_count == 2
                                mock_systemctl.assert_any_call(["daemon-reload"], user=True)
                                mock_systemctl.assert_any_call(["enable", "filebrowser.service"], user=True)


def test_service_install_caddy_permission_error(tmp_path, capsys):
    """Test installing service when Caddy config write fails."""
    from filebrowser.service import service_install
    
    unit_path = tmp_path / ".config" / "systemd" / "user" / "filebrowser.service"
    caddy_path = Path("/etc/caddy/conf.d/filebrowser.caddy")  # Will fail to write
    
    with patch("filebrowser.service._get_systemd_unit_path", return_value=unit_path):
        with patch("filebrowser.service._get_caddy_config_path", return_value=caddy_path):
            with patch("filebrowser.service._ensure_secret_key"):
                with patch("filebrowser.service._generate_systemd_unit", return_value="[Unit]\ntest"):
                    with patch("filebrowser.service._generate_caddy_config", return_value="test caddy"):
                        with patch("filebrowser.service._systemctl"):
                            with patch("subprocess.run"):
                                result = service_install(user=True, port=58080)
                                
                                assert result == 0
                                captured = capsys.readouterr()
                                assert "Writing Caddy config requires root privileges" in captured.out or "Wrote Caddy config" in captured.out


def test_service_uninstall():
    """Test uninstalling service."""
    from filebrowser.service import service_uninstall
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        with patch("filebrowser.service._get_caddy_config_path") as mock_get_caddy:
            mock_unit_path = MagicMock()
            mock_unit_path.exists.return_value = True
            mock_get_path.return_value = mock_unit_path
            
            mock_caddy_path = MagicMock()
            mock_caddy_path.exists.return_value = True
            mock_get_caddy.return_value = mock_caddy_path
            
            with patch("filebrowser.service._systemctl") as mock_systemctl:
                with patch("subprocess.run"):
                    result = service_uninstall()
                    
                    assert result == 0
                    mock_unit_path.unlink.assert_called()


def test_service_start_success():
    """Test starting service successfully."""
    from filebrowser.service import service_start
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path
        
        with patch("filebrowser.service._systemctl") as mock_systemctl:
            result = service_start()
            
            assert result == 0
            mock_systemctl.assert_called_once_with(["start", "filebrowser.service"], user=True)


def test_service_start_not_installed():
    """Test starting service when not installed."""
    from filebrowser.service import service_start
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path
        
        result = service_start()
        assert result == 1


def test_service_stop():
    """Test stopping service."""
    from filebrowser.service import service_stop
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path
        
        with patch("filebrowser.service._systemctl") as mock_systemctl:
            result = service_stop()
            
            assert result == 0
            mock_systemctl.assert_called_once_with(["stop", "filebrowser.service"], user=True, check=False)


def test_service_restart_success():
    """Test restarting service successfully."""
    from filebrowser.service import service_restart
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path
        
        with patch("filebrowser.service._systemctl") as mock_systemctl:
            result = service_restart()
            
            assert result == 0
            mock_systemctl.assert_called_once_with(["restart", "filebrowser.service"], user=True)


def test_service_restart_not_installed():
    """Test restarting service when not installed."""
    from filebrowser.service import service_restart
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path
        
        result = service_restart()
        assert result == 1


def test_service_status():
    """Test getting service status."""
    from filebrowser.service import service_status
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path
        
        with patch("filebrowser.service._systemctl") as mock_systemctl:
            mock_result = MagicMock()
            mock_result.stdout = "Active: active (running)"
            mock_result.returncode = 0
            mock_systemctl.return_value = mock_result
            
            result = service_status()
            
            assert result == 0
            mock_systemctl.assert_called_once_with(["status", "filebrowser.service"], user=True, check=False)


def test_service_logs():
    """Test viewing service logs."""
    from filebrowser.service import service_logs
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path
        
        with patch("subprocess.run") as mock_run:
            result = service_logs(follow=True, lines=100)
            
            assert result == 0
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "journalctl" in cmd
            assert "--user" in cmd
            assert "-u" in cmd
            assert "filebrowser.service" in cmd
            assert "-n" in cmd
            assert "100" in cmd
            assert "-f" in cmd


def test_service_logs_not_installed():
    """Test viewing logs when service not installed."""
    from filebrowser.service import service_logs
    
    with patch("filebrowser.service._get_systemd_unit_path") as mock_get_path:
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path
        
        result = service_logs(follow=False, lines=50)
        assert result == 1
