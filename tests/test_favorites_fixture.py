"""Safety checks for the standalone favorites browser fixture."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.fixtures.favorites import setup_env


REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SERVER = REPO_ROOT / "tests" / "fixtures" / "favorites" / "run_server.sh"
ACTUAL_TEST_HOME = REPO_ROOT / ".work" / "test-home"

@pytest.fixture(autouse=True)
def work_directory():
    """A clean checkout need not have generated browser evidence yet."""
    (REPO_ROOT / ".work").mkdir(exist_ok=True)


@pytest.fixture
def fixture_scratch():
    with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work") as directory:
        yield Path(directory)


def _tree_contents(path: Path) -> tuple[tuple[str, bytes | None], ...] | None:
    """Capture files without writing to the fixture's actual test HOME."""
    if not path.exists():
        return None
    return tuple(
        (str(item.relative_to(path)), item.read_bytes() if item.is_file() else None)
        for item in sorted(path.rglob("*"))
    )


def _import_fixture(
    home: Path, data: Path, code: str = "import tests.fixtures.favorites.fixture_app"
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "FILEBROWSER_DATA_DIR": str(data),
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_rejects_directories_outside_worktree_without_touching_test_home(
    tmp_path: Path,
) -> None:
    """An import must reject non-.work paths before it can affect real fixture data."""
    outside_home = tmp_path / "home"
    outside_data = tmp_path / "data"
    outside_home.mkdir()
    outside_data.mkdir()
    before = _tree_contents(ACTUAL_TEST_HOME)

    result = _import_fixture(outside_home, outside_data)

    assert result.returncode != 0
    assert "must be a descendant of this worktree's .work directory" in result.stderr
    assert _tree_contents(ACTUAL_TEST_HOME) == before


def test_fixture_rejects_work_directory_itself() -> None:
    """The .work container is not itself a permitted fixture directory."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work") as fixture_root:
        data = Path(fixture_root) / "data"
        data.mkdir()
        result = _import_fixture(REPO_ROOT / ".work", data)

    assert result.returncode != 0
    assert "must be a descendant of this worktree's .work directory" in result.stderr


def test_fixture_import_uses_worktree_package_and_dummy_auth_only() -> None:
    """A subprocess import validates its package source without starting a server."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work") as fixture_root:
        fixture_root_path = Path(fixture_root)
        home = fixture_root_path / "home"
        data = fixture_root_path / "data"
        home.mkdir()
        data.mkdir()
        result = _import_fixture(
            home,
            data,
            "\n".join(
                (
                    "from tests.fixtures.favorites import fixture_app",
                    "from filebrowser.config import settings",
                    "from filebrowser.routes import auth",
                    'assert fixture_app.dummy_authenticate_pam("alice", "password123")',
                    'assert fixture_app.dummy_authenticate_pam("bob", "password123")',
                    'assert not fixture_app.dummy_authenticate_pam("alice", "wrong")',
                    'assert not fixture_app.dummy_authenticate_pam("other", "password123")',
                    "assert auth.authenticate_pam is fixture_app.dummy_authenticate_pam",
                    "assert settings.home_dir == fixture_app.resolved_home",
                    "assert settings.data_dir == fixture_app.resolved_data",
                    "assert settings.terminal_enabled is False",
                    "assert settings.secure_cookies is False",
                    'print(f"MODULE={fixture_app.FILEBROWSER_MODULE_PATH}")',
                )
            ),
        )

    assert result.returncode == 0, result.stderr
    assert f"MODULE={REPO_ROOT / 'filebrowser' / '__init__.py'}" in result.stdout


def test_setup_preserves_the_odd_legacy_seed_on_repeat(fixture_scratch: Path) -> None:
    """Repeated setup is safe and retains the deliberately odd legacy JSON formatting."""
    setup_env.setup_test_environment(fixture_scratch)
    legacy_seed = (fixture_scratch / "test-data" / "favorites.json").read_text(encoding="utf-8")
    setup_env.setup_test_environment(fixture_scratch)

    assert '"favorites":   [' in legacy_seed
    assert (fixture_scratch / "test-data" / "favorites.json").read_text(encoding="utf-8") == legacy_seed


def test_setup_preserves_generated_favorites_and_location_state(fixture_scratch: Path) -> None:
    """Setup must never erase the state used by the persistence oracle."""
    setup_env.setup_test_environment(fixture_scratch)
    favorites_dir = fixture_scratch / "test-data" / "favorites-users"
    favorites_dir.mkdir()
    (favorites_dir / "alice.json").write_text("{}", encoding="utf-8")
    (fixture_scratch / "test-data" / "locations.json").write_text("{}", encoding="utf-8")

    setup_env.setup_test_environment(fixture_scratch)

    assert (favorites_dir / "alice.json").read_text() == "{}"
    assert (fixture_scratch / "test-data" / "locations.json").read_text() == "{}"


def test_setup_rejects_outside_paths_and_symlinks(tmp_path, fixture_scratch):
    with pytest.raises(ValueError, match="within"):
        setup_env.setup_test_environment(tmp_path)
    (fixture_scratch / "test-home").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        setup_env.setup_test_environment(fixture_scratch)
    assert list(tmp_path.iterdir()) == []


def test_launch_script_is_portable_and_delegates_to_fixture_main() -> None:
    """The launcher contains no machine path and cannot bypass the loopback guard."""
    source = RUN_SERVER.read_text(encoding="utf-8")

    assert "/home/" not in source
    assert 'PYTHON_BIN="${PYTHON_BIN:-python3}"' in source
    assert 'FILEBROWSER_TEST_PORT="${FILEBROWSER_TEST_PORT:-58180}"' in source
    assert "PYTHONDONTWRITEBYTECODE=1" in source
    assert "-m tests.fixtures.favorites.fixture_app" in source
    assert "-m uvicorn" not in source
