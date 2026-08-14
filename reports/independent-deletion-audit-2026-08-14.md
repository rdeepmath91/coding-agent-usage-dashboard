# Independent source-deletion audit

- Audited at: `2026-08-14T21:07:08+07:00`
- Source: `raychrisgdp/coding-agent-usage-dashboard`
- Destination: `rdeepmath91/coding-agent-usage-dashboard`
- Audit mode: read-only against both GitHub accounts, except for a temporary clean clone and local report creation
- Deletion performed: **no**

## Verdict

**BLOCKED — do not delete the source repository yet.**

The Git repository and most GitHub issue metadata are mirrored correctly, but the destination still contains source-dependent links and several recoverable records have not been archived. Deleting the source now would cause known link breakage and avoidable loss.

## Independently verified passes

### Repository identity and privacy

- Source API identity: `raychrisgdp`.
- Destination API identity: `rdeepmath91`.
- Source remains private and resolves under `raychrisgdp`.
- Destination is private and the personal account has admin permission.
- Source credentials cannot read the destination.
- Destination has one collaborator, its personal owner.

### Git and local refs

- Source `main`: `4bc75fa4e206cffd5e20a969824bc47a042c3bc1`.
- Destination `main`: the same SHA.
- All nine source user refs exist at the same SHA in the destination.
- Destination has 23 user refs: the nine source refs plus 14 intentional archive/local-only refs.
- All 15 local branch heads are represented by exact-SHA destination refs. The colliding local `fix/deepseek-provider-pricing` head is retained as `archive/local/fix/deepseek-provider-pricing`.
- Destination clone passed `git fsck --full --strict` with no output.
- No source or destination tags or Git notes exist.
- No Git LFS-tracked files or LFS attributes exist.
- Source and destination wikis do not exist.
- No releases exist.

### Numbered GitHub objects

- Source sequence: 54 objects, comprising 36 issues and 18 pull requests.
- Destination sequence: all numbers 1 through 54.
- Destination representation: 36 native issues, 17 archived-PR issues, and native open PR #53.
- Every title and reconstructed body matches the live source-derived expected representation.
- Labels and label metadata match; `archived-pr` is the only intentional extra label.
- Open/closed state matches.
- All nine source issue comments are present with exact attributed reconstructed bodies.
- Source has no PR reviews, PR review comments, milestones, or reactions, so none are missing.
- All 15 native parent/sub-issue relationships match.
- PR #53 matches source title, state, draft status, base/head refs and SHAs, commit count, changed-file count, additions, and deletions.

Known non-blocking representation difference: the 17 archived-PR issues have GitHub issue `state_reason=completed`; the historical source PRs expose no corresponding issue state reason.

### Archive integrity

- `migration-archive` local and remote head: `84c8b596fb639523ed7c4f0a133b2fe323ae9452`.
- The archive worktree is clean.
- All 275 entries in `archive/raw.sha256` verify.
- `archive/source-current.bundle` verifies as a Git bundle.
- The earlier recovery archive has 31 checksum entries and all verify.
- Its `repository-all-local-refs.bundle` also verifies.
- Required per-object raw issue, comment, pull-detail, commit, file, review, and review-comment JSON files are present.
- Current live counts still match the captured archive: 54 objects, 18 PRs, nine issue comments, 109 issue events, and zero review comments.
- No GitHub user-upload attachment URLs were found. Repository-hosted images are in mirrored Git history.

### Local cutover and execution

- All ten local worktrees now expose only the personal SSH destination URL.
- Nine worktrees are clean. The canonical worktree has one local untracked `.hermes/` directory containing the migration plan; no tracked changes are present.
- A new clean clone from the personal destination started at the expected `main` SHA.
- Fresh independent test result: `Ran 62 tests in 2.044s` and `OK`.
- No tracked changes were produced by the test run.

## Deletion blockers

### 1. Historical PR Git objects are missing from the destination and recovery bundles

An independent object-level audit compared 109 unique source PR-related commit SHAs across pull heads, pull commit lists, and merge SHAs against the destination and both recovery bundles.

- PR #6: three historical head/commit SHAs are missing.
- PR #14: twelve historical head/commit SHAs are missing.
- PR #53: the source-generated synthetic test-merge SHA `ddb94c02e5d7266a10300f6f059e4f67dcb7c1b9` is missing. The destination has its own different synthetic merge commit, which is expected for a recreated PR, but the source-specific merge object is not archived.

The 15 real historical commits from PRs #6 and #14 are currently available through the source's hidden `refs/pull/*/head` namespace but are not reachable from destination branches, `source-current.bundle`, or `repository-all-local-refs.bundle`. Deleting the source now could permanently lose those Git objects.

Required remediation:

