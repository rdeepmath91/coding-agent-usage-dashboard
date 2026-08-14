#!/usr/bin/env python3
"""Restore native parent/sub-issue and dependency edges from the source graph."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class APIError(RuntimeError):
    pass


class PersonalGraphQL:
    def __init__(self, command: str) -> None:
        self.command = command

    def mutate(self, query: str, variables: dict[str, str]) -> dict:
        command = [self.command, "api", "graphql", "-f", f"query={query}"]
        for name, value in variables.items():
            command.extend(["-F", f"{name}={value}"])
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise APIError(f"GraphQL mutation failed (exit {result.returncode})")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise APIError("GraphQL mutation returned invalid JSON") from exc
        if value.get("errors"):
            raise APIError(json.dumps(value["errors"], sort_keys=True))
        return value.get("data") or {}


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def append_checkpoint(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def load_checkpoints(path: Path) -> set[str]:
    result: set[str] = set()
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record.get("key"), str):
            result.add(record["key"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--gh-command", default=os.path.expanduser("~/bin/gh-personal"))
    args = parser.parse_args()

    root = args.root
    graph = read_json(root / "archive" / "raw" / "github" / "issue-graph.json", {})
    nodes = ((graph.get("data") or {}).get("repository") or {}).get("issues", {}).get("nodes", [])
    object_map = read_json(root / "state" / "object-map.json", {})
    checkpoints_path = root / "state" / "import-checkpoints.jsonl"
    checkpoints = load_checkpoints(checkpoints_path)
    graphql = PersonalGraphQL(args.gh_command)

    parent_edges = []
    blocker_edges = []
    for node in nodes:
        child = int(node["number"])
        if node.get("parent"):
            parent_edges.append((int(node["parent"]["number"]), child))
        for blocking in (node.get("blockedBy") or {}).get("nodes") or []:
            blocker_edges.append((child, int(blocking["number"])))
    parent_edges = sorted(set(parent_edges))
    blocker_edges = sorted(set(blocker_edges))

    add_sub_issue = """
    mutation($issueId:ID!, $subIssueId:ID!) {
      addSubIssue(input:{issueId:$issueId, subIssueId:$subIssueId, replaceParent:false}) {
        issue { id number }
        subIssue { id number }
      }
    }
    """
    add_blocked_by = """
    mutation($issueId:ID!, $blockingIssueId:ID!) {
      addBlockedBy(input:{issueId:$issueId, blockingIssueId:$blockingIssueId}) {
        issue { id number }
        blockingIssue { id number }
      }
    }
    """

    for parent, child in parent_edges:
        key = f"parent:{parent}:{child}"
        if key in checkpoints:
            continue
        parent_map = object_map.get(str(parent))
        child_map = object_map.get(str(child))
        if not parent_map or not child_map:
            raise APIError(f"missing object map for relationship {key}")
        result = graphql.mutate(
            add_sub_issue,
            {"issueId": parent_map["destination_node_id"], "subIssueId": child_map["destination_node_id"]},
        )
        append_checkpoint(
            checkpoints_path,
            {
                "key": key,
                "kind": "parent",
                "source_parent": parent,
                "source_child": child,
                "result": result,
                "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
        checkpoints.add(key)

    for issue, blocking in blocker_edges:
        key = f"blocked-by:{issue}:{blocking}"
        if key in checkpoints:
            continue
        issue_map = object_map.get(str(issue))
        blocking_map = object_map.get(str(blocking))
        if not issue_map or not blocking_map:
            raise APIError(f"missing object map for relationship {key}")
        result = graphql.mutate(
            add_blocked_by,
            {"issueId": issue_map["destination_node_id"], "blockingIssueId": blocking_map["destination_node_id"]},
        )
        append_checkpoint(
            checkpoints_path,
            {
                "key": key,
                "kind": "blocked-by",
                "source_issue": issue,
                "source_blocking": blocking,
                "result": result,
                "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
        checkpoints.add(key)

    print(json.dumps({"parent_edges": len(parent_edges), "blocker_edges": len(blocker_edges)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"relationship import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
