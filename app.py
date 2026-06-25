#!/usr/bin/env python3
"""Coding Agent Usage Dashboard — Flask entrypoint and route layer."""

import datetime
import os
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from dashboard.config import (
    DB_PATH,
    CODEX_STATE_PATH,
    CODEX_SESSIONS_DIR,
    CODEX_SOURCE_PATH,
    CURSOR_SOURCE_PATH,
    HERMES_STATE_PATH,
    KNOWN_TOOL_IDS,
    TOOL_COLOR_MAP,
    current_tool_sources,
    display_path,
    tool_source_label,
)
from dashboard.daily import build_daily_from_model_records
from dashboard.pricing import QUALITATIVE_COLORS, chart_color, estimate_cost, normalize_model
from dashboard.simulation import build_simulated_dataset
from dashboard.token_metrics import effective_token_total
from dashboard.sources import (
    aggregate_codex_models,
    aggregate_cursor_models,
    aggregate_hermes_models,
    codex_overview,
    codex_records,
    cursor_overview,
    cursor_records,
    get_db,
    hermes_overview,
    hermes_records,
)

app = Flask(__name__)


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

def parse_top_n(default: int = 8) -> int:
    """Top N visible chart models; remaining models are folded into Other."""
    raw = request.args.get("top_n", default, type=int)
    return max(3, min(raw or default, len(QUALITATIVE_COLORS)))

def empty_daily_response(top_n: int, selected_tool_id: str | None, error_message: str | None = None):
    return jsonify({
        "dates": [],
        "models": [],
        "data": {},
        "top_n": top_n,
        "other_count": 0,
        "selected_model_id": None,
        "selected_tool_id": selected_tool_id,
        "selected_tool_label": tool_source_label(selected_tool_id),
        "error": error_message,
    })

def simulate_enabled() -> bool:
    raw = request.args.get("simulate") or request.args.get("demo") or os.environ.get("DASHBOARD_SIMULATE")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# ── API Routes ──────────────────────────────────────────────────────────────


