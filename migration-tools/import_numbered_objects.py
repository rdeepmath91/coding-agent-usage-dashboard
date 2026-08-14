#!/usr/bin/env python3
"""Reconstruct the source 1..N issue/PR sequence in a private repository.

Historical closed/merged pull requests become explicitly labeled archive issues.
The source's currently open pull request is attempted as a native pull request
only after its base/head SHAs are verified in the destination.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


SOURCE = "raychrisgdp/coding-agent-usage-dashboard"


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


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def neutralize_mentions(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"(?<![A-Za-z0-9_])@([A-Za-z0-9-]+)", r"＠\1", value)


def source_stamp(item: dict, kind: str, number: int) -> str:
    return "\n".join(
        [
            f"> Migration source: `{SOURCE}` {kind} #{number}",
            f"> Original author: `{(item.get('user') or {}).get('login', 'unknown')}`",
            f"> Created: `{item.get('created_at') or 'unknown'}`",
            f"> Updated: `{item.get('updated_at') or 'unknown'}`",
            f"> Original state: `{item.get('state') or 'unknown'}`",
            f"> Original URL: {item.get('html_url') or 'unavailable'}",
            "> Original GitHub timestamps, author identity, reactions, and timeline events are preserved in the private raw archive.",
        ]
    )


def format_issue_body(item: dict, number: int, *, kind: str = "issue") -> str:
    body = neutralize_mentions(item.get("body"))
    return f"{source_stamp(item, kind, number)}\n\n---\n\n{body}".rstrip() + "\n"


def format_archived_pr_body(item: dict, number: int, raw: Path) -> str:
    details = item
    base = details.get("base") or {}
    head = details.get("head") or {}
    lines = [
        source_stamp(item, "pull request (archived)", number),
        "",
        "> This is a transparent archive record because ordinary GitHub APIs cannot recreate the original historical PR identity, author, timestamps, reviews, merge actor, or timeline.",
        "",
        "## Original pull request metadata",
        "",
        f"- Base: `{base.get('ref', 'unknown')}` at `{base.get('sha', 'unknown')}`",
        f"- Head: `{head.get('ref', 'unknown')}` at `{head.get('sha', 'unknown')}`",
        f"- Merged at: `{details.get('merged_at') or 'not merged'}`",
        f"- Merge commit: `{details.get('merge_commit_sha') or 'none'}`",
        f"- Merge actor: `{(details.get('merged_by') or {}).get('login', 'unknown')}`",
        f"- Patch URL: {details.get('patch_url') or 'unavailable'}",
        f"- Diff URL: {details.get('diff_url') or 'unavailable'}",
        "",
        "## Original body",
        "",
        neutralize_mentions(details.get("body")),
        "",
        "## Archived raw records",
        "",
        f"- `migration-archive:{raw}/pull-details/{number:04d}.json`",
        f"- `migration-archive:{raw}/pull-commits/{number:04d}.json`",
        f"- `migration-archive:{raw}/pull-files/{number:04d}.json`",
        f"- `migration-archive:{raw}/pull-reviews/{number:04d}.json`",
        f"- `migration-archive:{raw}/pull-review-comments-by-number/{number:04d}.json`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def comment_body(kind: str, record: dict, original_number: int) -> str:
    user = (record.get("user") or {}).get("login", "unknown")
    created = record.get("created_at") or record.get("submitted_at") or "unknown"
    body = neutralize_mentions(record.get("body"))
    header = [
        f"> Archived {kind} from `{SOURCE}` #{original_number}",
        f"> Original author: `{user}`",
        f"> Original timestamp: `{created}`",
        f"> Original URL: {record.get('html_url') or 'unavailable'}",
    ]
    extra = []
    if kind == "review":
        extra = [f"> Review state: `{record.get('state') or 'unknown'}`"]
    if kind == "review comment":
        extra = [
            f"> Path: `{record.get('path') or 'unknown'}`",
            f"> Line: `{record.get('line') or record.get('original_line') or 'unknown'}`",
        ]
        diff = record.get("diff_hunk")
        if diff:
            body = f"```diff\n{diff}\n```\n\n{body}"
    return "\n".join(header + extra + ["", body]).rstrip() + "\n"


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
        key = record.get("key")
        if isinstance(key, str):
            result.add(key)
    return result


def load_object_map(path: Path) -> dict[str, dict]:
    value = read_json(path, {})
    return value if isinstance(value, dict) else {}


def destination_next_number(github: PersonalGitHub, destination: str, expected: int) -> int:
    """Read the next sequence number, tolerating short GitHub indexing lag."""
    for _ in range(8):
        objects = github.api(f"repos/{destination}/issues?state=all&per_page=100", paginate=True)
        numbers = [int(item["number"]) for item in objects if isinstance(item, dict) and "number" in item]
        candidate = max(numbers, default=0) + 1
        if candidate >= expected:
            return candidate
        if expected > 1:
            try:
                previous = github.api(f"repos/{destination}/issues/{expected - 1}")
            except APIError:
                previous = None
            if isinstance(previous, dict) and previous.get("number") == expected - 1:
                return expected
        time.sleep(1)
    return candidate


def labels_for(item: dict, label_map: dict[str, dict], *, archived: bool) -> list[str]:
    result = []
    for label in item.get("labels") or []:
        name = label.get("name") if isinstance(label, dict) else label
        if isinstance(name, str) and name in label_map:
            result.append(label_map[name]["destination_name"])
    if archived:
        result.append("archived-pr")
    return sorted(set(result))


def milestone_number(item: dict, milestone_map: dict[str, dict]) -> int | None:
    milestone = item.get("milestone")
    if not isinstance(milestone, dict):
        return None
    mapped = milestone_map.get(milestone.get("title"))
    return mapped.get("destination_number") if mapped else None


def post_comment(github: PersonalGitHub, destination: str, number: int, body: str) -> dict:
    return github.api(f"repos/{destination}/issues/{number}/comments", method="POST", payload={"body": body})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", default="rdeepmath91/coding-agent-usage-dashboard")
    parser.add_argument("--expected-database-id", type=int, default=1334182958)
    parser.add_argument("--gh-command", default=os.path.expanduser("~/bin/gh-personal"))
    args = parser.parse_args()

    root = args.root
    raw = root / "archive" / "raw" / "github"
    source_manifest = read_json(root / "state" / "source-manifest.json", {})
    label_map = read_json(root / "state" / "label-map.json", {})
    milestone_map = read_json(root / "state" / "milestone-map.json", {})
    object_map_path = root / "state" / "object-map.json"
    object_map = load_object_map(object_map_path)
    checkpoint_path = root / "state" / "import-checkpoints.jsonl"
    checkpoints = load_checkpoints(checkpoint_path)
    github = PersonalGitHub(args.gh_command)

    destination = github.api(f"repos/{args.destination}")
    if destination.get("full_name") != args.destination or destination.get("id") != args.expected_database_id:
        raise APIError("destination identity mismatch")
    if destination.get("private") is not True:
        raise APIError("destination is not private")

    numbered = source_manifest.get("numbered") or {}
    numbers = numbered.get("numbers") or []
    pr_numbers = set(numbered.get("pull_request_numbers") or [])
    if numbers != list(range(1, (max(numbers) if numbers else 0) + 1)):
        raise APIError("source manifest number sequence is not contiguous")

    for number in numbers:
        number = int(number)
        key = f"object:{number}"
        detail_path = raw / "issue-details" / f"{number:04d}.json"
        detail = read_json(detail_path, None)
        if not isinstance(detail, dict):
            raise APIError(f"missing source detail for #{number}")
        is_pr = number in pr_numbers
        is_open_native_pr = is_pr and detail.get("state") == "open"
        is_archived_pr = is_pr and not is_open_native_pr

        mapped = object_map.get(str(number))
        if mapped is None:
            next_number = destination_next_number(github, args.destination, number)
            if next_number != number:
                raise APIError(f"destination next number is {next_number}, expected {number}")
            if is_open_native_pr:
                pull = read_json(raw / "pull-details" / f"{number:04d}.json", None)
                if not isinstance(pull, dict):
                    raise APIError(f"missing pull detail for open PR #{number}")
                base = pull.get("base") or {}
                head = pull.get("head") or {}
                base_ref = base.get("ref")
                head_ref = head.get("ref")
                base_sha = base.get("sha")
                head_sha = head.get("sha")
                if not all(isinstance(value, str) and value for value in (base_ref, head_ref, base_sha, head_sha)):
                    raise APIError(f"open PR #{number} has incomplete base/head metadata")
                for ref, expected_sha in ((base_ref, base_sha), (head_ref, head_sha)):
                    ref_response = github.api(
                        f"repos/{args.destination}/git/ref/heads/{quote(ref, safe='')}"
                    )
                    actual_sha = ((ref_response.get("object") or {}).get("sha"))
                    if actual_sha != expected_sha:
                        raise APIError(
                            f"open PR #{number} ref {ref!r} is {actual_sha}, expected {expected_sha}"
                        )
                created = github.api(
                    f"repos/{args.destination}/pulls",
                    method="POST",
                    payload={
                        "title": detail.get("title") or f"PR #{number}",
                        "head": head_ref,
                        "base": base_ref,
                        "body": format_issue_body(detail, number, kind="pull request"),
                    },
                )
                native_kind = "pull_request"
            else:
                if is_archived_pr:
                    pull = read_json(raw / "pull-details" / f"{number:04d}.json", None)
                    if not isinstance(pull, dict):
                        raise APIError(f"missing pull detail for archived PR #{number}")
                    body = format_archived_pr_body(pull, number, "archive/raw/github")
                else:
                    body = format_issue_body(detail, number)
                created = github.api(
                    f"repos/{args.destination}/issues",
                    method="POST",
                    payload={
                        "title": detail.get("title") or f"Issue #{number}",
                        "body": body,
                        "labels": labels_for(detail, label_map, archived=is_archived_pr),
                        "milestone": milestone_number(detail, milestone_map),
                    },
                )
                native_kind = "archived_pr_issue" if is_archived_pr else "issue"
            destination_number = int(created.get("number", -1))
            if destination_number != number:
                raise APIError(f"created source #{number} as destination #{destination_number}")
            mapped = {
                "source_number": number,
                "source_kind": "pull_request" if is_pr else "issue",
                "source_id": detail.get("id"),
                "source_node_id": detail.get("node_id"),
                "source_url": detail.get("html_url"),
                "destination_number": destination_number,
                "destination_kind": native_kind,
                "destination_id": created.get("id"),
                "destination_node_id": created.get("node_id"),
                "destination_url": created.get("html_url"),
                "source_assignees_omitted": [
                    assignee.get("login")
                    for assignee in detail.get("assignees") or []
                    if isinstance(assignee, dict) and assignee.get("login")
                ],
                "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            object_map[str(number)] = mapped
            write_json(object_map_path, object_map)
            append_checkpoint(
                checkpoint_path,
                {"key": key, "kind": "object", "source_number": number, "destination_number": destination_number},
            )

        destination_number = int(mapped["destination_number"])

        # Native PRs need labels/milestones applied through the issue endpoint.
        patch_payload = {
            "labels": labels_for(detail, label_map, archived=is_archived_pr),
            "milestone": milestone_number(detail, milestone_map),
        }
        if patch_payload["labels"] or patch_payload["milestone"] is not None:
            github.api(
                f"repos/{args.destination}/issues/{destination_number}",
                method="PATCH",
                payload=patch_payload,
            )

        comment_records: list[tuple[str, str, dict]] = []
        issue_comments = read_json(raw / "issue-comments-by-number" / f"{number:04d}.json", [])
        for index, record in enumerate(issue_comments if isinstance(issue_comments, list) else []):
            comment_records.append((f"comment:{number}:{index}", "comment", record))
        if is_pr:
            reviews = read_json(raw / "pull-reviews" / f"{number:04d}.json", [])
            for index, record in enumerate(reviews if isinstance(reviews, list) else []):
                comment_records.append((f"review:{number}:{index}", "review", record))
            review_comments = read_json(raw / "pull-review-comments-by-number" / f"{number:04d}.json", [])
            for index, record in enumerate(review_comments if isinstance(review_comments, list) else []):
                comment_records.append((f"review-comment:{number}:{index}", "review comment", record))
        comment_records.sort(key=lambda value: (value[2].get("created_at") or value[2].get("submitted_at") or "", value[0]))
        for comment_key, kind, record in comment_records:
            if comment_key in checkpoints:
                continue
            created_comment = post_comment(
                github,
                args.destination,
                destination_number,
                comment_body(kind, record, number),
            )
            append_checkpoint(
                checkpoint_path,
                {
                    "key": comment_key,
                    "kind": kind,
                    "source_number": number,
                    "destination_number": destination_number,
                    "destination_comment_id": created_comment.get("id"),
                },
            )
            checkpoints.add(comment_key)

        desired_state = detail.get("state")
        if desired_state == "closed":
            state_key = f"state:{number}"
            if state_key not in checkpoints:
                payload = {"state": "closed"}
                if detail.get("state_reason") in {"completed", "not_planned", "reopened"}:
                    payload["state_reason"] = detail["state_reason"]
                github.api(
                    f"repos/{args.destination}/issues/{destination_number}",
                    method="PATCH",
                    payload=payload,
                )
                append_checkpoint(
                    checkpoint_path,
                    {"key": state_key, "kind": "state", "source_number": number, "state": "closed"},
                )
                checkpoints.add(state_key)

    write_json(object_map_path, object_map)
    print(json.dumps({"objects": len(object_map), "last_number": max(map(int, object_map), default=0)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"numbered import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
