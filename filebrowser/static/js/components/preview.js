import { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import hljs from 'highlight.js';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { wasmFolder, graphviz as hpccGraphviz } from '@hpcc-js/wasm';
import * as d3 from 'd3';
import { graphviz as d3Graphviz } from 'd3-graphviz';
import GraphvizSvg from '../graphviz-svg.js';

// Set WASM path before d3-graphviz tries to load it
wasmFolder('https://cdn.jsdelivr.net/npm/@hpcc-js/wasm@1.16.6/dist');

// Register DOT/Graphviz language for highlight.js
hljs.registerLanguage('dot', function() {
    return {
        name: 'DOT',
        aliases: ['gv', 'graphviz'],
        case_insensitive: true,
        keywords: {
            keyword: 'strict digraph graph subgraph node edge',
        },
        contains: [
            hljs.C_LINE_COMMENT_MODE,          // // comment
            hljs.C_BLOCK_COMMENT_MODE,          // /* comment */
            hljs.HASH_COMMENT_MODE,             // # comment
            hljs.QUOTE_STRING_MODE,             // "string"
            {
                // HTML-like labels: < ... >
                className: 'string',
                begin: /</, end: />/,
                contains: [{ begin: /[^<>]+/ }],
            },
            {
                // Attribute names (before =)
                className: 'attr',
                begin: /\b[a-zA-Z_]\w*(?=\s*=)/,
            },
            {
                // Edge operators
                className: 'operator',
                begin: /->|--/,
            },
            {
                // Numbers
                className: 'number',
                begin: /\b\d+(\.\d+)?\b/,
            },
            {
                // Hex colors
                className: 'number',
                begin: /"#[0-9a-fA-F]{3,8}"/,
            },
        ],
    };
});

const FILE_TYPES = {
    text:     ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
    code:     ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.css'],
    html:     ['.html', '.htm'],
    markdown: ['.md'],
    image:    ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'],
    audio:    ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'],
    video:    ['.mp4', '.webm', '.mkv', '.mov', '.avi'],
    pdf:      ['.pdf'],
    graphviz: ['.dot', '.gv'],
};

function getFileType(path) {
    const dot = path.lastIndexOf('.');
    if (dot === -1) return 'other';
    const ext = path.slice(dot).toLowerCase();
    for (const [type, exts] of Object.entries(FILE_TYPES)) {
        if (exts.includes(ext)) return type;
    }
    return 'other';
}

function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
}

function formatDate(isoString) {
    const d = new Date(isoString);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffHr = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);
    let relative;
    if (diffMin < 1) relative = 'just now';
    else if (diffMin < 60) relative = `${diffMin}m ago`;
    else if (diffHr < 24) relative = `${diffHr}h ago`;
    else if (diffDay < 7) relative = `${diffDay}d ago`;
    else relative = null;

    const absolute = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
        + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return relative ? `${relative} (${absolute})` : absolute;
}

function FileInfoBar({ filePath }) {
    const [info, setInfo] = useState(null);

    useEffect(() => {
        if (!filePath) { setInfo(null); return; }
        api.get(`/api/files/info?path=${encodeURIComponent(filePath)}`)
            .then(setInfo)
            .catch(() => setInfo(null));
    }, [filePath]);

    if (!info) return null;

    const name = filePath.split('/').pop();
    return html`
        <div class="file-info-bar">
            <span class="file-info-name" title=${filePath}>${name}</span>
            <span class="file-info-meta">
                ${info.size != null && html`<span>${formatSize(info.size)}</span>`}
                ${info.modified && html`<span>Modified ${formatDate(info.modified)}</span>`}
            </span>
        </div>
    `;
}

function TextViewer({ text }) {
    const lines = text.split('\n');
    return html`
        <div class="text-viewer">
            <pre><code>${lines.map(
                (line, i) => html`<div class="line"><span class="line-number">${i + 1}</span><span class="line-content">${line}</span></div>`
            )}</code></pre>
        </div>
    `;
}

