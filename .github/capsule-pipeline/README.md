# Capsule pipeline on hosted compute — GitHub Actions variant

These are the **adapted capsule workflows**: the same issue → capsule PR → merge → fix
PR flow, but the **compute runs on a hosted compute backend** instead of an in-runner
engine. GitHub keeps events, issues, PRs, and review.

Full design + first-run risks: `../../docs/designs/gh-actions-hosted-compute.md`.

## What's here

| File | Role |
|------|------|
| `capsule-specify.yml` | Adapted specify workflow. Trigger: issue labelled `ready:spec`. Runs `capsule.dot` on the backend, opens a capsule PR. |
| `capsule-implement.yml` | Adapted implement workflow. Trigger: a capsule PR merged to `main`. Runs `task-runner.dot` on the backend, applies the fix locally, opens a fix PR. |
| `submit_compute.py` | Self-contained, stdlib-only submit client (bearer auth). Uploads → submits → polls → auto-answers human gates → fetches results + events. |
| `shim-specify.dot` | Workspace-resident shim: runs the repo's `capsule.dot`, exports `.ai/` findings into the results dir. |
| `shim-implement.dot` | Workspace-resident shim: runs the repo's `task-runner.dot`, exports the fix diff into the results dir. |

## How the compute swap works

Each workflow is the upstream workflow with the **in-runner engine steps removed**
(engine snapshot/detach, `setup-python`, `install uv`, the provider preflight and mount —
provider selection is the hosted backend's job now) and the single `attractor run …`
step replaced by a call to `submit_compute.py`. Everything else — issue materialization,
secret scrubbing, capsule PR / fix PR creation, issue comments, evidence upload — is
**preserved verbatim**.

- **specify** submits `capsule.dot`; results are fetched back to the exact runner paths
  the unchanged `Classify` / PR / comment steps read.
- **implement** submits `task-runner.dot`; the fix is exported as `fix.diff`, re-applied
  into the runner checkout, then the unchanged push/PR step pushes it.

## Deploying into a target repo

```
.github/workflows/capsule-specify.yml       <- capsule-specify.yml
.github/workflows/capsule-implement.yml     <- capsule-implement.yml
.github/capsule-pipeline/submit_compute.py  <- submit_compute.py   (chmod +x)
.github/capsule-pipeline/shim-specify.dot   <- shim-specify.dot
.github/capsule-pipeline/shim-implement.dot <- shim-implement.dot
```

The target repo also needs the existing capsule support the preserved plumbing calls
(`scrub_secrets.py`, `capsule_pair_fence.sh`, `verify_shipped_gate.sh`, plus
`capsule.dot`, `task-runner.dot`, `vendor/`).

### Repo configuration

| Kind | Name | Value |
|------|------|-------|
| **Variable** | `COMPUTE_URL` | the hosted backend base URL |
| **Secret** | `COMPUTE_TOKEN` | bearer token for the backend |
| Secret | `CAPSULE_PR_TOKEN` | fine-grained PAT for `gh pr create`; falls back to `github.token` |

Provider keys (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) are **not** required as runner
secrets — the hosted backend mounts providers. They remain referenced only by the
preserved secret-scrub steps, which no-op if unset.

## First-run notes

Structurally verified; pending a live run with a token. Watch: `.ai/` retrieval on
specify, the data-listing shape, the human-gate auto-answer text, upload path handling,
and token lifetime (a short-lived token needs re-minting per job). Port and prove
**specify first**, then implement.
