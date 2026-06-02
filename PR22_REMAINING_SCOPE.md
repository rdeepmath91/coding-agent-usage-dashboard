# PR 22 scope checklist

PR: https://github.com/raychrisgdp/coding-agent-usage-dashboard/pull/22
Issue: https://github.com/raychrisgdp/coding-agent-usage-dashboard/issues/20
Follow-up issue: https://github.com/raychrisgdp/coding-agent-usage-dashboard/issues/23

## Recommendation

Keep PR 22 focused on Overview card semantics, cost-confidence honesty, and last-mile card legibility. Do not add the full decision summary in this PR; that belongs in #23 because it changes dashboard information architecture and chart interactions.

After reviewing the screenshot, I would include card reorder in PR 22. It is a small hierarchy fix, and the screenshot makes the current order visibly wrong: `Sessions` is too prominent and cost appears too late.

## PR 22 checklist

| # | Priority | Item | Status | Why it belongs / does not belong in PR 22 | Suggested implementation |
|---:|---|---|---:|---|---|
| 1 | P0 | Make `Total Tokens` mean full token volume | Done | Core issue #20 requirement | `Total Tokens = non-cache input + output + cache read + cache write` |
| 2 | P0 | Rename top-level `Non-cache Input` to `Input Tokens` | Done | Core issue #20 requirement | `Input Tokens = non-cache input + cache read + cache write` |
| 3 | P0 | Keep `Output Tokens` as assistant output only | Done | Prevents cache write being misclassified as output | `Output Tokens = assistant output` |
| 4 | P0 | Preserve `Session Tokens` semantics in details/docs/tests | Done | Keeps backward-compatible accounting language without making it a top-level card | `Session Tokens = non-cache input + output` |
| 5 | P0 | Avoid top-level `Fresh`, `Canonical`, and `Effective` labels | Done | These are too internal for the Overview cards | Use those only in docs/tooltips if needed, not card labels |
| 6 | P0 | Make partial API-equivalent cost visually honest | Done | Cost confidence is part of making the metric trustworthy | Amber `PARTIAL ESTIMATE` badge plus `35 of 64 models priced` |
| 7 | P1 | Add cached-share ratio to `Total Tokens` card | Done | It directly supports issue #20's acceptance point: cache context as raw number plus ratio/share where useful | Change secondary text to `757.0M direct · 10.6B cached · 93% cached` |
| 8 | P1 | Use friendlier UI wording than `session` in top-card secondary copy | Done | `session` is precise but internal; it can be confused with the Sessions card | Use `direct` in UI, with tooltip: `Direct/session tokens = non-cache input + assistant output.` |
| 9 | P1 | Fix secondary-line wrapping in token cards | Done | Screenshot shows `10.6B cached` and `19.7M write` wrapping awkwardly even on a huge viewport | Use a more compact/flexible meta layout, or shorten copy while keeping tooltip detail |
| 10 | P1 | Clarify cache wording in `Input Tokens` secondary line | Done | `read/write` is terse; `cache read/cache write` is clearer, but may crowd the card | Prefer `727.6M fresh · 10.5B cache read · 19.7M cache write` if layout fits; otherwise use `727.6M fresh · 10.5B cached input` and put read/write split in tooltip |
| 11 | P1 | Reorder cards: Total, Cost, Input, Output, Sessions | Done | Screenshot confirms `Sessions` is too prominent and cost deserves earlier placement | Render order: `Total Tokens`, `API-Equivalent Cost`, `Input Tokens`, `Output Tokens`, `Sessions` |
| 12 | P2 | Add top decision summary strip | Defer to #23 | Changes dashboard information architecture and requires derived summary fields | `30d usage: 11.3B tokens · 93% cached · OpenCode leads · GPT-5.5 is 50%` |
| 13 | P2 | Add source mix summary | Defer to #23 | Better as part of decision summary, not token-card semantics | `OpenCode 65% · Codex 22% · Hermes 13%` |
| 14 | P2 | Replace source-card `ACTIVE SOURCE` states | Defer to #23 | Interaction/state work beyond issue #20 | `Included in totals`, `Focused`, `Click to focus chart` |
| 15 | P2 | Add source-card action affordances | Defer to #23 | Current `click name to filter repo` is cryptic and should become explicit interaction UI | `Focus chart →` and `Repos →` |
| 16 | P2 | Add chart focus summary and peak-day annotation | Defer to #23 | Chart interpretation work, not card semantics | `Focus: gpt-5.5 · 50% of 30d volume · peak May 19` and `Peak: May 19 · 989.5M tokens` |
| 17 | P2 | Improve chart legend truncation | Defer to #23 | Legend labels are cut aggressively; fixing this belongs with chart interaction work | Add hover/full-label tooltip or two-line legend items |
| 18 | P2 | Add total-volume line over stacked bars | Defer to #23 | Helps trend detection, but changes chart behavior beyond issue #20 | Thin total-volume overlay line above stacked bars |
| 19 | P3 | Typography split: sans UI text, mono numbers | Defer to #23 | Visual-system pass across dashboard | Keep mono for numbers/code; use sans for headings, labels, prose |
| 20 | P3 | Reduce H1 dominance and tighten vertical rhythm | Defer to #23 | Screenshot shows `Overview` and top spacing take attention from metrics | Smaller H1, less vertical gap, summary strip can replace explanatory dead space |
| 21 | P3 | Align info icons consistently | Defer to #23 | Screenshot shows info icons floating at inconsistent positions | Align to card top-right or consistent secondary-line end |
| 22 | P3 | Previous-window deltas | Defer to later / #23 stretch | Requires previous-window data and API/UI design | `+18% vs previous 30d` |
| 23 | P1 | Add `3d` quick range before `7d` in the top controls | Done | Keeps the dashboard quick filters aligned with requested short-window review | Render `3d`, `7d`, `30d`, `90d`, `All` and assert `3d` appears before `7d` |

