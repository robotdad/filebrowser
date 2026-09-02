set -euo pipefail

# Favorites backend-persistence gate (issue #26 / criteria comment 5420206455).
#
# Invocation contract: `bash .ai/capsule/DEFINITION.verify.sh`, cwd = repo
# root, no arguments. Writes .ai/census on EVERY run (green, red, partial):
# exactly one `AC-<n>: MET`/`AC-<n>: UNMET` row per ingested AC-ID, nothing
# else. Exits 0 only when every row is MET; exits 1 when any acceptance
# condition is honestly UNMET; exits >=2 ONLY for genuine infrastructure
# problems (missing system tooling), never for an absent feature.
#
# AC-1/AC-2/AC-3 require proof that survives a NEW OS PROCESS, so every
# probe step below is a SEPARATE `uv run` invocation of the vendored helper
# .ai/capsule/favorites_probe.py against the SAME FILEBROWSER_DATA_DIR --
# never two Python objects sharing one interpreter. The helper is a plain,
# readable sibling file (never embedded/encoded in this script) and it
# itself resolves the code under test from THIS invoking tree
# (sys.path.insert at the top of the helper) so the verdict tracks whatever
# tree the gate is run from, not an ambient install.
#
# "Through the backend API" (AC-1/AC-2/AC-3's own words) is proven via the
# actual FastAPI HTTP surface (TestClient against the real `app`), because
# that phrase's plain reading -- and the sibling `/api/locations` precedent
# this same criteria text points at for AC-3 -- is the HTTP route layer, not
# a bare service-class call. The exact route path/shape is NOT assumed: the
# helper auto-discovers every HTTP route absent at the pinned base SHA
# 48647a69db662dc321cf38abebadbcf5d0b6ee68 and tries each newly-introduced
# POST/GET/DELETE candidate, so an implementer's naming and request-shape
# choices (query string vs JSON body, route path) are fully delegated.
#
# Dependencies (fastapi/uvicorn/pydantic/etc) are NOT installed into the
# ambient environment: every probe runs through `uv run --extra dev`, which
# builds/uses a project-local .venv resolved from the repo's own committed
# pyproject.toml + uv.lock (offline-safe once uv's package cache is warm;
# no new external dependency is introduced beyond what the pinned tree
# already declares).

REPO_ROOT="$(pwd)"
CENSUS_FILE=".ai/census"
PROBE=".ai/capsule/favorites_probe.py"
ALL_AC_IDS=(AC-1 AC-2 AC-3 AC-4)

rm -f "$CENSUS_FILE"
declare -A AC_STATUS

mark_ac() { AC_STATUS["$1"]="$2"; }
fail_ac() { local id="$1"; shift; echo "UNMET $id: $*"; mark_ac "$id" "UNMET"; }
pass_ac() { local id="$1"; shift; echo "MET   $id: $*"; mark_ac "$id" "MET"; }

write_census() {
    for id in "${ALL_AC_IDS[@]}"; do
        if [[ -z "${AC_STATUS[$id]:-}" ]]; then
            echo "GATE INFRA ERROR: $id has no recorded verdict" >&2
            exit 2
        fi
    done
    : > "$CENSUS_FILE"
    for id in "${ALL_AC_IDS[@]}"; do
        echo "$id: ${AC_STATUS[$id]}" >> "$CENSUS_FILE"
    done
}
trap write_census EXIT

echo "=== Favorites backend-persistence gate ==="
echo "Repo root: $REPO_ROOT"
echo

# --- infrastructure prerequisites (genuine absence => exit >=2) -----------
command -v uv >/dev/null 2>&1 || {
    echo "GATE INFRA ERROR: 'uv' is not on PATH; cannot provision the project's own pinned Python environment." >&2
    exit 2
}
[[ -f "$PROBE" ]] || {
    echo "GATE INFRA ERROR: vendored probe helper missing at $PROBE" >&2
    exit 2
}
[[ -f pyproject.toml ]] || {
    echo "GATE INFRA ERROR: pyproject.toml missing; cannot resolve the project's environment." >&2
    exit 2
}

