import { useState, useEffect, useRef, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { getFileCategory, formatSize, formatDate } from '../file-utils.js';
import { EditableViewer } from './editable-viewer.js';
import { MarkdownEditor } from './markdown-editor.js';
import { CodeEditor } from './code-editor.js';
import { EditBar } from './edit-bar.js';
import { undo, redo } from '@codemirror/commands';
import { wasmFolder, graphviz as hpccGraphviz } from '@hpcc-js/wasm';
import * as d3 from 'd3';
import { graphviz as d3Graphviz } from 'd3-graphviz';
import GraphvizSvg from '../graphviz-svg.js';

// Set WASM path before d3-graphviz tries to load it
wasmFolder('https://cdn.jsdelivr.net/npm/@hpcc-js/wasm@1.16.6/dist');

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

function HtmlViewer({ text, path, contentUrl, onSave }) {
    const [mode, setMode] = useState('preview'); // 'preview' | 'source' | 'edit'
    const [editText, setEditText] = useState(text);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [cursor, setCursor] = useState(null);
    const viewRef = useRef(null);

    const handleDocChange = useCallback((newDoc) => {
        setEditText(newDoc);
        setDirty(newDoc !== text);
    }, [text]);

    const handleSave = useCallback(async () => {
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
    }, [dirty, saving, path, editText, onSave]);

    const handleUndo = useCallback(() => { if (viewRef.current) undo(viewRef.current); }, []);
    const handleRedo = useCallback(() => { if (viewRef.current) redo(viewRef.current); }, []);

    const handleModeSwitch = useCallback((newMode) => {
        if (mode === 'edit' && newMode !== 'edit' && dirty) {
            if (!confirm('Discard unsaved changes?')) return;
            setEditText(text);
            setDirty(false);
        }
        setMode(newMode);
    }, [mode, dirty, text]);

    return html`
        <div class="html-viewer">
            <div class="html-viewer-toolbar">
                <button class=${mode === 'preview' ? 'active' : ''} onClick=${() => handleModeSwitch('preview')}>Preview</button>
                <button class=${mode === 'source' ? 'active' : ''} onClick=${() => handleModeSwitch('source')}>Source</button>
                <button class=${mode === 'edit' ? 'active' : ''} onClick=${() => handleModeSwitch('edit')}>
                    Edit${dirty ? html` <span class="dirty-dot"></span>` : ''}
                </button>
            </div>
            ${mode === 'edit' && html`
                <${EditBar} dirty=${dirty} saving=${saving} language="HTML"
                            cursor=${cursor} onSave=${handleSave}
                            onUndo=${handleUndo} onRedo=${handleRedo} />
            `}
            ${mode === 'preview'
                ? html`<iframe class="html-preview-frame" src=${contentUrl} sandbox=""></iframe>`
                : html`<${CodeEditor}
                    doc=${mode === 'edit' ? editText : text}
                    path=${path}
                    readOnly=${mode === 'source'}
                    onDocChange=${mode === 'edit' ? handleDocChange : null}
                    onCursorChange=${mode === 'edit' ? setCursor : null}
                    onSave=${mode === 'edit' ? handleSave : null}
                    viewRef=${viewRef}
                    key=${path + ':' + mode} />`
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
    const [cursor, setCursor] = useState(null);

    const containerRef = useRef(null);
    const editorViewRef = useRef(null);
    const editInitRef = useRef(false);
    const graphvizSvgRef = useRef(new GraphvizSvg());
    const rendererRef = useRef(null);
    const selectionRef = useRef(new Set());

    // Sync editText when text prop changes from outside (new file or post-save)
    useEffect(() => {
        setEditText(text);
        setDirty(false);
    }, [text]);

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

    // CM6 doc-change handler for edit tab
    const handleEditorDocChange = useCallback((newDoc) => {
        setEditText(newDoc);
        setDirty(newDoc !== text);
    }, [text]);

    const handleUndo = useCallback(() => { if (editorViewRef.current) undo(editorViewRef.current); }, []);
    const handleRedo = useCallback(() => { if (editorViewRef.current) redo(editorViewRef.current); }, []);

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
                    <div class="graphviz-edit-editor">
                        <${EditBar} dirty=${dirty} saving=${saving} language="DOT"
                                    cursor=${cursor} onSave=${handleSave}
                                    onUndo=${handleUndo} onRedo=${handleRedo} />
                        <${CodeEditor}
                            doc=${editText}
                            path=${path}
                            readOnly=${false}
                            onDocChange=${handleEditorDocChange}
                            onCursorChange=${setCursor}
                            onSave=${handleSave}
                            viewRef=${editorViewRef}
                            key=${path + ':edit'} />
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
                <${CodeEditor} doc=${text} path=${path} readOnly=${true} key=${path + ':source'} />
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
        const type = getFileCategory(filePath);
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

    // Callback to update content after saving edits (shared by all editable viewers)
    const handleContentSave = useCallback((newText) => {
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
        case 'code':
            inner = html`<${EditableViewer} text=${content.text} path=${filePath}
                                             onSave=${handleContentSave} />`;
            break;
        case 'markdown':
            inner = html`<${MarkdownEditor} text=${content.text} path=${filePath} onSave=${handleContentSave} />`;
            break;
        case 'html':
            inner = html`<${HtmlViewer} text=${content.text} path=${filePath} contentUrl=${contentUrl} onSave=${handleContentSave} />`;
            break;
        case 'graphviz':
            inner = html`<${GraphvizViewer} text=${content.text} path=${filePath} onSave=${handleContentSave} />`;
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
