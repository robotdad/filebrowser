# tmux Cheatsheet

A quick reference for common tmux commands. This document contains tables that
must render in read-only View mode AND remain visible when opened in the editor.

## Sessions

| Command                     | Action                  |
| --------------------------- | ----------------------- |
| `tmux new -s name`          | Create a named session  |
| `tmux ls`                   | List sessions           |
| `tmux attach -t name`       | Attach to a session     |
| `tmux kill-session -t name` | Kill a session          |

## Windows

| Keybinding   | Action                  |
| ------------ | ----------------------- |
| `prefix c`   | Create a new window     |
| `prefix ,`   | Rename the window       |
| `prefix n`   | Next window             |
| `prefix &`   | Kill the current window |

## Panes

| Keybinding   | Action                |
| ------------ | --------------------- |
| `prefix %`   | Split vertically      |
| `prefix "`   | Split horizontally    |
| `prefix z`   | Toggle pane zoom      |
| `prefix x`   | Kill the current pane |
