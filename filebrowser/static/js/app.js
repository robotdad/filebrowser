import { render } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import { html } from './html.js';
import { api } from './api.js';
import { LoginForm } from './components/login.js';
import { Layout } from './components/layout.js';

function App() {
    const [user, setUser] = useState(null);
    const [authSource, setAuthSource] = useState(null);
    const [terminalEnabled, setTerminalEnabled] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get('/api/auth/me')
            .then((data) => {
                setUser(data.username);
                setAuthSource(data.auth_source);
                setTerminalEnabled(data.terminal_enabled ?? false);
            })
            .catch(() => setUser(null))
            .finally(() => setLoading(false));

        const handleLogout = () => setUser(null);
        window.addEventListener('auth:logout', handleLogout);
        return () => window.removeEventListener('auth:logout', handleLogout);
    }, []);

    if (loading) return html`<div class="loading">Loading...</div>`;
    if (!user) return html`<${LoginForm} onLogin=${(data) => {
        setUser(data.username);
        setTerminalEnabled(data.terminal_enabled ?? false);
    }} />`;
    return html`<${Layout} username=${user} authSource=${authSource} terminalEnabled=${terminalEnabled} onLogout=${() => setUser(null)} />`;
}

render(html`<${App} />`, document.getElementById('app'));
