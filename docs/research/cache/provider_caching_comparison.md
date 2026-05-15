# Provider Caching Comparison

Understanding how different LLM providers handle prompt caching - critical for compression strategy.

---

## Summary Table

| Provider | Cache Support | Control | TTL | Read Cost | Write Cost | Passthrough | Our Strategy |
|----------|---------------|---------|-----|-----------|------------|-------------|--------------|
| **Anthropic (direct)** | ✅ Excellent | Explicit markers | 5 min | $0.30/M | $3.75/M | N/A | Cache-aware compression |
| **OpenAI (direct)** | ✅ Good | Automatic | ~5-10 min | ~$0.50/M | ~$5/M | N/A | Cache-friendly compression |
| **Google Gemini** | ✅ Yes | Automatic | ~5 min | Varies | Varies | N/A | Cache-friendly compression |
| **OpenRouter** | ❌ NO | None | N/A | Full price | Full price | No | Aggressive compression |
| **AWS Bedrock** | ✅ Yes | Provider-dependent | Varies | Provider pricing | Provider pricing | Yes | Follow upstream provider |
| **Azure OpenAI** | ✅ Yes | Automatic | ~10 min | Similar to OpenAI | Similar to OpenAI | Yes | Cache-friendly compression |

---

## Anthropic (Claude) - BEST for Caching

### Cache Implementation

**Explicit control via `cache_control` markers:**

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "system": [
    {
      "type": "text",
      "text": "System prompt...",
      "cache_control": {"type": "ephemeral"}
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Old conversation...",
          "cache_control": {"type": "ephemeral"}
        }
      ]
    }
  ]
}
```

### Pricing (as of 2024-2026)

**Claude 3.5 Sonnet:**
- Input: $3/M tokens
- Output: $15/M tokens
- **Cache write:** $3.75/M (25% premium)
- **Cache read:** $0.30/M (90% discount!)

**Claude 3 Opus:**
- Input: $15/M tokens
- Output: $75/M tokens
- **Cache write:** $18.75/M
- **Cache read:** $1.50/M (90% discount)

### Features

- ✅ Up to 4 cache breakpoints
- ✅ Explicit boundary control
- ✅ TTL: 5 minutes from last use
- ✅ Per-boundary caching
- ✅ Excellent documentation

### For Our Proxy

**Strategy:** Cache-aware compression with explicit boundaries

```python
# Mark compression boundaries
def apply_anthropic_cache_boundaries(messages):
    boundaries = [
        (0, "system"),
        (20, "old_compressed"),
        (35, "mid_compressed"),
        (50, "recent")
    ]
    
    for idx, name in boundaries:
        messages[idx]["content"][-1]["cache_control"] = {
            "type": "ephemeral"
        }
    
    return messages
```

**Cost impact:** Compression + caching = 90-95% cost reduction

---

## OpenAI (GPT) - GOOD Caching (Less Control)

### Cache Implementation

**Automatic** - no explicit control:

```json
{
  "model": "gpt-4-turbo",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ]
}
```

OpenAI automatically caches repeated prompt prefixes.

### Pricing (as of 2024-2026)

**GPT-4 Turbo:**
- Input: $10/M tokens
- Output: $30/M tokens
- **Cached input:** ~$5/M (50% discount, estimated)

**GPT-4o:**
- Input: $5/M tokens
- Output: $15/M tokens
- **Cached input:** ~$2.50/M (50% discount, estimated)

**Note:** OpenAI doesn't publicly document cache pricing clearly. Estimates based on observed billing.

### Features

- ✅ Automatic caching (no setup needed)
- ❌ No explicit boundary control
- ⚠️ TTL: ~5-10 minutes (not documented)
- ⚠️ Cache behavior not fully documented
- ❌ Can't control what gets cached

### For Our Proxy

**Strategy:** Cache-friendly compression (assume automatic caching)

```python
# No explicit markers, but compress in stable layers
def openai_friendly_compression(messages):
    # Keep system prompt stable (likely cached)
    # Compress old messages in batches
    # Keep recent messages verbatim
    # Don't constantly recompress
    pass
