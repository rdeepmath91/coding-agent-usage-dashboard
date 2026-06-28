"""Configuration and tool-source metadata for the dashboard."""

from pathlib import Path
import os
import sqlite3
import sys

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
CODEX_STATE_PATH = os.path.expanduser("~/.codex/state_5.sqlite")
CODEX_SESSIONS_DIR = os.path.expanduser("~/.codex/sessions")
CODEX_SOURCE_PATH = CODEX_STATE_PATH
HERMES_STATE_PATH = os.path.expanduser("~/.hermes/state.db")


def default_cursor_state_path(platform_name: str | None = None, env: dict | None = None) -> str:
    """Return the default Cursor global-storage SQLite path for this platform."""
    env = os.environ if env is None else env
    override = env.get("DASHBOARD_CURSOR_STATE_PATH")
    if override:
        return os.path.expanduser(override)
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
    if platform_name.startswith("win"):
        appdata = env.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")
        return os.path.expanduser("~/AppData/Roaming/Cursor/User/globalStorage/state.vscdb")
    return os.path.expanduser("~/.config/Cursor/User/globalStorage/state.vscdb")


CURSOR_STATE_PATH = default_cursor_state_path()
CURSOR_SOURCE_PATH = CURSOR_STATE_PATH


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
        "source_type": "SQLite state + JSONL rollouts",
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
        "source_type": "Hermes session SQLite database",
        "source_path": "TBD",
        "repo_url": "https://github.com/NousResearch/hermes-agent/",
        "color": "#EAB308",
        "issue": None,
    },
    {
        "id": "cursor",
        "label": "Cursor",
        "status": "placeholder",
        "status_label": "Planned adapter",
        "source_type": "Cursor global storage SQLite database",
        "source_path": "TBD",
        "repo_url": "https://github.com/getcursor/cursor/",
        "color": "#6EE7B7",
        "issue": None,
    },
]

TOOL_COLOR_MAP = {item["id"]: item["color"] for item in TOOL_SOURCES}
KNOWN_TOOL_IDS = {item["id"] for item in TOOL_SOURCES}


def codex_source_available() -> bool:
    """Return whether local Codex state exists on this machine."""
    return Path(CODEX_STATE_PATH).exists()


def hermes_source_available() -> bool:
    """Return whether local Hermes session state exists on this machine."""
    return Path(HERMES_STATE_PATH).exists()


def cursor_source_available() -> bool:
    """Return whether local Cursor composer state with token rows exists."""
    state_path = Path(CURSOR_STATE_PATH)
    if not state_path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{CURSOR_STATE_PATH}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT 1 FROM cursorDiskKV WHERE key LIKE 'composerData:%' AND CAST(value AS TEXT) LIKE '%tokenCount%' AND CAST(value AS TEXT) LIKE '%inputTokens%' LIMIT 1"
            ).fetchone()
            if row:
                return True
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return False


def current_tool_sources() -> list[dict]:
    """Return tool source metadata with the active DB path baked in."""
    sources = []
    for source in TOOL_SOURCES:
        item = dict(source)
        if item["id"] == "opencode":
            item["source_path"] = display_path(DB_PATH)
        elif item["id"] == "codex" and codex_source_available():
            item.update({
                "status": "active",
                "status_label": "Active source",
                "source_type": "SQLite state + JSONL rollouts",
                "source_path": display_path(CODEX_SOURCE_PATH),
            })
        elif item["id"] == "hermes" and hermes_source_available():
            item.update({
                "status": "active",
                "status_label": "Active source",
                "source_type": "Hermes session SQLite database",
                "source_path": display_path(HERMES_STATE_PATH),
            })
        elif item["id"] == "cursor" and cursor_source_available():
            item.update({
                "status": "active",
                "status_label": "Active source",
                "source_type": "Cursor global storage SQLite database",
                "source_path": display_path(CURSOR_SOURCE_PATH),
            })
        sources.append(item)
    return sources


def tool_source_label(tool_id: str | None) -> str | None:
    if not tool_id:
        return None
    for source in current_tool_sources():
        if source["id"] == tool_id:
            return source["label"]
    return tool_id
