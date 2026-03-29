/**
 * logger.js — lightweight client-side logging with level gating.
 *
 * Usage:
 *   import { createLogger } from '../logger.js';
 *   const log = createLogger('MyComponent');
 *   log.debug('mount: path=%s', path);   // → console.debug('[MyComponent]', 'mount: path=%s', path)
 *   log.error('save failed', err);        // → console.error('[MyComponent]', 'save failed', err)
 *
 * Runtime level control from DevTools:
 *   window.__filebrowser_log_level('debug')   // enable all output
 *   window.__filebrowser_log_level('warn')    // back to default
 *   window.__filebrowser_log_level('silent')  // suppress everything
 */

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3, silent: 4 };

// Default to 'warn': debug/info are suppressed in production but warn/error always show.
let currentLevel = LEVELS.warn;

/**
 * Set the minimum log level. Messages below this level are silently dropped.
 * @param {'debug'|'info'|'warn'|'error'|'silent'} level
 */
export function setLevel(level) {
    const numeric = LEVELS[level];
    if (numeric === undefined) {
        console.warn('[logger] Unknown level:', level, '— valid values:', Object.keys(LEVELS).join(', '));
        return;
    }
    currentLevel = numeric;
}

/**
 * Create a logger bound to the given component/module name.
 * Each method prepends [name] and maps to the corresponding console.* method.
 * @param {string} name
 * @returns {{ debug: Function, info: Function, warn: Function, error: Function }}
 */
export function createLogger(name) {
    const prefix = `[${name}]`;
    return {
        debug(...args) { if (currentLevel <= LEVELS.debug) console.debug(prefix, ...args); },
        info(...args)  { if (currentLevel <= LEVELS.info)  console.info(prefix, ...args);  },
        warn(...args)  { if (currentLevel <= LEVELS.warn)  console.warn(prefix, ...args);  },
        error(...args) { if (currentLevel <= LEVELS.error) console.error(prefix, ...args); },
    };
}

// Expose setLevel globally so developers can adjust at runtime from DevTools:
//   window.__filebrowser_log_level('debug')
window.__filebrowser_log_level = setLevel;
