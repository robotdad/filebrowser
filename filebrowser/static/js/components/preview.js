import { useState, useEffect, useRef, useMemo } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import hljs from 'highlight.js';
import { marked } from 'marked';

const FILE_TYPES = {
    text:     ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
    code:     ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.css'],
    html:     ['.html', '.htm'],
    markdown: ['.md'],
    image:    ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'],
    audio:    ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'],
    video:    ['.mp4', '.webm', '.mkv', '.mov', '.avi'],
    pdf:      ['.pdf'],
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
    const htmlContent = useMemo(() => marked.parse(text), [text]);
    return html`<div class="markdown-viewer" dangerouslySetInnerHTML=${{ __html: htmlContent }}></div>`;
}

function ImageViewer({ contentUrl, filePath }) {
    const [zoom, setZoom] = useState(1);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const isDragging = useRef(false);
    const dragStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 });
    const canvasRef = useRef(null);

    const clampZoom = (z) => Math.min(Math.max(z, 0.1), 20);

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

    const reset = () => { setZoom(1); setOffset({ x: 0, y: 0 }); };

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
                <button onClick=${reset} title="Reset zoom">
                    <i class="ph ph-arrows-in"></i> Reset
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
                    src=${contentUrl}
                    alt=${filePath}
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
                : html`<iframe class="html-preview-frame" src=${contentUrl}></iframe>`
            }
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

        if (['text', 'code', 'markdown', 'html'].includes(type)) {
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