function CodeViewer({ text, path }) {
    const codeRef = useRef(null);

    useEffect(() => {
        if (codeRef.current) {
            codeRef.current.textContent = text;
            hljs.highlightElement(codeRef.current);
        }
    }, [text]);

    const ext = path.split('.').pop();
    const langMap = { py: 'python', js: 'javascript', ts: 'typescript', rs: 'rust', sh: 'bash', yml: 'yaml' };
    const lang = langMap[ext] || ext;

    return html`
        <div class="code-viewer">
            <pre><code ref=${codeRef} class="language-${lang}">${text}</code></pre>
        </div>
    `;
}

function MarkdownViewer({ text }) {
    const htmlContent = useMemo(() => DOMPurify.sanitize(marked.parse(text)), [text]);
    return html`<div class="markdown-viewer" dangerouslySetInnerHTML=${{ __html: htmlContent }}></div>`;
}

function ImageViewer({ contentUrl, filePath }) {
    const [zoom, setZoom] = useState(1);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const isDragging = useRef(false);
    const dragStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 });
    const canvasRef = useRef(null);
    const imgRef = useRef(null);
    const fitScale = useRef(1);

    const clampZoom = (z) => Math.min(Math.max(z, 0.1), 20);

    const computeFitScale = () => {
        const canvas = canvasRef.current;
        const img = imgRef.current;
        if (!canvas || !img || !img.naturalWidth) return 1;
        const scale = Math.min(
            canvas.clientWidth / img.naturalWidth,
            canvas.clientHeight / img.naturalHeight,
            1  // never upscale small images
        );
        return clampZoom(scale);
    };

    const handleImageLoad = () => {
        fitScale.current = computeFitScale();
        setZoom(fitScale.current);
        setOffset({ x: 0, y: 0 });
    };

    const handleWheel = (e) => {
        e.preventDefault();
        const factor = e.deltaY > 0 ? 0.9 : 1.1;
        setZoom(z => clampZoom(z * factor));
    };

    const handleMouseDown = (e) => {
        if (e.button !== 0) return;
        isDragging.current = true;
        dragStart.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
        canvasRef.current?.classList.add('dragging');
    };

    const handleMouseMove = (e) => {
        if (!isDragging.current) return;
        setOffset({
            x: dragStart.current.ox + e.clientX - dragStart.current.x,
            y: dragStart.current.oy + e.clientY - dragStart.current.y,
        });
    };

    const handleMouseUp = () => {
        isDragging.current = false;
        canvasRef.current?.classList.remove('dragging');
    };

    const reset = () => { setZoom(fitScale.current); setOffset({ x: 0, y: 0 }); };

    return html`
        <div class="image-viewer">
            <div class="image-viewer-toolbar">
                <button onClick=${() => setZoom(z => clampZoom(z * 1.25))} title="Zoom in">
                    <i class="ph ph-magnifying-glass-plus"></i>
                </button>
                <button onClick=${() => setZoom(z => clampZoom(z * 0.8))} title="Zoom out">
                    <i class="ph ph-magnifying-glass-minus"></i>
                </button>
                <span class="zoom-level">${Math.round(zoom * 100)}%</span>
                <button onClick=${reset} title="Fit to window">
                    <i class="ph ph-arrows-in"></i> Fit
                </button>
            </div>
            <div class="image-viewer-canvas"
                 ref=${canvasRef}
                 onWheel=${handleWheel}
                 onMouseDown=${handleMouseDown}
                 onMouseMove=${handleMouseMove}
                 onMouseUp=${handleMouseUp}
                 onMouseLeave=${handleMouseUp}>
                <img
                    ref=${imgRef}
                    src=${contentUrl}
                    alt=${filePath}
                    onLoad=${handleImageLoad}
                    style=${{
                        transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
                        transformOrigin: 'center center',
                    }}
                    draggable="false"
                />
            </div>
        </div>
    `;
}

