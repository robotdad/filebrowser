/**
 * GraphvizSvg — Vanilla ES6 port of jquery.graphviz.svg.js (MIT, mountainstorm)
 *
 * Parses rendered Graphviz SVG, indexes nodes/edges/clusters,
 * provides traversal (linkedFrom, linkedTo) and highlight/dim support.
 */

// Named color → hex lookup (common SVG/Graphviz colors)
const NAMED_COLORS = {
    black: '#000000', white: '#ffffff', red: '#ff0000', green: '#008000',
    blue: '#0000ff', yellow: '#ffff00', cyan: '#00ffff', magenta: '#ff00ff',
    orange: '#ffa500', purple: '#800080', pink: '#ffc0cb', gray: '#808080',
    grey: '#808080', lightgray: '#d3d3d3', lightgrey: '#d3d3d3',
    darkgray: '#a9a9a9', darkgrey: '#a9a9a9', brown: '#a52a2a',
    lime: '#00ff00', navy: '#000080', teal: '#008080', olive: '#808000',
    maroon: '#800000', aqua: '#00ffff', silver: '#c0c0c0', fuchsia: '#ff00ff',
    crimson: '#dc143c', coral: '#ff7f50', gold: '#ffd700', indigo: '#4b0082',
    ivory: '#fffff0', khaki: '#f0e68c', lavender: '#e6e6fa', salmon: '#fa8072',
    sienna: '#a0522d', tan: '#d2b48c', tomato: '#ff6347', turquoise: '#40e0d0',
    violet: '#ee82ee', wheat: '#f5deb3', transparent: null, none: null,
};

/**
 * Parse a CSS color string to {r,g,b} (0-255) or null if unparseable/none.
 */
function parseColor(str) {
    if (!str || str === 'none' || str === 'transparent') return null;

    // hex: #rgb, #rrggbb
    if (str.startsWith('#')) {
        let hex = str.slice(1);
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        if (hex.length === 6) {
            return {
                r: parseInt(hex.slice(0,2), 16),
                g: parseInt(hex.slice(2,4), 16),
                b: parseInt(hex.slice(4,6), 16),
            };
        }
    }

    // rgb(r,g,b)
    const rgbMatch = str.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i);
    if (rgbMatch) {
        return { r: +rgbMatch[1], g: +rgbMatch[2], b: +rgbMatch[3] };
    }

    // named color
    const lower = str.toLowerCase().trim();
    if (lower in NAMED_COLORS) {
        const mapped = NAMED_COLORS[lower];
        return mapped ? parseColor(mapped) : null;
    }

    return null;
}

/**
 * Convert {r,g,b} back to #rrggbb hex string.
 */
function toHex(rgb) {
    const h = (n) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, '0');
    return `#${h(rgb.r)}${h(rgb.g)}${h(rgb.b)}`;
}

/**
 * Linearly interpolate between two colors.  t=0 → colorA, t=1 → colorB.
 * Returns hex string, or colorA unchanged if either is unparseable.
 */
export function lerpColor(colorA, colorB, t) {
    const a = parseColor(colorA);
    const b = parseColor(colorB);
    if (!a || !b) return colorA;
    return toHex({
        r: a.r + (b.r - a.r) * t,
        g: a.g + (b.g - a.g) * t,
        b: a.b + (b.b - a.b) * t,
    });
}

/** WeakMap to store original fill/stroke per shape element */
const originalColors = new WeakMap();

function saveColor(el) {
    if (!originalColors.has(el)) {
        originalColors.set(el, {
            fill: el.getAttribute('fill'),
            stroke: el.getAttribute('stroke'),
        });
    }
}

function getOriginalColor(el) {
    return originalColors.get(el) || { fill: el.getAttribute('fill'), stroke: el.getAttribute('stroke') };
}

export default class GraphvizSvg {
    constructor() {
        this._svg = null;
        this._graph = null;
        this._background = null;
        this._nodes = [];
        this._edges = [];
        this._clusters = [];
        this._nodesByName = {};
        this._edgesByName = {};
        this._clustersByName = {};
        this._bgColor = '#ffffff';
    }

    /**
     * Parse and index the SVG inside containerEl.
     * Call this after every render (d3-graphviz "end" event).
     */
    setup(containerEl) {
        const svg = containerEl.querySelector('svg');
        if (!svg) return;
        this._svg = svg;

        // Root <g> is the first <g> child of <svg>
        this._graph = svg.querySelector(':scope > g');
        if (!this._graph) return;

        // Background polygon (may not exist)
        this._background = this._graph.querySelector(':scope > polygon');
        if (this._background) {
            const fill = this._background.getAttribute('fill');
            if (fill && fill !== 'none') this._bgColor = fill;
        }

        // Collect nodes, edges, clusters
        this._nodes = [...this._graph.querySelectorAll(':scope > .node')];
        this._edges = [...this._graph.querySelectorAll(':scope > .edge')];
        this._clusters = [...this._graph.querySelectorAll(':scope > .cluster')];

        // Reset indices
        this._nodesByName = {};
        this._edgesByName = {};
        this._clustersByName = {};

        // Index each category
        for (const el of this._nodes) this._indexElement(el, 'node');
        for (const el of this._edges) this._indexElement(el, 'edge');
        for (const el of this._clusters) this._indexElement(el, 'cluster');
    }

