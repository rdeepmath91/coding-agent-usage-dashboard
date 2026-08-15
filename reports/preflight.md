# Preflight — coding-agent-usage-dashboard private mirror (historical baseline)

Captured: 2026-08-14

This document records the pre-migration baseline. It is retained for audit
history; the current canonical recovery evidence is documented in the deletion
gate and uses `archive/source-with-pull-refs.bundle` plus the post-remediation
package, not the original preflight tarball.

## Current live source

- Repository: `raychrisgdp/coding-agent-usage-dashboard`
- Database ID: `1249859353`
- GraphQL node ID: `R_kgDOSn9XGQ`
- Visibility: private
- Default branch: `main`
- Live `refs/heads/main`: `4bc75fa4e206cffd5e20a969824bc47a042c3bc1`
- Numbered inventory: 54 objects, consisting of 36 issues and 18 pull requests
- Maximum source number: 54; no gap was observed in the REST inventory
- Destination `rdeepmath91/coding-agent-usage-dashboard`: absent (GitHub API repository lookup returned 404)

## Local recovery archive

- Path: `/home/raymond-christopher/migration-backups/coding-agent-usage-dashboard-20260814T101757Z.tar.gz`
- SHA-256: `d67e06864fffd7374317451821c55483cb6bf85826eeceb410372eff6e2a1103`
- Gzip and tar listing checks: passed
- Archived bundle verification: the pre-remediation baseline bundle reports a complete history and 41 refs; it is not the canonical recovery bundle
- Archived worktrees: 10

## Fresh local Git capture

- Bundle: `archive/source-with-pull-refs.bundle` (canonical; includes hidden pull refs)
- Bundle verification: passed; complete history, 57 bundle refs
- Ref snapshot: `archive/source-pull-refs.txt` (19 preserved hidden pull refs)
- Bundle SHA-256: `86c26247ad1653420531c1fe1246097a01ccdfd251afffa80932fa914d210e27`
- Git LFS: unavailable and no `.gitattributes` LFS rules were found
- Local wiki checkout: absent; wiki availability still requires GitHub API/UI verification

The archive was captured at `2026-08-14T10:17:57Z`. Its metadata reports the
source as public, whereas the live source is private. It is therefore a
recovery baseline only and must not be treated as the refreshed source
manifest. The refresh must explain this visibility and timestamp delta.

## Transfer and mutation gate

- REST transfer lookup: `404`; this endpoint does not establish that the
  pending UI transfer request is absent.
- Authenticated CLI identity: `raychrisgdp`.
- Browser Settings access: unavailable; the browser session is unauthenticated
  and GitHub returns a 404 page.
- No transfer cancellation was attempted.
- No destination repository was created.
- No GitHub metadata, source repository, or local remote was modified.

The plan requires an authenticated source-account browser session to verify and
cancel the pending transfer before destination creation. This report is
intentionally a preflight record, not a cancellation receipt or migration
approval.
