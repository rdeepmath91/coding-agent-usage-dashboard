#!/usr/bin/env python3
"""Create source labels and milestones in the verified personal repository."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


class APIError(RuntimeError):
    pass


class PersonalGitHub:
    def __init__(self, command: str) -> None:
        self.command = command

    def api(self, endpoint: str, *, method: str = "GET", payload: dict | None = None, paginate: bool = False):
        command = [self.command, "api", endpoint]
        if method != "GET":
            command.extend(["-X", method])
        if paginate:
            command.extend(["--paginate", "--slurp"])
        input_data = None
        if payload is not None:
            command.extend(["--input", "-"])
            input_data = json.dumps(payload)
        result = subprocess.run(
            command,
            input=input_data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            raise APIError(f"{method} {endpoint} failed (exit {result.returncode})")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise APIError(f"{method} {endpoint} returned invalid JSON") from exc
        if paginate and isinstance(value, list) and all(isinstance(page, list) for page in value):
            return [item for page in value for item in page]
        return value


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", default="rdeepmath91/coding-agent-usage-dashboard")
    parser.add_argument("--expected-database-id", type=int, default=1334182958)
    parser.add_argument("--gh-command", default=os.path.expanduser("~/bin/gh-personal"))
    args = parser.parse_args()

    root = args.root
    raw = root / "archive" / "raw" / "github"
    source_labels = json.loads((raw / "labels.json").read_text(encoding="utf-8"))
    source_milestones = json.loads((raw / "milestones.json").read_text(encoding="utf-8"))
    github = PersonalGitHub(args.gh_command)

    destination = github.api(f"repos/{args.destination}")
    if destination.get("full_name") != args.destination or destination.get("id") != args.expected_database_id:
        raise APIError("destination identity mismatch")
    if destination.get("private") is not True:
        raise APIError("destination is not private")

    existing_labels = github.api(f"repos/{args.destination}/labels?per_page=100", paginate=True)
    labels_by_name = {item["name"]: item for item in existing_labels}
    desired_labels = list(source_labels) + [
        {
            "name": "archived-pr",
            "color": "5319e7",
            "description": "Historical pull request reconstructed as an attributed archive record",
        }
    ]
    label_map = {}
    checkpoints = []
    for label in desired_labels:
        name = label["name"]
        encoded_name = quote(name, safe="")
        existing = labels_by_name.get(name)
        payload = {key: label.get(key) for key in ("new_name", "color", "description") if label.get(key) is not None}
        payload.pop("new_name", None)
        if existing is None:
            created = github.api(f"repos/{args.destination}/labels", method="POST", payload=label)
        else:
            created = github.api(f"repos/{args.destination}/labels/{encoded_name}", method="PATCH", payload=payload)
        label_map[name] = {
            "source_name": name,
            "destination_name": created.get("name", name),
            "source_color": label.get("color"),
            "destination_id": created.get("id"),
        }
        checkpoints.append({"kind": "label", "name": name, "destination_id": created.get("id")})

    existing_milestones = github.api(
        f"repos/{args.destination}/milestones?state=all&per_page=100", paginate=True
    )
    milestones_by_title = {item["title"]: item for item in existing_milestones}
    milestone_map = {}
    for milestone in source_milestones:
        title = milestone["title"]
        payload = {
            "title": title,
            "state": milestone.get("state", "open"),
            "description": milestone.get("description") or "",
            "due_on": milestone.get("due_on"),
        }
        existing = milestones_by_title.get(title)
        if existing is None:
            created = github.api(f"repos/{args.destination}/milestones", method="POST", payload=payload)
        else:
            created = github.api(
                f"repos/{args.destination}/milestones/{existing['number']}", method="PATCH", payload=payload
            )
        milestone_map[title] = {
            "source_number": milestone.get("number"),
            "destination_number": created.get("number"),
            "destination_id": created.get("id"),
        }
        checkpoints.append({"kind": "milestone", "title": title, "destination_id": created.get("id")})

    write_json(root / "state" / "label-map.json", label_map)
    write_json(root / "state" / "milestone-map.json", milestone_map)
    checkpoint_path = root / "state" / "import-checkpoints.jsonl"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as handle:
        for checkpoint in checkpoints:
            checkpoint["completed_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            handle.write(json.dumps(checkpoint, sort_keys=True) + "\n")

    print(json.dumps({"labels": len(label_map), "milestones": len(milestone_map)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"label/milestone import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