    _indexElement(el, type) {
        // Save colors on shapes
        for (const shape of el.querySelectorAll('polygon, ellipse, path, text')) {
            saveColor(shape);
        }

        // Extract name from <title> child
        const titleEl = el.querySelector(':scope > title');
        if (!titleEl) return;

        // Strip compass-point port suffixes for edge matching
        const name = titleEl.textContent.replace(/:[snew][ew]?/g, '');
        el.setAttribute('data-name', name);

        if (type === 'node') {
            this._nodesByName[name] = el;
        } else if (type === 'edge') {
            if (!this._edgesByName[name]) this._edgesByName[name] = [];
            this._edgesByName[name].push(el);
        } else if (type === 'cluster') {
            this._clustersByName[name] = el;
        }
    }

    // ── Accessors ──────────────────────────────────────────────

    nodes()          { return this._nodes; }
    edges()          { return this._edges; }
    clusters()       { return this._clusters; }
    nodesByName()    { return this._nodesByName; }
    edgesByName()    { return this._edgesByName; }
    clustersByName() { return this._clustersByName; }
    bgColor()        { return this._bgColor; }

    // ── Traversal ──────────────────────────────────────────────

    /**
     * Downstream traversal: follow arrows forward from `nodeEl`.
     * Returns Set<Element> of reachable nodes (and optionally edges).
     */
    linkedFrom(nodeEl, includeEdges = true) {
        const result = new Set();
        this._findLinked(nodeEl, includeEdges, (nodeName, edgeName) => {
            const parts = edgeName.split('->');
            if (parts.length > 1 &&
                (parts[0] === nodeName || parts[0].startsWith(nodeName + ':'))) {
                return parts[1].split(':')[0];
            }
            return null;
        }, result);
        return result;
    }

    /**
     * Upstream traversal: follow arrows backward to `nodeEl`.
     * Returns Set<Element> of reachable nodes (and optionally edges).
     */
    linkedTo(nodeEl, includeEdges = true) {
        const result = new Set();
        this._findLinked(nodeEl, includeEdges, (nodeName, edgeName) => {
            const parts = edgeName.split('->');
            if (parts.length > 1 &&
                (parts[1] === nodeName || parts[1].startsWith(nodeName + ':'))) {
                return parts[0].split(':')[0];
            }
            return null;
        }, result);
        return result;
    }

    _findLinked(nodeEl, includeEdges, testEdge, result) {
        const nodeName = nodeEl.getAttribute('data-name');
        if (!nodeName) return;

        for (const edgeName of Object.keys(this._edgesByName)) {
            const matched = testEdge(nodeName, edgeName);
            if (matched) {
                if (includeEdges) {
                    for (const e of this._edgesByName[edgeName]) result.add(e);
                }
                const targetNode = this._nodesByName[matched];
                if (targetNode && !result.has(targetNode)) {
                    result.add(targetNode);
                    this._findLinked(targetNode, includeEdges, testEdge, result);
                }
            }
        }
    }

    // ── Highlight / Dim ────────────────────────────────────────

    /**
     * Highlight a set of elements. Everything NOT in the set is dimmed
     * (colors blended 90% toward the background color).
     * Pass null/undefined/empty to restore all elements.
     */
    highlight(elements) {
        const all = [...this._nodes, ...this._edges, ...this._clusters];
        const bg = this._bgColor;

        if (!elements || (elements instanceof Set && elements.size === 0) ||
            (Array.isArray(elements) && elements.length === 0)) {
            // Restore all
            for (const el of all) this._restoreElement(el);
            return;
        }

        const selectedSet = elements instanceof Set ? elements : new Set(elements);

        for (const el of all) {
            if (selectedSet.has(el)) {
                this._restoreElement(el);
            } else {
                this._dimElement(el, bg);
            }
        }
    }

    _dimElement(el, bg) {
        for (const shape of el.querySelectorAll('polygon, ellipse, path, text')) {
            const orig = getOriginalColor(shape);
            if (orig.fill && orig.fill !== 'none') {
                shape.setAttribute('fill', lerpColor(orig.fill, bg, 0.9));
            }
            if (orig.stroke && orig.stroke !== 'none') {
                shape.setAttribute('stroke', lerpColor(orig.stroke, bg, 0.9));
            }
        }
    }

    _restoreElement(el) {
        for (const shape of el.querySelectorAll('polygon, ellipse, path, text')) {
            const orig = getOriginalColor(shape);
            if (orig.fill && orig.fill !== 'none') {
                shape.setAttribute('fill', orig.fill);
            }
            if (orig.stroke && orig.stroke !== 'none') {
                shape.setAttribute('stroke', orig.stroke);
            }
        }
    }

    // ── Search helpers ─────────────────────────────────────────

    /**
     * Search nodes by name key and textContent.
     * matchFn(text, query) → boolean (default: case-insensitive substring)
     */
    findNodes(query, matchFn) {
        const fn = matchFn || ((text, q) => text.toLowerCase().includes(q.toLowerCase()));
        const results = [];
        for (const [name, el] of Object.entries(this._nodesByName)) {
            const text = el.textContent || '';
            if (fn(name, query) || fn(text, query)) results.push(el);
        }
        return results;
    }

    /**
     * Search edges by textContent (label).
     */
    findEdges(query, matchFn) {
        const fn = matchFn || ((text, q) => text.toLowerCase().includes(q.toLowerCase()));
        const results = [];
        for (const edgeEls of Object.values(this._edgesByName)) {
            for (const el of edgeEls) {
                const text = el.textContent || '';
                if (fn(text, query)) results.push(el);
            }
        }
        return results;
    }

    /**
     * Search clusters by name and textContent.
     */
    findClusters(query, matchFn) {
        const fn = matchFn || ((text, q) => text.toLowerCase().includes(q.toLowerCase()));
        const results = [];
        for (const [name, el] of Object.entries(this._clustersByName)) {
            const text = el.textContent || '';
            if (fn(name, query) || fn(text, query)) results.push(el);
        }
        return results;
    }
}
