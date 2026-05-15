# Proxy-Side Boundary Management

How the proxy tracks, bundles, and manages cache boundaries for optimal compression + caching.

---

## Core Concept: Proxy as Boundary Manager

**The proxy maintains a "boundary map" for each session:**

```python
class BoundaryManager:
    def __init__(self):
        self.boundaries = {
            "session_abc123": {
                "boundary_1": {
                    "name": "system",
                    "message_range": (0, 1),      # messages[0:1]
                    "token_count": 12000,
                    "compressed": False,
                    "stable_since_turn": 1,
                    "last_modified": 1
                },
                "boundary_2": {
                    "name": "old_history",
                    "message_range": (1, 20),     # messages[1:20]
                    "token_count": 3000,
                    "compressed": False,
                    "stable_since_turn": None,    # Not established yet
                    "last_modified": 9
                },
                "boundary_3": {
                    "name": "recent",
                    "message_range": (20, 35),    # messages[20:35]
                    "token_count": 2000,
                    "compressed": False,
                    "stable_since_turn": None,
                    "last_modified": 9
                },
                "boundary_4": {
                    "name": "very_recent",
                    "message_range": (35, -3),    # messages[35:-3]
                    "token_count": 1000,
                    "compressed": False,
                    "stable_since_turn": None,
                    "last_modified": 9
                }
            }
        }
```

---

## Strategy: Bundle Every M Turns

### Example: Bundle every 10 turns into one boundary

**Turns 1-10:** Build up, no compression

```python
Turn 1-10 state:
┌──────────────────────────────┐
│ Boundary 1: System (12K)     │ ← Always separate
├──────────────────────────────┤
│ Growing history (3K)         │ ← Not yet bounded
│ [turns 1-10]                 │
└──────────────────────────────┘

proxy.boundaries["session_abc"]["boundary_1"] = {
    "message_range": (0, 1),
    "compressed": False,
    "stable_since_turn": 1
}
# No boundary_2 yet - still accumulating
```

**Turn 10:** Time to establish first boundary!

```python
# Bundle turns 1-10 into boundary_2
proxy.compress_and_freeze_boundary(
    session_id="abc123",
    boundary_name="boundary_2",
    message_range=(1, 20),      # Messages from turns 1-10
    compression_strategy="summarize_tool_results"
)

Result:
┌──────────────────────────────┐
│ Boundary 1: System (12K)     │ ← Stable since turn 1
├──────────────────────────────┤ 
│ Boundary 2: Old (1.5K)       │ ← NEW! Compressed turns 1-10
│ [compressed]                 │    (3K → 1.5K)
├──────────────────────────────┤
│ Recent (500)                 │ ← Not bounded yet
└──────────────────────────────┘

proxy.boundaries["session_abc"]["boundary_2"] = {
    "message_range": (1, 1),    # Now single compressed message
    "compressed": True,
    "compressed_from": (1, 20), # Original span
    "stable_since_turn": 10,
    "last_modified": 10
}
```

**Turns 11-20:** Boundary 2 is frozen, accumulate new

```python
State at turn 15:
┌──────────────────────────────┐
│ Boundary 1: System (12K)     │ ← Frozen
├──────────────────────────────┤
│ Boundary 2: Old (1.5K)       │ ← Frozen (cached since turn 11)
├──────────────────────────────┤
│ Growing (2K)                 │ ← Accumulating turns 11-15
└──────────────────────────────┘
```

**Turn 20:** Compress next 10 turns

```python
# Bundle turns 11-20 into boundary_3
proxy.compress_and_freeze_boundary(
    session_id="abc123",
    boundary_name="boundary_3",
    message_range=(20, 35),
    compression_strategy="remove_stale_reads + strip_noise"
)

Result:
┌──────────────────────────────┐
│ Boundary 1: System (12K)     │ ← Frozen
├──────────────────────────────┤
│ Boundary 2: Old (1.5K)       │ ← Frozen (cached)
├──────────────────────────────┤
│ Boundary 3: Mid (800)        │ ← NEW! Compressed turns 11-20
│ [compressed]                 │    (2K → 800)
├──────────────────────────────┤
│ Recent (500)                 │ ← New accumulation
└──────────────────────────────┘
```

---

## Selective Invalidation: "Just Invalidate the One We Like"

### The Power of Selective Compression

**Scenario:** Turn 25, want to recompress boundary_2 (old history)

