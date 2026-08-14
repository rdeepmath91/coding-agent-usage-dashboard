"""Model labeling, chart colors, alias resolution, and cost estimation."""

from dataclasses import dataclass
import json
import time
from urllib.parse import quote
import urllib.request

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_MODEL_PAGE_BASE = "https://openrouter.ai"
OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing"
PRICING_CACHE = {"fetched_at": 0, "prices": {}}

HARDCODED_MODEL_PRICES = {
    "openai/gpt-5.5": {
        "prompt": "0.000005",
        "completion": "0.00003",
        "input_cache_read": "0.0000005",
    },
    "openai/gpt-5.4": {
        "prompt": "0.0000025",
        "completion": "0.000015",
        "input_cache_read": "0.00000025",
    },
    "openai/gpt-5.4-mini": {
        "prompt": "0.00000075",
        "completion": "0.0000045",
        "input_cache_read": "0.000000075",
    },
    "openai/gpt-5.3-codex": {
        "prompt": "0.00000175",
        "completion": "0.000014",
        "input_cache_read": "0.000000175",
    },
    "deepseek/deepseek-v4-flash:free": {
        "prompt": "0",
        "completion": "0",
    },
    "deepseek/deepseek-v4-pro": {
        "prompt": "0.000000435",
        "completion": "0.00000087",
        "input_cache_read": "0.000000003625",
    },
    "moonshotai/kimi-k2.6": {
        "prompt": "0.00000073",
        "completion": "0.00000349",
        "input_cache_read": "0.00000025",
    },
    "qwen/qwen3.6-plus": {
        "prompt": "0.000000325",
        "completion": "0.00000195",
        "input_cache_write": "0.00000040625",
    },
    "minimax/minimax-m2.5:free": {
        "prompt": "0",
        "completion": "0",
    },
    "inclusionai/ling-2.6-flash": {
        "prompt": "0.00000001",
        "completion": "0.00000003",
        "input_cache_read": "0.000000002",
    },
    "anthropic/claude-sonnet-4": {
        "prompt": "0.000003",
        "completion": "0.000015",
        "input_cache_read": "0.0000003",
        "input_cache_write": "0.00000375",
    },
    "google/gemini-3.1-pro-preview": {
        "prompt": "0.000002",
        "completion": "0.000012",
        "input_cache_read": "0.0000002",
        "input_cache_write": "0.000000375",
    },
}

# OpenAI's pricing page is authoritative for first-party OpenAI models. Keep
# these values ahead of aggregator data because provider catalogs can lag an
# official price change.
OFFICIAL_MODEL_PRICES = {
    "openai/gpt-5.6-sol": {
        "prompt": "0.000005",
        "completion": "0.00003",
        "input_cache_read": "0.0000005",
        "input_cache_write": "0.00000625",
    },
    "openai/gpt-5.6-luna": {
        "prompt": "0.0000002",
        "completion": "0.0000012",
        "input_cache_read": "0.00000002",
        "input_cache_write": "0.00000025",
    },
}


@dataclass(frozen=True)
class PricingResolution:
    """Resolved provider pricing ID plus human-readable provenance."""

    model_id: str | None
    source: str | None = None
    aliased: bool = False


PRICING_MODEL_ALIASES = {
    ("opencode", "gpt-5.3-codex-spark"): "openai/gpt-5.3-codex",
    ("opencode-go", "gpt-5.3-codex-spark"): "openai/gpt-5.3-codex",
    ("openai", "gpt-5.3-codex-spark"): "openai/gpt-5.3-codex",
    ("openai-codex", "gpt-5.3-codex-spark"): "openai/gpt-5.3-codex",
    ("unknown", "gpt-5.3-codex-spark"): "openai/gpt-5.3-codex",
    ("antigravity", "gemini-3.1-pro"): "google/gemini-3.1-pro-preview",
    ("google-antigravity", "gemini-3.1-pro"): "google/gemini-3.1-pro-preview",
    ("google", "antigravity-gemini-3.1-pro"): "google/gemini-3.1-pro-preview",
    ("google", "antigravity-gemini-3.1-pro-low"): "google/gemini-3.1-pro-preview",
}

FREE_SUFFIX_MODEL_ALIASES = {
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash:free",
    "minimax-m2.5": "minimax/minimax-m2.5:free",
}

