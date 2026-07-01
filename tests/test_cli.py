"""Tests for filebrowser CLI."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


def test_find_uv_in_path():
    """Test finding uv in PATH."""
    from filebrowser.cli import _find_uv
    
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/local/bin/uv"
        result = _find_uv()
        assert result == "/usr/local/bin/uv"
        mock_which.assert_called_once_with("uv")


def test_find_uv_in_common_locations(tmp_path):
    """Test finding uv in common installation locations."""
    from filebrowser.cli import _find_uv
    
    # Create a fake uv binary
    fake_uv = tmp_path / "uv"
    fake_uv.write_text("#!/bin/bash\necho uv")
    fake_uv.chmod(0o755)
    
    with patch("shutil.which", return_value=None):
        # Mock Path.home() to return tmp_path so the first common path exists
        with patch("pathlib.Path.home", return_value=tmp_path):
            # Create the .local/bin directory structure
            local_bin = tmp_path / ".local" / "bin"
            local_bin.mkdir(parents=True)
            uv_path = local_bin / "uv"
            uv_path.write_text("#!/bin/bash\necho uv")
            
            result = _find_uv()
            assert result == str(uv_path)


def test_find_uv_not_found():
    """Test when uv is not found anywhere."""
    from filebrowser.cli import _find_uv
    
    with patch("shutil.which", return_value=None):
        with patch("pathlib.Path.exists", return_value=False):
            result = _find_uv()
            assert result is None


def test_resolve_filebrowser_bin_in_path():
    """Test resolving filebrowser binary in PATH."""
    from filebrowser.cli import _resolve_filebrowser_bin
    
    with patch("shutil.which", return_value="/usr/local/bin/filebrowser"):
        result = _resolve_filebrowser_bin()
        assert result == "/usr/local/bin/filebrowser"


def test_resolve_filebrowser_bin_fallback():
    """Test fallback to python -m filebrowser."""
    from filebrowser.cli import _resolve_filebrowser_bin
    
    with patch("shutil.which", return_value=None):
        result = _resolve_filebrowser_bin()
        assert result == f"{sys.executable} -m filebrowser"


def test_get_install_source_git(tmp_path):
    """Test detecting git install source."""
    from filebrowser.cli import _get_install_source
    import filebrowser
    
    # Create a mock direct_url.json for git install
    dist_info = tmp_path / "filebrowser-0.1.0.dist-info"
    dist_info.mkdir()
    direct_url = dist_info / "direct_url.json"
    direct_url.write_text(json.dumps({
        "url": "https://github.com/robotdad/filebrowser",
        "vcs_info": {
            "vcs": "git",
            "commit_id": "abc123"
        }
    }))
    
    # Mock the filebrowser module's __file__ attribute
    original_file = filebrowser.__file__
    try:
        filebrowser.__file__ = str(tmp_path / "filebrowser" / "__init__.py")
        source_type, source_url = _get_install_source()
        assert source_type == "git"
        assert source_url == "https://github.com/robotdad/filebrowser"
    finally:
        filebrowser.__file__ = original_file


def test_get_install_source_editable(tmp_path):
    """Test detecting editable install source."""
    from filebrowser.cli import _get_install_source
    import filebrowser
    
    # Create a mock direct_url.json for editable install
    dist_info = tmp_path / "filebrowser-0.1.0.dist-info"
    dist_info.mkdir()
    direct_url = dist_info / "direct_url.json"
    direct_url.write_text(json.dumps({
        "url": "file:///home/user/projects/filebrowser",
        "dir_info": {
            "editable": True
        }
    }))
    
    original_file = filebrowser.__file__
    try:
        filebrowser.__file__ = str(tmp_path / "filebrowser" / "__init__.py")
        source_type, source_url = _get_install_source()
        assert source_type == "editable"
        assert source_url == "file:///home/user/projects/filebrowser"
    finally:
        filebrowser.__file__ = original_file


def test_get_install_source_pypi():
    """Test detecting PyPI install source (no direct_url.json)."""
    from filebrowser.cli import _get_install_source
    
    with patch("pathlib.Path.exists", return_value=False):
        source_type, source_url = _get_install_source()
        assert source_type == "pypi"
        assert source_url is None


def test_is_uv_managed_true():
    """Test detecting uv-managed installation."""
    from filebrowser.cli import _is_uv_managed
    
    uv_tools_path = str(Path.home() / ".local" / "share" / "uv" / "tools" / "filebrowser" / "bin" / "filebrowser")
    
    with patch("shutil.which", return_value=uv_tools_path):
        with patch("pathlib.Path.resolve", return_value=Path(uv_tools_path)):
            result = _is_uv_managed()
            assert result is True


def test_is_uv_managed_false():
    """Test detecting non-uv-managed installation."""
    from filebrowser.cli import _is_uv_managed
    
    with patch("shutil.which", return_value="/usr/local/bin/filebrowser"):
        result = _is_uv_managed()
        assert result is False


def test_is_uv_managed_not_found():
    """Test when filebrowser is not found."""
    from filebrowser.cli import _is_uv_managed
    
    with patch("shutil.which", return_value=None):
        result = _is_uv_managed()
        assert result is False


def test_cmd_serve():
    """Test the serve command."""
    from filebrowser.cli import cmd_serve
    
    args = argparse.Namespace(host="0.0.0.0", port=8080, log_level="debug")
    
    with patch("uvicorn.run") as mock_run:
        result = cmd_serve(args)
        assert result == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[1]["host"] == "0.0.0.0"
        assert call_args[1]["port"] == 8080
        assert call_args[1]["log_level"] == "debug"


def test_cmd_service_install():
    """Test the service install command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(
        service_command="install",
        user=True,
        port=58080,
        caddy_port=8447,
        frontdoor_port=8420
    )
    
    with patch("filebrowser.service.service_install", return_value=0) as mock_install:
        result = cmd_service(args)
        assert result == 0
        mock_install.assert_called_once_with(True, 58080, 8447, 8420)


