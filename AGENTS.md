# AGENTS.md

Guidance for agents working in this repo.

## Scope

- This repo is a local Flask dashboard for coding-agent usage data.
- Active production data sources are OpenCode at `~/.local/share/opencode/opencode.db`, Codex CLI via `~/.codex/state_5.sqlite` when that local state file exists, and Hermes via `~/.hermes/state.db` when that local state DB exists.
- Keep the current product contract explicit: show where totals come from, avoid ambiguous labels, and do not invent data when a source is missing.

## Working style

- Prefer small, reviewable PRs. Do not push straight to `main`.
- Work in a worktree, not in the `main` checkout. Default location is **outside** the repo (a sibling directory), created with:
  ```bash
  git worktree add ../worktrees/<branch-slug> -b <branch> origin/main
  ```
  The on-disk path does not need to be `../worktrees/`, but it must not be inside the repo unless it is also added to `.gitignore` (it is, as `.worktrees/`). When a worktree lives inside the repo, never stage or commit its directory.
- Run `scripts/review.sh` from inside the worktree before pushing. The script refuses to run from `main` outside `REVIEW_MODE=docs`, which is the safety net for this rule.
- Make the smallest change that fully solves the problem.
- Preserve existing behavior unless the task explicitly changes it.
- If a request expands scope, capture it as follow-up work instead of quietly folding unrelated refactors into the same PR.

## Architecture rules

- Keep modules focused. If a file starts carrying multiple unrelated responsibilities, split it.
- Avoid long files when practical. In particular:
  - keep Python route, query, formatting, and simulation logic separated by responsibility
  - move reusable presentation logic out of inline template scripts when it starts growing
  - avoid packing large CSS, HTML, and JS changes into one monolithic edit when smaller modules/templates/assets would be clearer
- Prefer DRY code, but do not extract abstractions prematurely. Extract helpers only when logic is reused or the extraction makes the code materially easier to read or test.
- Keep data-shaping rules centralized. Token definitions, cost rules, source labels, and placeholder semantics should not be duplicated in several places.
- Favor explicit names over cleverness. Anyone reading the repo should be able to trace how dashboard numbers are derived.

## Data and UX rules

- Source provenance must stay visible. If a chart or summary only reflects a subset of OpenCode, Codex CLI, and Hermes, say so.
- Overview `Total Tokens` means full token volume: non-cache input + output assistant-message tokens + cache read/write. Session/model-history totals may still use `Session Tokens` semantics (`non-cache input + output`) when explicitly labeled.
- Unpriced or unsupported models must remain clearly labeled instead of guessed.
- Simulated/demo mode should stay deterministic enough for screenshots, regression checks, and design review.
- Tooltips and interactive affordances should work for hover, focus, and tap.
- Accessibility and keyboard interaction are part of done, not polish.

## Python / Flask guidance

- Keep query code, aggregation code, and response-shaping code straightforward and testable.
- Prefer small pure helpers for formatting, normalization, and aggregation boundaries.
- Avoid hidden global state beyond stable app configuration.
- When adding a new adapter or source, give it a clear boundary rather than scattering source-specific conditionals across unrelated routes.

## Frontend guidance

- Keep the dashboard visually compact, but not at the expense of clarity.
- Prefer readable dark-theme contrast and stable categorical colors.
- If inline JS or CSS becomes unwieldy, split it into dedicated static files.
- Avoid duplicating rendering logic across cards, charts, and filters; shared UI behavior should have one source of truth.

## Testing and verification

- Update or add tests for behavior changes. Do not rely on manual inspection alone.
- Use the repo's uv-native workflow:
  - `uv sync`
  - `uv run python -m unittest tests.test_app tests.test_readme -v`
  - `uv run python -m py_compile app.py scripts/snapshot_dashboard.py`
- If `uv` is not on `$PATH`, it usually lives at `~/miniconda3/bin/uv`; export `PATH="$HOME/miniconda3/bin:$PATH"` or call it directly instead of installing a second copy.
- For UI-affecting changes, also verify the rendered dashboard locally, and use simulated mode when deterministic output helps.

## Review workflow

- Before opening or updating a PR, review the diff for scope creep, duplicated logic, wording drift, and source-provenance regressions.
- For AGENTS.md, README, and other instruction/docs edits, check that the guidance matches the real repo commands and current file structure.
- If an instruction references a command, make sure that command actually works in this repo.

Simple local review pass:

```bash
scripts/review.sh
```

Equivalent manual commands:

```bash
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
uv run python -m unittest tests.test_app tests.test_readme -v
uv run python -m py_compile app.py scripts/snapshot_dashboard.py
```

For docs-only or AGENTS.md-only PRs, use this lightweight check:

```bash
REVIEW_MODE=docs scripts/review.sh
```

Review focus for this repo:

- Does the change keep token definitions, cost wording, and source labels consistent across backend, templates, tests, and README?
- Does it reduce clarity by hiding provenance or by mixing active data with planned adapters?
- Does it add file length or inline-script complexity without a good reason?
- If behavior changed, were tests updated to prove it?

## Repo conventions

- Keep secrets and machine-specific credentials out of the repo.
- Preserve concise, direct wording in UI and docs.
- When adding planned adapters, prefer honest placeholders such as `TBD` over fake completeness.
- If a change introduces a new source of truth, document it in README and keep the wording consistent across backend payloads, templates, and tests.
- Keep the `main` checkout clean. It exists to receive merges and run `scripts/review.sh`, not to host in-flight work. Use `git worktree list` to see active worktrees and `git worktree remove <path>` to retire them.
