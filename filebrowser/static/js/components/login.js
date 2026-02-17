import { useState } from 'preact/hooks';
import { html } from '../html.js';
import { api } from '../api.js';

export function LoginForm({ onLogin }) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const data = await api.post('/api/auth/login', { username, password });
            onLogin(data.username);
        } catch {
            setError('Invalid username or password');
        } finally {
            setLoading(false);
        }
    };

    return html`
        <div class="login-container">
            <form class="login-form" onSubmit=${handleSubmit}>
                <h1>File Browser</h1>
                ${error && html`<div class="error">${error}</div>`}
                <input
                    type="text"
                    placeholder="Username"
                    value=${username}
                    onInput=${(e) => setUsername(e.target.value)}
                    required
                    autocomplete="username"
                />
                <input
                    type="password"
                    placeholder="Password"
                    value=${password}
                    onInput=${(e) => setPassword(e.target.value)}
                    required
                    autocomplete="current-password"
                />
                <button type="submit" disabled=${loading}>
                    ${loading ? 'Signing in...' : 'Sign In'}
                </button>
            </form>
        </div>
    `;
}
