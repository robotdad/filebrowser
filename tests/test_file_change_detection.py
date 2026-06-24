"""Tests for Phase 1: On-disk file change detection.

Tests both backend and frontend implementation:
- Backend: PUT /api/files/content returns mtime + size
- Frontend: Pure change-detector.js module (hasChanged / classifyDiskState) executed in Node
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filebrowser.main import app
from filebrowser.auth import require_auth
from filebrowser.routes.files import get_fs
from filebrowser.services.filesystem import FilesystemService


# ─── Node helpers ────────────────────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
CHANGE_DETECTOR_JS = STATIC_DIR / "js" / "lib" / "change-detector.js"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS change-detector module"
)


def _run_js(script: str) -> str:
    """Execute ESM JS in Node and return stdout."""
    assert NODE is not None  # guarded by requires_node
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _has_changed(known, current) -> bool:
    """Call hasChanged() from change-detector.js in Node."""
    module_url = CHANGE_DETECTOR_JS.resolve().as_uri()
    script = (
        f"import {{ hasChanged }} from {json.dumps(module_url)};\n"
        f"const known = {json.dumps(known)};\n"
        f"const current = {json.dumps(current)};\n"
        f"process.stdout.write(String(hasChanged(known, current)));"
    )
    return _run_js(script) == "true"


def _classify(gone: bool, changed: bool, dirty: bool) -> dict:
    """Call classifyDiskState() from change-detector.js in Node."""
    module_url = CHANGE_DETECTOR_JS.resolve().as_uri()
    script = (
        f"import {{ classifyDiskState }} from {json.dumps(module_url)};\n"
        f"const result = classifyDiskState({{ gone: {json.dumps(gone)}, "
        f"changed: {json.dumps(changed)}, dirty: {json.dumps(dirty)} }});\n"
        f"process.stdout.write(JSON.stringify(result));"
    )
    raw = _run_js(script)
    return json.loads(raw)


# ─── Backend tests ───────────────────────────────────────────────────────────

class TestBackendFileChangeDetection:
    """Backend tests for file change detection support."""

    def test_put_content_returns_mtime_and_size(self, tmp_home):
        """PUT /api/files/content should return {ok, size, modified} after write."""
        file_path = tmp_home / "test.txt"
        file_path.write_text("original content")

        app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
        app.dependency_overrides[require_auth] = lambda: "testuser"

        client = TestClient(app)
        response = client.put(
            "/api/files/content",
            json={"path": "test.txt", "content": "new content"},
        )

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "size" in data
        assert "modified" in data
        assert isinstance(data["size"], int)
        assert data["size"] == len("new content")
        # modified should be ISO datetime string
        assert isinstance(data["modified"], str)
        assert "T" in data["modified"]  # ISO format

    def test_put_content_mtime_reflects_actual_write_time(self, tmp_home):
        """mtime in response should match the file's actual mtime after write."""
        file_path = tmp_home / "test.txt"
        file_path.write_text("original content")

        # Wait a bit to ensure mtime changes
        time.sleep(0.01)

        app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
        app.dependency_overrides[require_auth] = lambda: "testuser"

        client = TestClient(app)
        response = client.put(
            "/api/files/content",
            json={"path": "test.txt", "content": "new content"},
        )

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()

        # Check that the mtime from response matches file's actual mtime
        from datetime import datetime
        stat = file_path.stat()
        expected_mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        assert data["modified"] == expected_mtime

    def test_identical_mtime_content_change_detectable_via_size(self, tmp_home):
        """
        Acceptance criterion: Identical-mtime content change IS detected (via size).

        When a tool preserves mtime but changes bytes, size will differ.
        """
        file_path = tmp_home / "test.txt"
        file_path.write_text("original content")
        stat1 = file_path.stat()
        mtime1 = stat1.st_mtime
        size1 = stat1.st_size

        # Simulate a timestamp-preserving writer that changes content
        file_path.write_text("different content longer")
        # Set mtime back to original (timestamp-preserving tool)
        os.utime(file_path, (mtime1, mtime1))

        stat2 = file_path.stat()
        mtime2 = stat2.st_mtime
        size2 = stat2.st_size

        # mtime is identical, but size differs
        assert mtime1 == mtime2
        assert size1 != size2

        # Frontend's (mtime, size) != comparison will detect this

    def test_mtime_rollback_detected(self, tmp_home):
        """
        Acceptance criterion: mtime rollback (older timestamp) IS detected (!= comparison).

        Using != instead of > catches mtime rollbacks (restoring an older version).
        """
        file_path = tmp_home / "test.txt"
        file_path.write_text("version 1")
        time.sleep(0.01)
        stat1 = file_path.stat()
        mtime1 = stat1.st_mtime

        # Simulate advancing time
        time.sleep(0.01)
        file_path.write_text("version 2")
        stat2 = file_path.stat()
        mtime2 = stat2.st_mtime
        assert mtime2 > mtime1  # mtime advanced

        # Simulate rollback (restore older version with older mtime)
        file_path.write_text("version 1 restored")
        os.utime(file_path, (mtime1, mtime1))
        stat3 = file_path.stat()
        mtime3 = stat3.st_mtime

        # mtime rolled back
        assert mtime3 < mtime2
        assert mtime3 == mtime1

        # Frontend's != comparison catches this (mtime3 != mtime2)