# DeepSeek V4 Flash is available through OpenCode plugins, but no trusted
# provider rate is configured for the non-free model yet. Keep the explicit
# `:free` alias separately priced at zero above.
UNPRICED_CANONICAL_MODEL_IDS = {
    "deepseek/deepseek-v4-flash",
}

CODEX_MODEL_PROVIDER_NAMESPACES = {
    "opencode-go",
    "opencode-free",
}

PROVIDER_MODEL_NAMESPACES = {
    "openai": "openai",
    "openai-codex": "openai",
    "google": "google",
}

MODEL_PREFIX_NAMESPACES = (
    ("deepseek-", "deepseek"),
    ("kimi-", "moonshotai"),
    ("qwen", "qwen"),
    ("minimax-", "minimax"),
    ("ling-", "inclusionai"),
)


def normalize_model(raw: str) -> dict:
    """Parse a model JSON or ID string into short name + provider."""
    if not raw:
        return {"id": "unknown", "provider": "unknown", "label": "Unknown"}

    import json

    try:
        obj = json.loads(raw)
        model_id = obj.get("id", "unknown")
        provider = obj.get("providerID", "unknown")
        variant = obj.get("variant", "")
    except (json.JSONDecodeError, TypeError):
        model_id = raw
        provider = "unknown"
        variant = ""

    # Build a clean display label
    label = model_id
    if provider == "opencode-go":
        label = f"{model_id} (go)"
    elif provider == "opencode":
        label = model_id
    elif provider == "openai":
        label = f"{model_id} (openai)"
    elif provider and provider != "unknown":
        label = f"{model_id} ({provider})"

    return {"id": model_id, "provider": provider, "label": label, "variant": variant}


def normalize_provider_model(provider: str, model_id: str) -> tuple[str, str]:
    """Recover a plugin provider encoded in a Codex model namespace."""
    provider_key = (provider or "unknown").strip().lower()
    model_key = (model_id or "unknown").strip()
    if "/" in model_key:
        namespace, namespaced_model = model_key.split("/", 1)
        if namespace in CODEX_MODEL_PROVIDER_NAMESPACES and namespaced_model:
            return namespace, namespaced_model
    return provider_key, model_key

QUALITATIVE_COLORS = [
    "#38BDF8",
    "#F59E0B",
    "#22C55E",
    "#8B5CF6",
    "#EC4899",
    "#14B8A6",
    "#F97316",
    "#64748B",
]

def chart_color(rank: int, model_id: str, provider: str) -> str:
    """Use rank-first colors so the chart adapts when model mix changes."""
    return QUALITATIVE_COLORS[rank % len(QUALITATIVE_COLORS)]

def pricing_model_resolution(provider: str, model_id: str) -> PricingResolution:
    """Resolve a local provider/model pair to a public pricing model ID."""
    if not model_id:
        return PricingResolution(None, "No local model ID available")

    provider_key = (provider or "unknown").strip().lower()
    model_key = model_id.strip()
    alias = PRICING_MODEL_ALIASES.get((provider_key, model_key))
    if alias:
        local_id = f"{provider_key}/{model_key}"
        return PricingResolution(alias, f"alias registry: {local_id} -> {alias}", True)

    free = model_key.endswith("-free")
    base = model_key.removesuffix("-free")

    if "/" in base and not free:
        return PricingResolution(base)

    if free:
        alias = FREE_SUFFIX_MODEL_ALIASES.get(base)
        if alias:
            local_id = f"{provider_key}/{model_key}"
            return PricingResolution(alias, f"alias registry: {local_id} -> {alias}", True)
        return PricingResolution(None, f"No matched pricing alias for free-suffixed model {provider_key}/{model_key}")

    namespace = PROVIDER_MODEL_NAMESPACES.get(provider_key)
    if namespace:
        return PricingResolution(f"{namespace}/{base}")

    for prefix, namespace in MODEL_PREFIX_NAMESPACES:
        if base.startswith(prefix):
            return PricingResolution(f"{namespace}/{base}")

    return PricingResolution(None, f"No matched pricing alias for {provider_key}/{model_key}")


def openrouter_model_id(provider: str, model_id: str) -> str | None:
    """Best-effort mapping from local provider/model IDs to OpenRouter model IDs."""
    return pricing_model_resolution(provider, model_id).model_id


def openrouter_model_url(model_id: str | None) -> str | None:
    """Return the public OpenRouter model page for a canonical model ID."""
    if not model_id:
        return None
    return f"{OPENROUTER_MODEL_PAGE_BASE}/{quote(model_id, safe='/:')}"


