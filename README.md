# Coding Agent Usage Dashboard

Local session and token usage viewer for coding agents. The first source adapter
reads directly from your local OpenCode SQLite database and renders a dark-themed
web dashboard; Codex and Hermes sources are tracked as follow-up work.

## Setup

```
cd coding-agent-usage-dashboard
pip install -r requirements.txt
python app.py
```

Open http://localhost:8321 in your browser.

The dashboard auto-detects your OpenCode database at
`~/.local/share/opencode/opencode.db`.

## Overview

- **Daily token chart** — daily stacked bar chart by model, with 7/30/90/all/custom ranges
- **Model breakdown** — each model's session count, total tokens, input tokens, output tokens, and secondary cache-read context
- **Usage history** — recent session feed with model, title, and token totals
- **Dark theme** — optimized for dense coding-agent usage data

## Data Source

Currently pulls from OpenCode's local SQLite database with read-only access. The
dashboard is structured to add more coding-agent sources without changing the UI
model. Cost is intentionally hidden for now. Cached tokens are shown only as
secondary context, separate from input/output totals.
