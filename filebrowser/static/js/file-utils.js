/**
 * file-utils.js — Shared file type, icon, and formatting utilities.
 *
 * Single source of truth for all file category, icon, and display logic
 * used by preview.js, tree.js, and command-palette.js.
 */

// ---------------------------------------------------------------------------
// File categories
// NOTE: .html/.htm live in 'html', NOT in 'code'.
// ---------------------------------------------------------------------------

export const FILE_CATEGORIES = {
    text:     ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
    code:     ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.css'],
    html:     ['.html', '.htm'],
    markdown: ['.md'],
    image:    ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'],
    audio:    ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'],
    video:    ['.mp4', '.webm', '.mkv', '.mov', '.avi'],
    pdf:      ['.pdf'],
    graphviz: ['.dot', '.gv'],
};

// Map category → icon descriptor (icon class, CSS class)
const CATEGORY_ICONS = {
    text:     { icon: 'ph-file-text',  cls: 'file-icon-text'     },
    code:     { icon: 'ph-code',       cls: 'file-icon-code'      },
    html:     { icon: 'ph-code',       cls: 'file-icon-code'      },
    markdown: { icon: 'ph-article',    cls: 'file-icon-markdown'  },
    image:    { icon: 'ph-image',      cls: 'file-icon-image'     },
    audio:    { icon: 'ph-music-note', cls: 'file-icon-audio'     },
    video:    { icon: 'ph-film-strip', cls: 'file-icon-video'     },
    pdf:      { icon: 'ph-file-pdf',   cls: 'file-icon-pdf'       },
    graphviz: { icon: 'ph-graph',      cls: 'file-icon-graphviz'  },
};

// ---------------------------------------------------------------------------
// Category lookup
// ---------------------------------------------------------------------------

/**
 * Return the file category string for a given filename or path.
 * Falls back to 'other' for unknown extensions or no extension.
 */
export function getFileCategory(nameOrPath) {
    const dot = nameOrPath.lastIndexOf('.');
    if (dot === -1) return 'other';
    const ext = nameOrPath.slice(dot).toLowerCase();
    for (const [category, exts] of Object.entries(FILE_CATEGORIES)) {
        if (exts.includes(ext)) return category;
    }
    return 'other';
}

// ---------------------------------------------------------------------------
// Icon lookup
// ---------------------------------------------------------------------------

/**
 * Return `{ icon, cls }` for a given filename.
 * `icon` is a Phosphor icon class name (e.g. 'ph-code').
 * `cls`  is a CSS modifier class   (e.g. 'file-icon-code').
 */
export function getFileIcon(name) {
    const category = getFileCategory(name);
    return CATEGORY_ICONS[category] || { icon: 'ph-file', cls: 'file-icon-default' };
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/**
 * Format a byte count as a human-readable string (B / KB / MB / GB).
 */
export function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
}

/**
 * Format an ISO date string as an absolute date/time, optionally prefixed
 * with a short relative label ("5m ago (Jan 1, 2024 09:00 AM)").
 * Used by the preview info bar.
 */
export function formatDate(isoString) {
    const d = new Date(isoString);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);
    let relative;
    if (diffMin < 1) relative = 'just now';
    else if (diffMin < 60) relative = `${diffMin}m ago`;
    else if (diffHr < 24) relative = `${diffHr}h ago`;
    else if (diffDay < 7) relative = `${diffDay}d ago`;
    else relative = null;

    const absolute = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
        + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return relative ? `${relative} (${absolute})` : absolute;
}

/**
 * Format an ISO date string as a compact relative label.
 * Returns "just now", "5m ago", "3h ago", "2d ago", or a short date.
 * Used by tree item detail rows.
 */
export function formatRelativeDate(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 7) return `${diffDay}d ago`;
    if (diffDay < 365) return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}
