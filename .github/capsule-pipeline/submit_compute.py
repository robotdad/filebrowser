#!/usr/bin/env python3
r"""Self-contained compute-backend submit client for CI (bearer token).

Purpose
-------
Submit a dot-graph "custom" pipeline run to a hosted compute backend from a
GitHub Actions runner, poll it to a terminal state, auto-answer any human-gate
input requests, and pull the pipeline's `capsule_out` artifacts + event log
back to the runner filesystem.

Design
------
stdlib-only, so it runs on a bare runner with no pip install. It reads a
pre-issued BEARER TOKEN from the environment. HTTP contract:
  POST /api/instances  {"resolver","input":{"pipeline":...}}  -> {id/instance_id}
  POST /api/uploads    (multipart)                            -> {"handle"}
  GET  /api/instances/{id}                                    -> {"status"}
  POST /api/instances/{id}/input-requests/{rid}  {"response","text"}
  GET  /api/instances/{id}/events

Auth contract
-------------
  COMPUTE_URL    e.g. https://<compute-backend-host>   (or --url)
  COMPUTE_TOKEN  bearer token, sent as `Authorization: Bearer <token>`
NOTE (see docs/designs/gh-actions-hosted-compute.md): if the token is a
short-lived access token it expires quickly; a static service token or a
per-job-minted token is required for durable automation.

Usage
-----
  submit_compute.py \
      --pipeline custom \
      --params-file params.json \        # the `input` params (dot_content, workspace_repo, base_sha, ...)
      --upload issue_file=./issue.md \   # 0+; uploads file, sets input[<name>]=<handle>
      --out ./out \                      # capsule_out data tree + events.json land here
      --data-subpath capsule \           # which /data/<subpath> tree to pull back
      [--gate-answer K] [--poll-interval 10] [--timeout 21600]

Exit codes: 0 = instance reached `completed`; 1 = terminal non-success or error;
2 = auth failure; 3 = network failure. The resolved instance_id is written to
stdout (last line) and to <out>/instance_id.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import NoReturn

# Terminal statuses the standard terminal statuses. `awaiting_input`
# is terminal-for-watch but NOT terminal-for-us: in unattended CI we answer the
# gate and keep polling.
_SUCCESS = "completed"
_TERMINAL = frozenset({"completed", "failed", "error", "cancelled", "canceled"})
_AWAITING = "awaiting_input"


def _die(msg: str, code: int = 1) -> NoReturn:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


class Compute:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    # --- low-level request (JSON) ----
    def _request(
        self, method: str, path: str, data: dict | None = None, timeout: float = 60
    ) -> tuple[int, dict | None, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        body: bytes | None = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            self.url + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Network/timeout blip -> return a sentinel (code 0) so pollers can
            # retry. Fail-fast callers (create/upload) still treat this as an
            # error because parsed is None.
            return 0, None, f"network error: {exc}"
        if status == 401:
            _die(
                f"401 from {path}: the bearer token was rejected (stale/expired/wrong "
                "audience). Refresh COMPUTE_TOKEN.",
                2,
            )
        try:
            return status, (json.loads(raw) if raw else None), raw
        except json.JSONDecodeError:
            return status, None, raw

    def _get_bytes(self, path: str, timeout: float = 300) -> tuple[int, bytes]:
        req = urllib.request.Request(
            self.url + path,
            headers={"Authorization": f"Bearer {self.token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            _die(f"could not reach {self.url}{path}: {exc.reason}", 3)

    # --- uploads: POST /api/uploads (multipart) -> {"handle": ...} -----------
    def upload(self, path: Path, timeout: float = 300) -> str:
        boundary = "----submitcompute" + uuid.uuid4().hex
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        tail = f"\r\n--{boundary}--\r\n".encode()
        body = head + path.read_bytes() + tail
        req = urllib.request.Request(
            self.url + "/api/uploads",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            _die(
                f"upload of {path} failed ({exc.code}): {exc.read().decode(errors='replace')}"
            )
        except urllib.error.URLError as exc:
            _die(f"could not reach {self.url}: {exc.reason}", 3)
        handle = parsed.get("handle")
        if not handle:
            _die(f"upload of {path} returned no handle: {parsed}")
        print(f"uploaded {path} -> {handle}", file=sys.stderr)
        return handle

    # --- submit: POST /api/instances ----------------------------------------
    def create(self, resolver: str, input_data: dict) -> str:
        status, parsed, raw = self._request(
            "POST", "/api/instances", data={"resolver": resolver, "input": input_data}
        )
        if status >= 400 or not parsed:
            _die(f"create instance failed (HTTP {status}): {raw.strip()}")
        # InstanceCreateRequest is extra=ignore server-side; the response id key
        # has been seen as both `id` and `instance_id` -- accept either.
        instance_id = parsed.get("instance_id") or parsed.get("id")
        if not instance_id:
            _die(f"create returned no instance id: {parsed}")
        return str(instance_id)

    def status(self, instance_id: str) -> dict | None:
        # Returns the status dict, or None on a TRANSIENT failure (5xx / network
        # blip / empty body) so the poll loop can retry instead of aborting a
        # live run. Only a 404 (instance genuinely gone) is fatal here; 401 is
        # handled fatally inside _request.
        code, parsed, raw = self._request("GET", f"/api/instances/{instance_id}")
        if code == 404:
            _die(f"instance {instance_id} not found (HTTP 404): {raw.strip()}")
        if parsed is not None and code < 400:
            return parsed
        print(
            f"WARN: transient status poll failure (HTTP {code}): {raw.strip()[:160]}",
            file=sys.stderr,
        )
        return None

    # --- human-gate auto-answer (analog of `--on-human-gate auto-approve`) ---
    def answer_open_gates(self, instance_id: str, text: str) -> int:
        code, parsed, _ = self._request(
            "GET", f"/api/instances/{instance_id}/input-requests"
        )
        if code >= 400 or not isinstance(parsed, list):
            return 0
        answered = 0
        for reqobj in parsed:
            if reqobj.get("status") == "answered":
                continue
            rid = reqobj.get("id") or reqobj.get("request_id")
            if not rid:
                continue
            acode, _, araw = self._request(
                "POST",
                f"/api/instances/{instance_id}/input-requests/{rid}",
                data={"response": text, "text": text},
            )
            if acode in (200, 204):
                print(f"auto-answered gate {rid} with '{text}'", file=sys.stderr)
                answered += 1
            else:
                print(
                    f"WARN: gate {rid} answer HTTP {acode}: {araw.strip()}",
                    file=sys.stderr,
                )
        return answered

    def events_raw(self, instance_id: str) -> bytes:
        _, body = self._get_bytes(f"/api/instances/{instance_id}/events")
        return body

    # --- data retrieval (proven contract, docs/capsule-out-probe.md) ----------
    # GET /data-tree lists paths under the served data root; each FILE is fetched
    # at GET /data/<rel>, where <rel> already includes the <subpath> prefix
    # (e.g. capsule/<id>.verify.sh). We strip that prefix when writing locally so
    # $OUT holds the pair at top level (and $OUT/ai/... beneath it).
    def fetch_data(self, instance_id: str, subpath: str, out: Path) -> int:
        code, parsed, raw = self._request(
            "GET", f"/api/instances/{instance_id}/data-tree"
        )
        print(f"data-tree HTTP {code}: {raw[:3000]}", file=sys.stderr)
        rels = _flatten_tree(parsed) if code < 400 and parsed is not None else []
        pref = subpath.strip("/") + "/"
        wanted = [r for r in rels if r.startswith(pref)]
        if not wanted:
            print(
                f"WARN: no files under data/{subpath} (tree listed {len(rels)} path(s): "
                f"{rels[:12]}). If the tree is empty the pipeline wrote no capsule_out.",
                file=sys.stderr,
            )
            # Diagnostic: dump the node status JSONs that carry the reason a run
            # rejected/short-circuited (bad_input, setup, the folder node).
            for rel in rels:
                if any(k in rel for k in ("bad_input", "setup", "RunWorkspaceGraph")):
                    sc, blob = self._get_bytes(
                        f"/api/instances/{instance_id}/data/{rel}"
                    )
                    if sc < 400:
                        print(
                            f"--- {rel} ---\n{blob.decode('utf-8', 'replace')[:2500]}",
                            file=sys.stderr,
                        )
            return 0
        fetched = 0
        for rel in wanted:
            scode, blob = self._get_bytes(f"/api/instances/{instance_id}/data/{rel}")
            if scode >= 400:
                print(f"WARN: fetch data/{rel} HTTP {scode}", file=sys.stderr)
                continue
            dest = out / rel[len(pref) :]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            fetched += 1
        print(
            f"retrieved {fetched} file(s) under data/{subpath} -> {out}",
            file=sys.stderr,
        )
        return fetched


def _flatten_tree(node: object, prefix: str = "") -> list[str]:
    """Tolerant flattener -> relative FILE paths. Accepts a list of path strings,
    or nested {name|path, type, children} nodes. A node carrying a full `path`
    (contains '/') is trusted as-is rather than re-prefixed, so a tree that
    already stores full paths does not get doubled (capsule/capsule/...)."""
    out: list[str] = []
    if isinstance(node, list):
        for item in node:
            out.extend(_flatten_tree(item, prefix))
    elif isinstance(node, str):
        out.append(node.lstrip("/"))
    elif isinstance(node, dict):
        path = node.get("path")
        if path and "/" in path.strip("/"):
            rel = path.lstrip("/")  # full path already; don't re-prefix
        else:
            rel = f"{prefix}{path or node.get('name') or ''}".lstrip("/")
        children = node.get("children")
        is_dir = node.get("type") == "dir" or children is not None
        if children:
            base = rel + "/" if rel and not rel.endswith("/") else rel
            out.extend(_flatten_tree(children, base))
        elif rel and not is_dir:
            out.append(rel)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Submit a the backend dot-graph run (bearer auth)."
    )
    ap.add_argument("--url", default=os.environ.get("COMPUTE_URL", ""))
    ap.add_argument("--resolver", default="dot-graph")
    ap.add_argument("--pipeline", default="custom")
    ap.add_argument(
        "--params-file",
        required=True,
        help="JSON of the `input` params (minus pipeline)",
    )
    ap.add_argument(
        "--upload",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="upload a file and set input[NAME]=<handle>; repeatable",
    )
    ap.add_argument(
        "--out", required=True, help="dir to write ONLY retrieved capsule_out data"
    )
    ap.add_argument(
        "--meta-dir",
        default="",
        help="dir for run metadata (events.json, final-status.json, instance_id.txt); "
        "keep it OUT of --out so downstream capsule-artifact secret gates don't scan it. "
        "Defaults to --out.",
    )
    ap.add_argument(
        "--data-subpath", default="capsule", help="/data/<subpath> tree to pull back"
    )
    ap.add_argument(
        "--gate-answer",
        default=os.environ.get("GATE_ANSWER", "A"),
        help="text to auto-answer any human-gate with (default 'A'; RISK: calibrate per graph)",
    )
    ap.add_argument("--poll-interval", type=float, default=10.0)
    ap.add_argument(
        "--timeout", type=float, default=21600.0, help="max seconds to wait (0=none)"
    )
    args = ap.parse_args()

    if not args.url:
        _die("no the backend URL: set COMPUTE_URL or pass --url", 2)
    token = os.environ.get("COMPUTE_TOKEN", "")
    if not token:
        _die("no bearer token: set COMPUTE_TOKEN", 2)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = Path(args.meta_dir) if args.meta_dir else out
    meta.mkdir(parents=True, exist_ok=True)
    input_params = json.loads(Path(args.params_file).read_text())

    client = Compute(args.url, token)

    # Phase 1: uploads (issue_file etc.) -> handles substituted into params.
    for spec in args.upload:
        if "=" not in spec:
            _die(f"--upload must be NAME=PATH, got {spec!r}")
        name, _, p = spec.partition("=")
        input_params[name] = client.upload(Path(p))

    input_params["pipeline"] = args.pipeline
    instance_id = client.create(args.resolver, input_params)
    (meta / "instance_id.txt").write_text(instance_id + "\n")
    print(f"submitted instance {instance_id}", file=sys.stderr)

    # Phase 2: poll to terminal, tolerating transient poll failures. A single
    # 502/network blip must NOT abort a live multi-hour run (that bug abandoned
    # a healthy queued instance). Only a sustained outage gives up.
    started = time.monotonic()
    final: dict = {}
    consecutive_fail = 0
    max_consec_fail = 30  # ~5 min at the default 10s interval before giving up
    while True:
        got = client.status(instance_id)
        if got is None:
            consecutive_fail += 1
            if consecutive_fail >= max_consec_fail:
                _die(
                    f"status poll failed {max_consec_fail}x in a row -- backend "
                    f"unreachable; last known status "
                    f"'{final.get('status', '<none>')}'",
                    1,
                )
            if args.timeout and (time.monotonic() - started) >= args.timeout:
                print(
                    f"WARN: timeout ({args.timeout}s) during poll failures",
                    file=sys.stderr,
                )
                break
            time.sleep(args.poll_interval)
            continue
        consecutive_fail = 0
        final = got
        st = final.get("status", "<unknown>")
        print(f"[{time.strftime('%H:%M:%S')}] status: {st}", file=sys.stderr)
        if st in _TERMINAL:
            break
        if (
            st == _AWAITING
            and client.answer_open_gates(instance_id, args.gate_answer) == 0
        ):
            print("WARN: awaiting_input but no answerable gate found", file=sys.stderr)
        if args.timeout and (time.monotonic() - started) >= args.timeout:
            print(f"WARN: timeout ({args.timeout}s) still '{st}'", file=sys.stderr)
            break
        time.sleep(args.poll_interval)

    # Phase 3: pull events + final status into meta (NOT --out, so the capsule
    # secret gate never scans them), then the capsule_out data into --out.
    (meta / "events.json").write_bytes(client.events_raw(instance_id))
    (meta / "final-status.json").write_text(json.dumps(final, indent=2))
    client.fetch_data(instance_id, args.data_subpath, out)

    print(instance_id)  # last stdout line = instance id (for the workflow)
    st = final.get("status")
    if st != _SUCCESS:
        _die(f"instance {instance_id} ended '{st}' (see {meta}/events.json)", 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
