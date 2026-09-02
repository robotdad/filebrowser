<!-- BINDING maintainer acceptance criteria -- extracted VERBATIM from the authenticated maintainer comment channel by criteria_gate. NO ONE in this run may edit this file: the pipeline holds no authority over maintainer text. -->
Source-comment-author: @robotdad
Source-comment-id: 5420206455
Source-comment-updated-at: 2026-08-26T03:33:21Z

## Acceptance criteria (feature-capsule)

_Supersedes the earlier blocks. Resolves the two open questions from the specify run: **Q1/AC-3** path-sameness = resolved/canonicalized equality (as `/api/locations` does); **Q2/AC-2** the delete surface identifies a favorite by its **path value**, not a numeric id._

Owned-by: @robotdad
Scope: IN -- server-side, on-disk persistence of pinned favorite folders exposed over the backend HTTP API, proven to survive a fresh OS process. OUT -- per-user isolation, pin ordering, multi-device sync, and any UI change beyond wiring the existing pin control to the store.

AC-1: A favorite added through the backend API is present when the store is read by a NEW OS process (a subprocess, or a fresh app instance in a separate interpreter) pointed at the same data_dir. An in-process / in-memory-only store that loses its data when the process exits does NOT satisfy this.
AC-2: A favorite removed through the backend API -- identified by its **path value** (the path in the request body or query string, not a numeric id) -- is still absent when read by a new OS process against the same data_dir; the removal is written to disk, not merely mutated in memory.
AC-3: Adding the same favorite path twice does not create a duplicate entry (idempotent add), where "same" means **resolved/canonicalized path equality** -- the rule the sibling locations feature uses via `Path(...).resolve()` in `filebrowser/services/locations.py` (so e.g. `./x` and an already-stored `x` that resolve to the same path are one entry). The deduplication still holds after the store is reloaded by a new OS process against the same data_dir.
AC-4 [guard]: The existing external-locations feature (POST/GET/DELETE /api/locations and its locations.json on-disk store) continues to work unchanged.