# Every probe call is direct invocation only (uv run python3 <script>) --
# no service boot chains, no containers, no network beyond uv's own
# package resolution against the committed lock (a no-op once warm).
run_probe() {
    # $1 = data_dir, remaining = probe argv
    local data_dir="$1"; shift
    FILEBROWSER_DATA_DIR="$data_dir" uv run --extra dev python3 "$PROBE" "$@"
}

extract_result() {
    # Pull the last "RESULT: ..." line from probe output (stdout+stderr
    # already captured by caller); never trusts the line's absence as
    # meaning success.
    grep '^RESULT:' | tail -1
}

TMP_ROOT="$(mktemp -d)"
cleanup_tmp() { rm -rf "$TMP_ROOT"; }
trap 'cleanup_tmp; write_census' EXIT

rand_name() {
    # RC-8: synthetic witness names are born at gate RUNTIME, never fixed
    # literals, and carry NO domain vocabulary from the criteria's subject
    # space (no "favorite"/"location"/"pin" tokens) -- neutral alphanumerics
    # only. `mktemp`'s own randomization already satisfies this; this
    # wrapper exists so every call site is visibly uniform.
    mktemp -u "XXXXXXXXXX"
}

# ===========================================================================
# AC-1: add through backend API persists across a NEW OS process
# ===========================================================================
echo "--- AC-1 ---"
AC1_DATA="$TMP_ROOT/$(rand_name)"
AC1_DATA_OTHER="$TMP_ROOT/$(rand_name)"
AC1_DIR="$TMP_ROOT/$(rand_name)"
mkdir -p "$AC1_DATA" "$AC1_DATA_OTHER" "$AC1_DIR"

set +e
ADD_OUT="$(run_probe "$AC1_DATA" add "$AC1_DIR" 2>&1)"
ADD_RC=$?
set -e
echo "$ADD_OUT"
if [[ $ADD_RC -ge 2 ]]; then
    echo "GATE INFRA ERROR: probe process itself failed (rc=$ADD_RC) invoking 'add'" >&2
    exit 2
fi
ADD_LINE="$(echo "$ADD_OUT" | extract_result)"

set +e
LIST_OUT="$(run_probe "$AC1_DATA" list_check "$AC1_DIR" 2>&1)"
LIST_RC=$?
set -e
echo "$LIST_OUT"
if [[ $LIST_RC -ge 2 ]]; then
    echo "GATE INFRA ERROR: probe process itself failed (rc=$LIST_RC) invoking 'list_check'" >&2
    exit 2
fi
LIST_LINE="$(echo "$LIST_OUT" | extract_result)"

# A different, independently configured data_dir must not see the favorite.
# This distinguishes a store genuinely scoped by data_dir from a global file
# shared by every server instance while still leaving filename and format free.
set +e
LIST_OTHER_OUT="$(run_probe "$AC1_DATA_OTHER" list_check "$AC1_DIR" 2>&1)"
LIST_OTHER_RC=$?
set -e
echo "$LIST_OTHER_OUT"
if [[ $LIST_OTHER_RC -ge 2 ]]; then
    echo "GATE INFRA ERROR: probe process itself failed (rc=$LIST_OTHER_RC) invoking cross-data_dir 'list_check'" >&2
    exit 2
fi
LIST_OTHER_LINE="$(echo "$LIST_OTHER_OUT" | extract_result)"

if [[ "$ADD_LINE" == *"ADD=OK"* ]] \
    && [[ "$LIST_LINE" == *"PRESENT=yes"* ]] \
    && [[ "$LIST_OTHER_LINE" == *"PRESENT=no"* ]]; then
    pass_ac AC-1 "add via HTTP API in process 1, present via HTTP API in a fresh process 2 against the same data_dir ($AC1_DATA), and absent via HTTP API in a fresh process 3 against a different data_dir ($AC1_DATA_OTHER)"
else
    fail_ac AC-1 "add='$ADD_LINE' same-data_dir-read='$LIST_LINE' cross-data_dir-read='$LIST_OTHER_LINE' (need ADD=OK, PRESENT=yes under the same data_dir, and PRESENT=no under a different data_dir)"
fi

