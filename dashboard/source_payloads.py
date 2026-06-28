"""Response shaping for multi-source dashboard payloads."""

from __future__ import annotations

from . import config as dashboard_config
from .config import current_tool_sources, display_path, tool_source_label
from .pricing import chart_color

CONNECTED_TOOL_IDS = {"opencode", "codex", "hermes", "cursor"}

EXTERNAL_SOURCE_SPECS = (
    {
        "id": "codex",
        "overview_key": "codex_overview",
        "records_key": "codex_records",
        "models_key": "codex_models",
        "unavailable": "Codex CLI data is unavailable.",
        "metrics_note": "Cache write unavailable in local Codex JSONL.",
    },
    {
        "id": "hermes",
        "overview_key": "hermes_overview",
        "records_key": "hermes_records",
        "models_key": "hermes_models",
        "unavailable": "Hermes data is unavailable.",
        "metrics_note": "Hermes token metrics come from ~/.hermes/state.db sessions columns.",
    },
    {
        "id": "cursor",
        "overview_key": "cursor_overview",
        "records_key": "cursor_records",
        "models_key": "cursor_models",
        "unavailable": "Cursor data is unavailable.",
        "metrics_note": None,
    },
)

EXTERNAL_RECORD_KEYS = {spec["id"]: spec["records_key"] for spec in EXTERNAL_SOURCE_SPECS}
UNAVAILABLE_DAILY_MESSAGES = {spec["id"]: spec["unavailable"] for spec in EXTERNAL_SOURCE_SPECS}


def empty_daily_payload(top_n: int, selected_tool_id: str | None, error_message: str | None = None) -> dict:
    return {
        "dates": [],
        "models": [],
        "data": {},
        "top_n": top_n,
        "other_count": 0,
        "selected_model_id": None,
        "selected_tool_id": selected_tool_id,
        "selected_tool_label": tool_source_label(selected_tool_id),
        "error": error_message,
    }


def overview_token_totals(
    sessions,
    tokens_input,
    tokens_output,
    cache_read,
    cache_write,
    metrics_note: str | None = None,
) -> dict:
    non_cache_input = tokens_input or 0
    output_available = tokens_output is not None
    output = tokens_output or 0
    cache_read_available = cache_read is not None
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
        "tokens_output": tokens_output if output_available else None,
        "cache_read": cache_read if cache_read_available else None,
        "cache_write": cache_write,
        "cache_total": read + write,
    }
    if metrics_note:
        totals["metrics_note"] = metrics_note
    return totals


def _overview_totals_by_source(snapshot: dict) -> dict[str, dict]:
    opencode = snapshot["opencode"]["overview"]
    source_overviews = {
        "opencode": overview_token_totals(
            opencode["total_sessions"],
            opencode["total_input"],
            opencode["total_output"],
            opencode["cache_read"],
            opencode["cache_write"],
        )
    }
    for spec in EXTERNAL_SOURCE_SPECS:
        overview = snapshot.get(spec["overview_key"])
        if not overview:
            continue
        source_overviews[spec["id"]] = overview_token_totals(
            overview["total_sessions"],
            overview["total_input"],
            overview["total_output"],
            overview["cache_read"],
            overview["cache_write"],
            overview.get("metrics_note") or spec["metrics_note"],
        )
    return source_overviews


def build_overview_payload(snapshot: dict, days: int | None) -> dict:
    row = dict(snapshot["opencode"]["overview"])
    row["days"] = days
    source_overviews = _overview_totals_by_source(snapshot)

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
    for spec in EXTERNAL_SOURCE_SPECS:
        overview = snapshot.get(spec["overview_key"])
        if overview:
            session_dates.extend([overview["first_session"], overview["last_session"]])
    session_dates = [date for date in session_dates if date]
    if session_dates:
        row["first_session"] = min(session_dates)
        row["last_session"] = max(session_dates)

    current_sources = current_tool_sources()
    counted_sources = [source for source in current_sources if source["id"] in source_overviews]
    row["active_tool"] = "multiple" if len(counted_sources) > 1 else (counted_sources[0]["id"] if counted_sources else "opencode")
    row["active_tool_label"] = " + ".join(source["label"] for source in counted_sources) if counted_sources else "OpenCode"
    row["source_path"] = " + ".join(source["source_path"] for source in counted_sources) if counted_sources else display_path(dashboard_config.DB_PATH)

    row["tool_sources"] = []
    for source in current_sources:
        item = dict(source)
        if item["id"] in source_overviews:
            item.update(source_overviews[item["id"]])
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
    return row


def build_models_payload(snapshot: dict) -> list[dict]:
    models = list(snapshot["opencode"]["models"])
    for spec in EXTERNAL_SOURCE_SPECS:
        models.extend(snapshot[spec["models_key"]])
    models.sort(key=lambda item: item.get("tokens_effective_total") or 0, reverse=True)
    for rank, model in enumerate(models, start=1):
        model["rank"] = rank
        model["color"] = chart_color(rank - 1, model.get("model_id", ""), model.get("provider", ""))
    return models


def daily_records_for_tool(snapshot: dict, selected_tool_id: str | None) -> tuple[list[dict], str | None]:
    if selected_tool_id in EXTERNAL_RECORD_KEYS:
        records = snapshot[EXTERNAL_RECORD_KEYS[selected_tool_id]]
        if not records:
            return [], UNAVAILABLE_DAILY_MESSAGES[selected_tool_id]
        return records, None

    records = list(snapshot["opencode"]["daily_records"])
    if selected_tool_id is None:
        for spec in EXTERNAL_SOURCE_SPECS:
            records.extend(snapshot[spec["records_key"]])
    return records, None


def external_history_records(snapshot: dict) -> list[dict]:
    records = []
    for spec in EXTERNAL_SOURCE_SPECS:
        records.extend(snapshot[spec["records_key"]])
    return records


def history_row_from_record(record: dict) -> dict:
    return {
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
    }


def build_history_payload(history_snapshot: dict, recent_snapshot: dict, *, offset: int, limit: int) -> list[dict]:
    sessions = list(history_snapshot["opencode"]["history"])
    sessions.extend(history_row_from_record(record) for record in external_history_records(recent_snapshot))
    sessions.sort(key=lambda item: item.get("timestamp") or 0, reverse=True)
    return sessions[offset: offset + limit]
