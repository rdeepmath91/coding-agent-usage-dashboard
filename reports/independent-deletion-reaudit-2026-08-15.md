# Independent deletion re-audit — 2026-08-15

- Audited at: `2026-08-15T07:49:20+07:00`
- Source: `raychrisgdp/coding-agent-usage-dashboard`
- Destination: `rdeepmath91/coding-agent-usage-dashboard`
- Mode: read-only against both GitHub repositories; temporary local clones only
- Source deletion or mutation: **none**

## Verdict

**BLOCKED pending recovery-package and final-report cleanup.**

The previously missing source data is now preserved. No historical PR commit, live numbered object, operational link target, Actions log, assignee attribution, or tested source branch content was found missing from the destination/remediation archive.

The current deletion gate is still not reliable enough to authorize deletion because it contains stale Git claims, presents an incomplete pre-remediation tarball without qualification, and leaves an old machine-specific checksum manifest active. A redundant local remote-tracking namespace is also stale.

## Substantive preservation checks that pass

### Git and PR history

- Source `main`: `4bc75fa4e206cffd5e20a969824bc47a042c3bc1`.
- Destination `main`: `0c643299dff197f1e7a0f98cc6a9f15a229daa4a` after two intentional destination-only commits.
- `archive/source-baseline/main` preserves the exact source `main` SHA.
- All nine source branch names exist at the destination. Eight have the same SHA; `main` intentionally differs as above.
- All 19 live source `refs/pull/*` refs match ordinary destination `archive/source-pull/*` branches by exact SHA.
- All 110 unique PR-related commit/merge SHAs are present in:
  - a fresh destination mirror; and
  - `archive/source-with-pull-refs.bundle`.
- `git bundle verify` passes for the replacement bundle.
- Fresh destination-mirror `git fsck --full --strict` passes with no output.
- The source PR #53 synthetic merge commit `ddb94c02e5d7266a10300f6f059e4f67dcb7c1b9` is preserved.
- All 34 generated historical PR artifacts reproduce byte-for-byte from their recorded base/head objects:
  - 17 `.patch` files;
  - 17 `.diff` files;
  - 34/34 artifact checksums pass.

### GitHub records and links

- Source and destination each expose objects #1–#54 with no missing or extra number.
- Titles and open/closed states match for all 54 objects.
- Destination representation remains intentional: 36 issues, 17 attributed archived-PR issues, and native open PR #53.
- Source and destination each expose nine reconstructed issue comments.
- All nine original `raychrisgdp` assignee records are visible in destination attribution headers.
- The native parent/sub-issue graph matches exactly across all 15 relationships.
- Source labels are preserved with matching metadata; `archived-pr` is the only intentional destination-only label.
- A live scan found 63 remaining source-repository URL occurrences in destination bodies/comments, all confined to immutable `Original URL:` attribution lines.
- No rewritable operational source URL remains.
- All 54 destinations in `state/link-map.json` resolve with personal-account authentication.
- Destination `main` has zero tracked `raychrisgdp/coding-agent-usage-dashboard` literals and zero tracked `/home/raymond-christopher` literals.
- No source user-upload attachment URLs were found.
- No source/destination releases, tags, notes, Actions artifacts, wiki history, LFS attributes, deploy keys, hooks, Actions secrets, Actions variables, or environments require migration.
- Repository merge/settings and Actions permission settings match on the checked surfaces.
- No source or destination issue/PR has a GitHub ProjectV2 membership.

### Actions evidence

- Live source runs: 89.
- Raw archived run records: 89.
- Downloaded log ZIPs: 89.
- Run-ID sets match exactly; zero unavailable logs.
- All 89 ZIP hashes pass; every ZIP opens, has entries, and passes CRC validation.
- Source PR #53 head has the original successful `test` check.
- Destination PR #53 head has no check, as explicitly accepted by the owner.
- Destination workflow-dispatch run `31810963075` failed before any runner or step started; job `94801219949` has `runner_id: 0`, empty runner name, and no steps.
- Destination currently has zero registered self-hosted runners.

### Fresh recovery/execution checks

- Fresh `migration-archive` clone at `a2342bf8e5e31c7747dcf35e7d1f312687888d88` verifies:
  - 275/275 raw archive checksums;
  - 34/34 PR artifact checksums;
  - 89/89 Actions log checksums;
  - 4/4 replacement-bundle manifest entries.
- Fresh destination `main` clone at `0c643299dff197f1e7a0f98cc6a9f15a229daa4a` passes:
  - `git fsck --full --strict`;
  - all 62 unit tests;
  - Python compilation checks;
  - clean post-test status.
- All ten worktrees use `git@github.com-rdeepmath91:rdeepmath91/coding-agent-usage-dashboard.git` through `origin`.
- `test-update-button-doc-note` now tracks its same-named destination branch.
- All 41 local branch heads are represented by an exact-SHA destination branch.
- Anonymous API access to both private repositories returns 404.
- Source credentials cannot read the destination; personal credentials cannot read the source.

## Remaining blockers and discrepancies

### 1. The live `migration-archive` branch is behind the canonical remediation state

The live branch is clean at `a2342bf8e5e31c7747dcf35e7d1f312687888d88`, but it does not contain all canonical migration-root updates:

