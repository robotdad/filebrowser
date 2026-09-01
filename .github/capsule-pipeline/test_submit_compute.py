from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("submit_compute.py")
SPEC = importlib.util.spec_from_file_location("submit_compute", MODULE_PATH)
assert SPEC and SPEC.loader
submit_compute = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(submit_compute)
SCRUB_SPEC = importlib.util.spec_from_file_location(
    "scrub_secrets", MODULE_PATH.with_name("scrub_secrets.py")
)
assert SCRUB_SPEC and SCRUB_SPEC.loader
scrub_secrets = importlib.util.module_from_spec(SCRUB_SPEC)
SCRUB_SPEC.loader.exec_module(scrub_secrets)


def make_export(
    files: dict[str, bytes],
    *,
    links: dict[str, str] | None = None,
    special: dict[str, bytes] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        directories: set[str] = set()
        for name in files:
            parts = Path(name).parts[:-1]
            for index in range(1, len(parts) + 1):
                directories.add("/".join(parts[:index]))
        for directory in sorted(directories):
            info = tarfile.TarInfo(directory)
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
        for name, member_type in (special or {}).items():
            info = tarfile.TarInfo(name)
            info.type = member_type
            tar.addfile(info)
    return buffer.getvalue()


COMPLETE_FILES = {
    "events.jsonl": b'{"type":"completed"}\n',
    "pipeline_logs/node/stdout.log": b"full log\n",
    "artifacts/data/capsule/candidate.verify.sh": b"#!/bin/sh\n",
    "artifacts/data/pipeline-status/node.json": b"{}",
    "workspace_resolve/reality_check/verdict.json": b'{"verdict":"PASS"}',
}


class ExportExtractionTests(unittest.TestCase):
    def test_extracts_current_export_logs_events_data_and_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            members, errors = submit_compute._extract_export(
                make_export(COMPLETE_FILES), destination
            )
            self.assertEqual(errors, [])
            for name, content in COMPLETE_FILES.items():
                self.assertEqual((destination / name).read_bytes(), content)

    def test_rejects_traversal_absolute_and_link_members(self) -> None:
        files = {
            "safe/file.txt": b"safe",
            "../escape.txt": b"escape",
            "/absolute.txt": b"absolute",
        }
        archive = make_export(
            files,
            links={"safe/link": "/etc/passwd"},
            special={"safe/device": tarfile.CHRTYPE, "safe/fifo": tarfile.FIFOTYPE},
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "evidence"
            members, errors = submit_compute._extract_export(archive, destination)
            self.assertEqual((destination / "safe/file.txt").read_bytes(), b"safe")
            self.assertNotIn("../escape.txt", members)
            self.assertNotIn("/absolute.txt", members)
            self.assertFalse((destination / "safe/link").exists())
            self.assertFalse((destination / "safe/device").exists())
            self.assertFalse((destination / "safe/fifo").exists())
            self.assertGreaterEqual(len(errors), 5)
            self.assertTrue(any("non-regular member" in error for error in errors))
            self.assertTrue(any("unsafe member path" in error for error in errors))
            self.assertFalse((Path(tmp) / "escape.txt").exists())

    def test_unreadable_or_partial_archive_is_incomplete(self) -> None:
        members, errors = submit_compute._extract_export(b"not a tar", Path("unused"))
        self.assertEqual(members, set())
        self.assertEqual(len(errors), 1)
        self.assertIn("unreadable", errors[0])

    def test_member_collision_is_reported_while_other_files_survive(self) -> None:
        archive = make_export(
            {
                "collision": b"a file blocks the following directory",
                "collision/child.txt": b"cannot land",
                "safe/last.txt": b"survives",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            members, errors = submit_compute._extract_export(archive, destination)
            self.assertTrue(errors)
            self.assertIn("safe/last.txt", members)
            self.assertEqual((destination / "safe/last.txt").read_bytes(), b"survives")

    def test_operational_copy_preserves_export_and_excludes_shim_ai(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capsule = root / "artifacts" / "data" / "capsule"
            (capsule / "ai").mkdir(parents=True)
            (capsule / "ai" / "finding.md").write_text("evidence\n")
            (capsule / "fix.diff").write_text("diff\n")
            copied = submit_compute._copy_data_subpath(
                root / "artifacts" / "data", "capsule", root / "out"
            )
            self.assertEqual(copied, 1)
            self.assertEqual((root / "out" / "fix.diff").read_text(), "diff\n")
            self.assertFalse((root / "out" / "ai").exists())
            self.assertTrue((capsule / "ai" / "finding.md").is_file())


class WorkspaceAiRetrievalTests(unittest.TestCase):
    def test_enumerates_and_fetches_every_exposed_ai_file(self) -> None:
        client = submit_compute.Compute("https://example.invalid", "token")
        tree = [
            {
                "path": ".ai",
                "type": "directory",
                "children": [
                    {"path": ".ai/capsule/DEFINITION.md", "type": "file"},
                    {"path": ".ai/sessions/a file/events.jsonl", "type": "file"},
                ],
            },
            {"path": "src/not-evidence.py", "type": "file"},
        ]
        client._request = mock.Mock(return_value=(200, tree, json.dumps(tree)))
        payloads = {
            "/api/instances/i/workspace/.ai/capsule/DEFINITION.md": b"definition",
            "/api/instances/i/workspace/.ai/sessions/a%20file/events.jsonl": b"events",
        }
        client._get_bytes = mock.Mock(side_effect=lambda path: (200, payloads[path]))

        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            fetched, errors = client.fetch_workspace_ai("i", destination)

            self.assertEqual(fetched, 2)
            self.assertEqual(errors, [])
            self.assertEqual(
                (destination / "capsule/DEFINITION.md").read_bytes(), b"definition"
            )
            self.assertEqual(
                (destination / "sessions/a file/events.jsonl").read_bytes(), b"events"
            )
            self.assertFalse((destination / "src").exists())
        tree_path = client._request.call_args.args[1]
        self.assertIn("workspace-tree?include_hidden=true&include_ignored=true", tree_path)

    def test_tree_request_and_per_file_failures_are_incomplete(self) -> None:
        client = submit_compute.Compute("https://example.invalid", "token")
        client._request = mock.Mock(return_value=(503, None, "unavailable"))
        with tempfile.TemporaryDirectory() as tmp:
            fetched, errors = client.fetch_workspace_ai("i", Path(tmp))
        self.assertEqual(fetched, 0)
        self.assertEqual(errors, ["workspace-tree: HTTP 503: unavailable"])

        client._request = mock.Mock(return_value=(200, {"not": "a tree"}, "{}"))
        with tempfile.TemporaryDirectory() as tmp:
            fetched, errors = client.fetch_workspace_ai("i", Path(tmp))
        self.assertEqual(fetched, 0)
        self.assertEqual(
            errors,
            ["workspace-tree: invalid response shape dict; expected a JSON array"],
        )

        tree = [
            {"path": ".ai/kept.md", "type": "file"},
            {"path": ".ai/../escape.md", "type": "file"},
            {"path": ".ai/missing.md", "type": "file"},
        ]
        client._request = mock.Mock(return_value=(200, tree, json.dumps(tree)))
        client._get_bytes = mock.Mock(
            side_effect=[
                (200, b"kept"),
                (404, b"missing"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp)
            fetched, errors = client.fetch_workspace_ai("i", destination)
            self.assertEqual(fetched, 1)
            self.assertEqual(
                errors,
                [
                    "workspace-tree: rejected unsafe path '.ai/../escape.md'",
                    "workspace/.ai/missing.md: HTTP 404",
                ],
            )
            self.assertEqual((destination / "kept.md").read_bytes(), b"kept")
            self.assertFalse((destination / "missing.md").exists())
            self.assertFalse((Path(tmp) / "escape.md").exists())

    def test_empty_exposed_ai_tree_is_not_fabricated(self) -> None:
        client = submit_compute.Compute("https://example.invalid", "token")
        client._request = mock.Mock(
            return_value=(
                200,
                [{"path": "src/main.py", "type": "file"}],
                '[{"path":"src/main.py","type":"file"}]',
            )
        )
        client._get_bytes = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "workspace_ai"
            fetched, errors = client.fetch_workspace_ai("i", destination)
            self.assertEqual((fetched, errors), (0, []))
            self.assertFalse(destination.exists())
        client._get_bytes.assert_not_called()


class FakeComputeBase:
    export_files = COMPLETE_FILES
    status_value = {"status": "completed"}
    workspace_ai_files = {
        "capsule/DEFINITION.md": b"candidate\n",
        "sessions/raw/events.jsonl": b'{"event":"tool:post"}\n',
    }
    workspace_fetch_called = False

    def __init__(self, _url: str, _token: str) -> None:
        type(self).workspace_fetch_called = False

    def create(self, _resolver: str, _params: dict) -> str:
        return "instance-123"

    def status(self, _instance_id: str) -> dict:
        return self.status_value

    def _request(self, _method: str, path: str):
        endpoint = path.rsplit("/", 1)[-1]
        return 200, {"endpoint": endpoint, "stderr_tail": "bounded"}, "{}"

    def export_raw(self, _instance_id: str):
        return 200, make_export(self.export_files)

    def fetch_workspace_ai(self, _instance_id: str, destination: Path):
        type(self).workspace_fetch_called = True
        for relative, content in self.workspace_ai_files.items():
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return len(self.workspace_ai_files), []


def run_main(compute_type: type[FakeComputeBase], root: Path) -> int:
    params = root / "params.json"
    params.write_text("{}")
    argv = [
        "submit_compute.py",
        "--url",
        "https://example.invalid",
        "--params-file",
        str(params),
        "--out",
        str(root / "out"),
        "--evidence-dir",
        str(root / "evidence"),
        "--workspace-ai-dir",
        str(root / ".ai"),
        "--logs-dir",
        str(root / "logs"),
    ]
    with (
        mock.patch.object(submit_compute, "Compute", compute_type),
        mock.patch.object(sys, "argv", argv),
        mock.patch.dict(os.environ, {"COMPUTE_TOKEN": "test-token"}),
    ):
        return submit_compute.main()


class MainRetrievalTests(unittest.TestCase):
    def test_complete_current_api_composition_preserves_all_roots_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_main(FakeComputeBase, root), 0)
            evidence = root / "evidence"
            metadata = evidence / "metadata"
            self.assertEqual((metadata / "retrieval-complete.txt").read_text(), "true\n")
            self.assertEqual(
                json.loads((metadata / "retrieval-errors.json").read_text()),
                {"errors": []},
            )
            self.assertEqual((root / "logs/node/stdout.log").read_bytes(), b"full log\n")
            self.assertEqual(
                (evidence / "events.jsonl").read_bytes(), COMPLETE_FILES["events.jsonl"]
            )
            self.assertEqual(
                (root / ".ai/capsule/DEFINITION.md").read_bytes(), b"candidate\n"
            )
            self.assertEqual(
                (evidence / "workspace_ai/sessions/raw/events.jsonl").read_bytes(),
                b'{"event":"tool:post"}\n',
            )
            self.assertEqual(
                (root / "out/candidate.verify.sh").read_bytes(), b"#!/bin/sh\n"
            )
            self.assertEqual(
                json.loads((metadata / "logs.json").read_text())["stderr_tail"],
                "bounded",
            )
            self.assertEqual(list(root.rglob("*.tar.gz")), [])
            self.assertTrue(FakeComputeBase.workspace_fetch_called)

    def test_each_missing_authoritative_root_is_precise_and_incomplete(self) -> None:
        required_roots = {
            "events.jsonl": (lambda name: name == "events.jsonl", "events.jsonl"),
            "pipeline_logs": (
                lambda name: name.startswith("pipeline_logs/"),
                "pipeline_logs",
            ),
            "artifacts/data": (
                lambda name: name.startswith("artifacts/data/"),
                "artifacts/data",
            ),
        }
        for missing_root, (belongs_to_root, extracted_path) in required_roots.items():
            with self.subTest(missing_root=missing_root), tempfile.TemporaryDirectory() as tmp:
                export_files = {
                    name: content
                    for name, content in COMPLETE_FILES.items()
                    if not belongs_to_root(name)
                }
                missing_compute = type(
                    "MissingRootCompute",
                    (FakeComputeBase,),
                    {"export_files": export_files},
                )
                root = Path(tmp)

                with self.assertRaises(SystemExit) as raised:
                    run_main(missing_compute, root)

                self.assertEqual(raised.exception.code, 1)
                metadata = root / "evidence/metadata"
                self.assertEqual(
                    (metadata / "retrieval-complete.txt").read_text(), "false\n"
                )
                errors = json.loads(
                    (metadata / "retrieval-errors.json").read_text()
                )["errors"]
                self.assertIn(
                    f"export: required authoritative root {missing_root!r} is missing",
                    errors,
                )
                self.assertFalse((root / "evidence" / extracted_path).exists())

    def test_missing_optional_workspace_resolve_remains_complete(self) -> None:
        class NoWorkspaceResolveCompute(FakeComputeBase):
            export_files = {
                name: content
                for name, content in COMPLETE_FILES.items()
                if not name.startswith("workspace_resolve/")
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_main(NoWorkspaceResolveCompute, root), 0)
            metadata = root / "evidence/metadata"
            self.assertEqual(
                (metadata / "retrieval-complete.txt").read_text(), "true\n"
            )
            self.assertEqual(
                json.loads((metadata / "retrieval-errors.json").read_text()),
                {"errors": []},
            )
            self.assertFalse((root / "evidence/workspace_resolve").exists())

    def test_omission_marker_marks_retrieval_incomplete(self) -> None:
        class OmittedCompute(FakeComputeBase):
            export_files = {**COMPLETE_FILES, "_export_omitted.txt": b"omitted member\n"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit) as raised:
                run_main(OmittedCompute, root)
            self.assertEqual(raised.exception.code, 1)
            metadata = root / "evidence/metadata"
            self.assertEqual((metadata / "retrieval-complete.txt").read_text(), "false\n")
            self.assertEqual((metadata / "run-exit-code.txt").read_text(), "0\n")
            errors = json.loads((metadata / "retrieval-errors.json").read_text())["errors"]
            self.assertTrue(any("_export_omitted.txt" in error for error in errors))

    def test_workspace_ai_fetch_failure_marks_retrieval_incomplete(self) -> None:
        class WorkspaceFailureCompute(FakeComputeBase):
            def fetch_workspace_ai(self, _instance_id: str, destination: Path):
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "capsule/DEFINITION.md").parent.mkdir(parents=True)
                (destination / "capsule/DEFINITION.md").write_text("preserved\n")
                return 1, ["workspace/.ai/sessions/events.jsonl: HTTP 503"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit):
                run_main(WorkspaceFailureCompute, root)
            self.assertTrue(
                (root / "evidence/workspace_ai/capsule/DEFINITION.md").is_file()
            )
            self.assertEqual(
                (root / "evidence/metadata/retrieval-complete.txt").read_text(),
                "false\n",
            )
            errors = json.loads(
                (root / "evidence/metadata/retrieval-errors.json").read_text()
            )["errors"]
            self.assertIn("workspace/.ai/sessions/events.jsonl: HTTP 503", errors)

    def test_empty_workspace_ai_tree_is_honestly_complete(self) -> None:
        class EmptyWorkspaceCompute(FakeComputeBase):
            workspace_ai_files = {}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(run_main(EmptyWorkspaceCompute, root), 0)
            self.assertEqual(
                (root / "evidence/metadata/retrieval-complete.txt").read_text(),
                "true\n",
            )
            self.assertFalse((root / "evidence/workspace_ai").exists())
            self.assertFalse((root / ".ai").exists())

    def test_terminal_failure_preserves_original_outcome_after_complete_retrieval(self) -> None:
        class FailedCompute(FakeComputeBase):
            status_value = {"status": "failed", "failure_reason": "duration fuse"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit) as raised:
                run_main(FailedCompute, root)
            self.assertEqual(raised.exception.code, 1)
            self.assertEqual(
                (root / "evidence/metadata/retrieval-complete.txt").read_text(),
                "true\n",
            )
            status = json.loads(
                (root / "evidence/metadata/final-status.json").read_text()
            )
            self.assertEqual(status["failure_reason"], "duration fuse")


class WorkflowContractTests(unittest.TestCase):
    WORKFLOWS = MODULE_PATH.parent.parent / "workflows"

    def _text(self, name: str) -> str:
        return (self.WORKFLOWS / name).read_text()

    def test_timeout_headroom_is_at_least_thirty_minutes(self) -> None:
        expected = {
            "capsule-specify.yml": (360, 19800),
            "feature-specify.yml": (250, 12600),
            "capsule-implement.yml": (330, 17400),
        }
        for name, (job_minutes, client_seconds) in expected.items():
            with self.subTest(workflow=name):
                text = self._text(name)
                self.assertRegex(text, rf"timeout-minutes:\s*{job_minutes}\b")
                self.assertRegex(text, rf"--timeout\s+{client_seconds}\b")
                self.assertGreaterEqual(job_minutes * 60 - client_seconds, 1800)

    def test_run_exit_and_retrieval_outputs_are_captured_despite_shell_errexit(self) -> None:
        for name in (
            "capsule-specify.yml",
            "feature-specify.yml",
            "capsule-implement.yml",
        ):
            with self.subTest(workflow=name):
                text = self._text(name)
                capture = re.search(
                    r"set \+e\n\s+python3 \.github/capsule-pipeline/submit_compute\.py"
                    r"[\s\S]*?rc=\$\?\n\s+set -e[\s\S]*?"
                    r'echo "client_exit=\$rc"[\s\S]*?'
                    r'echo "attractor_exit=\$attractor_exit"[\s\S]*?'
                    r'echo "retrieval_complete=\$retrieval_complete"',
                    text,
                )
                self.assertIsNotNone(capture)

    def test_publication_paths_require_complete_retrieval(self) -> None:
        for name in ("capsule-specify.yml", "feature-specify.yml"):
            text = self._text(name)
            open_pr = text.index("- name: Open capsule PR")
            condition_match = re.search(r"^\s+if:.*$", text[open_pr:], re.MULTILINE)
            self.assertIsNotNone(condition_match)
            condition = condition_match.group(0)
            self.assertIn("steps.run.outputs.retrieval_complete == 'true'", condition)
        implement = self._text("capsule-implement.yml")
        for step in (
            "- name: Apply the backend-produced fix into the workspace",
            "- name: Push fix branch and open PR",
        ):
            start = implement.index(step)
            condition_match = re.search(
                r"^\s+if:.*$", implement[start:], re.MULTILINE
            )
            self.assertIsNotNone(condition_match)
            condition = condition_match.group(0)
            self.assertIn("steps.run.outputs.retrieval_complete == 'true'", condition)

    def test_implement_scans_and_fences_both_operational_copies(self) -> None:
        text = self._text("capsule-implement.yml")
        early = text[text.index("Operational output: a secret finding") : text.index("Apply the backend-produced fix")]
        self.assertIn("scrub_secrets.py scan", early)
        self.assertIn('$RUNNER_TEMP/capsule-implement/out', early)
        self.assertIn("evidence/artifacts/data/capsule", early)
        scrub = text[text.index("- name: Scrub secrets from run evidence") : text.index("Apply the backend-produced fix")]
        self.assertNotIn('scrub_secrets.py scrub \\\n            "$RUNNER_TEMP/capsule-implement"', scrub)
        residual = text[text.index("Residual secret gate") : text.index("Upload run evidence")]
        self.assertIn('--never-redact "$RUNNER_TEMP/capsule-implement/out"', residual)
        self.assertIn("--never-redact", residual)
        self.assertIn("evidence/artifacts/data/capsule", residual)

    def test_implement_does_not_overwrite_checkpoint_and_requires_real_success(self) -> None:
        text = self._text("capsule-implement.yml")
        run_step = text[
            text.index("- name: Submit task-runner.dot")
            : text.index('- name: "Classify the run')
        ]
        self.assertNotIn("checkpoint.json", run_step)
        self.assertNotIn("SHIPPED.md", run_step)
        self.assertNotIn("json.dump", run_step)

        classify_step = text[
            text.index('- name: "Classify the run')
            : text.index('- name: "Operational output')
        ]
        self.assertIn("o in ('success','fail')", classify_step)
        self.assertIn(
            '[ "$EXIT" = "0" ] && [ "$RECORDED" = "success" ] '
            '&& [ "$RETRIEVAL_COMPLETE" = "true" ]',
            classify_step,
        )

        parser = (
            "import json,sys; d=json.load(open(sys.argv[1])); "
            "c=d.get('context'); "
            "o=c.get('outcome') if isinstance(c,dict) else None; "
            "print(o if isinstance(o,str) and o in ('success','fail') "
            "else 'outcome-less')"
        )

        def recorded(path: Path) -> str:
            if not path.exists():
                return "absent"
            result = subprocess.run(
                [sys.executable, "-c", parser, str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else "unreadable"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "success.json": ('{"context":{"outcome":"success"}}', "success", True),
                "fail.json": ('{"context":{"outcome":"fail"}}', "fail", False),
                "malformed.json": ("{", "unreadable", False),
                "outcome-less.json": ('{"context":{}}', "outcome-less", False),
                "wrong-type.json": ('{"context":{"outcome":true}}', "outcome-less", False),
            }
            for name, (body, expected, converged) in cases.items():
                with self.subTest(checkpoint=name):
                    path = root / name
                    path.write_text(body)
                    before = path.read_bytes()
                    actual = recorded(path)
                    self.assertEqual(actual, expected)
                    self.assertEqual(
                        actual == "success",
                        converged,
                    )
                    self.assertEqual(path.read_bytes(), before)

            missing = root / "missing.json"
            self.assertEqual(recorded(missing), "absent")
            self.assertFalse(missing.exists())

    def test_evidence_scrub_does_not_mutate_operational_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            operational = root / "out/fix.diff"
            duplicate = root / "evidence/artifacts/data/capsule/fix.diff"
            evidence = root / "evidence/pipeline_logs/events.jsonl"
            operational.parent.mkdir(parents=True)
            duplicate.parent.mkdir(parents=True)
            evidence.parent.mkdir(parents=True)
            secret_shape = "github" + "_pat_" + ("A" * 40)
            original = f"+TOKEN={secret_shape}\n"
            operational.write_text(original)
            duplicate.write_text(original)
            evidence.write_text(original)

            self.assertEqual(scrub_secrets.cmd_scrub([str(evidence)]), 0)

            self.assertEqual(operational.read_text(), original)
            self.assertEqual(duplicate.read_text(), original)
            self.assertNotEqual(evidence.read_text(), original)
            self.assertEqual(scrub_secrets.cmd_scan([str(operational)]), 1)

    def test_smoke_remains_submit_only_and_documented(self) -> None:
        text = self._text("backend-smoke.yml")
        self.assertNotIn("submit_compute.py", text)
        self.assertNotIn("actions/upload-artifact", text)
        docs = MODULE_PATH.parents[2] / "docs" / "HOSTED-COMPUTE.md"
        self.assertIn("`backend-smoke.yml` remains intentionally submit-only", docs.read_text())


if __name__ == "__main__":
    unittest.main()
