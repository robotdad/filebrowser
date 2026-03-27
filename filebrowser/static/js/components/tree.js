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
}) {
    const [entries, setEntries] = useState({});
    const [expanded, setExpanded] = useState({});

    useEffect(() => { reloadAll(); }, [refreshKey, showHidden]);

    // When currentPath changes (e.g. from pinned favorites), expand all ancestors
    useEffect(() => {
        if (!currentPath) return;
        const segments = currentPath.split('/');
        const toExpand = [];
        for (let i = 1; i <= segments.length; i++) {
            toExpand.push(segments.slice(0, i).join('/'));
        }
        const missing = toExpand.filter(p => !expanded[p]);
        if (missing.length === 0) return;
        setExpanded(prev => {
            const next = { ...prev };
            for (const p of missing) next[p] = true;
            return next;
        });
        // Load directory contents for each newly expanded segment
        (async () => {
            for (const p of missing) await loadDirectory(p);
        })();
    }, [currentPath]);

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
        const items = entries[currentPath] || entries[''] || [];
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
        const items = entries[path] || [];
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
                    class="tree-item tree-file ${isSelected ? 'selected' : ''} ${isBatch ? 'multi-selected' : ''}"
                    style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick=${(e) => handleFileClick(e, itemPath)}
                    onContextMenu=${(e) => handleContextMenu(e, itemPath, 'file')}
                    title=${item.name}
                >
                    <span class="file-icon ${fi.cls}"><i class="ph ${fi.icon}"></i></span>
                    <span class="tree-name">${item.name}</span>
                </div>
            `;
        });
    };

    return html`<div class="file-tree">${renderEntries('')}</div>`;
}