# ─── Frontend behavioral tests (Node) ────────────────────────────────────────

@requires_node
class TestChangeDetectorModule:
    """Verify the change-detector.js module exists and exports the expected functions."""

    def test_module_file_exists(self):
        assert CHANGE_DETECTOR_JS.exists(), (
            f"change-detector.js not found at {CHANGE_DETECTOR_JS}"
        )

    def test_module_exports_both_functions(self):
        """Both hasChanged and classifyDiskState must be importable."""
        module_url = CHANGE_DETECTOR_JS.resolve().as_uri()
        script = (
            f"import {{ hasChanged, classifyDiskState }} from {json.dumps(module_url)};\n"
            f"process.stdout.write(typeof hasChanged + ',' + typeof classifyDiskState);"
        )
        output = _run_js(script)
        assert output == "function,function", f"Unexpected export types: {output!r}"


@requires_node
class TestHasChanged:
    """Behavioral tests for hasChanged()."""

    def test_identical_values_no_change(self):
        known = {"modified": "2024-01-01T10:00:00", "size": 100}
        current = {"modified": "2024-01-01T10:00:00", "size": 100}
        assert _has_changed(known, current) is False

    def test_different_size_same_mtime_detected(self):
        """Identical-mtime, different-size write is caught (AC1)."""
        known = {"modified": "2024-01-01T10:00:00", "size": 100}
        current = {"modified": "2024-01-01T10:00:00", "size": 200}
        assert _has_changed(known, current) is True

    def test_mtime_rollback_detected(self):
        """Older timestamp is detected — != catches rollbacks that > would miss (AC2)."""
        known = {"modified": "2024-01-01T10:05:00", "size": 100}
        current = {"modified": "2024-01-01T10:00:00", "size": 100}
        assert _has_changed(known, current) is True

    def test_newer_mtime_same_size_detected(self):
        known = {"modified": "2024-01-01T10:00:00", "size": 100}
        current = {"modified": "2024-01-01T10:05:00", "size": 100}
        assert _has_changed(known, current) is True

    def test_known_null_returns_false(self):
        """No known state → no change (first-time seed path)."""
        assert _has_changed(None, {"modified": "2024-01-01T10:00:00", "size": 100}) is False

    def test_current_null_returns_false(self):
        assert _has_changed({"modified": "2024-01-01T10:00:00", "size": 100}, None) is False


@requires_node
class TestClassifyDiskState:
    """Behavioral tests for classifyDiskState()."""

    def test_gone_file(self):
        """Gone file → {gone:true, reload:false, conflict:false}."""
        result = _classify(gone=True, changed=False, dirty=False)
        assert result == {"gone": True, "reload": False, "conflict": False}

    def test_gone_overrides_changed(self):
        """gone:true always wins regardless of changed/dirty."""
        result = _classify(gone=True, changed=True, dirty=True)
        assert result == {"gone": True, "reload": False, "conflict": False}

    def test_changed_clean_tab_auto_reload(self):
        """Changed on disk, clean tab → auto-reload (F1 fix)."""
        result = _classify(gone=False, changed=True, dirty=False)
        assert result == {"gone": False, "reload": True, "conflict": False}

    def test_changed_dirty_tab_conflict(self):
        """Changed on disk, dirty tab → conflict banner (F1 fix: no auto-reload over edits)."""
        result = _classify(gone=False, changed=True, dirty=True)
        assert result == {"gone": False, "reload": False, "conflict": True}

    def test_no_change_neutral(self):
        """No change → all false."""
        result = _classify(gone=False, changed=False, dirty=False)
        assert result == {"gone": False, "reload": False, "conflict": False}

    def test_no_change_dirty_tab_neutral(self):
        """No change even when dirty → neutral (tab is dirty but disk hasn't changed)."""
        result = _classify(gone=False, changed=False, dirty=True)
        assert result == {"gone": False, "reload": False, "conflict": False}

    def test_default_args_neutral(self):
        """classifyDiskState() with no args → neutral."""
        module_url = CHANGE_DETECTOR_JS.resolve().as_uri()
        script = (
            f"import {{ classifyDiskState }} from {json.dumps(module_url)};\n"
            f"process.stdout.write(JSON.stringify(classifyDiskState()));"
        )
        result = json.loads(_run_js(script))
        assert result == {"gone": False, "reload": False, "conflict": False}
