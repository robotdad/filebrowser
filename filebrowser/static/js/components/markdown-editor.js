/**
 * markdown-editor.js — file-level editor for markdown files.
 *
 * Three tabs:
 *   View   — Rendered markdown (marked + DOMPurify), read-only
 *   Edit   — WYSIWYG rich-text editor (Tiptap v2 + tiptap-markdown)
 *   Source — Split-pane: CodeMirror 6 editor + live rendered preview
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { CodeEditor } from './code-editor.js';
import { EditBar } from './edit-bar.js';
import { WysiwygEditor } from './wysiwyg-editor.js';
import { WysiwygBar } from './wysiwyg-bar.js';
import { undo, redo } from '@codemirror/commands';

const LOG_PREFIX = '[MarkdownEditor]';

/** Render markdown text to sanitized HTML. */
function renderMarkdown(text) {
    return DOMPurify.sanitize(marked.parse(text || ''));
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
    const [previewHtml, setPreviewHtml] = useState(() => renderMarkdown(text));
    const editorViewRef = useRef(null);       // CodeMirror EditorView (Source tab)
    const wysiwygEditorRef = useRef(null);    // Tiptap Editor (Edit tab)
    const sourceInitRef = useRef(false);      // tracks first open of Source tab

    // Sync editText when text prop changes (new file or post-save)
    useEffect(() => {
        setEditText(text);
        setPreviewHtml(renderMarkdown(text));
        setDirty(false);
    }, [text]);

    // Live preview for Source tab (immediate on first open, debounced after)
    useEffect(() => {
        if (activeTab !== 'source') {
            sourceInitRef.current = false;
            return;
        }
        if (!editText) { setPreviewHtml(''); return; }

        if (!sourceInitRef.current) {
            sourceInitRef.current = true;
            setPreviewHtml(renderMarkdown(editText));
            return;
        }

        let cancelled = false;
        const timer = setTimeout(() => {
            if (!cancelled) setPreviewHtml(renderMarkdown(editText));
        }, 300);
        return () => { cancelled = true; clearTimeout(timer); };
    }, [editText, activeTab]);

    // Rendered HTML for View tab (memoized from saved text only)
    const viewHtml = useMemo(() => renderMarkdown(text), [text]);

    // Stable save callback via ref to avoid stale closures
    const saveRef = useRef(null);
    saveRef.current = async () => {
        if (!dirty || saving) return;
        setSaving(true);
        try {
            await api.put('/api/files/content', { path, content: editText });
            setDirty(false);
            if (onSave) onSave(editText);
        } catch (e) {
            console.error(LOG_PREFIX, 'save failed', e);
        } finally {
            setSaving(false);
        }
    };
    const handleSave = useCallback(() => saveRef.current?.(), []);

    // CodeMirror doc-change handler (Source tab)
    const handleDocChange = useCallback((newDoc) => {
        setEditText(newDoc);
        setDirty(newDoc !== text);
    }, [text]);

    // WYSIWYG doc-change handler (Edit tab)
    const handleWysiwygChange = useCallback((newMarkdown) => {
        setEditText(newMarkdown);
        setDirty(newMarkdown !== text);
    }, [text]);

    const handleUndo = useCallback(() => { if (editorViewRef.current) undo(editorViewRef.current); }, []);
    const handleRedo = useCallback(() => { if (editorViewRef.current) redo(editorViewRef.current); }, []);

    // Flush WYSIWYG editor's current markdown to editText before switching away
    const flushWysiwyg = useCallback(() => {
        const editor = wysiwygEditorRef.current;
        if (editor && !editor.isDestroyed) {
            const md = editor.storage.markdown.getMarkdown();
            setEditText(md);
            return md;
        }
        return editText;
    }, [editText]);

    // Tab switching — flush WYSIWYG on exit, warn when discarding to View
    const handleTabSwitch = useCallback((newTab) => {
        if (newTab === 'view' && dirty) {
            if (!confirm('Discard unsaved changes?')) return;
            setEditText(text);
            setDirty(false);
            setActiveTab(newTab);
            return; // skip flush — we're discarding
        }
        if (activeTab === 'wysiwyg') flushWysiwyg();
        setActiveTab(newTab);
    }, [activeTab, dirty, text, flushWysiwyg]);

    // Track Tiptap editor instance for the toolbar
    const [tiptapEditor, setTiptapEditor] = useState(null);
    // Clear tiptapEditor when leaving the wysiwyg tab (WysiwygEditor unmounts)
    useEffect(() => {
        if (activeTab !== 'wysiwyg') setTiptapEditor(null);
    }, [activeTab]);
    const handleEditorReady = useCallback((editor) => {
        setTiptapEditor(editor);
    }, []);

    return html`
        <div class="markdown-editor">
            <div class="markdown-editor-toolbar">
                <div class="markdown-editor-tabs">
                    <button class=${activeTab === 'view' ? 'active' : ''}
                            onClick=${() => handleTabSwitch('view')}>View</button>
                    <button class=${activeTab === 'wysiwyg' ? 'active' : ''}
                            onClick=${() => handleTabSwitch('wysiwyg')}>
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
            ${activeTab === 'wysiwyg' && html`
                <div class="wysiwyg-pane">
                    <${WysiwygBar} editor=${tiptapEditor} dirty=${dirty}
                                   saving=${saving} onSave=${handleSave} />
                    <${WysiwygEditor}
                        doc=${editText}
                        onDocChange=${handleWysiwygChange}
                        onSave=${handleSave}
                        editorRef=${wysiwygEditorRef}
                        onEditorReady=${handleEditorReady}
                        key=${path + ':wysiwyg'} />
                </div>
            `}
            ${activeTab === 'source' && html`
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
                            key=${path + ':source'} />
                    </div>
                    <div class="markdown-edit-preview"
                         dangerouslySetInnerHTML=${{ __html: previewHtml }}></div>
                </div>
            `}
        </div>
    `;
}