## Suggested final PR 22 scope

I would make these PR 22 changes before merge:

1. Add cached share to the `Total Tokens` secondary line.
2. Replace `session` with `direct` in visible card copy, while keeping precise `session tokens` wording in tooltip/docs/tests.
3. Fix secondary-line wrapping in the token cards.
4. Reorder the metric cards: `Total Tokens`, `API-Equivalent Cost`, `Input Tokens`, `Output Tokens`, `Sessions`.
5. Clarify `read/write` as `cache read/cache write`.
6. Add the `3d` quick range before `7d` in the top controls.

Everything else should remain in #23.

## Proposed final card copy for PR 22

```text
TOTAL TOKENS
11.3B
757.0M direct · 10.6B cached · 93% cached
```

```text
API-EQUIVALENT COST
$6367.91
PARTIAL ESTIMATE
35 of 64 models priced
```

```text
INPUT TOKENS
11.3B
727.6M fresh · 10.5B cache read · 19.7M cache write
```

If that line wraps too much:

```text
INPUT TOKENS
11.3B
727.6M fresh · 10.5B cached input
```

and keep the exact cache read/write split in the tooltip.

```text
OUTPUT TOKENS
29.5M
assistant-generated
```

```text
SESSIONS
1,777
2026-05-03 → 2026-06-02
```

## Current validation status

As of the latest PR 22 update:

- Local unit tests passed: `uv run python -m unittest tests.test_app tests.test_readme -v`
- Local review script passed: `scripts/review.sh`
- Browser smoke passed on `http://127.0.0.1:8321`
- Browser console had no JS errors
- DOM verified range order: `3d`, `7d`, `30d`, `90d`, `All`
- GitHub CI `test` passed at `606f0792e28a2666f904da394e83becf6b562348`
- PR 22 is mergeable at that head
