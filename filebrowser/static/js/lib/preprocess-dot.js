// Pure DOT-source preprocessor: quote unquoted attribute keys that contain dots.
//
// Graphviz only allows unquoted IDs matching [a-zA-Z_][a-zA-Z0-9_]*, so namespaced
// keys (param.owner, context.route) must be quoted to parse. Tools commonly emit
// such keys, so we quote them before handing the source to the renderer.
//
// CRITICAL: we must NOT rewrite dotted text that appears inside quoted string
// VALUES (e.g. label="route a.b=c"). Doing so splits the string literal and
// produces invalid DOT. So we split the source on quoted strings first and only
// transform the unquoted segments.
//
// Extracted from components/preview.js so it can be unit-tested without a DOM.

// Unquoted dotted key (two or more dot-separated identifier segments) directly
// before an '=' assignment. No leading word char so we start at a token boundary.
const DOTTED_KEY = /(?<!\w)([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)(?=\s*=)/g;

// A double-quoted string, honoring backslash escapes (e.g. \").
const QUOTED_STRING = /("(?:[^"\\]|\\.)*")/g;

export function preprocessDot(src) {
    // split() with a capturing group keeps the delimiters: quoted strings land
    // on odd indices, unquoted segments on even indices.
    return src
        .split(QUOTED_STRING)
        .map((segment, i) =>
            i % 2 === 1 ? segment : segment.replace(DOTTED_KEY, '"$1"'),
        )
        .join("");
}
