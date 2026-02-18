import { useState, useEffect } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function FileTree({ currentPath, onNavigate, onSelectFile, refreshKey, showHidden }) {
    const [entries, setEntries] = useState({});
    const [expanded, setExpanded] = useState({});
    const [selected, setSelected] = useState(null);

    useEffect(() => {
        reloadAll();
    }, [refreshKey, showHidden]);

    const reloadAll = async () => {
        const paths = ['', ...Object.keys(expanded)];
        for (const p of paths) {
            await loadDirectory(p);
        }
    };

    const loadDirectory = async (path) => {
        try {
            const data = await api.get(`/api/files?path=${encodeURIComponent(path)}&show_hidden=${showHidden}`);
            setEntries((prev) => ({ ...prev, [path]: data }));
        } catch {
            // toast is shown by api.js
        }
    };

    const toggleFolder = (path) => {
        setExpanded((prev) => {
            const next = { ...prev };
            if (next[path]) {
                delete next[path];
            } else {
                next[path] = true;
                loadDirectory(path);
            }
            return next;
        });
        onNavigate(path);
    };

    const selectFile = (path) => {
        setSelected(path);
        onSelectFile(path);
    };

    const renderEntries = (path, depth = 0) => {
        const items = entries[path] || [];
        return items.map((item) => {
            const itemPath = path ? `${path}/${item.name}` : item.name;
            if (item.type === 'directory') {
                return html`
                    <div key=${itemPath}>
                        <div
                            class="tree-item tree-folder ${expanded[itemPath] ? 'expanded' : ''}"
                            style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                            onClick=${() => toggleFolder(itemPath)}
                        >
                            <span class="tree-icon">${expanded[itemPath] ? '\u{1F4C2}' : '\u{1F4C1}'}</span>
                            ${item.name}
                        </div>
                        ${expanded[itemPath] && renderEntries(itemPath, depth + 1)}
                    </div>
                `;
            }
            return html`
                <div
                    key=${itemPath}
                    class="tree-item tree-file ${selected === itemPath ? 'selected' : ''}"
                    style=${{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick=${() => selectFile(itemPath)}
                >
                    <span class="tree-icon">\u{1F4C4}</span>
                    ${item.name}
                </div>
            `;
        });
    };

    return html`<div class="file-tree">${renderEntries('')}</div>`;
}
