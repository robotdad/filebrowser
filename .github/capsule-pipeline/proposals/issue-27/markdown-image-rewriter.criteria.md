<!-- BINDING maintainer acceptance criteria -- extracted VERBATIM from the authenticated maintainer comment channel by criteria_gate. NO ONE in this run may edit this file: the pipeline holds no authority over maintainer text. -->
Source-comment-author: @robotdad
Source-comment-id: 5417367406
Source-comment-updated-at: 2026-08-25T21:57:53Z

## Acceptance criteria (feature-capsule)

Owned-by: @robotdad
Scope: IN -- a dependency-free, Node-testable helper in static/js/lib/ that rewrites relative Markdown image sources to the authenticated /api/files/content URL for a given current-file path. OUT -- wiring it into the live View render path and browser-level confirmation (tracked in tests/reality-check, since renderMarkdown pulls marked+DOMPurify from the CDN import map and needs a DOM); the Tiptap Edit->Source bug (#28); any change to /api/files/content.

AC-1: A helper exported from static/js/lib/ (importable under Node with no bundler and no DOM, exactly like preprocess-markdown.js) rewrites a relative image source, given the current file path, to /api/files/content?path=<url-encoded resolved repo-relative path>. Example: current file "docs/page.md", source "img/x.png" or "./img/x.png" -> "/api/files/content?path=docs%2Fimg%2Fx.png".
AC-2: Absolute / non-file sources pass through byte-for-byte unchanged: http://, https://, protocol-relative //host/..., and data: URLs are never rewritten.
AC-3: Parent segments resolve with no ".." left in the output: current file "docs/page.md", source "../assets/y.png" -> "/api/files/content?path=assets%2Fy.png".
AC-4 [guard]: The existing pure module static/js/lib/preprocess-markdown.js and its Node tests (tests/test_markdown_preprocess.py) keep passing unchanged.
