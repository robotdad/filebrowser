---
id: markdown-image-rewriter
title: Markdown Image Source Rewriter
red_signal: AC-1: UNMET
criteria_digest: 9a80d3e4a62075edb7eea200295dfd8b58dead2ad6954e1db0ac7198beab92f4
base_sha: aa9e640e5bfc7712f417bd3266d4032692c9de2e
later_commit: 312a636b3d849ba9c394a3f96a265494ba5ef13a
target_repo: robotdad/filebrowser
verify: DEFINITION.verify.sh
---

## Goal

Provide a dependency-free, Node-testable helper module in `static/js/lib/` that rewrites relative Markdown image sources to authenticated `/api/files/content` URLs, given the current file's path. The helper resolves relative paths (including parent directory segments like `../`) to repo-relative paths and encodes them for use in the file-content API query parameter.

## Why this matters

Markdown files referencing images with relative paths currently show broken images in the View tab because the raw relative `src` attribute cannot resolve against the SPA origin. The file-content API (`/api/files/content?path=<encoded-path>`) is the only authenticated way to fetch file bytes, so relative image sources must be rewritten to this API format. This helper provides the path-resolution and URL-construction logic needed to fix image rendering in the markdown viewer.

## Definition of done

### AC-1: Helper exports relative image rewrite
**Probe:** Import the helper module from `static/js/lib/` in a Node.js environment (no bundler, no DOM). Call the exported function with a current file path and various relative image sources. Verify it returns `/api/files/content?path=<url-encoded resolved repo-relative path>`.

**Test approach:**
- Auto-discover exported function by testing behavior with both parameter orders: `(currentFile, imageSource)` and `(imageSource, currentFile)` - the gate tests which order produces correct output, not which signature is "right"
- Load 23 pre-computed test cases from vendored oracle file `test-oracle.json`
- Execute criteria examples: `docs/page.md` + `img/x.png`, `docs/page.md` + `./img/x.png`
- Execute real repo paths: `README.md` + `assets/branding/icons/filebrowser-icon-128.png`
- Execute diverse non-criteria cases: nested subdirectories, special characters in filenames, root-level files
- Execute runtime-generated test with semantically-neutral random identifiers
- Verify URL encoding correctness: `/` → `%2F`, space → `%20`
- Verify output format matches established pattern from `static/js/components/preview.js:922`

**Verified:** The helper module exists in `static/js/lib/`, exports a function that correctly resolves relative paths and constructs API URLs for diverse inputs including criteria examples, real repo paths, and runtime-generated cases.

### AC-2: Absolute/non-file sources pass through unchanged
**Probe:** Call the helper with absolute and non-file URL sources. Verify each returns byte-for-byte identical to the input (no rewriting).

**Test approach:**
- Load pre-computed test cases from vendored oracle file including all four criteria-specified URL types
- Execute criteria examples: `http://`, `https://`, `//` protocol-relative, `data:` URIs
- Execute diverse non-criteria cases: URLs with query parameters and fragments, URLs with ports, long data URIs
- Execute runtime-generated absolute URL with semantically-neutral random domain/path
- Verify negative-space: absolute URLs unaffected by current file path (same URL with different files produces identical output)
- Verify protocol-relative URLs not treated as relative paths
- Verify long data URIs not truncated or modified

**Verified:** The helper correctly identifies absolute URLs (http://, https://, //) and data URIs, returning them byte-for-byte unchanged regardless of current file path.

### AC-3: Parent segments resolve with no ".." left in output
**Probe:** Call the helper with relative paths containing `..` parent directory segments. Verify the output path has all `..` segments resolved and the final path contains no `..`.

**Test approach:**
- Load pre-computed test cases from vendored oracle file
- Execute criteria example: `docs/page.md` + `../assets/y.png`
- Execute diverse non-criteria cases: multiple parent segments (`../../`), mixed relative (`./../`), parent-then-child navigation (`../d/e.png`), complex interleaved segments (`../s/../t/u.png`)
- Execute runtime-generated test with semantically-neutral random identifiers at depth N with N-1 `..` segments
- Verify output contains no `..` characters (string search for literal `..`)
- Verify normalization correctness against expected resolved paths

**Verified:** The helper normalizes paths to remove all `..` segments, producing clean repo-relative paths with no `..` characters remaining in the output.

### AC-4 [guard]: Existing module and tests keep passing unchanged
**Probe:** Verify `static/js/lib/preprocess-markdown.js` content is byte-identical to base SHA. Run `tests/test_markdown_preprocess.py` and verify the same pass/fail pattern as base SHA (34 pass, 3 fail).

**Test approach:**
- Compare `preprocess-markdown.js` file hash against base SHA version
- Run `uv run pytest tests/test_markdown_preprocess.py -v --tb=no`
- Verify exactly 34 tests pass and exactly 3 tests fail
- Verify the 3 failing tests are the same ones that fail at base SHA:
  - `test_empty_frontmatter_block`
  - `test_nested_brackets_are_not_matched`
  - `test_wikilink_with_pipe_in_display_text`

**Verified:** The existing pure module and its test suite remain unchanged and exhibit the same behavior as at base SHA.

## Non-goals

**Scope OUT (from acceptance criteria):**
- **Browser integration:** Wiring the helper into the live View render path and browser-level confirmation are tracked separately in `tests/reality-check` (deferred: requires DOM and CDN imports for marked+DOMPurify)
- **Edit tab bug:** The Tiptap Edit→Source image-stripping bug (#28) is a separate issue (deferred: different component, different root cause)
- **API changes:** No changes to the `/api/files/content` endpoint itself (out of scope: API is stable and working)

**Delegated freedoms:**
- **Module name:** The helper can have any filename in `static/js/lib/` as long as it's importable under Node
- **Function name:** The exported function can have any name
- **Function signature:** The function can use any parameter order `(currentFile, imageSource)` or `(imageSource, currentFile)`, and can accept additional optional parameters - the gate tests both orders to discover which works
- **Internal implementation:** Path resolution can use any algorithm (built-in Node.js path module, manual string manipulation, etc.) as long as the output matches the specified format
- **Error handling:** How the helper handles edge cases like paths that escape the repo root is implementation-defined (no criteria specify this behavior)
