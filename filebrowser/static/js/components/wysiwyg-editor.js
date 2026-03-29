/**
 * wysiwyg-editor.js — Tiptap v2 WYSIWYG wrapper for markdown editing.
 *
 * Wraps Tiptap's vanilla JS Editor with the tiptap-markdown extension
 * so content round-trips as markdown. Exposes the editor instance via
 * an imperative ref so the parent can flush markdown on tab switch.
 *
 * Props:
 *   doc          — string, initial markdown content
 *   onDocChange  — function(markdownString), called on every content change
 *   onSave       — function(), called on Ctrl+S / Cmd+S
 *   editorRef    — Preact ref, parent reads editorRef.current to get the
 *                  Tiptap Editor instance (for flushing markdown)
 */
import { useRef, useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import { Markdown } from 'tiptap-markdown';

const LOG_PREFIX = '[WysiwygEditor]';

export function WysiwygEditor({ doc, onDocChange, onSave, editorRef, onEditorReady }) {
    const containerRef = useRef(null);

    useEffect(() => {
        if (!containerRef.current) return;

        console.debug(LOG_PREFIX, `mount: creating editor, doc=${doc?.length ?? 0} chars`);

        const editor = new Editor({
            element: containerRef.current,
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
            ],
            content: doc || '',
            editorProps: {
                attributes: {
                    class: 'wysiwyg-content',
                },
                handleKeyDown: (_view, event) => {
                    if (onSave && (event.metaKey || event.ctrlKey) && event.key === 's') {
                        event.preventDefault();
                        onSave();
                        return true;
                    }
                    return false;
                },
            },
            onUpdate: ({ editor: ed }) => {
                if (onDocChange) {
                    const md = ed.storage.markdown.getMarkdown();
                    onDocChange(md);
                }
            },
        });

        if (editorRef) editorRef.current = editor;
        if (onEditorReady) onEditorReady(editor);

        // Auto-focus at end of content when the Edit tab opens
        requestAnimationFrame(() => {
            if (!editor.isDestroyed) editor.commands.focus('end');
        });

        console.debug(LOG_PREFIX, 'mount: editor created');

        return () => {
            console.debug(LOG_PREFIX, 'unmount: destroying editor');
            editor.destroy();
            if (editorRef) editorRef.current = null;
        };
    }, []); // Mount once — parent controls remount via key prop

    return html`
        <div class="wysiwyg-editor" ref=${containerRef}></div>
    `;
}
