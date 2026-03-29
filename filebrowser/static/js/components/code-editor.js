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
import { oneDark } from '@codemirror/theme-one-dark';
import { createLogger } from '../logger.js';

const log = createLogger('CodeEditor');

/** Load a CM6 LanguageSupport for the given file path. Returns null for unknown. */
async function loadLanguage(path) {
    const ext = getFileExtension(path);
    const loader = LANGUAGE_MAP[ext];
    if (!loader) return null;
    try {
        const lang = await loader();
        log.debug('language loaded: ext=%s', ext);
        return lang;
    } catch (e) {
        log.warn(`Failed to load language for ${ext}:`, e);
        return null;
    }
}

/** Detect current color scheme preference. */
function isDarkMode() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

/** Light mode base theme. */
const lightTheme = EditorView.theme({
    '&': {
        fontSize: '13px',
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace",
        backgroundColor: 'var(--bg-secondary)',
        color: 'var(--text-primary)',
    },
    '.cm-content': {
        padding: '8px 0',
        caretColor: '#000',
    },
    '&.cm-focused .cm-cursor': {
        borderLeftColor: '#000',
        borderLeftWidth: '2px',
    },
    '.cm-gutters': {
        backgroundColor: 'transparent',
        color: 'var(--text-muted)',
        border: 'none',
    },
    '.cm-lineNumbers .cm-gutterElement': {
        padding: '0 8px 0 4px',
        minWidth: '3em',
    },
    '&.cm-focused': { outline: 'none' },
    '.cm-scroller': { overflow: 'auto' },
    '.cm-activeLine': { backgroundColor: 'rgba(0, 0, 0, 0.04)' },
    '.cm-activeLineGutter': { backgroundColor: 'rgba(0, 0, 0, 0.04)' },
});

/** Dark mode base theme — cursor, gutter, active line overrides. */
const darkTheme = EditorView.theme({
    '&': {
        fontSize: '13px',
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace",
    },
    '.cm-content': {
        padding: '8px 0',
        caretColor: '#fff',
    },
    '&.cm-focused .cm-cursor': {
        borderLeftColor: '#fff',
        borderLeftWidth: '2px',
    },
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
}, { dark: true });

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
        log.debug('mount: path=%s', path);
        let destroyed = false;

        (async () => {
            const lang = await loadLanguage(path || '');
            if (destroyed) return;

            const dark = isDarkMode();
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
                dark ? darkTheme : lightTheme,
                // oneDark provides both a base theme AND a highlight style for dark mode.
                // For light mode, use defaultHighlightStyle as the syntax color scheme.
                dark ? oneDark : syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
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