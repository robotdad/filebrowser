"""Regression tests for the ImageViewer tall/extreme-aspect-ratio SVG fix.

The fit-to-window math was extracted from components/preview.js into the pure
module static/js/lib/fit-scale.js so it can be exercised with real inputs instead
of scanned for source patterns. The tests below actually execute the function via
Node and assert its numeric output (the previous version of this file only
regex-matched the JS source, which passed even when the logic was wrong).

Browser-level rendering coverage (does a tall SVG actually paint non-blank?) lives
in the reality-check acceptance suite (tests/reality-check/acceptance/), which
drives a real browser against the DTU.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
FIT_SCALE_JS = STATIC_DIR / "js" / "lib" / "fit-scale.js"

NODE = shutil.which("node")

requires_node = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the JS fit-scale module"
)


def _fit_scale(canvas_w, canvas_h, img_w, img_h) -> float:
    """Execute computeFitScale() from fit-scale.js in Node and return the result."""
    assert NODE is not None  # guarded by requires_node on the test classes
    module_url = FIT_SCALE_JS.resolve().as_uri()
    script = (
        f"import {{ computeFitScale }} from {json.dumps(module_url)};\n"
        f"process.stdout.write(String(computeFitScale("
        f"{canvas_w}, {canvas_h}, {img_w}, {img_h})));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


@requires_node
class TestComputeFitScale:
    """Behavioral tests: run the real JS function and check the returned scale."""

    def test_zero_natural_height_returns_1(self):
        """pt-unit SVGs report naturalHeight=0; must fall back to 1 (not Infinity/blank)."""
        assert _fit_scale(800, 600, 100, 0) == 1.0

    def test_zero_natural_width_returns_1(self):
        assert _fit_scale(800, 600, 0, 175) == 1.0

    def test_zero_canvas_height_returns_1(self):
        """Incomplete flex layout reports clientHeight=0; must fall back to 1."""
        assert _fit_scale(800, 0, 100, 175) == 1.0

    def test_zero_canvas_width_returns_1(self):
        assert _fit_scale(0, 600, 100, 175) == 1.0

    def test_tall_svg_is_not_upscaled(self):
        """A small/tall SVG (100x175) in a large canvas fits at 1x (never upscale)."""
        # min(800/100=8, 600/175~3.43, 1) -> 1
        assert _fit_scale(800, 600, 100, 175) == 1.0

    def test_large_image_scales_down_to_fit(self):
        """A 4000x3000 image in an 800x600 canvas scales to 0.2."""
        assert _fit_scale(800, 600, 4000, 3000) == pytest.approx(0.2)

    def test_extremely_large_image_clamps_to_floor(self):
        """Scale never drops below the 0.1 viewer floor."""
        assert _fit_scale(800, 600, 100000, 100000) == pytest.approx(0.1)

    def test_normal_small_image_fits_at_1(self):
        """A 400x300 image in an 800x600 canvas is not upscaled."""
        assert _fit_scale(800, 600, 400, 300) == 1.0


class TestFitScaleModule:
    """The pure module must exist and export the function the viewer depends on."""

    def test_module_exists_and_exports_function(self):
        assert FIT_SCALE_JS.exists(), "static/js/lib/fit-scale.js is missing"
        source = FIT_SCALE_JS.read_text()
        assert "export function computeFitScale" in source


class TestSvgFixtures:
    def test_tall_svg_fixture_exists(self, tmp_home):
        """conftest.py must include a tall SVG fixture for regression testing."""
        tall_svg_path = tmp_home / "images" / "tall.svg"
        assert tall_svg_path.exists(), (
            "Tall SVG fixture (images/tall.svg) missing from tmp_home fixture"
        )

        content = tall_svg_path.read_text()
        # Verify it's a valid SVG
        assert "<svg" in content and "</svg>" in content, (
            "tall.svg must be a valid SVG file"
        )

        # Verify it uses pt dimensions (which can trigger naturalHeight=0)
        assert "pt" in content, (
            "tall.svg should use pt dimensions to test naturalHeight=0 edge case"
        )

    def test_tall_svg_has_extreme_aspect_ratio(self, tmp_home):
        """Tall SVG fixture must have an extreme (tall) aspect ratio."""
        tall_svg_path = tmp_home / "images" / "tall.svg"
        content = tall_svg_path.read_text()

        # Extract width and height attributes
        width_match = re.search(r'width="(\d+)', content)
        height_match = re.search(r'height="(\d+)', content)

        assert width_match and height_match, (
            "tall.svg must have explicit width and height attributes"
        )

        width = int(width_match.group(1))
        height = int(height_match.group(1))

        # Verify aspect ratio is tall (height > width)
        assert height > width, f"tall.svg must be taller than wide (got {width}x{height})"

        # Verify it's significantly tall (aspect ratio > 1.5)
        aspect_ratio = height / width
        assert aspect_ratio > 1.5, (
            f"tall.svg must have extreme aspect ratio (got {aspect_ratio:.2f}, need > 1.5)"
        )
