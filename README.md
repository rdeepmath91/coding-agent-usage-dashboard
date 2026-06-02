# Coding Agent Usage Dashboard

Local dashboard for inspecting coding-agent usage from your machine.

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

## Snapshots

Capture a localhost snapshot with Playwright:

```bash
uv run --with playwright python scripts/snapshot_dashboard.py --url http://localhost:8321
```

To snapshot the simulated dataset instead of your live local usage:

```bash
uv run --with playwright python scripts/snapshot_dashboard.py --url http://localhost:8321/?simulate=1
```

Outputs are written to:

```text
dashboard-snapshots/
```

That snapshot run produces a rendered screenshot plus a DOM summary so you can
review what the dashboard actually showed at capture time.

## What the dashboard shows

- daily usage by model
- model breakdown with token totals
- recent usage history
- API-equivalent estimated cost when a model can be matched to public provider pricing
- explicit tool/source labeling so multi-source totals are not ambiguous

## Current data rules

- active sources: OpenCode local SQLite DB; Codex local state DB plus rollout JSONL; Hermes local session DB
- total tokens = non-cache input + output assistant-message tokens
- cache read/write tokens are shown separately and excluded from total tokens
- API-equivalent estimated cost can include priced cache read/write tokens even though cache tokens are excluded from total tokens
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

Total tokens remain dashboard non-cache input + output. Cache read/write tokens are shown
separately and excluded from total tokens. Codex local JSONL does not expose
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
Total tokens remain dashboard input + output. Cache read/write tokens are shown
separately and excluded from total tokens. The adapter does not infer token
counts from message text.

## Local verification

```bash
uv run python -m unittest tests.test_app tests.test_readme -v
uv run python -m py_compile app.py scripts/snapshot_dashboard.py
```
