# Browser-Based Behavioral Testing

## 1. Overview

Browser-based behavioral tests verify actual UI behavior through Amplifier's browser testing agents (`browser-tester:browser-operator`). They complement the existing Python static-analysis tests (which inspect JS source text) and Python backend tests (which test API endpoints).

The three test types are complementary — no single type covers everything:
- **Backend tests** run fast and verify server logic with no browser required
- **Static-analysis tests** verify component structure and wiring at the source level
- **Browser tests** verify real user interaction flows, visual states, and component coexistence at runtime

## 2. When to Use Browser Tests

- Verifying UI flows that depend on user interaction (clicks, form fills, navigation)
- Testing visual state changes (tab switching, panel open/close, animations)
- Regression testing after frontend changes
- Validating terminal/preview/sidebar coexistence
- Any behavioral verification that static analysis can't cover

## 3. The Baseline-Before/Verify-After Pattern

This is the core testing approach for avoiding unintended regressions:

1. **Before changes**: Run the scenario list and screenshot each key state. These screenshots are the baseline.
2. **Make your changes**: Implement the feature or fix.
3. **After changes**: Run the same scenarios again. Compare with baseline. The only differences should be the intentional changes.
4. **Add feature-specific scenarios**: Test the new behavior directly.

This pattern catches visual regressions that static analysis misses — layout shifts, overlapping elements, missing UI updates, and broken interactions.

## 4. How to Run Browser Tests

### Prerequisites

- `agent-browser` installed:
  ```bash
  npm install -g agent-browser && agent-browser install
  ```
- Dev server running:
  ```bash
  cd /home/robotdad/repos/files/filebrowser && uv run uvicorn filebrowser.main:app --reload --host 0.0.0.0 --port 58080
  ```

### Running a Scenario

In an Amplifier session, delegate to `browser-tester:browser-operator`:

```
delegate(agent="browser-tester:browser-operator", instruction="Navigate to http://localhost:58080 and [scenario description]")
```

Example:

```
delegate(
  agent="browser-tester:browser-operator",
  instruction="Navigate to http://localhost:58080. Log in if prompted. Click a .py file in the file tree, then screenshot the result. Verify the code editor renders with syntax highlighting."
)
```

### Capturing Baseline Screenshots

Before making frontend changes, run a full pass of the Standard Scenario Checklist (section 5) and save screenshots with descriptive names:

```
delegate(
  agent="browser-tester:browser-operator",
  instruction="Navigate to http://localhost:58080. For each scenario below, take a screenshot and save it to /tmp/baseline/[scenario-name].png: ..."
)
```

## 5. Standard Scenario Checklist

Use this checklist when verifying the app is working correctly. Run it before and after any frontend change.

### File Browsing

- [ ] Navigate to app, verify file tree loads with directory entries visible
- [ ] Click a file, verify preview renders in the main panel
- [ ] Click a directory, verify navigation into that directory works
- [ ] Open a `.md` file, verify Markdown preview renders with formatting
- [ ] Open an image file, verify image displays (not raw bytes)
- [ ] Open a code file (`.py`, `.js`), verify syntax-highlighted code editor
- [ ] Open a `.dot` file, verify DOT diagram renders as SVG

### Terminal Coexistence

- [ ] Open terminal (Ctrl+\`), verify it appears alongside the preview
- [ ] Close terminal, verify preview returns to full width
- [ ] Dock terminal to bottom, verify layout changes and terminal is usable
- [ ] Open a file while terminal is open, verify preview updates without closing terminal

### Tab Management (post-tab-feature)

- [ ] Open a file, verify tab bar appears with the file name
- [ ] Pin a tab, verify pin icon changes state
- [ ] Open another file, verify new default tab appears and pinned tab remains
- [ ] Switch tabs, verify correct file content renders for each tab
- [ ] Close a tab, verify it is removed from the tab bar
- [ ] Close a tab with unsaved changes, verify unsaved-changes prompt appears
- [ ] With multiple tabs open, verify terminal can still be opened and closed

### Sidebar and Navigation

- [ ] Breadcrumb reflects current directory
- [ ] Navigating up with breadcrumb works correctly
- [ ] File tree scrolls for deep directory trees

### Command Palette

- [ ] Open command palette (Ctrl+K or command bar), verify it appears
- [ ] Type a file name, verify search results filter
- [ ] Select a result, verify navigation occurs

## 6. Writing New Scenarios

When adding a feature, write scenarios that cover:

**Happy path**
- The feature works as designed under normal conditions

**Edge cases**
- Empty state (e.g., no tabs open, empty directory)
- Error state (e.g., file not found, permission denied)
- Boundary conditions (e.g., very long file names, deeply nested paths)

**Interaction with existing features**
- Terminal still works alongside the new feature
- Sidebar and file tree still function
- Command palette still opens
- Keyboard shortcuts still fire

**Screenshots for key states**
- Initial state before interaction
- State after the primary interaction
- Final settled state

### Scenario Description Template

```
Navigate to http://localhost:58080. Log in if prompted with test credentials.

Scenario: [Feature name] — [what you're verifying]

Steps:
1. [Action]
2. [Action]
3. Screenshot the result and save to /tmp/[scenario-name].png

Expected: [What should be visible or have changed]
```

## 7. Relationship to Other Test Types

| Test Type | What It Tests | How It Works | When to Use |
|-----------|--------------|--------------|-------------|
| Python backend tests (`uv run pytest`) | API endpoints, auth, file operations | httpx test client | Backend logic changes |
| Python static-analysis tests | JS/CSS source structure | Read file, assert patterns | Any frontend file change |
| Browser behavioral tests | Actual UI behavior | Browser automation via agent-browser | UI interaction changes, visual verification |

All three types should stay green. Backend and static-analysis tests run in CI automatically. Browser tests are run manually by a developer or Amplifier session before merging frontend changes.