def _pricing_source(base_source: str, resolution: PricingResolution) -> str:
    if resolution.source and resolution.aliased:
        return f"{base_source}; {resolution.source}"
    return base_source

def openrouter_prices() -> dict:
    """Fetch public OpenRouter per-token pricing, cached for one hour."""
    now = time.time()
    if PRICING_CACHE["prices"] and now - PRICING_CACHE["fetched_at"] < 3600:
        return PRICING_CACHE["prices"]

    try:
        with urllib.request.urlopen(OPENROUTER_MODELS_URL, timeout=8) as response:
            payload = json.load(response)
        prices = {m.get("id"): m.get("pricing", {}) for m in payload.get("data", []) if m.get("id")}
        PRICING_CACHE.update({"fetched_at": now, "prices": prices})
        return prices
    except Exception:
        return PRICING_CACHE["prices"]

def estimate_cost(provider: str, model_id: str, tokens_input: int, tokens_output: int, cache_read: int = 0, cache_write: int = 0) -> dict:
    """Estimate USD cost from token counts using latest fetched OpenRouter pricing."""
    resolution = pricing_model_resolution(provider, model_id)
    router_id = resolution.model_id
    if router_id in UNPRICED_CANONICAL_MODEL_IDS:
        return {
            "estimated_cost": None,
            "pricing_status": "unpriced",
            "pricing_source": f"No trusted pricing configured for {router_id}",
            "pricing_model_id": router_id,
            "pricing_url": openrouter_model_url(router_id),
        }
    fallback_pricing = HARDCODED_MODEL_PRICES.get(router_id or "", {})
    fetched_pricing = openrouter_prices().get(router_id or "", {})
    official_pricing = OFFICIAL_MODEL_PRICES.get(router_id or "", {})
    pricing = {**fallback_pricing, **fetched_pricing, **official_pricing}

    def price(key: str) -> float:
        try:
            return float(pricing.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    if not pricing:
        pricing_source = resolution.source or (
            f"No matched public pricing for {router_id}" if router_id else "No matched public pricing"
        )
        return {
            "estimated_cost": None,
            "pricing_status": "unpriced",
            "pricing_source": pricing_source,
            "pricing_model_id": router_id,
            "pricing_url": openrouter_model_url(router_id),
        }

    input_price = price("prompt")
    output_price = price("completion")
    cache_read_price = price("input_cache_read")
    cache_write_price = price("input_cache_write")
    priced_components = [input_price, output_price, cache_read_price, cache_write_price]
    paid_model = any(component > 0 for component in priced_components)
    token_buckets = {
        "prompt": tokens_input or 0,
        "completion": tokens_output or 0,
        "input_cache_read": cache_read or 0,
        "input_cache_write": cache_write or 0,
    }
    missing_price_buckets = [
        bucket
        for bucket, tokens in token_buckets.items()
        if paid_model and tokens > 0 and price(bucket) <= 0
    ]

    estimated = (
        token_buckets["prompt"] * input_price
        + token_buckets["completion"] * output_price
        + token_buckets["input_cache_read"] * cache_read_price
        + token_buckets["input_cache_write"] * cache_write_price
    )
    cost_breakdown = {
        "input": token_buckets["prompt"] * input_price,
        "output": token_buckets["completion"] * output_price,
        "cache_read": token_buckets["input_cache_read"] * cache_read_price,
        "cache_write": token_buckets["input_cache_write"] * cache_write_price,
    }
    source = _pricing_source(
        "OpenAI official API pricing"
        if official_pricing
        else "OpenRouter /api/v1/models" if fetched_pricing else "Hardcoded pricing fallback",
        resolution,
    )
    result = {
        "estimated_cost": estimated,
        "pricing_status": "priced",
        "pricing_source": source,
        "pricing_model_id": router_id,
        "pricing_url": OPENAI_PRICING_URL if official_pricing else openrouter_model_url(router_id),
        "cost_basis": "api_equivalent_estimate",
        "cost_breakdown": cost_breakdown,
        "input_price": input_price,
        "output_price": output_price,
        "cache_read_price": cache_read_price,
        "cache_write_price": cache_write_price,
    }
    if missing_price_buckets:
        result.update({
            "estimated_cost": None,
            "pricing_status": "partial",
            "pricing_source": f"{source}; missing prices for {', '.join(missing_price_buckets)}",
            "partial_cost_usd": estimated,
            "missing_price_buckets": missing_price_buckets,
        })
    return result