```python
# Decide: Should we recompress boundary_2?
if should_recompress(boundary_2):
    # This ONLY invalidates boundary_2's cache
    proxy.recompress_boundary(
        session_id="abc123",
        boundary_name="boundary_2",
        new_strategy="aggressive_summarization"  # More compression
    )

Cache impact:
┌──────────────────────────────┐
│ Boundary 1: System (12K)     │ ✓ Still cached (untouched)
├──────────────────────────────┤
│ Boundary 2: Old (1K)         │ ✗ Cache miss (recompressed)
│ [recompressed 1.5K → 1K]     │    (one-time cost)
├──────────────────────────────┤
│ Boundary 3: Mid (800)        │ ✓ Still cached (untouched)
├──────────────────────────────┤
│ Boundary 4: Recent (500)     │ ✓ Still cached (untouched)
└──────────────────────────────┘

Only 1K tokens recomputed!
Other 13.3K stay cached!
```

**Without boundaries:** Would recompute all 14.3K tokens!

---

## Implementation: Boundary Tracking

### Data Structure

```python
class SessionBoundaryState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_turn = 0
        self.boundaries = []
        
    def add_boundary(self, name: str, messages_slice: tuple, 
                     compressed: bool = False):
        boundary = {
            "name": name,
            "message_range": messages_slice,
            "established_at_turn": self.current_turn,
            "compressed": compressed,
            "last_content_hash": self._hash_messages(messages_slice),
            "stable": False,  # Becomes True after 1 turn unchanged
        }
        self.boundaries.append(boundary)
        return boundary
        
    def mark_stable(self, boundary_name: str):
        """Mark boundary as stable (won't change anymore)"""
        for b in self.boundaries:
            if b["name"] == boundary_name:
                b["stable"] = True
                b["stable_since_turn"] = self.current_turn
                
    def should_compress_next_layer(self) -> bool:
        """Decide if it's time to establish a new boundary"""
        # Every 10 turns, or when token count exceeds threshold
        turns_since_last_boundary = self.current_turn - self._last_boundary_turn()
        return turns_since_last_boundary >= 10
        
    def get_compression_target(self) -> tuple:
        """Return message range that should be compressed next"""
        if not self.boundaries:
            # First compression: everything after system prompt
            return (1, self._current_message_count() - 5)
        
        # Compress messages between last boundary and recent messages
        last_boundary_end = self.boundaries[-1]["message_range"][1]
        return (last_boundary_end, self._current_message_count() - 5)
```

---

## Compression Decision Tree

```python
def decide_compression_strategy(proxy, session_id, current_turn):
    """
    Decide what to compress and when based on boundaries
    """
    state = proxy.get_session_state(session_id)
    
    # Rule 1: Never compress until turn 10 (let cache build)
    if current_turn < 10:
        return {"action": "none", "reason": "Building initial cache"}
    
    # Rule 2: Check if time for new boundary (every 10 turns)
    if state.should_compress_next_layer():
        target_range = state.get_compression_target()
        return {
            "action": "compress_and_freeze",
            "boundary": f"boundary_{len(state.boundaries) + 1}",
            "message_range": target_range,
            "strategy": "remove_stale_reads + strip_noise",
            "reason": f"10 turns since last boundary"
        }
    
    # Rule 3: Check if existing boundary needs recompression
    for boundary in state.boundaries:
        if boundary["compressed"] and not boundary.get("aggressive_compressed"):
            # Can we compress this boundary MORE aggressively?
            if boundary["token_count"] > 2000:
                return {
                    "action": "recompress",
                    "boundary": boundary["name"],
                    "strategy": "aggressive_summarization",
                    "reason": f"{boundary['name']} still large"
                }
    
    # Rule 4: No compression needed
    return {"action": "none", "reason": "All boundaries optimal"}
```

---

## Example: Full Session with Boundary Tracking

### Session Timeline

```python
Session: abc123 (building calculator app)

Turn 1:
  Messages: [system, user:"build calculator"]
  Boundaries: 
    - boundary_1: system [stable ✓]
  Action: none

Turn 5:
  Messages: [system, user, assistant, tool, tool, ...]
  Boundaries:
    - boundary_1: system [stable ✓]
  Action: none (accumulating)

Turn 10:
  Messages: 35 messages
  Token count: 15K
  Decision: TIME TO COMPRESS!
  
  Action: 
    - Bundle messages[1:30] → compressed_old
    - Establish boundary_2
  
  Boundaries after:
    - boundary_1: system (12K) [stable ✓]
    - boundary_2: old (1.5K) [compressed, new]
  
  Cache impact:
    - boundary_1: cached ✓
    - boundary_2: miss ✗ (new)
  
  Cost: 12K cached + 3.5K computed

Turn 11:
  Messages: 37 messages  
  Boundaries:
    - boundary_1: system (12K) [stable ✓]
    - boundary_2: old (1.5K) [stable ✓] ← NOW CACHED!
  
  Cache impact:
    - boundary_1: cached ✓
    - boundary_2: cached ✓ ← Frozen!
  
  Cost: 13.5K cached + 1K computed ← Much better!

Turn 20:
  Messages: 55 messages
  Token count: 17K
  Decision: TIME FOR BOUNDARY 3!
  
  Action:
    - Bundle messages[30:50] → compressed_mid
    - Establish boundary_3
  
  Boundaries after:
    - boundary_1: system (12K) [stable ✓]
    - boundary_2: old (1.5K) [stable ✓]
    - boundary_3: mid (800) [compressed, new]
  
  Cache impact:
    - boundary_1: cached ✓
    - boundary_2: cached ✓
    - boundary_3: miss ✗ (new)
  
  Cost: 13.5K cached + 2K computed

Turn 21+:
  All boundaries frozen and cached!
  Only new messages computed each turn.
  Cost: ~14.3K cached + 500 new per turn
```

