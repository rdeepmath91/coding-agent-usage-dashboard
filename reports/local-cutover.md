# Local cutover

Completed: 2026-08-14

## Remote routing

- Previous shared `origin`: `git@github.com:raychrisgdp/coding-agent-usage-dashboard.git`
- Current shared `origin`: `git@github.com-rdeepmath91:rdeepmath91/coding-agent-usage-dashboard.git`
- Personal SSH authentication was verified as `rdeepmath91`.
- The source URL remains documented here but is no longer an active remote.
- The explicit `destination` remote remains pointed at the same personal SSH URL.

## Worktree preservation

All ten registered worktree HEADs were unchanged during cutover:

| Worktree branch | HEAD | Upstream after cutover |
|---|---|---|
| `main` | `4bc75fa4e206cffd5e20a969824bc47a042c3bc1` | `origin/main` |
| `fix/codex-preview-column` | `bcfdb579d8fc8d1f8c58b3f45422b91a31cb0dcd` | `origin/fix/codex-preview-column` |
| `fix/deepseek-provider-pricing` | `4bc75fa4e206cffd5e20a969824bc47a042c3bc1` | `origin/archive/local/fix/deepseek-provider-pricing` |
| `issue-16-pricing-alias-registry` | `4beef110d306dd981a13d6280d1e42e1c6d6d155` | `origin/issue-16-pricing-alias-registry` |
| `issue-20-overview-token-cards` | `38284d577e7ec6d767561fda2fb680b0faf4f7af` | `origin/issue-20-overview-token-cards` |
| `issue-24-performance` | `d35fe1b3fbc395357070f2af5608a2b621bcfb41` | `origin/issue-24-performance` |
| `issue-25-readme-screenshot` | `7d5de34a1751f5f2b3f9d6dd2352e37ca5ada052` | `origin/issue-25-readme-screenshot` |
| `issue-34-update-app` | `0dbefdd9ab9604ea8836c8bdf48d0015c2985a20` | `origin/issue-34-update-app` |
| `test-update-button-doc-note` | `7129fe8fa6eecbccabe30556f5dffcc61105aaa6` | `origin/main` |
| `design/usage-explorer-prototype` | `edd02b199a9b1c7c2b64e7233bb52b6b872af64c` | `origin/design/usage-explorer-prototype` |

The main worktree retains untracked `.hermes/` migration-plan content. It was
not deleted, stashed, or included in the product `main` push. All other
registered worktrees were clean at cutover.

## Verification

- Post-cutover source branch count: 9; all source branch SHAs match destination.
- Destination remains private and personal-admin accessible.
- Anonymous destination access remains HTTP 404.
- Clean destination clone test suite: 62 tests, all passed.
- Current main worktree test suite: 62 tests, all passed.
