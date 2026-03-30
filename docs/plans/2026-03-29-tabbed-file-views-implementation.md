# Tabbed File Views Implementation Plan

> **Execution:** Use the subagent-driven-development workflow to implement this plan.

**Goal:** Add tab support for file preview views so users can pin files open and switch between them without losing context.
**Architecture:** A `useTabManager` custom hook manages the tab array and active tab selection, extracted from layout.js. A `TabBar` component renders horizontally above the preview pane inside `<main class="preview">`. PreviewPane's interface gains one new callback prop (`onDirtyChange`) but is otherwise unchanged — it still receives a single `filePath`.
**Tech Stack:** Preact + HTM (no build step, CDN imports), Python static-analysis tests (pytest), CSS design tokens

**Design document:** `docs/plans/2026-03-29-tabbed-file-views-design.md`

---

## Task 1: Create BROWSER_TESTING.md + Update DEV_GUIDE.md

**Files:**
- Create: `tests/BROWSER_TESTING.md`
- Modify: `DEV_GUIDE.md`

**Step 1: Create the browser testing guide**

Create `tests/BROWSER_TESTING.md` with the following content:

```markdown
# Browser Testing Guide

Browser-based behavioral testing for filebrowser using Amplifier's browser testing agents (playwright skill). These tests complement the Python static-analysis tests by verifying actual UI behavior through browser automation.

## When to Use Browser Tests

Use browser tests when you need to verify:
- UI flows that span multiple components (e.g., click file in tree -> preview renders)
- Visual state changes (e.g., active tab highlighting, dirty indicators)
- User interactions that trigger complex state updates (e.g., drag, resize, keyboard shortcuts)
- Regression after refactoring rendering logic

Browser tests are NOT a replacement for static-analysis tests. Use static-analysis tests for structural verification (exports, props, imports, class names). Use browser tests for behavioral verification (clicking a button does the right thing).

## How to Run Browser Tests

Browser tests are run by delegating to an Amplifier browser testing agent. The agent uses the playwright skill to automate a headless browser.

### Prerequisites

1. The filebrowser dev server must be running:
   ```bash
   cd filebrowser
   uv run uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
   ```

2. Load the playwright skill and delegate to a browser testing agent.

### Running a Test Scenario

Describe the scenario to the browser testing agent. Example:

> Navigate to http://localhost:58080. Log in if prompted. Click on a .py file in the file tree. Verify the preview pane shows syntax-highlighted code. Screenshot the result.

The agent will:
1. Launch a headless browser
2. Execute the steps
3. Return screenshots and pass/fail status

## The Baseline Pattern

For any feature that modifies UI behavior:

1. **Before changes:** Run key scenarios against the current codebase. Save screenshots as baseline artifacts.
2. **Implement changes.**
3. **After changes:** Run the same scenarios plus new feature-specific scenarios. Compare against baseline.

This catches visual regressions and ensures existing flows still work.

## Writing New Test Scenarios

A test scenario is a plain-English description of user actions and expected outcomes:

```
Scenario: File preview renders markdown
1. Navigate to http://localhost:58080
2. In the file tree, click on README.md
3. Verify the preview pane shows rendered markdown (not raw text)
4. Verify headings are rendered as <h1>, <h2>, etc.
5. Screenshot the result
```

Keep scenarios focused on one flow. Name them descriptively. Group related scenarios together when delegating to the browser agent.

## Relationship to Static-Analysis Tests

| Aspect | Static-Analysis Tests | Browser Tests |
|--------|----------------------|---------------|
| What they test | Code structure (imports, exports, props, class names) | UI behavior (clicks, renders, state changes) |
| How they run | `uv run pytest` — reads JS/CSS source as text | Amplifier browser agent — headless browser |
| Speed | Fast (milliseconds) | Slow (seconds per scenario) |
| When to use | Every PR, every change | Feature work, refactors, regression checks |
| Catches | Missing imports, wrong class names, dead props | Broken interactions, visual regressions, state bugs |
```

**Step 2: Update DEV_GUIDE.md with Testing section**

Open `DEV_GUIDE.md`. At the end of the file (after line 178), add the following section:

```markdown

## Testing

The project uses three complementary testing approaches:

### Python Backend Tests

Standard pytest tests for API routes, auth, filesystem operations, and path validation. Run with:

```bash
cd filebrowser
uv run pytest tests/ -v
```

### Python Static-Analysis Tests of JS/CSS Source

The primary frontend test approach. Python tests read JS and CSS source files as text and assert on patterns — verifying imports, exports, function signatures, class names, and structural contracts. No JS runtime is needed.

Example: `tests/test_layout_integration.py` reads `layout.js` and verifies that `TerminalPanel` is imported, rendered, and receives the correct props.

These tests run as part of the standard pytest suite.

### Browser-Based Behavioral Tests

UI behavioral verification using Amplifier's browser testing agents (playwright skill). Tests actual user flows — clicking, navigating, verifying rendered output. Used for feature work and regression checks.

See `tests/BROWSER_TESTING.md` for the full guide, including the baseline-before/verify-after pattern.
```

**Step 3: Verify files**

```bash
cd /home/robotdad/repos/files/filebrowser && cat tests/BROWSER_TESTING.md | head -5
cd /home/robotdad/repos/files/filebrowser && tail -10 DEV_GUIDE.md
```

Expected: First 5 lines of BROWSER_TESTING.md show the title. Last 10 lines of DEV_GUIDE.md show the new Testing section.

**Step 4: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add tests/BROWSER_TESTING.md DEV_GUIDE.md && git commit -m "docs: add browser testing guide and update dev guide with testing section"
```

---

## Task 2: Browser Baseline Capture

**Files:** None modified (screenshot artifacts only)

This task uses Amplifier's browser testing capability to capture current behavior before any code changes. The dev server must be running.

**Step 1: Start the dev server**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
```

Run this in the background. Wait for the "Uvicorn running" message.

**Step 2: Capture baseline using browser testing agent**

Delegate to a browser testing agent (load the `playwright` skill) with these scenarios:

1. Navigate to `http://localhost:58080`. Screenshot the initial state (file tree + empty preview).
2. Click on a `.py` file in the file tree. Screenshot showing code preview.
3. Click on a `.md` file. Screenshot showing markdown preview.
4. Open the terminal (Ctrl+` or the terminal button). Screenshot showing terminal coexisting with preview.
5. Close the terminal. Screenshot showing preview without terminal.

Save screenshots to `docs/plans/baseline/` for reference.

**Step 3: Note results**

Record which scenarios passed and any issues observed. This is the baseline against which post-change verification (Task 10) will compare.

No commit for this task — screenshots are working artifacts, not committed code.

---

## Task 3: useTabManager Hook

**Files:**
- Create: `filebrowser/static/js/hooks/use-tab-manager.js`
- Test: `tests/test_use_tab_manager.py`

**Step 1: Write the failing tests**

Create `tests/test_use_tab_manager.py`:

```python
"""Tests for the useTabManager custom hook (tabbed file views).

Verifies the structure and content of the hook file to ensure all tab
management state, mutations, and logging are correctly implemented.

Tests follow the static-analysis approach used throughout this project —
inspecting the JS source text rather than running a JS test framework.
"""

import re
from functools import lru_cache
from pathlib import Path

HOOK_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "hooks"
    / "use-tab-manager.js"
)


