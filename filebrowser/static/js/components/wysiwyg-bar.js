/**
 * wysiwyg-bar.js — Formatting toolbar for the WYSIWYG markdown editor.
 *
 * Renders formatting buttons (bold, italic, headings, lists, etc.) that
 * call Tiptap editor chain commands. Also includes Save/Undo/Redo.
 *
 * Props:
 *   editor   — Tiptap Editor instance (null while loading)
 *   dirty    — boolean, document has unsaved changes
 *   saving   — boolean, save in progress
 *   onSave   — function, trigger save
 */
import { html } from '../html.js';

function TipButton({ editor, icon, title, command, isActive }) {
    const active = editor && isActive ? isActive(editor) : false;
    const handleClick = (e) => {
        e.preventDefault();
        if (editor && command) {
            command(editor);
        }
    };

    return html`
        <button class=${'wysiwyg-bar-btn' + (active ? ' active' : '')}
                onClick=${handleClick}
                title=${title}
                type="button">
            <i class=${'ph ' + icon}></i>
        </button>
    `;
}

export function WysiwygBar({ editor, dirty, saving, onSave }) {
    const modKey = navigator.platform.includes('Mac') ? '\u2318' : 'Ctrl';

    return html`
        <div class="wysiwyg-bar">
            <div class="wysiwyg-bar-actions">
                <button class=${'edit-bar-save' + (dirty ? ' dirty' : '')}
                        onClick=${onSave}
                        disabled=${!dirty || saving}
                        type="button">
                    <i class=${'ph ' + (saving ? 'ph-circle-notch' : dirty ? 'ph-floppy-disk' : 'ph-check')}></i>
                    ${' '}${saving ? 'Saving\u2026' : dirty ? 'Save' : 'Saved'}
                </button>
                <span class="wysiwyg-bar-divider"></span>
            </div>
            <div class="wysiwyg-bar-formatting">
                <${TipButton} editor=${editor} icon="ph-text-bolder" title=${'Bold (' + modKey + '+B)'}
                    command=${(ed) => ed.chain().focus().toggleBold().run()}
                    isActive=${(ed) => ed.isActive('bold')} />
                <${TipButton} editor=${editor} icon="ph-text-italic" title=${'Italic (' + modKey + '+I)'}
                    command=${(ed) => ed.chain().focus().toggleItalic().run()}
                    isActive=${(ed) => ed.isActive('italic')} />
                <${TipButton} editor=${editor} icon="ph-text-strikethrough" title="Strikethrough"
                    command=${(ed) => ed.chain().focus().toggleStrike().run()}
                    isActive=${(ed) => ed.isActive('strike')} />
                <${TipButton} editor=${editor} icon="ph-code" title="Inline Code"
                    command=${(ed) => ed.chain().focus().toggleCode().run()}
                    isActive=${(ed) => ed.isActive('code')} />
                <span class="wysiwyg-bar-divider"></span>
                <${TipButton} editor=${editor} icon="ph-text-h-one" title="Heading 1"
                    command=${(ed) => ed.chain().focus().toggleHeading({ level: 1 }).run()}
                    isActive=${(ed) => ed.isActive('heading', { level: 1 })} />
                <${TipButton} editor=${editor} icon="ph-text-h-two" title="Heading 2"
                    command=${(ed) => ed.chain().focus().toggleHeading({ level: 2 }).run()}
                    isActive=${(ed) => ed.isActive('heading', { level: 2 })} />
                <${TipButton} editor=${editor} icon="ph-text-h-three" title="Heading 3"
                    command=${(ed) => ed.chain().focus().toggleHeading({ level: 3 }).run()}
                    isActive=${(ed) => ed.isActive('heading', { level: 3 })} />
                <span class="wysiwyg-bar-divider"></span>
                <${TipButton} editor=${editor} icon="ph-list-bullets" title="Bullet List"
                    command=${(ed) => ed.chain().focus().toggleBulletList().run()}
                    isActive=${(ed) => ed.isActive('bulletList')} />
                <${TipButton} editor=${editor} icon="ph-list-numbers" title="Ordered List"
                    command=${(ed) => ed.chain().focus().toggleOrderedList().run()}
                    isActive=${(ed) => ed.isActive('orderedList')} />
                <${TipButton} editor=${editor} icon="ph-quotes" title="Blockquote"
                    command=${(ed) => ed.chain().focus().toggleBlockquote().run()}
                    isActive=${(ed) => ed.isActive('blockquote')} />
                <span class="wysiwyg-bar-divider"></span>
                <${TipButton} editor=${editor} icon="ph-minus" title="Horizontal Rule"
                    command=${(ed) => ed.chain().focus().setHorizontalRule().run()}
                    isActive=${() => false} />
                <${TipButton} editor=${editor} icon="ph-link" title="Link"
                    command=${(ed) => {
                        if (ed.isActive('link')) {
                            const existing = ed.getAttributes('link').href || '';
                            const url = prompt('Enter URL:', existing);
                            if (url === null) return;           // cancelled
                            if (url === '') {
                                ed.chain().focus().unsetLink().run();
                            } else {
                                ed.chain().focus().setLink({ href: url }).run();
                            }
                        } else {
                            const url = prompt('Enter URL:');
                            if (url) ed.chain().focus().setLink({ href: url }).run();
                        }
                    }}
                    isActive=${(ed) => ed.isActive('link')} />
            </div>
            <div class="wysiwyg-bar-right">
                <button class="wysiwyg-bar-btn" title="Undo" type="button"
                        onClick=${() => editor?.chain().focus().undo().run()}>
                    <i class="ph ph-arrow-counter-clockwise"></i>
                </button>
                <button class="wysiwyg-bar-btn" title="Redo" type="button"
                        onClick=${() => editor?.chain().focus().redo().run()}>
                    <i class="ph ph-arrow-clockwise"></i>
                </button>
                <span class="edit-bar-hint">
                    <kbd>${modKey}</kbd>+<kbd>S</kbd>
                </span>
            </div>
        </div>
    `;
}
