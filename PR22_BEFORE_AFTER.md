# PR 22 before/after changes

PR: https://github.com/rdeepmath91/coding-agent-usage-dashboard/issues/22 (archived PR record)

## Implemented in the latest PR 22 update

| # | Area | Before | After |
|---:|---|---|---|
| 1 | Card order | `Sessions`, `Total Tokens`, `Input Tokens`, `Output Tokens`, `API-Equivalent Cost` | `Total Tokens`, `API-Equivalent Cost`, `Input Tokens`, `Output Tokens`, `Sessions` |
| 2 | Total token secondary copy | `757.0M session · 10.6B cached` | `764.8M direct · 10.6B cached · 93% cached` on the current live data |
| 3 | Total token cache context | Raw cached token count only | Raw cached token count plus cached-share ratio |
| 4 | Visible token-bucket wording | `session` shown as a visible bucket label | `direct` shown as the visible UI label; tooltip keeps precise `Direct/session tokens = non-cache input + output` wording |
| 5 | Input token secondary copy | `727.6M fresh · 10.5B read · 19.7M write` | `735.0M fresh · 10.6B cache read · 19.7M cache write` on the current live data |
| 6 | Secondary-line wrapping | Browser could split phrases like `10.6B cached`, `19.7M write`, or `93% cached` awkwardly | Added non-breaking number+label fragments so each metric phrase stays together when wrapping |
| 7 | Cost confidence | Muted `approx · 35/64 priced` footnote-style copy | Amber `PARTIAL ESTIMATE` badge plus `35 of 64 models priced` |
| 8 | Cost card priority | Cost was last among the top metric cards | Cost is second, immediately after `Total Tokens` |
| 9 | Sessions card priority | Sessions was first and visually over-weighted | Sessions moved last |
| 10 | Regression tests | Tests checked general accessible dashboard controls and cost badge | Tests now also assert card order, `direct` wording logic, total cached-share logic, and `cache read` wording logic |
| 11 | Top range controls | Quick filters started at `7d` | Added `3d` before `7d`, rendering `3d`, `7d`, `30d`, `90d`, `All` |

## Final visible card copy pattern

```text
TOTAL TOKENS
11.4B
764.8M direct · 10.6B cached · 93% cached
```

```text
API-EQUIVALENT COST
$6434.95
PARTIAL ESTIMATE
35 of 64 models priced
```

```text
INPUT TOKENS
11.4B
735.0M fresh · 10.6B cache read · 19.7M cache write
```

```text
OUTPUT TOKENS
29.7M
assistant-generated
```

```text
SESSIONS
1,787
2026-05-03 → 2026-06-02
```

Numbers above reflect the live dashboard at verification time; they can move as new local usage lands.

## Still deferred to issue #23

| # | Deferred item | Reason |
|---:|---|---|
| 1 | Usage Summary strip | Changes dashboard information architecture |
| 2 | Source mix summary | Better as part of Usage Summary |
| 3 | Source-card selected/included states | Interaction/state redesign beyond issue #20 |
| 4 | Source-card explicit actions | Needs broader source-card UX pass |
| 5 | Chart focus summary | Chart interpretation work, not card semantics |
| 6 | Peak-day annotation | Chart interpretation work |
| 7 | Legend truncation cleanup | Chart/legend UX pass |
| 8 | Total-volume line overlay | Chart behavior change |
| 9 | Typography split | Visual-system pass |
| 10 | H1/spacing cleanup | Page-level layout pass |
| 11 | Info-icon alignment | Broader component polish |
| 12 | Previous-window deltas | Requires previous-window data/API design |

## Verification

- `uv run python -m unittest tests.test_app tests.test_readme -v` passed.
- `scripts/review.sh` passed.
- Browser smoke on `http://127.0.0.1:8321` passed.
- Browser console had no JavaScript errors.
- DOM verified card order: `TOTAL TOKENS`, `API-EQUIVALENT COST`, `INPUT TOKENS`, `OUTPUT TOKENS`, `SESSIONS`.

## Latest update: tooltip clipping fix

- Replaced `.stat-card { overflow: hidden; }` with `.stat-card { overflow: visible; }` so metric tooltips can render outside their cards again.
- Kept the loading shimmer constrained by animating `background-position` on the card overlay instead of translating an overflowing pseudo-element.
- Added regression assertions for visible card overflow and background-position shimmer animation.
- Browser geometry check confirmed the cost tooltip is visible, escapes the card bounds, and remains inside the viewport.

## Latest update: 3d range filter

- Added `3d` before `7d` in the top Usage date range controls.
- Added a regression assertion that `data-days="3"` exists and appears before `data-days="7"`.
- Pushed commit `095a5c6` (`095a5c6e1e465b7385b56280a0aec5646826ce20`).
- GitHub CI `test` passed on that head.