- `state/import-checkpoints.jsonl` has 99 records on the live branch versus 114 in the canonical root. The omitted 15 records are the native parent/sub-issue mutation receipts.
- The live-branch copies of `reports/deletion-gate.md`, `reports/independent-deletion-audit-2026-08-14.md`, and `reports/remediation-status-2026-08-14.md` differ from the canonical-root copies.
- The live-branch reports do not include the owner’s accepted PR #53 CI exception and retain older deletion-gate language.
- The canonical migration root contains the raw export tree but lacks its colocated `archive/raw.sha256`; the live branch has the valid 275-entry manifest.

The destination’s native hierarchy is correct, so this is missing recovery evidence rather than missing GitHub relationships. Required before deletion: reconcile the canonical root and live archive branch so the branch contains the complete checkpoint log, accepted exception, current reports, and all canonical checksum manifests.

### 2. The only packaged recovery tarball is pre-remediation and incomplete

`/home/raymond-christopher/migration-backups/coding-agent-usage-dashboard-20260814T101757Z.tar.gz` is still the only matching packaged `.tar.gz` backup found.

Its `repository-all-local-refs.bundle` is structurally valid but misses 16 of the 110 current PR-related SHAs: the 15 real PR #6/#14 commits previously identified plus the source PR #53 synthetic merge commit.

`reports/deletion-gate.md` cites this tarball and its SHA-256 without saying that it is a pre-remediation snapshot and is not sufficient by itself for full recovery.

Required before deletion: create and verify a new post-remediation recovery package or full mirror bundle containing the current destination refs, `migration-archive`, the replacement pull-ref bundle, raw metadata, patches/diffs, Actions logs, state maps, and reports. Mark the old tarball explicitly as superseded/incomplete for PR-object recovery.

### 3. `archive/source-current.sha256` remains machine-specific

The live `migration-archive` still contains three absolute paths under:

`/home/raymond-christopher/migrations/coding-agent-usage-dashboard-mirror/archive/`

The manifest appears to pass on this machine even from a fresh clone only because those original absolute files still exist elsewhere on the same host. It is not self-contained.

The associated `archive/source-current.bundle` also misses the same 16 PR-related SHAs. The replacement `archive/source-with-pull-refs.bundle` is complete and has a portable relative manifest, but the old files are not marked as superseded.

Required before deletion: either rewrite `source-current.sha256` to archive-relative paths and replace its bundle with the complete one, or clearly retire/rename both old artifacts as superseded and make the replacement bundle the sole canonical recovery bundle.

### 4. `reports/deletion-gate.md` contains stale Git statements

The report says destination `main` is `4bc75fa4...` and that source/destination live branch SHAs reconcile. Live destination `main` is `0c643299...`; only `archive/source-baseline/main` remains at `4bc75fa4...`.

Required before deletion: update the final gate to state the intentional destination-only divergence and identify the baseline ref and replacement bundle as preservation evidence.

### 5. PR #53 has no standalone archived patch/diff

The archive has 17 historical PR patch/diff pairs but no `archive/pr-artifacts/0053.patch` or `0053.diff`. Live source and destination PR #53 currently produce matching artifacts:

- patch SHA-256: `43dd5168cee7de9aef064c1024121b251c26e5b23de3e09f527ade6c38349266`
- diff SHA-256: `80d6e28c3c106793d40097613866c11a222f5cad56eeb4bf4745395de05a0927`

Native destination PR #53 currently supplies these views, but the requested durable PR-evidence archive is incomplete without standalone copies. Archive and hash both before the source is deleted.

### 6. PR #53 base-state divergence needs explicit documentation

The source PR records base SHA `4bc75fa4...`. Destination PR #53 still has the same head SHA and matching core diff metrics, but its API currently records base SHA `940396080b6ea49a3de2615444acad1615044c8a`, while live destination `main` has advanced again to `0c643299...`. The PR reports `mergeable: true` and `mergeable_state: clean`.

This is expected fallout from the destination-only documentation and CI-trigger commits, not lost code. It should be recorded so the final report does not continue claiming exact base-SHA parity.

### 7. Secondary local verification/tracking state is stale

The canonical worktrees use the exact `origin/*` namespace, which has all 50 live destination refs at matching SHAs. The duplicate `destination/*` namespace has only 30 refs, is missing 20 newer refs including `migration-archive` and all 19 pull-preservation branches, and has a stale `main` SHA.

The named local verification mirrors `fresh-archive-verify` and `fresh-final-destination.git` also retain `migration-archive` at `ce57c94c4c3633ba102d91bbb545004b88915421`, one commit behind the live branch. This re-audit used separate fresh `/tmp` clones at the live tips, so the new test evidence is sound.

These are not source-deletion data-loss blockers, but they contradict broad claims that all local refs and named verification clones were refreshed. Refresh or remove the redundant namespace and regenerate the named verification clones before calling local cutover fully normalized.

## Accepted and inherent limitations

- Destination PR #53 has no native successful GitHub check; owner acceptance is recorded.
- Historical PRs other than #53 are attributed archive issues, not native PRs.
- Original GitHub database IDs, native URLs, timestamps, actors, merge actors, subscriptions, notifications, reactions, and full native timelines cannot be recreated.
- Historical Actions runs cannot be transplanted natively; metadata and logs are archived instead.
- Original source URLs retained only as historical attribution will return 404 after source deletion.
- Third-party forks, clones, GitHub audit/support records, caches, notifications, and external indexes cannot be erased.

## Final gate

Do **not** delete `raychrisgdp/coding-agent-usage-dashboard` from the current reports.

After the seven discrepancies above are resolved, rerun the portable package verification from a neutral extraction/clone, correct the final deletion-gate report, and obtain a new explicit deletion instruction naming `raychrisgdp/coding-agent-usage-dashboard`.
