#!/usr/bin/env python3
"""
OpenCode Dashboard — local session and token usage viewer.
Reads from ~/.local/share/opencode/opencode.db and serves a dark-themed web UI.
"""

import datetime
import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def get_db():
    """Return a read-only connection to the OpenCode SQLite DB."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=wal")
    return conn


def parse_days(default: int | None = 30) -> int | None:
    """Parse a days=N query param. 0/all means all time."""
    raw = request.args.get("days")
    if raw is None:
        return default
    if str(raw).lower() in {"all", "0", ""}:
        return None
    try:
        days = int(raw)
    except ValueError:
        return default
    return None if days <= 0 else min(days, 3650)


def since_clause(days: int | None) -> tuple[str, tuple]:
    if days is None:
        return "", ()
    since = (
        datetime.datetime.now() - datetime.timedelta(days=days)
    ).timestamp() * 1000
    return "WHERE time_created >= ?", (since,)


def normalize_model(raw: str) -> dict:
    """Parse a model JSON or ID string into short name + provider."""
    if not raw:
        return {"id": "unknown", "provider": "unknown", "label": "Unknown"}

    import json

    try:
        obj = json.loads(raw)
        model_id = obj.get("id", "unknown")
        provider = obj.get("providerID", "unknown")
        variant = obj.get("variant", "")
    except (json.JSONDecodeError, TypeError):
        model_id = raw
        provider = "unknown"
        variant = ""

    # Build a clean display label
    label = model_id
    if provider == "opencode-go":
        label = f"{model_id} (go)"
    elif provider == "opencode":
        label = model_id
    elif provider == "openai":
        label = f"{model_id} (openai)"
    elif provider:
        label = f"{model_id}"

    return {"id": model_id, "provider": provider, "label": label, "variant": variant}


def get_color(model_id: str) -> str:
    """Consistent color per model for stacked charts."""
    palette = {
        "deepseek-v4-flash": "#5B8C5A",
        "deepseek-v4-flash-free": "#8BC34A",
        "deepseek-v4-pro": "#7B5EA7",
        "kimi-k2.5": "#A5D6A7",
        "kimi-k2.6": "#2E7D32",
        "minimax-m2.7": "#2196F3",
        "qwen3.6-plus": "#795548",
        "qwen3.6-plus-free": "#A1887F",
        "gpt-5.5": "#FF9800",
        "gpt-5.5-fast": "#FFB74D",
        "gemini-2.5-flash": "#00BCD4",
        "gemini-2.5-pro": "#0097A7",
        "anthropic/claude-sonnet-4": "#D32F2F",
        "gemma": "#607D8B",
    }
    # Exact match first
    if model_id in palette:
        return palette[model_id]
    # Prefix match for gemini variants
    if model_id.startswith("gemini-"):
        base = "gemini-2.5-flash"
        h = hash(model_id)
        return "#" + format(h & 0xFFFFFF, "06x")
    if model_id.startswith("antigravity-"):
        h = hash(model_id)
        return "#" + format(h & 0xFFFFFF, "06x")
    # Hash for unknowns
    return "#" + format(hash(model_id) & 0xFFFFFF, "06x")


# ── API Routes ──────────────────────────────────────────────────────────────


@app.route("/api/overview")
def api_overview():
    """Aggregate totals for a selected range; days=0/all means all time."""
    days = parse_days(default=None)
    where, params = since_clause(days)
    conn = get_db()
    cur = conn.execute(f"""
        SELECT
            COUNT(*) as total_sessions,
            COALESCE(SUM(tokens_input), 0) as total_input,
            COALESCE(SUM(tokens_output), 0) as total_output,
            COALESCE(SUM(tokens_input), 0) + COALESCE(SUM(tokens_output), 0) as total_tokens,
            MIN(date(time_created / 1000, 'unixepoch', 'localtime')) as first_session,
            MAX(date(time_created / 1000, 'unixepoch', 'localtime')) as last_session
        FROM session
        {where}
    """, params)
    row = dict(cur.fetchone())
    row["days"] = days
    conn.close()
    return jsonify(row)


@app.route("/api/models")
def api_models():
    """Session and token totals per model, attributed per assistant message."""
    days = parse_days(default=30)
    where, params = since_clause(days)
    msg_where = where.replace("time_created", "m.time_created")

    conn = get_db()
    cur = conn.execute(f"""
        SELECT
            json_extract(m.data, '$.modelID') as model_id,
            json_extract(m.data, '$.providerID') as provider,
            COUNT(*) as messages,
            COUNT(DISTINCT m.session_id) as sessions,
            COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0) as tokens_input,
            COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0) as tokens_output
        FROM message m
        {msg_where + " AND" if msg_where else "WHERE"}
          json_valid(m.data)
          AND json_extract(m.data, '$.role') = 'assistant'
          AND json_extract(m.data, '$.modelID') IS NOT NULL
        GROUP BY model_id, provider
        ORDER BY (tokens_input + tokens_output) DESC
    """, params)

    models = []
    for row in cur.fetchall():
        raw = {"id": row["model_id"], "providerID": row["provider"]}
        import json
        info = normalize_model(json.dumps(raw))
        total = (row["tokens_input"] or 0) + (row["tokens_output"] or 0)
        models.append({
            "label": info["label"],
            "provider": info["provider"],
            "model_id": info["id"],
            "sessions": row["sessions"] or 0,
            "messages": row["messages"] or 0,
            "tokens_input": row["tokens_input"] or 0,
            "tokens_output": row["tokens_output"] or 0,
            "tokens_total": total,
            "color": get_color(info["id"]),
        })
    conn.close()
    return jsonify(models)


@app.route("/api/daily")
def api_daily():
    """Daily token breakdown by model, attributed per assistant message."""
    days = parse_days(default=31)
    where, params = since_clause(days)
    msg_where = where.replace("time_created", "m.time_created")

    conn = get_db()
    cur = conn.execute(f"""
        SELECT
            date(m.time_created / 1000, 'unixepoch', 'localtime') as dt,
            json_extract(m.data, '$.modelID') as model_id,
            json_extract(m.data, '$.providerID') as provider,
            COUNT(*) as messages,
            COUNT(DISTINCT m.session_id) as sessions,
            COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0) as tokens_input,
            COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0) as tokens_output
        FROM message m
        {msg_where + " AND" if msg_where else "WHERE"}
          json_valid(m.data)
          AND json_extract(m.data, '$.role') = 'assistant'
          AND json_extract(m.data, '$.modelID') IS NOT NULL
        GROUP BY dt, model_id, provider
        ORDER BY dt, (tokens_input + tokens_output) DESC
    """, params)

    daily_data = {}
    model_map = {}
    all_models_ordered = []

    import json
    for row in cur.fetchall():
        raw = {"id": row["model_id"], "providerID": row["provider"]}
        info = normalize_model(json.dumps(raw))
        dt = row["dt"]
        model_id = f"{info['provider']}/{info['id']}"
        label = info["label"]
        total = (row["tokens_input"] or 0) + (row["tokens_output"] or 0)

        if model_id not in model_map:
            model_map[model_id] = {"label": label, "color": get_color(info["id"])}
            all_models_ordered.append(model_id)

        daily_data.setdefault(dt, {})
        daily_data[dt][model_id] = {
            "sessions": row["sessions"] or 0,
            "messages": row["messages"] or 0,
            "tokens_input": row["tokens_input"] or 0,
            "tokens_output": row["tokens_output"] or 0,
            "tokens_total": total,
        }

    dates = sorted(daily_data.keys())
    for dt in dates:
        for mid in all_models_ordered:
            daily_data[dt].setdefault(mid, {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
            })

    conn.close()

    model_totals = {}
    for dt in dates:
        for mid in all_models_ordered:
            model_totals[mid] = model_totals.get(mid, 0) + daily_data[dt][mid]["tokens_total"]
    all_models_ordered.sort(key=lambda m: model_totals.get(m, 0), reverse=True)

    top_n = 8
    active_models = [m for m in all_models_ordered if model_totals.get(m, 0) > 0]
    top_models = active_models[:top_n]
    other_models = [m for m in all_models_ordered if m not in top_models]

    chart_data = {}
    for dt in dates:
        chart_data[dt] = {
            mid: daily_data[dt].get(mid, {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
            })
            for mid in top_models
        }
        other = {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0}
        for mid in other_models:
            row = daily_data[dt].get(mid)
            if not row:
                continue
            other["sessions"] += row["sessions"]
            other["messages"] += row["messages"]
            other["tokens_input"] += row["tokens_input"]
            other["tokens_output"] += row["tokens_output"]
            other["tokens_total"] += row["tokens_total"]
        if other["tokens_total"] > 0 or other["sessions"] > 0:
            chart_data[dt]["other"] = other

    chart_models = [
        {"id": mid, "label": model_map[mid]["label"], "color": model_map[mid]["color"]}
        for mid in top_models
    ]
    if any("other" in chart_data[dt] for dt in dates):
        chart_models.append({"id": "other", "label": "Other", "color": "#646262"})
        for dt in dates:
            chart_data[dt].setdefault(
                "other",
                {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0},
            )

    return jsonify({"dates": dates, "models": chart_models, "data": chart_data})


@app.route("/api/usage-history")
def api_usage_history():
    """Recent sessions feed."""
    limit = request.args.get("limit", "50", type=int)
    offset = request.args.get("offset", "0", type=int)

    conn = get_db()
    cur = conn.execute("""
        WITH session_models AS (
            SELECT
                session_id,
                group_concat(DISTINCT json_extract(data, '$.providerID') || '/' || json_extract(data, '$.modelID')) as models,
                COUNT(*) as messages
            FROM message
            WHERE json_valid(data)
              AND json_extract(data, '$.role') = 'assistant'
              AND json_extract(data, '$.modelID') IS NOT NULL
            GROUP BY session_id
        )
        SELECT
            datetime(s.time_created / 1000, 'unixepoch', 'localtime') as created,
            datetime(s.time_updated / 1000, 'unixepoch', 'localtime') as updated,
            s.id,
            s.title,
            s.directory,
            s.model,
            sm.models,
            sm.messages,
            s.tokens_input,
            s.tokens_output,
            s.summary_files,
            s.summary_additions,
            s.summary_deletions
        FROM session s
        LEFT JOIN session_models sm ON sm.session_id = s.id
        WHERE s.model IS NOT NULL AND s.model != ''
        ORDER BY s.time_created DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    sessions = []
    for row in cur.fetchall():
        info = normalize_model(row["model"])
        model_label = row["models"] or info["label"]
        sessions.append({
            "id": row["id"],
            "title": row["title"],
            "created": row["created"],
            "updated": row["updated"],
            "directory": row["directory"],
            "model": model_label,
            "messages": row["messages"] or 0,
            "tokens_input": row["tokens_input"] or 0,
            "tokens_output": row["tokens_output"] or 0,
            "tokens_total": (row["tokens_input"] or 0) + (row["tokens_output"] or 0),
            "files_changed": row["summary_files"],
            "additions": row["summary_additions"],
            "deletions": row["summary_deletions"],
        })
    conn.close()
    return jsonify(sessions)


@app.route("/api/refresh")
def api_refresh():
    """Return the last session timestamp so the UI can poll for updates."""
    conn = get_db()
    cur = conn.execute(
        "SELECT MAX(time_updated) as max_ts FROM session"
    )
    row = cur.fetchone()
    conn.close()
    return jsonify({"last_updated": row["max_ts"] or 0})


# ── Page Routes ──────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/settings")
def settings():
    return render_template("settings.html")


# ── Main ────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8321))
    print(f"◆ OpenCode Dashboard → http://localhost:{port}")
    print(f"◆ Database: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
