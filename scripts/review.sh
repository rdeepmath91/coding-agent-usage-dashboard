#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

BASE_REF=${1:-origin/main}
MODE=${REVIEW_MODE:-full}

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" == "main" && "$MODE" != "docs" ]]; then
  printf '\033[31merror:\033[0m scripts/review.sh must run from a feature branch, not main.\n' >&2
  printf 'Create a worktree and rerun from there:\n' >&2
  printf '  git worktree add ../worktrees/<branch-slug> -b <branch> origin/main\n' >&2
  printf 'For docs-only or AGENTS.md-only edits, set REVIEW_MODE=docs.\n' >&2
  exit 1
fi

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
