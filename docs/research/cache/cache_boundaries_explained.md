# Cache Boundaries (Breakpoints) - The Key to Multi-Layer Caching

Understanding cache boundaries is the KEY to compression without losing cache benefits.

---

## The Problem Without Boundaries

### Single Cache Entry (No Boundaries)

```
Turn N: [system, old_history, recent, new]
        └──────────────────────────────┘
        One big cache entry (all or nothing)

Turn N+1: Compress old_history
        [system, compressed_old, recent, new]
        └────────────────────────────────┘
        Entire cache INVALID! Must recompute ALL
```

**Result:** Any change anywhere invalidates the ENTIRE cache.

---

## The Solution: Multiple Cache Boundaries

### What Is a Cache Boundary?

A **cache boundary** creates a **separate cache entry** for each section:

```
Turn N:
┌─────────────────────┐
│ System prompt       │ ← Cache Entry #1
├─────────────────────┤ ← BOUNDARY
│ Old history         │ ← Cache Entry #2
├─────────────────────┤ ← BOUNDARY
│ Recent messages     │ ← Cache Entry #3
├─────────────────────┤ ← BOUNDARY
│ New message         │ ← Not cached yet
└─────────────────────┘
```

**Key insight:** Each boundary creates an **independent cache entry**.

---

## How It Works: Multiple Entries

### Example with 3 Boundaries

**Turn 10:**

```json
{
  "system": [
    {
      "type": "text",
      "text": "You are an AI assistant... [12K tokens]",
      "cache_control": {"type": "ephemeral"}  ← Boundary 1
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Old history [turns 1-5]: ... [3K tokens]",
          "cache_control": {"type": "ephemeral"}  ← Boundary 2
        }
      ]
    },
    {
      "role": "assistant",
      "content": "..." 
    },
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Recent history [turns 6-9]: ... [2K tokens]",
          "cache_control": {"type": "ephemeral"}  ← Boundary 3
        }
      ]
    },
    {
      "role": "assistant",
      "content": "..."
    },
    {
      "role": "user",
      "content": "New message [turn 10]"  ← No boundary (new)
    }
  ]
}
```

**This creates 3 separate cache entries:**

```
Cache Entry #1: hash(system) → K,V for 12K tokens
Cache Entry #2: hash(old_history) → K,V for 3K tokens  
Cache Entry #3: hash(recent_history) → K,V for 2K tokens
```

---

## The Magic: Partial Cache Invalidation

### Turn 11: Compress Only Old History

```
Change: Compress old history 3K → 1K tokens
Keep: System and recent unchanged

Request:
┌─────────────────────┐
│ System (12K)        │ ← Same content
│ [boundary 1]        │ ← Cache Entry #1: HIT ✓
├─────────────────────┤
│ Compressed old (1K) │ ← Different content!
│ [boundary 2]        │ ← Cache Entry #2: MISS ✗
├─────────────────────┤
│ Recent (2K)         │ ← Same content
│ [boundary 3]        │ ← Cache Entry #3: HIT ✓
├─────────────────────┤
│ New message         │ ← New
└─────────────────────┘

Cache result:
✓ Entry #1 (system): Retrieved from cache (12K cached)
✗ Entry #2 (old): Recompute (1K new computation)
✓ Entry #3 (recent): Retrieved from cache (2K cached)
  New: Compute (500 tokens)

Total: 14K cached + 1.5K computed
```

**Without boundaries:** Would recompute entire 15.5K tokens!
**With boundaries:** Only recompute 1.5K tokens!

---

## Progressive Freezing Strategy

### The Workflow

**Phase 1: Build cache (turns 1-9)**

```
Turn 1: [system] → Cache Entry #1 created
Turn 5: [system, history] → Entry #1 cached, growing history
Turn 9: [system, history (5K)] → Entry #1 cached, history uncached
```

**Phase 2: First compression (turn 10)**

```
Turn 10: Create boundaries
  [system [B1], old [B2], recent [B3], new]
  
Cache:
  Entry #1: system ✓ (cached since turn 1)
  Entry #2: old ✗ (first time seeing this boundary)
  Entry #3: recent ✗ (first time)
```

