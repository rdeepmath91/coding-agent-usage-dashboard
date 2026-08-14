#!/usr/bin/env python3
"""Dispatch destination CI on the unchanged PR #53 head ref and verify it."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


class APIError(RuntimeError):
    pass


class PersonalGitHub:
    def __init__(self, command: str) -> None:
        self.command = command

    def api(self, endpoint: str, *, method: str = "GET", payload: dict | None = None):
        command = [self.command, "api", endpoint]
        if method != "GET":
            command.extend(["-X", method])
        input_data = None
        if payload is not None:
            command.extend(["--input", "-"])
            input_data = json.dumps(payload)
        result = subprocess.run(command, input=input_data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
        if result.returncode != 0:
            raise APIError(f"{method} {endpoint} failed")
        return json.loads(result.stdout) if result.stdout.strip() else None


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", default="rdeepmath91/coding-agent-usage-dashboard")
    parser.add_argument("--gh-command", default=os.path.expanduser("~/bin/gh-personal"))
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()

    github = PersonalGitHub(args.gh_command)
    pr = github.api(f"repos/{args.destination}/pulls/53")
    head_sha = pr.get("head", {}).get("sha")
    head_ref = pr.get("head", {}).get("ref")
    if pr.get("state") != "open" or head_sha != "edd02b199a9b1c7c2b64e7233bb52b6b872af64c":
        raise APIError("PR #53 is not the expected open PR/head")
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    github.api(f"repos/{args.destination}/actions/workflows/ci.yml/dispatches", method="POST", payload={"ref": head_ref})
    deadline = time.monotonic() + args.timeout
    runs = []
    checks = []
    while time.monotonic() < deadline:
        run_response = github.api(f"repos/{args.destination}/actions/runs?head_sha={head_sha}&per_page=100")
        runs = [run for run in (run_response or {}).get("workflow_runs", []) if run.get("event") == "workflow_dispatch"]
        checks_response = github.api(f"repos/{args.destination}/commits/{head_sha}/check-runs")
        checks = [check for check in (checks_response or {}).get("check_runs", []) if check.get("name") == "test"]
        if runs and checks and all(check.get("status") == "completed" for check in checks):
            break
        time.sleep(10)
    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    success = bool(checks) and all(check.get("conclusion") == "success" for check in checks)
    state = {
        "operation": "workflow-dispatch-pr-53-head",
        "migration_operation": True,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "destination": args.destination,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "runs": [{key: run.get(key) for key in ("id", "name", "event", "status", "conclusion", "head_sha", "html_url")} for run in runs],
        "test_checks": [{key: check.get(key) for key in ("id", "name", "status", "conclusion", "started_at", "completed_at", "html_url")} for check in checks],
        "success": success,
    }
    write_json(args.root / "state/pr53-ci-dispatch.json", state)
    print(json.dumps({"head_sha": head_sha, "runs": len(runs), "test_checks": len(checks), "success": success}, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"PR #53 CI dispatch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