@lru_cache(maxsize=1)
def read_hook() -> str:
    return HOOK_FILE.read_text()


# ── TestFileExists ────────────────────────────────────────────────────


class TestFileExists:
    def test_hook_file_exists(self):
        """The use-tab-manager.js file must exist at the expected path."""
        assert HOOK_FILE.exists(), f"use-tab-manager.js not found at {HOOK_FILE}"


# ── TestImports ───────────────────────────────────────────────────────


class TestImports:
    def test_imports_use_state(self):
        """Must import useState from preact/hooks."""
        src = read_hook()
        assert "useState" in src, "useState not imported"

    def test_imports_use_callback(self):
        """Must import useCallback from preact/hooks."""
        src = read_hook()
        assert "useCallback" in src, "useCallback not imported"

    def test_imports_from_preact_hooks(self):
        """Hooks must be imported from 'preact/hooks'."""
        src = read_hook()
        assert "from 'preact/hooks'" in src or 'from "preact/hooks"' in src, (
            "preact/hooks import not found"
        )

    def test_imports_create_logger(self):
        """Must import createLogger from logger.js."""
        src = read_hook()
        assert "createLogger" in src, "createLogger not imported"
        assert "logger.js" in src, "logger.js import not found"


# ── TestExports ───────────────────────────────────────────────────────


class TestExports:
    def test_exports_use_tab_manager(self):
        """Hook must be exported as a named export."""
        src = read_hook()
        assert re.search(
            r"export\s+function\s+useTabManager", src
        ), "useTabManager is not exported as a named function"


# ── TestHookState ─────────────────────────────────────────────────────


class TestHookState:
    def test_has_tabs_state(self):
        """Must maintain a tabs array in state."""
        src = read_hook()
        assert "tabs" in src, "tabs state not found"
        assert re.search(r"useState\(\s*\{", src) or "tabs:" in src, (
            "tabs must be part of hook state"
        )

    def test_has_active_tab_id(self):
        """Must track activeTabId."""
        src = read_hook()
        assert "activeTabId" in src, "activeTabId not found in hook"

    def test_has_active_file_path(self):
        """Must compute activeFilePath from the active tab."""
        src = read_hook()
        assert "activeFilePath" in src, "activeFilePath not found in hook"


# ── TestHookAPI ───────────────────────────────────────────────────────


class TestHookAPI:
    def test_has_open_function(self):
        """Must expose an open(filePath) function."""
        src = read_hook()
        assert re.search(r"const\s+open\s*=\s*useCallback", src), (
            "open function not found as useCallback"
        )

    def test_has_pin_function(self):
        """Must expose a pin(tabId) function."""
        src = read_hook()
        assert re.search(r"const\s+pin\s*=\s*useCallback", src), (
            "pin function not found as useCallback"
        )

    def test_has_close_function(self):
        """Must expose a close(tabId) function."""
        src = read_hook()
        assert re.search(r"const\s+close\s*=\s*useCallback", src), (
            "close function not found as useCallback"
        )

    def test_has_activate_function(self):
        """Must expose an activate(tabId) function."""
        src = read_hook()
        assert re.search(r"const\s+activate\s*=\s*useCallback", src), (
            "activate function not found as useCallback"
        )

    def test_has_set_dirty_function(self):
        """Must expose a setDirty(tabId, boolean) function."""
        src = read_hook()
        assert re.search(r"const\s+setDirty\s*=\s*useCallback", src), (
            "setDirty function not found as useCallback"
        )

    def test_has_update_path_function(self):
        """Must expose an updatePath(oldPath, newPath) function."""
        src = read_hook()
        assert re.search(r"const\s+updatePath\s*=\s*useCallback", src), (
            "updatePath function not found as useCallback"
        )

    def test_has_close_by_path_function(self):
        """Must expose a closeByPath(filePath) function."""
        src = read_hook()
        assert re.search(r"const\s+closeByPath\s*=\s*useCallback", src), (
            "closeByPath function not found as useCallback"
        )

    def test_returns_all_api_members(self):
        """The return statement must include all API members."""
        src = read_hook()
        for member in ["tabs", "activeTabId", "activeFilePath", "open", "pin",
                        "close", "activate", "setDirty", "updatePath", "closeByPath"]:
            assert member in src, f"'{member}' not found in hook source"


# ── TestTabModel ──────────────────────────────────────────────────────


class TestTabModel:
    def test_tab_has_id_field(self):
        """Tab objects must have an id field."""
        src = read_hook()
        assert re.search(r"id\s*:", src), "id field not found in tab construction"

    def test_tab_has_file_path_field(self):
        """Tab objects must have a filePath field."""
        src = read_hook()
        assert "filePath" in src, "filePath field not found in tab construction"

    def test_tab_has_pinned_field(self):
        """Tab objects must have a pinned field."""
        src = read_hook()
        assert "pinned" in src, "pinned field not found in tab construction"

    def test_tab_has_dirty_field(self):
        """Tab objects must have a dirty field."""
        src = read_hook()
        assert "dirty" in src, "dirty field not found in tab construction"


# ── TestDirtyClose ────────────────────────────────────────────────────


class TestDirtyClose:
    def test_close_checks_dirty_state(self):
        """close() must check tab.dirty before closing."""
        src = read_hook()
        assert re.search(r"\.dirty", src), (
            "dirty state check not found in close logic"
        )

    def test_close_uses_confirm_for_dirty_tab(self):
        """close() must use confirm() dialog for dirty tabs."""
        src = read_hook()
        assert "confirm(" in src, (
            "confirm() dialog not found — dirty tabs must prompt before close"
        )


# ── TestDefaultTabBehavior ────────────────────────────────────────────


class TestDefaultTabBehavior:
    def test_open_finds_unpinned_tab(self):
        """open() must look for an existing unpinned tab to replace."""
        src = read_hook()
        assert re.search(r"!t\.pinned|pinned\s*===?\s*false", src), (
            "open() must check for unpinned tabs"
        )

    def test_open_creates_new_tab_when_all_pinned(self):
        """open() must create a new tab when all existing tabs are pinned."""
        src = read_hook()
        # Should have tab creation with id, filePath, pinned: false
        assert re.search(r"pinned\s*:\s*false", src), (
            "New tab creation with pinned: false not found"
        )


