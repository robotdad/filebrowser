#!/usr/bin/env python3
r"""Self-contained compute-backend submit client for CI (bearer token).

Purpose
-------
Submit a dot-graph "custom" pipeline run to a hosted compute backend from a
GitHub Actions runner, poll it to a terminal state, auto-answer any human-gate
input requests, and mirror the run evidence back to the runner filesystem.
The evidence mirror is deliberately interpretation-free: it safely extracts
the platform's raw export archive (artifact data, pipeline logs, optional
workspace `.resolve`, and raw events), then separately retrieves every `.ai`
file exposed by the workspace APIs. The selected `capsule_out` path is also
copied to its historical local location for downstream PR plumbing. Any
omission, unsafe path, or fetch failure makes retrieval explicitly incomplete.

Design
------
stdlib-only, so it runs on a bare runner with no pip install. It reads a
pre-issued BEARER TOKEN from the environment. HTTP contract:
  POST /api/instances  {"resolver","input":{"pipeline":...}}  -> {id/instance_id}
  POST /api/uploads    (multipart)                            -> {"handle"}
  GET  /api/instances/{id}                                    -> {"status"}
  POST /api/instances/{id}/input-requests/{rid}  {"response","text"}
  GET  /api/instances/{id}/export
  GET  /api/instances/{id}/logs
  GET  /api/instances/{id}/workspace-tree
  GET  /api/instances/{id}/workspace/{path}

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
      --out ./out \                      # historical capsule_out destination
      --evidence-dir ./evidence \        # safely extracted raw export + metadata
      --workspace-ai-dir ./.ai \         # mapped workspace .ai files
      --logs-dir ./logs \                # mapped exported pipeline_logs
      --data-subpath capsule \           # copied from artifacts/data to --out
      [--gate-answer K] [--poll-interval 10] [--timeout 21600]

Exit codes: 0 = instance reached `completed`; 1 = terminal non-success or error;
2 = auth failure; 3 = network failure. The resolved instance_id is written to
stdout (last line) and to <meta-dir>/instance_id.txt.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import NoReturn

# Terminal statuses the standard terminal statuses. `awaiting_input`
# is terminal-for-watch but NOT terminal-for-us: in unattended CI we answer the
# gate and keep polling.
_SUCCESS = "completed"
_TERMINAL = frozenset({"completed", "failed", "error", "cancelled", "canceled"})
_AWAITING = "awaiting_input"
_REQUIRED_EXPORT_ROOTS = (
    "events.jsonl",
    "pipeline_logs",
    "artifacts/data",
)


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
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, f"network error: {exc}".encode()

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

    def export_raw(self, instance_id: str) -> tuple[int, bytes]:
        return self._get_bytes(f"/api/instances/{instance_id}/export")

    def fetch_tree(
        self,
        instance_id: str,
        *,
        tree_name: str,
        file_name: str,
        destination: Path,
        source_prefix: str = "",
    ) -> tuple[int, list[str]]:
        """Mirror every file selected by a structural tree prefix.

        ``source_prefix`` selects the workspace's `.ai` root; it never selects
        evidence *within* that root.
        """
        errors: list[str] = []
        code, parsed, raw = self._request(
            "GET",
            f"/api/instances/{instance_id}/{tree_name}"
            "?include_hidden=true&include_ignored=true",
        )
        print(f"{tree_name} HTTP {code}", file=sys.stderr)
        if code >= 400 or parsed is None:
            return 0, [f"{tree_name}: HTTP {code}: {raw.strip()[:300]}"]
        if not isinstance(parsed, list):
            return 0, [
                f"{tree_name}: invalid response shape "
                f"{type(parsed).__name__}; expected a JSON array"
            ]

        rels = _flatten_tree(parsed)
        prefix = source_prefix.strip("/")
        if prefix:
            wanted = [rel for rel in rels if rel == prefix or rel.startswith(prefix + "/")]
        else:
            wanted = rels

        fetched = 0
        for rel in wanted:
            safe_rel = _safe_relative_path(rel)
            if safe_rel is None:
                errors.append(f"{tree_name}: rejected unsafe path {rel!r}")
                continue
            local_rel = safe_rel
            if prefix:
                if safe_rel == prefix:
                    errors.append(f"{tree_name}: expected {prefix!r} to be a directory")
                    continue
                local_rel = safe_rel[len(prefix) + 1 :]
            encoded = urllib.parse.quote(safe_rel, safe="/")
            scode, blob = self._get_bytes(
                f"/api/instances/{instance_id}/{file_name}/{encoded}"
            )
            if scode >= 400 or scode == 0:
                errors.append(f"{file_name}/{safe_rel}: HTTP {scode}")
                print(f"WARN: fetch {file_name}/{safe_rel} HTTP {scode}", file=sys.stderr)
                continue
            dest = _safe_destination(destination, local_rel)
            if dest is None:
                errors.append(f"{tree_name}: local path escaped destination: {local_rel!r}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            fetched += 1

        print(
            f"retrieved {fetched}/{len(wanted)} file(s) from {tree_name} -> {destination}",
            file=sys.stderr,
        )
        return fetched, errors

    def fetch_workspace_ai(
        self, instance_id: str, destination: Path
    ) -> tuple[int, list[str]]:
        """Mirror every `.ai/` file exposed by the current workspace API."""
        return self.fetch_tree(
            instance_id,
            tree_name="workspace-tree",
            file_name="workspace",
            destination=destination,
            source_prefix=".ai",
        )


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
        # Preserve an absolute marker so the safety layer can reject it.
        out.append(node if node.startswith("/") else node.lstrip("/"))
    elif isinstance(node, dict):
        path = node.get("path")
        if path is not None and not isinstance(path, str):
            return out
        name = node.get("name")
        if name is not None and not isinstance(name, str):
            return out
        if path and path.startswith("/"):
            # Preserve an invalid absolute path for the safety layer.
            rel = path
        elif path and "/" in path.strip("/"):
            # Full path already; don't re-prefix. Preserve a leading slash so
            # an invalid absolute path is rejected rather than normalized.
            rel = path.lstrip("/")
        else:
            rel = f"{prefix}{path or name or ''}".lstrip("/")
        children = node.get("children")
        is_dir = node.get("type") == "dir" or children is not None
        if children:
            base = rel + "/" if rel and not rel.endswith("/") else rel
            out.extend(_flatten_tree(children, base))
        elif rel and not is_dir:
            out.append(rel)
    return out


def _safe_relative_path(path: str) -> str | None:
    """Return a normalized POSIX relative path, or None for unsafe input."""
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        return None
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        return None
    return pure.as_posix()


def _safe_destination(root: Path, relative: str) -> Path | None:
    safe = _safe_relative_path(relative)
    if safe is None:
        return None
    root_resolved = root.resolve()
    destination = (root_resolved / safe).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError:
        return None
    return destination


def _copy_data_subpath(data_root: Path, subpath: str, out: Path) -> int:
    """Copy the historical capsule_out subtree from the complete data mirror."""
    safe_subpath = _safe_relative_path(subpath.strip("/"))
    if safe_subpath is None:
        raise ValueError(f"unsafe --data-subpath: {subpath!r}")
    source = _safe_destination(data_root, safe_subpath)
    if source is None or not source.is_dir():
        print(
            f"WARN: no files under mirrored data/{safe_subpath}; "
            "the pipeline may not have packaged capsule_out",
            file=sys.stderr,
        )
        return 0
    copied = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        # The shims historically placed selected .ai evidence beneath
        # capsule_out, and the workflows moved it out before downstream PR
        # handling. The complete copy now comes from the raw export instead;
        # keep the operational out/ path's established artifact-only shape.
        if relative.parts and relative.parts[0] == "ai":
            continue
        destination = _safe_destination(out, relative.as_posix())
        if destination is None:
            raise ValueError(f"unsafe mirrored capsule path: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, destination)
        copied += 1
    print(f"copied {copied} file(s) from data/{safe_subpath} -> {out}", file=sys.stderr)
    return copied


def _extract_export(archive: bytes, destination: Path) -> tuple[set[str], list[str]]:
    """Safely extract a platform export without persisting the compressed input.

    Only regular files and directories are accepted. Any unsafe member makes
    the retrieval incomplete; links and special files are never extracted.
    """
    extracted: set[str] = set()
    errors: list[str] = []
    try:
        opened = tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        return extracted, [f"export archive unreadable: {exc}"]

    with opened as tar:
        for member in tar.getmembers():
            safe_name = _safe_relative_path(member.name.rstrip("/"))
            if safe_name is None:
                errors.append(f"export: rejected unsafe member path {member.name!r}")
                continue
            if not (member.isdir() or member.isreg()):
                errors.append(
                    f"export: rejected non-regular member {member.name!r} "
                    f"(type={member.type!r})"
                )
                continue
            target = _safe_destination(destination, safe_name)
            if target is None:
                errors.append(f"export: member escaped destination {member.name!r}")
                continue
            try:
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    extracted.add(safe_name)
                    continue
                source = tar.extractfile(member)
                if source is None:
                    errors.append(f"export: could not read regular member {member.name!r}")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.add(safe_name)
            except (OSError, tarfile.TarError) as exc:
                errors.append(f"export: failed to extract {member.name!r}: {exc}")
    return extracted, errors


def _has_member(members: set[str], root: str) -> bool:
    return root in members or any(name.startswith(root + "/") for name in members)


def _copy_tree_files(source: Path, destination: Path) -> int:
    copied = 0
    if not source.is_dir():
        return copied
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source).as_posix()
        target = _safe_destination(destination, relative)
        if target is None:
            raise ValueError(f"unsafe extracted path: {relative!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)
        copied += 1
    return copied


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
        help="dir for run metadata; defaults to <evidence-dir>/metadata",
    )
    ap.add_argument(
        "--evidence-dir",
        required=True,
        help="dir for the safely extracted raw export and retrieval metadata",
    )
    ap.add_argument(
        "--workspace-ai-dir",
        required=True,
        help="dir receiving .ai files fetched through the workspace API",
    )
    ap.add_argument(
        "--logs-dir",
        required=True,
        help="dir receiving the authoritative raw pipeline_logs tree",
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
    evidence = Path(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    meta = Path(args.meta_dir) if args.meta_dir else evidence / "metadata"
    meta.mkdir(parents=True, exist_ok=True)
    workspace_ai = Path(args.workspace_ai_dir)
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
    poll_failure = ""
    consecutive_fail = 0
    max_consec_fail = 30  # ~5 min at the default 10s interval before giving up
    while True:
        got = client.status(instance_id)
        if got is None:
            consecutive_fail += 1
            if consecutive_fail >= max_consec_fail:
                poll_failure = (
                    f"status poll failed {max_consec_fail}x in a row; last known "
                    f"status '{final.get('status', '<none>')}'"
                )
                print(f"WARN: {poll_failure}; attempting evidence retrieval", file=sys.stderr)
                break
            if args.timeout and (time.monotonic() - started) >= args.timeout:
                print(
                    f"WARN: timeout ({args.timeout}s) during poll failures",
                    file=sys.stderr,
                )
                poll_failure = f"poll timeout after {args.timeout}s during status failures"
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
            poll_failure = f"poll timeout after {args.timeout}s while status was {st!r}"
            break
        time.sleep(args.poll_interval)

    # Phase 3: mirror first, interpret later. This runs for completed,
    # terminal non-success, timeout, and sustained poll failure outcomes.
    # Current API composition: /export is authoritative for raw events, logs,
    # artifact data, and optional workspace .resolve material. Workspace .ai
    # is independently enumerated and fetched through the workspace API.
    retrieval_errors: list[str] = []
    (meta / "final-status.json").write_text(json.dumps(final, indent=2))
    if poll_failure:
        (meta / "poll-failure.txt").write_text(poll_failure + "\n")
        retrieval_errors.append(
            f"polling did not reach a known terminal outcome: {poll_failure}"
        )

    st = final.get("status")
    run_exit_code = 0 if st == _SUCCESS else 1
    (meta / "run-exit-code.txt").write_text(f"{run_exit_code}\n")

    # Preserve additional generic metadata exposed by the service. There is
    # no session-list endpoint, so transcripts are not guessed from UUID-like
    # strings; all `.ai` paths exposed by the workspace API are fetched.
    for endpoint, filename in (
        ("state", "state.json"),
        ("artifacts", "artifacts.json"),
        ("logs", "logs.json"),
    ):
        code, parsed, raw = client._request(
            "GET", f"/api/instances/{instance_id}/{endpoint}"
        )
        if code < 400 and parsed is not None:
            (meta / filename).write_text(json.dumps(parsed, indent=2))
        elif code not in (404,):
            retrieval_errors.append(f"{endpoint}: HTTP {code}: {raw.strip()[:200]}")

    export_code, export_body = client.export_raw(instance_id)
    export_members: set[str] = set()
    if export_code < 400 and export_code != 0:
        export_members, export_errors = _extract_export(export_body, evidence)
        retrieval_errors.extend(export_errors)
    else:
        retrieval_errors.append(f"export: HTTP {export_code}")

    if "_export_omitted.txt" in export_members:
        retrieval_errors.append(
            "export: _export_omitted.txt is present; the platform omitted archive members"
        )

    for required_root in _REQUIRED_EXPORT_ROOTS:
        if not _has_member(export_members, required_root):
            retrieval_errors.append(
                f"export: required authoritative root {required_root!r} is missing"
            )

    evidence_workspace_ai = evidence / "workspace_ai"
    _, workspace_errors = client.fetch_workspace_ai(
        instance_id, evidence_workspace_ai
    )
    retrieval_errors.extend(workspace_errors)
    _copy_tree_files(evidence_workspace_ai, workspace_ai)

    # Map authoritative raw pipeline logs to the same local logs root the
    # in-runner workflows upload. Keep the archive-shaped copy in evidence too.
    logs_destination = Path(args.logs_dir)
    logs_destination.mkdir(parents=True, exist_ok=True)
    _copy_tree_files(evidence / "pipeline_logs", logs_destination)

    _copy_data_subpath(evidence / "artifacts" / "data", args.data_subpath, out)

    (meta / "retrieval-errors.json").write_text(
        json.dumps({"errors": retrieval_errors}, indent=2)
    )
    retrieval_complete = not retrieval_errors
    (meta / "retrieval-complete.txt").write_text(
        ("true" if retrieval_complete else "false") + "\n"
    )

    print(instance_id)  # last stdout line = instance id (for the workflow)
    if st != _SUCCESS:
        detail = poll_failure or f"instance ended {st!r}"
        _die(f"instance {instance_id}: {detail} (see {meta})", 1)
    if not retrieval_complete:
        _die(
            f"instance {instance_id} completed but evidence retrieval was incomplete "
            f"(see {meta}/retrieval-errors.json)",
            1,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
