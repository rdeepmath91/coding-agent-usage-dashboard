#!/usr/bin/env python3
"""Coding Agent Usage Dashboard — Flask entrypoint and route layer."""

import datetime
import os
import subprocess
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from dashboard import config as dashboard_config
from dashboard.config import (
    KNOWN_TOOL_IDS,
    current_tool_sources,
    display_path,
    tool_source_label,
)
from dashboard.daily import build_daily_from_model_records
from dashboard.pricing import QUALITATIVE_COLORS, chart_color
from dashboard.simulation import build_simulated_dataset
from dashboard.snapshot import load_dashboard_snapshot
from dashboard.sources import codex_records, get_db, hermes_records

app = Flask(__name__)

REPO_ROOT = Path(__file__).resolve().parent
UPDATE_REMOTE = "origin"
UPDATE_BRANCH = "main"
UPDATE_TARGET_REF = f"{UPDATE_REMOTE}/{UPDATE_BRANCH}"
UPDATE_FALLBACK_COMMAND = f"git pull --ff-only {UPDATE_REMOTE} {UPDATE_BRANCH} && uv sync"
UPDATE_HEADER_NAME = "X-Dashboard-Update"
UPDATE_HEADER_VALUE = "1"
APP_COMMAND_TIMEOUT_SECONDS = 120


