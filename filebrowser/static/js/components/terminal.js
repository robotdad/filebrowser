import { useEffect, useRef, useCallback } from 'preact/hooks';
import { html } from '../html.js';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';

export function TerminalPanel({ cwd, onClose, dockPosition, onToggleDock }) {
    const containerRef = useRef(null);
    const fitRef       = useRef(null);
    const fitFrameRef  = useRef(null);

    const scheduleFit = useCallback(() => {
        if (fitFrameRef.current !== null) return;

        fitFrameRef.current = requestAnimationFrame(() => {
            fitFrameRef.current = null;
            const fitAddon = fitRef.current;
            if (!fitAddon) return;
            fitAddon.fit();
        });
    }, []);

    // ── Main effect: create terminal + WebSocket, wired to cwd ─────────────────
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        // Create Terminal instance
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', monospace",
            theme: {
                background: '#1c1c1e',
                foreground: '#f5f5f7',
                cursor:     '#f5f5f7',
                // ANSI 16-color palette
                black:         '#1c1c1e',
                red:           '#ff453a',
                green:         '#32d74b',
                yellow:        '#ffd60a',
                blue:          '#0a84ff',
                magenta:       '#bf5af2',
                cyan:          '#5ac8fa',
                white:         '#ebebf5',
                brightBlack:   '#636366',
                brightRed:     '#ff6961',
                brightGreen:   '#30d158',
                brightYellow:  '#ffd426',
                brightBlue:    '#409cff',
                brightMagenta: '#da8fff',
                brightCyan:    '#70d7ff',
                brightWhite:   '#ffffff',
            },
        });

        // Load FitAddon
        const fitAddon = new FitAddon();
        fitRef.current = fitAddon;
        term.loadAddon(fitAddon);

        // Open terminal into the container div
        term.open(container);

        // Fit after the browser has laid out the container
        scheduleFit();

        // ── WebSocket ───────────────────────────────────────────────────────────
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url      = `${protocol}//${location.host}/api/terminal?path=${encodeURIComponent(cwd || '')}`;
        const ws       = new WebSocket(url);
        ws.binaryType  = 'arraybuffer';

        ws.onopen = () => {
            // Send initial resize so the PTY matches the visible terminal
            ws.send(JSON.stringify({
                type: 'resize',
                cols: term.cols,
                rows: term.rows,
            }));
        };

        ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                term.write(new Uint8Array(event.data));
            } else {
                term.write(event.data);
            }
        };

        ws.onclose = () => {
            term.write('\r\n\x1b[90m[Terminal session ended]\x1b[0m\r\n');
        };

        ws.onerror = () => {
            term.write('\r\n\x1b[31m[Connection error]\x1b[0m\r\n');
        };

        // ── Terminal → WebSocket ───────────────────────────────────────────────
        const dataDisposable = term.onData((data) => {
            if (ws.readyState === WebSocket.OPEN) ws.send(data);
        });

        const resizeDisposable = term.onResize(({ cols, rows }) => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'resize', cols, rows }));
            }
        });

        // ── Resize handling ─────────────────────────────────────────────────────
        const observer = new ResizeObserver(() => scheduleFit());
        observer.observe(container);

        // ── Cleanup ─────────────────────────────────────────────────────────────
        return () => {
            observer.disconnect();
            if (fitFrameRef.current !== null) {
                cancelAnimationFrame(fitFrameRef.current);
                fitFrameRef.current = null;
            }
            dataDisposable.dispose();
            resizeDisposable.dispose();
            // Null out callbacks before closing so ws.onclose / ws.onerror cannot
            // fire after cleanup — avoids writing "[Terminal session ended]" to an
            // already-disposed terminal instance (teardown race on cwd changes).
            ws.onopen    = null;
            ws.onmessage = null;
            ws.onclose   = null;
            ws.onerror   = null;
            ws.close();
            term.dispose();
        };
    }, [cwd, scheduleFit]);

    // ── Render ─────────────────────────────────────────────────────────────────
    return html`
        <div class="terminal-panel">
            <div class="terminal-header">
                <span class="terminal-header-title terminal-title">
                    <i class="ph ph-terminal-window"></i>
                    Terminal
                </span>
                <button
                    class="terminal-action-btn terminal-dock-toggle"
                    onClick=${onToggleDock}
                    title=${dockPosition === 'bottom' ? 'Dock to side' : 'Dock to bottom'}
                >
                    <i class=${dockPosition === 'bottom' ? 'ph ph-columns' : 'ph ph-rows'}></i>
                </button>
                <button
                    class="terminal-action-btn terminal-close"
                    onClick=${onClose}
                    title="Close terminal"
                >
                    <i class="ph ph-x"></i>
                </button>
            </div>
            <div class="terminal-container">
                <div class="terminal-xterm-wrapper" ref=${containerRef}></div>
            </div>
        </div>
    `;
}
