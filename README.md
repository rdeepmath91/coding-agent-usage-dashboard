# Coding Agent Usage Dashboard

Local dashboard for inspecting coding-agent usage from your machine.

Right now the active sources are:

- OpenCode via `~/.local/share/opencode/opencode.db`
- Codex CLI via `~/.codex/state_5.sqlite` plus rollout JSONL files referenced by that state DB

Hermes remains a planned adapter placeholder.

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
- estimated cost when a model can be matched to public OpenRouter pricing
- explicit tool/source labeling so the current OpenCode-backed totals are not ambiguous

## Current data rules

- active sources: OpenCode local SQLite DB; Codex local state DB plus rollout JSONL
- total tokens = non-cache input + output assistant-message tokens
- cache read/write tokens are shown separately and excluded from total tokens
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

Total tokens remain dashboard non-cache input + output. Cache read/write tokens are shown
separately and excluded from total tokens. Codex local JSONL does not expose
cache-write tokens, so the dashboard shows cache write as unavailable for Codex
instead of treating it as zero. The adapter does not infer token counts from
transcript text.

## Local verification

```bash
uv run python -m unittest tests.test_app tests.test_readme -v
uv run python -m py_compile app.py scripts/snapshot_dashboard.py
```
