"""Local source adapters for OpenCode, Codex CLI, Hermes, and Cursor."""

import datetime
import json
import os
import sqlite3
from pathlib import Path

from . import config
from .config import display_path
from .pricing import estimate_cost, normalize_model, openrouter_model_url, pricing_model_resolution
from .token_metrics import effective_token_total


def get_db():
    """Return a read-only connection to the OpenCode SQLite DB."""
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def _jsonl_latest_codex_usage(path: str | None) -> tuple[dict | None, int]:
    """Return latest cumulative Codex token usage and count of token-bearing turns."""
    if not path or not Path(path).exists():
        return None, 0
    latest = None
    token_events = 0
    try:
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = obj.get("payload") if isinstance(obj, dict) else None
                if not isinstance(payload, dict):
                    continue
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue
                usage = info.get("total_token_usage")
                if isinstance(usage, dict):
                    latest = usage
                    token_events += 1
    except OSError:
        return None, 0
    return latest, token_events

def _safe_int(value, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def codex_records(days: int | None = None) -> list[dict]:
    """Normalize Codex CLI thread state + JSONL token events into dashboard records.

    Trust boundary: ~/.codex/state_5.sqlite is used for session metadata, while
    the latest cumulative `total_token_usage` in each rollout JSONL is used for
    token metrics. Codex records are windowed, grouped, sorted, and displayed by
    updated_at so a long-lived thread updated inside the selected range does not
    render on an out-of-range created_at date. Codex reports cached tokens inside
    `input_tokens`; the dashboard subtracts `cached_input_tokens` so the public
    input column is comparable with OpenCode's non-cache input. Codex does not
    expose cache-write tokens in this local format, so cache_write remains None.
    """
    if not config.codex_source_available():
        return []

    since_ms = None
    if days is not None:
        since_ms = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp() * 1000)

    def _fetch_rows_with_preview(conn, where: str, params: tuple) -> list[sqlite3.Row]:
        return conn.execute(f"""
            SELECT
                id,
                rollout_path,
                COALESCE(created_at_ms, created_at * 1000) as created_ms,
                COALESCE(updated_at_ms, updated_at * 1000) as updated_ms,
                model_provider,
                model,
                title,
                cwd,
                preview,
                tokens_used
            FROM threads
            {where}
            ORDER BY COALESCE(updated_at_ms, updated_at * 1000, created_at_ms, created_at * 1000) DESC
        """, params).fetchall()

    def _fetch_rows_without_preview(conn, where: str, params: tuple) -> list[sqlite3.Row]:
        return conn.execute(f"""
            SELECT
                id,
                rollout_path,
                COALESCE(created_at_ms, created_at * 1000) as created_ms,
                COALESCE(updated_at_ms, updated_at * 1000) as updated_ms,
                model_provider,
                model,
                title,
                cwd,
                tokens_used
            FROM threads
            {where}
            ORDER BY COALESCE(updated_at_ms, updated_at * 1000, created_at_ms, created_at * 1000) DESC
        """, params).fetchall()

    conn = sqlite3.connect(f"file:{config.CODEX_STATE_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    where = "WHERE COALESCE(updated_at_ms, updated_at * 1000, created_at_ms, created_at * 1000) >= ?" if since_ms else ""
    params = (since_ms,) if since_ms else ()
    try:
        try:
            rows = _fetch_rows_with_preview(conn, where, params)
        except sqlite3.OperationalError as e:
            if "no such column: preview" in str(e).lower():
                rows = _fetch_rows_without_preview(conn, where, params)
            else:
                raise
    finally:
        conn.close()

    records = []
    for row in rows:
        usage, token_events = _jsonl_latest_codex_usage(row["rollout_path"])
        if not usage:
            continue
        raw_input_tokens = _safe_int(usage.get("input_tokens"), None)
        output_tokens = _safe_int(usage.get("output_tokens"), None)
        cache_read = _safe_int(usage.get("cached_input_tokens"), None)
        input_tokens = raw_input_tokens
        if raw_input_tokens is not None and cache_read is not None:
            input_tokens = max(0, raw_input_tokens - cache_read)
        model_id = row["model"] or "unknown"
        provider = row["model_provider"] or "unknown"
        created_ms = _safe_int(row["created_ms"], 0) or 0
        updated_ms = _safe_int(row["updated_ms"], created_ms) or created_ms
        created_dt = datetime.datetime.fromtimestamp(created_ms / 1000) if created_ms else None
        updated_dt = datetime.datetime.fromtimestamp(updated_ms / 1000) if updated_ms else None
        records.append({
            "tool": "Codex CLI",
            "tool_id": "codex",
            "tool_color": config.TOOL_COLOR_MAP.get("codex", "#BA68C8"),
            "source_path": display_path(config.CODEX_SOURCE_PATH),
            "id": row["id"],
            "session_id": row["id"],
            "timestamp": updated_ms,
            "created": updated_dt.strftime("%Y-%m-%d %H:%M:%S") if updated_dt else None,
            "created_at": created_dt.strftime("%Y-%m-%d %H:%M:%S") if created_dt else None,
            "updated": updated_dt.strftime("%Y-%m-%d %H:%M:%S") if updated_dt else None,
            "date": updated_dt.date().isoformat() if updated_dt else None,
            "title": row["title"] or (row["preview"] if "preview" in row.keys() else "") or row["id"],
            "directory": row["cwd"],
            "provider": provider,
            "model_id": model_id,
            "model": f"{provider}/{model_id}",
            "chart_model_id": f"{provider}/{model_id}",
            "label": normalize_model(json.dumps({"id": model_id, "providerID": provider}))["label"],
            "sessions": 1,
            "messages": token_events,
            "tokens_input": input_tokens,
            "raw_tokens_input": raw_input_tokens,
            "tokens_output": output_tokens,
            "tokens_total": (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None and output_tokens is not None else None,
            "tokens_effective_total": effective_token_total(
                (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None and output_tokens is not None else None,
                cache_read,
                None,
            ),
            "cache_read": cache_read,
            "cache_write": None,
            "cache_write_available": False,
            "metrics_note": "Codex total_token_usage.input_tokens includes cached input; dashboard input subtracts cached_input_tokens so input/cache read match OpenCode semantics. Cache write is unavailable.",
            "files_changed": None,
            "additions": None,
            "deletions": None,
        })
    return records

def _sum_available(records: list[dict], key: str) -> int | None:
    values = [r.get(key) for r in records if r.get(key) is not None]
    if not values:
        return None
    return sum(values)

def _record_tool_source_totals(records: list[dict], source: dict) -> dict:
    item = dict(source)
    matching = [r for r in records if r.get("tool_id") == item["id"]]
    item.update({
        "sessions": len({r.get("session_id") or r.get("id") for r in matching}),
        "tokens_total": _sum_available(matching, "tokens_total"),
        "tokens_input": _sum_available(matching, "tokens_input"),
        "tokens_output": _sum_available(matching, "tokens_output"),
        "cache_read": _sum_available(matching, "cache_read"),
        "cache_write": _sum_available(matching, "cache_write"),
        "tokens_effective_total": (
            _sum_available(matching, "tokens_total") or 0
        ) + (
            _sum_available(matching, "cache_read") or 0
        ) + (
            _sum_available(matching, "cache_write") or 0
        ),
    })
    return item

def codex_overview(days: int | None = None, *, records: list[dict] | None = None) -> dict | None:
    records = records if records is not None else codex_records(days)
    if not records:
        return None
    dates = sorted({r["date"] for r in records if r.get("date")})
    total_input = _sum_available(records, "tokens_input") or 0
    total_output = _sum_available(records, "tokens_output") or 0
    return {
        "total_sessions": len({r["session_id"] for r in records}),
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_input + total_output,
        "cache_read": _sum_available(records, "cache_read") or 0,
        "cache_write": None,
        "first_session": dates[0] if dates else None,
        "last_session": dates[-1] if dates else None,
    }


def _cursor_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.CURSOR_STATE_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _cursor_nonzero_token_count(item: dict) -> dict | None:
    token_count = item.get("tokenCount")
    if not isinstance(token_count, dict):
        return None
    input_tokens = _safe_int(token_count.get("inputTokens"), 0) or 0
    output_tokens = _safe_int(token_count.get("outputTokens"), 0) or 0
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    return {"inputTokens": input_tokens, "outputTokens": output_tokens}


def _cursor_title(composer: dict) -> str:
    name = (composer.get("name") or "").strip()
    if name:
        return name[:120]
    for item in composer.get("conversation") or []:
        if item.get("type") != 1:
            continue
        text = (item.get("text") or "").strip()
        if text:
            return text.splitlines()[0][:120]
    return f"Cursor composer {composer.get('composerId', 'unknown')}"


def _cursor_workspace_paths(composer: dict) -> list[str]:
    paths = []
    context = composer.get("context") or {}
    for file_selection in context.get("fileSelections") or []:
        uri = file_selection.get("uri") or {}
        path = uri.get("fsPath")
        if path:
            paths.append(path)
    return paths


def _cursor_directory(composer: dict) -> str | None:
    paths = _cursor_workspace_paths(composer)
    if not paths:
        return None
    try:
        common = Path(os.path.commonpath(paths))
    except ValueError:
        return str(Path(paths[0]).parent)
    if common.is_file() or common.suffix:
        return str(common.parent)
    return str(common)


def _cursor_timestamp_ms(composer: dict, assistant_items: list[dict]) -> int:
    item_times = []
    for item in assistant_items:
        timing = item.get("timingInfo") or {}
        for key in ("clientEndTime", "clientSettleTime", "clientRpcSendTime", "clientStartTime"):
            ts = _safe_int(timing.get(key), None)
            if ts:
                item_times.append(ts)
                break
    for key in ("lastUpdatedAt", "createdAt"):
        ts = _safe_int(composer.get(key), None)
        if ts:
            item_times.append(ts)
    return max(item_times) if item_times else 0


def _cursor_header_timestamp_ms(composer: dict) -> int:
    item_times = []
    for item in composer.get("fullConversationHeadersOnly") or []:
        if not isinstance(item, dict):
            continue
        created_at = item.get("createdAt")
        if not created_at:
            continue
        try:
            item_times.append(int(datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp() * 1000))
        except ValueError:
            continue
    for key in ("lastUpdatedAt", "conversationCheckpointLastUpdatedAt", "createdAt"):
        ts = _safe_int(composer.get(key), None)
        if ts:
            item_times.append(ts)
    return max(item_times) if item_times else 0


def _cursor_prompt_total_tokens(composer: dict) -> int | None:
    prompt_breakdown = composer.get("promptTokenBreakdown") or {}
    total_used = _safe_int(prompt_breakdown.get("totalUsedTokens"), None)
    if total_used and total_used > 0:
        return total_used
    context_used = _safe_int(composer.get("contextTokensUsed"), None)
    if context_used and context_used > 0:
        return context_used
    return None


def _cursor_header_counts(composer: dict) -> tuple[int, int]:
    headers = [item for item in (composer.get("fullConversationHeadersOnly") or []) if isinstance(item, dict)]
    messages = len([item for item in headers if item.get("type") in {1, 2}])
    assistant_messages = len([item for item in headers if item.get("type") == 2])
    return messages, assistant_messages


def _cursor_session_record(composer: dict) -> dict | None:
    assistant_items = []
    for item in composer.get("conversation") or []:
        if not isinstance(item, dict) or item.get("type") != 2:
            continue
        token_count = _cursor_nonzero_token_count(item)
        if token_count is None:
            continue
        assistant_items.append({"item": item, "token_count": token_count})
    if not assistant_items:
        prompt_total_tokens = _cursor_prompt_total_tokens(composer)
        if not prompt_total_tokens:
            return None
        timestamp_ms = _cursor_header_timestamp_ms(composer)
        timestamp_dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else None
        total_messages, assistant_messages = _cursor_header_counts(composer)
        directory = _cursor_directory(composer)
        model_label = "Model unavailable (Cursor)"
        return {
            "tool": "Cursor",
            "tool_id": "cursor",
            "tool_color": config.TOOL_COLOR_MAP.get("cursor", "#6EE7B7"),
            "source_path": display_path(config.CURSOR_SOURCE_PATH),
            "id": composer.get("composerId"),
            "session_id": composer.get("composerId"),
            "timestamp": timestamp_ms,
            "created": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
            "created_at": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
            "updated": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
            "date": timestamp_dt.date().isoformat() if timestamp_dt else None,
            "title": _cursor_title(composer),
            "directory": directory,
            "provider": "cursor",
            "model_id": "model-unavailable",
            "model": model_label,
            "chart_model_id": "cursor/model-unavailable",
            "label": model_label,
            "sessions": 1,
            "messages": total_messages,
            "assistant_messages": assistant_messages,
            "tokens_input": prompt_total_tokens,
            "raw_tokens_input": prompt_total_tokens,
            "tokens_output": None,
            "tokens_total": prompt_total_tokens,
            "tokens_effective_total": effective_token_total(prompt_total_tokens, None, None),
            "cache_read": None,
            "cache_write": None,
            "cache_write_available": False,
            "metrics_note": "Cursor prompt/context token totals come from Cursor globalStorage promptTokenBreakdown.totalUsedTokens or contextTokensUsed. Assistant output, cache metrics, and trusted model IDs are unavailable in this newer local format.",
            "files_changed": None,
            "additions": None,
            "deletions": None,
        }

    timestamp_ms = _cursor_timestamp_ms(composer, [entry["item"] for entry in assistant_items])
    timestamp_dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else None
    tokens_input = sum(entry["token_count"]["inputTokens"] for entry in assistant_items)
    tokens_output = sum(entry["token_count"]["outputTokens"] for entry in assistant_items)
    total_messages = len([item for item in composer.get("conversation") or [] if isinstance(item, dict) and item.get("type") in {1, 2}])
    directory = _cursor_directory(composer)
    model_label = "Model unavailable (Cursor)"

    return {
        "tool": "Cursor",
        "tool_id": "cursor",
        "tool_color": config.TOOL_COLOR_MAP.get("cursor", "#6EE7B7"),
        "source_path": display_path(config.CURSOR_SOURCE_PATH),
        "id": composer.get("composerId"),
        "session_id": composer.get("composerId"),
        "timestamp": timestamp_ms,
        "created": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
        "created_at": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
        "updated": timestamp_dt.strftime("%Y-%m-%d %H:%M:%S") if timestamp_dt else None,
        "date": timestamp_dt.date().isoformat() if timestamp_dt else None,
        "title": _cursor_title(composer),
        "directory": directory,
        "provider": "cursor",
        "model_id": "model-unavailable",
        "model": model_label,
        "chart_model_id": "cursor/model-unavailable",
        "label": model_label,
        "sessions": 1,
        "messages": total_messages,
        "assistant_messages": len(assistant_items),
        "tokens_input": tokens_input,
        "raw_tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_total": tokens_input + tokens_output,
        "tokens_effective_total": effective_token_total(tokens_input + tokens_output, None, None),
        "cache_read": None,
        "cache_write": None,
        "cache_write_available": False,
        "metrics_note": "Cursor token totals come from Cursor globalStorage composerData assistant bubble tokenCount fields. Cursor local state does not expose trusted model IDs or cache metrics, so those fields remain unavailable.",
        "files_changed": None,
        "additions": None,
        "deletions": None,
    }


def cursor_records(days: int | None = None) -> list[dict]:
    """Normalize Cursor composer state into dashboard session records.

    Trust boundary: Cursor stores composer sessions in
    `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, table
    `cursorDiskKV`, keys `composerData:*`. Trusted token metrics come from
    assistant conversation items with `tokenCount.inputTokens` and
    `tokenCount.outputTokens`. Cursor local state does not expose stable cache
    metrics or trusted model IDs for these sessions, so those fields remain
    unavailable instead of guessed.
    """
    if not config.cursor_source_available():
        return []

    since_ms = None
    if days is not None:
        since_ms = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp() * 1000)

    records = []
    conn = _cursor_db()
    try:
        rows = conn.execute("SELECT value FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
    finally:
        conn.close()

    for row in rows:
        raw_value = row[0]
        if not raw_value:
            continue
        try:
            composer = json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(composer, dict):
            continue
        record = _cursor_session_record(composer)
        if not record:
            continue
        if since_ms is not None and (record.get("timestamp") or 0) < since_ms:
            continue
        records.append(record)

    records.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return records


def cursor_overview(days: int | None = None, *, records: list[dict] | None = None) -> dict | None:
    records = records if records is not None else cursor_records(days)
    if not records:
        return None
    dates = sorted({r["date"] for r in records if r.get("date")})
    return {
        "total_sessions": len({r["session_id"] for r in records}),
        "total_input": _sum_available(records, "tokens_input") or 0,
        "total_output": _sum_available(records, "tokens_output") or 0,
        "total_tokens": _sum_available(records, "tokens_total") or 0,
        "cache_read": None,
        "cache_write": None,
        "first_session": dates[0] if dates else None,
        "last_session": dates[-1] if dates else None,
        "metrics_note": "Cursor token totals come from Cursor globalStorage composerData assistant bubble tokenCount fields when present, or prompt/context token totals come from promptTokenBreakdown.totalUsedTokens or contextTokensUsed in newer local records. Cache metrics and trusted model IDs are unavailable locally.",
    }


def aggregate_cursor_models(days: int | None = 30, *, records: list[dict] | None = None) -> list[dict]:
    records = records if records is not None else cursor_records(days)
    if not records:
        return []
    return [{
        "tool": "Cursor",
        "tool_id": "cursor",
        "tool_color": config.TOOL_COLOR_MAP.get("cursor", "#6EE7B7"),
        "source_path": display_path(config.CURSOR_SOURCE_PATH),
        "provider": "cursor",
        "model_id": "model-unavailable",
        "label": "Model unavailable (Cursor)",
        "chart_model_id": "cursor/model-unavailable",
        "sessions": len({r["session_id"] for r in records}),
        "messages": sum(r.get("messages") or 0 for r in records),
        "tokens_input": _sum_available(records, "tokens_input"),
        "tokens_output": _sum_available(records, "tokens_output"),
        "tokens_total": _sum_available(records, "tokens_total"),
        "tokens_effective_total": _sum_available(records, "tokens_total") or 0,
        "cache_read": None,
        "cache_write": None,
        "cache_write_available": False,
        "estimated_cost": None,
        "pricing_status": "unpriced",
        "pricing_source": None,
        "pricing_model_id": None,
        "metrics_note": "Cursor token totals are available from composerData tokenCount fields or prompt/context token totals in newer local records, but trusted model IDs are unavailable locally.",
    }]

def hermes_records(days: int | None = None) -> list[dict]:
    """Normalize Hermes session rows into dashboard records.

    Trust boundary: ~/.hermes/state.db `sessions` is the authoritative source
    for session metadata and token metrics. Hermes stores non-cache input,
    output, cache read, and cache write counts as separate session columns, so
    dashboard totals stay `input_tokens + output_tokens` with cache surfaced
    separately. Message text is never parsed to infer unavailable metrics.
    """
    if not config.hermes_source_available():
        return []

    since_ts = None
    if days is not None:
        since_ts = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()

    where = "WHERE started_at >= ?" if since_ts else ""
    params = (since_ts,) if since_ts else ()
    conn = sqlite3.connect(f"file:{config.HERMES_STATE_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"""
            SELECT
                id,
                source,
                title,
                started_at,
                ended_at,
                message_count,
                tool_call_count,
                model,
                billing_provider,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
                estimated_cost_usd,
                actual_cost_usd,
                cost_status,
                cost_source
            FROM sessions
            {where}
            ORDER BY started_at DESC
        """, params).fetchall()
    finally:
        conn.close()

    records = []
    for row in rows:
        model_id = row["model"] or "unknown"
        provider = row["billing_provider"] or "unknown"
        started = float(row["started_at"] or 0)
        ended = float(row["ended_at"] or 0) if row["ended_at"] is not None else None
        started_dt = datetime.datetime.fromtimestamp(started) if started else None
        ended_dt = datetime.datetime.fromtimestamp(ended) if ended else None
        input_tokens = _safe_int(row["input_tokens"], None)
        output_tokens = _safe_int(row["output_tokens"], None)
        cache_read = _safe_int(row["cache_read_tokens"], None)
        cache_write = _safe_int(row["cache_write_tokens"], None)
        records.append({
            "tool": "Hermes",
            "tool_id": "hermes",
            "tool_color": config.TOOL_COLOR_MAP.get("hermes", "#EAB308"),
            "source_path": display_path(config.HERMES_STATE_PATH),
            "id": row["id"],
            "session_id": row["id"],
            "timestamp": int(started * 1000) if started else 0,
            "created": started_dt.strftime("%Y-%m-%d %H:%M:%S") if started_dt else None,
            "created_at": started_dt.strftime("%Y-%m-%d %H:%M:%S") if started_dt else None,
            "updated": ended_dt.strftime("%Y-%m-%d %H:%M:%S") if ended_dt else None,
            "date": started_dt.date().isoformat() if started_dt else None,
            "title": row["title"] or row["id"],
            "directory": row["source"],
            "provider": provider,
            "model_id": model_id,
            "model": f"{provider}/{model_id}",
            "chart_model_id": f"{provider}/{model_id}",
            "label": normalize_model(json.dumps({"id": model_id, "providerID": provider}))["label"],
            "sessions": 1,
            "messages": _safe_int(row["message_count"], 0) or 0,
            "tool_calls": _safe_int(row["tool_call_count"], 0) or 0,
            "tokens_input": input_tokens,
            "raw_tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "tokens_total": (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None and output_tokens is not None else None,
            "tokens_effective_total": effective_token_total(
                (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None and output_tokens is not None else None,
                cache_read,
                cache_write,
            ),
            "cache_read": cache_read,
            "cache_write": cache_write,
            "cache_write_available": cache_write is not None,
            "metrics_note": "Hermes session totals come from ~/.hermes/state.db sessions columns; total tokens are input_tokens + output_tokens with cache read/write tracked separately.",
            "estimated_cost": row["estimated_cost_usd"],
            "actual_cost": row["actual_cost_usd"],
            "cost_status": row["cost_status"],
            "cost_source": row["cost_source"],
            "files_changed": None,
            "additions": None,
            "deletions": None,
        })
    return records

def hermes_overview(days: int | None = None, *, records: list[dict] | None = None) -> dict | None:
    records = records if records is not None else hermes_records(days)
    if not records:
        return None
    dates = sorted({r["date"] for r in records if r.get("date")})
    total_input = _sum_available(records, "tokens_input") or 0
    total_output = _sum_available(records, "tokens_output") or 0
    return {
        "total_sessions": len({r["session_id"] for r in records}),
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_input + total_output,
        "cache_read": _sum_available(records, "cache_read") or 0,
        "cache_write": _sum_available(records, "cache_write") or 0,
        "first_session": dates[0] if dates else None,
        "last_session": dates[-1] if dates else None,
    }

def _trusted_hermes_accounting_cost(record: dict) -> float | None:
    """Return Hermes session-accounting cost only when the row says it was actually costed."""
    status = (record.get("cost_status") or "").strip().lower()
    source = (record.get("cost_source") or "").strip().lower()
    if status in {"", "unknown"} or source in {"", "none", "unknown"}:
        return None
    accounted_cost = record.get("actual_cost")
    if accounted_cost is None:
        accounted_cost = record.get("estimated_cost")
    return accounted_cost


def _hermes_pricing_url(provider: str, model_id: str) -> str | None:
    """Return a public model reference URL when Hermes accounting names a known model."""
    if "/" in (model_id or ""):
        return openrouter_model_url(model_id)
    return openrouter_model_url(pricing_model_resolution(provider, model_id).model_id)


def aggregate_hermes_models(days: int | None = 30, *, records: list[dict] | None = None) -> list[dict]:
    grouped = {}
    for record in (records if records is not None else hermes_records(days)):
        key = (record["provider"], record["model_id"])
        agg = grouped.setdefault(key, {
            "tool": "Hermes",
            "tool_id": "hermes",
            "tool_color": config.TOOL_COLOR_MAP.get("hermes", "#EAB308"),
            "source_path": display_path(config.HERMES_STATE_PATH),
            "provider": record["provider"],
            "model_id": record["model_id"],
            "label": normalize_model(json.dumps({"id": record["model_id"], "providerID": record["provider"]}))["label"],
            "chart_model_id": record["chart_model_id"],
            "sessions": 0,
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "tokens_effective_total": 0,
            "cache_read": 0,
            "cache_write": 0,
            "cache_write_available": True,
            "accounted_cost": 0.0,
            "accounted_sessions": 0,
            "accounted_tokens_total": 0,
            "unaccounted_sessions": 0,
            "unaccounted_tokens_total": 0,
        })
        agg["sessions"] += 1
        agg["messages"] += record.get("messages") or 0
        agg["tokens_input"] += record.get("tokens_input") or 0
        agg["tokens_output"] += record.get("tokens_output") or 0
        agg["tokens_total"] += record.get("tokens_total") or 0
        agg["tokens_effective_total"] += effective_token_total(
            record.get("tokens_total"),
            record.get("cache_read"),
            record.get("cache_write"),
        )
        agg["cache_read"] += record.get("cache_read") or 0
        agg["cache_write"] += record.get("cache_write") or 0
        accounted_cost = _trusted_hermes_accounting_cost(record)
        record_tokens_total = record.get("tokens_total") or 0
        if accounted_cost is not None:
            agg["accounted_cost"] += float(accounted_cost)
            agg["accounted_sessions"] += 1
            agg["accounted_tokens_total"] += record_tokens_total
        else:
            agg["unaccounted_sessions"] += 1
            agg["unaccounted_tokens_total"] += record_tokens_total
    models = sorted(grouped.values(), key=lambda item: item["tokens_effective_total"], reverse=True)
    for item in models:
        accounted_sessions = item.get("accounted_sessions", 0)
        unaccounted_sessions = item.get("unaccounted_sessions", 0)
        if accounted_sessions and not unaccounted_sessions:
            accounted_cost = item.pop("accounted_cost")
            item.update({
                "estimated_cost": accounted_cost,
                "pricing_status": "priced",
                "pricing_source": "Hermes session accounting",
                "pricing_model_id": item["chart_model_id"],
                "pricing_url": _hermes_pricing_url(item["provider"], item["model_id"]),
                "cost_basis": "actual_or_session_estimate",
                "cost_breakdown": None,
            })
        elif accounted_sessions:
            accounted_cost = item.pop("accounted_cost")
            provider_estimate = estimate_cost(
                item["provider"],
                item["model_id"],
                item["tokens_input"],
                item["tokens_output"],
                item["cache_read"],
                item["cache_write"],
            )
            accounting_note = f"Hermes session accounting covers {accounted_sessions}/{item['sessions']} sessions"
            if provider_estimate.get("pricing_status") == "unpriced":
                item.update({
                    "estimated_cost": None,
                    "pricing_status": "partial",
                    "pricing_source": accounting_note,
                    "pricing_model_id": item["chart_model_id"],
                    "pricing_url": _hermes_pricing_url(item["provider"], item["model_id"]),
                    "cost_basis": "partial_actual_or_session_estimate",
                    "partial_cost_usd": accounted_cost,
                    "cost_breakdown": None,
                })
            else:
                provider_source = provider_estimate.get("pricing_source") or "provider/model pricing"
                provider_estimate["pricing_source"] = f"{provider_source}; {accounting_note}"
                provider_estimate["cost_basis"] = "api_equivalent_estimate_with_partial_session_accounting"
                provider_estimate["session_accounting_partial_cost_usd"] = accounted_cost
                provider_estimate["session_accounting_note"] = accounting_note
                item.update(provider_estimate)
        else:
            item.pop("accounted_cost", None)
            item.update(estimate_cost(
                item["provider"],
                item["model_id"],
                item["tokens_input"],
                item["tokens_output"],
                item["cache_read"],
                item["cache_write"],
            ))
    return models

def aggregate_codex_models(days: int | None = 30, *, records: list[dict] | None = None) -> list[dict]:
    grouped = {}
    for record in (records if records is not None else codex_records(days)):
        key = (record["provider"], record["model_id"])
        agg = grouped.setdefault(key, {
            "tool": "Codex CLI",
            "tool_id": "codex",
            "tool_color": config.TOOL_COLOR_MAP.get("codex", "#BA68C8"),
            "source_path": display_path(config.CODEX_SOURCE_PATH),
            "provider": record["provider"],
            "model_id": record["model_id"],
            "label": normalize_model(json.dumps({"id": record["model_id"], "providerID": record["provider"]}))["label"],
            "chart_model_id": record["chart_model_id"],
            "sessions": 0,
            "messages": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "tokens_effective_total": 0,
            "cache_read": 0,
            "cache_write": None,
            "cache_write_available": False,
        })
        agg["sessions"] += 1
        agg["messages"] += record.get("messages") or 0
        agg["tokens_input"] += record.get("tokens_input") or 0
        agg["tokens_output"] += record.get("tokens_output") or 0
        agg["tokens_total"] += record.get("tokens_total") or 0
        agg["tokens_effective_total"] += effective_token_total(
            record.get("tokens_total"),
            record.get("cache_read"),
            record.get("cache_write"),
        )
        agg["cache_read"] += record.get("cache_read") or 0
    models = sorted(grouped.values(), key=lambda item: item["tokens_effective_total"], reverse=True)
    for item in models:
        item.update(estimate_cost(
            item["provider"],
            item["model_id"],
            item["tokens_input"],
            item["tokens_output"],
            item["cache_read"],
            0,
        ))
    return models
