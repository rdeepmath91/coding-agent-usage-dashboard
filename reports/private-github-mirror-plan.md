# Private GitHub Mirror and Metadata Reconstruction Plan

> **For Hermes:** Execute this plan only after Raymond reviews and approves it. Use isolated scripts, checkpoint files, and read-back verification for every external mutation.

**Goal:** Reproduce `raychrisgdp/coding-agent-usage-dashboard` as a new private `rdeepmath91/coding-agent-usage-dashboard` repository without using GitHub repository transfer, preserve all code and as much GitHub-hosted history as ordinary APIs allow, and delete nothing from the source until a final reconciliation report is accepted.

**Architecture:** Use two parallel fidelity tracks. The Git track creates an exact object/ref mirror and separately preserves local-only work. The GitHub metadata track first creates an immutable source archive, then deterministically reconstructs the repository's issue-number sequence, labels, milestones, discussions, attachments, releases, and relationships in the private destination. Closed and merged PRs become clearly attributed archived-PR issues at their original sequence positions; the currently open PR may be recreated as a native PR if its head/base commits permit it. Raw source records and unavailable native fields remain in a dedicated private archive branch.

**Tech Stack:** Git and Git bundles; Git LFS if detected; GitHub REST and GraphQL APIs through account-isolated `gh` wrappers; Python 3 migration scripts; JSON/JSONL manifests; SHA-256 reconciliation; GitHub CLI; Playwright/browser only for the transfer-cancellation UI if GitHub exposes no API.

---

## Feasibility and fidelity contract

### Can be preserved exactly

- Commit objects and commit authorship.
- Branch and tag tips that GitHub accepts.
- Current file contents and executable history.
- Git notes and normal refs where the destination permits them.
- Local-only branch heads, once explicitly named and pushed to the private destination.
- Raw exported GitHub API records in the private migration archive.

### Can be reconstructed with visible attribution

- Labels and milestones.
- Issues, issue state, assignees where eligible, comments, and most body content.
- Native parent/sub-issue relationships and blockers where the personal destination supports them.
- Releases, release notes, tags, and downloadable assets.
- Wiki history and content.
- Attachments that can be downloaded from their current URLs.
- The currently open PR, if its source/base refs can form a valid native destination PR.

Every reconstructed body/comment must carry an attribution header with the original repository, object type and number, author, creation/update timestamp, state, and source URL. The private archive must retain the unmodified API payload even if a field cannot be reproduced natively.

### Cannot be recreated exactly through ordinary GitHub APIs

- Original GitHub database/repository object identity.
- Native issue/PR author identity when posting as `rdeepmath91`.
- Original `created_at`/`updated_at` timestamps on new destination objects.
- Exact historical merged/closed PR identity, merge actor, merge event, review decisions, review threads, or timeline.
- Stars, watchers, subscriptions, notifications, traffic data, Actions run identity/history, audit logs, secret values, fork-network identity, or old URLs.
- Original reaction actors and some timeline event types.
- Organization project membership or organization-only fields that a personal repository cannot own.
- Erasure of the existing public fork `RaihanParl/coding-agent-usage-dashboard`, prior clones, caches, notifications, audit/support records, or external indexes.

This migration must never be described as a perfect invisible clone. It is an exact Git mirror plus a transparent, high-fidelity metadata reconstruction.

## Number-preservation strategy

GitHub issues and PRs share one monotonically increasing repository number sequence. The source currently has 54 numbered objects: 36 issues and 18 PRs.

To preserve references such as `#9`, `#52`, `#53`, and `#54`:

1. Recreate source objects strictly in ascending source number order.
2. Recreate ordinary source issues as destination issues.
3. Recreate closed or merged historical PRs as destination issues labeled `archived-pr`, with their PR body, commits, reviews, review comments, discussion, merge metadata, changed-file manifest, and patch links preserved in the body/comments/archive.
4. Attempt to recreate the single currently open PR as a real native PR at its corresponding sequence position only after its base and head refs have been pushed and verified.
5. If native PR creation at the exact sequence position is impossible, create an `archived-pr` issue instead and record that deviation.
6. Stop immediately if any destination number differs from the expected source number. Do not continue and compound the mapping error.

This preserves issue numbers and internal references better than recreating every historical PR as a misleading new native PR. The tradeoff is that historical PRs are visibly archived issues rather than native pull-request objects.

