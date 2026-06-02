## Summary

- Make Overview `Total Tokens` the intuitive full token volume including cache read/write.
- Rename the top-level input card from `Non-cache Input` to `Input Tokens` and show fresh/read/write breakdown in the secondary line.
- Show partial API-equivalent cost coverage as an amber `PARTIAL ESTIMATE` badge instead of muted footnote copy.
- Reorder top cards to put `Total Tokens` and cost first, move `Sessions` last, add cached-share percentage, and use `direct` for the visible session-token bucket.
- Add the `3d` quick range before `7d` in the top Usage date range controls.
- Keep session-token semantics explicit in details/docs/tests instead of using `Canonical`, `Effective`, or `Fresh` as top-level card language.
- Update simulated data, settings copy, README, AGENTS guidance, scope logs, and tests to lock the new formulas and UI order.

## Formulas

- `Total Tokens = non-cache input + output + cache read + cache write`
- `Input Tokens = non-cache input + cache read + cache write`
- `Output Tokens = assistant output`
- `Session Tokens = non-cache input + output`

## Fixes in latest update

- Include partial model costs (`partial_cost_usd`) in the Overview cost card total, not just fully priced models.
- When some models are only partially priced, show their known subtotal in the cost card tooltip metadata.
- Reduce simulated mode to a single `OpenCode (simulated)` source card so screenshots no longer show empty local `Codex CLI` / `Hermes` cards that have no simulated totals.
- Make `setCostMeta` distinguish fully priced vs partially priced models with an explicit `partialCount` argument.
- In all-partial scenarios, the badge still shows `Partial estimate` and the visible copy now says `6 partially priced of 6 models` instead of falsely saying `6 of 6 models priced`.
- In mixed scenarios, copy reads `X fully priced, Y partially priced of Z models`.
- Constrain loading shimmer styling to stat cards.
- Add `3d` before `7d` in the top range controls and assert the order in tests.

Latest patch: `d429b9b`

## Scope notes

- `PR22_REMAINING_SCOPE.md` tracks fixed vs deferred review items.
- `PR22_BEFORE_AFTER.md` records before/after UI changes and latest validation.
- Decision-guided Usage Summary and dashboard focus states remain split out to #23.

## Validation

- `uv run python -m unittest tests.test_app tests.test_readme -v`
- `scripts/review.sh`
- Browser smoke: `http://127.0.0.1:8321`
  - cards rendered in order as `Total Tokens`, `API-Equivalent Cost`, `Input Tokens`, `Output Tokens`, `Sessions`
  - range controls rendered in order as `3d`, `7d`, `30d`, `90d`, `All`
  - cost card rendered `PARTIAL ESTIMATE` + model coverage copy
  - `Total Tokens` secondary line renders `direct`, cached raw volume, and cached-share percentage
  - `Input Tokens` secondary line renders `fresh`, `cache read`, and `cache write` buckets
  - browser console had no JS errors
- GitHub CI `test` passed on `d429b9b9e8e96b67dba2e8f0310437258a4ad7d7`.

Closes #20
