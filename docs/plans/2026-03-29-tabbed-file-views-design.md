# Tabbed File Views Design

## Goal

Add tab support for file preview views so users can pin files open for comparison — navigating to another folder without losing pinned views.

## Background

The filebrowser app currently tracks a single `selectedFile` string in `layout.js`. When a user clicks a file in the tree, the preview pane switches to that file, discarding the previous view. Users want to pin a file open and navigate elsewhere to compare materials side-by-side (or at least switch quickly between pinned files). This is tracked in issue `0f46929e`.

The existing `layout.js` already has 20 `useState` calls (26% of the 77 total across all components), making it the wrong place to add more state. A custom hook is the natural extraction point.

## Approach

**Chosen: Tab state in a `useTabManager` custom hook.**

This keeps tab logic self-contained and testable without further bloating `layout.js`. The hook owns the tab array, active tab tracking, dirty state, and all mutation functions. `PreviewPane` continues to receive a single `{ filePath }` prop — its interface is completely unchanged.

Drag-to-reorder is explicitly deferred to a future enhancement.

## Architecture

```
layout.js
  └── useTabManager() hook
        ├── tabs: Tab[]
        ├── activeTabId: string
        ├── activeFilePath: string (computed)
        ├── open(filePath)
        ├── pin(tabId)
        ├── close(tabId)
        ├── activate(tabId)
        ├── setDirty(tabId, boolean)
        ├── updatePath(oldPath, newPath)
        └── closeByPath(filePath)

<main class="preview">
  ├── <TabBar tabs={...} activeTabId={...} onActivate onPin onClose />
  └── <PreviewPane filePath={tabManager.activeFilePath} onDirtyChange={...} />
</main>
```

The tab bar lives inside the preview pane's grid area. It does not affect the `.main-content` grid that handles `.terminal-side` / `.terminal-bottom` layout. The terminal panel and the preview+tabs area are siblings in the grid, so there is no encroachment.

## Components

### `useTabManager` Hook

Manages an ordered array of tab objects and the active tab selection.

**Tab data model:**

```js
{ id: string, filePath: string, pinned: boolean }
```

**Behavior:**

- `tabs` — ordered array; pinned tabs always appear after the default (unpinned) tab
- `activeTabId` — which tab is currently displayed
- `activeFilePath` — computed from the active tab, fed directly to `PreviewPane`

**Default tab behavior:**

The default tab has no special type flag — it is simply the first unpinned tab in the array. When a file is clicked in the tree:

- If an unpinned tab exists, its `filePath` is replaced (it becomes the new default)
- If all tabs are pinned (or no tabs exist), a new unpinned tab is created at position 0

Pinning a tab sets `pinned: true` and keeps it in place. The unpinned "default" slot then becomes empty until the next file click creates a new one.

**Exposed API:**

| Function | Description |
|---|---|
| `open(filePath)` | Open a file in the default tab (or create one) |
| `pin(tabId)` | Pin a tab, converting it from default to permanent |
| `close(tabId)` | Close a tab (with dirty-state prompt if needed) |
| `activate(tabId)` | Switch the active tab |
| `setDirty(tabId, boolean)` | Mark a tab as having unsaved changes |
| `updatePath(oldPath, newPath)` | Update tab path after rename/move |
| `closeByPath(filePath)` | Close all tabs pointing to a deleted file |

### `TabBar` Component

Renders horizontally above the preview pane inside `<main class="preview">`.

**Props:** `tabs`, `activeTabId`, `onActivate`, `onPin`, `onClose`.

**Each tab renders:**

- **File name** (basename only, e.g. `config.py`) — clicking activates the tab
- **Pin icon** — shown on unpinned tabs as an outline; clicking calls `pin(tabId)`. Once pinned, the icon changes to a filled "pinned" indicator
- **Close X** — on all tabs (pinned and unpinned, right side); clicking calls `close(tabId)`, with an unsaved-changes prompt if dirty

**Tab ordering:** the unpinned default tab (if it exists) sits leftmost, pinned tabs to its right in the order they were pinned.

