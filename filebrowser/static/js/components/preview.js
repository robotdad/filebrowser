import { useState, useEffect, useRef, useMemo } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import hljs from 'highlight.js';
import { marked } from 'marked';

const FILE_TYPES = {
    text: ['.txt', '.log', '.csv', '.json', '.xml', '.yaml', '.yml', '.toml', '.env', '.conf'],
    code: ['.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.java', '.sh', '.sql', '.html', '.css'],
    markdown: ['.md'],
    image: ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'],
    audio: ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'],
    video: ['.mp4', '.webm', '.mkv', '.mov', '.avi'],
    pdf: ['.pdf'],
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

export function PreviewPane({ filePath }) {
    const [content, setContent] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!filePath) {
            setContent(null);
            return;
        }

        const type = getFileType(filePath);
        setLoading(true);

        if (['text', 'code', 'markdown'].includes(type)) {
            api.get(`/api/files/content?path=${encodeURIComponent(filePath)}`)
                .then((text) => setContent({ type, text }))
                .catch(() => setContent(null))
                .finally(() => setLoading(false));
        } else {
            api.get(`/api/files/info?path=${encodeURIComponent(filePath)}`)
                .then((info) => setContent({ type, info }))
                .catch(() => setContent(null))
                .finally(() => setLoading(false));
        }
    }, [filePath]);

    if (!filePath) return html`<div class="preview-empty">Select a file to preview</div>`;
    if (loading) return html`<div class="preview-loading">Loading...</div>`;
    if (!content) return html`<div class="preview-empty">Unable to load file</div>`;

    const contentUrl = `/api/files/content?path=${encodeURIComponent(filePath)}`;
    const downloadUrl = `/api/files/download?path=${encodeURIComponent(filePath)}`;

    switch (content.type) {
        case 'text':
            return html`<${TextViewer} text=${content.text} />`;
        case 'code':
            return html`<${CodeViewer} text=${content.text} path=${filePath} />`;
        case 'markdown':
            return html`<${MarkdownViewer} text=${content.text} />`;
        case 'image':
            return html`<div class="preview-image"><img src=${contentUrl} alt=${filePath} /></div>`;
        case 'audio':
            return html`<div class="preview-audio"><audio controls src=${contentUrl}></audio></div>`;
        case 'video':
            return html`<div class="preview-video"><video controls src=${contentUrl}></video></div>`;
        case 'pdf':
            return html`<div class="preview-pdf"><iframe src=${contentUrl}></iframe></div>`;
        default:
            return html`
                <div class="preview-other">
                    <h3>${filePath.split('/').pop()}</h3>
                    ${content.info && html`<p>Size: ${formatSize(content.info.size)}</p>`}
                    ${content.info && html`<p>Modified: ${content.info.modified}</p>`}
                    <a href=${downloadUrl} class="download-btn">Download</a>
                </div>
            `;
    }
}