---

## Advanced: Adaptive Bundling

Instead of fixed "every 10 turns", use adaptive criteria:

```python
def should_establish_boundary(state, current_messages):
    """
    Adaptive decision: when to bundle and freeze
    """
    # Criterion 1: Token growth
    tokens_since_last = count_tokens_since_last_boundary(current_messages)
    if tokens_since_last > 3000:
        return True, "token_threshold"
    
    # Criterion 2: Turn count
    turns_since_last = state.current_turn - state.last_boundary_turn()
    if turns_since_last >= 10:
        return True, "turn_threshold"
    
    # Criterion 3: Task boundary (detect new user goal)
    if detected_new_task(current_messages):
        return True, "task_boundary"
    
    # Criterion 4: Cache efficiency drop
    cache_hit_rate = get_recent_cache_hit_rate(state.session_id)
    if cache_hit_rate < 0.85:
        return True, "cache_efficiency"
    
    return False, None
```

---

## Code: Applying Boundaries to Request

```python
def prepare_request_with_boundaries(messages, session_state):
    """
    Apply cache_control markers based on tracked boundaries
    """
    # Get current boundary configuration
    boundaries = session_state.boundaries
    
    # Apply cache_control to each boundary's last message
    for i, boundary in enumerate(boundaries):
        if i >= 4:  # Anthropic's limit
            break
            
        start, end = boundary["message_range"]
        boundary_msg_idx = end - 1
        
        # Add cache_control marker
        msg = messages[boundary_msg_idx]
        
        if isinstance(msg.get("content"), str):
            msg["content"] = [
                {
                    "type": "text",
                    "text": msg["content"],
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        elif isinstance(msg.get("content"), list):
            # Add to last content block
            msg["content"][-1]["cache_control"] = {"type": "ephemeral"}
    
    return messages
```

---

## Visualization: Boundary Evolution

```
Turn 1-9: Accumulation phase
┌─────────────────┐
│ System          │ Boundary 1 (frozen)
│                 │
│ Growing history │ No boundary yet
│                 │
└─────────────────┘

Turn 10: First freeze
┌─────────────────┐
│ System          │ B1 (frozen)
├─────────────────┤ ← NEW BOUNDARY!
│ Compressed old  │ B2 (new, will cache next turn)
├─────────────────┤
│ Recent          │ No boundary
└─────────────────┘

Turn 11-19: Stable state
┌─────────────────┐
│ System          │ B1 (cached)
├─────────────────┤
│ Compressed old  │ B2 (cached)
├─────────────────┤
│ Growing recent  │ Accumulating
└─────────────────┘

Turn 20: Second freeze
┌─────────────────┐
│ System          │ B1 (cached)
├─────────────────┤
│ Compressed old  │ B2 (cached)
├─────────────────┤ ← NEW BOUNDARY!
│ Compressed mid  │ B3 (new)
├─────────────────┤
│ Very recent     │ No boundary
└─────────────────┘

Turn 21+: Optimal state
┌─────────────────┐
│ System          │ B1 (cached) ✓
├─────────────────┤
│ Compressed old  │ B2 (cached) ✓
├─────────────────┤
│ Compressed mid  │ B3 (cached) ✓
├─────────────────┤
│ Very recent     │ B4 (cached) ✓
├─────────────────┤
│ New             │ Compute only this
└─────────────────┘
```

---

## Summary: Proxy as Boundary Manager

**What the proxy tracks:**
1. Session state (which boundaries exist)
2. Boundary content (message ranges, token counts)
3. Compression status (which boundaries are compressed)
4. Stability status (which boundaries are frozen)

**What the proxy decides:**
1. When to establish new boundary (every M turns)
2. What to compress (target message range)
3. How to compress (strategy per boundary)
4. When to recompress (if boundary still too large)

**Key benefits:**
- ✅ Bundle turns into stable layers
- ✅ Selectively invalidate only what you compress
- ✅ Keep other boundaries cached
- ✅ Minimize recomputation cost
- ✅ Maximize cache efficiency

**Result:** 90%+ cache hit rate even with aggressive compression!