**Phase 3: Boundaries stabilize (turn 11+)**

```
Turn 11: [system [B1], old [B2], recent [B3], new]
         Same boundaries, only "new" section changes
         
Cache:
  Entry #1: system ✓ (cached)
  Entry #2: old ✓ (NOW cached!)
  Entry #3: recent ✓ (NOW cached!)
  
Only compute: new section
```

**Phase 4: Compress middle layer (turn 20)**

```
Turn 20: Compress recent history
  [system [B1], old [B2], compressed_mid [B3], very_recent [B4], new]
  
Cache:
  Entry #1: system ✓ (cached)
  Entry #2: old ✓ (cached)
  Entry #3: compressed_mid ✗ (changed! recompute once)
  Entry #4: very_recent ✗ (new boundary)
```

**Phase 5: Stable again (turn 21+)**

```
Turn 21+: All boundaries stable
  [system [B1], old [B2], compressed_mid [B3], very_recent [B4], new]
  
Cache:
  Entry #1: system ✓
  Entry #2: old ✓
  Entry #3: compressed_mid ✓ (NOW cached!)
  Entry #4: very_recent ✓ (NOW cached!)
  
Only new section recomputed each turn
```

---

## Anthropic's Limit: 4 Boundaries

Anthropic allows **up to 4 cache_control markers**:

```
Structure:
┌─────────────────────┐
│ System              │ ← Boundary 1 (12K tokens)
├─────────────────────┤
│ Tools/Rules         │ ← Boundary 2 (3K tokens)
├─────────────────────┤
│ Old history         │ ← Boundary 3 (2K tokens)
├─────────────────────┤
│ Recent history      │ ← Boundary 4 (1K tokens)
├─────────────────────┤
│ New messages        │ ← No boundary (always new)
└─────────────────────┘

Cache entries created: 4 independent entries
```

### Why 4? Engineering Tradeoff

**Benefits of more boundaries:**
- More granular control
- Less recomputation when changing content

**Costs of more boundaries:**
- More cache lookups (latency)
- More memory overhead (cache metadata)
- More complexity in cache management

**4 is the sweet spot** for most use cases.

---

## Visual: How Boundaries Work Over Time

### Scenario: 20-turn session with compression

```
Turn 1-5: Building cache
┌─────────────────────┐
│ System (12K)        │ Cache #1 ✓
│                     │
│ Growing history     │ Not cached yet
│                     │
└─────────────────────┘

Turn 10: First compression, establish boundaries
┌─────────────────────┐
│ System (12K)        │ Cache #1 ✓ (reused)
├─────────────────────┤ Boundary!
│ Compressed (2K)     │ Cache #2 ✗ (new)
├─────────────────────┤ Boundary!
│ Recent (1K)         │ Cache #3 ✗ (new)
├─────────────────────┤
│ New                 │ Compute
└─────────────────────┘

Turn 11-19: Cache stabilized
┌─────────────────────┐
│ System (12K)        │ Cache #1 ✓
├─────────────────────┤
│ Compressed (2K)     │ Cache #2 ✓ (now cached!)
├─────────────────────┤
│ Recent (1K)         │ Cache #3 ✓ (now cached!)
├─────────────────────┤
│ New                 │ Compute (only this!)
└─────────────────────┘

Turn 20: Second compression, add 4th boundary
┌─────────────────────┐
│ System (12K)        │ Cache #1 ✓
├─────────────────────┤
│ Compressed old (2K) │ Cache #2 ✓
├─────────────────────┤
│ Compressed mid (1K) │ Cache #3 ✗ (changed)
├─────────────────────┤ New boundary!
│ Very recent (500)   │ Cache #4 ✗ (new)
├─────────────────────┤
│ New                 │ Compute
└─────────────────────┘

Turn 21+: All stable again
┌─────────────────────┐
│ System (12K)        │ Cache #1 ✓
├─────────────────────┤
│ Compressed old (2K) │ Cache #2 ✓
├─────────────────────┤
│ Compressed mid (1K) │ Cache #3 ✓ (now cached!)
├─────────────────────┤
│ Very recent (500)   │ Cache #4 ✓ (now cached!)
├─────────────────────┤
│ New                 │ Compute (only this!)
└─────────────────────┘

Cache efficiency: 15.5K cached / 16K total = 97%!
```

