"""Static and executable checks for authenticated favorites UI behavior."""

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
LAYOUT_FILE = REPO_ROOT / "filebrowser" / "static" / "js" / "components" / "layout.js"
CONTEXT_MENU_FILE = (
    REPO_ROOT / "filebrowser" / "static" / "js" / "components" / "context-menu.js"
)
HELPERS_FILE = REPO_ROOT / "filebrowser" / "static" / "js" / "favorites.js"
NODE_TEST_FILE = REPO_ROOT / "tests" / "browser" / "favorites-helper.test.js"
NODE = shutil.which("node")


def test_favorites_use_the_authenticated_api_not_legacy_local_storage():
    """The old shared browser key must remain completely untouched."""
    source = LAYOUT_FILE.read_text()

    assert "fb-favorites" not in source
    assert "loadFavorites: () => api.get('/api/favorites')" in source
    assert (
        "addFavorite: (physicalPath) => api.post('/api/favorites', { path: physicalPath })"
        in source
    )
    assert (
        "api.del(`/api/favorites?path=${encodeURIComponent(physicalPath)}`)"
        in source
    )


def test_favorites_ui_keeps_location_roots_synthesized_and_distinct():
    """Locations are loaded independently and joined only for rendering."""
    source = LAYOUT_FILE.read_text()

    assert "api.get('/api/locations')" in source
    assert "activeExternalLocations" in source
    assert "mergeFavoritePaths(mappedFavoritePaths, activeExternalLocations)" in source
    assert "favoriteVirtualToPhysicalPath(" in source
    assert "mapFavoritePaths(" in source


def test_favorite_reordering_is_client_only():
    """Drag ordering changes only the rendered component state."""
    source = LAYOUT_FILE.read_text()
    start = source.index("const reorderFavorite")
    end = source.index("// Must be memoized", start)
    reorder_source = source[start:end]

    assert "setFavoriteOrder(next)" in reorder_source
    assert "api." not in reorder_source


def test_exact_external_root_has_a_remove_location_context_action():
    """A location root cannot be confused with a personal external child pin."""
    layout_source = LAYOUT_FILE.read_text()
    context_source = CONTEXT_MENU_FILE.read_text()

    assert "externalLocationForFavoriteRoot(contextMenu.path, activeExternalLocations)" in layout_source
    assert "isExternalRoot=${contextIsExternalRoot}" in layout_source
    assert "isExternalRoot" in context_source
    assert "Remove location" in context_source


def test_favorites_helper_has_no_browser_storage_state():
    """The favorites helper remains a pure API/path-state module."""
    source = HELPERS_FILE.read_text()

    assert "localStorage" not in source
    assert "createFavoritesController" in source
    assert "favoritePhysicalToVirtualPath" in source
    assert "favoriteVirtualToPhysicalPath" in source


@pytest.mark.skipif(NODE is None, reason="node is required to execute favorites helper tests")
def test_favorites_helper_node_tests_pass():
    """Exercise mapping, loading, error, duplicate, and stale-identity behavior."""
    assert NODE is not None
    result = subprocess.run(
        [NODE, str(NODE_TEST_FILE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"favorites Node tests failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "favorites helper tests passed" in result.stdout