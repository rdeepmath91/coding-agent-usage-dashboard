#!/usr/bin/env python3
"""Export the source repository through the source-account gh profile.

This exporter is deliberately read-only with respect to GitHub. It writes raw
API responses and a normalized manifest under the migration workspace. It does
not create repositories, push refs, cancel transfers, or export secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


class GitHubAPIError(RuntimeError):
    def __init__(self, endpoint: str, returncode: int) -> None:
        super().__init__(f"gh api failed for {endpoint!r} (exit {returncode})")
        self.endpoint = endpoint
        self.returncode = returncode


class Exporter:
    def __init__(self, root: Path, source: str, expected_id: int, gh: str) -> None:
        self.root = root
        self.source = source
        self.expected_id = expected_id
        self.gh = gh
        self.raw_root = root / "archive" / "raw" / "github"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.collections: dict[str, dict[str, Any]] = {}
        self.unavailable: list[dict[str, Any]] = []

    def api(self, endpoint: str, *, paginate: bool = False) -> Any:
        command = [self.gh, "api", endpoint]
        if paginate:
            command.extend(["--paginate", "--slurp"])
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if result.returncode != 0:
            raise GitHubAPIError(endpoint, result.returncode)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSON from gh api for {endpoint!r}") from exc
        if paginate and isinstance(value, list) and all(isinstance(page, list) for page in value):
            flattened: list[Any] = []
            for page in value:
                flattened.extend(page)
            return flattened
        return value

    @staticmethod
    def count(value: Any) -> int | None:
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for key in ("total_count", "count"):
                if isinstance(value.get(key), int):
                    return value[key]
        return None

    def write_json(self, relative: str, value: Any) -> None:
        destination = self.raw_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent, delete=False
        ) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, destination)

    def capture(
        self,
        name: str,
        endpoint: str,
        relative: str | None = None,
        *,
        paginate: bool = False,
        optional: bool = False,
    ) -> Any | None:
        try:
            value = self.api(endpoint, paginate=paginate)
        except GitHubAPIError as exc:
            if not optional:
                raise
            self.unavailable.append(
                {"name": name, "endpoint": endpoint, "exit_code": exc.returncode}
            )
            return None
        self.write_json(relative or f"{name}.json", value)
        self.collections[name] = {
            "endpoint": endpoint,
            "count": self.count(value),
            "raw": f"archive/raw/github/{relative or f'{name}.json'}",
        }
        return value

    def capture_per_number(
        self,
        name: str,
        numbers: list[int],
        endpoint_template: str,
        *,
        paginate: bool = False,
        optional: bool = False,
    ) -> None:
        for number in numbers:
            endpoint = endpoint_template.format(number=number)
            try:
                value = self.api(endpoint, paginate=paginate)
            except GitHubAPIError as exc:
                if not optional:
                    raise
                self.unavailable.append(
                    {"name": f"{name}/{number}", "endpoint": endpoint, "exit_code": exc.returncode}
                )
                continue
            self.write_json(f"{name}/{number:04d}.json", value)

    def export(self) -> dict[str, Any]:
        repository = self.capture("repository", f"repos/{self.source}")
        assert isinstance(repository, dict)
        if repository.get("full_name") != self.source:
            raise RuntimeError(f"source identity mismatch: {repository.get('full_name')!r}")
        if repository.get("id") != self.expected_id:
            raise RuntimeError(
                f"repository ID mismatch: expected {self.expected_id}, got {repository.get('id')!r}"
            )
        if repository.get("private") is not True:
            raise RuntimeError("source repository is not private")

        default_branch = repository.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise RuntimeError("source repository has no default branch")
        default_ref = self.capture(
            "default-ref", f"repos/{self.source}/git/ref/heads/{quote(default_branch, safe='')}", optional=False
        )
        assert isinstance(default_ref, dict)
        default_sha = ((default_ref.get("object") or {}).get("sha"))
        if not isinstance(default_sha, str):
            raise RuntimeError("default branch response has no commit SHA")

        numbered = self.capture(
            "issues", f"repos/{self.source}/issues?state=all&per_page=100", paginate=True
        )
        pulls = self.capture(
            "pulls", f"repos/{self.source}/pulls?state=all&per_page=100", paginate=True
        )
        if not isinstance(numbered, list) or not isinstance(pulls, list):
            raise RuntimeError("numbered GitHub inventory was not a list")

        numbers = sorted(int(item["number"]) for item in numbered if "number" in item)
        if numbers != list(range(1, (max(numbers) if numbers else 0) + 1)):
            raise RuntimeError("source numbered inventory is not contiguous")
        pull_numbers = sorted(int(item["number"]) for item in pulls if "number" in item)
        issue_numbers = [number for number in numbers if number not in set(pull_numbers)]

        self.capture("issue-comments", f"repos/{self.source}/issues/comments?per_page=100", paginate=True)
        self.capture("pull-review-comments", f"repos/{self.source}/pulls/comments?per_page=100", paginate=True)
        self.capture("issue-events", f"repos/{self.source}/issues/events?per_page=100", paginate=True)

        self.capture_per_number(
            "issue-details", numbers, f"repos/{self.source}/issues/{{number}}"
        )
        self.capture_per_number(
            "issue-comments-by-number",
            numbers,
            f"repos/{self.source}/issues/{{number}}/comments?per_page=100",
            paginate=True,
            optional=True,
        )
        self.capture_per_number(
            "issue-events-by-number",
            numbers,
            f"repos/{self.source}/issues/{{number}}/events?per_page=100",
            paginate=True,
            optional=True,
        )
        self.capture_per_number(
            "pull-details", pull_numbers, f"repos/{self.source}/pulls/{{number}}"
        )
        self.capture_per_number(
            "pull-commits",
            pull_numbers,
            f"repos/{self.source}/pulls/{{number}}/commits?per_page=100",
            paginate=True,
        )
        self.capture_per_number(
            "pull-files",
            pull_numbers,
            f"repos/{self.source}/pulls/{{number}}/files?per_page=100",
            paginate=True,
        )
        self.capture_per_number(
            "pull-reviews",
            pull_numbers,
            f"repos/{self.source}/pulls/{{number}}/reviews?per_page=100",
            paginate=True,
        )
        self.capture_per_number(
            "pull-review-comments-by-number",
            pull_numbers,
            f"repos/{self.source}/pulls/{{number}}/comments?per_page=100",
            paginate=True,
        )

        self.capture("labels", f"repos/{self.source}/labels?per_page=100", paginate=True)
        self.capture(
            "milestones", f"repos/{self.source}/milestones?state=all&per_page=100", paginate=True
        )
        self.capture("branches", f"repos/{self.source}/branches?per_page=100", paginate=True)
        self.capture("tags", f"repos/{self.source}/tags?per_page=100", paginate=True)
        self.capture("releases", f"repos/{self.source}/releases?per_page=100", paginate=True)
        self.capture("topics", f"repos/{self.source}/topics", optional=True)
        self.capture("collaborators", f"repos/{self.source}/collaborators?affiliation=all&per_page=100", paginate=True, optional=True)
        self.capture("hooks", f"repos/{self.source}/hooks?per_page=100", paginate=True, optional=True)
        self.capture("deploy-keys", f"repos/{self.source}/keys?per_page=100", paginate=True, optional=True)
        self.capture("environments", f"repos/{self.source}/environments", optional=True)
        self.capture("pages", f"repos/{self.source}/pages", optional=True)
        self.capture("rulesets", f"repos/{self.source}/rulesets?includes_parents=true&per_page=100", paginate=True, optional=True)
        self.capture("actions-workflows", f"repos/{self.source}/actions/workflows?per_page=100", paginate=True, optional=True)
        self.capture("actions-runs", f"repos/{self.source}/actions/runs?per_page=100", paginate=True, optional=True)
        self.capture("actions-artifacts", f"repos/{self.source}/actions/artifacts?per_page=100", paginate=True, optional=True)
        self.capture("actions-variables", f"repos/{self.source}/actions/variables?per_page=100", paginate=True, optional=True)
        self.capture("actions-secrets", f"repos/{self.source}/actions/secrets?per_page=100", paginate=True, optional=True)

        manifest = {
            "status": "complete",
            "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": {
                "full_name": self.source,
                "database_id": repository["id"],
                "node_id": repository.get("node_id"),
                "private": repository.get("private"),
                "visibility": repository.get("visibility"),
                "default_branch": default_branch,
                "default_sha": default_sha,
                "updated_at": repository.get("updated_at"),
            },
            "numbered": {
                "max_number": max(numbers) if numbers else 0,
                "numbers": numbers,
                "issues": len(issue_numbers),
                "pull_requests": len(pull_numbers),
                "issue_numbers": issue_numbers,
                "pull_request_numbers": pull_numbers,
            },
            "collections": self.collections,
            "unavailable": self.unavailable,
            "secrets_policy": "actions-secrets contains names/metadata only; secret values were never requested",
        }
        destination = self.root / "state" / "source-manifest.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, destination)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", default="raychrisgdp/coding-agent-usage-dashboard")
    parser.add_argument("--expected-database-id", type=int, default=1249859353)
    parser.add_argument("--gh-command", default="gh", help="source-account gh executable")
    args = parser.parse_args()

    try:
        manifest = Exporter(args.root, args.source, args.expected_database_id, args.gh_command).export()
    except (GitHubAPIError, RuntimeError, OSError) as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": manifest["status"],
        "captured_at_utc": manifest["captured_at_utc"],
        "numbered": manifest["numbered"],
        "unavailable_count": len(manifest["unavailable"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
