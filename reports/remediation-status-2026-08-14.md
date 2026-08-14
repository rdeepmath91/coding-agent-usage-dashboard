# Remediation status

Updated: 2026-08-14

## Completed and verified

- Hidden source pull refs: 19 fetched and pushed as ordinary private `archive/source-pull/*` branches.
- PR-related Git objects: 110 unique base/head/commit/merge SHAs verified in the replacement bundle and a fresh destination mirror; 0 missing.
- PR artifacts: 34 Git-derived patch/diff fallbacks created because the authenticated GitHub web endpoints returned HTTP 404; every 404 is recorded in `state/pr-artifacts.json`, and all fallback files are hashed.
- Operational links: 61 occurrences across 54 unique URLs rewritten in destination records; 0 unresolved refs.
- Immutable raw exports and historical `Original URL` attribution were not rewritten.
- Tracked documentation: four source links in the two PR #22 records now point to the destination archived issue representation.
- Assignees: all nine omitted `raychrisgdp` assignments are visible in reconstructed attribution headers.
- Actions logs: all 89 source run log bundles downloaded and hashed; no source log was unavailable.
- Checksum portability: fresh archive clone verified 275 raw entries, 34 PR artifacts, 89 Actions logs, and the replacement bundle using relative paths.
- Local refs: stale tracking refs refreshed; `test-update-button-doc-note` now tracks its same-named destination branch; seven dangling local commits are protected under `archive/local-dangling/`.
- Fresh destination mirror: `git fsck --full --strict` passed, all 110 PR-related SHAs are present, and a fresh destination `main` clone passed all 62 tests.

## Destination-only changes

- `archive/source-baseline/main` preserves the original source `main` SHA
  `4bc75fa4e206cffd5e20a969824bc47a042c3bc1`.
- Destination `main` includes the link cleanup and the CI dispatch trigger;
  current SHA is `0c643299dff197f1e7a0f98cc6a9f15a229daa4a`.

## Remaining blocker

Destination PR #53 still has no successful GitHub check on its unchanged head
`edd02b199a9b1c7c2b64e7233bb52b6b872af64c`:

1. The required close/reopen operation completed and preserved the head SHA,
   but produced no check run after 360 seconds.
2. A destination `workflow_dispatch` trigger was added to `main`; dispatching
   against the unchanged PR head returns HTTP 422 because that head’s workflow
   file does not contain the new trigger.
3. Dispatching the workflow on destination `main` created run `31810963075`,
   which failed before any steps and has no available job log.

The PR head was not changed merely to force a check. Local tests and fresh-clone
tests pass, but the destination GitHub CI requirement remains unresolved.

## Deletion gate

The source remains private and undeleted. Do not delete
`raychrisgdp/coding-agent-usage-dashboard` until the PR #53 CI blocker is
resolved or explicitly accepted in a fresh independent audit, followed by a
new explicit deletion instruction naming the source repository.
