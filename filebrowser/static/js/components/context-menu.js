import { useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';

/**
 * ContextMenu — right-click menu for tree items.
 *
 * Props:
 *   menu  — null | { x, y, path, type }
 *   onClose()
 *   onOpen(path)
 *   onDownload(path)
 *   onRename(path)
 *   onDelete(path)
 *   onCopyPath(path)
 */
export function ContextMenu({ menu, onClose, onOpen, onDownload, onRename, onDelete, onCopyPath }) {
    const ref = useRef(null);

    // Close on outside click or Escape
    useEffect(() => {
        if (!menu) return;
        const handleClick = (e) => {
            if (ref.current && !ref.current.contains(e.target)) onClose();
        };
        const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
        // Small delay so the right-click event itself doesn't immediately close
        const t = setTimeout(() => {
            document.addEventListener('mousedown', handleClick);
            document.addEventListener('keydown', handleKey);
        }, 0);
        return () => {
            clearTimeout(t);
            document.removeEventListener('mousedown', handleClick);
            document.removeEventListener('keydown', handleKey);
        };
    }, [menu]);

    if (!menu) return null;

    // Keep menu within viewport
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const menuW = 192;
    const menuH = menu.type === 'file' ? 200 : 120;
    const x = menu.x + menuW > vw ? vw - menuW - 8 : menu.x;
    const y = menu.y + menuH > vh ? vh - menuH - 8 : menu.y;

    const act = (fn) => (e) => {
        e.stopPropagation();
        fn(menu.path);
        onClose();
    };

    return html`
        <div
            ref=${ref}
            class="context-menu"
            style=${{ left: `${x}px`, top: `${y}px` }}
            onContextMenu=${(e) => e.preventDefault()}
        >
            ${menu.type === 'file' && html`
                <button class="context-menu-item" onClick=${act(onOpen)}>
                    <i class="ph ph-arrow-square-out"></i> Open
                </button>
                <button class="context-menu-item" onClick=${act(onDownload)}>
                    <i class="ph ph-download-simple"></i> Download
                </button>
                <div class="context-menu-divider"></div>
            `}
            <button class="context-menu-item" onClick=${act(onRename)}>
                <i class="ph ph-pencil-simple"></i> Rename
            </button>
            <button class="context-menu-item" onClick=${act(onCopyPath)}>
                <i class="ph ph-copy"></i> Copy path
            </button>
            <div class="context-menu-divider"></div>
            <button class="context-menu-item danger" onClick=${act(onDelete)}>
                <i class="ph ph-trash"></i> Delete
            </button>
        </div>
    `;
}