## Migration workspace

Create all implementation artifacts outside the product tree until reviewed:

- Migration root: `/home/raymond-christopher/migrations/coding-agent-usage-dashboard-mirror/`
- Existing recovery archive: `/home/raymond-christopher/migration-backups/coding-agent-usage-dashboard-20260814T101757Z.tar.gz`
- Planned scripts:
  - `scripts/export_source.py`
  - `scripts/download_attachments.py`
  - `scripts/build_numbered_import.py`
  - `scripts/import_labels_milestones.py`
  - `scripts/import_numbered_objects.py`
  - `scripts/import_relationships.py`
  - `scripts/import_releases.py`
  - `scripts/reconcile.py`
  - `scripts/rewrite_local_remotes.py`
- Planned state:
  - `state/source-manifest.json`
  - `state/destination-manifest.json`
  - `state/object-map.json`
  - `state/import-checkpoints.jsonl`
  - `state/attachment-map.json`
  - `state/reconciliation.json`
- Planned reports:
  - `reports/preflight.md`
  - `reports/fidelity-limitations.md`
  - `reports/final-reconciliation.md`
  - `reports/deletion-gate.md`

Scripts must be idempotent where possible, refuse to operate on the wrong owner/repository ID, never print credentials, and checkpoint each created object before continuing.

---

### Task 1: Cancel the pending native transfer

**Objective:** Remove the transfer request to `rdeepmath91` and prove the repository remains private under `raychrisgdp`.

**Files:**
- Create: `reports/transfer-cancellation.md`
- Update: `state/source-manifest.json`

**Steps:**

1. Verify source identity, repository ID `1249859353`, owner, and private visibility with the GDP-scoped GitHub identity.
2. Verify `rdeepmath91/coding-agent-usage-dashboard` does not exist.
3. Open the source repository's Settings → Danger Zone through an authenticated source-account browser session.
4. Use GitHub's `Cancel transfer` control. Do not initiate another transfer.
5. Read back the source repository owner, ID, visibility, default branch SHA, issue count, and PR count.
6. Verify the personal account still receives `404` for the nonexistent destination.
7. Save a cancellation receipt without email addresses, cookies, tokens, or session data.

**Expected result:** source remains `raychrisgdp/coding-agent-usage-dashboard`, ID `1249859353`, private; no transfer invitation remains; personal destination absent.

**Stop condition:** Login wall or missing cancel control. Ask Raymond to cancel it in GitHub Settings and verify afterward.

### Task 2: Refresh the immutable source archive

**Objective:** Capture the complete live source state after transfer cancellation and before destination creation.

**Files:**
- Create: `scripts/export_source.py`
- Create: `scripts/download_attachments.py`
- Create: `state/source-manifest.json`
- Create: `archive/raw/**/*.json`
- Create: `archive/attachments/**/*`
- Create: `reports/preflight.md`

**Steps:**

1. Recheck source repository ID, owner, visibility, default branch, and exact main SHA.
2. Export all branches, tags, Git refs, PR refs reachable through GitHub, and commit graph.
3. Detect Git LFS with `.gitattributes`, `git lfs ls-files --all`, and remote LFS fetch; record zero explicitly if absent.
4. Detect and clone the wiki repository; record absence explicitly if unavailable.
5. Export every numbered issue and PR in sequence, including bodies, comments, labels, assignees, milestones, reactions, timeline/events, linked commits, files, reviews, review comments, checks, and relationship nodes.
6. Export labels, milestones, releases/assets, discussions, repository settings, collaborators, rulesets, protection, Actions workflow/run/artifact metadata, environment names, secret names, variable names, deploy keys, hooks, Pages, packages, security settings, projects, and issue types when the APIs permit access.
7. Scan Markdown bodies/comments for attachment URLs. Download each reachable attachment without executing content; hash it; record original URL, MIME type, byte length, SHA-256, and local path.
8. Store raw unmodified API payloads and normalized JSONL records separately.
9. Create a fresh Git bundle and `git bundle verify` it.
10. Generate SHA-256 checksums for every archive file and verify them.
11. Compare the refreshed inventory against the existing 2026-08-14 archive; explain every delta.

**Verification:**

- Source default SHA equals live `refs/heads/main`.
- Numbered object count equals the maximum sequence and has no unexplained gaps.
- Issue count, PR count, comments, reviews, labels, relationships, branches, tags, and assets agree across REST, GraphQL, and normalized manifests.
- Every downloaded attachment hash verifies.
- Bundle verification passes.