def run_app_command(args: list[str], *, timeout: int = APP_COMMAND_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Run a fixed app-maintenance command from the repository root."""
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def command_text(result: subprocess.CompletedProcess | None) -> str:
    if result is None:
        return ""
    output = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part and part.strip())
    return output[-1200:]


def git_value(args: list[str]) -> str | None:
    result = run_app_command(["git", *args], timeout=20)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def fetch_update_target() -> subprocess.CompletedProcess:
    return run_app_command(
        ["git", "fetch", UPDATE_REMOTE, f"{UPDATE_BRANCH}:refs/remotes/{UPDATE_TARGET_REF}", "--quiet"],
        timeout=60,
    )


def is_git_ancestor(base_ref: str, tip_ref: str) -> bool:
    result = run_app_command(["git", "merge-base", "--is-ancestor", base_ref, tip_ref], timeout=20)
    return result.returncode == 0


def app_dirty_state() -> tuple[bool, str]:
    result = run_app_command(["git", "status", "--porcelain"], timeout=20)
    if result.returncode != 0:
        return True, command_text(result) or "Unable to inspect local changes."
    details = result.stdout.strip()
    return bool(details), details


def app_version_payload() -> dict:
    fetch = fetch_update_target()
    branch = git_value(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    sha = git_value(["rev-parse", "--short", "HEAD"]) or "unknown"
    full_sha = git_value(["rev-parse", "HEAD"])
    target_sha = git_value(["rev-parse", "--short", UPDATE_TARGET_REF])
    target_full_sha = git_value(["rev-parse", UPDATE_TARGET_REF])
    dirty, dirty_details = app_dirty_state()
    update_available = False
    status = "check_failed"
    message = f"Could not check latest {UPDATE_BRANCH}."
    if fetch.returncode != 0:
        message = command_text(fetch) or message
    elif full_sha and target_full_sha:
        if full_sha == target_full_sha or is_git_ancestor(UPDATE_TARGET_REF, "HEAD"):
            status = "current"
            message = f"Current version · {target_sha or sha}"
        elif is_git_ancestor("HEAD", UPDATE_TARGET_REF):
            update_available = True
            status = "blocked_dirty" if dirty else "update_available"
            message = (
                f"New version available · {target_sha} blocked by local changes"
                if dirty
                else f"New version available · {target_sha}"
            )
        else:
            status = "manual_required"
            message = f"Manual update required · {UPDATE_TARGET_REF}"
    return {
        "branch": branch,
        "sha": sha,
        "target_branch": UPDATE_BRANCH,
        "target_ref": UPDATE_TARGET_REF,
        "target_sha": target_sha,
        "update_available": update_available,
        "status": status,
        "message": message,
        "dirty": dirty,
        "dirty_details": dirty_details,
        "fallback_command": UPDATE_FALLBACK_COMMAND,
    }


def is_local_request() -> bool:
    return (request.remote_addr or "") in {"127.0.0.1", "::1", "localhost"}


def has_update_header() -> bool:
    return request.headers.get(UPDATE_HEADER_NAME) == UPDATE_HEADER_VALUE


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


def profile_endpoint(name: str, start: float) -> None:
    if str(os.environ.get("DASHBOARD_PROFILE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        app.logger.info("%s total %.1fms", name, (time.perf_counter() - start) * 1000)


# ── API Routes ──────────────────────────────────────────────────────────────


@app.route("/api/overview")
def api_overview():
    """Aggregate totals for a selected range; days=0/all means all time."""
    started = time.perf_counter()
    days = parse_days(default=None)
    if simulate_enabled():
        return jsonify(build_simulated_dataset(days)["overview"])
    snapshot = load_dashboard_snapshot(days)
    row = dict(snapshot["opencode"]["overview"])
    codex = snapshot["codex_overview"]
    hermes = snapshot["hermes_overview"]
    row["days"] = days

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
    for overview in [codex, hermes]:
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
    profile_endpoint("api_overview", started)
    return jsonify(row)


@app.route("/api/models")
def api_models():
    """Session and token totals per model, attributed per assistant message."""
    started = time.perf_counter()
    days = parse_days(default=30)
    if simulate_enabled():
        return jsonify(build_simulated_dataset(days)["models"])
    snapshot = load_dashboard_snapshot(days)
    models = list(snapshot["opencode"]["models"])
    models.extend(snapshot["codex_models"])
    models.extend(snapshot["hermes_models"])
    models.sort(key=lambda item: item.get("tokens_effective_total") or 0, reverse=True)
    for rank, model in enumerate(models, start=1):
        model["rank"] = rank
        model["color"] = chart_color(rank - 1, model.get("model_id", ""), model.get("provider", ""))
    profile_endpoint("api_models", started)
    return jsonify(models)


@app.route("/api/daily")
def api_daily():
    """Daily token breakdown by model, attributed per assistant message."""
    started = time.perf_counter()
    days = parse_days(default=31)
    top_n = parse_top_n(default=8)
    selected_model_id = request.args.get("model_id") or None
    selected_tool_id = request.args.get("tool_id") or None
    if selected_tool_id and selected_tool_id not in {"opencode", "codex", "hermes"}:
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
    snapshot = load_dashboard_snapshot(days)
    if selected_tool_id == "codex":
        records = snapshot["codex_records"]
        if not records:
            return empty_daily_response(top_n, selected_tool_id, error_message="Codex CLI data is unavailable.")
        profile_endpoint("api_daily", started)
        return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))
    if selected_tool_id == "hermes":
        records = snapshot["hermes_records"]
        if not records:
            return empty_daily_response(top_n, selected_tool_id, error_message="Hermes data is unavailable.")
        profile_endpoint("api_daily", started)
        return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))

    records = list(snapshot["opencode"]["daily_records"])
    if selected_tool_id is None:
        records.extend(snapshot["codex_records"])
        records.extend(snapshot["hermes_records"])
    profile_endpoint("api_daily", started)
    return jsonify(build_daily_from_model_records(records, top_n, selected_model_id, selected_tool_id))


@app.route("/api/usage-history")
def api_usage_history():
    """Recent sessions feed."""
    started = time.perf_counter()
    limit = request.args.get("limit", "50", type=int)
    offset = request.args.get("offset", "0", type=int)

    if simulate_enabled():
        history = build_simulated_dataset(31)["history"]
        start = int(offset or 0)
        count = int(limit or 50)
        return jsonify(history[start: start + count])
    history_snapshot = load_dashboard_snapshot(None)
    recent_snapshot = load_dashboard_snapshot(30)
    sessions = list(history_snapshot["opencode"]["history"])
    for record in recent_snapshot["codex_records"] + recent_snapshot["hermes_records"]:
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
    profile_endpoint("api_usage_history", started)
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


@app.route("/api/app-version")
def api_app_version():
    """Return local dashboard version metadata for the update control."""
    if not is_local_request():
        return (
            jsonify({
                "status": "forbidden",
                "error": "App version is only available from localhost.",
            }),
            403,
        )
    if not has_update_header():
        return (
            jsonify({
                "status": "forbidden",
                "error": "App version requires a dashboard UI request.",
            }),
            403,
        )
    return jsonify(app_version_payload())


@app.route("/api/update", methods=["POST"])
def api_update():
    """Fast-forward this local dashboard checkout, then sync dependencies."""
    if not is_local_request():
        return (
            jsonify({
                "status": "forbidden",
                "error": "Update is only available from localhost.",
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            403,
        )

    if not has_update_header():
        return (
            jsonify({
                "status": "forbidden",
                "error": "Update requires a dashboard UI request.",
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            403,
        )

    fetch = fetch_update_target()
    old_sha = git_value(["rev-parse", "--short", "HEAD"]) or "unknown"
    old_full_sha = git_value(["rev-parse", "HEAD"])
    target_sha = git_value(["rev-parse", "--short", UPDATE_TARGET_REF])
    target_full_sha = git_value(["rev-parse", UPDATE_TARGET_REF])
    if fetch.returncode != 0 or not old_full_sha or not target_full_sha:
        return (
            jsonify({
                "status": "failure",
                "old_sha": old_sha,
                "new_sha": old_sha,
                "error": f"Could not check latest {UPDATE_BRANCH}.",
                "output": command_text(fetch),
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            500,
        )

    if old_full_sha == target_full_sha or is_git_ancestor(UPDATE_TARGET_REF, "HEAD"):
        return jsonify({
            "status": "already_current",
            "old_sha": old_sha,
            "new_sha": old_sha,
            "target_sha": target_sha,
            "restart_required": False,
            "output": f"Already up to date with {UPDATE_TARGET_REF}.",
            "fallback_command": UPDATE_FALLBACK_COMMAND,
        })

    dirty, dirty_details = app_dirty_state()
    if dirty:
        return (
            jsonify({
                "status": "local_changes",
                "old_sha": old_sha,
                "new_sha": old_sha,
                "target_sha": target_sha,
                "error": "Local changes detected. Update manually to avoid overwriting work.",
                "output": dirty_details,
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            409,
        )

    if not is_git_ancestor("HEAD", UPDATE_TARGET_REF):
        return (
            jsonify({
                "status": "manual_required",
                "old_sha": old_sha,
                "new_sha": old_sha,
                "target_sha": target_sha,
                "error": f"This checkout cannot fast-forward to {UPDATE_TARGET_REF}.",
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            409,
        )

    try:
        pull = run_app_command(["git", "pull", "--ff-only", UPDATE_REMOTE, UPDATE_BRANCH], timeout=120)
    except subprocess.TimeoutExpired:
        return (
            jsonify({
                "status": "failure",
                "old_sha": old_sha,
                "new_sha": old_sha,
                "target_sha": target_sha,
                "error": f"Update failed. git pull --ff-only {UPDATE_REMOTE} {UPDATE_BRANCH} timed out.",
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            500,
        )
    if pull.returncode != 0:
        return (
            jsonify({
                "status": "failure",
                "old_sha": old_sha,
                "new_sha": old_sha,
                "target_sha": target_sha,
                "error": f"Update failed during git pull --ff-only {UPDATE_REMOTE} {UPDATE_BRANCH}.",
                "output": command_text(pull),
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            500,
        )

    try:
        sync = run_app_command(["uv", "sync"], timeout=180)
    except subprocess.TimeoutExpired:
        new_sha = git_value(["rev-parse", "--short", "HEAD"]) or old_sha
        return (
            jsonify({
                "status": "failure",
                "old_sha": old_sha,
                "new_sha": new_sha,
                "target_sha": target_sha,
                "error": "Update failed. uv sync timed out.",
                "output": command_text(pull),
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            500,
        )
    new_sha = git_value(["rev-parse", "--short", "HEAD"]) or old_sha
    if sync.returncode != 0:
        return (
            jsonify({
                "status": "failure",
                "old_sha": old_sha,
                "new_sha": new_sha,
                "target_sha": target_sha,
                "error": "Update failed during uv sync.",
                "output": command_text(sync),
                "fallback_command": UPDATE_FALLBACK_COMMAND,
            }),
            500,
        )

    status = "already_current" if old_sha == new_sha else "updated"
    return jsonify({
        "status": status,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "target_sha": target_sha,
        "restart_required": status == "updated",
        "output": "\n".join(part for part in [command_text(pull), command_text(sync)] if part),
        "fallback_command": UPDATE_FALLBACK_COMMAND,
    })


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
    print(f"◆ Database: {dashboard_config.DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=True)
