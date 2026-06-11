# Coding Agent Usage Dashboard

Local dashboard for inspecting coding-agent usage from your machine.

## Data Sources

Right now the active sources are:

- OpenCode via `~/.local/share/opencode/opencode.db`
- Codex CLI via `~/.codex/state_5.sqlite` plus rollout JSONL files referenced by that state DB
- Hermes via `~/.hermes/state.db`

## Setup

### 1. Install uv

This repo uses [uv](https://docs.astral.sh/uv/) as a proper project environment,
so the committed `pyproject.toml` and `uv.lock` are the source of truth for a
reproducible local setup.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# alternative
pip install uv
```

### 2. Sync the project environment

```bash
cd coding-agent-usage-dashboard
uv sync
```

That creates the local environment from the committed lockfile.

### 3. Run the dashboard

```bash
uv run python app.py
```

Then open:

```text
http://localhost:8321
```

For a deterministic fake dataset that is useful for screenshots and UI checks,
open:

```text
http://localhost:8321/?simulate=1
```

## Screenshots

All screenshots use the simulated dataset from `?simulate=1`, so the examples are deterministic for docs, screenshots, and regression checks.

### Overview

<img src="docs/screenshots/dashboard-overview.png" alt="Dashboard overview cards" width="800">

The overview cards show full token volume, API-equivalent estimated cost, input/output split, and session count for the selected range.

### Tool Sources

<img src="docs/screenshots/dashboard-tool-sources.png" alt="Dashboard tool sources" width="800">

Tool Sources shows how OpenCode, Codex CLI, and Hermes can all contribute to dashboard totals while keeping source provenance visible.

### Daily Tokens by Model

<img src="docs/screenshots/dashboard-daily-tokens.png" alt="Dashboard daily tokens chart" width="800">

Daily Tokens by Model shows stacked model usage over time, with categorical colors and source filtering.

### Model Breakdown

<img src="docs/screenshots/dashboard-model-breakdown.png" alt="Dashboard model breakdown table" width="800">

Model Breakdown lists sessions, token totals, cache read, and pricing status per model. Table totals use session-token semantics: non-cache input plus output.

### Usage History

<img src="docs/screenshots/dashboard-usage-history.png" alt="Dashboard usage history table" width="800">

Usage History shows recent sessions with source, date, model, title, and token details.

## What the dashboard shows

- daily usage by model
- model breakdown with token totals
- recent usage history
- API-equivalent estimated cost when a model can be matched to public provider pricing
- explicit tool/source labeling so multi-source totals are not ambiguous

## Current data rules

- active sources: OpenCode local SQLite DB; Codex local state DB plus rollout JSONL; Hermes local session DB
- top-level Overview `Total Tokens` = non-cache input + output assistant-message tokens + cache read/write
- top-level Overview `Input Tokens` = non-cache input + cache read/write
- session/model-history token totals use session-token semantics: non-cache input + output assistant-message tokens
- API-equivalent estimated cost can include priced cache read/write tokens, so cost can be driven by cached context as well as fresh input/output
- subscription-backed tools may not bill like public API pricing, so estimated cost is not necessarily actual subscription spend
- raw provider input can include cached tokens; adapters subtract cache read where needed before reporting dashboard input
- unmatched model pricing stays unpriced instead of guessed

### Codex source contract

The Codex adapter reads session metadata from `~/.codex/state_5.sqlite`, table
`threads`. The trusted metadata fields are session id, rollout path, created and
updated timestamps, title/preview, cwd, provider, and model.

Token metrics come from the latest cumulative `total_token_usage` object in each
referenced rollout JSONL file. The trusted token fields are:

- `input_tokens` → raw Codex input, including cached input
- `cached_input_tokens` → cache read tokens
- `input_tokens - cached_input_tokens` → dashboard input, to match OpenCode's non-cache input semantics
- `output_tokens` → output tokens

The adapter filters, groups, sorts, and displays Codex records by thread `updated_at`, not `created_at`, because token metrics are latest cumulative rollout usage for the thread. This keeps long-lived threads updated inside the selected range from appearing on out-of-range created dates.

Adapter session tokens remain non-cache input + output. Cache read tokens are preserved so the Overview can add them into full `Total Tokens`. Codex local JSONL does not expose
cache-write tokens, so the dashboard shows cache write as unavailable for Codex
instead of treating it as zero. The adapter does not infer token counts from
transcript text.

### Hermes source contract

The Hermes adapter reads session metadata and token metrics from
`~/.hermes/state.db`, table `sessions`. The trusted metadata fields are session
id, source, title, started/ended timestamps, message/tool-call counts, provider,
and model.

The trusted token fields are:

- `input_tokens` → dashboard non-cache input tokens
- `output_tokens` → output tokens
- `cache_read_tokens` → cache read tokens
- `cache_write_tokens` → cache write tokens

Hermes records are filtered, grouped, sorted, and displayed by `started_at`.
Adapter session tokens remain input + output. Cache read/write tokens are preserved so the Overview can add them into full `Total Tokens`. The adapter does not infer token
counts from message text.

## Local verification

```bash
uv run python -m unittest tests.test_app tests.test_readme -v
uv run python -m py_compile app.py scripts/snapshot_dashboard.py
```