---

## Implementation in Our Proxy

```python
def apply_cache_boundaries(messages, compression_layers):
    """
    Apply cache_control markers to establish boundaries
    
    compression_layers: [
        {"name": "system", "start": 0, "end": 1, "stable": True},
        {"name": "old", "start": 1, "end": 20, "stable": True},
        {"name": "mid", "start": 20, "end": 35, "stable": True},
        {"name": "recent", "start": 35, "end": -3, "stable": True},
    ]
    """
    
    for i, layer in enumerate(compression_layers):
        if i >= 4:  # Anthropic limit
            break
            
        # Mark the LAST message in each layer as a boundary
        boundary_idx = layer["end"] - 1
        msg = messages[boundary_idx]
        
        # Add cache_control to the last content block
        if isinstance(msg.get("content"), list):
            msg["content"][-1]["cache_control"] = {"type": "ephemeral"}
        else:
            # Convert string content to list with cache control
            msg["content"] = [
                {
                    "type": "text",
                    "text": msg["content"],
                    "cache_control": {"type": "ephemeral"}
                }
            ]
    
    return messages
```

---

## Key Benefits of Cache Boundaries

| Without Boundaries | With Boundaries (4) |
|-------------------|---------------------|
| Single cache entry | 4 independent entries |
| All-or-nothing caching | Partial cache hits |
| Compression breaks entire cache | Only affected sections recomputed |
| ~50% cache hit after compression | ~90% cache hit after compression |
| Compression can increase costs | Compression saves costs |

---

## Rules for Effective Boundary Strategy

1. **Place boundaries at stable compression points**
   - After system prompt (never changes)
   - After compressed layers (compress once, keep stable)
   - Before recent messages (might change)

2. **Never cross boundaries when compressing**
   - Compress within a boundary section
   - Don't mix content from different boundaries

3. **Minimize boundary changes**
   - Establish boundaries early
   - Keep them stable across turns
   - Only add new boundaries when needed

4. **Use all 4 boundaries strategically**
   - Boundary 1: System prompt (largest, most stable)
   - Boundary 2: Compressed old history
   - Boundary 3: Compressed medium history  
   - Boundary 4: Recent verbatim history

5. **Accept one-time recompute cost**
   - When establishing new boundary: one turn of cache miss
   - After that: back to high cache hit rate

---

## Real Example: Cache Stats from Turn

### Without Boundaries

```
Turn 20 request: 16,000 tokens
Compressed old history (3K → 1K)

Cache lookup: hash(all 16K tokens)
Result: MISS (content changed)

Cost:
- Cache read: 0 tokens
- Compute: 16,000 tokens × $3/M = $0.048
```

### With Boundaries (4)

```
Turn 20 request: 14,000 tokens (compressed)
Boundaries:
  [system (12K)] [old (1K)] [recent (1K)] [new]

Cache lookup:
- Boundary 1 (system): hash match → HIT
- Boundary 2 (old): hash mismatch → MISS (compressed)
- Boundary 3 (recent): hash match → HIT
- New section: always compute

Cost:
- Cache read: 13,000 tokens × $0.30/M = $0.0039
- Compute: 1,000 tokens × $3/M = $0.003
- Total: $0.0069

Savings: $0.048 - $0.0069 = $0.0411 (86% cheaper!)
```

---

## Summary

**Cache boundaries = Multiple independent cache entries**

Instead of one big cache that invalidates completely:
```
[system + history] → One entry (all or nothing)
```

You get multiple entries:
```
[system] → Entry 1
[old] → Entry 2  
[recent] → Entry 3
[new] → Entry 4
```

**This lets you:**
1. ✅ Freeze old sections (Entry 1, 2 stay cached)
2. ✅ Update middle sections (Entry 3 invalidates, 1+2 stay)
3. ✅ Keep new sections separate (don't affect old cache)
4. ✅ Compress without losing cache benefits

**Result:** Compression + Caching work TOGETHER instead of fighting!