# ── TestLogging ───────────────────────────────────────────────────────


class TestLogging:
    def test_creates_named_logger(self):
        """Must create a logger named 'useTabManager'."""
        src = read_hook()
        assert re.search(r"createLogger\(\s*['\"]useTabManager['\"]\s*\)", src), (
            "createLogger('useTabManager') not found"
        )

    def test_logs_open_events(self):
        """open() must log at debug level."""
        src = read_hook()
        assert "log.debug" in src, "log.debug calls not found — hook must log key events"
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_use_tab_manager.py -v
```

Expected: ALL tests FAIL. The `TestFileExists` test fails with `"use-tab-manager.js not found"`. All other tests fail with `FileNotFoundError` since the hook file doesn't exist yet.

**Step 3: Create the hooks directory and implement the hook**

```bash
mkdir -p filebrowser/static/js/hooks
```

Create `filebrowser/static/js/hooks/use-tab-manager.js`:

```js
import { useState, useCallback } from 'preact/hooks';
import { createLogger } from '../logger.js';

const log = createLogger('useTabManager');

let _id = 0;
const genId = () => `tab-${++_id}`;

export function useTabManager() {
    const [state, setState] = useState({ tabs: [], activeTabId: null });

    const { tabs, activeTabId } = state;
    const activeFilePath = (tabs.find(t => t.id === activeTabId) || {}).filePath || null;

    const open = useCallback((filePath) => {
        log.debug('open: path=%s', filePath);
        setState(prev => {
            const unpinned = prev.tabs.find(t => !t.pinned);
            if (unpinned) {
                return {
                    tabs: prev.tabs.map(t =>
                        t.id === unpinned.id ? { ...t, filePath, dirty: false } : t
                    ),
                    activeTabId: unpinned.id,
                };
            }
            const id = genId();
            return {
                tabs: [{ id, filePath, pinned: false, dirty: false }, ...prev.tabs],
                activeTabId: id,
            };
        });
    }, []);

    const pin = useCallback((tabId) => {
        log.debug('pin: tabId=%s', tabId);
        setState(prev => {
            const tab = prev.tabs.find(t => t.id === tabId);
            if (!tab || tab.pinned) return prev;
            const without = prev.tabs.filter(t => t.id !== tabId);
            return {
                ...prev,
                tabs: [...without, { ...tab, pinned: true }],
            };
        });
    }, []);

    const close = useCallback((tabId) => {
        setState(prev => {
            const tab = prev.tabs.find(t => t.id === tabId);
            if (!tab) return prev;
            if (tab.dirty && !confirm(`Close "${tab.filePath.split('/').pop()}" with unsaved changes?`)) {
                return prev;
            }
            log.debug('close: tabId=%s path=%s', tabId, tab.filePath);
            const next = prev.tabs.filter(t => t.id !== tabId);
            let nextActiveId = prev.activeTabId;
            if (tabId === prev.activeTabId) {
                const closedIdx = prev.tabs.findIndex(t => t.id === tabId);
                const neighbor = next[Math.min(closedIdx, next.length - 1)];
                nextActiveId = neighbor ? neighbor.id : null;
            }
            return { tabs: next, activeTabId: nextActiveId };
        });
    }, []);

    const activate = useCallback((tabId) => {
        log.debug('activate: tabId=%s', tabId);
        setState(prev => ({ ...prev, activeTabId: tabId }));
    }, []);

    const setDirty = useCallback((tabId, dirty) => {
        log.debug('setDirty: tabId=%s dirty=%s', tabId, dirty);
        setState(prev => ({
            ...prev,
            tabs: prev.tabs.map(t =>
                t.id === tabId ? { ...t, dirty } : t
            ),
        }));
    }, []);

    const updatePath = useCallback((oldPath, newPath) => {
        log.debug('updatePath: old=%s new=%s', oldPath, newPath);
        setState(prev => ({
            ...prev,
            tabs: prev.tabs.map(t =>
                t.filePath === oldPath ? { ...t, filePath: newPath } : t
            ),
        }));
    }, []);

    const closeByPath = useCallback((filePath) => {
        log.debug('closeByPath: path=%s', filePath);
        setState(prev => {
            const next = prev.tabs.filter(t => t.filePath !== filePath);
            let nextActiveId = prev.activeTabId;
            const activeTab = prev.tabs.find(t => t.id === prev.activeTabId);
            if (activeTab && activeTab.filePath === filePath) {
                const neighbor = next[0];
                nextActiveId = neighbor ? neighbor.id : null;
            }
            return { tabs: next, activeTabId: nextActiveId };
        });
    }, []);

    return { tabs, activeTabId, activeFilePath, open, pin, close, activate, setDirty, updatePath, closeByPath };
}
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_use_tab_manager.py -v
```

Expected: ALL tests PASS (27 tests).

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/hooks/use-tab-manager.js tests/test_use_tab_manager.py && git commit -m "feat: add useTabManager hook with static-analysis tests"
```

---

## Task 4: TabBar Component

**Files:**
- Create: `filebrowser/static/js/components/tab-bar.js`
- Test: `tests/test_tab_bar.py`

**Step 1: Write the failing tests**

Create `tests/test_tab_bar.py`:

```python
"""Tests for the TabBar Preact component (tabbed file views).

Verifies the structure and content of the TabBar component file to ensure
correct props, rendering structure, and accessibility.

Tests follow the static-analysis approach used throughout this project —
inspecting the JS source text rather than running a JS test framework.
"""

import re
from functools import lru_cache
from pathlib import Path

COMPONENT_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "tab-bar.js"
)


@lru_cache(maxsize=1)
def read_component() -> str:
    return COMPONENT_FILE.read_text()


# ── TestFileExists ────────────────────────────────────────────────────


class TestFileExists:
    def test_tab_bar_file_exists(self):
        """The tab-bar.js file must exist at the expected path."""
        assert COMPONENT_FILE.exists(), f"tab-bar.js not found at {COMPONENT_FILE}"


# ── TestImports ───────────────────────────────────────────────────────


class TestImports:
    def test_imports_html_from_html_js(self):
        """Must import html from '../html.js'."""
        src = read_component()
        assert "../html.js" in src, "html.js import not found"

    def test_imports_create_logger(self):
        """Must import createLogger from logger.js."""
        src = read_component()
        assert "createLogger" in src, "createLogger not imported"
        assert "logger.js" in src, "logger.js import not found"


# ── TestExports ───────────────────────────────────────────────────────


class TestExports:
    def test_exports_tab_bar(self):
        """Component must export TabBar as a named export."""
        src = read_component()
        assert re.search(
            r"export\s+function\s+TabBar", src
        ), "TabBar is not exported as a named function"


# ── TestProps ─────────────────────────────────────────────────────────


class TestProps:
    def test_accepts_tabs_prop(self):
        """Component must accept a tabs prop."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*tabs[^}]*\}", src
        ), "tabs not found in TabBar function signature"

    def test_accepts_active_tab_id_prop(self):
        """Component must accept an activeTabId prop."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*activeTabId[^}]*\}", src
        ), "activeTabId not found in TabBar function signature"

    def test_accepts_on_activate_prop(self):
        """Component must accept an onActivate prop."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*onActivate[^}]*\}", src
        ), "onActivate not found in TabBar function signature"

    def test_accepts_on_pin_prop(self):
        """Component must accept an onPin prop."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*onPin[^}]*\}", src
        ), "onPin not found in TabBar function signature"

    def test_accepts_on_close_prop(self):
        """Component must accept an onClose prop."""
        src = read_component()
        assert re.search(
            r"function\s+TabBar\s*\(\s*\{[^}]*onClose[^}]*\}", src
        ), "onClose not found in TabBar function signature"


# ── TestRendering ─────────────────────────────────────────────────────


class TestRendering:
    def test_renders_file_tab_bar_container(self):
        """Must render a container with class 'file-tab-bar'."""
        src = read_component()
        assert "file-tab-bar" in src, "file-tab-bar class not found"

    def test_renders_file_name_as_basename(self):
        """Must display just the file name (basename), not the full path."""
        src = read_component()
        assert "split('/')" in src or 'split("/")' in src, (
            "split('/') not found — must extract basename from filePath"
        )
        assert ".pop()" in src, (
            ".pop() not found — must get last segment of path"
        )

    def test_renders_pin_icon(self):
        """Must render a pin icon element."""
        src = read_component()
        assert "push-pin" in src or "pin" in src.lower(), (
            "Pin icon not found in rendered output"
        )

    def test_renders_close_button(self):
        """Must render a close button for each tab."""
        src = read_component()
        assert "file-tab-close" in src, (
            "file-tab-close class not found — tabs must have close button"
        )

    def test_close_button_calls_on_close(self):
        """Close button must call onClose with tab id."""
        src = read_component()
        assert "onClose" in src, (
            "onClose not called in close button handler"
        )

    def test_pin_button_calls_on_pin(self):
        """Pin button must call onPin with tab id."""
        src = read_component()
        assert "onPin" in src, (
            "onPin not called in pin button handler"
        )


# ── TestActiveState ───────────────────────────────────────────────────


class TestActiveState:
    def test_has_active_class_for_active_tab(self):
        """Active tab must have 'active' CSS class."""
        src = read_component()
        assert "'active'" in src or '"active"' in src, (
            "active class not applied to active tab"
        )
        assert "activeTabId" in src, (
            "activeTabId not used for active state comparison"
        )


# ── TestDirtyIndicator ────────────────────────────────────────────────


class TestDirtyIndicator:
    def test_renders_dirty_indicator(self):
        """Must render a dirty indicator for dirty tabs."""
        src = read_component()
        assert "file-tab-dirty" in src, (
            "file-tab-dirty class not found — must show dirty indicator"
        )

    def test_dirty_indicator_is_conditional(self):
        """Dirty indicator must only render when tab is dirty."""
        src = read_component()
        assert re.search(r"\.dirty|tab\.dirty", src), (
            "dirty state check not found in rendering"
        )


# ── TestEmptyState ────────────────────────────────────────────────────


class TestEmptyState:
    def test_returns_null_when_no_tabs(self):
        """Must return null when tabs array is empty."""
        src = read_component()
        assert "return null" in src, (
            "return null not found — must render nothing when no tabs"
        )


# ── TestLogging ───────────────────────────────────────────────────────


class TestLogging:
    def test_creates_named_logger(self):
        """Must create a logger named 'TabBar'."""
        src = read_component()
        assert re.search(r"createLogger\(\s*['\"]TabBar['\"]\s*\)", src), (
            "createLogger('TabBar') not found"
        )
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_tab_bar.py -v
```

Expected: ALL tests FAIL with `"tab-bar.js not found"` or `FileNotFoundError`.

**Step 3: Implement the TabBar component**

Create `filebrowser/static/js/components/tab-bar.js`:

```js
import { html } from '../html.js';
import { createLogger } from '../logger.js';

const log = createLogger('TabBar');

export function TabBar({ tabs, activeTabId, onActivate, onPin, onClose }) {
    if (!tabs || tabs.length === 0) return null;

    return html`
        <div class="file-tab-bar">
            ${tabs.map(tab => html`
                <div
                    key=${tab.id}
                    class="file-tab ${tab.id === activeTabId ? 'active' : ''} ${tab.pinned ? 'pinned' : ''}"
                    onClick=${() => { log.debug('activate: tabId=%s', tab.id); onActivate(tab.id); }}
                >
                    <span class="file-tab-name">${tab.filePath.split('/').pop()}</span>
                    ${tab.dirty ? html`<span class="file-tab-dirty"></span>` : ''}
                    ${!tab.pinned ? html`
                        <button
                            class="file-tab-pin"
                            onClick=${(e) => { e.stopPropagation(); log.debug('pin: tabId=%s', tab.id); onPin(tab.id); }}
                            title="Pin tab"
                        >
                            <i class="ph ph-push-pin"></i>
                        </button>
                    ` : html`
                        <span class="file-tab-pinned-icon" title="Pinned">
                            <i class="ph-fill ph-push-pin"></i>
                        </span>
                    `}
                    <button
                        class="file-tab-close"
                        onClick=${(e) => { e.stopPropagation(); onClose(tab.id); }}
                        title="Close tab"
                    >
                        <i class="ph ph-x"></i>
                    </button>
                </div>
            `)}
        </div>
    `;
}
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_tab_bar.py -v
```

Expected: ALL tests PASS (20 tests).

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/tab-bar.js tests/test_tab_bar.py && git commit -m "feat: add TabBar component with static-analysis tests"
```

---

## Task 5: Tab Bar CSS

**Files:**
- Modify: `filebrowser/static/css/styles.css`
- Test: `tests/test_tab_bar.py` (add CSS tests to existing file)

**Step 1: Add CSS tests to test_tab_bar.py**

Append the following to the end of `tests/test_tab_bar.py`:

```python

# ── TestCssClasses ────────────────────────────────────────────────────

CSS_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "css"
    / "styles.css"
)


@lru_cache(maxsize=1)
def read_css() -> str:
    return CSS_FILE.read_text()