def test_cmd_service_uninstall():
    """Test the service uninstall command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="uninstall")
    
    with patch("filebrowser.service.service_uninstall", return_value=0) as mock_uninstall:
        result = cmd_service(args)
        assert result == 0
        mock_uninstall.assert_called_once()


def test_cmd_service_start():
    """Test the service start command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="start")
    
    with patch("filebrowser.service.service_start", return_value=0) as mock_start:
        result = cmd_service(args)
        assert result == 0
        mock_start.assert_called_once()


def test_cmd_service_stop():
    """Test the service stop command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="stop")
    
    with patch("filebrowser.service.service_stop", return_value=0) as mock_stop:
        result = cmd_service(args)
        assert result == 0
        mock_stop.assert_called_once()


def test_cmd_service_restart():
    """Test the service restart command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="restart")
    
    with patch("filebrowser.service.service_restart", return_value=0) as mock_restart:
        result = cmd_service(args)
        assert result == 0
        mock_restart.assert_called_once()


def test_cmd_service_status():
    """Test the service status command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="status")
    
    with patch("filebrowser.service.service_status", return_value=0) as mock_status:
        result = cmd_service(args)
        assert result == 0
        mock_status.assert_called_once()


def test_cmd_service_logs():
    """Test the service logs command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="logs", follow=True, lines=100)
    
    with patch("filebrowser.service.service_logs", return_value=0) as mock_logs:
        result = cmd_service(args)
        assert result == 0
        mock_logs.assert_called_once_with(True, 100)


def test_cmd_service_unknown():
    """Test unknown service command."""
    from filebrowser.cli import cmd_service
    
    args = argparse.Namespace(service_command="unknown")
    
    result = cmd_service(args)
    assert result == 1


def test_cmd_upgrade_no_uv():
    """Test upgrade command when uv is not found."""
    from filebrowser.cli import cmd_upgrade
    
    args = argparse.Namespace(force=False)
    
    with patch("filebrowser.cli._find_uv", return_value=None):
        result = cmd_upgrade(args)
        assert result == 1


