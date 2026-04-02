#!/usr/bin/env python3
"""
filebrowser brand asset renderer
Usage: python3 render-brand-assets.py [--force] [--workdir PATH]

Renders the filebrowser icon design to PNG/ICO at all required sizes.
Requires: Pillow (pip install Pillow)
"""

import argparse
import struct
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("[ERROR] Pillow not installed. Run: pip install Pillow")

# ──────────────────────────────────────────────────────────────────────────────
# Argument parsing
# ──────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Render filebrowser brand assets")
parser.add_argument("--force", action="store_true", help="Re-render even if output exists")
parser.add_argument("--workdir", default=None, help="Base directory (default: parent of script)")
args = parser.parse_args()

WORKDIR = Path(args.workdir).resolve() if args.workdir else Path(__file__).parent.parent
ASSETS = WORKDIR / "assets" / "branding"
FORCE = args.force

if not ASSETS.exists():
    raise SystemExit(f"[ERROR] Cannot find {ASSETS}")

print(f"[workdir] {WORKDIR}")
print(f"[assets]  {ASSETS}")

# ──────────────────────────────────────────────────────────────────────────────
# Design constants (all in 64×64 design space)
# ──────────────────────────────────────────────────────────────────────────────

CORNER_RATIO  = 2.059 / 64
BORDER_RATIO  = 2.745 / 64
HEADER_BOTTOM = 15.786 / 64
BODY_START    = 18.188 / 64

DOT_RADIUS = 2.917 / 64
DOT_Y      = 9.265 / 64
DOT_X1     = 9.265 / 64
DOT_X2     = 18.531 / 64
DOT_X3     = 27.796 / 64

# Sidebar (design coords)
SIDEBAR_X1 = 4.5  / 64
SIDEBAR_X2 = 19.5 / 64
SIDEBAR_Y1 = 21.0 / 64
SIDEBAR_Y2 = 58.0 / 64

# Tree item rows (y centres), all at same x range
TREE_ROWS = [26.0, 32.0, 38.0, 44.0]      # design-space y of each bar top
TREE_X1   = [7.0,  7.0,  9.0,  9.0]       # indent level
TREE_X2   = [16.0, 14.0, 16.0, 14.0]
TREE_H    = 2.0 / 64
TREE_ALPHA = [0.85, 0.55, 0.40, 0.30]

# Sidebar/content divider
DIV_X     = 20.0 / 64
DIV_W     = 1.0  / 64

# Content area
CONTENT_X1 = 22.5 / 64
CONTENT_X2 = 59.5 / 64

# File squares: 3×3 grid, 7px size, 11px pitch (7+4 gap)
FS_ORIGIN_X = 26.0 / 64
FS_ORIGIN_Y = 25.0 / 64
FS_SIZE     = 7.0  / 64
FS_PITCH    = 11.0 / 64   # column/row pitch
FS_RADIUS   = 1.5  / 64   # corner rounding of each square

# 3×3 color grid (row-major)
FILE_COLORS = [
    "#3b82f6", "#f59e0b", "#10b981",   # row 0: folder, image, code
    "#8b5cf6", "#ef4444", "#06b6d4",   # row 1: markdown, video, graphviz
    "#ec4899", "#6b7280", "#007AFF",   # row 2: audio, default, blue accent
]

# ──────────────────────────────────────────────────────────────────────────────
# Color palettes
# ──────────────────────────────────────────────────────────────────────────────

def h(hex_str):
    s = hex_str.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))

DARK = dict(
    bg           = h("#0D1117"),
    chrome       = h("#FFFFFF"),
    dot1         = h("#FF9500"),
    dot2         = h("#FFFFFF"),
    dot3         = h("#007AFF"),
    sidebar_fill = h("#1A1F2B"),
    tree_color   = h("#FFFFFF"),
    div_alpha    = 0.22,
    content_fill = h("#1A1F2B"),
)