function HtmlViewer({ text, path, contentUrl }) {
    const [showSource, setShowSource] = useState(false);
    const codeRef = useRef(null);

    useEffect(() => {
        if (showSource && codeRef.current) {
            codeRef.current.textContent = text;
            hljs.highlightElement(codeRef.current);
        }
    }, [showSource, text]);

    return html`
        <div class="html-viewer">
            <div class="html-viewer-toolbar">
                <button class=${!showSource ? 'active' : ''} onClick=${() => setShowSource(false)}>Preview</button>
                <button class=${showSource ? 'active' : ''} onClick=${() => setShowSource(true)}>Source</button>
            </div>
            ${showSource
                ? html`<div class="code-viewer"><pre><code ref=${codeRef} class="language-html">${text}</code></pre></div>`
                : html`<iframe class="html-preview-frame" src=${contentUrl} sandbox=""></iframe>`
            }
        </div>
    `;
}

const GRAPHVIZ_ENGINES = ['dot', 'circo', 'fdp', 'neato', 'osage', 'patchwork', 'twopi'];
const GRAPHVIZ_WASM_OPTS = { wasmFolder: 'https://cdn.jsdelivr.net/npm/@hpcc-js/wasm@1.16.6/dist' };
const DIRECTIONS = ['bidirectional', 'downstream', 'upstream', 'single'];
const DIRECTION_LABELS = { bidirectional: 'Bidirectional', downstream: 'Downstream', upstream: 'Upstream', single: 'Single' };

function getAffectedElements(graphvizSvg, selectedElements, direction) {
    const result = new Set(selectedElements);
    for (const el of selectedElements) {
        // Only traverse from nodes
        if (!el.classList.contains('node')) continue;
        if (direction === 'single') continue;
        if (direction === 'downstream' || direction === 'bidirectional') {
            for (const r of graphvizSvg.linkedFrom(el, true)) result.add(r);
        }
        if (direction === 'upstream' || direction === 'bidirectional') {
            for (const r of graphvizSvg.linkedTo(el, true)) result.add(r);
        }
    }
    return result;
}