**CSS:** follows the existing `.markdown-editor-tabs` and `.graphviz-tabs` patterns — a flex row with `.active` state. Named `.file-tab-bar` to distinguish from in-editor tabs.

**Empty state:** when there are no tabs open, `TabBar` renders nothing, preserving the current empty preview pane behavior.

## Data Flow

### File Selection

```
User clicks file in tree
  → handleSelectFile(path)
    → tabManager.open(path)          // replaces setSelectedFile(path)
    → setSelectedFiles(...)          // batch selection unchanged
      → activeFilePath updates
        → PreviewPane re-renders with new filePath
```

### Dirty State

```
Editor detects change
  → calls onDirtyChange(true)
    → PreviewPane relays to tabManager.setDirty(activeTabId, true)
      → TabBar shows dirty indicator (follows .markdown-dirty-indicator pattern)

Editor saves
  → calls onDirtyChange(false)
    → dirty indicator clears
```

Editors already track their own dirty state internally. The new `onDirtyChange` callback prop on `PreviewPane` bridges that to the tab system.

### File Management Events

| Event | Tab Behavior |
|---|---|
| File renamed/moved | `updatePath(oldPath, newPath)` updates any matching tab's `filePath` — called by layout after a successful rename/move API response |
| File deleted | `closeByPath(filePath)` closes matching tabs automatically (no dirty prompt — file is gone) |
| Directory navigation | Default (unpinned) tab follows selection; pinned tabs stay put (paths are absolute) |

## Layout Integration

In `layout.js`, the `useTabManager` hook replaces the current `selectedFile` state for preview purposes. The hook's `activeFilePath` feeds into `PreviewPane` exactly where `selectedFile` does today. The existing `selectedFiles` Set (batch selection) stays independent.

```jsx
// layout.js — before
const [selectedFile, setSelectedFile] = useState(null);
// ...
<PreviewPane filePath={selectedFile} />

// layout.js — after
const tabManager = useTabManager();
// ...
<main class="preview">
    <TabBar
        tabs={tabManager.tabs}
        activeTabId={tabManager.activeTabId}
        onActivate={tabManager.activate}
        onPin={tabManager.pin}
        onClose={tabManager.close}
    />
    <PreviewPane
        filePath={tabManager.activeFilePath}
        onDirtyChange={(dirty) => tabManager.setDirty(tabManager.activeTabId, dirty)}
    />
</main>
```

### Terminal Coexistence

The tab bar lives inside the preview pane's grid area — it doesn't affect the `.main-content` grid that handles `.terminal-side` / `.terminal-bottom` layout. The terminal panel and the preview+tabs area are siblings in the grid, so no encroachment. CSS variables `--terminal-width` / `--terminal-height` continue to work unchanged.

## Error Handling

- **Close dirty tab:** unsaved-changes prompt appears. Choosing "don't save" closes the tab and discards dirty state. No auto-save, no recovery.
- **File deleted while tab open:** tab closes automatically without a dirty prompt (the file is gone).
- **Rename/move failure:** tab paths only update after a successful API response, so failed operations leave tabs unchanged.

## Testing Strategy

The project uses Python-based static analysis tests of JS source (no JS runtime tests). Testing will follow that existing pattern:

- Static analysis tests to verify `useTabManager` hook structure and exports
- Static analysis tests to verify `TabBar` component props and rendering structure
- Static analysis tests to verify `layout.js` integration (replacement of `selectedFile` with `tabManager.activeFilePath`)
- Verify CSS class naming follows conventions (`.file-tab-bar` distinct from `.markdown-editor-tabs` / `.graphviz-tabs`)

## Scope Boundaries

| Item | Status |
|---|---|
| Tab persistence across browser sessions (localStorage) | Deferred to future |
| Drag-to-reorder tabs | Deferred to future |
| Tab support for multiple terminal instances | Separate issue |
| Maximum tab count limit | Unlimited for now; scroll/overflow addressed if needed |

## Open Questions

- **Unsaved-changes prompt implementation:** native browser `confirm()` dialog vs. custom modal — to be decided during implementation.
- **Tab overflow behavior:** if many tabs are pinned, may need horizontal scroll or overflow menu — can address if it becomes a problem.