### Task 3: Build and dry-run the importer

**Objective:** Prove import ordering, attribution, reference rewriting, and resume behavior without touching GitHub.

**Files:**
- Create: `scripts/build_numbered_import.py`
- Create: `tests/test_numbered_import.py`
- Create: `tests/test_reference_rewrite.py`
- Create: `tests/test_checkpoint_resume.py`
- Create: `state/import-plan.jsonl`
- Create: `reports/fidelity-limitations.md`

**Steps:**

1. Write tests for contiguous source-number ordering and issue/PR classification.
2. Write tests for attribution headers and preservation of original Markdown.
3. Write tests that rewrite `#N` references to the same destination number while retaining the original URL in metadata.
4. Write tests for cross-repository URLs, deleted attachment URLs, code fences, and mentions that must not notify unrelated users.
5. Neutralize source `@mentions` in reconstructed text unless intentionally retained as plain attribution.
6. Write tests for resume checkpoints so a failed import cannot duplicate objects.
7. Generate the complete planned API mutation stream locally.
8. Assert expected destination number for every planned create operation.
9. Render representative issue, archived PR, review, and attachment records to Markdown for manual review.
10. Produce an explicit field-by-field fidelity matrix.

**Run:** `python -m pytest tests -v`

**Expected:** all importer tests pass; import plan covers every source object exactly once; no external mutation occurs.

### Task 4: Create and verify the empty private destination

**Objective:** Create a blank private personal repository with no README/license initialization and prove its access boundary before pushing anything.

**Files:**
- Update: `state/destination-manifest.json`
- Create: `reports/destination-creation.md`

**Steps:**

1. Verify personal API identity is exactly `rdeepmath91`.
2. Recheck target-name availability immediately before creation.
3. Create `rdeepmath91/coding-agent-usage-dashboard` as private, without initializing files.
4. Verify destination owner, new repository ID, private visibility, and personal `ADMIN` permission.
5. Verify anonymous access returns `404`.
6. Verify the GDP identity has no access unless deliberately required during the migration. Prefer personal-token API writes and personal SSH transport rather than adding GDP as collaborator.
7. Disable or leave unused destination features until their corresponding import phase.
8. Record the destination repository ID and reject every later mutation if it changes.

**Stop condition:** destination is public, preexisting, initialized, wrong owner, or visible to the GDP identity unexpectedly.

### Task 5: Mirror Git data and auxiliary repositories

**Objective:** Put exact code/history into the verified private destination before recreating metadata.

**Files:**
- Create: `reports/git-mirror.md`
- Update: `state/destination-manifest.json`

**Steps:**

1. Create a fresh bare mirror from the source and retain its `show-ref` output.
2. Push accepted branch/tag/note refs to the destination with the personal SSH identity. Do not push GitHub-managed `refs/pull/*` as normal refs.
3. For every source PR, preserve head/base commit SHAs in the archive. Create namespaced archival refs only if necessary and clearly named, such as `refs/heads/archive/pr-<N>-head`.
4. Fetch all LFS objects and push all LFS objects to the destination if LFS is present.
5. Mirror wiki Git history if the source wiki exists.
6. Recreate release tags only after proving their SHAs match.
7. Preserve reviewed local-only branches under their existing names when safe; use `archive/local/<name>` for deleted-upstream or ambiguous branches.
8. Do not push stashes as branches without an explicit manifest entry.
9. Compare source and destination commit IDs, trees, branch tips, tags, notes, LFS hashes, and wiki refs.

**Verification:** default branch tree hash and commit SHA match; every planned ref has the same SHA; destination remains private; source is unchanged.

### Task 6: Import labels and milestones

**Objective:** Establish metadata dependencies without consuming numbered issue slots.

**Files:**
- Create: `scripts/import_labels_milestones.py`
- Create: `tests/test_labels_milestones.py`
- Update: `state/import-checkpoints.jsonl`

**Steps:**

1. Recreate source labels with exact names, colors, and descriptions.
2. Add migration-only labels such as `archived-pr` only after confirming label creation does not affect object numbering.
3. Recreate milestones with title, description, due date, and open/closed state.
4. Record source node/REST IDs to destination IDs.
5. Read back every label and milestone and compare normalized fields.

