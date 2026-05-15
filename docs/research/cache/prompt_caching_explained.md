# Prompt Caching - Engineering Perspective

Understanding why cached tokens are 90% cheaper from a technical standpoint.

---

## How Transformers Process Text

### Without Caching (Normal Processing)

When an LLM processes your prompt, here's what happens at each transformer layer:

```
Input tokens: [system, user, history...] → 15,000 tokens

Layer 1:
  For each token:
    1. Compute Query (Q) vector
    2. Compute Key (K) vector  
    3. Compute Value (V) vector
    4. Attention: Q × all K's → attention weights
    5. Weighted sum of all V's → output
    
Layer 2:
  For each token:
    (same process with Layer 1 outputs)
    
...

Layer 80 (for Claude):
  For each token:
    (same process)
```

**Key Point:** Each token must compute attention with ALL previous tokens at EVERY layer.

**Computational Cost:**
- 15,000 tokens
- × 80 layers
- × attention computation (O(n²) with sequence length)
- = Millions of operations

---

## What Gets Cached: KV Cache

The breakthrough: **Key-Value (KV) Cache**

### The Insight

For tokens that don't change between requests (like your system prompt), the intermediate representations are IDENTICAL:

```
System prompt: "You are an AI assistant..."

Turn 1 - Compute from scratch:
  Layer 1: token_1 → K₁, V₁
           token_2 → K₂, V₂
           ...
  Layer 2: token_1 → K₁, V₁
           ...
  (Store K, V for all layers)

Turn 2 - Same system prompt:
  Instead of recomputing:
    - Retrieve stored K₁, V₁, K₂, V₂, ... from cache
    - Skip all computation for these tokens
    - Only compute K, V for NEW tokens
```

### What's Actually Cached

```
Cached representation (per layer, per token):
┌─────────────────────────────────────────┐
│ Token: "You"                            │
│ Layer 1: K vector (4096 dims)           │
│          V vector (4096 dims)           │
│ Layer 2: K vector (4096 dims)           │
│          V vector (4096 dims)           │
│ ...                                     │
│ Layer 80: K vector, V vector           │
└─────────────────────────────────────────┘
```

**Size per token:** ~80 layers × 2 vectors × 4096 dims × 2 bytes = ~1.3 MB

For 12,000 cached tokens: ~15 GB of cache storage (stored in GPU memory)

---

## Why It's Cheaper: Computational Cost

### Cost Breakdown (Claude-3.5 Sonnet, 15K token prompt)

**Without Cache (Turn 1):**

```
Compute required:
- Forward pass through 80 layers
- 15,000 tokens × 80 layers = 1.2M layer computations
- Each layer: attention (O(n²)) + FFN operations
- Total FLOPs: ~10¹⁵ operations
- GPU time: ~500ms
- Energy: ~50 watt-seconds
```

**With Cache (Turn 2, 12K cached + 3K new):**

```
Cached tokens (12,000):
- No computation needed (K, V retrieved from memory)
- Memory read: ~15 GB from GPU RAM
- GPU time: ~50ms (just memory access)
- Energy: ~5 watt-seconds

New tokens (3,000):
- Full computation required
- 3,000 × 80 = 240K layer computations
- GPU time: ~100ms
- Energy: ~10 watt-seconds

Total: 150ms, 15 watt-seconds
Savings: 70% time, 70% energy!
```

### Why Providers Charge Less

**Direct costs saved:**

1. **GPU compute cycles:** 70% fewer FLOPs
2. **Energy:** 70% less electricity
3. **Time:** 70% faster → higher throughput per GPU

**Provider can:**
- Serve 3x more requests per GPU
- Pay 70% less electricity per request
- Amortize GPU cost over 3x more requests

**Result:** 90% discount on cached tokens is still PROFITABLE for the provider!

---

## Attention Computation Details

### Without Cache

```python
# For token at position i (e.g., position 15,000)
# Must compute attention with ALL previous tokens

Q_i = W_q @ token_i  # Query for new token

# Attend to ALL previous tokens (no cache)
for j in range(15000):
    K_j = W_k @ token_j      # Compute key (expensive!)
    V_j = W_v @ token_j      # Compute value (expensive!)
    attention_weight = Q_i · K_j
    
output = Σ(attention_weight_j × V_j)

# This happens at EVERY layer!
```

**Cost:** O(n) computation per previous token × n tokens = O(n²)

### With Cache

```python
# For token at position i (position 15,000)
Q_i = W_q @ token_i  # Query for new token

# First 12,000 tokens: retrieve from cache (cheap!)
cached_K = retrieve_from_cache(layer_id, token_range=(0, 12000))
cached_V = retrieve_from_cache(layer_id, token_range=(0, 12000))

# Only compute for last 3,000 NEW tokens
for j in range(12000, 15000):
    K_j = W_k @ token_j      # Only 3K computations
    V_j = W_v @ token_j
    
# Attention uses both cached and new K, V
all_K = concat(cached_K, new_K)
all_V = concat(cached_V, new_V)
attention_weights = softmax(Q_i @ all_K)
output = attention_weights @ all_V
```

**Cost:** O(1) cache retrieval for 12K + O(n) for 3K = 80% savings!

---

## Memory vs. Computation Trade-off

### Storage Requirements

