/**
 * markdown-editor.js — View/Edit/Source tri-mode editor for markdown files.
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
    const previewRef = useRef(null);
    // Track whether the edit tab has been opened (for immediate vs debounced render)
    const editInitRef = useRef(false);

    console.debug(LOG_PREFIX, `render: activeTab=${activeTab}, dirty=${dirty}, ` +
        `editText=${editText?.length ?? 0} chars, previewHtml=${previewHtml?.length ?? 0} chars`);

    // Diagnostic: log preview pane DOM dimensions + ancestor scroll/visibility
    useEffect(() => {
        if (activeTab !== 'edit') return;

        const diagnose = (label) => {
            const el = previewRef.current;
            if (!el) { console.warn(LOG_PREFIX, `${label}: previewRef is null`); return; }
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            console.debug(LOG_PREFIX, `${label}: preview size=${el.clientWidth}x${el.clientHeight}, ` +
                `rect=${Math.round(rect.width)}x${Math.round(rect.height)} @ (${Math.round(rect.top)},${Math.round(rect.left)}), ` +
                `scrollH=${el.scrollHeight}, html=${el.innerHTML.length} chars, ` +
                `opacity=${style.opacity}, visibility=${style.visibility}, display=${style.display}`);
            // Walk ancestors: check scroll positions and dimensions
            let anc = el.parentElement;
            let depth = 0;
            while (anc && depth < 8) {
                const r = anc.getBoundingClientRect();
                const overflow = getComputedStyle(anc).overflow;
                const scrollInfo = (overflow !== 'visible')
                    ? `, scroll=${anc.scrollTop}/${anc.scrollHeight - anc.clientHeight}`
                    : '';
                if (r.height === 0 || anc.scrollTop > 0 || overflow !== 'visible') {
                    console.debug(LOG_PREFIX, `${label}: ancestor[${depth}] cls="${anc.className.slice(0, 50)}" ` +
                        `size=${Math.round(r.width)}x${Math.round(r.height)}, overflow=${overflow}${scrollInfo}`);
                }
                anc = anc.parentElement;
                depth++;
            }
        };

        // Check immediately after paint
        const raf = requestAnimationFrame(() => diagnose('paint'));
        // Check again after 2s (post-CodeMirror init)
        const timer = setTimeout(() => diagnose('2s-later'), 2000);
        return () => { cancelAnimationFrame(raf); clearTimeout(timer); };
    }, [activeTab, previewHtml]);

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
            console.debug(LOG_PREFIX, 'edit preview: editText is empty, clearing preview');
            setPreviewHtml('');
            return;
        }

        // Render immediately on first open / tab switch; debounce subsequent edits
        if (!editInitRef.current) {
            editInitRef.current = true;
            console.debug(LOG_PREFIX, 'edit preview: initial render (immediate)');
            setPreviewHtml(renderMarkdown(editText));
            return;
        }

        let cancelled = false;
        console.debug(LOG_PREFIX, 'edit preview: scheduling debounced render (300ms)');
        const timer = setTimeout(() => {
            if (!cancelled) {
                console.debug(LOG_PREFIX, 'edit preview: debounced render firing');
                setPreviewHtml(renderMarkdown(editText));
            } else {
                console.debug(LOG_PREFIX, 'edit preview: debounced render cancelled');
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
        console.debug(LOG_PREFIX, `save: starting, path=${path}, content=${editText?.length ?? 0} chars`);
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
                console.debug(LOG_PREFIX, 'tab switch: cancelled by user (dirty discard)');
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
                         ref=${previewRef}
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
