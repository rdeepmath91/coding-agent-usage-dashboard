# Source Contracts

This document records adapter-specific field and token rules for dashboard data sources.

## Codex CLI

The Codex adapter reads session metadata from `~/.codex/state_5.sqlite`, table
`threads`. The trusted metadata fields are session id, rollout path, created and
updated timestamps, title/preview, cwd, provider, and model.

Token metrics come from the latest cumulative `total_token_usage` object in each
referenced rollout JSONL file. The trusted token fields are:

- `input_tokens` -> raw Codex input, including cached input
- `cached_input_tokens` -> cache read tokens
- `input_tokens - cached_input_tokens` -> dashboard input, to match OpenCode's non-cache input semantics
- `output_tokens` -> output tokens

The adapter filters, groups, sorts, and displays Codex records by thread
`updated_at`, not `created_at`, because token metrics are latest cumulative
rollout usage for the thread. This keeps long-lived threads updated inside the
selected range from appearing on out-of-range created dates.

Adapter session tokens remain non-cache input + output. Cache read tokens are
preserved so the Overview can add them into full `Total Tokens`. Codex local
JSONL does not expose cache-write tokens, so the dashboard shows cache write as
unavailable for Codex instead of treating it as zero. The adapter does not infer
token counts from transcript text.

## Hermes

The Hermes adapter reads session metadata and token metrics from
`~/.hermes/state.db`, table `sessions`. The trusted metadata fields are session
id, source, title, started/ended timestamps, message/tool-call counts, provider,
and model.

The trusted token fields are:

- `input_tokens` -> dashboard non-cache input tokens
- `output_tokens` -> output tokens
- `cache_read_tokens` -> cache read tokens
- `cache_write_tokens` -> cache write tokens

Hermes records are filtered, grouped, sorted, and displayed by `started_at`.
Adapter session tokens remain input + output. Cache read/write tokens are
preserved so the Overview can add them into full `Total Tokens`. The adapter
does not infer token counts from message text.

## Cursor IDE Composer

Cursor local data comes from Cursor IDE global storage SQLite state, table
`cursorDiskKV`, keys `composerData:*`. The default path is
`~/.config/Cursor/User/globalStorage/state.vscdb` on Linux and
`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` on macOS.
Set `DASHBOARD_CURSOR_STATE_PATH` when Cursor stores global state somewhere
else.

The trusted local fields are:

- `composerId` -> session id
- `createdAt` / `lastUpdatedAt` / assistant `timingInfo.*` -> display timestamp windowing
- assistant conversation item `tokenCount.inputTokens` -> dashboard non-cache input tokens
- assistant conversation item `tokenCount.outputTokens` -> output tokens
- `promptTokenBreakdown.totalUsedTokens` -> prompt/context tokens when assistant bubble `tokenCount` rows are absent
- `contextTokensUsed` -> prompt/context tokens when `promptTokenBreakdown.totalUsedTokens` is absent

The adapter prefers summed assistant-bubble token counts per composer session.
When newer local records omit bubble counts, it uses prompt/context token totals
as input/session tokens and leaves assistant output unavailable. Cursor local
state does not expose trusted cache metrics or model IDs in a stable local
contract for these sessions, so the dashboard keeps those fields unavailable
instead of guessing values.

Cursor Agent CLI chats are a separate local storage surface under `~/.cursor`.
PR #37 does not parse those files for token totals because the local transcript
and chat store observed so far expose message/model provenance but not trusted
input/output token counters.
