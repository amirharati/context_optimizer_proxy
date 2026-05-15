# Prompt Caching Granularity - How Cache Boundaries Work

Understanding cache granularity is crucial for designing effective compression strategies.

---

## The Answer: Token-Level Caching with Prefix Matching

### Key Concept: **Progressive Prefix Cache**

Caching works at the **token level**, but with a **prefix constraint**:

```
Cache Key = hash(token_1, token_2, token_3, ..., token_N)

The cache matches the LONGEST PREFIX of unchanged tokens.
```

### Example: How It Works Turn-by-Turn

**Turn 1:**
```
Tokens: [sys_1, sys_2, ..., sys_12000, user_1, user_2, ..., user_100]
Total: 12,100 tokens

Cache: MISS (nothing cached yet)
Action: Compute all tokens, store K,V for all 12,100 tokens
Cache entry created: hash(all 12,100 tokens) → K,V pairs
```

**Turn 2 (user sends new message):**
```
Tokens: [sys_1, sys_2, ..., sys_12000, user_1, ..., user_100, 
         assistant_1, ..., assistant_200, 
         user_101, ..., user_150]
Total: 12,450 tokens

Cache lookup:
  - Check: does prefix match cached tokens?
  - hash(token_1 to token_12,100) == cached hash? YES!
  
Cache: HIT for first 12,100 tokens
Action: 
  - Retrieve K,V for tokens 1-12,100 from cache
  - Only COMPUTE new tokens: 12,101-12,450 (350 new tokens)
  - EXTEND cache: store K,V for tokens 12,101-12,450
  
New cache entry: hash(all 12,450 tokens) → K,V pairs
```

**Turn 3 (user continues):**
```
Tokens: [sys_1, ..., sys_12000, user_1, ..., user_150, 
         assistant_201, ..., assistant_400,
         user_151, ..., user_200]
Total: 12,800 tokens

Cache lookup:
  - hash(token_1 to token_12,450) == cached hash? YES!
  
Cache: HIT for first 12,450 tokens
Action:
  - Retrieve K,V for tokens 1-12,450 from cache
  - Compute only tokens 12,451-12,800 (350 new tokens)
  - Extend cache
```

---

## What Happens When Content Changes?

### Scenario: You Compress Old Messages

**Original Turn 3:**
```
[system (12K), old_history (3K), new_messages (1K)]
Total: 16,000 tokens
Cache: 15,000 cached, 1,000 new
```

**Turn 4 WITH COMPRESSION:**
```
[system (12K), compressed_history (1K), new_messages (1K)]
Total: 14,000 tokens

Cache lookup:
  - hash(token_1 to token_12,000) == sys? YES! ✓
  - hash(token_12,001 to ...) == old_history? NO! ✗
  
Cache: PARTIAL HIT
  - Tokens 1-12,000 (system): CACHED ✓
  - Tokens 12,001+ (compressed history): MISS ✗
  
Action:
  - Retrieve K,V for system prompt (12K tokens)
  - RECOMPUTE compressed history (1K tokens)
  - RECOMPUTE new messages (1K tokens)
  - Store new cache entry
```

### The Cache Boundary Problem

```
┌─────────────────────────────────────────────────────┐
│ System Prompt (12,000 tokens)                       │ ← CACHED
│ "You are an AI assistant... [tool definitions]..."  │    (unchanged)
├─────────────────────────────────────────────────────┤
│ Old History (3,000 tokens)                          │ ← CACHE MISS!
│ [Many user/assistant exchanges]                     │    (changed by compression)
├─────────────────────────────────────────────────────┤
│ New Messages (1,000 tokens)                         │ ← Must recompute
│ [Latest exchanges]                                  │    (new anyway)
└─────────────────────────────────────────────────────┘

Cache effectiveness: 12K cached / 16K total = 75%
```

---

## Critical Insight for Our Compression Strategy

### The Tradeoff

**Compression breaks cache continuity!**

1. **Without compression:**
   - Turn 4: 16K tokens, 15K cached (94% cache hit)
   - Cost: 15K × $0.30/M + 1K × $3/M = $0.0045 + $0.003 = $0.0075

