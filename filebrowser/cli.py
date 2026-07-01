"""Command-line interface for filebrowser."""
import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Optional

logger = logging.getLogger(__name__)


def _find_uv() -> Optional[str]:
    """Find uv executable in common locations."""
    # Check PATH first
    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path
    
    # Check common installation locations
    common_paths = [
        Path.home() / ".local" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
        Path("/snap/bin/uv"),
        Path("/root/.local/bin/uv"),
    ]
    
    for path in common_paths:
        if path.exists() and path.is_file():
            return str(path)
    
    return None


def _resolve_filebrowser_bin() -> str:
    """Resolve the filebrowser executable path."""
    # Check if filebrowser is on PATH
    fb_path = shutil.which("filebrowser")
    if fb_path:
        return fb_path
    
    # Fallback to python -m filebrowser
    return f"{sys.executable} -m filebrowser"


def _get_install_source() -> tuple[str, Optional[str]]:
    """
    Detect how filebrowser was installed.
    
    Returns:
        (source_type, source_url) where source_type is 'git', 'pypi', or 'editable'
    """
    try:
        import filebrowser
        package_path = Path(filebrowser.__file__).parent.parent
        direct_url_file = package_path / "filebrowser-0.1.0.dist-info" / "direct_url.json"
        
        if direct_url_file.exists():
            data = json.loads(direct_url_file.read_text())
            if "vcs_info" in data:
                return "git", data.get("url")
            elif "dir_info" in data:
                return "editable", data.get("url")
        
        return "pypi", None
    except Exception as e:
        logger.debug(f"Could not detect install source: {e}")
        return "unknown", None


def _is_uv_managed() -> bool:
    """Check if filebrowser is managed by uv tool."""
    fb_path = shutil.which("filebrowser")
    if not fb_path:
        return False
    
    uv_tools_dir = Path.home() / ".local" / "share" / "uv" / "tools"
    try:
        resolved = Path(fb_path).resolve()
        return str(uv_tools_dir) in str(resolved)
    except Exception:
        return False


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the filebrowser server."""
    import uvicorn
    from filebrowser.main import app
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )
    return 0


def cmd_service(args: argparse.Namespace) -> int:
    """Manage filebrowser systemd service."""
    from filebrowser.service import (
        service_install,
        service_uninstall,
        service_start,
        service_stop,
        service_restart,
        service_status,
        service_logs,
    )
    
    subcommand = args.service_command
    
    if subcommand == "install":
        return service_install(args.user, args.port, args.caddy_port, args.frontdoor_port)
    elif subcommand == "uninstall":
        return service_uninstall()
    elif subcommand == "start":
        return service_start()
    elif subcommand == "stop":
        return service_stop()
    elif subcommand == "restart":
        return service_restart()
    elif subcommand == "status":
        return service_status()
    elif subcommand == "logs":
        return service_logs(args.follow, args.lines)
    else:
        print(f"Unknown service command: {subcommand}", file=sys.stderr)
        return 1


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Upgrade filebrowser to the latest version."""
    from filebrowser.service import service_stop, service_restart, service_install
    
    # Find uv
    uv = _find_uv()
    if not uv:
        print("Error: uv not found. Install it from https://github.com/astral-sh/uv", file=sys.stderr)
        return 1
    
    # Detect install source
    source_type, source_url = _get_install_source()
    is_uv_tool = _is_uv_managed()
    
    if not is_uv_tool:
        print("Warning: filebrowser does not appear to be installed as a uv tool.", file=sys.stderr)
        print("Consider reinstalling with: uv tool install git+https://github.com/robotdad/filebrowser", file=sys.stderr)
    
    print(f"Detected install source: {source_type}")
    if source_url:
        print(f"Source URL: {source_url}")
    
    # Stop service if running (ignore errors if not installed)
    print("Stopping filebrowser service...")
    service_stop()
    
    try:
        # Upgrade based on source type
        if source_type == "git" and source_url:
            print(f"Upgrading from git: {source_url}")
            cmd = [uv, "tool", "install", "--reinstall", "--force", source_url]
        elif source_type == "editable":
            print("Warning: Editable install detected. Skipping upgrade.", file=sys.stderr)
            print("To upgrade, pull latest changes and reinstall manually.", file=sys.stderr)
            return 1
        else:
            # Default to github for unknown/pypi sources
            print("Upgrading from default git repository...")
            cmd = [uv, "tool", "install", "--reinstall", "--force", 
                   "git+https://github.com/robotdad/filebrowser"]
        
        if args.force:
            print("Force flag enabled")
        
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        
        if result.returncode != 0:
            print(f"Error: Upgrade failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode
        
        print("Upgrade successful!")
        
        # Regenerate service file to update paths
        print("Regenerating service files...")
        service_install(user=True, port=58080, caddy_port=8447, frontdoor_port=8420)
        
        # Restart service
        print("Restarting filebrowser service...")
        return service_restart()
        
    except Exception as e:
        print(f"Error during upgrade: {e}", file=sys.stderr)
        return 1
    finally:
        # Always try to restart service even if upgrade failed
        print("Ensuring service is restarted...")
        service_restart()


def main() -> NoReturn:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="filebrowser",
        description="File browser web application",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # serve command (default)
    serve_parser = subparsers.add_parser("serve", help="Run the filebrowser server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=58080, help="Port to bind to")
    serve_parser.add_argument("--log-level", default="info", 
                             choices=["debug", "info", "warning", "error"],
                             help="Log level")
    serve_parser.set_defaults(func=cmd_serve)
    
    # service command
    service_parser = subparsers.add_parser("service", help="Manage systemd service")
    service_subparsers = service_parser.add_subparsers(dest="service_command", 
                                                        help="Service action")
    
    install_parser = service_subparsers.add_parser("install", 
                                                    help="Install systemd service and Caddy config")
    install_parser.add_argument("--user", action="store_true", 
                               help="Install as user service (default: system service)")
    install_parser.add_argument("--port", type=int, default=58080, 
                               help="Internal port (default: 58080)")
    install_parser.add_argument("--caddy-port", type=int, default=8447, 
                               help="External Caddy port (default: 8447)")
    install_parser.add_argument("--frontdoor-port", type=int, default=8420,
                               help="Frontdoor auth port (default: 8420)")
    
    service_subparsers.add_parser("uninstall", help="Uninstall systemd service and Caddy config")
    service_subparsers.add_parser("start", help="Start the service")
    service_subparsers.add_parser("stop", help="Stop the service")
    service_subparsers.add_parser("restart", help="Restart the service")
    service_subparsers.add_parser("status", help="Show service status")
    
    logs_parser = service_subparsers.add_parser("logs", help="Show service logs")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    logs_parser.add_argument("-n", "--lines", type=int, default=50, help="Number of lines to show")
    
    service_parser.set_defaults(func=cmd_service)
    
    # upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade filebrowser to latest version")
    upgrade_parser.add_argument("--force", action="store_true", 
                               help="Force upgrade even if already up to date")
    upgrade_parser.set_defaults(func=cmd_upgrade)
    
    args = parser.parse_args()
    
    # Default to serve if no command specified
    if not args.command:
        args.command = "serve"
        args.host = "127.0.0.1"
        args.port = 58080
        args.log_level = "info"
        args.func = cmd_serve
    
    try:
        exit_code = args.func(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
