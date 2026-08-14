#!/usr/bin/env python3
"""Map and optionally rewrite operational source links in destination records."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SOURCE_OWNER = "raychrisgdp"
SOURCE_REPO = "coding-agent-usage-dashboard"
DEST_OWNER = "rdeepmath91"
DEST_REPO = "coding-agent-usage-dashboard"
DEST_ROOT = f"https://github.com/{DEST_OWNER}/{DEST_REPO}"
URL_RE = re.compile(r"https?://[^\s<>()\"'`]+")
TRAILING = ".,;:!?)]}"


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
        result = subprocess.run(command, input=input_data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
        if result.returncode != 0:
            raise APIError(f"{method} {endpoint} failed")
        value = json.loads(result.stdout)
        if paginate and isinstance(value, list) and all(isinstance(page, list) for page in value):
            return [item for page in value for item in page]
        return value


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_ref_map(root: Path) -> tuple[set[str], dict[str, str]]:
    source_branches = json.loads((root / "archive/raw/github/branches.json").read_text(encoding="utf-8"))
    branch_names = {item.get("name") for item in source_branches if item.get("name")}
    ref_map = {}
    for path in (root / "archive/raw/github/pull-details").glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        head = item.get("head") or {}
        if head.get("ref") and head.get("sha"):
            ref_map[head["ref"]] = head["sha"]
    return branch_names, ref_map


def map_url(url: str, branch_names: set[str], ref_map: dict[str, str], root: Path) -> tuple[str, str | None]:
    trailing = ""
    while url and url[-1] in TRAILING:
        trailing = url[-1] + trailing
        url = url[:-1]
    parts = urlsplit(url)
    path = parts.path
    source_prefix = f"/{SOURCE_OWNER}/{SOURCE_REPO}"
    patch_match = re.fullmatch(rf"{re.escape(source_prefix)}/pull/(\d+)\.(patch|diff)", path)
    if parts.netloc == "github.com" and patch_match:
        number, suffix = patch_match.groups()
        replacement = f"{DEST_ROOT}/blob/migration-archive/archive/pr-artifacts/{int(number):04d}.{suffix}"
        return replacement + trailing, "historical-pr-artifact"

    if parts.netloc == "github.com" and path.startswith(source_prefix):
        remainder = path[len(source_prefix):]
        segments = remainder.strip("/").split("/") if remainder.strip("/") else []
        if not segments:
            return DEST_ROOT + ("?" + parts.query if parts.query else "") + trailing, "repository"
        if segments[0] in {"issues", "pull"} and len(segments) >= 2 and segments[1].isdigit():
            number = int(segments[1])
            target_kind = "pull" if segments[0] == "pull" and number == 53 else "issues"
            replacement_path = f"/{target_kind}/{number}" + ("/" + "/".join(segments[2:]) if len(segments) > 2 else "")
            return urlunsplit((parts.scheme, "github.com", f"/{DEST_OWNER}/{DEST_REPO}{replacement_path}", parts.query, parts.fragment)) + trailing, "numbered-object"
        if segments[0] in {"blob", "tree"} and len(segments) >= 3:
            ref = segments[1]
            mapped_ref = ref if ref in branch_names or re.fullmatch(r"[0-9a-f]{40}", ref) else ref_map.get(ref)
            if mapped_ref is None:
                return url + trailing, "unresolved-source-ref"
            replacement = f"{DEST_ROOT}/{segments[0]}/{mapped_ref}/{'/'.join(segments[2:])}"
            return replacement + (("?" + parts.query) if parts.query else "") + trailing, "repository-content"
        replacement = urlunsplit((parts.scheme, "github.com", f"/{DEST_OWNER}/{DEST_REPO}{remainder}", parts.query, parts.fragment))
        return replacement + trailing, "repository-link"

    if parts.netloc == "raw.githubusercontent.com":
        segments = path.strip("/").split("/")
        if len(segments) >= 3 and segments[0] == SOURCE_OWNER and segments[1] == SOURCE_REPO:
            ref = segments[2]
            mapped_ref = ref if ref in branch_names or re.fullmatch(r"[0-9a-f]{40}", ref) else ref_map.get(ref)
            if mapped_ref is None:
                return url + trailing, "unresolved-source-ref"
            replacement = urlunsplit((parts.scheme, parts.netloc, f"/{DEST_OWNER}/{DEST_REPO}/{mapped_ref}/{'/'.join(segments[3:])}", parts.query, parts.fragment))
            return replacement + trailing, "raw-repository-content"

    return url + trailing, None


def rewrite_text(text: str, branch_names: set[str], ref_map: dict[str, str], root: Path, context: str, links: dict[str, dict]) -> str:
    output_lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("> Original URL:"):
            output_lines.append(line)
            continue
        def replace(match: re.Match) -> str:
            original = match.group(0)
            replacement, category = map_url(original, branch_names, ref_map, root)
            if category and replacement != original:
                record = links.setdefault(original, {"source_url": original, "replacement_url": replacement, "category": category, "contexts": []})
                if context not in record["contexts"]:
                    record["contexts"].append(context)
            return replacement
        output_lines.append(URL_RE.sub(replace, line))
    return "".join(output_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--gh-command", default=os.path.expanduser("~/bin/gh-personal"))
    parser.add_argument("--destination", default="rdeepmath91/coding-agent-usage-dashboard")
    args = parser.parse_args()

    github = PersonalGitHub(args.gh_command)
    branch_names, ref_map = load_ref_map(args.root)
    issues = github.api(f"repos/{args.destination}/issues?state=all&per_page=100", paginate=True)
    comments = github.api(f"repos/{args.destination}/issues/comments?per_page=100", paginate=True)
    links: dict[str, dict] = {}
    changes = []
    snapshots = {"issues": issues, "comments": comments}
    for item in issues:
        old = item.get("body") or ""
        new = rewrite_text(old, branch_names, ref_map, args.root, f"issue:{item['number']}", links)
        if new != old:
            changes.append({"kind": "issue", "number": item["number"], "id": item.get("id"), "old_body": old, "new_body": new})
    for item in comments:
        old = item.get("body") or ""
        new = rewrite_text(old, branch_names, ref_map, args.root, f"comment:{item['id']}", links)
        if new != old:
            changes.append({"kind": "comment", "number": item.get("issue_url"), "id": item["id"], "old_body": old, "new_body": new})

    plan = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "apply": args.apply,
        "link_count": len(links),
        "change_count": len(changes),
        "unresolved": sorted({url for record in links.values() if record["category"] == "unresolved-source-ref" for url in [record["source_url"]]}),
        "links": links,
        "changes": [{key: value for key, value in change.items() if key not in {"old_body", "new_body"}} for change in changes],
    }
    write_json(args.root / "state" / "link-map.json", plan)
    write_json(args.root / "state" / "link-rewrite-before.json", snapshots)
    if args.apply:
        for change in changes:
            if change["kind"] == "issue":
                github.api(f"repos/{args.destination}/issues/{change['number']}", method="PATCH", payload={"body": change["new_body"]})
            else:
                github.api(f"repos/{args.destination}/issues/comments/{change['id']}", method="PATCH", payload={"body": change["new_body"]})
        plan["applied_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_json(args.root / "state" / "link-map.json", plan)
    print(json.dumps({"apply": args.apply, "links": len(links), "changes": len(changes), "unresolved": len(plan["unresolved"])}, sort_keys=True))
    return 0 if not plan["unresolved"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (APIError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"link rewrite failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
