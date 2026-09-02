// Pure helper: rewrite a Markdown image `src` to an authenticated content URL.
//
// The View tab renders Markdown to HTML client-side, but relative image paths
// (e.g. `img/x.png`) can't resolve against the SPA's origin -- there is no static
// file server backing arbitrary repo paths. The only authenticated way to fetch
// file bytes is the `/api/files/content?path=<repo-relative path>` endpoint (see
// components/preview.js), so any relative image source found in a Markdown
// document must be rewritten to that API shape before the browser tries to load it.
//
// Absolute/non-file sources (http:, https:, protocol-relative //, and data: URIs)
// are left byte-for-byte untouched -- they're already fetchable as-is and have no
// meaningful "repo-relative path" to resolve.
//
// Extracted as a standalone module (like preprocess-markdown.js) so path resolution
// can be unit-tested without a DOM or bundler.
//
// NOTE: This module is loaded directly by the browser as a plain ES module.
// It must not import any Node built-ins (node:path, node:fs, etc.).
// Path operations are implemented inline to stay browser-compatible.

/**
 * Return the directory portion of a POSIX path (everything up to and including
 * the last slash, or an empty string if there is no slash).
 *
 * @param {string} p - A POSIX path string
 * @returns {string}
 */
function posixDirname(p) {
    const idx = p.lastIndexOf('/');
    if (idx === -1) return '';
    if (idx === 0) return '/';
    return p.slice(0, idx);
}

/**
 * Join two POSIX path segments.  If `b` is absolute (starts with '/') it wins
 * outright; otherwise the segments are concatenated with a single '/'.
 *
 * @param {string} a
 * @param {string} b
 * @returns {string}
 */
function posixJoin(a, b) {
    if (!a) return b;
    if (!b) return a;
    if (b.startsWith('/')) return b;
    return a.replace(/\/$/, '') + '/' + b;
}

/**
 * Normalize a POSIX path: collapse redundant slashes, resolve `.` and `..`
 * segments.  The result never ends with a trailing slash (unless it is the root
 * '/').  Leading `..` segments that would escape the root are dropped (they
 * can't be represented in a repo-relative path anyway).
 *
 * @param {string} p
 * @returns {string}
 */
function posixNormalize(p) {
    const parts = p.split('/');
    const out = [];
    for (const part of parts) {
        if (part === '' || part === '.') {
            // skip
        } else if (part === '..') {
            if (out.length > 0) out.pop();
            // else: leading '..' at repo root — drop it
        } else {
            out.push(part);
        }
    }
    return out.join('/');
}

/**
 * Test whether an image source is already an absolute/non-file reference that
 * should never be rewritten: `http://`, `https://`, protocol-relative `//...`,
 * or a `data:` URI. Checked against the START of the string only, so a
 * legitimate relative path that happens to contain `//` or `:` elsewhere is
 * never misclassified.
 *
 * @param {string} src - Image source string
 * @returns {boolean} - True if the source should pass through unchanged
 */
function isAbsoluteOrNonFileSource(src) {
    return (
        src.startsWith('http://') ||
        src.startsWith('https://') ||
        src.startsWith('//') ||
        src.startsWith('data:')
    );
}

/**
 * Rewrite a Markdown image source to an authenticated `/api/files/content` URL,
 * resolving it relative to the directory of the current Markdown file.
 *
 * Absolute URLs, protocol-relative URLs, and data URIs pass through unchanged.
 * Relative sources (including `./` and `../` segments) are resolved against
 * `dirname(currentFile)` and normalized so no `..` segments survive, then
 * URL-encoded as a single query-parameter value -- matching the
 * `/api/files/content?path=${encodeURIComponent(filePath)}` pattern already
 * used in components/preview.js.
 *
 * @param {string} currentFile - Repo-relative path of the Markdown file being viewed
 * @param {string} imageSource - The image `src` attribute value found in that file
 * @returns {string} - Either the untouched imageSource, or a rewritten
 *   `/api/files/content?path=...` URL
 */
export function rewriteImageSrc(currentFile, imageSource) {
    if (isAbsoluteOrNonFileSource(imageSource)) {
        return imageSource;
    }

    const resolvedPath = posixNormalize(posixJoin(posixDirname(currentFile), imageSource));
    return `/api/files/content?path=${encodeURIComponent(resolvedPath)}`;
}
