"""Favorites backend-persistence gate probe helper.

Vendored beside DEFINITION.verify.sh and loaded from that fixed relative
path (the gate's invocation contract fixes the repo root as cwd, so
`.ai/capsule/favorites_probe.py` resolves directly). This is a PLAIN,
readable helper module -- never embedded/encoded in the gate script itself.

Invoked once per step, always as a FRESH OS process:

    FILEBROWSER_DATA_DIR=<dir> uv run --extra dev python3 \
        .ai/capsule/favorites_probe.py <mode> [args...]

The gate's bash orchestrator calls this multiple times across separate
`uv run` invocations so that cross-process durability (AC-1/AC-2/AC-3) is
proven by a REAL process boundary -- not two Python objects sharing one
interpreter.

Every invocation prints exactly one final line of the form

    RESULT: KEY=VALUE [KEY2=VALUE2 ...]

to stdout. All other output is free-form diagnostic text (never parsed).
Every foreseeable absence -- no favorites route exists yet, wrong request
shape, a 404, the whole app failing to import -- is caught and reported
through that RESULT line so the calling gate can convert it into a census
row. Only a genuine bug in invoking THIS helper (bad argv) exits non-zero.
"""

import os
import random
import string
import sys
import traceback
from pathlib import Path

# --- hermeticity: resolve the code under test from the INVOKING tree, ------
# --- never from an ambient install (see DEFINITION.md / task rider).    ---
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# The (method, path) pairs that exist at the pinned base SHA
# (48647a69db662dc321cf38abebadbcf5d0b6ee68). Used ONLY to recognize which
# routes are NEW -- i.e. added by a favorites patch -- never to assume the
# favorites route's own name/path, which the criteria deliberately leave to
# the implementer (Delegated freedom).
KNOWN_BASE_ROUTES = {
    ("HEAD", "/openapi.json"),
    ("GET", "/openapi.json"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/files"),
    ("GET", "/api/files/info"),
    ("GET", "/api/files/content"),
    ("GET", "/api/files/download"),
    ("POST", "/api/files/upload"),
    ("POST", "/api/files/mkdir"),
    ("PUT", "/api/files/content"),
    ("PUT", "/api/files/rename"),
    ("DELETE", "/api/files"),
    ("GET", "/api/locations"),
    ("POST", "/api/locations"),
    ("DELETE", "/api/locations/{location_id}"),
}


def _rand_token(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _build_client():
    from fastapi.testclient import TestClient
    from filebrowser.main import app
    from filebrowser.auth import require_auth

    app.dependency_overrides[require_auth] = lambda: "probe-" + _rand_token(6)
    return TestClient(app)


def _new_routes(app):
    found = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for m in methods:
            if (m, path) not in KNOWN_BASE_ROUTES:
                found.append((m, path))
    return found


def _contains_resolved_path(obj, target_resolved, _depth=0):
    if _depth > 6:
        return False
    if isinstance(obj, str):
        try:
            return Path(obj).resolve() == target_resolved
        except Exception:
            return False
    if isinstance(obj, dict):
        return any(_contains_resolved_path(v, target_resolved, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_resolved_path(v, target_resolved, _depth + 1) for v in obj)
    return False


def _count_resolved_path(obj, target_resolved, _depth=0):
    if _depth > 6:
        return 0
    if isinstance(obj, str):
        try:
            return 1 if Path(obj).resolve() == target_resolved else 0
        except Exception:
            return 0
    if isinstance(obj, dict):
        return sum(_count_resolved_path(v, target_resolved, _depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_resolved_path(v, target_resolved, _depth + 1) for v in obj)
    return 0


def _try_add(client, new_routes, path_value):
    """Try every newly-discovered POST route as the add-favorite surface.

    Returns (True, route_path) on the first route accepting it (2xx status).
    """
    candidates = [p for (m, p) in new_routes if m == "POST"]
    for route_path in candidates:
        try:
            resp = client.post(route_path, json={"path": path_value})
        except Exception as exc:
            print(f"  add candidate {route_path}: request raised {exc!r}")
            continue
        print(f"  add candidate {route_path}: status={resp.status_code} body={resp.text[:200]!r}")
        if 200 <= resp.status_code < 300:
            return True, route_path
    return False, None


def _try_list_contains(client, new_routes, target_resolved):
    """Try every newly-discovered GET route, looking for target_resolved
    anywhere in the (shape-agnostic) JSON response body."""
    candidates = [p for (m, p) in new_routes if m == "GET"]
    for route_path in candidates:
        try:
            resp = client.get(route_path)
        except Exception as exc:
            print(f"  list candidate {route_path}: request raised {exc!r}")
            continue
        print(f"  list candidate {route_path}: status={resp.status_code}")
        if resp.status_code != 200:
            continue
        try:
            body = resp.json()
        except Exception:
            continue
        if _contains_resolved_path(body, target_resolved):
            return True, route_path
    return False, None


def _count_in_list(client, new_routes, target_resolved):
    candidates = [p for (m, p) in new_routes if m == "GET"]
    for route_path in candidates:
        try:
            resp = client.get(route_path)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        try:
            body = resp.json()
        except Exception:
            continue
        count = _count_resolved_path(body, target_resolved)
        if count:
            return count, route_path
    return 0, None


def _try_remove(client, new_routes, path_value):
    """Try every newly-discovered DELETE route, trying BOTH query-string and
    JSON-body shapes for the path value (the criteria explicitly allow
    either)."""
    candidates = [p for (m, p) in new_routes if m == "DELETE"]
    for route_path in candidates:
        try:
            resp = client.request("DELETE", route_path, params={"path": path_value})
        except Exception as exc:
            print(f"  remove candidate {route_path} (query): request raised {exc!r}")
            resp = None
        if resp is not None:
            print(f"  remove candidate {route_path} (query): status={resp.status_code}")
            if 200 <= resp.status_code < 300:
                return True, route_path
        try:
            resp2 = client.request("DELETE", route_path, json={"path": path_value})
        except Exception as exc:
            print(f"  remove candidate {route_path} (body): request raised {exc!r}")
            continue
        print(f"  remove candidate {route_path} (body): status={resp2.status_code}")
        if 200 <= resp2.status_code < 300:
            return True, route_path
    return False, None


def mode_add(args):
    (path_value,) = args
    client = _build_client()
    new_routes = _new_routes(client.app)
    print(f"  new routes discovered: {new_routes}")
    ok, route = _try_add(client, new_routes, path_value)
    print(f"RESULT: ADD={'OK' if ok else 'FAIL'} ROUTE={route}")


def mode_list_check(args):
    (path_value,) = args
    target = Path(path_value).resolve()
    client = _build_client()
    new_routes = _new_routes(client.app)
    print(f"  new routes discovered: {new_routes}")
    present, route = _try_list_contains(client, new_routes, target)
    print(f"RESULT: PRESENT={'yes' if present else 'no'} ROUTE={route}")


def mode_remove(args):
    (path_value,) = args
    client = _build_client()
    new_routes = _new_routes(client.app)
    print(f"  new routes discovered: {new_routes}")
    ok, route = _try_remove(client, new_routes, path_value)
    print(f"RESULT: REMOVE={'OK' if ok else 'FAIL'} ROUTE={route}")


def mode_dedupe_check(args):
    """Single-process step: add several DIFFERENTLY-SPELLED-but-same-target
    variants of path_a (generated at runtime; at least one is NOT the
    criteria's own literal "./x" example), plus one genuinely distinct
    path_b, then read the list back (same process) and report counts so the
    caller can verify BOTH that dedup fired for path_a's variants AND that
    it did NOT over-fire against the unrelated path_b."""
    path_a, path_b = args
    real_a = Path(path_a).resolve()
    real_b = Path(path_b).resolve()
    client = _build_client()
    new_routes = _new_routes(client.app)
    print(f"  new routes discovered: {new_routes}")

    token = _rand_token(6)
    variants = [
        path_a,
        os.path.join(path_a, "."),
        os.path.join(path_a, token, ".."),
    ]
    add_results = []
    for v in variants:
        ok, _ = _try_add(client, new_routes, v)
        add_results.append(ok)
    print(f"  variant add results for path_a ({variants}): {add_results}")

    ok_b, _ = _try_add(client, new_routes, path_b)
    print(f"  add result for distinct path_b: {ok_b}")

    count_a, _ = _count_in_list(client, new_routes, real_a)
    present_b, _ = _try_list_contains(client, new_routes, real_b)

    print(
        f"RESULT: ADDED_A={'yes' if any(add_results) else 'no'} "
        f"COUNT_A={count_a} PRESENT_B={'yes' if present_b else 'no'}"
    )


def mode_dedupe_verify(args):
    """Fresh-process step: independently re-count path_a's resolved entries
    via a NEW OS process, proving the dedup outcome (not just the raw data)
    survives a process boundary."""
    (path_a,) = args
    real_a = Path(path_a).resolve()
    client = _build_client()
    new_routes = _new_routes(client.app)
    print(f"  new routes discovered: {new_routes}")
    count_a, route = _count_in_list(client, new_routes, real_a)
    print(f"RESULT: COUNT_A={count_a} ROUTE={route}")


def mode_http_guard(args):
    """AC-4 guard: exercise the EXISTING /api/locations HTTP surface
    end-to-end (add/list/delete), independent of the pytest suite the gate
    also runs, as a direct effect assertion through the public HTTP
    surface."""
    (real_dir,) = args
    client = _build_client()

    add_resp = client.post("/api/locations", json={"path": real_dir})
    if add_resp.status_code != 200:
        print(f"RESULT: GUARD_HTTP=FAIL STAGE=add STATUS={add_resp.status_code}")
        return
    entry = add_resp.json()
    loc_id = entry.get("id")

    list_resp = client.get("/api/locations")
    if list_resp.status_code != 200 or not any(
        e.get("id") == loc_id for e in list_resp.json()
    ):
        print(f"RESULT: GUARD_HTTP=FAIL STAGE=list STATUS={list_resp.status_code}")
        return

    del_resp = client.delete(f"/api/locations/{loc_id}")
    if del_resp.status_code != 200:
        print(f"RESULT: GUARD_HTTP=FAIL STAGE=delete STATUS={del_resp.status_code}")
        return

    list_resp2 = client.get("/api/locations")
    still_present = list_resp2.status_code == 200 and any(
        e.get("id") == loc_id for e in list_resp2.json()
    )
    if still_present:
        print("RESULT: GUARD_HTTP=FAIL STAGE=post-delete-check")
        return

    # Negative-space: removing a nonexistent numeric id must fail cleanly,
    # not silently "succeed" (guards the guard against a stubbed-out route).
    bogus_id = 900000 + random.randint(0, 99999)
    bogus_resp = client.delete(f"/api/locations/{bogus_id}")
    if bogus_resp.status_code == 200:
        print("RESULT: GUARD_HTTP=FAIL STAGE=nonexistent-delete-should-fail")
        return

    print("RESULT: GUARD_HTTP=OK")


MODES = {
    "add": mode_add,
    "list_check": mode_list_check,
    "remove": mode_remove,
    "dedupe_check": mode_dedupe_check,
    "dedupe_verify": mode_dedupe_verify,
    "http_guard": mode_http_guard,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        print(
            f"FATAL: usage: favorites_probe.py <mode> [args...]; modes={sorted(MODES)}",
            file=sys.stderr,
        )
        sys.exit(3)
    mode = sys.argv[1]
    args = sys.argv[2:]
    try:
        MODES[mode](args)
    except Exception as exc:
        # A broken favorites route (or a wholly broken app import) is an
        # OBSERVED absence, not an infrastructure failure: report it through
        # the same RESULT channel so the calling gate can record the
        # relevant AC as UNMET rather than aborting the whole round.
        traceback.print_exc()
        print(f"RESULT: ERROR={exc!r}")


if __name__ == "__main__":
    main()
