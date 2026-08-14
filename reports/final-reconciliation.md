# Final reconciliation

Generated: `2026-08-14T13:30:01.699767Z`

Status: **pass**

## Checks

- PASS — `source_identity`
- PASS — `destination_identity`
- PASS — `destination_anonymous_404`
- PASS — `source_api_cannot_read_destination`
- PASS — `numbered_coverage`
- PASS — `source_markers`
- PASS — `source_refs_match`
- PASS — `labels_match`
- PASS — `comment_count`
- PASS — `native_open_pr`
- PASS — `relationships_match`
- PASS — `attachments_reconciled`
- PASS — `releases_reconciled`
- PASS — `clean_destination_tests`
- PASS — `local_origin_cutover`

## Counts

- Numbered source/destination coverage: `54/54`
- Imported object map entries: `54`
- Source/destination issue comments: `9/9`
- Source/destination parent edges: `15/15`

## Named exceptions

- Original GitHub author identities and timestamps cannot be recreated on new objects.
- Pages and rulesets were unavailable to the source exporter and remain explicit archive exceptions.
- Historical PRs are attributed archived issues; only open PR #53 is native.
- Stars, watchers, notifications, Actions run identity/history, audit logs, and secret values are not migrated.

## Cutover gate

- completed with untracked .hermes/ migration-plan content preserved in the main worktree
