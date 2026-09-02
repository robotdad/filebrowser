---
id: favorites-backend-persistence
title: Favorites backend persistence (server-side, on-disk)
red_signal: AC-1: UNMET
criteria_digest: 7ef8d2917d0d4b0d602119c803bc79f0790f25a67f53124602adb5d4ed7af989
base_sha: 48647a69db662dc321cf38abebadbcf5d0b6ee68
later_commit: eb4c88e828b7c0c7ba7b1384dca89447700e75ec
target_repo: robotdad/filebrowser
verify: DEFINITION.verify.sh
---

## Goal

A favorite folder added through the backend HTTP API is durable: it is
written to disk under the server's `data_dir` and is present when a
*different* OS process (a fresh interpreter, not just a fresh Python
object in the same process) reads it back. Removal works the same way in
reverse, and it identifies the favorite being removed by its **path
value** (the path carried in the request body or query string), never by
a numeric id. Adding the same folder twice -- even under a differently
spelled but equivalent path -- never creates two entries; "equivalent"
means resolved/canonicalized path equality, the same rule
`filebrowser/services/locations.py` already uses via `Path(...).resolve()`
for the sibling external-locations feature. The existing
`/api/locations` feature (add/list/remove, backed by `locations.json`)
keeps working exactly as it does today.

## Why this matters

Today "favorites" is purely a browser-side concept: `layout.js` reads and
writes an array to `localStorage` and nothing else. A pinned folder
therefore evaporates the moment the browser's local storage is cleared or
a different browser/device is used, and -- more immediately observable --
a restart of the backend process has no bearing on it either way, because
the backend has never heard of favorites at all. Giving the backend its
own durable store for favorites, mirroring the on-disk persistence pattern
the external-locations feature already established, is the missing piece
that lets a favorite survive independently of any one browser session.

## Definition of done

### AC-1: add via the backend API survives a new OS process
**Criterion:** "A favorite added through the backend API is present when
the store is read by a NEW OS process (a subprocess, or a fresh app
instance in a separate interpreter) pointed at the same data_dir. An
in-process / in-memory-only store that loses its data when the process
exits does NOT satisfy this."

**What the script checks:** it starts one process that adds a favorite
folder through the running FastAPI application's HTTP surface (a real
request through the ASGI stack, not a bare Python function call), then
starts a **second, independent process** pointed at the same
`FILEBROWSER_DATA_DIR` and confirms the same path is present when read
back through the HTTP surface there. A **third, independent process**
pointed at a different, freshly-created `FILEBROWSER_DATA_DIR` confirms
the same path is absent there. This proves the store is genuinely scoped
by the configured `data_dir`, rather than using one global/shared file
that every server instance can see. All three steps are separate `uv run`
invocations of the same vendored helper script -- genuinely separate
interpreters, not objects sharing memory. The exact route path, request
shape, on-disk filename/format, and module/class names are NOT assumed:
the script discovers whichever HTTP routes are new relative to the pinned
base SHA and tries each as a candidate.

### AC-2: remove via the backend API, identified by path value, survives a new OS process
**Criterion:** "A favorite removed through the backend API -- identified
by its path value (the path in the request body or query string, not a
numeric id) -- is still absent when read by a new OS process against the
same data_dir; the removal is written to disk, not merely mutated in
memory."

**What the script checks:** two favorites (A and B) are added in one
process. A second process then removes **whichever of A or B is chosen
at gate RUNTIME by a coin flip** -- not always the first-added one --
supplying that entry's path value (tried both as a query-string parameter
and as a JSON body field, since the criterion explicitly allows either).
A third, independent process confirms the runtime-chosen target is absent
AND that the non-targeted sibling is still present, whichever of the two
that turns out to be. Randomizing which of the pair is removed (rather
than always removing the first-added one) is required to actually prove
path-based identification: a fixed always-remove-the-first-added target
can be satisfied by an implementation that ignores the path value
entirely and always drops whichever entry was added first (e.g. a
`list.pop(0)`), since "first-added" and "the requested path" would
coincide on every gate run. Because the target varies at runtime, only a
removal that genuinely reads and matches the supplied path value passes
on both branches. A candidate route that only accepts a numeric path
segment (the `/api/locations/{location_id}` pattern the criterion
explicitly rules out for favorites) will not match any path-value-only
request and is correctly scored as not satisfying this criterion.
Whether removing a path that was never added should succeed idempotently
or raise an error is genuinely unspecified by the criteria and is
deliberately NOT asserted either way (see Non-goals).

