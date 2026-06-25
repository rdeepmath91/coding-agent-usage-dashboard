"""Cached dashboard snapshots and OpenCode aggregation helpers."""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import threading
from collections import defaultdict, OrderedDict
from pathlib import Path
from time import perf_counter

from . import config as dashboard_config
from .config import display_path
from .pricing import chart_color, estimate_cost, normalize_model
from .sources import (
    aggregate_codex_models,
    aggregate_hermes_models,
    codex_overview,
    codex_records,
    get_db,
    hermes_overview,
    hermes_records,
)
from .token_metrics import effective_token_total

logger = logging.getLogger(__name__)

PROFILE_REQUESTS = str(os.environ.get("DASHBOARD_PROFILE", "")).strip().lower() in {"1", "true", "yes", "on"}
SNAPSHOT_CACHE_LIMIT = 8

_SNAPSHOT_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_SNAPSHOT_IN_FLIGHT: dict[tuple, threading.Event] = {}
_SNAPSHOT_LOCK = threading.Lock()


def _profile(message: str, start: float) -> None:
    if PROFILE_REQUESTS:
        logger.info("%s %.1fms", message, (perf_counter() - start) * 1000)


def _file_signature(path: str) -> tuple[str, int | None, int | None]:
    file_path = Path(path)
    try:
        stat = file_path.stat()
    except OSError:
        return (str(file_path), None, None)
    return (str(file_path), stat.st_mtime_ns, stat.st_size)


def _sqlite_live_signatures(path: str) -> tuple[tuple[str, int | None, int | None], ...]:
    return (
        _file_signature(path),
        _file_signature(f"{path}-wal"),
    )


