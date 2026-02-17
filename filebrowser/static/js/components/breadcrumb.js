import { html } from '../html.js';

export function Breadcrumb({ path, onNavigate }) {
    const parts = path ? path.split('/') : [];

    return html`
        <nav class="breadcrumb">
            <span class="breadcrumb-item" onClick=${() => onNavigate('')}>Home</span>
            ${parts.map((part, i) => {
                const partPath = parts.slice(0, i + 1).join('/');
                return html`
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item" onClick=${() => onNavigate(partPath)}>
                        ${part}
                    </span>
                `;
            })}
        </nav>
    `;
}