2. **With naive compression:**
   - Turn 4: 14K tokens, 12K cached (86% cache hit)
   - Cost: 12K × $0.30/M + 2K × $3/M = $0.0036 + $0.006 = $0.0096
   - **WORSE!** Compression increased cost!

### The Solution: Cache-Aware Compression

**Strategy:** Only compress BELOW stable cache boundaries

```
Turn 4 structure:
┌─────────────────────────────────────────────────────┐
│ System Prompt (12K tokens)                          │ ← NEVER compress
│                                                      │    (always cached)
├─────────────────────────────────────────────────────┤
│ Turn 1-10 History (3K tokens)                       │ ← Compress ONCE
│ [user: build calculator]                            │    then keep stable
│ [assistant: scaffold files...]                      │    (new cache boundary)
│ [tool results...]                                   │
├─────────────────────────────────────────────────────┤
│ Turn 11-15 Recent (500 tokens)                      │ ← Keep verbatim
│ [Last few exchanges]                                │    (might change)
├─────────────────────────────────────────────────────┤
│ Turn 16 New (500 tokens)                            │ ← New content
│ [Current exchange]                                  │    (must compute)
└─────────────────────────────────────────────────────┘

Cache plan:
- System (12K): cached from turn 1 ✓
- Compressed history (1K): cache once, then stable ✓
- Recent (500): cache once, then stable ✓
- New (500): recompute each turn ✓

Cache hit rate: 13.5K / 14K = 96%
```

---

## Cache Invalidation Patterns

### Pattern 1: Append-Only (Best for Caching)

```
Turn N:   [A, B, C, D]
Turn N+1: [A, B, C, D, E, F]  ← Only append
          └─────────┘ cached
                      └───┘ new

Cache: 100% hit rate on old content
```

### Pattern 2: Compress Once, Then Stable

```
Turn N:   [A, B, C, D, E, F, G, H]  (8K tokens)
Turn N+1: [A, B, C, X, Y, Z]        (6K tokens, compressed D-H → X,Y,Z)
          └─────┘ cached
                  └─────┘ recompute (one-time cost)

Turn N+2: [A, B, C, X, Y, Z, new]
          └─────────────┘ cached!
                          └──┘ new

Cache: After one-time recompute, back to high hit rate
```

### Pattern 3: Rolling Compression (BAD!)

```
Turn N:   [A, B, C, D, E, F]
Turn N+1: [A, B, C, X, Y]     ← Compress D-F → X,Y
          └─────┘ cached
                  └───┘ recompute

Turn N+2: [A, B, C, X, Z]     ← Compress Y differently!
          └─────────┘ miss!
                      └ recompute

Cache: Constantly invalidating! Very expensive!
```

---

## Anthropic's Cache Control: Explicit Boundaries

Anthropic lets you **explicitly mark** cache boundaries:

```json
{
  "system": [
    {
      "type": "text",
      "text": "System prompt (12K tokens)",
      "cache_control": {"type": "ephemeral"}  ← Cache boundary 1
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Compressed old history (1K)",
          "cache_control": {"type": "ephemeral"}  ← Cache boundary 2
        }
      ]
    },
    {
      "role": "assistant",
      "content": "..."
    },
    {
      "role": "user",
      "content": "New message (no cache control)"
    }
  ]
}
```

### How Multiple Boundaries Work

You can have **up to 4 cache breakpoints**:

```
Request structure:
┌─────────────────────────────────────────┐
│ System (12K)     [cache_control: 1]     │ ← Boundary 1
├─────────────────────────────────────────┤
│ Tools (3K)       [cache_control: 2]     │ ← Boundary 2
├─────────────────────────────────────────┤
│ Old history (2K) [cache_control: 3]     │ ← Boundary 3
├─────────────────────────────────────────┤
│ Recent (1K)      [cache_control: 4]     │ ← Boundary 4
├─────────────────────────────────────────┤
│ New (500)        [no cache control]     │ ← Not cached
└─────────────────────────────────────────┘

Cache behavior:
- If system unchanged: boundary 1 cached
- If system+tools unchanged: boundaries 1+2 cached
- If all old content unchanged: boundaries 1+2+3+4 cached
- New content always recomputed
```

---

## Optimal Compression Strategy (Cache-Aware)

### Phase 1: Establish Cache Boundaries

