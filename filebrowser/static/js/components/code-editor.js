/**
 * code-editor.js — Shared CodeMirror 6 wrapper component.
 *
 * Used for both read-only source views and editable code.
 * Parent controls identity via Preact `key` prop — when the file changes,
 * set key=${filePath} to unmount/remount cleanly.
 */
import { useRef, useEffect, useState } from 'preact/hooks';
import { html } from '../html.js';
import { LANGUAGE_MAP, getFileExtension } from '../file-utils.js';
import { EditorView, keymap, lineNumbers, highlightActiveLine,
         highlightActiveLineGutter, drawSelection,
         highlightSpecialChars } from '@codemirror/view';
import { EditorState } from '@codemirror/state';
import { defaultKeymap, history, historyKeymap,
         indentWithTab } from '@codemirror/commands';
import { syntaxHighlighting, defaultHighlightStyle,
         bracketMatching, foldGutter, foldKeymap,
         indentOnInput } from '@codemirror/language';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';

/** Load a CM6 LanguageSupport for the given file path. Returns null for unknown. */
async function loadLanguage(path) {
    const ext = getFileExtension(path);
    const loader = LANGUAGE_MAP[ext];
    if (!loader) return null;
    try {
        return await loader();
    } catch (e) {
        console.warn(`Failed to load language for ${ext}:`, e);
        return null;
    }
}

/** App-aware CM6 theme using CSS variables from styles.css. */
const appTheme = EditorView.theme({
    '&': {
        fontSize: '13px',
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace",
    },
    '.cm-content': { padding: '8px 0' },
    '.cm-gutters': {
        backgroundColor: 'transparent',
        border: 'none',
    },
    '.cm-lineNumbers .cm-gutterElement': {
        padding: '0 8px 0 4px',
        minWidth: '3em',
    },
    '&.cm-focused': { outline: 'none' },
    '.cm-scroller': { overflow: 'auto' },
});

/**
 * CodeEditor — shared Preact component wrapping CodeMirror 6.
 *
 * Props:
 *   doc            — string, initial document content (required)
 *   path           — string, file path for language detection
 *   readOnly       — boolean, read-only mode (default false)
 *   onDocChange    — function(newDoc), called on every document change
 *   onCursorChange — function({line, col}), called on cursor move
 *   onSave         — function(), called on Ctrl+S / Cmd+S
 *   viewRef        — Preact ref, exposes EditorView for external control
 */
export function CodeEditor({ doc, path, readOnly = false, onDocChange,
                              onCursorChange, onSave, viewRef }) {
    const containerRef = useRef(null);
    const internalViewRef = useRef(null);
    const [loading, setLoading] = useState(true);

    // Create editor on mount, destroy on unmount.
    // Parent controls identity via key prop — doc/path changes remount.
    useEffect(() => {
        if (!containerRef.current) return;
        let destroyed = false;

        (async () => {
            const lang = await loadLanguage(path || '');
            if (destroyed) return;

            const extensions = [
                lineNumbers(),
                highlightActiveLineGutter(),
                highlightSpecialChars(),
                history(),
                foldGutter(),
                drawSelection(),
                EditorState.allowMultipleSelections.of(true),
                indentOnInput(),
                bracketMatching(),
                closeBrackets(),
                highlightActiveLine(),
                highlightSelectionMatches(),
                appTheme,
                syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
                keymap.of([
                    ...closeBracketsKeymap,
                    ...defaultKeymap,
                    ...searchKeymap,
                    ...historyKeymap,
                    ...foldKeymap,
                    indentWithTab,
                ]),
            ];

            if (lang) extensions.push(lang);

            if (readOnly) {
                extensions.push(EditorState.readOnly.of(true));
                extensions.push(EditorView.editable.of(false));
            }

            if (onDocChange) {
                extensions.push(EditorView.updateListener.of(update => {
                    if (update.docChanged) {
                        onDocChange(update.state.doc.toString());
                    }
                }));
            }

            if (onCursorChange) {
                extensions.push(EditorView.updateListener.of(update => {
                    if (update.selectionSet || update.docChanged) {
                        const pos = update.state.selection.main.head;
                        const line = update.state.doc.lineAt(pos);
                        onCursorChange({ line: line.number, col: pos - line.from + 1 });
                    }
                }));
            }

            if (onSave) {
                extensions.push(keymap.of([{
                    key: 'Mod-s',
                    run: () => { onSave(); return true; },
                }]));
            }

            const view = new EditorView({
                doc: doc || '',
                extensions,
                parent: containerRef.current,
            });

            internalViewRef.current = view;
            if (viewRef) viewRef.current = view;
            setLoading(false);
        })();

        return () => {
            destroyed = true;
            if (internalViewRef.current) {
                internalViewRef.current.destroy();
                internalViewRef.current = null;
            }
        };
    }, []); // Mount once — parent key prop controls remount

    return html`
        <div class="code-editor${loading ? ' code-editor-loading' : ''}"
             ref=${containerRef}>
            ${loading && html`<div class="code-editor-placeholder">Loading editor…</div>`}
        </div>
    `;
}