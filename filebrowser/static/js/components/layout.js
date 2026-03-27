import { useState, useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { Breadcrumb } from './breadcrumb.js';
import { FileTree } from './tree.js';
import { PreviewPane } from './preview.js';
import { ActionBar } from './actions.js';
import { CommandPalette } from './command-palette.js';
import { ContextMenu } from './context-menu.js';

export function Layout({ username, authSource, onLogout }) {
    // ── Core state ──────────────────────────────────────────────
    const [currentPath, setCurrentPath] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [selectedFiles, setSelectedFiles] = useState(new Set());
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);
    const [showHidden, setShowHidden] = useState(false);
    const [sidebarWidth, setSidebarWidth] = useState(280);
    const isResizing = useRef(false);

    // ── Feature state ────────────────────────────────────────────
    const [viewMode, setViewMode] = useState('list');         // 'list' | 'grid'
    const [commandOpen, setCommandOpen] = useState(false);   // ⌘K palette
    const [contextMenu, setContextMenu] = useState(null);    // {x,y,path,type}
    const [allFiles, setAllFiles] = useState([]);             // flat file list for palette
    const [dragOver, setDragOver] = useState(false);         // drag-drop overlay
    const [showUpload, setShowUpload] = useState(false);     // upload modal
    const dragCounter = useRef(0);

    const refresh = () => setRefreshKey((k) => k + 1);

    // ── Keyboard shortcuts ───────────────────────────────────────
    useEffect(() => {
        const handler = (e) => {
            // ⌘K / Ctrl+K → open command palette
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                setCommandOpen(true);
            }
            // Escape → close overlays
            if (e.key === 'Escape') {
                setCommandOpen(false);
                setContextMenu(null);
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    // ── Resize handle ────────────────────────────────────────────
    const startResize = (e) => {
        e.preventDefault();
        isResizing.current = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        const onMove = (ev) => {
            if (!isResizing.current) return;
            setSidebarWidth(Math.min(Math.max(ev.clientX, 180), 600));
        };
        const onUp = () => {
            isResizing.current = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    };

    // ── Drag-drop overlay (Feature 6) ────────────────────────────
    const handleDragEnter = (e) => {
        if (!e.dataTransfer?.types?.includes('Files')) return;
        e.preventDefault();
        dragCounter.current += 1;
        if (dragCounter.current === 1) setDragOver(true);
    };
    const handleDragLeave = (e) => {
        e.preventDefault();
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) {
            dragCounter.current = 0;
            setDragOver(false);
        }
    };
    const handleDragOver = (e) => e.preventDefault();
    const handleDrop = (e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setDragOver(false);
        // Open upload modal when files dropped anywhere on the app
        if (e.dataTransfer?.files?.length > 0) {
            setShowUpload(true);
        }
    };

    // ── Auth ─────────────────────────────────────────────────────
    const handleLogout = async () => {
        await api.post('/api/auth/logout');
        if (authSource === 'frontdoor') {
            // Form POST to frontdoor's logout to clear the shared session cookie.
            // Use form.submit() so the browser sends a POST with cookies to the
            // frontdoor origin (same hostname, port 443).
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `https://${window.location.hostname}/api/auth/logout`;
            document.body.appendChild(form);
            form.submit();
        } else {
            onLogout();
        }
    };

    // ── Navigation ───────────────────────────────────────────────
    const handleNavigate = (path) => {
        setCurrentPath(path);
        setSidebarOpen(false);
    };

    // ── File selection ───────────────────────────────────────────
    const handleSelectFile = (path) => {
        setSelectedFile(path);
        setSelectedFiles(new Set([path]));
        setSidebarOpen(false);
    };

    const handleBatchToggle = (path) => {
        setSelectedFiles((prev) => {
            const next = new Set(prev);
            if (next.has(path)) next.delete(path);
            else next.add(path);
            return next;
        });
    };

    const clearSelection = () => {
        setSelectedFiles(new Set());
    };

    // ── Context menu actions (Feature 5) ─────────────────────────
    const handleCtxOpen = (path) => handleSelectFile(path);

    const handleCtxDownload = (path) => {
        const a = document.createElement('a');
        a.href = `/api/files/download?path=${encodeURIComponent(path)}`;
        a.download = path.split('/').pop();
        a.click();
    };

    const handleCtxRename = (path) => {
        const name = prompt('New name:', path.split('/').pop());
        if (!name) return;
        const parts = path.split('/');
        parts[parts.length - 1] = name;
        const newPath = parts.join('/');
        api.put('/api/files/rename', { old_path: path, new_path: newPath })
            .then(refresh)
            .catch(() => {});
    };

    const handleCtxDelete = async (path) => {
        if (!confirm(`Delete ${path.split('/').pop()}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(path)}`);
            if (selectedFile === path) setSelectedFile(null);
            refresh();
        } catch { /* toast shown */ }
    };

    const handleCtxCopyPath = (path) => {
        navigator.clipboard?.writeText(path).then(() => {
            // brief visual feedback via toast
            const t = document.createElement('div');
            t.className = 'toast';
            t.style.cssText = 'background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border-color)';
            t.textContent = 'Path copied!';
            document.body.appendChild(t);
            setTimeout(() => t.remove(), 2000);
        });
    };

    return html`
        <div
            class="layout"
            onDragEnter=${handleDragEnter}
            onDragLeave=${handleDragLeave}
            onDragOver=${handleDragOver}
            onDrop=${handleDrop}
        >
            <!-- Header -->
            <header class="header">
                <button class="hamburger" onClick=${() => setSidebarOpen(!sidebarOpen)}>&#9776;</button>
                <${Breadcrumb} path=${currentPath} onNavigate=${setCurrentPath} />
                <div class="header-right">
                    <!-- ⌘K hint -->
                    <button
                        style="background:none;border:1px solid var(--border-color);color:var(--text-secondary);padding:4px 10px;border-radius:var(--radius-full);font-size:12px;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:6px;transition:all 0.15s"
                        onClick=${() => setCommandOpen(true)}
                        title="Open command palette (⌘K)"
                    >
                        <i class="ph ph-magnifying-glass" style="font-size:13px"></i>
                        <span>Search</span>
                        <kbd style="background:var(--fill);border:1px solid var(--border-color);border-radius:4px;padding:1px 5px;font-size:10px;font-family:inherit">⌘K</kbd>
                    </button>
                    <label class="hidden-toggle">
                        <input type="checkbox" checked=${showHidden} onChange=${() => setShowHidden(!showHidden)} />
                        Show hidden
                    </label>
                    <span class="username">${username}</span>
                    <button class="logout-btn" onClick=${handleLogout} title="Sign out">
                    <i class="ph ph-sign-out"></i>
                </button>
                </div>
            </header>

            <!-- Main -->
            <div class="main-content" style=${{ '--sidebar-width': `${sidebarWidth}px` }}>
                <aside class="sidebar ${sidebarOpen ? 'open' : ''}">
                    <!-- Sidebar header with view toggle -->
                    <div class="sidebar-header">
                        <div class="view-toggle">
                            <button
                                class=${viewMode === 'list' ? 'active' : ''}
                                onClick=${() => setViewMode('list')}
                                title="List view"
                            >
                                <i class="ph ph-list"></i>
                            </button>
                            <button
                                class=${viewMode === 'grid' ? 'active' : ''}
                                onClick=${() => setViewMode('grid')}
                                title="Grid view"
                            >
                                <i class="ph ph-squares-four"></i>
                            </button>
                        </div>
                    </div>

                    <${FileTree}
                        currentPath=${currentPath}
                        onNavigate=${handleNavigate}
                        onSelectFile=${handleSelectFile}
                        onBatchToggle=${handleBatchToggle}
                        onContextMenu=${setContextMenu}
                        onEntriesChange=${setAllFiles}
                        refreshKey=${refreshKey}
                        showHidden=${showHidden}
                        viewMode=${viewMode}
                        selectedFile=${selectedFile}
                        selectedFiles=${selectedFiles}
                    />
                </aside>

                <div class="resize-handle" onMouseDown=${startResize}></div>

                <div
                    class="sidebar-overlay ${sidebarOpen ? 'visible' : ''}"
                    onClick=${() => setSidebarOpen(false)}
                ></div>

                <main class="preview">
                    <${PreviewPane} filePath=${selectedFile} />
                </main>
            </div>

            <!-- Action bar -->
            <${ActionBar}
                currentPath=${currentPath}
                selectedFile=${selectedFile}
                selectedFiles=${selectedFiles}
                onRefresh=${refresh}
                onClearSelection=${clearSelection}
                showUpload=${showUpload}
                onShowUpload=${() => setShowUpload(true)}
                onHideUpload=${() => setShowUpload(false)}
            />

            <!-- Command palette (Feature 2) -->
            <${CommandPalette}
                isOpen=${commandOpen}
                onClose=${() => setCommandOpen(false)}
                allFiles=${allFiles}
                onSelectFile=${handleSelectFile}
            />

            <!-- Context menu (Feature 5) -->
            <${ContextMenu}
                menu=${contextMenu}
                onClose=${() => setContextMenu(null)}
                onOpen=${handleCtxOpen}
                onDownload=${handleCtxDownload}
                onRename=${handleCtxRename}
                onDelete=${handleCtxDelete}
                onCopyPath=${handleCtxCopyPath}
            />

            <!-- Full-page drag-drop overlay (Feature 6) -->
            ${dragOver && html`
                <div class="drag-upload-overlay">
                    <div class="drag-upload-message">
                        <i class="ph ph-upload-simple"></i>
                        <span>Drop to upload</span>
                        <small>Files will be uploaded to: /${currentPath || 'root'}</small>
                    </div>
                </div>
            `}
        </div>
    `;
}
