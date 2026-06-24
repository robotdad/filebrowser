# FileBrowser Fixtures

Welcome to the test fixture directory. These files exercise every supported file type,
editor, and viewer in the FileBrowser app. Open any file to preview it; switch between
the **View**, **Edit**, and **Source** tabs to explore the different rendering paths.

## What's here

- **[markdown/](markdown/)** — Markdown files testing the three-tab editor (View = marked.js,
  Edit = Tiptap WYSIWYG, Source = CodeMirror). `showcase.md` deliberately exercises every
  Tiptap edge case including fenced code blocks, GFM tables, task lists, and images.
- **[code/](code/)** — One representative source file per CodeMirror language mode (Python,
  JavaScript, TypeScript, Go, Rust, SQL, CSS, Bash, Java, C++). Opens in the code editor
  with syntax highlighting.
- **[text/](text/)** — Non-code text formats: CSV, YAML, TOML, JSON, JSONL, plain text,
  log files, `.env`, nginx config, XML. Exercises the JSON/YAML highlighting and plain-text
  fallback paths.
- **[diagrams/](diagrams/)** — Graphviz `.dot` / `.gv` files rendered by d3-graphviz in the
  GraphvizViewer (Graph / Source / Edit tabs). Test engine switching and node interaction.
- **[web/](web/)** — SVG and HTML files. SVG goes through the ImageViewer; HTML is served
  under strict CSP/sandbox so the Preview tab shows raw source (a known limitation).
- **images/** — Raster images: PNG, JPEG, GIF, WebP. Opens in the ImageViewer.
- **media/** — Audio (MP3, OGG) and video (MP4, WebM). Opens in the MediaViewer.
- **documents/** — Binary documents: PDF. Opens in the DocumentViewer (iframe embed).

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+K` | Open command palette |
| Ctrl+\` | Toggle terminal panel |
| `Escape` | Close palette or modal |
| `Ctrl+S` | Save file in editor |
| `Ctrl+click` | Multi-select files in directory listing |

> **Tip:** Start with `markdown/showcase.md` to exercise the full editor surface, then open
> `diagrams/architecture.dot` to test the Graphviz viewer. Use the keyboard shortcuts above
> to navigate without the mouse.