function GraphvizViewer({ text, path, onSave }) {
    const [activeTab, setActiveTab] = useState('graph');
    const [engine, setEngine] = useState('dot');
    const [darkCanvas, setDarkCanvas] = useState(
        () => window.matchMedia('(prefers-color-scheme: dark)').matches
    );
    const [error, setError] = useState(null);
    const [rendering, setRendering] = useState(false);
    const [direction, setDirection] = useState('bidirectional');
    const [searchQuery, setSearchQuery] = useState('');
    const [searchCount, setSearchCount] = useState(null);

    // Edit tab state
    const [editText, setEditText] = useState(text);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [previewSvg, setPreviewSvg] = useState('');
    const [previewError, setPreviewError] = useState(null);

    const containerRef = useRef(null);
    const codeRef = useRef(null);
    const editorRef = useRef(null);
    const highlightRef = useRef(null);
    const cursorRef = useRef(null);
    const editInitRef = useRef(false);
    const graphvizSvgRef = useRef(new GraphvizSvg());
    const rendererRef = useRef(null);
    const selectionRef = useRef(new Set());

    // Sync editText when text prop changes from outside (new file or post-save)
    useEffect(() => {
        setEditText(text);
        setDirty(false);
    }, [text]);

    // Restore cursor position after Tab key insertion
    useEffect(() => {
        if (cursorRef.current !== null && editorRef.current) {
            editorRef.current.selectionStart = cursorRef.current;
            editorRef.current.selectionEnd = cursorRef.current;
            cursorRef.current = null;
        }
    });

    // Render DOT → SVG via d3-graphviz whenever text or engine changes
    useEffect(() => {
        if (!containerRef.current || !text) return;
        let cancelled = false;
        setError(null);
        setRendering(true);

        // Clear previous selection state
        selectionRef.current = new Set();
        setSearchQuery('');
        setSearchCount(null);

        try {
            const container = containerRef.current;
            if (!rendererRef.current) {
                container.innerHTML = '';
            }

            const renderer = d3Graphviz(container)
                .engine(engine)
                .fade(true)
                .zoom(true)
                .zoomScaleExtent([0.1, Infinity])
                .tweenShapes(false)
                .convertEqualSidedPolygons(false)
                .transition(() => d3.transition().duration(500))
                .on('end', () => {
                    if (cancelled) return;
                    setRendering(false);
                    graphvizSvgRef.current.setup(container);
                })
                .onerror((err) => {
                    if (cancelled) return;
                    setError(typeof err === 'string' ? err : (err.message || String(err)));
                    setRendering(false);
                });

            rendererRef.current = renderer;
            renderer.renderDot(text);
        } catch (e) {
            if (!cancelled) {
                setError(e.message || String(e));
                setRendering(false);
            }
        }

        return () => {
            cancelled = true;
            rendererRef.current = null;
        };
    }, [text, engine]);

    // Highlight source when switching to source tab
    useEffect(() => {
        if (activeTab === 'source' && codeRef.current) {
            codeRef.current.textContent = text;
            hljs.highlightElement(codeRef.current);
        }
    }, [activeTab, text]);

    // Sync editor syntax highlight overlay
    useEffect(() => {
        if (activeTab === 'edit' && highlightRef.current) {
            // Set text + trailing newline so the overlay height matches the textarea
            highlightRef.current.textContent = editText + '\n';
            hljs.highlightElement(highlightRef.current);
        }
    }, [activeTab, editText]);

    // Live preview for Edit tab (immediate on tab switch, debounced on edits)
    useEffect(() => {
        if (activeTab !== 'edit') {
            editInitRef.current = false;
            return;
        }
        if (!editText?.trim()) {
            setPreviewSvg('');
            setPreviewError(null);
            return;
        }

        let cancelled = false;
        const doRender = () => {
            if (cancelled) return;
            hpccGraphviz.layout(editText, 'svg', engine, GRAPHVIZ_WASM_OPTS)
                .then(svg => {
                    if (!cancelled) { setPreviewSvg(svg); setPreviewError(null); }
                })
                .catch(e => {
                    if (!cancelled) { setPreviewError(e.message || String(e)); setPreviewSvg(''); }
                });
        };

        // Render immediately on first open / tab switch; debounce subsequent edits
        if (!editInitRef.current) {
            editInitRef.current = true;
            doRender();
            return () => { cancelled = true; };
        }

        const timer = setTimeout(doRender, 800);
        return () => { cancelled = true; clearTimeout(timer); };
    }, [editText, engine, activeTab]);

    // Click interaction: event delegation on container
    useEffect(() => {
        const container = containerRef.current;
        if (!container || activeTab !== 'graph') return;

        const handleClick = (e) => {
            const gsvg = graphvizSvgRef.current;
            const node = e.target.closest('.node');
            const edge = e.target.closest('.edge');
            const cluster = e.target.closest('.cluster');
            const clickedEl = node || edge || cluster;

            if (!clickedEl) {
                selectionRef.current = new Set();
                gsvg.highlight(null);
                return;
            }

            const isMulti = e.ctrlKey || e.metaKey || e.shiftKey;
            const sel = selectionRef.current;

            if (isMulti) {
                if (sel.has(clickedEl)) {
                    sel.delete(clickedEl);
                } else {
                    sel.add(clickedEl);
                }
            } else {
                sel.clear();
                sel.add(clickedEl);
            }

            if (sel.size === 0) {
                gsvg.highlight(null);
            } else {
                const dir = cluster && !node ? 'single' : direction;
                const affected = getAffectedElements(gsvg, sel, dir);
                for (const s of sel) affected.add(s);
                gsvg.highlight(affected);
            }
        };

        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                selectionRef.current = new Set();
                graphvizSvgRef.current.highlight(null);
            }
        };

        container.addEventListener('click', handleClick);
        document.addEventListener('keydown', handleKeyDown);
        return () => {
            container.removeEventListener('click', handleClick);
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [activeTab, direction]);

    // Search: update match count as user types
    const handleSearchInput = useCallback((e) => {
        const q = e.target.value;
        setSearchQuery(q);
        if (!q) {
            setSearchCount(null);
            return;
        }
        const gsvg = graphvizSvgRef.current;
        const nodes = gsvg.findNodes(q);
        const edges = gsvg.findEdges(q);
        const clusters = gsvg.findClusters(q);
        setSearchCount(nodes.length + edges.length + clusters.length);
    }, []);

    // Search: commit on Enter
    const handleSearchKeyDown = useCallback((e) => {
        if (e.key !== 'Enter') return;
        const q = searchQuery;
        if (!q) {
            graphvizSvgRef.current.highlight(null);
            selectionRef.current = new Set();
            return;
        }
        const gsvg = graphvizSvgRef.current;
        const found = [
            ...gsvg.findNodes(q),
            ...gsvg.findEdges(q),
            ...gsvg.findClusters(q),
        ];
        if (found.length > 0) {
            const affected = getAffectedElements(gsvg, found, direction);
            for (const f of found) affected.add(f);
            gsvg.highlight(affected);
            selectionRef.current = new Set(found);
        } else {
            gsvg.highlight(null);
            selectionRef.current = new Set();
        }
    }, [searchQuery, direction]);

    const handleExportSvg = useCallback(() => {
        if (!containerRef.current) return;
        const svg = containerRef.current.querySelector('svg');
        if (!svg) return;
        const serializer = new XMLSerializer();
        const svgStr = '<?xml version="1.0" encoding="UTF-8"?>\n' + serializer.serializeToString(svg);
        const blob = new Blob([svgStr], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = (path.split('/').pop() || 'graph').replace(/\.(dot|gv)$/i, '') + '.svg';
        a.click();
        URL.revokeObjectURL(url);
    }, [path]);

    // Save handler (stable reference via ref pattern to avoid circular deps)
    const saveRef = useRef(null);
    saveRef.current = async () => {
        if (!dirty || saving) return;
        setSaving(true);
        try {
            await api.put('/api/files/content', { path, content: editText });
            setDirty(false);
            if (onSave) onSave(editText);
        } catch (e) {
            // error toast handled by api client
        } finally {
            setSaving(false);
        }
    };
    const handleSave = useCallback(() => saveRef.current?.(), []);

    // Editor input handler
    const handleEditorInput = useCallback((e) => {
        const val = e.target.value;
        setEditText(val);
        setDirty(val !== text);
    }, [text]);

    // Editor keydown handler (Tab inserts spaces, Ctrl+S / Cmd+S saves)
    const handleEditorKeyDown = useCallback((e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            saveRef.current?.();
            return;
        }
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = e.target.selectionStart;
            const end = e.target.selectionEnd;
            setEditText(prev => prev.substring(0, start) + '    ' + prev.substring(end));
            setDirty(true);
            cursorRef.current = start + 4;
        }
    }, []);

    return html`
        <div class="graphviz-viewer">
            <div class="graphviz-toolbar">
                <div class="graphviz-tabs">
                    <button class=${activeTab === 'graph' ? 'active' : ''} onClick=${() => setActiveTab('graph')}>Graph</button>
                    <button class=${activeTab === 'source' ? 'active' : ''} onClick=${() => setActiveTab('source')}>Source</button>
                    <button class=${activeTab === 'edit' ? 'active' : ''} onClick=${() => setActiveTab('edit')}>
                        Edit${dirty ? html` <span class="graphviz-dirty-indicator"></span>` : ''}
                    </button>
                </div>
                ${activeTab === 'graph' && html`
                    <select class="graphviz-engine-select"
                            value=${engine}
                            onChange=${(e) => setEngine(e.target.value)}
                            title="Layout engine">
                        ${GRAPHVIZ_ENGINES.map(eng => html`<option value=${eng}>${eng}</option>`)}
                    </select>
                    <select class="graphviz-direction-select"
                            value=${direction}
                            onChange=${(e) => setDirection(e.target.value)}
                            title="Traversal direction">
                        ${DIRECTIONS.map(d => html`<option value=${d}>${DIRECTION_LABELS[d]}</option>`)}
                    </select>
                    <div class="graphviz-search-wrap">
                        <input class="graphviz-search-input"
                               type="text"
                               placeholder="Search nodes…"
                               value=${searchQuery}
                               onInput=${handleSearchInput}
                               onKeyDown=${handleSearchKeyDown} />
                        ${searchCount !== null && html`
                            <span class="graphviz-search-count">${searchCount}</span>
                        `}
                    </div>
                    <button class="graphviz-export-btn" onClick=${handleExportSvg} title="Export SVG">
                        <i class="ph ph-download-simple"></i> SVG
                    </button>
                    <button class=${'graphviz-theme-btn' + (darkCanvas ? ' active' : '')}
                            onClick=${() => setDarkCanvas(d => !d)}
                            title=${darkCanvas ? 'Light background' : 'Dark background'}>
                        <i class=${'ph ' + (darkCanvas ? 'ph-sun' : 'ph-moon')}></i>
                    </button>
                `}
                ${activeTab === 'edit' && html`
                    <select class="graphviz-engine-select"
                            value=${engine}
                            onChange=${(e) => setEngine(e.target.value)}
                            title="Layout engine">
                        ${GRAPHVIZ_ENGINES.map(eng => html`<option value=${eng}>${eng}</option>`)}
                    </select>
                    <button class=${'graphviz-save-btn' + (dirty ? ' dirty' : '')}
                            onClick=${handleSave}
                            disabled=${!dirty || saving}>
                        <i class="ph ${saving ? 'ph-circle-notch' : dirty ? 'ph-floppy-disk' : 'ph-check'}"></i>
                        ${' '}${saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
                    </button>
                    <span class="graphviz-save-hint"><kbd>${navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}</kbd>+<kbd>S</kbd></span>
                `}
            </div>
            ${error && activeTab === 'graph' && html`
                <div class="graphviz-error">
                    <i class="ph ph-warning-circle"></i>
                    <span>${error}</span>
                </div>
            `}
            <div class=${'graphviz-canvas' + (darkCanvas ? ' graphviz-dark' : '')}
                 ref=${containerRef}
                 style=${{ display: activeTab === 'graph' ? '' : 'none' }}>
                ${rendering && html`<div class="graphviz-loading">Rendering…</div>`}
            </div>
            ${activeTab === 'edit' && html`
                <div class="graphviz-edit-pane">
                    <div class="graphviz-editor-wrap">
                        <pre class="graphviz-editor-highlight" aria-hidden="true"><code ref=${highlightRef} class="language-dot">${editText + '\n'}</code></pre>
                        <textarea class="graphviz-editor"
                                  ref=${editorRef}
                                  value=${editText}
                                  onInput=${handleEditorInput}
                                  onKeyDown=${handleEditorKeyDown}
                                  onScroll=${(e) => {
                                      if (highlightRef.current?.parentElement) {
                                          highlightRef.current.parentElement.scrollTop = e.target.scrollTop;
                                          highlightRef.current.parentElement.scrollLeft = e.target.scrollLeft;
                                      }
                                  }}
                                  spellcheck="false"
                                  placeholder="Enter DOT source…"></textarea>
                    </div>
                    <div class="graphviz-preview">
                        ${previewError
                            ? html`<div class="graphviz-preview-error">
                                <i class="ph ph-warning-circle"></i>
                                <span>${previewError}</span>
                              </div>`
                            : html`<div dangerouslySetInnerHTML=${{ __html: previewSvg }}></div>`
                        }
                    </div>
                </div>
            `}
            ${activeTab === 'source' && html`
                <div class="code-viewer"><pre><code ref=${codeRef} class="language-dot">${text}</code></pre></div>
            `}
        </div>
    `;
}

