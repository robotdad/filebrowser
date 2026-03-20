import { useState, useEffect, useRef } from 'preact/hooks';
import { html } from '../html.js';

const FILE_ICON_MAP = [
    { exts: ['.png','.jpg','.jpeg','.gif','.webp','.svg','.bmp'], icon: 'ph-image', cls: 'file-icon-image' },
    { exts: ['.py','.js','.ts','.go','.rs','.c','.cpp','.java','.sh','.sql','.html','.css'], icon: 'ph-code', cls: 'file-icon-code' },
    { exts: ['.md'], icon: 'ph-article', cls: 'file-icon-markdown' },
    { exts: ['.txt','.log','.csv','.json','.xml','.yaml','.yml','.toml','.env','.conf'], icon: 'ph-file-text', cls: 'file-icon-text' },
    { exts: ['.mp3','.wav','.ogg','.flac','.aac','.m4a'], icon: 'ph-music-note', cls: 'file-icon-audio' },
    { exts: ['.mp4','.webm','.mkv','.mov','.avi'], icon: 'ph-film-strip', cls: 'file-icon-video' },
    { exts: ['.pdf'], icon: 'ph-file-pdf', cls: 'file-icon-pdf' },
];

function getIcon(name) {
    const dot = name.lastIndexOf('.');
    if (dot !== -1) {
        const ext = name.slice(dot).toLowerCase();
        for (const t of FILE_ICON_MAP) {
            if (t.exts.includes(ext)) return t;
        }
    }
    return { icon: 'ph-file', cls: 'file-icon-default' };
}

export function CommandPalette({ isOpen, onClose, allFiles, onSelectFile }) {
    const [query, setQuery] = useState('');
    const [activeIdx, setActiveIdx] = useState(0);
    const inputRef = useRef(null);
    const listRef = useRef(null);

    // Reset and focus when opened
    useEffect(() => {
        if (isOpen) {
            setQuery('');
            setActiveIdx(0);
            setTimeout(() => inputRef.current?.focus(), 0);
        }
    }, [isOpen]);

    // Build filtered results
    const results = query.trim()
        ? allFiles
              .filter(
                  (f) =>
                      f.type === 'file' &&
                      f.name.toLowerCase().includes(query.toLowerCase())
              )
              .slice(0, 50)
        : allFiles.filter((f) => f.type === 'file').slice(0, 20);

    // Clamp active index
    useEffect(() => {
        setActiveIdx((i) => Math.min(i, Math.max(results.length - 1, 0)));
    }, [results.length]);

    // Scroll active item into view
    useEffect(() => {
        if (!listRef.current) return;
        const el = listRef.current.querySelector('.command-item.highlighted');
        el?.scrollIntoView({ block: 'nearest' });
    }, [activeIdx]);

    const handleKeyDown = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIdx((i) => Math.min(i + 1, results.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIdx((i) => Math.max(i - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (results[activeIdx]) {
                onSelectFile(results[activeIdx].path);
                onClose();
            }
        } else if (e.key === 'Escape') {
            onClose();
        }
    };

    if (!isOpen) return null;

    return html`
        <div class="command-palette-overlay" onClick=${onClose}>
            <div class="command-palette" onClick=${(e) => e.stopPropagation()}>
                <div class="command-input-wrapper">
                    <i class="ph ph-magnifying-glass"></i>
                    <input
                        ref=${inputRef}
                        class="command-input"
                        placeholder="Search files…"
                        value=${query}
                        onInput=${(e) => { setQuery(e.target.value); setActiveIdx(0); }}
                        onKeyDown=${handleKeyDown}
                    />
                </div>

                <div class="command-results" ref=${listRef}>
                    ${results.length === 0 && html`
                        <div class="command-empty">
                            ${query ? `No files matching "${query}"` : 'No files loaded yet — expand a folder first'}
                        </div>
                    `}
                    ${results.length > 0 && !query && html`
                        <div class="command-section-label">Recent files</div>
                    `}
                    ${results.length > 0 && query && html`
                        <div class="command-section-label">${results.length} result${results.length !== 1 ? 's' : ''}</div>
                    `}
                    ${results.map((file, i) => {
                        const fi = getIcon(file.name);
                        const dir = file.path.includes('/')
                            ? file.path.slice(0, file.path.lastIndexOf('/'))
                            : '';
                        return html`
                            <button
                                key=${file.path}
                                class="command-item ${i === activeIdx ? 'highlighted' : ''}"
                                onClick=${() => { onSelectFile(file.path); onClose(); }}
                                onMouseEnter=${() => setActiveIdx(i)}
                            >
                                <span class="file-icon ${fi.cls}" style="width:24px;height:24px;font-size:13px;flex-shrink:0">
                                    <i class="ph ${fi.icon}"></i>
                                </span>
                                <div class="command-item-content">
                                    <div class="command-item-title">${file.name}</div>
                                    ${dir && html`<div class="command-item-path">${dir}</div>`}
                                </div>
                            </button>
                        `;
                    })}
                </div>

                <div class="command-hint">
                    <span class="command-hint-item">
                        <kbd>↑</kbd><kbd>↓</kbd> navigate
                    </span>
                    <span class="command-hint-item">
                        <kbd>↵</kbd> open
                    </span>
                    <span class="command-hint-item">
                        <kbd>Esc</kbd> close
                    </span>
                </div>
            </div>
        </div>
    `;
}