class TestCssClasses:
    def test_file_tab_bar_selector_exists(self):
        """styles.css must define .file-tab-bar selector."""
        css = read_css()
        assert ".file-tab-bar" in css, ".file-tab-bar selector not found in styles.css"

    def test_file_tab_selector_exists(self):
        """styles.css must define .file-tab selector."""
        css = read_css()
        assert re.search(r"\.file-tab\s*\{", css), ".file-tab selector not found in styles.css"

    def test_file_tab_active_selector_exists(self):
        """styles.css must define .file-tab.active selector."""
        css = read_css()
        assert ".file-tab.active" in css, ".file-tab.active selector not found in styles.css"

    def test_file_tab_dirty_selector_exists(self):
        """styles.css must define .file-tab-dirty selector."""
        css = read_css()
        assert ".file-tab-dirty" in css, ".file-tab-dirty selector not found in styles.css"

    def test_file_tab_close_selector_exists(self):
        """styles.css must define .file-tab-close selector."""
        css = read_css()
        assert ".file-tab-close" in css, ".file-tab-close selector not found in styles.css"

    def test_file_tab_pin_selector_exists(self):
        """styles.css must define .file-tab-pin selector."""
        css = read_css()
        assert ".file-tab-pin" in css, ".file-tab-pin selector not found in styles.css"

    def test_uses_design_tokens(self):
        """Tab CSS must use project design tokens, not hardcoded colors."""
        css = read_css()
        # Extract just the file-tab section (between .file-tab-bar and next major section)
        # Simpler: just verify design tokens appear near file-tab selectors
        assert "var(--accent)" in css, "var(--accent) not found in styles.css"
        assert "var(--bg-primary)" in css, "var(--bg-primary) not found in styles.css"

    def test_active_tab_uses_accent(self):
        """Active file tab must use the accent color."""
        css = read_css()
        # .file-tab.active should reference accent
        assert ".file-tab.active" in css, ".file-tab.active not found"

    def test_dirty_indicator_follows_existing_pattern(self):
        """Dirty indicator must follow the circular dot pattern from markdown/graphviz."""
        css = read_css()
        assert ".file-tab-dirty" in css, ".file-tab-dirty not found"
        assert "border-radius" in css, "border-radius not found — dirty indicator must be circular"
```

**Step 2: Run tests to verify CSS tests fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_tab_bar.py::TestCssClasses -v
```

Expected: Tests for `.file-tab-bar`, `.file-tab`, `.file-tab.active`, `.file-tab-dirty`, `.file-tab-close`, `.file-tab-pin` FAIL because these selectors don't exist in styles.css yet.

**Step 3: Add CSS to styles.css**

Open `filebrowser/static/css/styles.css`. Find the `.preview` section (around line 446-451) and the `.file-info-bar` section (around line 453). Insert the following **between** the `.preview` block and the `/* === File Info Bar === */` comment — that is, after line 451 and before line 452:

```css

/* === File Tab Bar === */
.file-tab-bar {
    display: flex;
    gap: 2px;
    margin-bottom: var(--space-sm);
    overflow-x: auto;
    flex-shrink: 0;
}
.file-tab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border: 0.5px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--bg-primary);
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s var(--ease-out);
    white-space: nowrap;
}
.file-tab:hover {
    background: var(--bg-secondary);
    color: var(--text-primary);
}
.file-tab.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--text-on-accent);
}
.file-tab-name {
    overflow: hidden;
    text-overflow: ellipsis;
}
.file-tab-pin,
.file-tab-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
    padding: 0;
    font-size: 12px;
    opacity: 0.6;
    transition: opacity 0.15s var(--ease-out);
}
.file-tab-pin:hover,
.file-tab-close:hover {
    opacity: 1;
}
.file-tab-dirty {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
}
.file-tab.active .file-tab-dirty {
    background: rgba(255, 255, 255, 0.9);
}
.file-tab-pinned-icon {
    display: inline-flex;
    align-items: center;
    font-size: 12px;
    opacity: 0.6;
}
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_tab_bar.py -v
```

Expected: ALL tests PASS (29 tests total — 20 component + 9 CSS).

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/css/styles.css tests/test_tab_bar.py && git commit -m "feat: add file tab bar CSS following existing design token patterns"
```

---

## Task 6: Layout Integration

**Files:**
- Modify: `filebrowser/static/js/components/layout.js`
- Test: `tests/test_layout_integration.py` (add new test classes)

**Step 1: Add tab integration tests to test_layout_integration.py**

Append the following to the end of `tests/test_layout_integration.py`:

```python


# ── TestTabManagerIntegration ─────────────────────────────────────────────


class TestTabManagerIntegration:
    def test_imports_use_tab_manager(self):
        """Must import useTabManager from the hooks directory."""
        src = read_layout()
        assert "useTabManager" in src, "useTabManager not imported"
        assert "use-tab-manager.js" in src, "use-tab-manager.js import path not found"

    def test_use_tab_manager_import_is_named(self):
        """useTabManager must be a named import from '../hooks/use-tab-manager.js'."""
        src = read_layout()
        assert re.search(
            r"import\s*\{[^}]*useTabManager[^}]*\}\s*from\s*['\"]\.\.\/hooks\/use-tab-manager\.js['\"]",
            src,
        ), "useTabManager must be a named import from '../hooks/use-tab-manager.js'"

    def test_imports_tab_bar(self):
        """Must import TabBar from './tab-bar.js'."""
        src = read_layout()
        assert "TabBar" in src, "TabBar not imported"
        assert "tab-bar.js" in src, "tab-bar.js import path not found"

    def test_tab_bar_import_is_named(self):
        """TabBar must be a named import from './tab-bar.js'."""
        src = read_layout()
        assert re.search(
            r"import\s*\{[^}]*TabBar[^}]*\}\s*from\s*['\"]\.\/tab-bar\.js['\"]",
            src,
        ), "TabBar must be a named import from './tab-bar.js'"

    def test_tab_manager_hook_is_called(self):
        """Layout must call useTabManager() to get the tab manager instance."""
        src = read_layout()
        assert re.search(r"useTabManager\(\)", src), (
            "useTabManager() call not found — hook must be invoked in Layout"
        )

    def test_selected_file_uses_tab_manager(self):
        """selectedFile must be derived from tabManager.activeFilePath."""
        src = read_layout()
        assert "activeFilePath" in src, (
            "activeFilePath not found — selectedFile must come from tab manager"
        )

    def test_handle_select_file_calls_tab_manager_open(self):
        """handleSelectFile must call tabManager.open() instead of setSelectedFile()."""
        src = read_layout()
        assert re.search(r"tabManager\.open\(", src) or re.search(
            r"\.open\(path\)", src
        ), "tabManager.open() not called in handleSelectFile"


# ── TestTabBarRendering ───────────────────────────────────────────────────


