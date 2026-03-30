/**
 * use-tab-manager.js — Custom hook for managing editor tabs.
 *
 * Maintains a list of open file tabs with support for pinning, dirty-state
 * tracking, and neighbour activation on close.
 *
 * Tab model:
 *   { id: string, filePath: string, pinned: boolean, dirty: boolean }
 *
 * Usage:
 *   const { tabs, activeTabId, activeFilePath, open, pin, close,
 *           activate, setDirty, updatePath, closeByPath } = useTabManager();
 */

import { useState, useCallback } from 'preact/hooks';
import { createLogger } from '../logger.js';

const log = createLogger('useTabManager');

// ── ID generator ──────────────────────────────────────────────────────────────

let _counter = 0;

function genId() {
    _counter += 1;
    return `tab-${_counter}`;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTabManager() {
    const [tabs, setTabs] = useState([]);
    const [activeTabId, setActiveTabId] = useState(null);

    // Derive the active file path from the active tab
    const activeTab = tabs.find((t) => t.id === activeTabId) ?? null;
    const activeFilePath = activeTab ? activeTab.filePath : null;

    // ── open(filePath) ─────────────────────────────────────────────────────────
    // If there is an unpinned tab, replace it.  Otherwise create a new tab.
    const open = useCallback((filePath) => {
        log.debug('open:', filePath);
        setTabs((prev) => {
            // Find the first unpinned tab to replace
            const unpinnedIdx = prev.findIndex(({ pinned }) => !pinned);
            if (unpinnedIdx !== -1) {
                // Replace the unpinned tab in-place
                const updated = [...prev];
                updated[unpinnedIdx] = {
                    ...updated[unpinnedIdx],
                    filePath,
                    dirty: false,
                };
                setActiveTabId(updated[unpinnedIdx].id);
                return updated;
            }
            // All tabs are pinned (or no tabs exist) — create a new tab
            const newTab = { id: genId(), filePath, pinned: false, dirty: false };
            setActiveTabId(newTab.id);
            return [...prev, newTab];
        });
    }, []);

    // ── pin(tabId) ─────────────────────────────────────────────────────────────
    // Mark a tab as pinned and move it to the end of the pinned section.
    const pin = useCallback((tabId) => {
        log.debug('pin:', tabId);
        setTabs((prev) => {
            const tab = prev.find((t) => t.id === tabId);
            if (!tab) return prev;
            // Remove the tab and append it as pinned
            const rest = prev.filter((t) => t.id !== tabId);
            return [...rest, { ...tab, pinned: true }];
        });
    }, []);

    // ── close(tabId) ───────────────────────────────────────────────────────────
    // Close a tab.  Prompt via confirm() if the tab is dirty.
    // Activate a neighbour tab after closing.
    const close = useCallback((tabId) => {
        log.debug('close:', tabId);
        setTabs((prev) => {
            const idx = prev.findIndex((t) => t.id === tabId);
            if (idx === -1) return prev;
            const tab = prev[idx];
            // Guard: confirm before discarding unsaved changes
            if (tab.dirty) {
                const ok = confirm(`Discard unsaved changes to "${tab.filePath}"?`);
                if (!ok) return prev;
            }
            const next = prev.filter((t) => t.id !== tabId);
            // Activate a neighbour when the active tab is closed
            if (activeTabId === tabId) {
                const neighbourIdx = Math.min(idx, next.length - 1);
                const neighbour = next[neighbourIdx];
                setActiveTabId(neighbour ? neighbour.id : null);
            }
            return next;
        });
    }, [activeTabId]);

    // ── activate(tabId) ────────────────────────────────────────────────────────
    const activate = useCallback((tabId) => {
        log.debug('activate:', tabId);
        setActiveTabId(tabId);
    }, []);

    // ── setDirty(tabId, dirty) ─────────────────────────────────────────────────
    const setDirty = useCallback((tabId, dirty) => {
        log.debug('setDirty:', tabId, dirty);
        setTabs((prev) =>
            prev.map((t) => (t.id === tabId ? { ...t, dirty } : t))
        );
    }, []);

    // ── updatePath(oldPath, newPath) ───────────────────────────────────────────
    const updatePath = useCallback((oldPath, newPath) => {
        log.debug('updatePath:', oldPath, '->', newPath);
        setTabs((prev) =>
            prev.map((t) =>
                t.filePath === oldPath ? { ...t, filePath: newPath } : t
            )
        );
    }, []);

    // ── closeByPath(filePath) ──────────────────────────────────────────────────
    const closeByPath = useCallback((filePath) => {
        log.debug('closeByPath:', filePath);
        setTabs((prev) => {
            const tab = prev.find((t) => t.filePath === filePath);
            if (!tab) return prev;
            if (tab.dirty) {
                const ok = confirm(`Discard unsaved changes to "${filePath}"?`);
                if (!ok) return prev;
            }
            const next = prev.filter((t) => t.filePath !== filePath);
            if (activeTabId === tab.id) {
                const idx = prev.findIndex((t) => t.filePath === filePath);
                const neighbourIdx = Math.min(idx, next.length - 1);
                const neighbour = next[neighbourIdx];
                setActiveTabId(neighbour ? neighbour.id : null);
            }
            return next;
        });
    }, [activeTabId]);

    // ── Public API ─────────────────────────────────────────────────────────────
    return {
        tabs,
        activeTabId,
        activeFilePath,
        open,
        pin,
        close,
        activate,
        setDirty,
        updatePath,
        closeByPath,
    };
}
