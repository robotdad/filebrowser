import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { UploadModal } from './upload.js';

export function ActionBar({ currentPath, selectedFile, onRefresh }) {
    const [showUpload, setShowUpload] = useState(false);
    const [renaming, setRenaming] = useState(false);
    const [newName, setNewName] = useState('');

    const handleNewFolder = async () => {
        const name = prompt('Folder name:');
        if (!name) return;
        const path = currentPath ? `${currentPath}/${name}` : name;
        try {
            await api.post(`/api/files/mkdir?path=${encodeURIComponent(path)}`);
            onRefresh();
        } catch {
            // toast shown by api.js
        }
    };

    const handleDelete = async () => {
        if (!selectedFile) return;
        if (!confirm(`Delete ${selectedFile}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(selectedFile)}`);
            onRefresh();
        } catch {
            // toast shown by api.js
        }
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
        } catch {
            // toast shown by api.js
        }
    };

    return html`
        <div class="action-bar">
            <button onClick=${() => setShowUpload(true)}>Upload</button>
            <button onClick=${handleNewFolder}>New Folder</button>
            ${selectedFile && !renaming && html`
                <a
                    class="action-download-btn"
                    href=${`/api/files/download?path=${encodeURIComponent(selectedFile)}`}
                >Download</a>
                <button onClick=${startRename}>Rename</button>
                <button class="danger" onClick=${handleDelete}>Delete</button>
            `}
            ${renaming && html`
                <input
                    value=${newName}
                    onInput=${(e) => setNewName(e.target.value)}
                    onKeyDown=${(e) => e.key === 'Enter' && handleRename()}
                />
                <button onClick=${handleRename}>Save</button>
                <button onClick=${() => setRenaming(false)}>Cancel</button>
            `}
            ${showUpload && html`
                <${UploadModal}
                    path=${currentPath}
                    onClose=${() => setShowUpload(false)}
                    onUploaded=${() => { setShowUpload(false); onRefresh(); }}
                />
            `}
        </div>
    `;
}
