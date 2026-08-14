#!/usr/bin/env python3
"""Trigger destination PR #53 CI by the approved close/reopen operation."""

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
        return json.loads(result.stdout)


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
    before = github.api(f"repos/{args.destination}/pulls/53")
    expected_head = before.get("head", {}).get("sha")
    if before.get("state") != "open" or expected_head != "edd02b199a9b1c7c2b64e7233bb52b6b872af64c":
        raise APIError("PR #53 is not the expected open destination PR/head")
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    closed = github.api(f"repos/{args.destination}/pulls/53", method="PATCH", payload={"state": "closed"})
    reopened = github.api(f"repos/{args.destination}/pulls/53", method="PATCH", payload={"state": "open"})
    deadline = time.monotonic() + args.timeout
    checks = []
    while time.monotonic() < deadline:
        result = github.api(f"repos/{args.destination}/commits/{expected_head}/check-runs")
        checks = result.get("check_runs") or []
        test_checks = [check for check in checks if check.get("name") == "test"]
        if test_checks and all(check.get("status") == "completed" for check in test_checks):
            break
        time.sleep(10)
    finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    test_checks = [check for check in checks if check.get("name") == "test"]
    success = bool(test_checks) and all(check.get("conclusion") == "success" for check in test_checks)
    state = {
        "operation": "close-reopen-pr-53",
        "migration_operation": True,
        "started_at_utc": started,
        "finished_at_utc": finished,
        "destination": args.destination,
        "head_sha": expected_head,
        "before": {key: before.get(key) for key in ("number", "state", "draft", "updated_at", "head", "base")},
        "closed": {key: closed.get(key) for key in ("number", "state", "updated_at")},
        "reopened": {key: reopened.get(key) for key in ("number", "state", "updated_at")},
        "test_checks": [{key: check.get(key) for key in ("id", "name", "status", "conclusion", "started_at", "completed_at", "html_url")} for check in test_checks],
        "success": success,
    }
    write_json(args.root / "state/pr53-ci-trigger.json", state)
    print(json.dumps({"head_sha": expected_head, "test_checks": len(test_checks), "success": success}, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"PR #53 CI trigger failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