class TestTabBarRendering:
    def test_tab_bar_rendered_in_preview_section(self):
        """TabBar must be rendered inside the preview section."""
        src = read_layout()
        assert "<${TabBar}" in src or "${TabBar}" in src, (
            "TabBar component not rendered in layout"
        )

    def test_tab_bar_receives_tabs_prop(self):
        """TabBar must receive tabs prop from tabManager."""
        src = read_layout()
        assert re.search(r"tabs=\$\{tabManager\.tabs\}", src) or (
            "tabManager.tabs" in src
        ), "tabs prop not passed to TabBar from tabManager"

    def test_tab_bar_receives_active_tab_id_prop(self):
        """TabBar must receive activeTabId prop."""
        src = read_layout()
        assert "activeTabId" in src, "activeTabId prop not passed to TabBar"

    def test_tab_bar_receives_on_activate_prop(self):
        """TabBar must receive onActivate prop."""
        src = read_layout()
        assert "onActivate" in src, "onActivate prop not passed to TabBar"

    def test_tab_bar_receives_on_pin_prop(self):
        """TabBar must receive onPin prop."""
        src = read_layout()
        assert "onPin" in src, "onPin prop not passed to TabBar"

    def test_tab_bar_receives_on_close_prop(self):
        """TabBar must receive onClose prop wired to tabManager.close."""
        src = read_layout()
        # onClose must appear in TabBar rendering (not the terminal onClose)
        assert re.search(r"onClose=\$\{tabManager\.close\}", src), (
            "onClose=${tabManager.close} not passed to TabBar"
        )

    def test_preview_pane_uses_active_file_path(self):
        """PreviewPane must receive filePath from tabManager.activeFilePath (via selectedFile alias or directly)."""
        src = read_layout()
        # PreviewPane should use the tab manager's active file path
        # Either directly: filePath=${tabManager.activeFilePath}
        # Or via alias: filePath=${selectedFile} where selectedFile = tabManager.activeFilePath
        assert "activeFilePath" in src, (
            "activeFilePath not referenced — PreviewPane must get its filePath from tab manager"
        )
```

**Step 2: Run new tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestTabManagerIntegration -v
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestTabBarRendering -v
```

Expected: ALL new tests FAIL because layout.js doesn't have tab manager integration yet.

**Step 3: Modify layout.js**

Open `filebrowser/static/js/components/layout.js` and make these changes:

**3a. Add imports** (after the existing imports, around line 10):

Add these two lines after `import { TerminalPanel } from './terminal.js';`:

```js
import { useTabManager } from '../hooks/use-tab-manager.js';
import { TabBar } from './tab-bar.js';
```

**3b. Replace selectedFile state** (line 15):

Remove this line:
```js
    const [selectedFile, setSelectedFile] = useState(null);
```

Add these two lines in its place:
```js
    const tabManager = useTabManager();
    const selectedFile = tabManager.activeFilePath;
```

The `selectedFile` alias preserves backward compatibility with everything that reads `selectedFile` (FileTree, ActionBar, etc.) while switching the underlying source to the tab manager.

**3c. Update handleSelectFile** (line 279-283):

Change `handleSelectFile` from:
```js
    const handleSelectFile = (path) => {
        setSelectedFile(path);
        setSelectedFiles(new Set([path]));
        setSidebarOpen(false);
    };
```

To:
```js
    const handleSelectFile = (path) => {
        tabManager.open(path);
        setSelectedFiles(new Set([path]));
        setSidebarOpen(false);
    };
```

**3d. Wire TabBar into preview section** (lines 465-467):

Change:
```js
                <main class="preview">
                    <${PreviewPane} filePath=${selectedFile} />
                </main>
```

To:
```js
                <main class="preview">
                    <${TabBar}
                        tabs=${tabManager.tabs}
                        activeTabId=${tabManager.activeTabId}
                        onActivate=${tabManager.activate}
                        onPin=${tabManager.pin}
                        onClose=${tabManager.close}
                    />
                    <${PreviewPane} filePath=${selectedFile} />
                </main>
```

**Step 4: Run ALL tests to verify**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py -v
```

Expected: ALL tests PASS — both the existing terminal integration tests AND the new tab manager tests. The existing tests pass because `selectedFile` still exists as an alias and `setSelectedFile` is no longer referenced (replaced by `tabManager.open`).

If any existing test references `setSelectedFile` and fails, that's expected — the variable no longer exists. Check the error message and verify the functionality is now handled by `tabManager.open`.

**Step 5: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/layout.js tests/test_layout_integration.py && git commit -m "feat: integrate useTabManager and TabBar into layout"
```

---

## Task 7: PreviewPane onDirtyChange

**Files:**
- Modify: `filebrowser/static/js/components/preview.js` (PreviewPane, HtmlViewer, GraphvizViewer)
- Modify: `filebrowser/static/js/components/editable-viewer.js` (EditableViewer)
- Modify: `filebrowser/static/js/components/markdown-editor.js` (MarkdownEditor)
- Modify: `filebrowser/static/js/components/layout.js` (wire onDirtyChange callback)
- Test: `tests/test_layout_integration.py` (add tests)

**Step 1: Add onDirtyChange integration tests**

Append to `tests/test_layout_integration.py`:

```python


# ── TestPreviewPaneDirtyIntegration ───────────────────────────────────────


PREVIEW_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "preview.js"
)

EDITABLE_VIEWER_FILE = (
    Path(__file__).parent.parent
    / "filebrowser"
    / "static"
    / "js"
    / "components"
    / "editable-viewer.js"
)


@lru_cache(maxsize=1)
def read_preview() -> str:
    return PREVIEW_FILE.read_text()


@lru_cache(maxsize=1)
def read_editable_viewer() -> str:
    return EDITABLE_VIEWER_FILE.read_text()


class TestPreviewPaneDirtyIntegration:
    def test_preview_pane_accepts_on_dirty_change_prop(self):
        """PreviewPane function signature must include onDirtyChange."""
        src = read_preview()
        assert re.search(
            r"function\s+PreviewPane\s*\(\s*\{[^}]*onDirtyChange[^}]*\}", src
        ), "onDirtyChange not found in PreviewPane function signature"

    def test_on_dirty_change_passed_to_editable_viewer(self):
        """PreviewPane must pass onDirtyChange to EditableViewer."""
        src = read_preview()
        assert re.search(r"EditableViewer.*onDirtyChange", src, re.DOTALL), (
            "onDirtyChange not passed to EditableViewer in PreviewPane"
        )

    def test_on_dirty_change_passed_to_markdown_editor(self):
        """PreviewPane must pass onDirtyChange to MarkdownEditor."""
        src = read_preview()
        assert re.search(r"MarkdownEditor.*onDirtyChange", src, re.DOTALL), (
            "onDirtyChange not passed to MarkdownEditor in PreviewPane"
        )

    def test_editable_viewer_accepts_on_dirty_change(self):
        """EditableViewer must accept onDirtyChange in its function signature."""
        src = read_editable_viewer()
        assert "onDirtyChange" in src, (
            "onDirtyChange not found in editable-viewer.js"
        )

    def test_layout_wires_on_dirty_change_to_preview_pane(self):
        """layout.js must pass onDirtyChange callback to PreviewPane."""
        src = read_layout()
        assert "onDirtyChange" in src, (
            "onDirtyChange not passed to PreviewPane in layout.js"
        )

    def test_layout_on_dirty_change_calls_set_dirty(self):
        """onDirtyChange callback must call tabManager.setDirty."""
        src = read_layout()
        assert "setDirty" in src, (
            "tabManager.setDirty not called in onDirtyChange callback"
        )
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestPreviewPaneDirtyIntegration -v
```

