import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';
import { Breadcrumb } from './breadcrumb.js';
import { FileTree } from './tree.js';
import { PreviewPane } from './preview.js';
import { ActionBar } from './actions.js';

export function Layout({ username, onLogout }) {
    const [currentPath, setCurrentPath] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);
    const [showHidden, setShowHidden] = useState(false);

    const refresh = () => setRefreshKey((k) => k + 1);

    const handleLogout = async () => {
        await api.post('/api/auth/logout');
        onLogout();
    };

    const handleNavigate = (path) => {
        setCurrentPath(path);
        setSidebarOpen(false);
    };

    const handleSelectFile = (path) => {
        setSelectedFile(path);
        setSidebarOpen(false);
    };

    return html`
        <div class="layout">
            <header class="header">
                <button class="hamburger" onClick=${() => setSidebarOpen(!sidebarOpen)}>\u2630</button>
                <${Breadcrumb} path=${currentPath} onNavigate=${setCurrentPath} />
                <div class="header-right">
                    <label class="hidden-toggle">
                        <input type="checkbox" checked=${showHidden} onChange=${() => setShowHidden(!showHidden)} />
                        Show hidden
                    </label>
                    <span class="username">${username}</span>
                    <button class="logout-btn" onClick=${handleLogout}>Logout</button>
                </div>
            </header>
            <div class="main-content">
                <aside class="sidebar ${sidebarOpen ? 'open' : ''}">
                    <${FileTree}
                        currentPath=${currentPath}
                        onNavigate=${handleNavigate}
                        onSelectFile=${handleSelectFile}
                        refreshKey=${refreshKey}
                        showHidden=${showHidden}
                    />
                </aside>
                <div
                    class="sidebar-overlay ${sidebarOpen ? 'visible' : ''}"
                    onClick=${() => setSidebarOpen(false)}
                ></div>
                <main class="preview">
                    <${PreviewPane} filePath=${selectedFile} />
                </main>
            </div>
            <${ActionBar}
                currentPath=${currentPath}
                selectedFile=${selectedFile}
                onRefresh=${refresh}
            />
        </div>
    `;
}
