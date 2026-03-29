/**
 * markdown-editor.js — file-level editor for markdown files.
 *
 * Three tabs following the GraphvizViewer pattern:
 *   View   — Rendered markdown (marked + DOMPurify), read-only
 *   Edit   — Split-pane: CodeMirror 6 editor + live rendered preview
 *   Source — CodeMirror 6 raw text editing with markdown syntax highlighting
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { CodeEditor } from './code-editor.js';
import { EditBar } from './edit-bar.js';
import { undo, redo } from '@codemirror/commands';

const LOG_PREFIX = '[MarkdownEditor]';

/** Render markdown text to sanitized HTML. */
function renderMarkdown(text) {
    const t0 = performance.now();
    const result = DOMPurify.sanitize(marked.parse(text || ''));
    console.debug(LOG_PREFIX, `renderMarkdown: ${(performance.now() - t0).toFixed(1)}ms, ` +
        `input=${text?.length ?? 0} chars, output=${result.length} chars`);
    return result;
}

/**
 * MarkdownEditor — tri-mode markdown file editor.
 *
 * Props:
 *   text    — file content string (markdown source)
 *   path    — file path (for save API and language detection)
 *   onSave  — callback after successful save, receives new text
 */
export function MarkdownEditor({ text, path, onSave }) {
    const [activeTab, setActiveTab] = useState('view');
    const [editText, setEditText] = useState(text);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [cursor, setCursor] = useState(null);
    // Initialize preview from text so Edit tab has content immediately
    const [previewHtml, setPreviewHtml] = useState(() => renderMarkdown(text));
    const editorViewRef = useRef(null);
    // Track whether the edit tab has been opened (for immediate vs debounced render)
    const editInitRef = useRef(false);

    // Sync editText when text prop changes (new file loaded or post-save)
    useEffect(() => {
        console.debug(LOG_PREFIX, `text prop changed: ${text?.length ?? 0} chars`);
        setEditText(text);
        setPreviewHtml(renderMarkdown(text));
        setDirty(false);
    }, [text]);

    // Live preview rendering for Edit tab
    // Immediate on first open (like GraphvizViewer), debounced on subsequent edits
    useEffect(() => {
        if (activeTab !== 'edit') {
            editInitRef.current = false;
            return;
        }
        if (!editText) {
            setPreviewHtml('');
            return;
        }

        // Render immediately on first open / tab switch; debounce subsequent edits
        if (!editInitRef.current) {
            editInitRef.current = true;
            setPreviewHtml(renderMarkdown(editText));
            return;
        }

        let cancelled = false;
        const timer = setTimeout(() => {
            if (!cancelled) {
                setPreviewHtml(renderMarkdown(editText));
            }
        }, 300);
        return () => { cancelled = true; clearTimeout(timer); };
    }, [editText, activeTab]);

    // Rendered HTML for View tab (memoized from saved text)
    const viewHtml = useMemo(
        () => renderMarkdown(text),
        [text]
    );

    // Save handler (stable ref pattern to avoid circular deps)
    const saveRef = useRef(null);
    saveRef.current = async () => {
        if (!dirty || saving) return;
        console.debug(LOG_PREFIX, `save: starting, path=${path}`);
        setSaving(true);
        try {
            await api.put('/api/files/content', { path, content: editText });
            console.debug(LOG_PREFIX, 'save: success');
            setDirty(false);
            if (onSave) onSave(editText);
        } catch (e) {
            console.error(LOG_PREFIX, 'save: failed', e);
        } finally {
            setSaving(false);
        }
    };
    const handleSave = useCallback(() => saveRef.current?.(), []);

    // CM6 doc-change handler (shared by Edit and Source tabs)
    const handleDocChange = useCallback((newDoc) => {
        setEditText(newDoc);
        setDirty(newDoc !== text);
    }, [text]);

    const handleUndo = useCallback(() => { if (editorViewRef.current) undo(editorViewRef.current); }, []);
    const handleRedo = useCallback(() => { if (editorViewRef.current) redo(editorViewRef.current); }, []);

    // Tab switching — warn when leaving an edit tab with unsaved changes for View
    const handleTabSwitch = useCallback((newTab) => {
        console.debug(LOG_PREFIX, `tab switch: ${activeTab} → ${newTab}, dirty=${dirty}`);
        if (newTab === 'view' && dirty) {
            if (!confirm('Discard unsaved changes?')) {
                return;
            }
            setEditText(text);
            setDirty(false);
        }
        setActiveTab(newTab);
    }, [activeTab, dirty, text]);

    return html`
        <div class="markdown-editor">
            <div class="markdown-editor-toolbar">
                <div class="markdown-editor-tabs">
                    <button class=${activeTab === 'view' ? 'active' : ''}
                            onClick=${() => handleTabSwitch('view')}>View</button>
                    <button class=${activeTab === 'edit' ? 'active' : ''}
                            onClick=${() => handleTabSwitch('edit')}>
                        Edit${dirty ? html` <span class="markdown-dirty-indicator"></span>` : ''}
                    </button>
                    <button class=${activeTab === 'source' ? 'active' : ''}
                            onClick=${() => handleTabSwitch('source')}>
                        Source${dirty ? html` <span class="markdown-dirty-indicator"></span>` : ''}
                    </button>
                </div>
            </div>
            ${activeTab === 'view' && html`
                <div class="markdown-viewer"
                     dangerouslySetInnerHTML=${{ __html: viewHtml }}></div>
            `}
            ${activeTab === 'edit' && html`
                <div class="markdown-edit-pane">
                    <div class="markdown-edit-editor">
                        <${EditBar} dirty=${dirty} saving=${saving} language="Markdown"
                                    cursor=${cursor} onSave=${handleSave}
                                    onUndo=${handleUndo} onRedo=${handleRedo} />
                        <${CodeEditor}
                            doc=${editText}
                            path=${path}
                            readOnly=${false}
                            onDocChange=${handleDocChange}
                            onCursorChange=${setCursor}
                            onSave=${handleSave}
                            viewRef=${editorViewRef}
                            key=${path + ':edit'} />
                    </div>
                    <div class="markdown-edit-preview"
                         dangerouslySetInnerHTML=${{ __html: previewHtml }}></div>
                </div>
            `}
            ${activeTab === 'source' && html`
                <div class="markdown-source-pane">
                    <${EditBar} dirty=${dirty} saving=${saving} language="Markdown"
                                cursor=${cursor} onSave=${handleSave}
                                onUndo=${handleUndo} onRedo=${handleRedo} />
                    <${CodeEditor}
                        doc=${editText}
                        path=${path}
                        readOnly=${false}
                        onDocChange=${handleDocChange}
                        onCursorChange=${setCursor}
                        onSave=${handleSave}
                        viewRef=${editorViewRef}
                        key=${path + ':source'} />
                </div>
            `}
        </div>
    `;
}
