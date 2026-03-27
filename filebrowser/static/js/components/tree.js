import { useState, useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

const FILE_ICON_TYPES = [
    { exts: ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'], icon: 'ph-image', cls: 'file-icon-image' },
    { exts: ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.html', '.css'], icon: 'ph-code', cls: 'file-icon-code' },
    { exts: ['.md'], icon: 'ph-article', cls: 'file-icon-markdown' },
    { exts: ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'], icon: 'ph-file-text', cls: 'file-icon-text' },
    { exts: ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'], icon: 'ph-music-note', cls: 'file-icon-audio' },
    { exts: ['.mp4', '.webm', '.mkv', '.mov', '.avi'], icon: 'ph-film-strip', cls: 'file-icon-video' },
    { exts: ['.pdf'], icon: 'ph-file-pdf', cls: 'file-icon-pdf' },
];

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
}

function formatRelativeDate(isoString) {
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

function sortEntries(items, sortBy) {
    const sorted = [...items];
    sorted.sort((a, b) => {
        // Always directories first
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
        switch (sortBy) {
            case 'modified':
                return new Date(b.modified) - new Date(a.modified); // newest first
            case 'size':
                return b.size - a.size; // largest first
            case 'type': {
                const extA = a.name.includes('.') ? a.name.split('.').pop().toLowerCase() : '';
                const extB = b.name.includes('.') ? b.name.split('.').pop().toLowerCase() : '';
                return extA.localeCompare(extB) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
            }
            default: // 'name'
                return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
        }
    });
    return sorted;
}

function getFileIcon(name) {
    const dot = name.lastIndexOf('.');
    if (dot !== -1) {
        const ext = name.slice(dot).toLowerCase();
        for (const t of FILE_ICON_TYPES) {
            if (t.exts.includes(ext)) return t;
        }
    }
    return { icon: 'ph-file', cls: 'file-icon-default' };
}

/**
 * PinnedFavorites — each pinned folder is a fully browsable mini file tree.
 */
export function PinnedFavorites({
    favorites,
    onNavigate,
    onSelectFile,
    onBatchToggle,
    onContextMenu,
    selectedFile,
    selectedFiles,
    showHidden,
    refreshKey,
    onReorder,
    onUnpin,
    sortBy,
}) {
    const [entries, setEntries] = useState({});
    const [expanded, setExpanded] = useState({});

    // Reload expanded directories when refresh or showHidden changes
    useEffect(() => {
        const paths = Object.keys(expanded);
        for (const p of paths) loadDirectory(p);
    }, [refreshKey, showHidden]);

    const loadDirectory = async (path) => {
        try {
            const data = await api.get(`/api/files?path=${encodeURIComponent(path)}&show_hidden=${showHidden}`);
            setEntries((prev) => ({ ...prev, [path]: data }));
        } catch { /* toast shown by api.js */ }
    };

    const toggleFolder = (path) => {
        setExpanded((prev) => {
            const next = { ...prev };
            if (next[path]) { delete next[path]; }
            else { next[path] = true; loadDirectory(path); }
            return next;
        });
        onNavigate(path);
    };

    const handleFileClick = (e, itemPath) => {
        if (e.ctrlKey || e.metaKey) { onBatchToggle?.(itemPath); }
        else { onSelectFile(itemPath); }
    };

    const handleContextMenu = (e, itemPath, itemType) => {
        e.preventDefault();
        onContextMenu?.({ x: e.clientX, y: e.clientY, path: itemPath, type: itemType });
    };

    // Render contents of a directory (recursive, identical to FileTree list view)
    const renderChildren = (path, depth) => {
        const items = sortEntries(entries[path] || [], sortBy);
        return items.map((item) => {
            const itemPath = path ? `${path}/${item.name}` : item.name;
            if (item.type === 'directory') {
                const isExpanded = !!expanded[itemPath];
                return html`
                    <div key=${itemPath}>
                        <div
                            class="tree-item tree-folder ${isExpanded ? 'expanded' : ''} ${selectedFiles?.has(itemPath) ? 'multi-selected' : ''}"
                            style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                            onClick=${(e) => {
                                if (e.ctrlKey || e.metaKey) { onBatchToggle?.(itemPath); }
                                else { toggleFolder(itemPath); }
                            }}
                            onContextMenu=${(e) => handleContextMenu(e, itemPath, 'directory')}
                            title=${item.name}
                        >
                            <span class="file-icon file-icon-folder">
                                <i class="ph ${isExpanded ? 'ph-folder-open' : 'ph-folder'}"></i>
                            </span>
                            <span class="tree-name">${item.name}</span>
                        </div>
                        ${isExpanded && renderChildren(itemPath, depth + 1)}
                    </div>
                `;
            }
            const fi = getFileIcon(item.name);
            const isSelected = selectedFile === itemPath;
            const isBatch = selectedFiles?.has(itemPath);
            return html`
                <div
                    key=${itemPath}
                    class="tree-item tree-file has-detail ${isSelected ? 'selected' : ''} ${isBatch ? 'multi-selected' : ''}"
                    style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick=${(e) => handleFileClick(e, itemPath)}
                    onContextMenu=${(e) => handleContextMenu(e, itemPath, 'file')}
                    title=${item.name}
                >
                    <span class="file-icon ${fi.cls}"><i class="ph ${fi.icon}"></i></span>
                    <div class="tree-item-text">
                        <span class="tree-name">${item.name}</span>
                        <span class="tree-detail">${formatSize(item.size)}${item.modified ? ` · ${formatRelativeDate(item.modified)}` : ''}</span>
                    </div>
                </div>
            `;
        });
    };

    if (!favorites.length) return null;

    return html`
        <div class="favorites-section">
            <div class="favorites-header">
                <i class="ph ph-push-pin-simple"></i>
                <span>Pinned</span>
            </div>
            ${favorites.map((path, i) => {
                const isExpanded = !!expanded[path];
                const name = path.split('/').pop() || 'Home';
                return html`
                    <div key=${'pin-' + path}>
                        <div
                            class="tree-item favorites-item tree-folder ${isExpanded ? 'expanded' : ''}"
                            draggable="true"
                            onClick=${(e) => {
                                if (e.ctrlKey || e.metaKey) return;
                                toggleFolder(path);
                            }}
                            onDragStart=${(e) => {
                                e.dataTransfer.effectAllowed = 'move';
                                e.dataTransfer.setData('text/x-fav-index', String(i));
                                e.currentTarget.classList.add('dragging');
                            }}
                            onDragEnd=${(e) => {
                                e.currentTarget.classList.remove('dragging');
                            }}
                            onDragOver=${(e) => {
                                e.preventDefault();
                                e.dataTransfer.dropEffect = 'move';
                                const rect = e.currentTarget.getBoundingClientRect();
                                const mid = rect.top + rect.height / 2;
                                e.currentTarget.classList.toggle('drop-above', e.clientY < mid);
                                e.currentTarget.classList.toggle('drop-below', e.clientY >= mid);
                            }}
                            onDragLeave=${(e) => {
                                e.currentTarget.classList.remove('drop-above', 'drop-below');
                            }}
                            onDrop=${(e) => {
                                e.preventDefault();
                                e.currentTarget.classList.remove('drop-above', 'drop-below');
                                const from = parseInt(e.dataTransfer.getData('text/x-fav-index'), 10);
                                if (!isNaN(from) && from !== i) onReorder(from, i);
                            }}
                            onContextMenu=${(e) => handleContextMenu(e, path, 'directory')}
                            title=${path}
                        >
                            <span class="file-icon file-icon-folder">
                                <i class="ph ${isExpanded ? 'ph-folder-open' : 'ph-folder'}"></i>
                            </span>
                            <span class="tree-name">${name}</span>
                            <button
                                class="favorites-unpin"
                                onClick=${(e) => { e.stopPropagation(); onUnpin(path); }}
                                title="Unpin"
                            >
                                <i class="ph ph-x"></i>
                            </button>
                        </div>
                        ${isExpanded && renderChildren(path, 1)}
                    </div>
                `;
            })}
        </div>
        <div class="favorites-divider"></div>
    `;
}

export function FileTree({
    currentPath,
    onNavigate,
    onSelectFile,
    onBatchToggle,
    onContextMenu,
    onEntriesChange,
    refreshKey,
    showHidden,
    viewMode,
    selectedFile,
    selectedFiles,
    sortBy,
}) {
    const [entries, setEntries] = useState({});
    const [expanded, setExpanded] = useState({});

    useEffect(() => { reloadAll(); }, [refreshKey, showHidden]);

    // Report flat file list upward whenever entries change
    useEffect(() => {
        if (!onEntriesChange) return;
        const flat = [];
        for (const [dirPath, items] of Object.entries(entries)) {
            for (const item of items) {
                const p = dirPath ? `${dirPath}/${item.name}` : item.name;
                flat.push({ name: item.name, path: p, type: item.type });
            }
        }
        onEntriesChange(flat);
    }, [entries]);

    const reloadAll = async () => {
        const paths = ['', ...Object.keys(expanded)];
        for (const p of paths) await loadDirectory(p);
    };

    const loadDirectory = async (path) => {
        try {
            const data = await api.get(`/api/files?path=${encodeURIComponent(path)}&show_hidden=${showHidden}`);
            setEntries((prev) => ({ ...prev, [path]: data }));
        } catch { /* toast shown by api.js */ }
    };

    const toggleFolder = (path) => {
        setExpanded((prev) => {
            const next = { ...prev };
            if (next[path]) { delete next[path]; }
            else { next[path] = true; loadDirectory(path); }
            return next;
        });
        onNavigate(path);
    };

    const handleFileClick = (e, itemPath) => {
        if (e.ctrlKey || e.metaKey) {
            // Ctrl/⌘+click → batch toggle, don't change preview
            onBatchToggle?.(itemPath);
        } else {
            // Normal click → single select, open preview
            onSelectFile(itemPath);
        }
    };

    const handleContextMenu = (e, itemPath, itemType) => {
        e.preventDefault();
        onContextMenu?.({ x: e.clientX, y: e.clientY, path: itemPath, type: itemType });
    };

    // ── Grid View ──────────────────────────────────────────────────
    if (viewMode === 'grid') {
        const items = sortEntries(entries[currentPath] || entries[''] || [], sortBy);
        return html`
            <div class="file-tree grid-view">
                ${items.map((item) => {
                    const itemPath = currentPath ? `${currentPath}/${item.name}` : item.name;
                    if (item.type === 'directory') {
                        return html`
                            <div
                                key=${itemPath}
                                class="tree-item tree-folder ${selectedFiles?.has(itemPath) ? 'multi-selected' : ''}"
                                onClick=${(e) => { if (e.ctrlKey || e.metaKey) { onBatchToggle?.(itemPath); } else { toggleFolder(itemPath); } }}
                                onContextMenu=${(e) => handleContextMenu(e, itemPath, 'directory')}
                                title=${item.name}
                            >
                                <span class="file-icon file-icon-folder">
                                    <i class="ph ph-folder"></i>
                                </span>
                                <span class="tree-name">${item.name}</span>
                            </div>
                        `;
                    }
                    const fi = getFileIcon(item.name);
                    const isSelected = selectedFile === itemPath;
                    const isBatch = selectedFiles?.has(itemPath);
                    return html`
                        <div
                            key=${itemPath}
                            class="tree-item tree-file ${isSelected ? 'selected' : ''} ${isBatch ? 'multi-selected' : ''}"
                            onClick=${(e) => handleFileClick(e, itemPath)}
                            onContextMenu=${(e) => handleContextMenu(e, itemPath, 'file')}
                            title=${item.name}
                        >
                            <span class="file-icon ${fi.cls}">
                                <i class="ph ${fi.icon}"></i>
                            </span>
                            <span class="tree-name">${item.name}</span>
                            <span class="tree-detail">${formatSize(item.size)}</span>
                        </div>
                    `;
                })}
                ${items.length === 0 && html`
                    <div style="grid-column:1/-1;padding:var(--space-lg);color:var(--text-muted);font-size:13px;text-align:center">
                        Empty folder
                    </div>
                `}
            </div>
        `;
    }

    // ── List View (default) ───────────────────────────────────────
    const renderEntries = (path, depth = 0) => {
        const items = sortEntries(entries[path] || [], sortBy);
        return items.map((item) => {
            const itemPath = path ? `${path}/${item.name}` : item.name;
            if (item.type === 'directory') {
                const isExpanded = !!expanded[itemPath];
                return html`
                    <div key=${itemPath}>
                        <div
                            class="tree-item tree-folder ${isExpanded ? 'expanded' : ''} ${selectedFiles?.has(itemPath) ? 'multi-selected' : ''}"
                            style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                            onClick=${(e) => {
                                if (e.ctrlKey || e.metaKey) { onBatchToggle?.(itemPath); }
                                else { toggleFolder(itemPath); }
                            }}
                            onContextMenu=${(e) => handleContextMenu(e, itemPath, 'directory')}
                            title=${item.name}
                        >
                            <span class="file-icon file-icon-folder">
                                <i class="ph ${isExpanded ? 'ph-folder-open' : 'ph-folder'}"></i>
                            </span>
                            <span class="tree-name">${item.name}</span>
                        </div>
                        ${isExpanded && renderEntries(itemPath, depth + 1)}
                    </div>
                `;
            }
            const fi = getFileIcon(item.name);
            const isSelected = selectedFile === itemPath;
            const isBatch = selectedFiles?.has(itemPath);
            return html`
                <div
                    key=${itemPath}
                    class="tree-item tree-file has-detail ${isSelected ? 'selected' : ''} ${isBatch ? 'multi-selected' : ''}"
                    style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick=${(e) => handleFileClick(e, itemPath)}
                    onContextMenu=${(e) => handleContextMenu(e, itemPath, 'file')}
                    title=${item.name}
                >
                    <span class="file-icon ${fi.cls}"><i class="ph ${fi.icon}"></i></span>
                    <div class="tree-item-text">
                        <span class="tree-name">${item.name}</span>
                        <span class="tree-detail">${formatSize(item.size)}${item.modified ? ` · ${formatRelativeDate(item.modified)}` : ''}</span>
                    </div>
                </div>
            `;
        });
    };

    return html`<div class="file-tree">${renderEntries('')}</div>`;
}
