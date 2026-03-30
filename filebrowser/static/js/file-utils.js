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
    text:     ['.txt', '.log', '.csv', '.json', '.jsonl', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
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
// Well-known extensionless filenames
// ---------------------------------------------------------------------------

const KNOWN_TEXT_NAMES = new Set([
    'LICENSE', 'LICENCE', 'README', 'CONTRIBUTING', 'CHANGELOG', 'CHANGES',
    'NOTICE', 'AUTHORS', 'COPYING', 'INSTALL', 'NEWS', 'TODO', 'PATENTS',
]);

const KNOWN_CODE_NAMES = new Set([
    'Makefile', 'makefile', 'GNUmakefile',
    'Dockerfile', 'dockerfile', 'Containerfile',
    'Vagrantfile', 'Procfile', 'Brewfile', 'Gemfile',
    'Rakefile', 'Guardfile', 'Capfile',
    'Justfile', 'justfile', 'Snakefile',
]);

// ---------------------------------------------------------------------------
// Category lookup
// ---------------------------------------------------------------------------

/**
 * Return the file category string for a given filename or path.
 * Falls back to 'other' for unknown extensions or no extension.
 *
 * Detection layers:
 * 1. Extension lookup in FILE_CATEGORIES.
 * 2. Well-known filename lookup (KNOWN_TEXT_NAMES / KNOWN_CODE_NAMES).
 * 3. Returns 'other' — caller may use backend category as fallback.
 */
export function getFileCategory(nameOrPath) {
    const name = nameOrPath.split('/').pop();
    const dot = name.lastIndexOf('.');
    if (dot === -1) {
        // No extension — check well-known filenames
        if (KNOWN_TEXT_NAMES.has(name)) return 'text';
        if (KNOWN_CODE_NAMES.has(name)) return 'code';
        return 'other';
    }
    const ext = name.slice(dot).toLowerCase();
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

// ---------------------------------------------------------------------------
// CodeMirror 6 language loaders (lazy, keyed by extension)
// ---------------------------------------------------------------------------

/**
 * Lazy CodeMirror 6 language loaders, keyed by file extension.
 * Each returns a Promise<LanguageSupport>. Missing extensions = plain text.
 */
export const LANGUAGE_MAP = {
    '.py':    () => import('@codemirror/lang-python').then(m => m.python()),
    '.js':    () => import('@codemirror/lang-javascript').then(m => m.javascript()),
    '.mjs':   () => import('@codemirror/lang-javascript').then(m => m.javascript()),
    '.jsx':   () => import('@codemirror/lang-javascript').then(m => m.javascript({ jsx: true })),
    '.ts':    () => import('@codemirror/lang-javascript').then(m => m.javascript({ typescript: true })),
    '.tsx':   () => import('@codemirror/lang-javascript').then(m => m.javascript({ jsx: true, typescript: true })),
    '.json':  () => import('@codemirror/lang-json').then(m => m.json()),
    '.jsonl': () => import('@codemirror/lang-json').then(m => m.json()),
    '.html':  () => import('@codemirror/lang-html').then(m => m.html()),
    '.htm':   () => import('@codemirror/lang-html').then(m => m.html()),
    '.css':   () => import('@codemirror/lang-css').then(m => m.css()),
    '.md':    () => import('@codemirror/lang-markdown').then(m => m.markdown()),
    '.rs':    () => import('@codemirror/lang-rust').then(m => m.rust()),
    '.go':    () => import('@codemirror/lang-go').then(m => m.go()),
    '.sql':   () => import('@codemirror/lang-sql').then(m => m.sql()),
    '.yaml':  () => import('@codemirror/lang-yaml').then(m => m.yaml()),
    '.yml':   () => import('@codemirror/lang-yaml').then(m => m.yaml()),
    '.xml':   () => import('@codemirror/lang-xml').then(m => m.xml()),
    '.c':     () => import('@codemirror/lang-cpp').then(m => m.cpp()),
    '.cpp':   () => import('@codemirror/lang-cpp').then(m => m.cpp()),
    '.h':     () => import('@codemirror/lang-cpp').then(m => m.cpp()),
    '.hpp':   () => import('@codemirror/lang-cpp').then(m => m.cpp()),
    '.java':  () => import('@codemirror/lang-java').then(m => m.java()),
    '.php':   () => import('@codemirror/lang-php').then(m => m.php()),
    '.dot':   () => import('cm-lang-dot').then(m => m.dot()),
    '.gv':    () => import('cm-lang-dot').then(m => m.dot()),
    // Fallback: extensions not listed here get plain text (still line numbers, etc.)
};

/**
 * Return the file extension (lowercase, with dot) for a path.
 */
export function getFileExtension(nameOrPath) {
    const dot = nameOrPath.lastIndexOf('.');
    return dot === -1 ? '' : nameOrPath.slice(dot).toLowerCase();
}

/**
 * Display name for a language by extension (for UI labels).
 */
export const LANG_NAMES = {
    '.py': 'Python', '.js': 'JavaScript', '.mjs': 'JavaScript',
    '.ts': 'TypeScript', '.jsx': 'JSX', '.tsx': 'TSX',
    '.json': 'JSON', '.jsonl': 'JSONL', '.html': 'HTML', '.htm': 'HTML',
    '.css': 'CSS', '.md': 'Markdown', '.rs': 'Rust',
    '.go': 'Go', '.sql': 'SQL', '.yaml': 'YAML', '.yml': 'YAML',
    '.xml': 'XML', '.c': 'C', '.cpp': 'C++', '.h': 'C/C++ Header',
    '.hpp': 'C++ Header', '.java': 'Java', '.php': 'PHP',
    '.sh': 'Shell', '.bash': 'Bash',
    '.txt': 'Plain Text', '.log': 'Log', '.csv': 'CSV',
    '.toml': 'TOML', '.env': 'Env', '.conf': 'Config',
    '.dot': 'DOT', '.gv': 'Graphviz',
};

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

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
