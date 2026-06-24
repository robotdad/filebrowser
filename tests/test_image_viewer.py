"""Static regression tests for ImageViewer tall/extreme-aspect-ratio SVG bug fix.

These tests verify that the ImageViewer component correctly handles tall SVGs
and extreme aspect ratios by ensuring proper guards and timing controls are in place.
"""

import re
from functools import lru_cache
from pathlib import Path

STATIC_DIR = Path(__file__).parent.parent / "filebrowser" / "static"
PREVIEW_JS = STATIC_DIR / "js" / "components" / "preview.js"


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_JS.read_text()


class TestComputeFitScale:
    def test_guards_natural_height(self):
        """computeFitScale must guard img.naturalHeight to prevent division by zero."""
        preview = read_preview()
        # Find the computeFitScale function
        compute_fit_scale_match = re.search(
            r'const computeFitScale = \(\) => \{(.*?)\n    \};',
            preview,
            re.DOTALL
        )
        assert compute_fit_scale_match, "computeFitScale function not found"
        
        function_body = compute_fit_scale_match.group(1)
        # Verify that naturalHeight is checked
        assert re.search(r'!img\.naturalHeight', function_body), (
            "computeFitScale must guard against zero/missing img.naturalHeight"
        )

    def test_guards_canvas_client_height(self):
        """computeFitScale must guard canvas.clientHeight to handle incomplete layout."""
        preview = read_preview()
        compute_fit_scale_match = re.search(
            r'const computeFitScale = \(\) => \{(.*?)\n    \};',
            preview,
            re.DOTALL
        )
        assert compute_fit_scale_match, "computeFitScale function not found"
        
        function_body = compute_fit_scale_match.group(1)
        # Verify that clientHeight is checked
        assert re.search(r'!canvas\.clientHeight', function_body), (
            "computeFitScale must guard against zero canvas.clientHeight (incomplete flex layout)"
        )

    def test_guards_canvas_client_width(self):
        """computeFitScale must guard canvas.clientWidth for consistency."""
        preview = read_preview()
        compute_fit_scale_match = re.search(
            r'const computeFitScale = \(\) => \{(.*?)\n    \};',
            preview,
            re.DOTALL
        )
        assert compute_fit_scale_match, "computeFitScale function not found"
        
        function_body = compute_fit_scale_match.group(1)
        # Verify that clientWidth is checked
        assert re.search(r'!canvas\.clientWidth', function_body), (
            "computeFitScale must guard against zero canvas.clientWidth"
        )


class TestHandleImageLoad:
    def test_uses_request_animation_frame(self):
        """handleImageLoad must defer computeFitScale via requestAnimationFrame."""
        preview = read_preview()
        # Find the handleImageLoad function
        handle_image_load_match = re.search(
            r'const handleImageLoad = \(\) => \{(.*?)\n    \};',
            preview,
            re.DOTALL
        )
        assert handle_image_load_match, "handleImageLoad function not found"
        
        function_body = handle_image_load_match.group(1)
        # Verify requestAnimationFrame is used
        assert 'requestAnimationFrame' in function_body, (
            "handleImageLoad must use requestAnimationFrame to defer scale computation"
        )

    def test_defers_compute_fit_scale(self):
        """handleImageLoad must call computeFitScale inside requestAnimationFrame."""
        preview = read_preview()
        handle_image_load_match = re.search(
            r'const handleImageLoad = \(\) => \{(.*?)\n    \};',
            preview,
            re.DOTALL
        )
        assert handle_image_load_match, "handleImageLoad function not found"
        
        function_body = handle_image_load_match.group(1)
        # Verify computeFitScale is called inside the requestAnimationFrame callback
        # The pattern should match: requestAnimationFrame(() => { ... computeFitScale() ... })
        assert re.search(
            r'requestAnimationFrame\(.*?computeFitScale\(',
            function_body,
            re.DOTALL
        ), (
            "computeFitScale call must be inside requestAnimationFrame callback"
        )


class TestSvgFixtures:
    def test_tall_svg_fixture_exists(self, tmp_home):
        """conftest.py must include a tall SVG fixture for regression testing."""
        tall_svg_path = tmp_home / "images" / "tall.svg"
        assert tall_svg_path.exists(), (
            "Tall SVG fixture (images/tall.svg) missing from tmp_home fixture"
        )
        
        content = tall_svg_path.read_text()
        # Verify it's a valid SVG
        assert '<svg' in content and '</svg>' in content, (
            "tall.svg must be a valid SVG file"
        )
        
        # Verify it uses pt dimensions (which can trigger naturalHeight=0)
        assert 'pt' in content, (
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
        assert height > width, (
            f"tall.svg must be taller than wide (got {width}x{height})"
        )
        
        # Verify it's significantly tall (aspect ratio > 1.5)
        aspect_ratio = height / width
        assert aspect_ratio > 1.5, (
            f"tall.svg must have extreme aspect ratio (got {aspect_ratio:.2f}, need > 1.5)"
        )
