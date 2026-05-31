"""Daily chart aggregation helpers."""

import datetime

from .config import tool_source_label
from .pricing import chart_color


def build_daily_from_model_records(model_records: list[dict], top_n: int, selected_model_id: str | None, selected_tool_id: str | None) -> dict:
    daily_data = {}
    model_map = {}
    all_models_ordered = []
    for row in model_records:
        dt = row["date"]
        mid = row["chart_model_id"]
        if mid not in model_map:
            model_map[mid] = {
                "label": row["label"],
                "model_id": row["model_id"],
                "provider": row["provider"],
            }
            all_models_ordered.append(mid)
        daily_data.setdefault(dt, {})
        bucket = daily_data[dt].setdefault(mid, {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0, "cache_read": 0, "cache_write": 0})
        bucket["sessions"] += row.get("sessions") or 0
        bucket["messages"] += row.get("messages") or 0
        bucket["tokens_input"] += row.get("tokens_input") or 0
        bucket["tokens_output"] += row.get("tokens_output") or 0
        bucket["tokens_total"] += row.get("tokens_total") or 0
        bucket["cache_read"] += row.get("cache_read") or 0
        bucket["cache_write"] += row.get("cache_write") or 0

    dates = sorted(daily_data.keys())
    for dt in dates:
        for mid in all_models_ordered:
            daily_data[dt].setdefault(mid, {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0, "cache_read": 0, "cache_write": 0})

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
        chart_data[dt] = {mid: daily_data[dt][mid] for mid in top_models}
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
        chart_models.append({"id": "other", "label": f"Other ({len(other_models)} models)", "color": "#64748B", "tokens_total": sum(model_totals.get(mid, 0) for mid in other_models), "rank": None})
        for dt in dates:
            chart_data[dt].setdefault("other", {"sessions": 0, "messages": 0, "tokens_input": 0, "tokens_output": 0, "tokens_total": 0, "cache_read": 0, "cache_write": 0})

    return {
        "dates": dates,
        "models": chart_models,
        "data": chart_data,
        "top_n": top_n,
        "other_count": 0 if selected_model_id else len(other_models),
        "selected_model_id": selected_model_id if selected_model_id in active_models else None,
        "selected_tool_id": selected_tool_id,
        "selected_tool_label": tool_source_label(selected_tool_id),
    }
