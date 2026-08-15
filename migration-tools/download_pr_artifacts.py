#!/usr/bin/env python3
"""Download historical GitHub PR patch/diff artifacts without changing raw exports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", default="raychrisgdp/coding-agent-usage-dashboard")
    parser.add_argument("--source-gh", default="gh")
    parser.add_argument(
        "--include-pr53",
        action="store_true",
        help="also archive native PR #53 through the GitHub API media-type endpoint",
    )
    parser.add_argument(
        "--git-dir",
        type=Path,
        default=None,
        help="bare Git archive containing source base/head objects",
    )
    args = parser.parse_args()

    raw = args.root / "archive" / "raw" / "github"
    manifest = json.loads((args.root / "state" / "source-manifest.json").read_text(encoding="utf-8"))
    pr_numbers = [int(number) for number in manifest["numbered"]["pull_request_numbers"] if int(number) != 53]
    if args.include_pr53:
        pr_numbers.append(53)
    token = subprocess.check_output([args.source_gh, "auth", "token"], text=True).strip()
    git_dir = args.git_dir or args.root / "archive" / "source-pull-archive.git"
    artifact_root = args.root / "archive" / "pr-artifacts"
    records = []
    for number in pr_numbers:
        detail = json.loads((raw / "pull-details" / f"{number:04d}.json").read_text(encoding="utf-8"))
        for suffix in ("patch", "diff"):
            url = f"https://github.com/{args.source}/pull/{number}.{suffix}"
            retrieval_url = url
            accept = "application/vnd.github+json"
            if number == 53:
                retrieval_url = f"https://api.github.com/repos/{args.source}/pulls/{number}"
                accept = f"application/vnd.github.{suffix}"
            destination = artifact_root / f"{number:04d}.{suffix}"
            record = {
                "source_number": number,
                "kind": suffix,
                "source_url": url,
                "source_api_url": detail.get(f"{suffix}_url"),
                "retrieval_url": retrieval_url,
                "path": str(destination.relative_to(args.root)),
            }
            request = urllib.request.Request(
                retrieval_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": accept,
                    "User-Agent": "private-mirror-migration",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    content = response.read()
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    record.update(
                        {
                            "status": "downloaded",
                            "http_status": response.status,
                            "content_type": response.headers.get_content_type(),
                            "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    )
            except urllib.error.HTTPError as exc:
                record.update({"status": "web_unavailable", "http_status": exc.code, "reason": str(exc.reason)})
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                record.update({"status": "web_unavailable", "reason": type(exc).__name__})
            if record["status"] == "web_unavailable":
                base_sha = (detail.get("base") or {}).get("sha")
                head_sha = (detail.get("head") or {}).get("sha")
                if not base_sha or not head_sha:
                    record["status"] = "unavailable"
                    record["fallback_reason"] = "source PR has no base/head SHA"
                else:
                    git_command = ["git", "--git-dir", str(git_dir)]
                    if suffix == "diff":
                        git_command.extend(["diff", "--binary", "--full-index", f"{base_sha}..{head_sha}"])
                    else:
                        git_command.extend(["format-patch", "--stdout", "--binary", f"{base_sha}..{head_sha}"])
                    generated = subprocess.run(
                        git_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    if generated.returncode != 0:
                        record["status"] = "unavailable"
                        record["fallback_reason"] = "Git-derived fallback generation failed"
                    else:
                        content = generated.stdout
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(content)
                        record.update(
                            {
                                "status": "generated_fallback",
                                "fallback_reason": "GitHub web artifact endpoint unavailable; generated from verified source base/head objects",
                                "bytes": len(content),
                                "sha256": hashlib.sha256(content).hexdigest(),
                                "base_sha": base_sha,
                                "head_sha": head_sha,
                            }
                        )
            records.append(record)

    state = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": args.source,
        "records": records,
        "web_downloaded": sum(record["status"] == "downloaded" for record in records),
        "generated_fallback": sum(record["status"] == "generated_fallback" for record in records),
        "unavailable": sum(record["status"] == "unavailable" for record in records),
    }
    write_json(args.root / "state" / "pr-artifacts.json", state)
    checksum_path = args.root / "archive" / "pr-artifacts.sha256"
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{record['sha256']}  {record['path']}"
        for record in records
        if record["status"] in {"downloaded", "generated_fallback"}
    ]
    checksum_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(json.dumps({"web_downloaded": state["web_downloaded"], "generated_fallback": state["generated_fallback"], "unavailable": state["unavailable"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"PR artifact download failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
