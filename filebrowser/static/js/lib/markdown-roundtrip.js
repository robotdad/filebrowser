/**
 * Markdown serialization safety helpers.
 *
 * Rich-text serializers may normalize Markdown syntax they cannot represent.
 * The only tolerated difference is the complete trailing LF sequence: it is
 * restored from the source supplied when rich editing began.
 */

function splitTrailingLfs(markdown) {
    const text = typeof markdown === 'string' ? markdown : '';
    const match = text.match(/\n+$/);
    const suffix = match ? match[0] : '';
    return {
        body: suffix ? text.slice(0, -suffix.length) : text,
        suffix,
    };
}

/**
 * Return whether two Markdown strings are byte-for-byte equal apart from
 * their trailing LF sequences. Spaces, CR characters, and all other content
 * remain significant.
 */
export function matchesMarkdownIgnoringTrailingLfs(original, candidate) {
    return splitTrailingLfs(original).body === splitTrailingLfs(candidate).body;
}

/**
 * Replace a serializer's trailing LF sequence with the original source's
 * trailing LF sequence. This preserves the source's exact terminal suffix
 * without changing any other serializer output.
 */
export function restoreOriginalTrailingLfs(original, serialized) {
    const { body } = splitTrailingLfs(serialized);
    const { suffix } = splitTrailingLfs(original);
    return body + suffix;
}