Expected: ALL tests FAIL because onDirtyChange doesn't exist yet.

**Step 3: Modify preview.js — PreviewPane signature**

Open `filebrowser/static/js/components/preview.js`.

**3a.** Change the PreviewPane function signature (line 597) from:
```js
export function PreviewPane({ filePath }) {
```
To:
```js
export function PreviewPane({ filePath, onDirtyChange }) {
```

**3b.** In the switch statement where sub-components are rendered (around lines 729-741), add `onDirtyChange` to each editable component:

Change:
```js
        case 'text':
        case 'code':
            inner = html`<${EditableViewer} text=${content.text} path=${filePath}
                                             onSave=${handleContentSave} />`;
            break;
        case 'markdown':
            inner = html`<${MarkdownEditor} text=${content.text} path=${filePath} onSave=${handleContentSave} />`;
            break;
        case 'html':
            inner = html`<${HtmlViewer} text=${content.text} path=${filePath} contentUrl=${contentUrl} onSave=${handleContentSave} />`;
            break;
        case 'graphviz':
            inner = html`<${GraphvizViewer} text=${content.text} path=${filePath} onSave=${handleContentSave} />`;
            break;
```

To:
```js
        case 'text':
        case 'code':
            inner = html`<${EditableViewer} text=${content.text} path=${filePath}
                                             onSave=${handleContentSave} onDirtyChange=${onDirtyChange} />`;
            break;
        case 'markdown':
            inner = html`<${MarkdownEditor} text=${content.text} path=${filePath} onSave=${handleContentSave} onDirtyChange=${onDirtyChange} />`;
            break;
        case 'html':
            inner = html`<${HtmlViewer} text=${content.text} path=${filePath} contentUrl=${contentUrl} onSave=${handleContentSave} onDirtyChange=${onDirtyChange} />`;
            break;
        case 'graphviz':
            inner = html`<${GraphvizViewer} text=${content.text} path=${filePath} onSave=${handleContentSave} onDirtyChange=${onDirtyChange} />`;
            break;
```

**3c.** For `HtmlViewer` (defined inside preview.js around line 142), add `onDirtyChange` to its signature and a useEffect:

Change:
```js
function HtmlViewer({ text, path, contentUrl, onSave }) {
```
To:
```js
function HtmlViewer({ text, path, contentUrl, onSave, onDirtyChange }) {
```

Add this useEffect right after the existing `const [dirty, setDirty] = useState(false);` line (after line 145):
```js
    useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
```

**3d.** For `GraphvizViewer` (defined inside preview.js), find its function signature and make the same changes. Find the function definition (search for `function GraphvizViewer`), add `onDirtyChange` to its destructured props, and add the same useEffect after its `const [dirty, setDirty] = useState(false);` line:
```js
    useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
```

**Step 4: Modify editable-viewer.js**

Open `filebrowser/static/js/components/editable-viewer.js`. Find the `EditableViewer` function signature (look for `export function EditableViewer`). Add `onDirtyChange` to the destructured props. Then find `const [dirty, setDirty] = useState(false);` and add this line right after it:

```js
    useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
```

Make sure `useEffect` is in the import list at the top of the file. Check the existing imports — if it already imports `useEffect` from `preact/hooks`, no change needed. If not, add it.

**Step 5: Modify markdown-editor.js**

Open `filebrowser/static/js/components/markdown-editor.js`. Find the `MarkdownEditor` function signature (look for `export function MarkdownEditor`). Add `onDirtyChange` to the destructured props. Then find `const [dirty, setDirty] = useState(false);` and add this line right after it:

```js
    useEffect(() => { if (onDirtyChange) onDirtyChange(dirty); }, [dirty, onDirtyChange]);
```

Same check for `useEffect` in imports as with editable-viewer.js.

**Step 6: Wire onDirtyChange in layout.js**

Open `filebrowser/static/js/components/layout.js`. Find the PreviewPane rendering (which was updated in Task 6). Change:

```js
                    <${PreviewPane} filePath=${selectedFile} />
```

To:
```js
                    <${PreviewPane}
                        filePath=${selectedFile}
                        onDirtyChange=${(dirty) => tabManager.setDirty(tabManager.activeTabId, dirty)}
                    />
```

**Step 7: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestPreviewPaneDirtyIntegration -v
```

Expected: ALL 6 tests PASS.

Also run the full test suite to make sure nothing broke:

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/ -v
```

Expected: ALL tests PASS.

**Step 8: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/preview.js filebrowser/static/js/components/editable-viewer.js filebrowser/static/js/components/markdown-editor.js filebrowser/static/js/components/layout.js tests/test_layout_integration.py && git commit -m "feat: add onDirtyChange callback threading from editors to tab manager"
```

---

## Task 8: File Management Integration

**Files:**
- Modify: `filebrowser/static/js/components/layout.js` (handleCtxRename, handleCtxDelete)
- Test: `tests/test_layout_integration.py` (add tests)

**Step 1: Add file management integration tests**

Append to `tests/test_layout_integration.py`:

```python


# ── TestFileManagementTabIntegration ──────────────────────────────────────


class TestFileManagementTabIntegration:
    def test_rename_calls_update_path(self):
        """handleCtxRename must call tabManager.updatePath after successful rename."""
        src = read_layout()
        assert re.search(r"tabManager\.updatePath\(|\.updatePath\(", src), (
            "tabManager.updatePath() not found — rename must update tab paths"
        )

    def test_delete_calls_close_by_path(self):
        """handleCtxDelete must call tabManager.closeByPath after successful delete."""
        src = read_layout()
        assert re.search(r"tabManager\.closeByPath\(|\.closeByPath\(", src), (
            "tabManager.closeByPath() not found — delete must close affected tabs"
        )

    def test_delete_no_longer_uses_set_selected_file_null(self):
        """handleCtxDelete must NOT use setSelectedFile(null) — replaced by closeByPath."""
        src = read_layout()
        assert "setSelectedFile(null)" not in src, (
            "setSelectedFile(null) still present — should be replaced by tabManager.closeByPath"
        )

    def test_delete_no_longer_references_set_selected_file(self):
        """setSelectedFile must not exist anywhere in layout.js — fully replaced by tab manager."""
        src = read_layout()
        assert "setSelectedFile" not in src, (
            "setSelectedFile still referenced — all writes to selectedFile "
            "should go through tabManager"
        )
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestFileManagementTabIntegration -v
```

Expected: Tests fail because layout.js still has the old rename/delete handlers.

**Step 3: Modify handleCtxRename in layout.js**

Open `filebrowser/static/js/components/layout.js`. Find `handleCtxRename` (around line 308).

Change:
```js
    const handleCtxRename = (path) => {
        const name = prompt('New name:', path.split('/').pop());
        if (!name) return;
        const parts = path.split('/');
        parts[parts.length - 1] = name;
        const newPath = parts.join('/');
        api.put('/api/files/rename', { old_path: path, new_path: newPath })
            .then(refresh)
            .catch(() => {});
    };
