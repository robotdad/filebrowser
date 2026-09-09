/**
 * wysiwyg-editor.js — Tiptap v2 WYSIWYG wrapper for markdown editing.
 *
 * Wraps Tiptap's vanilla JS Editor with the tiptap-markdown extension
 * so content round-trips as markdown. The candidate editor is checked against
 * its source serialization before it is made editable or exposed to the UI.
 *
 * Props:
 *   doc          — string, initial markdown content
 *   onDocChange  — function(markdownString), called on every content change
 *   onSave       — function(), called on Ctrl+S / Cmd+S
 *   onUnsafe     — called when this serializer cannot preserve doc exactly
 */
import { useRef, useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import { createLogger } from '../logger.js';
import {
    matchesMarkdownIgnoringTrailingLfs,
    restoreOriginalTrailingLfs,
} from '../lib/markdown-roundtrip.js';

const log = createLogger('WysiwygEditor');

export function WysiwygEditor({ doc, onDocChange, onSave, onEditorReady, onUnsafe }) {
    const containerRef = useRef(null);
    const callbacksRef = useRef({});
    const editableRef = useRef(false);
    callbacksRef.current = { onDocChange, onSave, onEditorReady, onUnsafe };

    useEffect(() => {
        if (!containerRef.current) return;

        const original = typeof doc === 'string' ? doc : '';
        log.debug(`mount: creating editor, doc=${original.length} chars`);

        const editor = new Editor({
            element: containerRef.current,
            editable: false,
            extensions: [
                StarterKit.configure({
                    codeBlock: false,
                }),
                Link.configure({
                    openOnClick: false,
                    HTMLAttributes: {
                        rel: 'noopener noreferrer',
                        target: '_blank',
                    },
                }),
                Markdown.configure({
                    html: false,
                    tightLists: true,
                    bulletListMarker: '-',
                }),
                Placeholder.configure({
                    placeholder: 'Start writing\u2026',
                }),
            ],
            content: original,
            editorProps: {
                attributes: {
                    class: 'wysiwyg-content',
                },
                handleKeyDown: (_view, event) => {
                    if (editableRef.current && (event.metaKey || event.ctrlKey) && event.key === 's') {
                        event.preventDefault();
                        callbacksRef.current.onSave?.();
                        return true;
                    }
                    return false;
                },
            },
            onUpdate: ({ editor: ed }) => {
                if (editableRef.current) {
                    const markdown = ed.storage.markdown.getMarkdown();
                    callbacksRef.current.onDocChange?.(
                        restoreOriginalTrailingLfs(original, markdown)
                    );
                }
            },
        });

        let safe = false;
        try {
            const serialized = editor.storage.markdown.getMarkdown();
            safe = matchesMarkdownIgnoringTrailingLfs(original, serialized);
        } catch (error) {
            log.warn('mount: markdown serializer preflight failed', error);
        }

        if (!safe) {
            log.warn('mount: rich editor blocked because serialization changes source');
            editor.destroy();
            callbacksRef.current.onUnsafe?.();
            return () => {
                editableRef.current = false;
            };
        }

        editableRef.current = true;
        editor.setEditable(true);
        callbacksRef.current.onEditorReady?.(editor);

        // Auto-focus at end of content when the Edit tab opens
        requestAnimationFrame(() => {
            if (!editor.isDestroyed) editor.commands.focus('end');
        });

        log.debug('mount: editor created');

        return () => {
            log.debug('unmount: destroying editor');
            editableRef.current = false;
            if (!editor.isDestroyed) editor.destroy();
        };
    }, []); // Mount once — parent controls remount via key prop

    return html`
        <div class="wysiwyg-editor" ref=${containerRef}></div>
    `;
}
