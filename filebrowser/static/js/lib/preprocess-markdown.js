// Pure markdown preprocessor: strip YAML frontmatter and transform Obsidian wikilinks.
//
// Frontmatter: YAML blocks delimited by --- at the very start of the file are extracted
// and returned separately. Mid-document --- (thematic breaks) are preserved. Only a
// frontmatter block starting at offset 0 is treated as metadata.
//
// Wikilinks: Obsidian-style [[target]] and [[target|display]] links are transformed to
// standard markdown [display](target.md) format so marked.js can render them as links.
//
// Extracted from components/markdown-editor.js so it can be unit-tested without a DOM.

/**
 * Strip YAML frontmatter from the beginning of markdown text.
 * 
 * Frontmatter is recognized ONLY when it starts at the very first character (offset 0)
 * and is delimited by --- lines. A --- appearing mid-document (thematic break) is NOT
 * treated as frontmatter and is preserved in the body.
 * 
 * @param {string} text - Raw markdown text
 * @returns {{frontmatter: string|null, body: string}} - Parsed frontmatter (if any) and remaining body
 */
export function stripFrontmatter(text) {
    // Match frontmatter ONLY at the start: ^--- followed by content, then closing ---
    // The [\s\S]*? is non-greedy so it stops at the first closing ---, not the last.
    const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
    if (!match) {
        return { frontmatter: null, body: text };
    }
    // Return the YAML content (without delimiters) and the text after the closing ---
    return {
        frontmatter: match[1],
        body: text.slice(match[0].length),
    };
}

/**
 * Transform Obsidian-style wikilinks to standard markdown links.
 * 
 * Converts:
 *   [[some-slug]] -> [some-slug](some-slug.md)
 *   [[some-slug|Display Text]] -> [Display Text](some-slug.md)
 * 
 * The target is assumed to be a sibling file, so we append .md to make it a relative link.
 * 
 * @param {string} text - Markdown text potentially containing wikilinks
 * @returns {string} - Text with wikilinks replaced by standard markdown links
 */
export function transformWikilinks(text) {
    return text
        // First handle [[target|display]] form (pipe-separated)
        // Capture group 1: target, group 2: display text
        .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '[$2]($1.md)')
        // Then handle [[target]] form (no pipe)
        // Use the target as both link text and href
        .replace(/\[\[([^\]]+)\]\]/g, '[$1]($1.md)');
}

/**
 * Render frontmatter as HTML for display in the markdown viewer.
 * 
 * Creates a collapsible details panel showing the YAML metadata. Uses <div> instead
 * of <details>/<summary> to avoid DOMPurify stripping issues.
 * 
 * @param {string} frontmatter - YAML frontmatter content (without --- delimiters)
 * @returns {string} - HTML for the frontmatter panel
 */
export function renderFrontmatter(frontmatter) {
    if (!frontmatter) return '';
    
    // Escape HTML in the YAML content to prevent XSS
    const escaped = frontmatter
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    
    // Return a styled div with the frontmatter content
    return `<div class="frontmatter-panel">
  <div class="frontmatter-header">Document Metadata</div>
  <pre class="frontmatter-content">${escaped}</pre>
</div>`;
}
