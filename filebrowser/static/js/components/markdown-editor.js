/**
 * markdown-editor.js — file-level editor for markdown files.
 *
 * Three tabs:
 *   View   — Rendered markdown (marked + DOMPurify), read-only
 *   Edit   — WYSIWYG rich-text editor (Tiptap v2 + tiptap-markdown)
 *   Source — Split-pane: CodeMirror 6 editor + live rendered preview
 */
import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { CodeEditor } from './code-editor.js';
import { EditBar } from './edit-bar.js';
import { WysiwygEditor } from './wysiwyg-editor.js';
import { WysiwygBar } from './wysiwyg-bar.js';
import { undo, redo } from '@codemirror/commands';
import { createLogger } from '../logger.js';
import { stripFrontmatter, transformWikilinks, renderFrontmatter } from '../lib/preprocess-markdown.js';
import { rewriteImageSrc } from '../lib/rewrite-image-src.js';

const log = createLogger('MarkdownEditor');

/**
 * Render markdown text to sanitized HTML, with relative image sources rewritten
 * to the authenticated `/api/files/content?path=...` endpoint.
 *
 * @param {string} text - Raw markdown source
 * @param {string} currentFile - Repo-relative path of the markdown file being rendered
 * @returns {string} Sanitized HTML string
 */
function renderMarkdown(text, currentFile) {
    // Strip YAML frontmatter and transform Obsidian wikilinks before parsing
    const { frontmatter, body } = stripFrontmatter(text || '');
    const processedBody = transformWikilinks(body);
    
    // Render frontmatter panel (if any) and markdown body
    const frontmatterHtml = renderFrontmatter(frontmatter);
    const bodyHtml = marked.parse(processedBody);
    
    // Sanitize the combined HTML (frontmatter panel + body)
    const sanitized = DOMPurify.sanitize(frontmatterHtml + bodyHtml);

    // Rewrite relative img src attributes to the authenticated content API.
    // We parse the sanitized HTML fragment, mutate img elements, and serialise
    // back to a string -- all in-process, no network requests.
    if (!currentFile) return sanitized;
    const template = document.createElement('template');
    template.innerHTML = sanitized;
    template.content.querySelectorAll('img').forEach((img) => {
        img.src = rewriteImageSrc(currentFile, img.getAttribute('src') || '');
    });
    return template.innerHTML;
}

/**
 * MarkdownEditor — tri-mode markdown file editor.
 *
 * Props:
 *   text    — file content string (markdown source)
 *   path    — file path (for save API and language detection)
 *   onSave  — callback after successful save, receives new text
 */
export function MarkdownEditor(props) {
    // File identity owns every buffer and pending-save lifetime, even when the
    // caller reuses this component rather than keying its preview container.
    return html`<${MarkdownEditorDocument} ...${props} key=${props.path} />`;
}