```

**Cost impact:** Compression + automatic caching = 60-80% cost reduction (less than Anthropic)

---

## Google Gemini - Automatic Caching

### Cache Implementation

**Automatic context caching:**

```json
{
  "model": "gemini-1.5-pro",
  "contents": [
    {"role": "user", "parts": [{"text": "..."}]}
  ]
}
```

Google automatically caches conversation context.

### Pricing (as of 2024-2026)

**Gemini 1.5 Pro:**
- Input: $1.25/M tokens (<128K)
- Input: $2.50/M tokens (>128K)
- Output: $5/M tokens
- **Cached input:** $0.125/M (90% discount for <128K)

**Gemini 1.5 Flash:**
- Input: $0.075/M tokens
- Output: $0.30/M tokens
- **Cached input:** ~$0.01/M (estimated)

### Features

- ✅ Automatic caching
- ✅ Very cheap pricing
- ❌ No explicit control
- ⚠️ TTL: ~5 minutes (not documented)
- ✅ Works well with large contexts

### For Our Proxy

**Strategy:** Cache-friendly compression

**Cost impact:** Already very cheap, compression helps with context window limits more than cost

---

## OpenRouter - NO Caching Passthrough (CRITICAL!)

### Cache Implementation

**NONE** - OpenRouter does NOT pass through provider caching:

```json
{
  "model": "anthropic/claude-3.5-sonnet",  // Via OpenRouter
  "messages": [...]
}
```

Even if you request `anthropic/claude-3.5-sonnet` through OpenRouter, **cache_control markers are ignored or stripped**.

### Pricing

OpenRouter charges provider rates + small markup:
- No cache discount
- Every token costs full price
- Even repeated content = full price

### Features

- ❌ No caching (even for providers that support it)
- ❌ `cache_control` markers stripped/ignored
- ❌ All tokens billed at full input rate
- ✅ Unified API across providers (convenience)
- ✅ Often better model availability

### For Our Proxy

**Strategy:** AGGRESSIVE compression (caching doesn't help)

```python
# If using OpenRouter:
# - Compress early and often
# - No cache to preserve
# - Focus on token reduction only
# - Don't worry about cache boundaries

if provider == "openrouter":
    strategy = "aggressive_compression"  # No cache considerations
else:
    strategy = "cache_aware_compression"  # Preserve cache
```

**Cost impact:** Compression is CRITICAL (no caching safety net)

**Recommendation:** Use Anthropic/OpenAI direct instead of OpenRouter if cost is priority.

---

## AWS Bedrock - Provider Passthrough

### Cache Implementation

Depends on underlying provider:
- Claude via Bedrock → Anthropic caching
- Titan → AWS caching (limited)

### Pricing

Follows provider pricing, including cache discounts (when available).

### For Our Proxy

**Strategy:** Depends on model used

- If Claude: Same as Anthropic direct
- If others: Check AWS docs for that model

---

## Azure OpenAI - Enterprise Caching

### Cache Implementation

Similar to OpenAI, with enterprise features:
- Automatic caching
- Longer TTL (~10 minutes)
- Better for high-throughput scenarios

### Pricing

Similar to OpenAI pricing, with enterprise contracts.

### For Our Proxy

**Strategy:** Same as OpenAI (cache-friendly compression)

---

## Comparison: Coffee Break Impact

**Scenario:** 20 turns, then 10-minute break, then 10 more turns

### Anthropic (5-min TTL, explicit cache)

```
Turns 1-20: All cached after turn 1
[10 min break - cache expires]
Turn 21: Full recompute (cache write)
Turns 22-30: All cached again

Cost: 2 cache writes + 28 cache reads
```

### OpenAI (longer TTL)

```
Turns 1-20: Automatically cached
[10 min break - might still be cached]
Turn 21: Possibly still cached!
Turns 22-30: Cached

Cost: 1-2 cache writes + 28-29 cache reads
```

### OpenRouter (no cache)

```
Turns 1-20: Full price every turn
[10 min break]
Turn 21: Full price
Turns 22-30: Full price

