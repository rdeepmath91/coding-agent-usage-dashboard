#!/usr/bin/env python3
"""
Coding Agent Usage Dashboard — local session and token usage viewer.
Currently reads from ~/.local/share/opencode/opencode.db and serves a dark-themed web UI.
"""

import datetime
import json
import os
import random
import sqlite3
import time
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")


def display_path(path: str) -> str:
    """Return a stable, user-facing local path."""
    home = os.path.expanduser("~")
    return path.replace(home, "~", 1) if path.startswith(home) else path


TOOL_SOURCES = [
    {
        "id": "opencode",
        "label": "OpenCode",
        "status": "active",
        "status_label": "Active source",
        "source_type": "SQLite database",
        "source_path": display_path(DB_PATH),
        "repo_url": "https://github.com/anomalyco/opencode/",
        "color": "#3B82F6",
        "issue": None,
    },
    {
        "id": "codex",
        "label": "Codex CLI",
        "status": "placeholder",
        "status_label": "Planned adapter",
        "source_type": "Local session/history data",
        "source_path": "TBD",
        "repo_url": "https://github.com/openai/codex/",
        "color": "#BA68C8",
        "issue": None,
    },
    {
        "id": "hermes",
        "label": "Hermes",
        "status": "placeholder",
        "status_label": "Planned adapter",
        "source_type": "Local session/tool logs or session DB",
        "source_path": "TBD",
        "repo_url": "https://github.com/NousResearch/hermes-agent/",
        "color": "#EAB308",
        "issue": None,
    },
]

TOOL_COLOR_MAP = {t["id"]: t["color"] for t in TOOL_SOURCES}
KNOWN_TOOL_IDS = {t["id"] for t in TOOL_SOURCES}


def current_tool_sources() -> list[dict]:
    """Return tool source metadata with the active DB path baked in."""
    sources = []
    for source in TOOL_SOURCES:
        item = dict(source)
        if item["id"] == "opencode":
            item["source_path"] = display_path(DB_PATH)
        sources.append(item)
    return sources


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
PRICING_CACHE = {"fetched_at": 0.0, "prices": {}}

# Per-token fallback prices, keyed by normalized OpenRouter model ID.
# OpenRouter live pricing remains primary; these keep estimates available when
# the live endpoint is unavailable or missing fields for models we actively use.
HARDCODED_MODEL_PRICES = {
    "openai/gpt-5.5": {
        "prompt": "0.000005",
        "completion": "0.00003",
        "input_cache_read": "0.0000005",
    },
    "openai/gpt-5.4": {
        "prompt": "0.0000025",
        "completion": "0.000015",
        "input_cache_read": "0.00000025",
    },
    "openai/gpt-5.4-mini": {
        "prompt": "0.00000075",
        "completion": "0.0000045",
        "input_cache_read": "0.000000075",
    },
    "openai/gpt-5.3-codex": {
        "prompt": "0.00000175",
        "completion": "0.000014",
        "input_cache_read": "0.000000175",
    },
    "deepseek/deepseek-v4-flash:free": {
        "prompt": "0",
        "completion": "0",
    },
    "deepseek/deepseek-v4-flash": {
        "prompt": "0.0000001",
        "completion": "0.0000002",
        "input_cache_read": "0.00000002",
    },
    "deepseek/deepseek-v4-pro": {
        "prompt": "0.000000435",
        "completion": "0.00000087",
        "input_cache_read": "0.000000003625",
    },
    "moonshotai/kimi-k2.6": {
        "prompt": "0.00000073",
        "completion": "0.00000349",
        "input_cache_read": "0.00000025",
    },
    "qwen/qwen3.6-plus": {
        "prompt": "0.000000325",
        "completion": "0.00000195",
        "input_cache_write": "0.00000040625",
    },
    "minimax/minimax-m2.5:free": {
        "prompt": "0",
        "completion": "0",
    },
    "inclusionai/ling-2.6-flash": {
        "prompt": "0.00000001",
        "completion": "0.00000003",
        "input_cache_read": "0.000000002",
    },
}


