# Complete Removal vs. Compression - Cache Impact

What happens when you REMOVE content entirely (0 tokens) vs. compress it?

---

## Scenario: Remove Irrelevant Content Completely

### The Setup

**Turn 15: Current conversation**

```
Messages:
┌────────────────────────────────────┐
│ System (12K)                       │ Boundary 1
├────────────────────────────────────┤
│ Old work: Build calculator (3K)    │ Boundary 2
├────────────────────────────────────┤
│ Irrelevant: Discussed weather (2K) │ Boundary 3 ← Want to REMOVE
├────────────────────────────────────┤
│ Recent: Fix bugs (1K)              │ Boundary 4
├────────────────────────────────────┤
│ New message                        │
└────────────────────────────────────┘

Total: 18K tokens
All cached except new message
```

**Decision: Remove weather discussion (completely irrelevant)**

---

## Option 1: Remove & Shift (Breaking Change)

### What You Might Think

```
Before removal:
[system, calculator_work, weather, bug_fixes, new]
 ^B1     ^B2              ^B3      ^B4

After removal:
[system, calculator_work, bug_fixes, new]
 ^B1     ^B2              ^B3 (was B4)

Just remove boundary 3, shift everything up!
```

### The Problem: Cache Breaks!

**Cache is position-based with prefix matching:**

```
Before removal:
Cache Entry #1: hash(position 0-1) → system
Cache Entry #2: hash(position 1-20) → calculator  
Cache Entry #3: hash(position 20-35) → weather
Cache Entry #4: hash(position 35-50) → bug_fixes

After removal (messages shifted):
Position 20-35 NOW contains bug_fixes (was weather)
  ↓
Cache lookup for position 20-35:
  - Expects: hash(weather)
  - Finds: hash(bug_fixes)
  - Result: MISS! ✗

Cache Entry #4 also breaks:
  - Was at position 35-50
  - Now at position 20-35 (shifted)
  - Cache lookup fails! ✗
```

**Result:** Removing boundary 3 invalidates BOTH boundary 3 AND 4!

---

## Option 2: Remove & Replace with Marker (Better)

### Strategy: Keep Structure, Zero Out Content

```
Before:
┌────────────────────────────────────┐
│ System (12K)                       │ B1
├────────────────────────────────────┤
│ Calculator work (3K)               │ B2
├────────────────────────────────────┤
│ Weather discussion (2K)            │ B3 ← Remove this
├────────────────────────────────────┤
│ Bug fixes (1K)                     │ B4
└────────────────────────────────────┘

After:
┌────────────────────────────────────┐
│ System (12K)                       │ B1 ✓ (cached)
├────────────────────────────────────┤
│ Calculator work (3K)               │ B2 ✓ (cached)
├────────────────────────────────────┤
│ [Removed - off-topic] (50 tokens)  │ B3 ✗ (changed)
├────────────────────────────────────┤
│ Bug fixes (1K)                     │ B4 ✓ (cached!)
└────────────────────────────────────┘

Total: 16K tokens (was 18K)
```

**Cache impact:**
- B1: Still cached ✓
- B2: Still cached ✓
- B3: Cache miss ✗ (content changed, but now tiny)
- B4: Still cached ✓ (position unchanged!)

**Cost:**
- 16K cached @ $0.30/M = $0.0048
- 50 new tokens @ $3/M = $0.00015
- Total: ~$0.005

**Savings:** Only recompute 50 tokens instead of 3K!

---

## Option 3: Complete Removal with Boundary Consolidation

### Strategy: Remove AND Merge Boundaries

```
Turn 15: Remove weather, merge B2 and B4
┌────────────────────────────────────┐
│ System (12K)                       │ B1 ✓
├────────────────────────────────────┤
│ Calculator + Bug fixes (4K)        │ B2 ✗ (merged)
├────────────────────────────────────┤
│ Recent (500)                       │ B3 (was B4)
└────────────────────────────────────┘

Cache impact:
- B1: cached ✓
- B2: MISS ✗ (new merged content)
- B3: MISS ✗ (shifted position)

Cost: Recompute 4.5K tokens
```

**This is WORSE!** More cache misses.

---

## The Best Strategy: Marker-Based Removal

### Implementation

```python
def remove_irrelevant_boundary(messages, boundary_to_remove):
    """
    Remove content but keep boundary structure intact
    """
    start, end = boundary_to_remove["message_range"]
    
    # Replace all messages in this boundary with a single marker
    marker_message = {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": "[Content removed: off-topic discussion about weather]",
                "cache_control": {"type": "ephemeral"}  # Keep boundary!
            }
        ]
    }
    
    # Replace messages[start:end] with single marker
    messages = messages[:start] + [marker_message] + messages[end:]
    
    return messages


# Example usage
Turn 15: Before removal (18K tokens)
┌────────────────────────────────────┐
│ System (12K)                       │ Cached
│ Calculator (3K)                    │ Cached
│ Weather (2K) ← 15 messages         │ Cached
│ Bug fixes (1K)                     │ Cached
│ New (500)                          │ New
└────────────────────────────────────┘

Turn 16: After removal (16K tokens)
┌────────────────────────────────────┐
│ System (12K)                       │ ✓ Cached
│ Calculator (3K)                    │ ✓ Cached
│ "[Removed: weather]" (50 tokens)   │ ✗ Changed (one-time cost)
│ Bug fixes (1K)                     │ ✓ Cached (position unchanged!)
│ New (500)                          │ New
└────────────────────────────────────┘

Turn 17: Marker now cached
┌────────────────────────────────────┐
│ System (12K)                       │ ✓ Cached
│ Calculator (3K)                    │ ✓ Cached  
│ "[Removed: weather]" (50 tokens)   │ ✓ Cached!
│ Bug fixes (1K)                     │ ✓ Cached
│ New (500)                          │ New
└────────────────────────────────────┘
```

