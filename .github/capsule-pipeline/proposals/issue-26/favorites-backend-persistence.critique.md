The gate can currently be greened by a favorites store that completely ignores which `data_dir` it was configured with -- one shared global file services every server instance -- so add a probe that adds a favorite under one `data_dir` and confirms it is ABSENT when read back through a second, differently-configured `data_dir`, before this capsule ships.

## Evidence: executed counterexample against the current tree

`.ai/hypothesis_v.patch` (this round's VOID/stub leg) implements `FavoritesService`:

```python
_SHARED_STORE = Path(tempfile.gettempdir()) / "filebrowser_favorites_shared.json"

class FavoritesService:
    def __init__(self, data_dir: Path | None = None) -> None:
        # data_dir is accepted for interface compatibility ... but is never
        # consulted -- the backing file is fixed regardless of it.
        self._store = _SHARED_STORE
```

The patch's own comment names the defect plainly, but per the injection-hardening rule that comment is untrusted prose, not evidence -- so I verified it by execution, not by reading the claim. I applied `.ai/hypothesis_v.patch` to the pinned base tree (`git apply .ai/hypothesis_v.patch`, `git status --short` confirmed only the expected 3 files touched), then ran two separate `uv run` invocations of the vendored `.ai/capsule/favorites_probe.py` against **two different `FILEBROWSER_DATA_DIR` values**:

```
=== add dirA under data_dir d1 ===
RESULT: ADD=OK ROUTE=/api/favorites

=== list_check dirA under data_dir d2 (DIFFERENT data_dir) ===
RESULT: PRESENT=yes ROUTE=/api/favorites
```

A favorite added while the server was configured with `data_dir=d1` is visible to a process configured with the completely unrelated `data_dir=d2`. I then reverted (`git checkout -- filebrowser/main.py`, removed the two new files, `git status --short` empty, `git rev-parse HEAD` back to `48647a69db662dc321cf38abebadbcf5d0b6ee68`) before re-testing the two honest legs the same way:

```
# hypothesis.patch (leg A) -- same two-data_dir probe
RESULT: ADD=OK ROUTE=/api/favorites          (data_dir=d1)
RESULT: PRESENT=no ROUTE=None                (data_dir=d2, DIFFERENT dir -- correctly absent)
```

`hypothesis_b.patch` (leg B) and `rival.patch` both thread `settings.data_dir` into every store call (`FavoritesService(settings.data_dir)` / `load_favorites(settings.data_dir)`, confirmed by reading both diffs) with no global/shared path anywhere, so they behave the same correct way structurally. I reverted cleanly again afterward (`git status --short` empty, HEAD at the pinned base SHA).

## Why this is the single most important finding

This is the under-specified-direction question stated in my brief, answered concretely: would the laziest change that greens this gate -- a single hardcoded `/tmp` file shared by every server instance, `data_dir` accepted and dropped -- be one I'd ship as the feature? No: it means two independently configured filebrowser deployments (or, more mundanely, two different `FILEBROWSER_DATA_DIR` test/staging setups on the same machine) silently share and clobber each other's favorites, which directly contradicts what `data_dir` is *for* and what DEFINITION.md itself claims ("written to disk under the server's `data_dir`"). AC-1's own text says persistence must hold for "a new OS process ... pointed at the SAME data_dir" -- the entire phrase presupposes `data_dir` is the scoping key, exactly the way the sibling `LocationsService` already treats it (`data_dir / "locations.json"`, confirmed in `filebrowser/services/locations.py`). The current gate only ever exercises ONE `data_dir` value per AC block, so "genuinely scoped by data_dir" and "ignores data_dir entirely" are indistinguishable to it -- precisely the same shape of gap the prior round found and fixed for AC-2's removal target (a single fixed scenario letting a fake coincide with the correct answer on every run), just on a different axis.

**Stub classification (required, since `stub_greened=true` this round):** I read the diff, not the self-report. `FavoritesService.__init__` still accepts and stores `self._data_dir = data_dir` for interface compatibility, and the constructor signature, docstring shape, and route/service split are otherwise indistinguishable from the honest legs -- a reviewer scanning the PR for "does it accept data_dir like LocationsService" would see yes. Only tracing `_load`/`_save` to confirm they read `self._data_dir` rather than a module-level constant reveals the fake, which is exactly the kind of thing an unhurried review catches but a quick one does not. Per the "when in doubt, reviewer-plausible" default, I classify this **REVIEWER-PLAUSIBLE -- BLOCKS**, not sabotage-class.

**The fix is narrow:** add, to each of AC-1/AC-2/AC-3's blocks (or as one shared new check), a step that adds a favorite under `data_dir=X`, then reads it back via a fresh process pointed at a DIFFERENT, freshly-created `data_dir=Y`, and asserts the favorite is **absent** there (mirroring the selectivity check AC-2 already does for sibling entries, just across the data_dir axis instead of the path axis). This traces directly to AC-1's own "pointed at the same data_dir" language and to DEFINITION.md's existing "written to disk under the server's data_dir" claim -- it is not a new invented demand, and both honest legs and the rival already satisfy it for free (verified above), so it will not turn a correct-but-differently-shaped implementation red.

## Prescription follow-through (prior round)

`.ai/gate.log` opens with `CRITIQUE ITERATE:` prescribing that AC-2's removal target be chosen at gate runtime (coin flip) rather than always removing the first-added entry. I read the current `DEFINITION.verify.sh` AC-2 block directly: it now does `if (( RANDOM % 2 == 0 )); then REMOVE_TARGET=$AC2_DIR_A ... else REMOVE_TARGET=$AC2_DIR_B ...`, with both the target and the expected survivor varying accordingly, and an explanatory comment crediting the prescription verbatim. This is a genuine, applied fix, not a rebuttal or a re-emission of unchanged bytes -- prescription compliance is satisfied for this item.

## Everything else checked out

- **Articulate-RED**: `.ai/verify-red.log` shows AC-1/AC-2/AC-3 UNMET, AC-4 MET at the pinned base SHA (`git rev-parse HEAD` in the workspace matches `.ai/base-sha` = `48647a69db662dc321cf38abebadbcf5d0b6ee68`), and the declared `red_signal: AC-1: UNMET` in `DEFINITION.md` frontmatter whole-line-matches a row of `.ai/census-red`.
- **criteria_digest** in the frontmatter (`7ef8d2917d...`) matches `sha256sum .ai/criteria.md` exactly; `.ai/criteria.md` reads as the untouched maintainer text.
- **Non-vacuity elsewhere / no over-specification**: both honest legs green the gate with genuinely different module shapes (`favorites.py` route+service pair with dict-of-favorites vs. a flat-list `favorites_store.py` module, atomic temp-file writes, filename `pinned.json` vs `favorites.json`) -- confirms the gate does not over-demand module placement, filenames, or decomposition. `identical_ab=false` in the ledger is consistent.
- **Rival evidence**: `rival.patch` greens the gate (`rival_rc=0`) and, per the asymmetric-weighting rule, a rival pass proves little on its own -- treated as one non-contradicting data point, not clearance.
- **Delegated freedoms honored**: route path/shape, request body vs. query string, error codes, on-disk filename all genuinely left open and exercised differently by the two honest legs.
- **AC-4 guard**: exercised via direct HTTP effect assertions AND the repo's own pre-existing `tests/test_locations.py` (14 tests) -- traces to the guard criterion's text.
- **No inert probes**: `inert_acs` is empty in the ledger.
- **No ambient-install contamination**: `.ai/findings/ambient-install.md` records a stale editable install removed before measurement; `hermetic: proven` in the ledger, and my own counterexample runs left `git status --short` clean before and after each application/reversion.
- **No void-adjudication fork this round**: `.ai/void-adjudication` does not exist -- ordinary judgment round, FEATURE-EQUIVALENT-STUB path does not apply.
- **No blocking spec ambiguity**: AC-1/2/3/4 read as concrete, testable, internally consistent, with an explicit named oracle (`Path(...).resolve()`) for AC-3; the data_dir gap above is a gate-tightening question, not a criteria fork -- it does not warrant `.ai/questions/blocking.md`.

VERDICT: ITERATE
