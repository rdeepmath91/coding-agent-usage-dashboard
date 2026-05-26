# OpenCode Dashboard

Local usage and cost viewer for OpenCode AI agent. Reads directly from your
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

- **Cost chart** — daily stacked bar chart by model, 7/30/90/all ranges
- **Model breakdown** — each model's session count, input/output tokens, cache
  hits, and total cost
- **Usage history** — recent session feed with model, title, and cost
- **Dark theme** — matches OpenCode's aesthetic

## Data Source

Pulls from the `session` table in OpenCode's local SQLite database. All reads
are read-only. Costs are what OpenCode recorded at session time.