def get_db():
    """Return a read-only connection to the OpenCode SQLite DB."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
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


QUALITATIVE_COLORS = [
    # Dark-background-safe categorical set. These are categories, not a gradient.
    # Keep this short: beyond ~8 hues, stacked bars become hard to compare.
    "#38BDF8",  # cyan
    "#F59E0B",  # amber
    "#22C55E",  # green
    "#8B5CF6",  # violet
    "#EC4899",  # pink
    "#14B8A6",  # teal
    "#F97316",  # orange
    "#64748B",  # slate
]

def chart_color(rank: int, model_id: str, provider: str) -> str:
    """Use rank-first colors so the chart adapts when model mix changes."""
    return QUALITATIVE_COLORS[rank % len(QUALITATIVE_COLORS)]


def parse_top_n(default: int = 8) -> int:
    """Top N visible chart models; remaining models are folded into Other."""
    raw = request.args.get("top_n", default, type=int)
    return max(3, min(raw or default, len(QUALITATIVE_COLORS)))


def tool_source_label(tool_id: str | None) -> str | None:
    if not tool_id:
        return None
    for source in current_tool_sources():
        if source["id"] == tool_id:
            return source["label"]
    return tool_id


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


def build_simulated_dataset(days: int | None = 31) -> dict:
    """Deterministic synthetic data for UI checks and screenshots."""
    window_days = days or 31
    window_days = max(7, min(window_days, 120))
    rng = random.Random(20260527)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=window_days - 1)
    date_keys = [
        (start + datetime.timedelta(days=i)).isoformat()
        for i in range(window_days)
    ]

    model_specs = [
        {"provider": "opencode-go", "model_id": "deepseek-v4-flash", "base": 180_000, "burst": 1.4, "session_ratio": 0.18},
        {"provider": "opencode-go", "model_id": "deepseek-v4-pro", "base": 120_000, "burst": 0.9, "session_ratio": 0.12},
        {"provider": "opencode-go", "model_id": "kimi-k2.5", "base": 90_000, "burst": 0.75, "session_ratio": 0.10},
        {"provider": "opencode-go", "model_id": "kimi-k2.6", "base": 260_000, "burst": 2.3, "session_ratio": 0.20},
        {"provider": "opencode-go", "model_id": "minimax-m2.7", "base": 80_000, "burst": 0.65, "session_ratio": 0.09},
        {"provider": "opencode-go", "model_id": "qwen3.6-plus", "base": 105_000, "burst": 0.82, "session_ratio": 0.11},
    ]

    daily = {}
    model_totals = {}
    history = []
    session_counter = 0

    for index, dt in enumerate(date_keys):
        daily[dt] = {}
        weekday_factor = 1.25 if index % 7 in {1, 2, 3} else 0.72
        burst_factor = 1.0
        if index == min(12, window_days - 1):
            burst_factor = 3.8
        elif index in {min(7, window_days - 1), min(16, window_days - 1)}:
            burst_factor = 2.1
        elif index > int(window_days * 0.78):
            burst_factor = 0.28

        for spec in model_specs:
            if index > int(window_days * 0.82) and spec["model_id"] not in {"kimi-k2.6", "deepseek-v4-flash"}:
                activity_factor = 0.0
            else:
                activity_factor = 0.82 + rng.random() * 0.42

            total_tokens = int(spec["base"] * weekday_factor * burst_factor * activity_factor)
            if total_tokens < 25_000:
                total_tokens = 0

            tokens_input = int(total_tokens * (0.56 + rng.random() * 0.1)) if total_tokens else 0
            tokens_output = max(total_tokens - tokens_input, 0)
            cache_read = int(tokens_input * (0.18 + rng.random() * 0.16)) if total_tokens else 0
            cache_write = int(tokens_input * (0.04 + rng.random() * 0.05)) if total_tokens else 0
            sessions = max(0, int(total_tokens / 95_000 * (0.8 + rng.random() * spec["session_ratio"]))) if total_tokens else 0
            messages = max(sessions, int(sessions * (1.6 + rng.random() * 1.7))) if total_tokens else 0

            chart_model_id = f'{spec["provider"]}/{spec["model_id"]}'
            daily[dt][chart_model_id] = {
                "sessions": sessions,
                "messages": messages,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "tokens_total": total_tokens,
                "cache_read": cache_read,
                "cache_write": cache_write,
            }
            model_totals[chart_model_id] = model_totals.get(chart_model_id, 0) + total_tokens

            if total_tokens and len(history) < 40:
                session_counter += 1
                created_at = datetime.datetime.fromisoformat(dt) + datetime.timedelta(hours=9 + (session_counter % 8), minutes=(session_counter * 7) % 60)
                history.append({
                    "id": f"sim-{session_counter:04d}",
                    "tool": "OpenCode",
                    "tool_id": "opencode",
                    "tool_color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
                    "source_path": "simulated dataset",
                    "title": f"Simulated {spec['model_id']} run {session_counter}",
                    "created": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "updated": (created_at + datetime.timedelta(minutes=15 + session_counter % 35)).strftime("%Y-%m-%d %H:%M:%S"),
                    "directory": f"~/sandbox/session-{session_counter:02d}",
                    "model": f"{spec['provider']}/{spec['model_id']}",
                    "messages": messages,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "tokens_total": total_tokens,
                    "files_changed": 2 + session_counter % 9,
                    "additions": 40 + session_counter * 5,
                    "deletions": 8 + session_counter * 2,
                })

    models = []
    ordered_model_ids = sorted(model_totals, key=lambda mid: model_totals[mid], reverse=True)
    for rank, chart_model_id in enumerate(ordered_model_ids):
        provider, model_id = chart_model_id.split("/", 1)
        aggregate = {
            "sessions": 0,
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "cache_read": 0,
            "cache_write": 0,
        }
        for day in daily.values():
            row = day.get(chart_model_id, {})
            for key in aggregate:
                aggregate[key] += row.get(key, 0)

        info = normalize_model(json.dumps({"id": model_id, "providerID": provider}))
        models.append({
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
            "source_path": "simulated dataset",
            "label": info["label"],
            "provider": info["provider"],
            "model_id": info["id"],
            "chart_model_id": chart_model_id,
            "rank": rank + 1,
            "sessions": aggregate["sessions"],
            "messages": aggregate["messages"],
            "tokens_input": aggregate["tokens_input"],
            "tokens_output": aggregate["tokens_output"],
            "tokens_total": aggregate["tokens_total"],
            "cache_read": aggregate["cache_read"],
            "cache_write": aggregate["cache_write"],
            "color": QUALITATIVE_COLORS[rank] if rank < len(QUALITATIVE_COLORS) else "#64748B",
            **estimate_cost(info["provider"], info["id"], aggregate["tokens_input"], aggregate["tokens_output"], aggregate["cache_read"], aggregate["cache_write"]),
        })

    total_sessions = sum(item["sessions"] for item in models)
    total_input = sum(item["tokens_input"] for item in models)
    total_output = sum(item["tokens_output"] for item in models)
    cache_read_total = sum(item["cache_read"] for item in models)
    cache_write_total = sum(item["cache_write"] for item in models)

    overview = {
        "total_sessions": total_sessions,
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_input + total_output,
        "cache_read": cache_read_total,
        "cache_write": cache_write_total,
        "first_session": date_keys[0],
        "last_session": date_keys[-1],
        "days": days,
        "active_tool": "opencode",
        "active_tool_label": "OpenCode (simulated)",
        "source_path": "simulated dataset",
        "token_total_definition": "input + output assistant-message tokens; cache read/write excluded",
        "tool_sources": [],
    }

    for source in current_tool_sources():
        item = dict(source)
        if item["id"] == "opencode":
            item.update({
                "status_label": "Simulated",
                "source_path": "simulated dataset",
                "sessions": total_sessions,
                "tokens_total": overview["total_tokens"],
                "tokens_input": total_input,
                "tokens_output": total_output,
                "cache_read": cache_read_total,
                "cache_write": cache_write_total,
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
        overview["tool_sources"].append(item)

    history.sort(key=lambda row: row["created"], reverse=True)
    return {
        "overview": overview,
        "models": models,
        "daily": daily,
        "dates": date_keys,
        "history": history,
    }


def openrouter_model_id(provider: str, model_id: str) -> str | None:
    """Best-effort mapping from local provider/model IDs to OpenRouter model IDs."""
    if not model_id:
        return None

    free = model_id.endswith("-free")
    base = model_id.removesuffix("-free")

    if "/" in base:
        return base
    if provider == "openai":
        return f"openai/{base}"
    if provider == "google":
        return f"google/{base}"
    if base.startswith("deepseek-"):
        suffix = ":free" if free else ""
        return f"deepseek/{base}{suffix}"
    if base.startswith("kimi-"):
        return f"moonshotai/{base}"
    if base.startswith("qwen"):
        return f"qwen/{base}"
    if base.startswith("minimax-"):
        suffix = ":free" if free else ""
        return f"minimax/{base}{suffix}"
    if base.startswith("ling-"):
        return f"inclusionai/{base}"
    return None


def openrouter_prices() -> dict:
    """Fetch public OpenRouter per-token pricing, cached for one hour."""
    now = time.time()
    if PRICING_CACHE["prices"] and now - PRICING_CACHE["fetched_at"] < 3600:
        return PRICING_CACHE["prices"]

    try:
        with urllib.request.urlopen(OPENROUTER_MODELS_URL, timeout=8) as response:
            payload = json.load(response)
        prices = {m.get("id"): m.get("pricing", {}) for m in payload.get("data", []) if m.get("id")}
        PRICING_CACHE.update({"fetched_at": now, "prices": prices})
        return prices
    except Exception:
        return PRICING_CACHE["prices"]


def estimate_cost(provider: str, model_id: str, tokens_input: int, tokens_output: int, cache_read: int = 0, cache_write: int = 0) -> dict:
    """Estimate USD cost from token counts using latest fetched OpenRouter pricing."""
    router_id = openrouter_model_id(provider, model_id)
    fallback_pricing = HARDCODED_MODEL_PRICES.get(router_id or "", {})
    fetched_pricing = openrouter_prices().get(router_id or "", {})
    pricing = {**fallback_pricing, **fetched_pricing}

    def price(key: str) -> float:
        try:
            return float(pricing.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    if not pricing:
        return {
            "estimated_cost": None,
            "pricing_status": "unpriced",
            "pricing_source": None,
            "pricing_model_id": router_id,
        }

    estimated = (
        (tokens_input or 0) * price("prompt")
        + (tokens_output or 0) * price("completion")
        + (cache_read or 0) * price("input_cache_read")
        + (cache_write or 0) * price("input_cache_write")
    )
    return {
        "estimated_cost": estimated,
        "pricing_status": "priced",
        "pricing_source": "OpenRouter /api/v1/models" if fetched_pricing else "Hardcoded pricing fallback",
        "pricing_model_id": router_id,
        "input_price": price("prompt"),
        "output_price": price("completion"),
        "cache_read_price": price("input_cache_read"),
        "cache_write_price": price("input_cache_write"),
    }


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
    row["days"] = days
    row["active_tool"] = "opencode"
    row["active_tool_label"] = "OpenCode"
    row["source_path"] = display_path(DB_PATH)
    row["token_total_definition"] = "input + output assistant-message tokens; cache read/write excluded"
    row["tool_sources"] = []
    for source in current_tool_sources():
        item = dict(source)
        if item["id"] == "opencode":
            item.update({
                "sessions": row["total_sessions"],
                "tokens_total": row["total_tokens"],
                "tokens_input": row["total_input"],
                "tokens_output": row["total_output"],
                "cache_read": row["cache_read"],
                "cache_write": row["cache_write"],
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
        ORDER BY (tokens_input + tokens_output) DESC
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
            "cache_read": cache_read,
            "cache_write": cache_write,
            "color": QUALITATIVE_COLORS[rank] if rank < len(QUALITATIVE_COLORS) else "#64748B",
            **estimate_cost(info["provider"], info["id"], tokens_input, tokens_output, cache_read, cache_write),
        })
    conn.close()
    return jsonify(models)


@app.route("/api/daily")
def api_daily():
    """Daily token breakdown by model, attributed per assistant message."""
    days = parse_days(default=31)
    top_n = parse_top_n(default=8)
    selected_model_id = request.args.get("model_id") or None
    selected_tool_id = request.args.get("tool_id") or None
    if selected_tool_id and selected_tool_id != "opencode":
        if selected_tool_id in KNOWN_TOOL_IDS:
            source_label = tool_source_label(selected_tool_id) or selected_tool_id
            return empty_daily_response(
                top_n,
                selected_tool_id,
                error_message=f"{source_label} is planned and not connected yet.",
            )
        return empty_daily_response(
            top_n,
            None,
            error_message=f"Unsupported tool_id: {selected_tool_id}.",
        )
    if simulate_enabled():
        simulated = build_simulated_dataset(days)
        daily_data = simulated["daily"]
        dates = simulated["dates"]
        all_models_ordered = [item["chart_model_id"] for item in simulated["models"]]
        model_map = {
            item["chart_model_id"]: {
                "label": item["label"],
                "model_id": item["model_id"],
                "provider": item["provider"],
                "color": item["color"],
            }
            for item in simulated["models"]
        }
        model_totals = {item["chart_model_id"]: item["tokens_total"] for item in simulated["models"]}
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
                    "cache_read": 0,
                    "cache_write": 0,
                })
                for mid in top_models
            }
            other = {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0, "cache_read": 0, "cache_write": 0}
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
                "tokens_total": model_totals.get(mid, 0),
                "rank": rank + 1,
            })
        if not selected_model_id and any("other" in chart_data[dt] for dt in dates):
            chart_models.append({
                "id": "other",
                "label": f"Other ({len(other_models)} models)",
                "color": "#64748B",
                "tokens_total": sum(model_totals.get(mid, 0) for mid in other_models),
                "rank": None,
            })
            for dt in dates:
                chart_data[dt].setdefault(
                    "other",
                    {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0},
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
            "cache_read": row["cache_read"] or 0,
            "cache_write": row["cache_write"] or 0,
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
                "cache_read": 0,
                "cache_write": 0,
            })

    conn.close()

    model_totals = {}
    for dt in dates:
        for mid in all_models_ordered:
            model_totals[mid] = model_totals.get(mid, 0) + daily_data[dt][mid]["tokens_total"]
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
                "cache_read": 0,
                "cache_write": 0,
            })
            for mid in top_models
        }
        other = {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0, "cache_read": 0, "cache_write": 0}
        for mid in other_models:
            row = daily_data[dt].get(mid)
            if not row:
                continue
            other["sessions"] += row["sessions"]
            other["messages"] += row["messages"]
            other["tokens_input"] += row["tokens_input"]
            other["tokens_output"] += row["tokens_output"]
            other["tokens_total"] += row["tokens_total"]
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
            "tokens_total": model_totals.get(mid, 0),
            "rank": rank + 1,
        })
    if not selected_model_id and any("other" in chart_data[dt] for dt in dates):
        chart_models.append({
            "id": "other",
            "label": f"Other ({len(other_models)} models)",
            "color": "#64748B",
            "tokens_total": sum(model_totals.get(mid, 0) for mid in other_models),
            "rank": None,
        })
        for dt in dates:
            chart_data[dt].setdefault(
                "other",
                {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0},
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
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
            "source_path": display_path(DB_PATH),
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


# ── Main ────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8321))
    print(f"◆ Coding Agent Usage Dashboard → http://localhost:{port}")
    print(f"◆ Database: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