**Per request cache:**
- 12,000 tokens × 1.3 MB/token = ~15 GB
- Stored in GPU HBM (high-bandwidth memory)
- 5-minute TTL

**Provider infrastructure:**
- A100 GPU: 80 GB HBM
- Can cache ~5 concurrent sessions
- $1.50/hour per GPU
- Cost per 5 minutes: $0.125

**Economics:**
- Without cache: 1 request uses GPU for 500ms → 120 req/min
- With cache: 1 request uses GPU for 150ms → 400 req/min
- Cache storage cost: $0.125 per 5min = $0.025/request
- Compute savings: $0.15/request

**Net savings: $0.125/request (80% reduction)**

---

## Why 5-Minute TTL?

**Balance between:**

1. **Hit rate:** Most multi-turn conversations happen within 5 minutes
2. **Memory pressure:** GPU memory is limited (80 GB)
3. **Complexity:** Longer TTL requires more sophisticated eviction policies

**Typical session patterns:**
- User sends message → model responds (20s)
- User reads response, thinks, types (60s)
- Next message arrives: 80s total

**Within 5 minutes:** 3-4 back-and-forth exchanges
**Cache hit rate:** ~80% for typical sessions

---

## Cache Invalidation

### When Cache Is Invalid

Cache is tied to **exact content match**:

```
Turn 1: [system: "...", user: "Build calculator"]
  → Compute all K, V
  → Store in cache with hash: abc123

Turn 2: [system: "...", user: "Build calculator", assistant: "...", user: "..."]
  → Cache lookup: hash(first N tokens)
  → Match! Use cached K, V for system + first user message
  → Only compute new tokens

Turn 3: [NEW system prompt] ← Content changed!
  → Cache miss
  → Recompute from scratch
  → Store NEW cache
```

**Key:** Even 1 character change invalidates the cache for that token onward.

---

## Implementation in Anthropic's API

### How to Use Prompt Caching

**Mark cacheable blocks in the request:**

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 1024,
  "system": [
    {
      "type": "text",
      "text": "You are an AI assistant...",
      "cache_control": {"type": "ephemeral"}  ← Mark for caching
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text", 
          "text": "Build a calculator",
          "cache_control": {"type": "ephemeral"}  ← Mark previous turns
        }
      ]
    }
  ]
}
```

**Response includes cache stats:**

```json
{
  "usage": {
    "input_tokens": 15000,
    "cache_creation_input_tokens": 12000,  ← Wrote to cache (turn 1)
    "cache_read_input_tokens": 0,
    "output_tokens": 500
  }
}
```

**Next request:**

```json
{
  "usage": {
    "input_tokens": 16000,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 12000,  ← Read from cache! (90% cheaper)
    "output_tokens": 600
  }
}
```

---

## Why This Is Revolutionary

### Before Prompt Caching (2023)

Every token costs the same: $3/M input tokens
- Turn 1:  15K tokens = $0.045
- Turn 2:  16K tokens = $0.048
- Turn 10: 25K tokens = $0.075
- **Total: $0.50+ for 10 turns**

### After Prompt Caching (2024)

Repeated tokens cost 90% less: $0.30/M cached tokens
- Turn 1:  15K new = $0.045
- Turn 2:  12K cached + 4K new = $0.0036 + $0.012 = $0.016
- Turn 10: 20K cached + 5K new = $0.006 + $0.015 = $0.021
- **Total: $0.15 for 10 turns (70% savings!)**

---

## Our Proxy Can Leverage This

### Automatic Cache Optimization

```python
# In main.py, before forwarding to Anthropic
def optimize_for_caching(messages):
    """
    Add cache_control markers to maximize caching benefits
    """
    # Mark system prompt as cacheable (always the same)
    if "system" in body:
        body["system"] = [
            {"type": "text", "text": body["system"], 
             "cache_control": {"type": "ephemeral"}}
        ]
    
    # Mark old conversation as cacheable (doesn't change)
    # Keep last N messages uncached (might change with compression)
    for i, msg in enumerate(messages[:-3]):  # All but last 3
        if isinstance(msg.get("content"), str):
            msg["content"] = [
                {"type": "text", "text": msg["content"],
                 "cache_control": {"type": "ephemeral"}}
            ]
    
    return messages
```

**Combined with compression:**
- Compress 15K → 8K tokens
- Cache the 8K (smaller cache footprint)
- Cache read on 6K + compute on 2K new
- **95%+ cost reduction!**

---

## Summary: Why Cached Tokens Are Cheaper

| Aspect | Without Cache | With Cache | Savings |
|--------|---------------|------------|---------|
| **Computation** | Full forward pass | Memory read only | 90% fewer FLOPs |
| **Time** | 500ms | 150ms | 70% faster |
| **Energy** | 50 watt-seconds | 15 watt-seconds | 70% less power |
| **Throughput** | 120 req/min per GPU | 400 req/min per GPU | 3.3× more requests |
| **Cost to provider** | $0.025/request | $0.008/request | 68% cheaper |
| **Price to user** | $3/M tokens | $0.30/M tokens | 90% discount |

**Engineering bottom line:** Cached tokens avoid expensive GPU computation by reusing pre-computed intermediate representations (Key-Value pairs from attention layers), making them 10× cheaper to serve while maintaining quality.
