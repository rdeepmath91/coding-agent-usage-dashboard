# Coding Agent Usage Dashboard

Local dashboard for inspecting coding-agent usage from your machine.

Right now the active source is OpenCode via its local SQLite database at
`~/.local/share/opencode/opencode.db`. The UI already leaves room for future
Codex CLI and Hermes adapters, but this README is intentionally about one thing:
getting the dashboard running locally and capturing snapshots.

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

- active source: OpenCode local SQLite DB
- total tokens = input + output assistant-message tokens
- cache read/write tokens are shown separately and excluded from total tokens
- unmatched model pricing stays unpriced instead of guessed

## Local verification

```bash
uv run python -m unittest tests.test_app tests.test_readme -v
uv run python -m py_compile app.py scripts/snapshot_dashboard.py
```