LIGHT = dict(
    bg           = h("#F5F5F7"),
    chrome       = h("#1D1D1F"),
    dot1         = h("#FF9500"),
    dot2         = h("#8E8E93"),
    dot3         = h("#007AFF"),
    sidebar_fill = h("#E5E5EA"),
    tree_color   = h("#1D1D1F"),
    div_alpha    = 0.15,
    content_fill = h("#FFFFFF"),
)

# ──────────────────────────────────────────────────────────────────────────────
# Rendering
# ──────────────────────────────────────────────────────────────────────────────

OVERSAMPLE = 4


def rgba(color, alpha=255):
    return color + (alpha,)


def render_icon(size, palette, oversample=OVERSAMPLE):
    S = size * oversample
    p = palette
    sf = S / 64.0

    img  = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    corner_r = max(1, round(CORNER_RATIO * S))
    border_w = max(1, round(BORDER_RATIO * S))
    hdr_bot  = round(HEADER_BOTTOM * S)
    body_top = round(BODY_START * S)

    # Chrome base (fills everything — white/dark)
    draw.rounded_rectangle([0, 0, S - 1, S - 1], radius=corner_r, fill=rgba(p["chrome"]))

    # Header fill (dark background inside header area)
    draw.rectangle([border_w, border_w, S - border_w, hdr_bot], fill=rgba(p["bg"]))

    # Body fill (dark background inside body area)
    draw.rectangle([border_w, body_top, S - border_w, S - border_w], fill=rgba(p["bg"]))

    # Header dots
    dot_r = max(1, round(DOT_RADIUS * S))
    for cx_ratio, key in [(DOT_X1, "dot1"), (DOT_X2, "dot2"), (DOT_X3, "dot3")]:
        cx = round(cx_ratio * S)
        cy = round(DOT_Y * S)
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=rgba(p[key]))

    # ── Sidebar panel ──
    sx1 = round(SIDEBAR_X1 * S)
    sx2 = round(SIDEBAR_X2 * S)
    sy1 = round(SIDEBAR_Y1 * S)
    sy2 = round(SIDEBAR_Y2 * S)
    draw.rounded_rectangle([sx1, sy1, sx2, sy2], radius=max(1, round(1/64 * S)), fill=rgba(p["sidebar_fill"]))

    # Sidebar tree items
    bar_h = max(1, round(TREE_H * S))
    for i, (row_y, tx1, tx2, alpha) in enumerate(zip(TREE_ROWS, TREE_X1, TREE_X2, TREE_ALPHA)):
        bx1 = round(tx1 / 64 * S)
        bx2 = round(tx2 / 64 * S)
        by1 = round(row_y / 64 * S)
        by2 = by1 + bar_h
        a = int(alpha * 255)
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=max(1, round(1/64 * S)), fill=rgba(p["tree_color"], a))

    # Sidebar/content divider
    div_x = round(DIV_X * S)
    div_w = max(1, round(DIV_W * S))
    div_a = int(p["div_alpha"] * 255)
    draw.rectangle([div_x, sy1, div_x + div_w, sy2], fill=rgba(p["chrome"], div_a))

    # Content panel
    cx1 = round(CONTENT_X1 * S)
    cx2 = round(CONTENT_X2 * S)
    draw.rounded_rectangle([cx1, sy1, cx2, sy2], radius=max(1, round(1/64 * S)), fill=rgba(p["content_fill"]))

    # File-type squares (3×3 grid)
    fsz = max(2, round(FS_SIZE * S))
    fsr = max(1, round(FS_RADIUS * S))
    fsp = round(FS_PITCH * S)
    for idx, color_hex in enumerate(FILE_COLORS):
        col = idx % 3
        row = idx // 3
        fx1 = round(FS_ORIGIN_X * S) + col * fsp
        fy1 = round(FS_ORIGIN_Y * S) + row * fsp
        draw.rounded_rectangle([fx1, fy1, fx1 + fsz, fy1 + fsz], radius=fsr, fill=rgba(h(color_hex)))

    # Rounded-corner mask
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=corner_r, fill=255)
    img.putalpha(mask)

    return img.resize((size, size), Image.Resampling.LANCZOS)


