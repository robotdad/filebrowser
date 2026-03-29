/**
 * edit-bar.js — Shared editor toolbar for all editable file types.
 *
 * Provides Save/Undo/Redo buttons, dirty indicator, cursor position,
 * and language label. Used by EditableViewer and GraphvizViewer.
 */
import { html } from '../html.js';

/**
 * EditBar — shared toolbar component.
 *
 * Props:
 *   dirty     — boolean, document has unsaved changes
 *   saving    — boolean, save in progress
 *   language  — string, display name of detected language (e.g. "Python")
 *   cursor    — { line, col } or null
 *   onSave    — function, trigger save
 *   onUndo    — function, trigger undo
 *   onRedo    — function, trigger redo
 */
export function EditBar({ dirty, saving, language, cursor, onSave, onUndo, onRedo }) {
    const modKey = navigator.platform.includes('Mac') ? '\u2318' : 'Ctrl';

    return html`
        <div class="edit-bar">
            <div class="edit-bar-actions">
                <button class=${'edit-bar-save' + (dirty ? ' dirty' : '')}
                        onClick=${onSave}
                        disabled=${!dirty || saving}>
                    <i class="ph ${saving ? 'ph-circle-notch' : dirty ? 'ph-floppy-disk' : 'ph-check'}"></i>
                    ${' '}${saving ? 'Saving\u2026' : dirty ? 'Save' : 'Saved'}
                </button>
                <button class="edit-bar-btn" onClick=${onUndo} title="Undo">
                    <i class="ph ph-arrow-counter-clockwise"></i>
                </button>
                <button class="edit-bar-btn" onClick=${onRedo} title="Redo">
                    <i class="ph ph-arrow-clockwise"></i>
                </button>
                <span class="edit-bar-hint">
                    <kbd>${modKey}</kbd>+<kbd>S</kbd>
                </span>
            </div>
            <div class="edit-bar-info">
                ${language && html`<span class="edit-bar-lang">${language}</span>`}
                ${cursor && html`<span class="edit-bar-cursor">Ln ${cursor.line}, Col ${cursor.col}</span>`}
            </div>
        </div>
    `;
}