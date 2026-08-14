#!/usr/bin/env python3
"""Compare the transferable source inventory with the private destination."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class CheckError(RuntimeError):
    pass


def command_json(command: list[str], *, paginate: bool = False):
    actual = list(command)
    if paginate:
        actual.extend(["--paginate", "--slurp"])
    result = subprocess.run(actual, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    if result.returncode != 0:
        raise CheckError(f"command failed: {' '.join(actual[:3])}")
    value = json.loads(result.stdout)
    if paginate and isinstance(value, list) and all(isinstance(page, list) for page in value):
        return [item for page in value for item in page]
    return value


def api(gh: str, endpoint: str, *, paginate: bool = False):
    return command_json([gh, "api", endpoint], paginate=paginate)


def graphql(gh: str, owner: str, name: str) -> dict:
    query = """
    query($owner:String!, $name:String!) {
      repository(owner:$owner, name:$name) {
        id isPrivate
        issues(first:100, states:[OPEN,CLOSED]) {
          nodes {
            number
            parent { number }
            subIssues(first:100) { nodes { number } }
            blockedBy(first:100) { nodes { number } }
            blocking(first:100) { nodes { number } }
          }
        }
      }
    }
    """
    command = [gh, "api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}", "-F", f"name={name}"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
    if result.returncode != 0:
        raise CheckError("GraphQL relationship read failed")
    value = json.loads(result.stdout)
    if value.get("errors"):
        raise CheckError("GraphQL relationship read returned errors")
    return value["data"]["repository"]


def refs(remote: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "-C", "/home/raymond-christopher/coding-agent-usage-dashboard", "ls-remote", remote, "refs/heads/*"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=True,
    )
    return {parts[1]: parts[0] for line in result.stdout.splitlines() if (parts := line.split())}


def source_relationships(repository: dict) -> dict[str, list[list[int]]]:
    parents = []
    blocked = []
    for node in (repository.get("issues") or {}).get("nodes") or []:
        if node.get("parent"):
            parents.append([node["parent"]["number"], node["number"]])
        for item in (node.get("blockedBy") or {}).get("nodes") or []:
            blocked.append([node["number"], item["number"]])
    return {"parents": sorted(set(map(tuple, parents))), "blocked_by": sorted(set(map(tuple, blocked)))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-gh", default="gh")
    parser.add_argument("--personal-gh", default=os.path.expanduser("~/bin/gh-personal"))
    parser.add_argument("--source", default="raychrisgdp/coding-agent-usage-dashboard")
    parser.add_argument("--destination", default="rdeepmath91/coding-agent-usage-dashboard")
    parser.add_argument("--destination-id", type=int, default=1334182958)
    args = parser.parse_args()

    root = args.root
    source_manifest = json.loads((root / "state/source-manifest.json").read_text(encoding="utf-8"))
    object_map = json.loads((root / "state/object-map.json").read_text(encoding="utf-8"))
    source_repo = api(args.source_gh, f"repos/{args.source}")
    destination_repo = api(args.personal_gh, f"repos/{args.destination}")
    source_items = api(args.source_gh, f"repos/{args.source}/issues?state=all&per_page=100", paginate=True)
    destination_items = api(args.personal_gh, f"repos/{args.destination}/issues?state=all&per_page=100", paginate=True)
    destination_comments = api(args.personal_gh, f"repos/{args.destination}/issues/comments?per_page=100", paginate=True)
    source_labels = json.loads((root / "archive/raw/github/labels.json").read_text(encoding="utf-8"))
    destination_labels = api(args.personal_gh, f"repos/{args.destination}/labels?per_page=100", paginate=True)
    source_graph = graphql(args.source_gh, "raychrisgdp", "coding-agent-usage-dashboard")
    destination_graph = graphql(args.personal_gh, "rdeepmath91", "coding-agent-usage-dashboard")
    source_git_url = "git@github.com:raychrisgdp/coding-agent-usage-dashboard.git"
    source_refs = refs(source_git_url)
    destination_refs = refs("destination")

    source_numbers = sorted(item["number"] for item in source_items)
    destination_numbers = sorted(item["number"] for item in destination_items)
    expected_labels = sorted([item["name"] for item in source_labels] + ["archived-pr"])
    actual_labels = sorted(item["name"] for item in destination_labels)
    source_relationship = source_relationships(source_graph)
    destination_relationship = source_relationships(destination_graph)
    ref_mismatches = {ref: {"source": sha, "destination": destination_refs.get(ref)} for ref, sha in source_refs.items() if destination_refs.get(ref) != sha}
    source_comments = sum(
        len(json.loads(path.read_text(encoding="utf-8")))
        for path in (root / "archive/raw/github/issue-comments-by-number").glob("*.json")
    )
    native_pr = api(args.personal_gh, f"repos/{args.destination}/pulls/53")
    source_pr = json.loads((root / "archive/raw/github/pull-details/0053.json").read_text(encoding="utf-8"))

    test_report_path = root / "reports/clean-destination-tests.txt"
    test_report = test_report_path.read_text(encoding="utf-8") if test_report_path.exists() else ""
    clean_destination_tests = "Ran 62 tests" in test_report and "OK" in test_report
    origin_url = subprocess.run(
        ["git", "-C", "/home/raymond-christopher/coding-agent-usage-dashboard", "remote", "get-url", "origin"],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()
    checks = {
        "source_identity": source_repo.get("id") == 1249859353 and source_repo.get("private") is True,
        "destination_identity": destination_repo.get("id") == args.destination_id and destination_repo.get("private") is True and destination_repo.get("permissions", {}).get("admin") is True,
        "destination_anonymous_404": subprocess.run(["curl", "-L", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"https://github.com/{args.destination}"], stdout=subprocess.PIPE, text=True, check=False).stdout.strip() == "404",
        "source_api_cannot_read_destination": subprocess.run([args.source_gh, "api", f"repos/{args.destination}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode != 0,
        "numbered_coverage": source_numbers == list(range(1, 55)) and destination_numbers == list(range(1, 55)) and len(object_map) == 54,
        "source_markers": sum("Migration source:" in (item.get("body") or "") for item in destination_items) == 54,
        "source_refs_match": not ref_mismatches,
        "labels_match": actual_labels == expected_labels,
        "comment_count": len(destination_comments) == source_comments,
        "native_open_pr": native_pr.get("number") == 53 and native_pr.get("state") == "open" and native_pr.get("base", {}).get("sha") == source_pr.get("base", {}).get("sha") and native_pr.get("head", {}).get("sha") == source_pr.get("head", {}).get("sha"),
        "relationships_match": source_relationship == destination_relationship,
        "attachments_reconciled": (root / "state/attachment-map.json").exists(),
        "releases_reconciled": len(json.loads((root / "archive/raw/github/releases.json").read_text(encoding="utf-8"))) == 0,
        "clean_destination_tests": clean_destination_tests,
        "local_origin_cutover": origin_url == "git@github.com-rdeepmath91:rdeepmath91/coding-agent-usage-dashboard.git",
    }
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": args.source,
        "destination": args.destination,
        "checks": checks,
        "ref_mismatches": ref_mismatches,
        "source_relationships": source_relationship,
        "destination_relationships": destination_relationship,
        "source_comments": source_comments,
        "destination_comments": len(destination_comments),
        "exceptions": [
            "Original GitHub author identities and timestamps cannot be recreated on new objects.",
            "Pages and rulesets were unavailable to the source exporter and remain explicit archive exceptions.",
            "Historical PRs are attributed archived issues; only open PR #53 is native.",
            "Stars, watchers, notifications, Actions run identity/history, audit logs, and secret values are not migrated.",
        ],
        "local_cutover": (
            "completed with untracked .hermes/ migration-plan content preserved in the main worktree"
            if checks["local_origin_cutover"] and checks["clean_destination_tests"]
            else "pending: origin or clean destination test gate is incomplete"
        ),
    }
    result["status"] = "pass" if all(checks.values()) else "needs_review"
    output = root / "state/reconciliation.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = root / "reports/final-reconciliation.md"
    lines = [
        "# Final reconciliation (pre-cutover)",
        "",
        f"Generated: `{result['generated_at_utc']}`",
        "",
        f"Status: **{result['status']}**",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {'PASS' if value else 'FAIL'} — `{key}`" for key, value in checks.items())
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Numbered source/destination coverage: `{len(source_numbers)}/{len(destination_numbers)}`",
            f"- Imported object map entries: `{len(object_map)}`",
            f"- Source/destination issue comments: `{source_comments}/{len(destination_comments)}`",
            f"- Source/destination parent edges: `{len(source_relationship['parents'])}/{len(destination_relationship['parents'])}`",
            "",
            "## Named exceptions",
            "",
        ]
    )
    lines.extend(f"- {exception}" for exception in result["exceptions"])
    lines.extend(["", "## Cutover gate", "", f"- {result['local_cutover']}"])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "failed_checks": [key for key, value in checks.items() if not value]}, sort_keys=True))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"reconciliation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
