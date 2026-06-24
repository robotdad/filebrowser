# Markdown Editor Showcase

> **This file is for editor testing.** Open it in the three tabs to observe rendering differences:
> - **View** — rendered via marked.js (should display everything correctly)
> - **Edit** — Tiptap WYSIWYG (known to STRIP fenced code blocks, GFM tables, task lists, and images on round-trip)
> - **Source** — CodeMirror with live preview (raw Markdown; should be lossless)
>
> After opening in Edit and saving, switch back to View to observe what content was dropped.

---

## H2: Headings (H1 declared above; H4–H6 require typing — not on Tiptap toolbar)

### H3: Third-level heading

#### H4: Fourth-level heading (toolbar absent in Tiptap — type manually)

##### H5: Fifth-level heading (toolbar absent in Tiptap — type manually)

###### H6: Sixth-level heading (toolbar absent in Tiptap — type manually)

---

## Inline Marks

A sentence exercising every inline style: this word is **bold**, this one is *italic*, ~~this text is struck through~~, and `this is inline code`. You can combine them: ***bold italic*** and **bold with `code` inside**. The Tiptap toolbar covers bold, italic, and strikethrough but code-inside-bold is a known edge case.

---

## Fenced Code Blocks (STRIPPED by Tiptap on save)

Python — with language tag and a small class:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileNode:
    """Represents a node in the file tree."""

    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None

    def display(self) -> str:
        """Return a human-readable label."""
        suffix = "/" if self.is_dir else f" ({self.size} bytes)"
        return f"{self.name}{suffix}"


def walk(root: FileNode, depth: int = 0) -> None:
    indent = "  " * depth
    print(f"{indent}{root.display()}")
```

JavaScript — async function, arrow functions, template literals:

```javascript
class FileBrowserClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async listDir(path) {
    const url = `${this.baseUrl}/api/files${path}`;
    const resp = await fetch(url, { credentials: "include" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    return resp.json();
  }
}

const formatBytes = (n) =>
  n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB`
  : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB`
  : n >= 1e3 ? `${(n / 1e3).toFixed(1)} KB`
  : `${n} B`;
```

---

## GFM Table (STRIPPED by Tiptap on save)

| File Type | Extension(s) | Viewer Component | Editable? |
|---|---|---|---|
| Markdown | `.md` | `MarkdownViewer` | Yes (WYSIWYG + Source) |
| Code | `.py .js .ts .go .rs` | `CodeEditor` | Yes (CodeMirror) |
| Image | `.png .jpg .gif .webp` | `ImageViewer` | No |
| Diagram | `.dot .gv` | `GraphvizViewer` | Yes (Source + Edit) |
| Video | `.mp4 .webm` | `MediaViewer` | No |
| PDF | `.pdf` | `DocumentViewer` | No |

---

## Task List (STRIPPED by Tiptap on save)

Reality-check checklist for this fixture:

- [x] H1–H6 headings all render in View tab
- [x] Bold, italic, strikethrough, inline code visible in View
- [ ] Fenced code blocks survive Tiptap round-trip (expected: FAIL — verify data loss)
- [ ] GFM table survives Tiptap round-trip (expected: FAIL — verify data loss)
- [ ] Task list survives Tiptap round-trip (expected: FAIL — verify data loss)
- [ ] Image survives Tiptap round-trip (expected: FAIL — verify data loss)
- [x] Nested lists render correctly in View
- [x] Blockquote renders in View
- [x] Horizontal rule renders in View

---

## Image (STRIPPED by Tiptap on save)

The image below should appear in the **View** tab but disappear after a Tiptap **Edit → Save** cycle:

![Amplifier fixture image](https://placehold.co/600x200/png?text=Fixture+Image)

---

## Nested Lists

Unordered — 3 levels deep:

- Animals
  - Mammals
    - Dogs
    - Cats
  - Birds
    - Parrots
    - Eagles
- Plants
  - Trees
    - Oak
    - Maple
  - Shrubs

Mixed ordered + unordered nesting:

1. Install dependencies
   - Python ≥ 3.11
   - `pip install fastapi uvicorn`
2. Configure environment
   - Copy `.env.example` → `.env`
   - Set `SECRET_KEY`
3. Run the server
   1. Activate virtualenv
   2. Execute `uvicorn filebrowser.main:app --reload`
   3. Open `http://localhost:58080`

---

## Blockquote with Nested Formatting

> Software is **never** finished — it is only *released*.
> 
> A quote within the quote:
> > "Make it work, make it right, make it fast." — Kent Beck
> 
> And `inline code` inside a blockquote works too.

---

## Links

Inline link: [Example Domain](https://example.com)

Reference-style link: [reference link][1]

Auto-linked URL: <https://github.com/robotdad/filebrowser>

[1]: https://example.org "Example Org"

---

## Horizontal Rule

Content above the rule.

---

Content below the rule. The `---` on its own line produces a `<hr>` in View.

---

## Long Paragraph for Scroll and Wrap Testing

Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam. Eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.

---

## Unicode: Emoji, Accented Characters, and CJK

Emoji: 🎉 🚀 📁 🔍 ✅ ❌ 🌐

Accented characters: café, naïve, résumé, Über, jalapeño, crème brûlée

CJK test: 日本語テスト — 中文测试 — 한국어 테스트

Arabic (RTL): مرحبا بالعالم

Greek: Ελληνικά δοκιμή

Mixed: The café serves 抹茶 (matcha) and crème brûlée — all on one line.
