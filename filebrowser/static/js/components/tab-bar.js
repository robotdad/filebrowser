import { html } from '../html.js';
import { createLogger } from '../logger.js';

const log = createLogger('TabBar');

/**
 * TabBar — renders the horizontal row of open-file tabs.
 *
 * Props:
 *   tabs        {Array}    — array of tab objects { id, path, dirty, pinned }
 *   activeTabId {string}   — id of the currently active tab
 *   onActivate  {Function} — called with (tabId) when a tab is clicked
 *   onPin       {Function} — called with (tabId) when the pin button is clicked
 *   onClose     {Function} — called with (tabId) when the close button is clicked
 */
export function TabBar({ tabs, activeTabId, onActivate, onPin, onClose }) {
    if (!tabs || tabs.length === 0) {
        return null;
    }

    return html`
        <div class="file-tab-bar">
            ${tabs.map((tab) => {
                const basename = tab.path ? tab.path.split('/').pop() : tab.id;
                const isActive = tab.id === activeTabId;
                const tabClass = [
                    'file-tab',
                    isActive ? 'active' : '',
                    tab.pinned ? 'pinned' : '',
                ].filter(Boolean).join(' ');

                return html`
                    <div key=${tab.id} class=${tabClass} onClick=${() => {
                        log.debug('activate tab: %s', tab.id);
                        onActivate(tab.id);
                    }}>
                        <span class="file-tab-name">${basename}</span>
                        ${tab.dirty && html`<span class="file-tab-dirty">●</span>`}
                        <button class="file-tab-pin" title=${tab.pinned ? 'Unpin tab' : 'Pin tab'}
                            onClick=${(e) => { e.stopPropagation(); log.debug('pin tab: %s', tab.id); onPin(tab.id); }}>
                            <i class=${tab.pinned ? 'ph-push-pin' : 'ph-push-pin ph-push-pin-outline'}></i>
                        </button>
                        <button class="file-tab-close" title="Close tab"
                            onClick=${(e) => { e.stopPropagation(); onClose(tab.id); }}>
                            <i class="ph-x"></i>
                        </button>
                    </div>
                `;
            })}
        </div>
    `;
}
