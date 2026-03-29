/**
 * editable-viewer.js — View/edit toggle for code and text files.
 *
 * Replaces CodeViewer + TextViewer with a unified component that
 * supports both read-only viewing and editing with syntax highlighting.
 */
import { useState, useRef, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { getFileExtension, LANG_NAMES } from '../file-utils.js';
import { CodeEditor } from './code-editor.js';
import { EditBar } from './edit-bar.js';
import { undo, redo } from '@codemirror/commands';

/**
 * EditableViewer — view/edit toggle for code and text files.
 *
 * Props:
 *   text     — file content string
 *   path     — file path (for save API and language detection)
 *   onSave   — optional callback after successful save, receives new text
 */
export function EditableViewer({ text, path, onSave: onSaveCallback }) {
    const [editing, setEditing] = useState(false);
    const [editText, setEditText] = useState(text);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [cursor, setCursor] = useState(null);
    const viewRef = useRef(null);

    const ext = getFileExtension(path);
    const langName = LANG_NAMES[ext] || 'Plain Text';

    const handleDocChange = useCallback((newDoc) => {
        setEditText(newDoc);
        setDirty(newDoc !== text);
    }, [text]);

    const handleSave = useCallback(async () => {
        if (!dirty || saving) return;
        setSaving(true);
        try {
            await api.put('/api/files/content', { path, content: editText });
            setDirty(false);
            if (onSaveCallback) onSaveCallback(editText);
        } catch (e) {
            // error toast handled by api client
        } finally {
            setSaving(false);
        }
    }, [dirty, saving, path, editText, onSaveCallback]);

    const handleUndo = useCallback(() => {
        if (viewRef.current) undo(viewRef.current);
    }, []);

    const handleRedo = useCallback(() => {
        if (viewRef.current) redo(viewRef.current);
    }, []);

    const handleToggle = useCallback(() => {
        if (editing && dirty) {
            if (!confirm('Discard unsaved changes?')) return;
        }
        setEditing(e => !e);
        setEditText(text); // Reset to saved content
        setDirty(false);
    }, [editing, dirty, text]);

    return html`
        <div class="editable-viewer">
            <div class="editable-viewer-toolbar">
                <button class=${!editing ? 'active' : ''}
                        onClick=${() => !editing || handleToggle()}>View</button>
                <button class=${editing ? 'active' : ''}
                        onClick=${() => editing || handleToggle()}>
                    Edit${dirty ? html` <span class="dirty-dot"></span>` : ''}
                </button>
            </div>
            ${editing && html`
                <${EditBar}
                    dirty=${dirty} saving=${saving} language=${langName}
                    cursor=${cursor} onSave=${handleSave}
                    onUndo=${handleUndo} onRedo=${handleRedo} />
            `}
            <${CodeEditor}
                doc=${editing ? editText : text}
                path=${path}
                readOnly=${!editing}
                onDocChange=${editing ? handleDocChange : null}
                onCursorChange=${editing ? setCursor : null}
                onSave=${editing ? handleSave : null}
                viewRef=${viewRef}
                key=${path + ':' + editing} />
        </div>
    `;
}