### Task 7: Recreate the numbered issue/PR sequence

**Objective:** Reconstruct all 54 numbered source objects without losing source-number references.

**Files:**
- Create: `scripts/import_numbered_objects.py`
- Create: `tests/test_object_payloads.py`
- Update: `state/object-map.json`
- Update: `state/import-checkpoints.jsonl`

**Steps for each source number, strictly serialized:**

1. Assert destination's next number equals the source number.
2. If source object is an issue, create a destination issue with attribution header, original body, mapped labels/milestone, and eligible assignees.
3. If source object is a closed/merged PR, create an issue labeled `archived-pr` containing:
   - original PR metadata and URL;
   - base/head refs and SHAs;
   - merge SHA/actor/time when present;
   - changed-file and commit manifests;
   - original body;
   - links to archived patch/diff/API records;
   - explicit statement that GitHub cannot recreate the original native PR identity.
4. If source object is the currently open PR, verify the exact destination base/head SHAs and attempt native PR creation. If that would alter numbering or cannot represent the source branch, stop for a decision rather than silently substituting.
5. Immediately verify the created destination number. Abort on mismatch.
6. Store source/destination node and REST IDs in `object-map.json`.
7. Add comments in chronological order with visible original author/timestamp attribution. Preserve raw Markdown and archived attachment links.
8. Represent reviews, review comments, and unreproducible timeline events as attributed archival comments and raw JSON records. Do not impersonate reviewers or claim new review decisions.
9. Restore issue state and state reason only after all comments are imported.
10. Avoid notifying source participants through live mentions.

**Verification after every object:** number, title, normalized body hash, labels, milestone, state, imported comment count, and source attribution.

### Task 8: Restore relationships, attachments, releases, and settings

**Objective:** Reconnect all secondary repository surfaces after the numbered sequence is stable.

**Files:**
- Create: `scripts/import_relationships.py`
- Create: `scripts/import_releases.py`
- Create: `tests/test_relationship_mapping.py`
- Update: `state/attachment-map.json`
- Update: `state/import-checkpoints.jsonl`

**Steps:**

1. Recreate native parent/sub-issue edges using mapped destination node IDs.
2. Recreate native blockers/dependencies where supported; otherwise preserve them in a machine-readable relationship section and raw GraphQL archive.
3. Store attachments in the private `migration-archive` branch with stable hashed paths; update reconstructed links to destination-hosted private content while retaining original URLs in metadata.
4. Recreate releases against verified tags and upload downloaded assets; annotate original publish author/time.
5. Restore repository description, topics, homepage, feature flags, merge policy, branch protection, rulesets, Pages, and other personal-repo-compatible settings.
6. Preserve Actions workflow files through Git. Record historical run metadata and downloadable logs/artifacts in the archive; do not claim run history was migrated.
7. Recreate secret/variable names only as a reconfiguration checklist. Never export or invent secret values.
8. Record unsupported organization project memberships and security/audit surfaces without attempting a misleading substitute.

### Task 9: Full reconciliation

**Objective:** Produce proof that every transferable item is present before any cutover or deletion discussion.

**Files:**
- Create: `scripts/reconcile.py`
- Create: `tests/test_reconciliation.py`
- Create: `state/reconciliation.json`
- Create: `reports/final-reconciliation.md`

**Checks:**

1. Source and destination owner, repository ID, visibility, and viewer permissions.
2. Default branch and every mirrored ref SHA.
3. Reachable commit and tree counts/hashes.
4. LFS object count/hash and wiki refs.
5. Exact 1..54 numbered-object coverage and source-to-destination mapping.
6. Issue/archived-PR/native-PR counts and states.
7. Body/comment normalized hashes and attachment hashes.
8. Label, milestone, release, asset, and relationship counts.
9. Native hierarchy for #54 → #9/#41, #9 → #10/#11, #52 → #12/#24/#36, plus every other source edge.
10. Repository settings and automation-support matrix.
11. Anonymous destination access is `404`.
12. GDP identity cannot read the private destination unless Raymond explicitly chooses temporary migration access.
13. Existing public fork and every other unavoidable residue are prominently listed.
14. Run the product test suite against a clean destination clone and compare its head SHA with the source.

**Required result:** all transferable fields pass; every unsupported or lossy field appears as a named reconciliation exception with a pointer to its raw archived record.

### Task 10: Local cutover