---

## Zero Tokens? Not Quite

**You can't have ZERO tokens for a boundary:**

1. **Minimum: Need a marker**
   - "[Content removed]" = ~10-50 tokens
   - Tiny compared to original 2K tokens
   - Maintains boundary structure

2. **Why not 0 tokens?**
   - Cache entries need content to hash
   - Boundaries need something to mark position
   - LLM needs context continuity signal

3. **But effectively zero cost:**
   - 50 tokens @ $0.30/M (cached) = $0.000015
   - Negligible!

---

## Special Case: Remove Entire Trailing Section

**If removing from the END of conversation:**

```
Before:
[system, recent_work, irrelevant_old_stuff, very_old_stuff]

After:
[system, recent_work]
```

**This is safe!** No position shifts for remaining content.

**Cache impact:**
- System: cached ✓
- Recent work: cached ✓
- Old stuff: simply not sent (no cache invalidation)

**This is the best case for removal!**

---

## Comparison: Compression vs. Removal

### Scenario: 2K tokens of irrelevant content

**Option A: Compress (2K → 500 tokens)**
```
Turn N+1: Cache miss on compressed section
  - Recompute: 500 tokens
  - Context saved: 1.5K tokens
  - Other boundaries: cached ✓

Turn N+2: Compressed version cached
  - Cost: 500 tokens @ $0.30/M = $0.00015
```

**Option B: Remove with marker (2K → 50 tokens)**
```
Turn N+1: Cache miss on marker
  - Recompute: 50 tokens
  - Context saved: 1.95K tokens
  - Other boundaries: cached ✓

Turn N+2: Marker cached
  - Cost: 50 tokens @ $0.30/M = $0.000015
```

**Winner: Removal (if content truly irrelevant)**

---

## When to Remove vs. Compress

### Remove (with marker):
- ✅ Truly irrelevant content (off-topic discussion)
- ✅ Stale file reads (can re-read if needed)
- ✅ Old tool results (tool can re-execute)
- ✅ Debugging attempts that failed
- ✅ Maximum token savings needed

### Compress (keep essence):
- ✅ Relevant but verbose content
- ✅ Important context that might be referenced
- ✅ Work history (shows evolution)
- ✅ When LLM shouldn't re-fetch (expensive tools)

---

## Implementation: Smart Removal

```python
def should_remove_vs_compress(boundary):
    """
    Decide: complete removal or compression?
    """
    # Analyze content
    content_type = classify_boundary_content(boundary)
    
    if content_type == "off_topic":
        return "remove"  # [Removed: off-topic]
    
    if content_type == "stale_file_read":
        # Can re-read if needed
        return "remove"  # [Removed: stale read of file.py]
    
    if content_type == "failed_debugging":
        # Dead-end attempts
        return "remove"  # [Removed: failed debugging attempts]
    
    if content_type == "repetitive_tool_results":
        # Multiple similar outputs
        return "remove"  # [Removed: 10 similar test runs]
    
    if content_type == "important_context":
        # Keep but compress
        return "compress"  # Summarize to key points
    
    return "keep"  # Recent or essential


# Apply decision
if should_remove_vs_compress(boundary) == "remove":
    remove_boundary_with_marker(boundary)
elif should_remove_vs_compress(boundary) == "compress":
    compress_boundary(boundary)
```

---

## Summary: Complete Removal

| Your Question | Answer |
|---------------|--------|
| Can we totally remove stuff? | Yes! But use markers (~50 tokens) |
| Do we invalidate those entries? | Yes, but only THAT boundary |
| Can it be 0 tokens? | No, but ~50 tokens is effectively free |
| Does it break other caches? | No! (if you keep position with marker) |
| When to remove vs compress? | Remove if truly irrelevant/refetchable |

**Key insight:** 
- Remove = 2K → 50 tokens (98% reduction!)
- Compress = 2K → 500 tokens (75% reduction)
- Remove wins IF content is truly disposable

**Best practice:**
```
[system] ← Never remove
[important_work] ← Compress, don't remove
[off_topic] ← REMOVE with marker
[stale_reads] ← REMOVE with marker
[failed_attempts] ← REMOVE with marker
[recent_work] ← Keep verbatim
```

You're right that removal is more aggressive than compression, and it gives better token savings! The key is using markers to maintain boundary structure and avoid breaking cache for subsequent boundaries.