@app.route("/api/overview")
def api_overview():
    """Aggregate totals for a selected range; days=0/all means all time."""
    days = parse_days(default=None)
    if simulate_enabled():
        return jsonify(build_simulated_dataset(days)["overview"])
    where, params = since_clause(days)
    msg_where = where.replace("time_created", "m.time_created")
    conn = get_db()
    cur = conn.execute(f"""
        WITH session_stats AS (
            SELECT
                COUNT(*) as total_sessions,
                MIN(date(time_created / 1000, 'unixepoch', 'localtime')) as first_session,
                MAX(date(time_created / 1000, 'unixepoch', 'localtime')) as last_session
            FROM session
            {where}
        ), message_stats AS (
            SELECT
                COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0) as total_input,
                COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0) as total_output,
                COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0) as cache_read,
                COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0) as cache_write
            FROM message m
            {msg_where + " AND" if msg_where else "WHERE"}
              json_valid(m.data)
              AND json_extract(m.data, '$.role') = 'assistant'
              AND json_extract(m.data, '$.modelID') IS NOT NULL
        )
        SELECT
            session_stats.total_sessions,
            message_stats.total_input,
            message_stats.total_output,
            message_stats.total_input + message_stats.total_output as total_tokens,
            message_stats.cache_read,
            message_stats.cache_write,
            session_stats.first_session,
            session_stats.last_session
        FROM session_stats CROSS JOIN message_stats
    """, params + params)
    row = dict(cur.fetchone())
    codex = codex_overview(days)
    hermes = hermes_overview(days)
    cursor = cursor_overview(days)
    row["days"] = days
    row["token_total_definition"] = "total token volume = input tokens + output tokens; includes cache read/write"
    row["input_token_definition"] = "input tokens = non-cache input + cache read + cache write"
    row["session_token_definition"] = "session tokens = non-cache input + output assistant-message tokens"

    def overview_token_totals(sessions, tokens_input, tokens_output, cache_read, cache_write, metrics_note=None):
        non_cache_input = tokens_input or 0
        output = tokens_output or 0
        read = cache_read or 0
        write = cache_write or 0
        session_tokens = non_cache_input + output
        input_tokens = non_cache_input + read + write
        total_tokens = session_tokens + read + write
        totals = {
            "sessions": sessions,
            "tokens_total": total_tokens,
            "session_tokens": session_tokens,
            "tokens_input": input_tokens,
            "non_cache_input": non_cache_input,
            "tokens_output": output,
            "cache_read": read,
            "cache_write": cache_write,
            "cache_total": read + write,
        }
        if metrics_note:
            totals["metrics_note"] = metrics_note
        return totals

    opencode_totals = overview_token_totals(
        row["total_sessions"],
        row["total_input"],
        row["total_output"],
        row["cache_read"],
        row["cache_write"],
    )
    source_overviews = {"opencode": opencode_totals}
    if codex:
        source_overviews["codex"] = overview_token_totals(
            codex["total_sessions"],
            codex["total_input"],
            codex["total_output"],
            codex["cache_read"],
            None,
            "Cache write unavailable in local Codex JSONL.",
        )
    if hermes:
        source_overviews["hermes"] = overview_token_totals(
            hermes["total_sessions"],
            hermes["total_input"],
            hermes["total_output"],
            hermes["cache_read"],
            hermes["cache_write"],
            "Hermes token metrics come from ~/.hermes/state.db sessions columns.",
        )
    if cursor:
        source_overviews["cursor"] = overview_token_totals(
            cursor["total_sessions"],
            cursor["total_input"],
            cursor["total_output"],
            cursor["cache_read"],
            cursor["cache_write"],
            cursor.get("metrics_note"),
        )
    row.update({
        "total_sessions": 0,
        "total_input": 0,
        "non_cache_input": 0,
        "total_output": 0,
        "total_tokens": 0,
        "session_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cache_total": 0,
    })
    for totals in source_overviews.values():
        row["total_sessions"] += totals["sessions"] or 0
        row["total_input"] += totals["tokens_input"] or 0
        row["non_cache_input"] += totals["non_cache_input"] or 0
        row["total_output"] += totals["tokens_output"] or 0
        row["total_tokens"] += totals["tokens_total"] or 0
        row["session_tokens"] += totals["session_tokens"] or 0
        row["cache_read"] += totals["cache_read"] or 0
        if totals["cache_write"] is not None:
            row["cache_write"] += totals["cache_write"] or 0
        row["cache_total"] += totals["cache_total"] or 0

    session_dates = [row["first_session"], row["last_session"]]
    for overview in [codex, hermes, cursor]:
        if overview:
            session_dates.extend([overview["first_session"], overview["last_session"]])
    session_dates = [d for d in session_dates if d]
    if session_dates:
        row["first_session"] = min(session_dates)
        row["last_session"] = max(session_dates)

    current_sources = current_tool_sources()
    counted_sources = [source for source in current_sources if source["id"] in source_overviews]
    row["active_tool"] = "multiple" if len(counted_sources) > 1 else (counted_sources[0]["id"] if counted_sources else "opencode")
    row["active_tool_label"] = " + ".join(source["label"] for source in counted_sources) if counted_sources else "OpenCode"
    row["source_path"] = " + ".join(source["source_path"] for source in counted_sources) if counted_sources else display_path(DB_PATH)

    row["tool_sources"] = []
    for source in current_sources:
        item = dict(source)
        if item["id"] in source_overviews:
            item.update(source_overviews[item["id"]])
            if item["id"] == "cursor":
                item.update({
                    "cache_read": None,
                    "cache_write": None,
                    "cache_total": None,
                })
        else:
            item.update({
                "sessions": None,
                "tokens_total": None,
                "tokens_input": None,
                "tokens_output": None,
                "cache_read": None,
                "cache_write": None,
            })
        row["tool_sources"].append(item)
    conn.close()
    return jsonify(row)