**Objective:** Move all local development worktrees to the private personal destination only after reconciliation passes.

**Files:**
- Create: `scripts/rewrite_local_remotes.py`
- Create: `reports/local-cutover.md`

**Steps:**

1. Snapshot all ten worktree paths, branches, heads, dirty state, upstreams, and current remotes again.
2. Verify every worktree is clean or stop for explicit treatment of dirty work.
3. Update the shared `origin` remote to the verified personal SSH URL.
4. Repair only upstreams whose intended branch was imported; preserve intentional `gone`/main-tracking arrangements explicitly.
5. Fetch from the destination through the personal SSH identity.
6. Verify every worktree head remains unchanged and reachable from the destination or recovery bundle.
7. Run the full test suite from a clean main worktree.
8. Keep the original source URL as a read-only manifest field, not as an active Git remote, unless Raymond asks for a temporary `source-archive` remote.

### Task 11: Deletion gate, separate approval required

**Objective:** Prevent source deletion until Raymond reviews the evidence and explicitly authorizes the exact repository deletion.

**Files:**
- Create: `reports/deletion-gate.md`

**Steps:**

1. Present `final-reconciliation.md`, fidelity limitations, destination URL/ID, visibility proof, test results, object/ref counts, local cutover proof, and recovery archive checksums.
2. State again that the public fork, prior clones, GitHub records, caches, and external indexes cannot be erased.
3. Ask a fresh, explicit question naming the source repository: whether to delete `raychrisgdp/coding-agent-usage-dashboard`.
4. Do not interpret earlier statements such as “after moving everything” as deletion approval.
5. If approved, re-run the complete live source-versus-destination reconciliation immediately before deletion.
6. Refuse deletion if source changed, destination is not private, any transferable object is missing, any local head is unpreserved, or the recovery archive fails checksums.
7. Delete only the named source repository, then verify source URL behavior and destination integrity.
8. Retain the offline recovery archive until Raymond separately approves its removal.

---

## Acceptance criteria

- No native GitHub transfer is used.
- Pending transfer request is canceled before destination creation.
- Destination is a new private repository owned by `rdeepmath91`.
- All accepted Git refs and object SHAs match the source.
- All local-only work is either pushed under reviewed names or present in the verified recovery bundle.
- Every source issue/PR number has one mapped destination record.
- Every source comment/review/timeline record is either reconstructed with attribution or preserved in the raw private archive with an explicit exception.
- Labels, milestones, releases/assets, attachments, and native issue relationships reconcile.
- The destination passes the repository's complete test suite.
- The destination is anonymous-inaccessible and personal-admin accessible.
- Source remains private and undeleted throughout migration and reconciliation.
- Source deletion requires a new explicit approval after the complete report.

## Principal risks and controls

| Risk | Control |
|---|---|
| Destination numbering drifts | Empty destination; strictly serialized creates; verify after every object; abort on mismatch |
| Historical PRs appear deceptively current | Use `archived-pr` issues with explicit attribution and raw records |
| Current open PR cannot be recreated at #53 | Preflight exact base/head refs; stop for decision rather than changing mapping silently |
| Attachments disappear after source deletion | Download, hash, store privately, rewrite links, retain original URL metadata |
| API interruption duplicates objects | Durable checkpoint JSONL plus destination-number and source-marker readback |
| Mentions notify old participants | Neutralize live mentions while retaining textual attribution |
| Source changes during long import | Capture cutoff timestamp/SHA; final delta export and reconciliation; replay deltas before deletion gate |
| Organization-only metadata cannot move to personal repo | Archive raw records and list unsupported fields explicitly |
| Existing public fork remains | Disclose as uncontrollable residue; never promise erasure |
| Accidental source deletion | Separate named approval gate and immediate pre-delete parity run |

## Open decisions for Raymond before execution

1. Confirm destination name: `rdeepmath91/coding-agent-usage-dashboard`.
2. Confirm the recommended PR representation: closed/merged PRs as numbered `archived-pr` issues, current open PR as native if feasible.
3. Confirm whether historical source `@mentions` should be neutralized to avoid notifications; recommended: yes.
4. Confirm whether the migration archive should live on an isolated `migration-archive` branch; recommended: yes.
5. Confirm whether all local-only/deleted-upstream branches should be pushed under `archive/local/*`; recommended: preserve them there.

No source deletion is included in plan approval. Deletion remains a separate final decision.