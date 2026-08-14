#!/usr/bin/env python3
"""Add original assignee attribution to reconstructed destination headers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
    args = parser.parse_args()

    numbers = [2, 6, 14, 19, 21, 26, 27, 37, 48]
    github = PersonalGitHub(args.gh_command)
    changes = []
    for number in numbers:
        item = github.api(f"repos/{args.destination}/issues/{number}")
        body = item.get("body") or ""
        if "> Original assignees:" in body:
            continue
        match = re.search(r"^> Original author:.*$", body, flags=re.MULTILINE)
        if not match:
            raise APIError(f"destination #{number} has no attribution header")
        insertion = "> Original assignees: `raychrisgdp`"
        new_body = body[: match.end()] + "\n" + insertion + body[match.end() :]
        github.api(f"repos/{args.destination}/issues/{number}", method="PATCH", payload={"body": new_body})
        changes.append({"number": number, "assignees": ["raychrisgdp"]})

    state = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "raychrisgdp/coding-agent-usage-dashboard",
        "changes": changes,
        "total": len(numbers),
    }
    write_json(args.root / "state/assignee-attribution.json", state)
    print(json.dumps({"updated": len(changes), "total": len(numbers)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