# ──────────────────────────────────────────────────────────────────────────────
# ICO builder
# ──────────────────────────────────────────────────────────────────────────────

def _png_bytes(img):
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def make_ico(images):
    import io
    n = len(images)
    png_chunks = [_png_bytes(img) for img in images]
    header_size = 6 + 16 * n
    data_offset = header_size
    entries = []
    for img, data in zip(images, png_chunks):
        w, h_ = img.size
        entries.append((w, h_, data_offset, len(data)))
        data_offset += len(data)
    buf = io.BytesIO()
    buf.write(struct.pack("<HHH", 0, 1, n))
    for (w, h_, offset, size) in entries:
        wbyte = w if w < 256 else 0
        hbyte = h_ if h_ < 256 else 0
        buf.write(struct.pack("<BBBBHHII", wbyte, hbyte, 0, 0, 1, 32, size, offset))
    for data in png_chunks:
        buf.write(data)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────────────

ICONS_DIR    = ASSETS / "icons"
FAVICONS_DIR = ASSETS / "favicons"
PWA_DIR      = ASSETS / "pwa"
LOCKUP_DIR   = ASSETS / "lockup"

for d in [ICONS_DIR, FAVICONS_DIR, PWA_DIR, LOCKUP_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def save(img, path):
    p = Path(path)
    if p.exists() and not FORCE:
        print(f"  [skip] {p.relative_to(WORKDIR)}")
        return
    img.save(str(p), optimize=True)
    kb = p.stat().st_size // 1024
    print(f"  [ok]   {p.relative_to(WORKDIR)} ({kb}KB)")


def save_ico(images, path):
    p = Path(path)
    if p.exists() and not FORCE:
        print(f"  [skip] {p.relative_to(WORKDIR)}")
        return
    p.write_bytes(make_ico(images))
    kb = p.stat().st_size // 1024
    print(f"  [ok]   {p.relative_to(WORKDIR)} ({kb}KB)")


print("\n── Icon sizes ──────────────────────────────────────────────────────────")
for sz in [16, 22, 24, 32, 48, 64, 128, 192, 256, 512, 1024]:
    save(render_icon(sz, DARK), ICONS_DIR / f"filebrowser-icon-{sz}.png")

print("\n── Favicons ────────────────────────────────────────────────────────────")
fav16  = render_icon(16,  DARK)
fav32  = render_icon(32,  DARK)
fav48  = render_icon(48,  DARK)
fav180 = render_icon(180, LIGHT)
save(fav16,  FAVICONS_DIR / "favicon-16.png")
save(fav32,  FAVICONS_DIR / "favicon-32.png")
save(fav48,  FAVICONS_DIR / "favicon-48.png")
save(fav180, FAVICONS_DIR / "apple-touch-icon.png")
save_ico([fav16, fav32, fav48], FAVICONS_DIR / "favicon.ico")

print("\n── PWA ─────────────────────────────────────────────────────────────────")
save(render_icon(192, DARK), PWA_DIR / "pwa-192.png")
save(render_icon(512, DARK), PWA_DIR / "pwa-512.png")

print("\n── Lockup thumbnails ───────────────────────────────────────────────────")
for h_px in [32, 64]:
    save(render_icon(h_px, DARK),  LOCKUP_DIR / f"lockup-on-dark-{h_px}.png")
    save(render_icon(h_px, LIGHT), LOCKUP_DIR / f"lockup-on-light-{h_px}.png")

print("\n── Done ────────────────────────────────────────────────────────────────")
print(f"All assets written to {ASSETS.relative_to(WORKDIR)}/")