// Animated wrapper — remounts (via key) on each new filePath to retrigger animation
function AnimatedContent({ filePath, children }) {
    return html`
        <div key=${filePath} class="preview-content-animate">
            ${children}
        </div>
    `;
}

export function PreviewPane({ filePath }) {
    const [content, setContent] = useState(null);
    const [loading, setLoading] = useState(false);
    // Track previous filePath to detect actual changes
    const prevPath = useRef(null);

    useEffect(() => {
        if (!filePath) {
            setContent(null);
            prevPath.current = null;
            return;
        }

        // Fade out then load new content
        prevPath.current = filePath;
        const type = getFileType(filePath);
        setLoading(true);
        setContent(null);

        if (['text', 'code', 'markdown', 'html', 'graphviz'].includes(type)) {
            api.get(`/api/files/content?path=${encodeURIComponent(filePath)}`)
                .then((text) => { if (prevPath.current === filePath) setContent({ type, text }); })
                .catch(() => { if (prevPath.current === filePath) setContent(null); })
                .finally(() => { if (prevPath.current === filePath) setLoading(false); });
        } else {
            api.get(`/api/files/info?path=${encodeURIComponent(filePath)}`)
                .then((info) => { if (prevPath.current === filePath) setContent({ type, info }); })
                .catch(() => { if (prevPath.current === filePath) setContent(null); })
                .finally(() => { if (prevPath.current === filePath) setLoading(false); });
        }
    }, [filePath]);

    // Callback for GraphvizViewer to update content after saving edits
    const handleGraphvizSave = useCallback((newText) => {
        setContent(prev => prev ? { ...prev, text: newText } : prev);
    }, []);

    if (!filePath) return html`<div class="preview-empty">Select a file to preview</div>`;

    if (loading) return html`
        <div class="preview-loading preview-loading-fade">Loading…</div>
    `;

    if (!content) return html`<div class="preview-empty">Unable to load file</div>`;

    const contentUrl  = `/api/files/content?path=${encodeURIComponent(filePath)}`;
    const downloadUrl = `/api/files/download?path=${encodeURIComponent(filePath)}`;

    let inner;
    switch (content.type) {
        case 'text':
            inner = html`<${TextViewer} text=${content.text} />`;
            break;
        case 'code':
            inner = html`<${CodeViewer} text=${content.text} path=${filePath} />`;
            break;
        case 'markdown':
            inner = html`<${MarkdownViewer} text=${content.text} />`;
            break;
        case 'html':
            inner = html`<${HtmlViewer} text=${content.text} path=${filePath} contentUrl=${contentUrl} />`;
            break;
        case 'graphviz':
            inner = html`<${GraphvizViewer} text=${content.text} path=${filePath} onSave=${handleGraphvizSave} />`;
            break;
        case 'image':
            inner = html`<${ImageViewer} contentUrl=${contentUrl} filePath=${filePath} />`;
            break;
        case 'audio':
            inner = html`<div class="preview-audio"><audio controls src=${contentUrl}></audio></div>`;
            break;
        case 'video':
            inner = html`<div class="preview-video"><video controls src=${contentUrl}></video></div>`;
            break;
        case 'pdf':
            inner = html`<div class="preview-pdf"><iframe src=${contentUrl}></iframe></div>`;
            break;
        default:
            inner = html`
                <div class="preview-other">
                    <h3>${filePath.split('/').pop()}</h3>
                    ${content.info && html`<p>Size: ${formatSize(content.info.size)}</p>`}
                    ${content.info && html`<p>Modified: ${content.info.modified}</p>`}
                    <a href=${downloadUrl} class="download-btn">Download</a>
                </div>
            `;
    }

    // AnimatedContent uses filePath as key — forces remount + animation on every file switch
    return html`
        <${FileInfoBar} filePath=${filePath} />
        <${AnimatedContent} filePath=${filePath}>${inner}</${AnimatedContent}>
    `;
}