def test_cmd_upgrade_git_source():
    """Test upgrade command with git source."""
    from filebrowser.cli import cmd_upgrade
    
    args = argparse.Namespace(force=False)
    
    with patch("filebrowser.cli._find_uv", return_value="/usr/bin/uv"):
        with patch("filebrowser.cli._get_install_source", return_value=("git", "https://github.com/robotdad/filebrowser")):
            with patch("filebrowser.cli._is_uv_managed", return_value=True):
                with patch("filebrowser.service.service_stop", return_value=0):
                    with patch("filebrowser.service.service_restart", return_value=0):
                        with patch("filebrowser.service.service_install", return_value=0):
                            with patch("subprocess.run") as mock_run:
                                mock_run.return_value = MagicMock(returncode=0)
                                result = cmd_upgrade(args)
                                assert result == 0
                                mock_run.assert_called_once()
                                cmd = mock_run.call_args[0][0]
                                assert cmd[0] == "/usr/bin/uv"
                                assert "tool" in cmd
                                assert "install" in cmd
                                assert "https://github.com/robotdad/filebrowser" in cmd


def test_cmd_upgrade_editable_source():
    """Test upgrade command with editable source (should fail)."""
    from filebrowser.cli import cmd_upgrade
    
    args = argparse.Namespace(force=False)
    
    with patch("filebrowser.cli._find_uv", return_value="/usr/bin/uv"):
        with patch("filebrowser.cli._get_install_source", return_value=("editable", "/path/to/filebrowser")):
            with patch("filebrowser.cli._is_uv_managed", return_value=False):
                with patch("filebrowser.service.service_stop", return_value=0):
                    result = cmd_upgrade(args)
                    assert result == 1


def test_cmd_upgrade_default_source():
    """Test upgrade command with default (unknown) source."""
    from filebrowser.cli import cmd_upgrade
    
    args = argparse.Namespace(force=True)
    
    with patch("filebrowser.cli._find_uv", return_value="/usr/bin/uv"):
        with patch("filebrowser.cli._get_install_source", return_value=("unknown", None)):
            with patch("filebrowser.cli._is_uv_managed", return_value=True):
                with patch("filebrowser.service.service_stop", return_value=0):
                    with patch("filebrowser.service.service_restart", return_value=0):
                        with patch("filebrowser.service.service_install", return_value=0):
                            with patch("subprocess.run") as mock_run:
                                mock_run.return_value = MagicMock(returncode=0)
                                result = cmd_upgrade(args)
                                assert result == 0
                                cmd = mock_run.call_args[0][0]
                                assert "git+https://github.com/robotdad/filebrowser" in cmd


def test_cmd_upgrade_failed_install():
    """Test upgrade command when installation fails."""
    from filebrowser.cli import cmd_upgrade
    
    args = argparse.Namespace(force=False)
    
    with patch("filebrowser.cli._find_uv", return_value="/usr/bin/uv"):
        with patch("filebrowser.cli._get_install_source", return_value=("git", "https://github.com/robotdad/filebrowser")):
            with patch("filebrowser.cli._is_uv_managed", return_value=True):
                with patch("filebrowser.service.service_stop", return_value=0):
                    with patch("filebrowser.service.service_restart", return_value=0):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(returncode=1)
                            result = cmd_upgrade(args)
                            assert result == 1


def test_main_no_command(capsys):
    """Test main with no command defaults to serve."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser"]):
        with patch("filebrowser.cli.cmd_serve", return_value=0) as mock_serve:
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


def test_main_serve_command():
    """Test main with serve command."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser", "serve", "--port", "9000"]):
        with patch("filebrowser.cli.cmd_serve", return_value=0):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


def test_main_service_install_command():
    """Test main with service install command."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser", "service", "install", "--user"]):
        with patch("filebrowser.cli.cmd_service", return_value=0):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


def test_main_upgrade_command():
    """Test main with upgrade command."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser", "upgrade", "--force"]):
        with patch("filebrowser.cli.cmd_upgrade", return_value=0):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


def test_main_keyboard_interrupt():
    """Test main handles KeyboardInterrupt."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser", "serve"]):
        with patch("filebrowser.cli.cmd_serve", side_effect=KeyboardInterrupt):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 130


def test_main_exception():
    """Test main handles general exceptions."""
    from filebrowser.cli import main
    
    with patch("sys.argv", ["filebrowser", "serve"]):
        with patch("filebrowser.cli.cmd_serve", side_effect=RuntimeError("test error")):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
