# Deletion gate

Status: **awaiting separate explicit approval**

## Verified migration state

- Source remains `raychrisgdp/coding-agent-usage-dashboard`, private, database ID `1249859353`.
- Destination is `rdeepmath91/coding-agent-usage-dashboard`, private, database ID `1334182958`.
- Source and destination live branch SHAs reconcile; destination `main` is `4bc75fa4e206cffd5e20a969824bc47a042c3bc1`.
- Numbered objects 1–54 reconcile, including native open PR #53 and 17 attributed archived-PR issues.
- Labels, comments, native parent/sub-issue relationships, settings, attachments, and releases reconcile or are explicitly recorded as zero/unavailable.
- The clean destination clone passes all 62 tests.
- Local worktrees were cut over to the personal destination SSH alias; the untracked `.hermes/` migration-plan directory was preserved.
- The private `migration-archive` branch contains raw API records, Git bundle evidence, state maps, checksums, scripts, and reports.
- The recovery archive remains at `/home/raymond-christopher/migration-backups/coding-agent-usage-dashboard-20260814T101757Z.tar.gz` with SHA-256 `d67e06864fffd7374317451821c55483cb6bf85826eeceb410372eff6e2a1103`.

## Unavoidable residue

Deletion cannot erase the existing public `RaihanParl/coding-agent-usage-dashboard`
fork, prior clones, caches, notifications, GitHub audit/support records, or
external indexes. Historical PR identity/timestamps and organization-only
metadata also cannot be recreated through ordinary APIs; the raw archive and
fidelity report document those exceptions.

## Approval boundary

No source deletion has occurred. A fresh approval must explicitly name:

`raychrisgdp/coding-agent-usage-dashboard`

Until that approval is received, the source remains private and available as a
final recovery reference.
