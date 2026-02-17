import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function UploadModal({ path, onClose, onUploaded }) {
    const [dragging, setDragging] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState('');

    const uploadFile = async (file) => {
        setUploading(true);
        setProgress(`Uploading ${file.name}...`);
        try {
            const formData = new FormData();
            formData.append('file', file);
            await api.post(`/api/files/upload?path=${encodeURIComponent(path)}`, formData);
            setProgress(`${file.name} uploaded!`);
            onUploaded();
        } catch {
            setProgress('Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length > 0) {
            uploadFile(e.dataTransfer.files[0]);
        }
    };

    const handleFileInput = (e) => {
        if (e.target.files.length > 0) {
            uploadFile(e.target.files[0]);
        }
    };

    return html`
        <div class="modal-overlay" onClick=${onClose}>
            <div class="modal" onClick=${(e) => e.stopPropagation()}>
                <h2>Upload File</h2>
                <div
                    class="drop-zone ${dragging ? 'dragging' : ''}"
                    onDragOver=${(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave=${() => setDragging(false)}
                    onDrop=${handleDrop}
                >
                    <p>Drag and drop a file here, or</p>
                    <input type="file" onChange=${handleFileInput} />
                </div>
                ${progress && html`<p class="upload-progress">${progress}</p>`}
                <button onClick=${onClose} disabled=${uploading}>Close</button>
            </div>
        </div>
    `;
}