def _codex_rollout_signatures() -> tuple[tuple[str, int | None, int | None], ...]:
    codex_state_path = dashboard_config.CODEX_STATE_PATH
    if not codex_state_path or not Path(codex_state_path).exists():
        return ()
    try:
        conn = sqlite3.connect(f"file:{codex_state_path}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        return ()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT rollout_path
            FROM threads
            WHERE rollout_path IS NOT NULL AND rollout_path != ''
            """
        ).fetchall()
    except (OSError, sqlite3.Error):
        return ()
    finally:
        conn.close()
    signatures = tuple(sorted({_file_signature(row[0]) for row in rows if row and row[0]}))
    return signatures


def _snapshot_key(days: int | None) -> tuple:
    return (
        days,
        *_sqlite_live_signatures(dashboard_config.DB_PATH),
        *_sqlite_live_signatures(dashboard_config.CODEX_STATE_PATH),
        *_codex_rollout_signatures(),
        _file_signature(dashboard_config.CODEX_SESSIONS_DIR),
        *_sqlite_live_signatures(dashboard_config.HERMES_STATE_PATH),
    )


def _since_clause(days: int | None) -> tuple[str, tuple]:
    if days is None:
        return "", ()
    since = (
        datetime.datetime.now() - datetime.timedelta(days=days)
    ).timestamp() * 1000
    return "WHERE time_created >= ?", (since,)


def _safe_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_opencode_sessions(days: int | None) -> list[dict]:
    where, params = _since_clause(days)
    conn = get_db()
    try:
        rows = conn.execute(f"""
            SELECT
                id,
                title,
                directory,
                model,
                tokens_input,
                tokens_output,
                summary_files,
                summary_additions,
                summary_deletions,
                time_created,
                time_updated
            FROM session
            {where}
            ORDER BY time_created DESC
        """, params).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _load_opencode_messages(days: int | None) -> list[dict]:
    where, params = _since_clause(days)
    msg_where = where.replace("time_created", "m.time_created")
    conn = get_db()
    try:
        rows = conn.execute(f"""
            SELECT
                m.time_created,
                m.session_id,
                date(m.time_created / 1000, 'unixepoch', 'localtime') as dt,
                json_extract(m.data, '$.modelID') as model_id,
                json_extract(m.data, '$.providerID') as provider,
                COALESCE(json_extract(m.data, '$.tokens.input'), 0) as tokens_input,
                COALESCE(json_extract(m.data, '$.tokens.output'), 0) as tokens_output,
                COALESCE(json_extract(m.data, '$.tokens.cache.read'), 0) as cache_read,
                COALESCE(json_extract(m.data, '$.tokens.cache.write'), 0) as cache_write
            FROM message m
            {msg_where + " AND" if msg_where else "WHERE"}
              json_valid(m.data)
              AND json_extract(m.data, '$.role') = 'assistant'
              AND json_extract(m.data, '$.modelID') IS NOT NULL
            ORDER BY m.time_created ASC
        """, params).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _load_opencode_snapshot(days: int | None) -> dict:
    sessions = _load_opencode_sessions(days)
    messages = _load_opencode_messages(days)

    overview = {
        "total_sessions": len(sessions),
        "total_input": 0,
        "total_output": 0,
        "total_tokens": 0,
        "session_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cache_total": 0,
        "first_session": None,
        "last_session": None,
        "days": days,
        "token_total_definition": "total token volume = input tokens + output tokens; includes cache read/write",
        "input_token_definition": "input tokens = non-cache input + cache read + cache write",
        "session_token_definition": "session tokens = non-cache input + output assistant-message tokens",
    }
    session_dates = []
    for row in sessions:
        created_ms = _safe_int(row.get("time_created"), 0)
        if not created_ms:
            continue
        session_dates.append(datetime.datetime.fromtimestamp(created_ms / 1000).date().isoformat())

    model_groups: dict[tuple[str, str], dict] = {}
    daily_groups: dict[tuple[str, str, str], dict] = {}
    session_models: dict[str, set[str]] = defaultdict(set)
    session_message_counts: dict[str, int] = defaultdict(int)
    model_meta_cache: dict[tuple[str, str], dict] = {}

    for row in messages:
        session_id = row["session_id"]
        provider = row["provider"] or "unknown"
        model_id = row["model_id"] or "unknown"
        tokens_input = _safe_int(row.get("tokens_input"), 0)
        tokens_output = _safe_int(row.get("tokens_output"), 0)
        cache_read = _safe_int(row.get("cache_read"), 0)
        cache_write = _safe_int(row.get("cache_write"), 0)
        total = tokens_input + tokens_output
        effective_total = effective_token_total(total, cache_read, cache_write)
        overview["total_input"] += tokens_input
        overview["total_output"] += tokens_output
        overview["total_tokens"] += total
        overview["session_tokens"] += total
        overview["cache_read"] += cache_read
        overview["cache_write"] += cache_write
        overview["cache_total"] += cache_read + cache_write

        model_key = (provider, model_id)
        model_group = model_groups.setdefault(model_key, {
            "session_ids": set(),
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "tokens_effective_total": 0,
            "cache_read": 0,
            "cache_write": 0,
        })
        model_group["session_ids"].add(session_id)
        model_group["messages"] += 1
        model_group["tokens_input"] += tokens_input
        model_group["tokens_output"] += tokens_output
        model_group["tokens_total"] += total
        model_group["tokens_effective_total"] += effective_total
        model_group["cache_read"] += cache_read
        model_group["cache_write"] += cache_write

        dt = row["dt"]
        daily_key = (dt, provider, model_id)
        daily_group = daily_groups.setdefault(daily_key, {
            "session_ids": set(),
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "tokens_effective_total": 0,
            "cache_read": 0,
            "cache_write": 0,
        })
        daily_group["session_ids"].add(session_id)
        daily_group["messages"] += 1
        daily_group["tokens_input"] += tokens_input
        daily_group["tokens_output"] += tokens_output
        daily_group["tokens_total"] += total
        daily_group["tokens_effective_total"] += effective_total
        daily_group["cache_read"] += cache_read
        daily_group["cache_write"] += cache_write

        session_models[session_id].add(f"{provider}/{model_id}")
        session_message_counts[session_id] += 1

    session_dates = [date for date in session_dates if date]
    if session_dates:
        overview["first_session"] = min(session_dates)
        overview["last_session"] = max(session_dates)

    def model_info(provider: str, model_id: str) -> dict:
        key = (provider, model_id)
        cached = model_meta_cache.get(key)
        if cached is None:
            cached = normalize_model(json.dumps({"id": model_id, "providerID": provider}))
            model_meta_cache[key] = cached
        return cached

    opencode_models = []
    for (provider, model_id), group in model_groups.items():
        info = model_info(provider, model_id)
        total = group["tokens_total"]
        cache_read = group["cache_read"]
        cache_write = group["cache_write"]
        opencode_models.append({
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": "#3B82F6",
            "source_path": display_path(dashboard_config.DB_PATH),
            "label": info["label"],
            "provider": info["provider"],
            "model_id": info["id"],
            "chart_model_id": f"{info['provider']}/{info['id']}",
            "sessions": len(group["session_ids"]),
            "messages": group["messages"],
            "tokens_input": group["tokens_input"],
            "tokens_output": group["tokens_output"],
            "tokens_total": total,
            "tokens_effective_total": group["tokens_effective_total"],
            "cache_read": cache_read,
            "cache_write": cache_write,
            "cache_write_available": True,
            **estimate_cost(info["provider"], info["id"], group["tokens_input"], group["tokens_output"], cache_read, cache_write),
        })

    opencode_models.sort(key=lambda item: item.get("tokens_effective_total") or 0, reverse=True)
    for rank, item in enumerate(opencode_models, start=1):
        item["rank"] = rank
        item["color"] = chart_color(rank - 1, item.get("model_id", ""), item.get("provider", ""))

    opencode_daily_records = []
    for (dt, provider, model_id), group in daily_groups.items():
        info = model_info(provider, model_id)
        opencode_daily_records.append({
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": "#3B82F6",
            "source_path": display_path(dashboard_config.DB_PATH),
            "date": dt,
            "label": info["label"],
            "provider": info["provider"],
            "model_id": info["id"],
            "chart_model_id": f"{info['provider']}/{info['id']}",
            "sessions": len(group["session_ids"]),
            "messages": group["messages"],
            "tokens_input": group["tokens_input"],
            "tokens_output": group["tokens_output"],
            "tokens_total": group["tokens_total"],
            "tokens_effective_total": group["tokens_effective_total"],
            "cache_read": group["cache_read"],
            "cache_write": group["cache_write"],
        })

    opencode_history = []
    for row in sessions:
        if not row.get("model"):
            continue
        session_id = row["id"]
        info = normalize_model(row["model"])
        model_label = " + ".join(sorted(session_models.get(session_id, set()))) or info["label"]
        created_ms = _safe_int(row.get("time_created"), 0)
        updated_ms = _safe_int(row.get("time_updated"), created_ms)
        created_dt = datetime.datetime.fromtimestamp(created_ms / 1000) if created_ms else None
        updated_dt = datetime.datetime.fromtimestamp(updated_ms / 1000) if updated_ms else None
        opencode_history.append({
            "id": session_id,
            "tool": "OpenCode",
            "tool_id": "opencode",
            "tool_color": "#3B82F6",
            "source_path": display_path(dashboard_config.DB_PATH),
            "title": row["title"],
            "created": created_dt.strftime("%Y-%m-%d %H:%M:%S") if created_dt else None,
            "updated": updated_dt.strftime("%Y-%m-%d %H:%M:%S") if updated_dt else None,
            "timestamp": created_ms,
            "directory": row["directory"],
            "model": model_label,
            "messages": session_message_counts.get(session_id, 0),
            "tokens_input": _safe_int(row.get("tokens_input"), 0),
            "tokens_output": _safe_int(row.get("tokens_output"), 0),
            "tokens_total": _safe_int(row.get("tokens_input"), 0) + _safe_int(row.get("tokens_output"), 0),
            "summary_files": _safe_int(row.get("summary_files"), 0),
            "summary_additions": _safe_int(row.get("summary_additions"), 0),
            "summary_deletions": _safe_int(row.get("summary_deletions"), 0),
        })

    return {
        "overview": overview,
        "models": opencode_models,
        "daily_records": opencode_daily_records,
        "history": opencode_history,
    }


def _build_snapshot(days: int | None) -> dict:
    started = perf_counter()
    snapshot = {"days": days}
    opencode_started = perf_counter()
    snapshot["opencode"] = _load_opencode_snapshot(days)
    _profile(f"snapshot opencode days={days}", opencode_started)

    codex_started = perf_counter()
    snapshot["codex_records"] = codex_records(days)
    snapshot["codex_overview"] = codex_overview(days, records=snapshot["codex_records"])
    snapshot["codex_models"] = aggregate_codex_models(days, records=snapshot["codex_records"])
    _profile(f"snapshot codex days={days}", codex_started)

    hermes_started = perf_counter()
    snapshot["hermes_records"] = hermes_records(days)
    snapshot["hermes_overview"] = hermes_overview(days, records=snapshot["hermes_records"])
    snapshot["hermes_models"] = aggregate_hermes_models(days, records=snapshot["hermes_records"])
    _profile(f"snapshot hermes days={days}", hermes_started)

    _profile(f"snapshot build days={days}", started)
    return snapshot


def load_dashboard_snapshot(days: int | None) -> dict:
    """Return a cached snapshot for the current source file state and range."""
    key = _snapshot_key(days)
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(key)
        if cached is not None:
            _SNAPSHOT_CACHE.move_to_end(key)
            if PROFILE_REQUESTS:
                logger.info("snapshot cache_hit days=%s", days)
            return cached
        inflight = _SNAPSHOT_IN_FLIGHT.get(key)
        if inflight is None:
            inflight = threading.Event()
            _SNAPSHOT_IN_FLIGHT[key] = inflight
            builder = True
        else:
            builder = False

    if not builder:
        inflight.wait()
        with _SNAPSHOT_LOCK:
            cached = _SNAPSHOT_CACHE.get(key)
            if cached is not None:
                _SNAPSHOT_CACHE.move_to_end(key)
                return cached
        return load_dashboard_snapshot(days)

    try:
        snapshot = _build_snapshot(days)
    except Exception:
        with _SNAPSHOT_LOCK:
            inflight = _SNAPSHOT_IN_FLIGHT.pop(key, None)
            if inflight is not None:
                inflight.set()
        raise

    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE[key] = snapshot
        _SNAPSHOT_CACHE.move_to_end(key)
        while len(_SNAPSHOT_CACHE) > SNAPSHOT_CACHE_LIMIT:
            _SNAPSHOT_CACHE.popitem(last=False)
        inflight = _SNAPSHOT_IN_FLIGHT.pop(key, None)
        if inflight is not None:
            inflight.set()
    return snapshot


def clear_dashboard_snapshot_cache() -> None:
    """Clear cached snapshots; useful for tests and manual refreshes."""
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE.clear()
        _SNAPSHOT_IN_FLIGHT.clear()
