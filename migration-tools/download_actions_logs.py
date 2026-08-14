#!/usr/bin/env python3
"""Download available source Actions run logs and record unavailable runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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
    args = parser.parse_args()

    raw = json.loads((args.root / "archive/raw/github/actions-runs.json").read_text(encoding="utf-8"))
    runs = raw[0]["workflow_runs"] if isinstance(raw, list) and raw and isinstance(raw[0], dict) else raw.get("workflow_runs", [])
    token = subprocess.check_output([args.source_gh, "auth", "token"], text=True).strip()
    archive_root = args.root / "archive" / "actions-logs"
    records = []
    for run in runs:
        run_id = run["id"]
        endpoint = f"https://api.github.com/repos/{args.source}/actions/runs/{run_id}/logs"
        destination = archive_root / f"{run_id}.zip"
        record = {
            "run_id": run_id,
            "run_number": run.get("run_number"),
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "head_sha": run.get("head_sha"),
            "head_branch": run.get("head_branch"),
            "source_endpoint": endpoint,
            "path": str(destination.relative_to(args.root)),
        }
        request = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "private-mirror-migration",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                content = response.read()
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                record.update({
                    "result": "downloaded",
                    "http_status": response.status,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                })
        except urllib.error.HTTPError as exc:
            record.update({"result": "unavailable", "http_status": exc.code, "reason": str(exc.reason)})
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record.update({"result": "unavailable", "reason": type(exc).__name__})
        records.append(record)

    state = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": args.source,
        "run_count": len(runs),
        "downloaded": sum(record["result"] == "downloaded" for record in records),
        "unavailable": sum(record["result"] == "unavailable" for record in records),
        "records": records,
    }
    write_json(args.root / "state/actions-logs.json", state)
    checksum_path = args.root / "archive/actions-logs.sha256"
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(
        "\n".join(f"{record['sha256']}  {record['path']}" for record in records if record["result"] == "downloaded")
        + ("\n" if state["downloaded"] else ""),
        encoding="utf-8",
    )
    print(json.dumps({key: state[key] for key in ("run_count", "downloaded", "unavailable")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
