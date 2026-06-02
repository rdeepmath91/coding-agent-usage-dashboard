"""Deterministic synthetic dashboard data for screenshots and UI checks."""

import datetime
import json
import random

from .config import TOOL_COLOR_MAP, current_tool_sources
from .pricing import QUALITATIVE_COLORS, estimate_cost, normalize_model
from .token_metrics import effective_token_total


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
            tokens_effective_total = effective_token_total(total_tokens, cache_read, cache_write)
            sessions = max(0, int(total_tokens / 95_000 * (0.8 + rng.random() * spec["session_ratio"]))) if total_tokens else 0
            messages = max(sessions, int(sessions * (1.6 + rng.random() * 1.7))) if total_tokens else 0

            chart_model_id = f'{spec["provider"]}/{spec["model_id"]}'
            daily[dt][chart_model_id] = {
                "sessions": sessions,
                "messages": messages,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "tokens_total": total_tokens,
                "tokens_effective_total": tokens_effective_total,
                "cache_read": cache_read,
                "cache_write": cache_write,
            }
            model_totals[chart_model_id] = model_totals.get(chart_model_id, 0) + tokens_effective_total

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
            "tokens_effective_total": 0,
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
            "tokens_effective_total": aggregate["tokens_effective_total"],
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

    session_tokens = total_input + total_output
    total_input_with_cache = total_input + cache_read_total + cache_write_total
    total_token_volume = session_tokens + cache_read_total + cache_write_total

    overview = {
        "total_sessions": total_sessions,
        "total_input": total_input_with_cache,
        "non_cache_input": total_input,
        "total_output": total_output,
        "total_tokens": total_token_volume,
        "session_tokens": session_tokens,
        "cache_read": cache_read_total,
        "cache_write": cache_write_total,
        "cache_total": cache_read_total + cache_write_total,
        "first_session": date_keys[0],
        "last_session": date_keys[-1],
        "days": days,
        "active_tool": "opencode",
        "active_tool_label": "OpenCode (simulated)",
        "source_path": "simulated dataset",
        "token_total_definition": "total token volume = input tokens + output tokens; includes cache read/write",
        "input_token_definition": "input tokens = non-cache input + cache read + cache write",
        "session_token_definition": "session tokens = non-cache input + output assistant-message tokens",
        "tool_sources": [],
    }

    overview["active_tool_label"] = "OpenCode (simulated)"
    overview.setdefault("tool_sources", [])

    opencode_source = next((src for src in current_tool_sources() if src["id"] == "opencode"), {
        "id": "opencode",
        "label": "OpenCode",
        "status": "active",
        "status_label": "Simulated",
        "source_type": "Synthetic dataset",
        "source_path": "simulated dataset",
        "repo_url": "https://github.com/anomalyco/opencode/",
        "color": TOOL_COLOR_MAP.get("opencode", "#64748B"),
        "issue": None,
    })
    opencode_item = dict(opencode_source)
    opencode_item.update({
        "status_label": "Simulated",
        "source_path": "simulated dataset",
        "sessions": total_sessions,
        "tokens_total": overview["total_tokens"],
        "tokens_input": total_input_with_cache,
        "non_cache_input": total_input,
        "tokens_output": total_output,
        "session_tokens": session_tokens,
        "cache_read": cache_read_total,
        "cache_write": cache_write_total,
        "cache_total": cache_read_total + cache_write_total,
        "estimated_cost": None,
        "actual_cost": None,
        "cost_status": None,
        "cost_source": None,
        "estimated_cost_subtotal": None,
        "actual_cost_subtotal": None,
        "pricing_status": "unpriced",
        "pricing_source": None,
        "pricing_model_id": None,
        "cost_basis": "simulated_no_billing",
        "cost_breakdown": None,
        "accounted_cost": None,
    })
    overview["tool_sources"] = [opencode_item]

    history.sort(key=lambda row: row["created"], reverse=True)
    return {
        "overview": overview,
        "models": models,
        "daily": daily,
        "dates": date_keys,
        "history": history,
    }