# ===========================================================================
# AC-2: remove through backend API, identified by PATH VALUE, persists
# across a NEW OS process
# ===========================================================================
echo "--- AC-2 ---"
AC2_DATA="$TMP_ROOT/$(rand_name)"
AC2_DIR_A="$TMP_ROOT/$(rand_name)"
AC2_DIR_B="$TMP_ROOT/$(rand_name)"
mkdir -p "$AC2_DATA" "$AC2_DIR_A" "$AC2_DIR_B"

set +e
ADD2A_OUT="$(run_probe "$AC2_DATA" add "$AC2_DIR_A" 2>&1)"; ADD2A_RC=$?
set -e
echo "$ADD2A_OUT"
[[ $ADD2A_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$ADD2A_RC on setup add (A) for AC-2" >&2; exit 2; }
ADD2A_LINE="$(echo "$ADD2A_OUT" | extract_result)"

set +e
ADD2B_OUT="$(run_probe "$AC2_DATA" add "$AC2_DIR_B" 2>&1)"; ADD2B_RC=$?
set -e
echo "$ADD2B_OUT"
[[ $ADD2B_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$ADD2B_RC on setup add (B) for AC-2" >&2; exit 2; }
ADD2B_LINE="$(echo "$ADD2B_OUT" | extract_result)"

if [[ "$ADD2A_LINE" != *"ADD=OK"* ]] || [[ "$ADD2B_LINE" != *"ADD=OK"* ]]; then
    fail_ac AC-2 "cannot set up (no working add surface): A='$ADD2A_LINE' B='$ADD2B_LINE'"
else
    # PRESCRIPTION COMPLIANCE (prior-round finding): a FIFO/positional fake
    # (e.g. "always remove whichever favorite was added first" via
    # state["favorites"].pop(0), ignoring the `path` argument entirely)
    # could coincidentally green a gate that always targeted the
    # first-added entry -- the removal target never varied, so "always
    # remove index 0" and "genuinely match by path" were indistinguishable.
    # Fix applied verbatim per the critique's own "better" option: WHICH of
    # A/B gets removed is now decided AT GATE RUNTIME by a coin flip, never
    # a fixed literal choice. Across repeated gate runs this exercises BOTH
    # "remove the first-added" and "remove the second-added" as the correct
    # answer, so neither a pop(0) (oldest-first) nor a pop(-1)/pop()
    # (newest-first) positional fake can satisfy the assertions on both
    # branches -- only genuine path-value matching in remove() does.
    if (( RANDOM % 2 == 0 )); then
        REMOVE_TARGET="$AC2_DIR_A"; REMOVE_TARGET_LABEL="A (first-added)"
        SURVIVOR="$AC2_DIR_B"; SURVIVOR_LABEL="B (second-added)"
    else
        REMOVE_TARGET="$AC2_DIR_B"; REMOVE_TARGET_LABEL="B (second-added)"
        SURVIVOR="$AC2_DIR_A"; SURVIVOR_LABEL="A (first-added)"
    fi
    echo "  AC-2 removal target chosen at runtime: $REMOVE_TARGET_LABEL; expected survivor: $SURVIVOR_LABEL"

    set +e
    REMOVE_OUT="$(run_probe "$AC2_DATA" remove "$REMOVE_TARGET" 2>&1)"; REMOVE_RC=$?
    set -e
    echo "$REMOVE_OUT"
    [[ $REMOVE_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$REMOVE_RC on 'remove' for AC-2" >&2; exit 2; }
    REMOVE_LINE="$(echo "$REMOVE_OUT" | extract_result)"

    set +e
    LIST_TARGET_OUT="$(run_probe "$AC2_DATA" list_check "$REMOVE_TARGET" 2>&1)"; LIST_TARGET_RC=$?
    set -e
    echo "$LIST_TARGET_OUT"
    [[ $LIST_TARGET_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$LIST_TARGET_RC on post-remove list_check(target) for AC-2" >&2; exit 2; }
    LIST_TARGET_LINE="$(echo "$LIST_TARGET_OUT" | extract_result)"

    # NEGATIVE-SPACE PROBE licensed directly by AC-2's own text ("identified
    # by its path value"): removing the runtime-chosen target must be
    # SELECTIVE -- the sibling favorite that was NOT targeted this run must
    # survive untouched, regardless of which of the two was added first.
    # This catches a stub that "removes" by clearing the whole store, or by
    # position rather than path, without inventing an error-handling
    # requirement AC-2 never states (removing a never-added path's expected
    # behavior -- fail vs. no-op -- is genuinely undelegated by the
    # criteria and is NOT asserted here).
    set +e
    LIST_SURVIVOR_OUT="$(run_probe "$AC2_DATA" list_check "$SURVIVOR" 2>&1)"; LIST_SURVIVOR_RC=$?
    set -e
    echo "$LIST_SURVIVOR_OUT"
    [[ $LIST_SURVIVOR_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$LIST_SURVIVOR_RC on post-remove list_check(survivor) for AC-2" >&2; exit 2; }
    LIST_SURVIVOR_LINE="$(echo "$LIST_SURVIVOR_OUT" | extract_result)"

    if [[ "$REMOVE_LINE" == *"REMOVE=OK"* ]] \
        && [[ "$LIST_TARGET_LINE" == *"PRESENT=no"* ]] \
        && [[ "$LIST_SURVIVOR_LINE" == *"PRESENT=yes"* ]]; then
        pass_ac AC-2 "path-identified remove of the RUNTIME-CHOSEN target ($REMOVE_TARGET_LABEL) in process 1, absence of that target AND continued presence of the non-targeted sibling ($SURVIVOR_LABEL) both confirmed via HTTP API in fresh processes (data_dir=$AC2_DATA) -- proves disk-backed, path-selective removal that cannot be satisfied by insertion-order position alone"
    else
        fail_ac AC-2 "removal_target=$REMOVE_TARGET_LABEL remove='$REMOVE_LINE' fresh-process target-absence='$LIST_TARGET_LINE' fresh-process survivor-present='$LIST_SURVIVOR_LINE'"
    fi
fi

# ===========================================================================
# AC-3: idempotent add via RESOLVED/CANONICALIZED path equality
# (oracle: filebrowser/services/locations.py's own Path(...).resolve()
# equality rule, exercised over runtime-generated path spellings, not just
# the criteria's own "./x" example)
# ===========================================================================
echo "--- AC-3 ---"
AC3_DATA="$TMP_ROOT/$(rand_name)"
AC3_DIR_A="$TMP_ROOT/$(rand_name)"
AC3_DIR_B="$TMP_ROOT/$(rand_name)"
mkdir -p "$AC3_DATA" "$AC3_DIR_A" "$AC3_DIR_B"

set +e
DEDUPE1_OUT="$(run_probe "$AC3_DATA" dedupe_check "$AC3_DIR_A" "$AC3_DIR_B" 2>&1)"; DEDUPE1_RC=$?
set -e
echo "$DEDUPE1_OUT"
[[ $DEDUPE1_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$DEDUPE1_RC on dedupe_check for AC-3" >&2; exit 2; }
DEDUPE1_LINE="$(echo "$DEDUPE1_OUT" | extract_result)"

set +e
DEDUPE2_OUT="$(run_probe "$AC3_DATA" dedupe_verify "$AC3_DIR_A" 2>&1)"; DEDUPE2_RC=$?
set -e
echo "$DEDUPE2_OUT"
[[ $DEDUPE2_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$DEDUPE2_RC on dedupe_verify for AC-3" >&2; exit 2; }
DEDUPE2_LINE="$(echo "$DEDUPE2_OUT" | extract_result)"

if [[ "$DEDUPE1_LINE" == *"ADDED_A=yes"* ]] \
    && [[ "$DEDUPE1_LINE" == *"COUNT_A=1"* ]] \
    && [[ "$DEDUPE1_LINE" == *"PRESENT_B=yes"* ]] \
    && [[ "$DEDUPE2_LINE" == *"COUNT_A=1"* ]]; then
    pass_ac AC-3 "3 differently-spelled resolved-equal variants of one path collapsed to exactly 1 stored entry, a genuinely distinct path was NOT merged into it, and the count-of-1 survived a fresh OS process (data_dir=$AC3_DATA)"
else
    fail_ac AC-3 "same-process result='$DEDUPE1_LINE' fresh-process count='$DEDUPE2_LINE' (need ADDED_A=yes, COUNT_A=1 both times, PRESENT_B=yes)"
fi

# ===========================================================================
# AC-4 [guard]: existing /api/locations feature (add/list/remove, on-disk
# locations.json) continues to work unchanged. Probed two ways: (a) direct
# HTTP-level exercise of the three verbs plus a negative-space check, (b)
# the repo's OWN pre-existing pytest suite for LocationsService (free
# coverage encoding real, already-negotiated expectations).
# ===========================================================================
echo "--- AC-4 [guard] ---"
AC4_LOC_DATA="$TMP_ROOT/$(rand_name)"
AC4_REAL_DIR="$TMP_ROOT/$(rand_name)"
mkdir -p "$AC4_LOC_DATA" "$AC4_REAL_DIR"

set +e
GUARD_HTTP_OUT="$(run_probe "$AC4_LOC_DATA" http_guard "$AC4_REAL_DIR" 2>&1)"; GUARD_HTTP_RC=$?
set -e
echo "$GUARD_HTTP_OUT"
[[ $GUARD_HTTP_RC -lt 2 ]] || { echo "GATE INFRA ERROR: probe rc=$GUARD_HTTP_RC on http_guard for AC-4" >&2; exit 2; }
GUARD_HTTP_LINE="$(echo "$GUARD_HTTP_OUT" | extract_result)"

GUARD_PYTEST_OK=false
if [[ -f "tests/test_locations.py" ]]; then
    set +e
    PYTEST_OUT="$(uv run --extra dev python3 -m pytest tests/test_locations.py -q 2>&1)"; PYTEST_RC=$?
    set -e
    echo "$PYTEST_OUT"
    if [[ $PYTEST_RC -eq 0 ]]; then
        GUARD_PYTEST_OK=true
    elif [[ $PYTEST_RC -ge 2 ]] && ! echo "$PYTEST_OUT" | grep -qE "failed|error"; then
        # pytest itself uses 2 for "test collection error" too, which IS a
        # feature-observation (broken import chain), not gate infra -- only
        # escalate to infra failure if pytest never even ran (e.g. module
        # not found for pytest itself).
        if echo "$PYTEST_OUT" | grep -qi "no module named pytest"; then
            echo "GATE INFRA ERROR: pytest is not resolvable via 'uv run --extra dev' from this tree" >&2
            exit 2
        fi
    fi
else
    echo "tests/test_locations.py not present in this tree -- relying on the direct HTTP guard probe only."
fi

if [[ "$GUARD_HTTP_LINE" == *"GUARD_HTTP=OK"* ]] && [[ "$GUARD_PYTEST_OK" == "true" ]]; then
    pass_ac AC-4 "direct HTTP add/list/delete + negative-space (bad id refused) all behave correctly, AND the repo's own tests/test_locations.py suite passes unchanged"
elif [[ "$GUARD_HTTP_LINE" == *"GUARD_HTTP=OK"* ]] && [[ ! -f "tests/test_locations.py" ]]; then
    pass_ac AC-4 "direct HTTP add/list/delete + negative-space (bad id refused) all behave correctly (tests/test_locations.py absent in this tree, HTTP probe is the sole evidence)"
else
    fail_ac AC-4 "http_guard='$GUARD_HTTP_LINE' pytest_suite_passed=$GUARD_PYTEST_OK"
fi

# ===========================================================================
# Summary + rc/census coherence
# ===========================================================================
echo
echo "=== Census ==="
for id in "${ALL_AC_IDS[@]}"; do
    echo "$id: ${AC_STATUS[$id]}"
done

ANY_UNMET=false
for id in "${ALL_AC_IDS[@]}"; do
    if [[ "${AC_STATUS[$id]}" == "UNMET" ]]; then
        ANY_UNMET=true
    fi
done

if [[ "$ANY_UNMET" == "true" ]]; then
    echo "Result: SOME ACCEPTANCE CRITERIA UNMET"
    exit 1
else
    echo "Result: ALL ACCEPTANCE CRITERIA MET"
    exit 0
fi
