# Coding Agent Usage Dashboard

Local session and token usage viewer for coding agents. The first source adapter
reads directly from your local OpenCode SQLite database and renders a dark-themed
web dashboard; Codex and Hermes sources are tracked as follow-up work.

## Setup

### Prerequisites

Requires [uv](https://docs.astral.sh/uv/) as the Python project/package manager.
Install it first if needed:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Alternative
pip install uv
```

### Install and run

```bash
cd coding-agent-usage-dashboard
uv venv
uv pip install -r requirements.txt
uv run python app.py
```

Open http://localhost:8321 in your browser.

The dashboard auto-detects your OpenCode database at
`~/.local/share/opencode/opencode.db`.

## Overview

- **Daily token chart** — daily stacked bar chart by model, with 7/30/90/all/custom ranges
- **Model breakdown** — each model's session count, total tokens, input tokens, output tokens, and secondary cache-read context
- **Usage history** — recent session feed with model, title, and token totals
- **Tool source scaffolding** — active OpenCode totals plus placeholders for Codex CLI and Hermes
- **Dark theme** — optimized for dense coding-agent usage data

## Data Source

Currently pulls from OpenCode's local SQLite database with read-only access. The
dashboard is structured to add more coding-agent sources without changing the UI
model. Total tokens are defined as input + output assistant-message tokens.
Cached tokens are shown only as secondary context, separate from input/output
totals.

## Cost estimates

Estimated costs use the latest public pricing fetched from OpenRouter's
`/api/v1/models` endpoint when a local model ID can be matched. Unmatched models
are shown as unpriced instead of guessed. Estimates combine input, output,
cache-read, and cache-write prices when those prices are available.

## Local QA

Capture a rendered localhost snapshot with Playwright:

```bash
uv run --with playwright python scripts/snapshot_dashboard.py --url http://localhost:8321
```

Screenshots and DOM summaries are written to `dashboard-snapshots/`.
