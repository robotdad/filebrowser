"""Isolated fixture application for favorites browser testing."""

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WORK_DIR = REPO_ROOT / ".work"
FIXTURE_SECRET_KEY = "fixture-only-dummy-signing-secret"
DUMMY_CREDENTIALS = {
    "alice": "password123",
    "bob": "password123",
}


def _is_work_descendant(path: Path) -> bool:
    """Return whether *path* is below this worktree's .work directory."""
    return path != WORK_DIR and path.is_relative_to(WORK_DIR)


def _require_isolated_directories() -> tuple[Path, Path]:
    """Validate the explicit, separate fixture HOME and data directories."""
    home_env = os.environ.get("HOME")
    data_env = os.environ.get("FILEBROWSER_DATA_DIR")
    if not home_env or not data_env:
        raise RuntimeError(
            "Explicit fixture HOME and FILEBROWSER_DATA_DIR environment variables are required."
        )

    home_dir = Path(home_env).resolve()
    data_dir = Path(data_env).resolve()
    for name, path in (("HOME", home_dir), ("FILEBROWSER_DATA_DIR", data_dir)):
        if not path.is_dir():
            raise RuntimeError(f"Fixture {name} must be an existing directory: {path}")
        if not _is_work_descendant(path):
            raise RuntimeError(
                f"Fixture {name} must be a descendant of this worktree's .work directory: "
                f"{path}"
            )

    if (
        home_dir == data_dir
        or home_dir.is_relative_to(data_dir)
        or data_dir.is_relative_to(home_dir)
    ):
        raise RuntimeError("Fixture HOME and FILEBROWSER_DATA_DIR must not overlap.")
    return home_dir, data_dir


resolved_home, resolved_data = _require_isolated_directories()

# The fixture never inherits a potentially real signing key or unsafe runtime flags.
os.environ["FILEBROWSER_SECRET_KEY"] = FIXTURE_SECRET_KEY
os.environ["FILEBROWSER_TERMINAL_ENABLED"] = "false"
os.environ["FILEBROWSER_SECURE_COOKIES"] = "false"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import filebrowser  # noqa: E402


FILEBROWSER_MODULE_PATH = Path(filebrowser.__file__).resolve()
EXPECTED_FILEBROWSER_PACKAGE = (REPO_ROOT / "filebrowser").resolve()
if FILEBROWSER_MODULE_PATH.parent != EXPECTED_FILEBROWSER_PACKAGE:
    raise RuntimeError(
        "Fixture imported filebrowser from outside this worktree: "
        f"{FILEBROWSER_MODULE_PATH}"
    )

from filebrowser.config import settings  # noqa: E402
from filebrowser.routes import auth as auth_route  # noqa: E402

settings.home_dir = resolved_home
settings.data_dir = resolved_data
settings.secret_key = FIXTURE_SECRET_KEY
settings.terminal_enabled = False
settings.secure_cookies = False


def dummy_authenticate_pam(username: str, password: str) -> bool:
    """Authenticate only the two fixture identities."""
    return DUMMY_CREDENTIALS.get(username) == password


# Patch only the function looked up by the real auth route.
auth_route.authenticate_pam = dummy_authenticate_pam

from filebrowser.main import app  # noqa: E402


def main() -> None:
    """Run the real application with a loopback-only fixture binding."""
    import uvicorn

    parser = argparse.ArgumentParser(description="Run isolated favorites fixture server")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind host")
    parser.add_argument("--port", type=int, default=58180, help="Loopback bind port")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise ValueError(f"Only loopback host allowed, got {args.host}")

    print(f"Fixture filebrowser module: {FILEBROWSER_MODULE_PATH}", flush=True)
    print(f"Starting isolated fixture server on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