function MarkdownEditorDocument({
    text, path, onSave, onSaveStarted, onSaveSettled, onSaveFailed, onDirtyChange,
    confirmOverwrite = false, saveLocked = false,
}) {
    const [activeTab, setActiveTab] = useState('view');
    const [editText, setEditText] = useState(text);
    const [dirty, setDirty] = useState(false);

    useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
    const [saving, setSaving] = useState(false);
    const [cursor, setCursor] = useState(null);
    const [previewHtml, setPreviewHtml] = useState(() => renderMarkdown(text, path));
    const editorViewRef = useRef(null);       // CodeMirror EditorView (Source tab)
    const sourceInitRef = useRef(false);      // tracks first open of Source tab
    const savedTextRef = useRef(text);        // content baseline for dirty checks
    const draftRef = useRef(text);           // includes edits made before a render
    const savingRef = useRef(false);         // synchronous duplicate-save lock
    const aliveRef = useRef(true);
    const loadVersionRef = useRef(0);
    const [loadVersion, setLoadVersion] = useState(0);
    const [richEditBlockReason, setRichEditBlockReason] = useState(null);

    useLayoutEffect(() => {
        aliveRef.current = true;
        return () => { aliveRef.current = false; };
    }, []);

    // Log component mount with initial tab
    useEffect(() => {
        log.debug('mount: mode=%s', activeTab);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Own-save acknowledgements equal the saved baseline. They must not replace
    // edits made while that PUT was in flight. An actual external replacement
    // invalidates pending callbacks and remounts the mount-only editor widgets.
    useLayoutEffect(() => {
        if (text === savedTextRef.current) return;
        loadVersionRef.current += 1;
        setLoadVersion(loadVersionRef.current);
        savedTextRef.current = text;
        draftRef.current = text;
        // A reload invalidates the acknowledgement, not the outstanding write.
        // Keep saving locked until it settles to prevent out-of-order PUTs.
        setEditText(text);
        setPreviewHtml(renderMarkdown(text, path));
        setDirty(false);
        setRichEditBlockReason(null);
    }, [text, path]);

    // Live preview for Source tab (immediate on first open, debounced after)
    useEffect(() => {
        if (activeTab !== 'source') {
            sourceInitRef.current = false;
            return;
        }
        if (!editText) { setPreviewHtml(''); return; }

        if (!sourceInitRef.current) {
            sourceInitRef.current = true;
            setPreviewHtml(renderMarkdown(editText, path));
            return;
        }

        let cancelled = false;
        const timer = setTimeout(() => {
            if (!cancelled) setPreviewHtml(renderMarkdown(editText, path));
        }, 300);
        return () => { cancelled = true; clearTimeout(timer); };
    }, [editText, activeTab, path]);

    // Rendered HTML for View tab (memoized from saved text only)
    const viewHtml = useMemo(() => renderMarkdown(text, path), [text, path]);

    // Stable save callback via ref to avoid stale closures
    const saveRef = useRef(null);
    saveRef.current = async () => {
        if (draftRef.current === savedTextRef.current || savingRef.current || saveLocked) return;
        if (confirmOverwrite && !confirm('This file changed on disk since you kept your version. Overwrite the on-disk changes?')) return;
        const contentToSave = draftRef.current;
        const saveVersion = loadVersionRef.current;
        const isCurrent = () => aliveRef.current && loadVersionRef.current === saveVersion;
        savingRef.current = true;
        setSaving(true);
        try {
            log.debug('save: path=%s size=%d', path, contentToSave.length);
            if (onSaveStarted) onSaveStarted(path, contentToSave);
            const response = await api.put('/api/files/content', { path, content: contentToSave });
            // The parent owns cross-remount reconciliation.  It must see a
            // completed save even if this editor was unmounted while awaiting
            // the response, whereas this document must not update itself then.
            if (onSaveSettled) onSaveSettled(path, contentToSave, response);
            if (!isCurrent()) return;
            savedTextRef.current = contentToSave;
            setDirty(draftRef.current !== contentToSave);
            log.info('saved: path=%s', path);
            if (onSave && !onSaveSettled) onSave(contentToSave, response);
        } catch (e) {
            log.error('save failed', e);
            if (onSaveFailed) onSaveFailed(path);
        } finally {
            if (aliveRef.current) {
                savingRef.current = false;
                setSaving(false);
            }
        }
    };
    const handleSave = useCallback(() => saveRef.current?.(), []);

    // CodeMirror doc-change handler (Source tab)
    const handleDocChange = useCallback((newDoc) => {
        draftRef.current = newDoc;
        setEditText(newDoc);
        setDirty(newDoc !== savedTextRef.current);
        setRichEditBlockReason(null);
    }, []);

    // WYSIWYG doc-change handler (Edit tab)
    const handleWysiwygChange = useCallback((newMarkdown) => {
        draftRef.current = newMarkdown;
        setEditText(newMarkdown);
        setDirty(newMarkdown !== savedTextRef.current);
    }, []);

    const handleUndo = useCallback(() => { if (editorViewRef.current) undo(editorViewRef.current); }, []);
    const handleRedo = useCallback(() => { if (editorViewRef.current) redo(editorViewRef.current); }, []);

    // Tab switching — WYSIWYG changes are synchronized only by onUpdate.
    // Never serialize merely because the user leaves the tab.
    const handleTabSwitch = useCallback((newTab) => {
        if (newTab === 'wysiwyg') setRichEditBlockReason(null);
        if (newTab === 'view' && dirty) {
            if (!confirm('Discard unsaved changes?')) return;
            draftRef.current = savedTextRef.current;
            setEditText(savedTextRef.current);
            setDirty(false);
            setActiveTab(newTab);
            return;
        }
        setActiveTab(newTab);
    }, [dirty]);

    // Track Tiptap editor instance for the toolbar
    const [tiptapEditor, setTiptapEditor] = useState(null);
    // Clear tiptapEditor when leaving the wysiwyg tab (WysiwygEditor unmounts)
    useEffect(() => {
        if (activeTab !== 'wysiwyg') setTiptapEditor(null);
    }, [activeTab]);
    const handleEditorReady = useCallback((editor) => {
        setTiptapEditor(editor);
    }, []);
    const handleUnsafeWysiwyg = useCallback(() => {
        setRichEditBlockReason(
            'Rich editing blocked: this editor cannot preserve this Markdown. Use Source to edit it; original unchanged.'
        );
        setActiveTab('source');
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
            ${richEditBlockReason && html`
                <div class="markdown-rich-edit-notice" role="alert">
                    ${richEditBlockReason}
                </div>
            `}
            ${activeTab === 'view' && html`
                <div class="markdown-viewer"
                     dangerouslySetInnerHTML=${{ __html: viewHtml }}></div>
            `}
            ${activeTab === 'wysiwyg' && html`
                <div class="wysiwyg-pane">
                    <${WysiwygBar} editor=${tiptapEditor} dirty=${dirty}
                                   saving=${saving || saveLocked} onSave=${handleSave} />
                    <${WysiwygEditor}
                        doc=${editText}
                        onDocChange=${handleWysiwygChange}
                        onSave=${handleSave}
                        onEditorReady=${handleEditorReady}
                        onUnsafe=${handleUnsafeWysiwyg}
                        key=${path + ':' + loadVersion + ':wysiwyg'} />
                </div>
            `}
            ${activeTab === 'source' && html`
                <div class="markdown-edit-pane">
                    <div class="markdown-edit-editor">
                        <${EditBar} dirty=${dirty} saving=${saving} language="Markdown"
                                    cursor=${cursor} saving=${saving || saveLocked} onSave=${handleSave}
                                    onUndo=${handleUndo} onRedo=${handleRedo} />
                        <${CodeEditor}
                            doc=${editText}
                            path=${path}
                            readOnly=${false}
                            onDocChange=${handleDocChange}
                            onCursorChange=${setCursor}
                            onSave=${handleSave}
                            viewRef=${editorViewRef}
                            key=${path + ':' + loadVersion + ':source'} />
                    </div>
                    <div class="markdown-edit-preview"
                         dangerouslySetInnerHTML=${{ __html: previewHtml }}></div>
                </div>
            `}
        </div>
    `;
}
