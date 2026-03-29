import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { UploadModal } from './upload.js';

export function ActionBar({
    currentPath,
    selectedFile,
    selectedFiles,
    onRefresh,
    onClearSelection,
    showUpload,
    onShowUpload,
    onHideUpload,
    terminalOpen,
    onToggleTerminal,
}) {
    const [renaming, setRenaming] = useState(false);
    const [newName, setNewName] = useState('');

    const handleNewFolder = async () => {
        const name = prompt('Folder name:');
        if (!name) return;
        const path = currentPath ? `${currentPath}/${name}` : name;
        try {
            await api.post(`/api/files/mkdir?path=${encodeURIComponent(path)}`);
            onRefresh();
        } catch { /* toast shown by api.js */ }
    };

    const handleDelete = async () => {
        if (!selectedFile) return;
        if (!confirm(`Delete ${selectedFile.split('/').pop()}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(selectedFile)}`);
            onRefresh();
        } catch { /* toast shown by api.js */ }
    };

    const startRename = () => {
        if (!selectedFile) return;
        setNewName(selectedFile.split('/').pop());
        setRenaming(true);
    };

    const handleRename = async () => {
        if (!selectedFile || !newName) return;
        const parts = selectedFile.split('/');
        parts[parts.length - 1] = newName;
        const newPath = parts.join('/');
        try {
            await api.put('/api/files/rename', { old_path: selectedFile, new_path: newPath });
            setRenaming(false);
            setNewName('');
            onRefresh();
        } catch { /* toast shown by api.js */ }
    };

    const handleBatchDelete = async () => {
        const paths = [...(selectedFiles ?? [])];
        if (!paths.length) return;
        if (!confirm(`Delete ${paths.length} item${paths.length !== 1 ? 's' : ''}?`)) return;
        for (const p of paths) {
            try { await api.del(`/api/files?path=${encodeURIComponent(p)}`); } catch { /* continue */ }
        }
        onClearSelection?.();
        onRefresh();
    };

    const handleBatchDownload = () => {
        for (const p of (selectedFiles ?? [])) {
            const a = document.createElement('a');
            a.href = `/api/files/download?path=${encodeURIComponent(p)}`;
            a.download = p.split('/').pop();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }
    };

    // ── Batch toolbar (shown when 2+ files selected) ─────────────
    const batchCount = selectedFiles?.size ?? 0;
    if (batchCount > 1) {
        return html`
            <div class="action-bar batch-toolbar">
                <span class="batch-count">${batchCount} selected</span>

                <button onClick=${handleBatchDownload}>
                    <i class="ph ph-download-simple"></i> Download all
                </button>

                <button class="danger" onClick=${handleBatchDelete}>
                    <i class="ph ph-trash"></i> Delete all
                </button>

                <button class="batch-clear" onClick=${onClearSelection}>
                    <i class="ph ph-x"></i> Clear
                </button>

                ${showUpload && html`
                    <${UploadModal}
                        path=${currentPath}
                        onClose=${onHideUpload}
                        onUploaded=${() => { onHideUpload(); onRefresh(); }}
                    />
                `}
            </div>
        `;
    }

    // ── Normal toolbar ───────────────────────────────────────────
    return html`
        <div class="action-bar">
            <button onClick=${onToggleTerminal} title="Toggle terminal (Ctrl+\`)">
                <i class="ph ${terminalOpen ? 'ph-terminal-window-fill' : 'ph-terminal-window'}"></i> Terminal</button>
            <button onClick=${() => onShowUpload()}>
                <i class="ph ph-upload-simple"></i> Upload
            </button>
            <button onClick=${handleNewFolder}>
                <i class="ph ph-folder-plus"></i> New Folder
            </button>

            ${selectedFile && !renaming && html`
                <a
                    class="action-download-btn"
                    href=${`/api/files/download?path=${encodeURIComponent(selectedFile)}`}
                >
                    <i class="ph ph-download-simple"></i> Download
                </a>
                <button onClick=${startRename}>
                    <i class="ph ph-pencil-simple"></i> Rename
                </button>
                <button class="danger" onClick=${handleDelete}>
                    <i class="ph ph-trash"></i> Delete
                </button>
            `}

            ${renaming && html`
                <input
                    value=${newName}
                    onInput=${(e) => setNewName(e.target.value)}
                    onKeyDown=${(e) => {
                        if (e.key === 'Enter') handleRename();
                        if (e.key === 'Escape') setRenaming(false);
                    }}
                    autoFocus
                />
                <button onClick=${handleRename}>Save</button>
                <button onClick=${() => setRenaming(false)}>Cancel</button>
            `}

            ${showUpload && html`
                <${UploadModal}
                    path=${currentPath}
                    onClose=${onHideUpload}
                    onUploaded=${() => { onHideUpload(); onRefresh(); }}
                />
            `}
        </div>
    `;
}