```

To:
```js
    const handleCtxRename = (path) => {
        const name = prompt('New name:', path.split('/').pop());
        if (!name) return;
        const parts = path.split('/');
        parts[parts.length - 1] = name;
        const newPath = parts.join('/');
        api.put('/api/files/rename', { old_path: path, new_path: newPath })
            .then(() => {
                tabManager.updatePath(path, newPath);
                refresh();
            })
            .catch(() => {});
    };
```

**Step 4: Modify handleCtxDelete in layout.js**

Find `handleCtxDelete` (around line 319).

Change:
```js
    const handleCtxDelete = async (path) => {
        if (!confirm(`Delete ${path.split('/').pop()}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(path)}`);
            if (selectedFile === path) setSelectedFile(null);
            refresh();
        } catch { /* toast shown */ }
    };
```

To:
```js
    const handleCtxDelete = async (path) => {
        if (!confirm(`Delete ${path.split('/').pop()}?`)) return;
        try {
            await api.del(`/api/files?path=${encodeURIComponent(path)}`);
            tabManager.closeByPath(path);
            refresh();
        } catch { /* toast shown */ }
    };
```

**Step 5: Run tests to verify they pass**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/test_layout_integration.py::TestFileManagementTabIntegration -v
```

Expected: ALL 4 tests PASS.

Run full test suite to catch regressions:

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/ -v
```

Expected: ALL tests PASS.

**Step 6: Commit**

```bash
cd /home/robotdad/repos/files/filebrowser && git add filebrowser/static/js/components/layout.js tests/test_layout_integration.py && git commit -m "feat: wire file rename/delete handlers to tab manager updatePath and closeByPath"
```

---

## Task 9: Verify and Update Existing Layout Tests

**Files:**
- Modify: `tests/test_layout_integration.py` (if any existing tests break)

**Step 1: Run the complete test suite**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/ -v
```

Examine the output carefully. Look for any failures in existing test files, especially:
- `tests/test_layout_integration.py` — the terminal tests should still pass since `selectedFile` still exists as an alias
- `tests/test_index_html.py` — shouldn't be affected
- Any test that references `setSelectedFile` — this no longer exists in layout.js

**Step 2: Fix any broken tests**

If any existing tests reference `setSelectedFile` directly and fail:
- Update the assertion to check for `tabManager.open` instead
- Or remove the assertion if the old behavior is fully replaced

If all tests pass (most likely scenario since `selectedFile` exists as an alias), no changes are needed. The existing terminal tests verify terminal integration which is unchanged.

**Step 3: Run the full suite one more time**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run pytest tests/ -v --tb=short
```

Expected: ALL tests PASS. Count the total: should be the original test count plus approximately 50 new tests across `test_use_tab_manager.py`, `test_tab_bar.py`, and the additions to `test_layout_integration.py`.

**Step 4: Commit (only if changes were made)**

```bash
cd /home/robotdad/repos/files/filebrowser && git add tests/ && git commit -m "test: update existing layout tests for tab manager integration"
```

If no changes were needed, skip this commit.

---

## Task 10: Browser Post-Change Verification

**Files:** None modified (verification only)

This task re-runs the baseline scenarios from Task 2 plus new tab-specific scenarios to verify everything works.

**Step 1: Ensure the dev server is running**

```bash
cd /home/robotdad/repos/files/filebrowser && uv run uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
```

**Step 2: Re-run baseline scenarios**

Delegate to a browser testing agent (playwright skill) with the same scenarios from Task 2:

1. Navigate to `http://localhost:58080`. Screenshot the initial state — should show file tree and empty preview pane (no tabs visible since no file is selected).
2. Click on a `.py` file. Screenshot — should show code preview AND a tab bar with one tab showing the file name.
3. Click on a `.md` file. Screenshot — the tab should update to show the new file name (replacing the unpinned default tab).
4. Open the terminal (Ctrl+`). Screenshot — terminal should coexist with preview + tab bar.
5. Close the terminal. Screenshot — preview + tab bar without terminal.

Compare with Task 2 baseline screenshots. The only visible difference should be the tab bar appearing above the preview content.

**Step 3: Run tab-specific scenarios**

Delegate these additional scenarios to the browser testing agent:

6. With a file open, look at the tab bar. The tab should show the file's basename and a pin icon (outline push-pin) and a close X.
7. Click the pin icon on the tab. The pin icon should change to a filled push-pin. The tab is now pinned.
8. Click on a different file in the file tree. A new tab should appear to the LEFT of the pinned tab with the new file's name. The pinned tab should still be visible.
9. Click on the pinned tab. The preview should switch back to the pinned file's content. The pinned tab should have the active (accent) background.
10. Click the close X on the pinned tab. The tab should close. The other tab should become active.
11. (If an editor is available) Edit a file to make it dirty. The tab should show a small dot indicator. Click close — a browser confirm dialog should appear asking about unsaved changes.

**Step 4: Record results**

Note which scenarios passed and any issues found. If issues are found, they should be filed as follow-up tasks — do not fix them in this task.

No commit for this task — this is verification only.

---

## Summary

| Task | What | New Tests | Files Changed |
|------|------|-----------|---------------|
| 1 | Browser testing guide + dev guide | 0 | 2 created/modified |
| 2 | Browser baseline capture | 0 | 0 (screenshots only) |
| 3 | useTabManager hook | ~27 | 2 created |
| 4 | TabBar component | ~20 | 2 created |
| 5 | Tab bar CSS | ~9 | 1 modified, 1 test updated |
| 6 | Layout integration | ~14 | 1 modified, 1 test updated |
| 7 | PreviewPane onDirtyChange | ~6 | 4 modified, 1 test updated |
| 8 | File management integration | ~4 | 1 modified, 1 test updated |
| 9 | Existing test updates | 0 | 0-1 modified |
| 10 | Browser post-change verification | 0 | 0 (verification only) |

**Total new tests:** ~80
**Total files created:** 4 (hook, component, 2 test files) + 1 doc
**Total files modified:** ~8 (layout.js, preview.js, editable-viewer.js, markdown-editor.js, styles.css, test_layout_integration.py, DEV_GUIDE.md, test_tab_bar.py)