Cost: 30 full-price inputs
```

**Cost difference: 10-20× more expensive with OpenRouter!**

---

## Routing Considerations

### Model Family Switching

**Question:** Does switching models break cache?

**Answer:** Depends on provider

| Switch | Anthropic | OpenAI | Impact |
|--------|-----------|--------|--------|
| Claude 3.5 Sonnet → Claude 3 Opus | ✗ Different cache | ✗ Different cache | Full rebuild |
| GPT-4 Turbo → GPT-4o | ✗ Different cache | ✗ Different cache | Full rebuild |
| GPT-4o → GPT-4o-mini | ⚠️ Might share | ⚠️ Might share | Test needed |
| Same model, different endpoint | ✓ Same cache | ✓ Same cache | Cache preserved |

**For our proxy routing strategy:**
- **Avoid switching model families** (kills cache)
- **Stick to same family** (GPT-4o variants, Claude 3.5 variants)
- **If must switch:** Do it at natural boundaries (new session, after compression)

### Cost Example: Routing Gone Wrong

```
Turn 1-10: GPT-4o (cheap tier) → Cache builds
Turn 11: Route to GPT-4 Turbo (medium tier)
  → Cache miss! Full recompute
  → Extra cost: $0.05
Turn 12-20: GPT-4 Turbo → Cache rebuilds
Turn 21: Route back to GPT-4o (task easier)
  → Cache miss! Full recompute again
  → Extra cost: $0.03

Total extra cost from routing: $0.08
```

**Solution:** Minimize model switches, or switch only when cost justifies cache rebuild.

---

## Recommendations for Our Proxy

### If Using Anthropic Direct ✅ BEST

1. Use explicit `cache_control` markers
2. Implement 4-boundary strategy
3. Compress once per boundary, then freeze
4. Monitor cache hit rate (target >85%)
5. Expected savings: 90-95%

### If Using OpenAI Direct ✅ GOOD

1. Compress in stable layers
2. Assume automatic caching
3. Don't recompress constantly
4. Expected savings: 60-80%

### If Using OpenRouter ⚠️ NO CACHE

1. Aggressive compression (no cache to preserve)
2. Focus purely on token reduction
3. Consider switching to direct provider for cost
4. Expected savings: 40-60% (compression only)

### If Using Gemini ✅ GOOD

1. Already very cheap
2. Compression helps context limits
3. Cache-friendly compression
4. Expected savings: 50-70%

---

## Provider Switching Strategy

If our proxy supports multiple providers:

```python
def get_compression_strategy(provider: str, model: str):
    """
    Return appropriate compression strategy for provider
    """
    if provider == "anthropic":
        return {
            "type": "cache_aware_boundaries",
            "boundaries": 4,
            "markers": True,
            "recompress": False  # Preserve cache
        }
    
    elif provider == "openai":
        return {
            "type": "cache_friendly_layers",
            "boundaries": "auto",
            "markers": False,
            "recompress": False
        }
    
    elif provider == "openrouter":
        return {
            "type": "aggressive_compression",
            "boundaries": 1,
            "markers": False,
            "recompress": True  # No cache to break
        }
    
    else:
        return {
            "type": "conservative",  # Unknown provider
            "boundaries": 2,
            "markers": False,
            "recompress": False
        }
```

---

## Summary: Provider Impact on Strategy

| Provider | Cache Quality | Compression Approach | Priority |
|----------|---------------|----------------------|----------|
| Anthropic | ⭐⭐⭐⭐⭐ | Cache-aware boundaries | Maximize cache hit rate |
| OpenAI | ⭐⭐⭐⭐ | Cache-friendly layers | Balance cache + compression |
| Gemini | ⭐⭐⭐⭐ | Cache-friendly | Context limits > cost |
| OpenRouter | ⭐ | Aggressive token reduction | Minimize tokens |

**Final recommendation:** Use Anthropic direct or OpenAI direct for best cost optimization. Avoid OpenRouter for cost-sensitive workloads (use for convenience/availability only).