@app.route("/api/models")
def api_models():
    """Session and token totals per model, attributed per assistant message."""
    days = parse_days(default=30)
    if simulate_enabled():
        return jsonify(build_simulated_dataset(days)["models"])
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
          COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0) as tokens_output,
          COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0) as cache_read,
          COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0) as cache_write
        FROM message m
        {msg_where + " AND" if msg_where else "WHERE"}
          json_valid(m.data)
          AND json_extract(m.data, '$.role') = 'assistant'
          AND json_extract(m.data, '$.modelID') IS NOT NULL
        GROUP BY model_id, provider
        ORDER BY (
            COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0)
        ) DESC
    """, params)

    models = []
    for rank, row in enumerate(cur.fetchall()):
        raw = {"id": row["model_id"], "providerID": row["provider"]}
        import json
        info = normalize_model(json.dumps(raw))
        total = (row["tokens_input"] or 0) + (row["tokens_output"] or 0)
        tokens_input = row["tokens_input"] or 0
        tokens_output = row["tokens_output"] or 0
        cache_read = row["cache_read"] or 0
        cache_write = row["cache_write"] or 0
        tokens_effective_total = effective_token_total(total, cache_read, cache_write)
        models.append({
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
            "source_path": display_path(DB_PATH),
            "label": info["label"],
            "provider": info["provider"],
            "model_id": info["id"],
            "chart_model_id": f"{info['provider']}/{info['id']}",
            "rank": rank + 1,
            "sessions": row["sessions"] or 0,
            "messages": row["messages"] or 0,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_total": total,
            "tokens_effective_total": tokens_effective_total,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "color": QUALITATIVE_COLORS[rank] if rank < len(QUALITATIVE_COLORS) else "#64748B",
            **estimate_cost(info["provider"], info["id"], tokens_input, tokens_output, cache_read, cache_write),
        })
    conn.close()
    models.extend(aggregate_codex_models(days))
    models.extend(aggregate_hermes_models(days))
    models.extend(aggregate_cursor_models(days))
    models.sort(key=lambda item: item.get("tokens_effective_total") or 0, reverse=True)
    for rank, model in enumerate(models, start=1):
        model["rank"] = rank
        model["color"] = chart_color(rank - 1, model.get("model_id", ""), model.get("provider", ""))
    return jsonify(models)


@app.route("/api/daily")
def api_daily():
    """Daily token breakdown by model, attributed per assistant message."""
    days = parse_days(default=31)
    top_n = parse_top_n(default=8)
    selected_model_id = request.args.get("model_id") or None
    selected_tool_id = request.args.get("tool_id") or None
    if selected_tool_id and selected_tool_id not in {"opencode", "codex", "hermes", "cursor"}:
        if selected_tool_id in KNOWN_TOOL_IDS:
            source_label = tool_source_label(selected_tool_id) or selected_tool_id
            return empty_daily_response(
                top_n,
                selected_tool_id,
                error_message=f"{source_label} is planned and not connected yet.",
            )
        return (
            jsonify({
                "error": f"Unsupported tool_id: {selected_tool_id}.",
                "dates": [],
                "models": [],
                "data": {},
                "top_n": top_n,
                "other_count": 0,
                "selected_model_id": None,
                "selected_tool_id": None,
                "selected_tool_label": None,
            }),
            400,
        )
    if simulate_enabled():
        simulated = build_simulated_dataset(days)
        daily_data = simulated["daily"]
        dates = simulated["dates"]
        simulated_models = [
            item for item in simulated["models"]
            if selected_tool_id is None or item.get("tool_id") == selected_tool_id
        ]
        all_models_ordered = [
            item["chart_model_id"]
            for item in sorted(
                simulated_models,
                key=lambda item: item.get("tokens_effective_total") or item.get("tokens_total") or 0,
                reverse=True,
            )
        ]
        model_map = {
            item["chart_model_id"]: {
                "label": item["label"],
                "model_id": item["model_id"],
                "provider": item["provider"],
                "color": item["color"],
            }
            for item in simulated_models
        }
        model_totals = {
            item["chart_model_id"]: item.get("tokens_effective_total") or item.get("tokens_total") or 0
            for item in simulated_models
        }
        model_total_display = {
            item["chart_model_id"]: item.get("tokens_total", 0)
            for item in simulated_models
        }
        active_models = [m for m in all_models_ordered if model_totals.get(m, 0) > 0]
        top_models = [selected_model_id] if selected_model_id in active_models else active_models[:top_n]
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
                    "tokens_effective_total": 0,
                    "cache_read": 0,
                    "cache_write": 0,
                })
                for mid in top_models
            }
            other = {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
                "tokens_effective_total": 0,
                "cache_read": 0,
                "cache_write": 0,
            }
            for mid in other_models:
                row = daily_data[dt].get(mid)
                if not row:
                    continue
                for key in other:
                    other[key] += row.get(key, 0)
            if not selected_model_id and (other["tokens_total"] > 0 or other["sessions"] > 0):
                chart_data[dt]["other"] = other

        chart_models = []
        for index, mid in enumerate(top_models):
            rank = active_models.index(mid) if mid in active_models else index
            meta = model_map[mid]
            chart_models.append({
                "id": mid,
                "label": meta["label"],
                "color": chart_color(rank, meta["model_id"], meta["provider"]),
                "tokens_total": model_total_display.get(mid, 0),
                "tokens_effective_total": model_totals.get(mid, 0),
                "rank": rank + 1,
            })
        if not selected_model_id and any("other" in chart_data[dt] for dt in dates):
            chart_models.append({
                "id": "other",
                "label": f"Other ({len(other_models)} models)",
                "color": "#64748B",
                "tokens_total": sum(model_total_display.get(mid, 0) for mid in other_models),
                "tokens_effective_total": sum(model_totals.get(mid, 0) for mid in other_models),
                "rank": None,
            })
            for dt in dates:
                chart_data[dt].setdefault(
                    "other",
                    {
                        "sessions": 0,
                        "messages": 0,
                        "tokens_input": 0,
                        "tokens_output": 0,
                        "tokens_total": 0,
                        "tokens_effective_total": 0,
                        "cache_read": 0,
                        "cache_write": 0,
                    },
                )

        return jsonify({
            "dates": dates,
            "models": chart_models,
            "data": chart_data,
            "top_n": top_n,
            "other_count": 0 if selected_model_id else len(other_models),
            "selected_model_id": selected_model_id if selected_model_id in active_models else None,
            "selected_tool_id": selected_tool_id,
            "selected_tool_label": tool_source_label(selected_tool_id),
        })
    if selected_tool_id == "codex":
        records = codex_records(days)
        if not records:
            return empty_daily_response(top_n, selected_tool_id, error_message="Codex CLI data is unavailable.")
        return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))
    if selected_tool_id == "hermes":
        records = hermes_records(days)
        if not records:
            return empty_daily_response(top_n, selected_tool_id, error_message="Hermes data is unavailable.")
        return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))
    if selected_tool_id == "cursor":
        records = cursor_records(days)
        if not records:
            return empty_daily_response(top_n, selected_tool_id, error_message="Cursor data is unavailable.")
        return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))

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
            COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0) as tokens_output,
            COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0) as cache_read,
            COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0) as cache_write
        FROM message m
        {msg_where + " AND" if msg_where else "WHERE"}
          json_valid(m.data)
          AND json_extract(m.data, '$.role') = 'assistant'
          AND json_extract(m.data, '$.modelID') IS NOT NULL
        GROUP BY dt, model_id, provider
        ORDER BY dt, (
          COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0)
          + COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0)
        ) DESC
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
        cache_read = row["cache_read"] or 0
        cache_write = row["cache_write"] or 0
        tokens_effective_total = effective_token_total(total, cache_read, cache_write)

        if model_id not in model_map:
            model_map[model_id] = {
                "label": label,
                "model_id": info["id"],
                "provider": info["provider"],
                "color": "#64748B",
            }
            all_models_ordered.append(model_id)

        daily_data.setdefault(dt, {})
        daily_data[dt][model_id] = {
            "sessions": row["sessions"] or 0,
            "messages": row["messages"] or 0,
            "tokens_input": row["tokens_input"] or 0,
            "tokens_output": row["tokens_output"] or 0,
            "tokens_total": total,
            "tokens_effective_total": tokens_effective_total,
            "cache_read": cache_read,
            "cache_write": cache_write,
        }

    if selected_tool_id is None:
        for record in codex_records(days) + hermes_records(days) + cursor_records(days):
            dt = record.get("date")
            if not dt:
                continue
            mid = record["chart_model_id"]
            if mid not in model_map:
                model_map[mid] = {
                    "label": record["label"],
                    "model_id": record["model_id"],
                    "provider": record["provider"],
                    "color": "#64748B",
                }
                all_models_ordered.append(mid)
            daily_data.setdefault(dt, {})
            bucket = daily_data[dt].setdefault(mid, {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
                "tokens_effective_total": 0,
                "cache_read": 0,
                "cache_write": 0,
            })
            bucket["sessions"] += 1
            bucket["messages"] += record.get("messages") or 0
            bucket["tokens_input"] += record.get("tokens_input") or 0
            bucket["tokens_output"] += record.get("tokens_output") or 0
            bucket["tokens_total"] += record.get("tokens_total") or 0
            bucket["tokens_effective_total"] += record.get("tokens_effective_total") or 0
            bucket["cache_read"] += record.get("cache_read") or 0
            bucket["cache_write"] += record.get("cache_write") or 0

    dates = sorted(daily_data.keys())
    for dt in dates:
        for mid in all_models_ordered:
            daily_data[dt].setdefault(mid, {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
                "tokens_effective_total": 0,
                "cache_read": 0,
                "cache_write": 0,
            })

    conn.close()

    model_totals = {}
    model_total_display = {}
    for dt in dates:
        for mid in all_models_ordered:
            model_totals[mid] = model_totals.get(mid, 0) + daily_data[dt][mid]["tokens_effective_total"]
            model_total_display[mid] = model_total_display.get(mid, 0) + daily_data[dt][mid]["tokens_total"]
    all_models_ordered.sort(key=lambda m: model_totals.get(m, 0), reverse=True)

    active_models = [m for m in all_models_ordered if model_totals.get(m, 0) > 0]
    top_models = [selected_model_id] if selected_model_id in active_models else active_models[:top_n]
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
                "tokens_effective_total": 0,
                "cache_read": 0,
                "cache_write": 0,
            })
            for mid in top_models
        }
        other = {
            "sessions": 0,
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "tokens_effective_total": 0,
            "cache_read": 0,
            "cache_write": 0,
        }
        for mid in other_models:
            row = daily_data[dt].get(mid)
            if not row:
                continue
            other["sessions"] += row["sessions"]
            other["messages"] += row["messages"]
            other["tokens_input"] += row["tokens_input"]
            other["tokens_output"] += row["tokens_output"]
            other["tokens_total"] += row["tokens_total"]
            other["tokens_effective_total"] += row.get("tokens_effective_total", 0) if isinstance(row, dict) else row["tokens_effective_total"]
            other["cache_read"] += row.get("cache_read", 0) if isinstance(row, dict) else row["cache_read"]
            other["cache_write"] += row.get("cache_write", 0) if isinstance(row, dict) else row["cache_write"]
        if not selected_model_id and (other["tokens_total"] > 0 or other["sessions"] > 0):
            chart_data[dt]["other"] = other

    chart_models = []
    for index, mid in enumerate(top_models):
        rank = active_models.index(mid) if mid in active_models else index
        meta = model_map[mid]
        chart_models.append({
            "id": mid,
            "label": meta["label"],
            "color": chart_color(rank, meta["model_id"], meta["provider"]),
            "tokens_total": model_total_display.get(mid, 0),
            "tokens_effective_total": model_totals.get(mid, 0),
            "rank": rank + 1,
        })
    if not selected_model_id and any("other" in chart_data[dt] for dt in dates):
        chart_models.append({
            "id": "other",
            "label": f"Other ({len(other_models)} models)",
            "color": "#64748B",
            "tokens_total": sum(model_total_display.get(mid, 0) for mid in other_models),
            "tokens_effective_total": sum(model_totals.get(mid, 0) for mid in other_models),
            "rank": None,
        })
        for dt in dates:
            chart_data[dt].setdefault("other", {
                "sessions": 0,
                "messages": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "tokens_total": 0,
                "tokens_effective_total": 0,
                "cache_read": 0,
                "cache_write": 0,
            })

    return jsonify({
        "dates": dates,
        "models": chart_models,
        "data": chart_data,
        "top_n": top_n,
        "other_count": 0 if selected_model_id else len(other_models),
        "selected_model_id": selected_model_id if selected_model_id in active_models else None,
        "selected_tool_id": selected_tool_id,
        "selected_tool_label": tool_source_label(selected_tool_id),
    })


@app.route("/api/usage-history")
def api_usage_history():
    """Recent sessions feed."""
    limit = request.args.get("limit", "50", type=int)
    offset = request.args.get("offset", "0", type=int)

    if simulate_enabled():
        history = build_simulated_dataset(31)["history"]
        start = int(offset or 0)
        count = int(limit or 50)
        return jsonify(history[start: start + count])

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
            s.time_created,
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
    """)

    sessions = []
    for row in cur.fetchall():
        info = normalize_model(row["model"])
        model_label = row["models"] or info["label"]
        sessions.append({
            "id": row["id"],
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
            "source_path": display_path(DB_PATH),
            "title": row["title"],
            "created": row["created"],
            "updated": row["updated"],
            "timestamp": row["time_created"],
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
    for record in codex_records(30) + hermes_records(30) + cursor_records(30):
        sessions.append({
            "id": record["id"],
            "tool": record["tool"],
            "tool_id": record["tool_id"],
            "tool_color": record["tool_color"],
            "source_path": record["source_path"],
            "title": record["title"],
            "created": record["created"],
            "updated": record["updated"],
            "timestamp": record["timestamp"],
            "directory": record["directory"],
            "model": record["model"],
            "messages": record["messages"],
            "tokens_input": record["tokens_input"],
            "tokens_output": record["tokens_output"],
            "tokens_total": record["tokens_total"],
            "cache_read": record["cache_read"],
            "cache_write": record["cache_write"],
            "metrics_note": record["metrics_note"],
            "files_changed": None,
            "additions": None,
            "deletions": None,
        })
    sessions.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    start = int(offset or 0)
    count = int(limit or 50)
    return jsonify(sessions[start: start + count])


@app.route("/api/refresh")
def api_refresh():
    """Return the last session timestamp so the UI can poll for updates."""
    if simulate_enabled():
        return jsonify({"last_updated": int(time.time() * 1000)})
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


@app.route("/favicon.ico")
def favicon():
    return Response(
        Path(app.root_path, "static", "favicon.svg").read_text(),
        mimetype="image/svg+xml",
    )


# ── Main ────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8321))
    print(f"◆ Coding Agent Usage Dashboard → http://localhost:{port}")
    print(f"◆ Database: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
