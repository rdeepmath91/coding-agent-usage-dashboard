#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

BASE_REF=${1:-origin/main}
MODE=${REVIEW_MODE:-full}

printf '==> Reviewing against %s\n' "$BASE_REF"
git diff --stat "$BASE_REF"...HEAD
printf '\n'
git diff --check "$BASE_REF"...HEAD

if [[ "$MODE" == "docs" ]]; then
  printf '\n==> Docs-only review mode complete\n'
  exit 0
fi

printf '\n==> Running tests\n'
uv run python -m unittest tests.test_app tests.test_readme -v

printf '\n==> Compiling Python files\n'
uv run python -m py_compile app.py scripts/snapshot_dashboard.py

printf '\n==> Full review mode complete\n'
