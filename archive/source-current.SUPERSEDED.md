# Superseded source-current artifacts

The files formerly named `source-current.*` are pre-remediation evidence. They
intentionally do not contain all hidden pull-request objects and must not be
used as the migration's recovery package or canonical Git bundle.

Use these artifacts instead:

- `archive/source-with-pull-refs.bundle`
- `archive/source-with-pull-refs.bundle.verify`
- `archive/source-with-pull-refs.sha256`

The replacement bundle contains all 110 verified PR-related Git SHAs and has a
portable checksum manifest. The old files are retained for audit history only.
