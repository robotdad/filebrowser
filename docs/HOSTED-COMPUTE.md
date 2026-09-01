# How to configure and run it

This is the plumbing. The human flow (issues and PRs) is in the top-level
[README](../README.md). This page is what you set up once and how the parts fit.

The idea is a compute swap. The capsule graphs normally run in a GitHub Actions runner. Here
the runner does no model work. It packages the issue, submits to a hosted backend over a
bearer token, waits, and pulls the result back. GitHub keeps events, issues, PRs, and review.
The backend is the engine. The design rationale and first-run risks are in
[docs/designs/gh-actions-hosted-compute.md](designs/gh-actions-hosted-compute.md).

## Secrets

Set these under Settings > Secrets and variables > Actions.

| Name | Value |
|------|-------|
| `COMPUTE_URL` | the hosted backend base URL, a secret so it stays out of public logs |
| `COMPUTE_TOKEN` | bearer token for the backend |
| `CAPSULE_PR_TOKEN` | a PAT for `gh pr create`, or rely on the default token |

The names are deliberately neutral so the backend's product name stays out of public YAML.
Put the URL and token the backend owner gave you into `COMPUTE_URL` and `COMPUTE_TOKEN`.

Until `COMPUTE_TOKEN` is set, the submit step fails fast by design. Everything up to the
backend call still exercises the wiring.

## Labels

Two labels trigger the pipeline. Create both.

- `ready:spec` starts the defect specify lane.
- `ready:feature-spec` starts the feature specify lane.

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `backend-smoke.yml` | manual (Actions, run workflow) | auth precheck plus a minimal submit, to confirm the token works |
| `capsule-specify.yml` | label `ready:spec` on an issue | runs `capsule.dot`, opens a defect capsule PR |
| `feature-specify.yml` | label `ready:feature-spec` on an issue | runs `feature-capsule.dot`, opens a feature capsule PR |
| `capsule-implement.yml` | a capsule PR is merged | runs `task-runner.dot`, opens a fix PR |

The implement workflow is unified. Merging any capsule PR, defect or feature, fires it, and it
runs `task-runner.dot` against whichever capsule the merge carried. There is no separate
feature-implement workflow.

Smoke-test the token before the first real run.

## The feature criteria comment

A feature run needs binding acceptance criteria, and the issue body is never trusted for them.
Post them as a comment from a repository OWNER, MEMBER, or COLLABORATOR, in this exact shape,
then add the `ready:feature-spec` label.

```markdown
## Acceptance criteria (feature-capsule)

Owned-by: @your-login
Scope: IN -- ... OUT -- ...

AC-1: <one testable behavior through a public surface>
AC-2: <another>
AC-3 [guard]: <a criterion that already holds at base and must keep holding>
```

`author_association` is computed server-side by GitHub, so a filer cannot forge a maintainer
comment. Issue #11 (`format_price()`) is a worked example.

## Submit and retrieve

`submit_compute.py` is the client that stands in for the in-runner engine. It builds a params
object from a workspace-resident shim (`shim-specify.dot`, `shim-feature-specify.dot`, or
`shim-implement.dot`), submits to the backend, polls to completion while auto-answering gates,
then composes the current API's two evidence surfaces. It safely extracts the raw export's
`events.jsonl`, `pipeline_logs/`, `artifacts/data/`, and optional `workspace_resolve/`; separately,
it enumerates `workspace-tree?include_hidden=true&include_ignored=true` and fetches every returned
`.ai/` file through `/workspace/{path}` with no content allowlist. This is a transport contract,
not a judgment-packet allowlist: retrieval does not depend on convergence, packaging, a
postmortem, or a shim Export node. Raw `pipeline_logs/` are also mapped to the workflow's
historical uploaded `logs/` path, and the selected `artifacts/data/capsule` subtree is copied to
the historical operational `out/` path. The compressed archive itself is never written into the
upload roots.

The workflows scrub the complete mirrored evidence and pass it through the existing fail-closed
residual secret gate before upload. The capsule output is fenced separately and is scanned but
never redacted in place. Metadata includes the instance ID, final status, retrieval errors,
and the generic state, artifact-manifest, and bounded `/logs` responses when available. `/logs`
is supplementary metadata only; raw exported `pipeline_logs/` and `events.jsonl` are authoritative.
The required export roots are `events.jsonl`, `pipeline_logs/`, and `artifacts/data/`.
`workspace_resolve/` is optional platform-adjacent material that is still extracted, scrubbed,
and uploaded whenever present. An export omission marker, missing required export root, unsafe
archive member, workspace-tree request error, unsafe `.ai` path, or per-file workspace fetch
failure marks retrieval incomplete and blocks successful PR publication. A successful workspace
enumeration with no `.ai` entries is recorded honestly as empty; no directory is fabricated.
The backend does not expose a generic session-list endpoint, so session IDs are not guessed;
session material returned under workspace `.ai/` is preserved instead.

`backend-smoke.yml` remains intentionally submit-only. It checks authentication and instance
creation but does not poll a long-running graph to a terminal outcome, so there is no completed
run-evidence lifecycle to mirror or upload in that smoke.

## Layout

```
.github/workflows/        capsule-specify.yml, feature-specify.yml, capsule-implement.yml,
                          backend-smoke.yml            (adapted, compute on the backend)
.github/capsule-pipeline/
    submit_compute.py     bearer-token submit/retrieve client (ours)
    shim-*.dot            workspace-resident shims: shim-specify, shim-feature-specify,
                          shim-implement (ours)
    capsule.dot, feature-capsule.dot, task-runner.dot,
    scrub_secrets.py, capsule_pair_fence.sh, verify_shipped_gate.sh, vendor/
                                                       (from amplifier-bundle-attractor, public)
    proposals/            shipped capsules for the sample scenarios
src/, tests/              the buggy sample project
docs/                     this guide, the explainer, scenarios, and the design docs
```

## Visibility and who can run it

This repo is private, and stays private as long as the backend (Resolve) is private. It is
tied to the backend, not to the pipeline. The pipeline itself is public.

The graphs are public. They are vendored unmodified from
[microsoft/amplifier-bundle-attractor](https://github.com/microsoft/amplifier-bundle-attractor),
which is public. Only where the compute runs is private here.

So this approach works on public repos too. You can wire these workflows into a public
repository and run the whole flow, as long as you have access to the backend (`COMPUTE_URL`
and `COMPUTE_TOKEN`). That is true for teammates today. The private piece is the backend
token, not the method.

To apply this to another repo, see [AGENTS.md](../AGENTS.md).