1. Fetch every source `refs/pull/*/head` and available `refs/pull/*/merge` into explicit local archival refs.
2. Push durable private archive refs for missing PR heads, or create and upload a new self-contained bundle that includes the hidden pull refs.
3. Verify every SHA listed by the raw `pull-commits` and `pull-details` records with `git cat-file -e <sha>^{commit}` against both the destination and the new recovery bundle.
4. Record the source and destination synthetic PR #53 merge SHAs as intentionally different.

### 2. Destination records still depend on the source URL

Live destination issue/PR bodies and comments contain:

- 34 source PR patch/diff URLs, covering the 17 archived PRs.
- 27 additional rewritable source-repository URLs in objects #9, #34, #52, #53, and #54.
- These additional links target issue cross-references, prototype HTML, screenshots, SVGs, and repository-hosted images.

The archive currently contains zero `.patch` files and zero `.diff` files. Deleting the source would break all 34 historical PR patch/diff URLs and the 27 internal links until they are rewritten.

Required remediation:

1. Download and hash every historical PR `.patch` and `.diff` while the source exists.
2. Commit those files to the private `migration-archive` branch.
3. Replace destination-internal source URLs with personal-destination URLs.
4. Replace archived PR patch/diff URLs with durable links or precise archive paths in the personal repository.
5. Recheck every rewritten target while authenticated as `rdeepmath91`.

### 3. Source-dependent links remain in tracked project documentation

Tracked `main` files still contain source URLs:

- `PR22_REMAINING_SCOPE.md`
- `PR22_BEFORE_AFTER.md`

These include source issue and source PR links. Historical PR #22 is represented at destination issue #22, not destination PR #22, so blind owner substitution is insufficient.

Required remediation: create a documented destination-only cleanup commit that points those records to their correct destination representations, while retaining the exact source `main` commit in history and in the recovery bundle.

### 4. GitHub Actions logs and current PR check state are not preserved

- Source Actions runs: 89.
- Destination Actions runs: 0.
- Raw archive: metadata for all 89 source runs.
- Archived workflow log bundles: 0.
- Source PR #53 head check runs: one successful `test` check.
- Destination PR #53 head check runs: zero.

GitHub Actions history cannot be recreated natively, but available logs can still be downloaded before deletion.

Required remediation:

1. Download all still-available run logs and hash them into the migration archive.
2. Record any expired/unavailable log IDs explicitly.
3. Trigger destination CI for native PR #53 without changing its code diff, then verify the destination head has a successful `test` check.

### 5. Nine original assignee records are not visible in destination objects

Original assignee `raychrisgdp` was omitted from objects #2, #6, #14, #19, #21, #26, #27, #37, and #48. The data exists only in raw JSON and `object-map.json`; destination bodies do not state the original assignee.

Required remediation: add visible `Original assignees` attribution to those reconstructed records, or explicitly map the assignments to `rdeepmath91` while retaining the original identity in the attribution block.

### 6. Bundle checksum manifest is not portable

`archive/source-current.sha256` contains absolute paths under:

`/home/raymond-christopher/migrations/coding-agent-usage-dashboard-mirror/archive/`

The hashes are currently valid on this machine, but a fresh clone of `migration-archive` cannot run the manifest self-contained.

Required remediation: rewrite this checksum manifest with paths relative to the archive branch root, push it, clone the branch into a new directory, and verify both the checksum manifest and bundle there.

## Additional local cleanup before final cutover

These are not source-deletion data-loss blockers, but they should be normalized before declaring the migration finished:

- The primary checkout's cached `origin/migration-archive` ref is `023efb211a06e7d489846ffa6185c5953db17686`, while the live branch and dedicated archive worktree are correctly at `84c8b596fb639523ed7c4f0a133b2fe323ae9452`. Fetch/prune the primary checkout after archive remediation.
- `test-update-button-doc-note` exists at the correct destination SHA but tracks `origin/main`; set its upstream to its same-named personal branch to avoid surprising pulls.
- The primary checkout has two dangling commits. One is the PR #6 head now identified as a deletion blocker; protect it with an archival ref before Git maintenance can prune it.

## Inherent limitations requiring explicit acceptance

Even after the blockers are repaired, deletion cannot make the destination a perfect GitHub-native clone. The accepted representation must remain explicit:

- Historical merged/closed PRs are archived issues, not native PRs.
- Original database IDs, object URLs, creation/update timestamps, actors, subscriptions, notification state, merge actors, and native event timelines cannot be recreated.
- Original source URLs retained as historical attribution will return 404 after deletion.
- GitHub Actions history cannot be transplanted natively; only metadata and downloaded logs can be archived.
- GitHub internal audit records, notifications, caches, third-party clones, and the public `RaihanParl/coding-agent-usage-dashboard` fork remain outside this migration's control.

## Final deletion gate

After remediation, rerun a fresh independent reconciliation and require a new explicit deletion instruction that names `raychrisgdp/coding-agent-usage-dashboard`. Until then, the source must remain private and undeleted.
