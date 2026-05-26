# OpenCode Dashboard

Local session and token usage viewer for OpenCode AI agent. Reads directly from your
local OpenCode SQLite database and renders a dark-themed web dashboard.

## Setup

```
cd opencode-dashboard
pip install -r requirements.txt
python app.py
```

Open http://localhost:8321 in your browser.

The dashboard auto-detects your OpenCode database at
`~/.local/share/opencode/opencode.db`.

## Overview

- **Daily token chart** — daily stacked bar chart by model, with 7/30/90/all/custom ranges
- **Model breakdown** — each model's session count, total tokens, input tokens, and output tokens
- **Usage history** — recent session feed with model, title, and token totals
- **Dark theme** — matches OpenCode's aesthetic

## Data Source

Pulls from the `session` table in OpenCode's local SQLite database. All reads
are read-only. Cost and cached-token fields are intentionally hidden for now.
