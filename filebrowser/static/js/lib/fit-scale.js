// Pure fit-to-window scale calculation for the image / SVG viewer.
//
// Extracted from components/preview.js so the math can be unit-tested without a
// DOM. Given a canvas (viewport) size and an image's natural size, it returns
// the zoom scale that fits the image inside the canvas, never upscaling past 1x,
// clamped to the viewer's allowed zoom range [0.1, 20].
//
// Guards (the reason this fix exists):
//   - imgW/imgH may be 0 for SVGs declared in `pt` units (the browser reports
//     naturalWidth/naturalHeight as 0) -> would divide by zero -> Infinity ->
//     image blown up to max zoom -> appears blank. Guard returns 1.
//   - canvasW/canvasH may be 0 when the flex layout has not completed yet on a
//     fast/cached load. Guard returns 1 so the image shows at natural size
//     instead of collapsing.
export function computeFitScale(canvasW, canvasH, imgW, imgH) {
    if (!imgW || !imgH) return 1;
    if (!canvasW || !canvasH) return 1;
    const scale = Math.min(
        canvasW / imgW,
        canvasH / imgH,
        1, // never upscale small images
    );
    // clampZoom: keep within the viewer's allowed zoom range.
    return Math.min(Math.max(scale, 0.1), 20);
}