### AC-3: idempotent add via resolved/canonicalized path equality, surviving a new OS process
**Criterion:** "Adding the same favorite path twice does not create a
duplicate entry (idempotent add), where 'same' means resolved/
canonicalized path equality -- the rule the sibling locations feature
uses via `Path(...).resolve()` in `filebrowser/services/locations.py` ...
The deduplication still holds after the store is reloaded by a new OS
process against the same data_dir."

**What the script checks:** three differently-spelled paths that all
resolve to the SAME real directory are added (the criterion's own literal
`./x`-style example, a `dir/.` spelling, and a runtime-generated
`dir/<random>/..` spelling -- only one of these three is the criteria's own
example, so a gate that merely special-cased the literal example would
fail this), plus one genuinely distinct directory. The script asserts
exactly one stored entry resolves to the first directory (not zero, not
three) and that the distinct directory is present too (dedup must not
over-fire). It then re-counts entries resolving to the first directory
from a fresh process, confirming the count of one survives the process
boundary. The comparison rule itself (`Path(...).resolve()` equality) is
exactly the oracle this criterion names, applied to path spellings never
enumerated in the criteria text.

### AC-4 [guard]: existing external-locations feature keeps working
**Criterion:** "The existing external-locations feature (POST/GET/DELETE
/api/locations and its locations.json on-disk store) continues to work
unchanged."

**What the script checks:** two independent lines of evidence. First, a
direct HTTP-level exercise of all three verbs against `/api/locations`
(add, confirm via list, delete, confirm absence via list) plus a
negative-space check that deleting a nonexistent numeric id is refused
rather than silently accepted. Second, the repository's own pre-existing
`tests/test_locations.py` suite (14 tests covering add/list/remove/
dedupe/id-stability) is executed and must pass unchanged. Both must hold
for this criterion to read MET.

## Non-goals

**Scope OUT (from the acceptance criteria's own Scope line), preserved
with their follow-up status:**
- **Per-user isolation** -- deferred, not dropped. The criteria's own
  negotiation history (the superseded criteria revisions) shows per-user
  scoping was explicitly proposed and then deliberately removed from this
  round's scope; the filer's issue (background only, unauthenticated) asks
  for per-login-session persistence, which is a superset this round does
  not build. A future round would need a new maintainer decision to bring
  per-user isolation back in scope.
- **Pin ordering** -- deferred. Not evaluated by this capsule; a future
  criterion would need to define what "order" means (insertion order,
  explicit user-set order, alphabetical) before it could be built or
  gated.
- **Multi-device sync** -- deferred. Out of scope entirely for a
  single-`data_dir`, single-server deployment model; would require a
  concept of device identity the codebase does not currently have.
- **UI changes beyond wiring the existing pin control to the store** --
  deferred. The client-side `layout.js` pin control's visual behavior is
  unchanged; only what it talks to on the backend is in scope.

**Delegated freedoms (implementer's choice, not asserted by the script):**
- **Route path and module/class names** -- the favorites HTTP route can
  live at any path and be backed by any Python module/class name; the
  verification script discovers new routes structurally rather than
  assuming a name.
- **Request shape for the path value on remove** -- query string or JSON
  body, per the criterion's own "or" -- either is accepted.
- **On-disk store filename/format** -- the criteria name no specific
  filename (unlike `locations.json`, which IS hardcoded for the sibling
  feature); any durable on-disk representation under `data_dir` that
  survives a fresh process satisfies AC-1/AC-2/AC-3.
- **Error-response shape/codes** -- the criteria do not mandate matching
  `/api/locations`'s `{"error": ..., "code": ...}` convention for
  favorites; the verification script only checks success-path effects and
  the specific negative-space cases the criteria themselves state (path-
  selective removal for AC-2; guard's nonexistent-id refusal for AC-4). It
  does not assert a particular behavior for removing a path that was never
  added (idempotent no-op vs. error), since the criteria are silent on
  that case.
- **Authentication behavior for the favorites route** -- the criteria do
  not specify anything beyond "through the backend API"; the script
  authenticates its own probe requests the same way the existing
  `/api/locations` tests do, but does not assert any particular auth
  policy is enforced for favorites specifically.