**Turn 1-5:** Build up conversation, no compression
```
Cache grows: 12K → 13K → 14K → 15K → 16K
All tokens progressively cached
```

### Phase 2: Compress Historical Layers

**Turn 6:** First compression (system prompt hit threshold)
```
Before: [system (12K), history (4K)]
After:  [system (12K), compressed (1.5K)]

Cache: 
- System (12K): cached ✓
- Compressed (1.5K): new entry (one-time cost)

Next turn:
- System (12K): cached ✓
- Compressed (1.5K): NOW cached! ✓
```

### Phase 3: Layered Compression

**Turn 10:** Old history compressible again
```
Structure:
[system (12K) - cached,
 compressed_old (1.5K) - cached,
 recent (2K) - keep verbatim,
 new (500) - new]

Cost: 13.5K cached + 2.5K new
```

**Turn 15:** Compress middle layer
```
Structure:
[system (12K) - cached,
 compressed_old (1.5K) - cached,
 compressed_mid (800) - recompute once, then cached,
 recent (1K) - keep,
 new (500) - new]

Cost: 14.3K cached + 1.5K new (after one turn)
```

---

## Recommendation for Our Proxy

### Compress in Stable Layers

```python
def cache_aware_compression(messages, turn_number):
    """
    Compress only when we can establish stable cache boundaries
    """
    layers = [
        # Layer 1: System prompt (never compress, always cached)
        messages[0],  # system message
        
        # Layer 2: Old history (compress once at turn 10, then stable)
        compress_if_needed(messages[1:first_old_boundary], turn_number >= 10),
        
        # Layer 3: Medium history (compress at turn 20, then stable)
        compress_if_needed(messages[first_old_boundary:recent_boundary], 
                           turn_number >= 20),
        
        # Layer 4: Recent history (keep verbatim for caching)
        messages[recent_boundary:-3],  # Last 3-5 turns verbatim
        
        # Layer 5: New content (always new, never cached)
        messages[-3:],  # Latest exchanges
    ]
    
    return flatten(layers)
```

### Rules:

1. **Never compress system prompt** - always cached
2. **Compress old history ONCE** - then keep stable (becomes cached)
3. **Don't recompress** - breaks cache
4. **Keep recent turns verbatim** - will be cached soon
5. **Accept new content cost** - unavoidable

### Expected Cache Performance

```
Turn 1-9:   No compression, cache builds (90%+ hit rate)
Turn 10:    Compress old history (60% hit rate this turn only)
Turn 11+:   Back to 90%+ hit rate (compressed version now cached)
Turn 20:    Compress medium history (70% hit rate this turn)
Turn 21+:   Back to 90%+ hit rate

Overall: 85-90% average cache hit rate with compression
Without compression: 90-95% cache hit rate but higher total tokens
```

### The Math

**With cache-aware compression (20 turns):**
- Avg 14K tokens/turn × 20 = 280K total
- 85% cached = 238K × $0.30/M = $0.071
- 15% new = 42K × $3/M = $0.126
- **Total: $0.197**

**Without compression (20 turns):**
- Avg 18K tokens/turn × 20 = 360K total  
- 92% cached = 331K × $0.30/M = $0.099
- 8% new = 29K × $3/M = $0.087
- **Total: $0.186**

Hmm, without compression is actually cheaper here! But...

**With better compression + caching (20 turns):**
- Avg 12K tokens/turn × 20 = 240K total (better compression)
- 88% cached = 211K × $0.30/M = $0.063
- 12% new = 29K × $3/M = $0.087
- **Total: $0.150** ← 20% savings!

---

## Summary: Cache Granularity

| Question | Answer |
|----------|--------|
| **Cache granularity?** | Token-level with prefix matching |
| **One entry or multiple?** | Progressive prefix cache (extends automatically) |
| **Compression breaks cache?** | YES - any change in prefix invalidates cache from that point |
| **How to handle?** | Compress in stable layers, don't recompress |
| **Explicit boundaries?** | Anthropic: up to 4 cache_control markers |
| **Best strategy?** | Compress once per layer, keep stable, high cache hit rate |

**Bottom line:** Cache works progressively on token prefixes. Compression must create NEW stable boundaries that won't change, allowing the cache to rebuild and stay effective.
