"""Shared helpers for token-metric normalization used across APIs."""


def normalize_token_count(value: int | None) -> int:
    """Normalize nullable token counters to a non-negative integer."""
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def effective_token_total(tokens_total: int | None, cache_read: int | None, cache_write: int | None) -> int:
    """Return token volume including cache read/write for ranking and charting."""
    return (
        normalize_token_count(tokens_total)
        + normalize_token_count(cache_read)
        + normalize_token_count(cache_write)
    )
