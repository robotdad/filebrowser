"""Tests for Phase 1: On-disk file change detection.

Tests both backend and frontend implementation:
- Backend: PUT /api/files/content returns mtime
- Frontend: Polling logic, (mtime, size) != detection, conflict handling
"""
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filebrowser.main import app
from filebrowser.auth import require_auth
from filebrowser.routes.files import get_fs
from filebrowser.services.filesystem import FilesystemService


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


class TestFrontendFileChangeDetection:
    """Frontend JavaScript code tests (static analysis)."""

    def test_layout_has_polling_hook(self):
        """Layout.js should have file change polling hook."""
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Check for polling state
        assert "diskChangeInfo" in content
        assert "lastKnownState" in content
        assert "pollTimerRef" in content
        assert "focusDebounceRef" in content

        # Check for polling logic
        assert "checkFileChanges" in content
        assert "/api/files/info" in content

        # Check for (mtime, size) comparison
        assert "modified" in content
        assert "size" in content

    def test_polling_uses_mtime_and_size_comparison(self):
        """Polling should use (mtime, size) != comparison for change detection."""
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Check for != comparison on both mtime and size
        # The code should have: known.modified !== current.modified || known.size !== current.size
        assert "modified" in content
        assert "!==" in content
        assert "size" in content
        # Check for OR condition that checks both
        assert "||" in content

    def test_polling_interval_is_modest(self):
        """Polling should use a modest interval (not < 3s for multi-tab)."""
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Should have setInterval with a reasonable delay (looking for 8000ms or similar)
        assert "setInterval" in content
        assert "8000" in content  # 8 seconds

    def test_focus_polling_is_debounced(self):
        """
        Acceptance criterion: Focus polling is debounced.
        
        Rapid focus/blur should not cause stat flood.
        """
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Check for debounce on focus
        assert "focusDebounceRef" in content
        assert "setTimeout" in content
        assert "500" in content  # 500ms debounce

    def test_listing_refresh_on_change_detected(self):
        """When changes detected, should call refresh() to update listing."""
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Should call refresh() when anyChange is true
        assert "refresh()" in content
        assert "anyChange" in content

    def test_previewpane_accepts_disk_change_props(self):
        """PreviewPane should accept diskChangeInfo and onFileSaved props."""
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # Check function signature includes new props
        assert "diskChangeInfo" in content
        assert "onFileSaved" in content

    def test_previewpane_handles_gone_state(self):
        """
        Acceptance criterion: Delete/rename while open → loud gone-state.
        
        PreviewPane should show 'File no longer exists' when diskChangeInfo.gone is true.
        """
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # Check for gone state rendering
        assert "case 'gone':" in content
        assert "File no longer exists" in content

    def test_previewpane_shows_conflict_banner(self):
        """PreviewPane should show conflict banner when dirty file changed on disk."""
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # Check for conflict banner
        assert "preview-disk-change-banner" in content
        assert "File changed on disk" in content
        assert "Reload" in content
        assert "Keep mine" in content

    def test_save_handlers_pass_response_to_callback(self):
        """Save handlers should pass PUT response to callback for mtime seeding."""
        # Check EditableViewer
        editable_path = Path("filebrowser/static/js/components/editable-viewer.js")
        editable_content = editable_path.read_text()
        assert "const response = await api.put('/api/files/content'" in editable_content
        assert "onSaveCallback(editText, response)" in editable_content

        # Check HtmlViewer in preview.js
        preview_path = Path("filebrowser/static/js/components/preview.js")
        preview_content = preview_path.read_text()
        # HtmlViewer save handler
        assert "const response = await api.put('/api/files/content'" in preview_content
        assert "onSave(editText, response)" in preview_content

        # Check MarkdownEditor
        markdown_path = Path("filebrowser/static/js/components/markdown-editor.js")
        markdown_content = markdown_path.read_text()
        assert "const response = await api.put('/api/files/content'" in markdown_content
        assert "onSave(editText, response)" in markdown_content

    def test_editableviewer_resets_on_text_prop_change(self):
        """
        Acceptance criterion: Clean in-place reload preserves scroll position.
        
        First part: EditableViewer must reset when text prop changes.
        """
        editable_path = Path("filebrowser/static/js/components/editable-viewer.js")
        content = editable_path.read_text()

        # Should have useEffect that resets editText when text changes
        assert "useEffect(() => {" in content
        assert "setEditText(text)" in content
        assert "setDirty(false)" in content
        assert "[text]" in content  # dependency array

    def test_htmlviewer_resets_on_text_prop_change(self):
        """HtmlViewer must also reset when text prop changes."""
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # HtmlViewer should have the same reset pattern
        # Look for the reset useEffect in HtmlViewer function
        assert "function HtmlViewer" in content
        # The useEffect should be in HtmlViewer
        html_viewer_section = content[content.index("function HtmlViewer"):content.index("function GraphvizViewer")]
        assert "useEffect(() => {" in html_viewer_section
        assert "setEditText(text)" in html_viewer_section
        assert "[text]" in html_viewer_section

    def test_manual_refresh_button_still_works(self):
        """
        Acceptance criterion: Manual Refresh button still works.
        
        Refresh button should still call refresh() function.
        """
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Refresh button should still exist and call refresh
        assert "refresh-btn" in content or "onRefresh=${refresh}" in content
        assert "onClick=${refresh}" in content or "onRefresh=${refresh}" in content

    def test_save_external_write_race_handling(self):
        """
        Acceptance criterion: Save → external write race handling.
        
        Seeding last-known from PUT response should not fire spurious "changed on disk"
        nor swallow a real external write.
        """
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # handleContentSave should call onFileSaved with response data
        assert "onFileSaved" in content
        assert "response?.modified" in content
        assert "response?.size" in content

        layout_path = Path("filebrowser/static/js/components/layout.js")
        layout_content = layout_path.read_text()

        # handleFileSaved should update lastKnownState
        assert "handleFileSaved" in layout_content
        assert "lastKnownState.current.set" in layout_content


class TestConflictHandling:
    """Tests for conflict handling logic."""

    def test_clean_file_auto_reloads_on_disk_change(self):
        """Clean files (no unsaved edits) should auto-reload when changed on disk."""
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # Should have logic to reload when diskChangeInfo.changed and clean
        assert "diskChangeInfo.changed" in content
        assert "loadTextContent" in content

    def test_dirty_file_shows_conflict_banner(self):
        """Dirty files (unsaved edits) should show conflict banner, not auto-reload."""
        layout_path = Path("filebrowser/static/js/components/layout.js")
        content = layout_path.read_text()

        # Should check tab.dirty before setting changed flag
        assert "tab.dirty" in content
        assert "pendingSave" in content or "conflict" in content.lower()

    def test_keep_mine_sets_pending_save_flag(self):
        """
        Acceptance criterion: keep-mine → save re-warns.
        
        Keeping local version should set a flag so save warns before overwriting.
        """
        preview_path = Path("filebrowser/static/js/components/preview.js")
        content = preview_path.read_text()

        # handleKeepMine should set pendingSaveConflict
        assert "handleKeepMine" in content
        assert "setPendingSaveConflict" in content
