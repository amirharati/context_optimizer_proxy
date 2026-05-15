# Cache TTL (Time-To-Live) Behavior

Understanding when cache entries expire and how the 5-minute clock works.

---

## Anthropic's Cache TTL: 5 Minutes

**Official rule:** Cache entries expire after 5 minutes of inactivity.

But what does "inactivity" mean exactly?

---

## How TTL Works: Entry-by-Entry

### Key Facts

1. **Each boundary = separate cache entry with its own TTL**
2. **TTL resets on EACH USE** (not just creation)
3. **Independent timers** (one entry can expire while others stay)

### Example Timeline

```
Turn 10 (12:00:00 PM):
  Create 3 boundaries
  ┌─────────────────────────────────────┐
  │ B1: System (created 12:00:00)       │ TTL: 12:05:00
  ├─────────────────────────────────────┤
  │ B2: Old (created 12:00:00)          │ TTL: 12:05:00
  ├─────────────────────────────────────┤
  │ B3: Recent (created 12:00:00)       │ TTL: 12:05:00
  └─────────────────────────────────────┘

Turn 11 (12:01:00 PM):
  All 3 boundaries accessed (cache hit)
  ┌─────────────────────────────────────┐
  │ B1: System (last used 12:01:00)     │ TTL: 12:06:00 ← Reset!
  ├─────────────────────────────────────┤
  │ B2: Old (last used 12:01:00)        │ TTL: 12:06:00 ← Reset!
  ├─────────────────────────────────────┤
  │ B3: Recent (last used 12:01:00)     │ TTL: 12:06:00 ← Reset!
  └─────────────────────────────────────┘
  
Turn 12 (12:07:00 PM):
  6 minutes since turn 11 (no activity between)
  ┌─────────────────────────────────────┐
  │ B1: EXPIRED                         │ Cache MISS ✗
  ├─────────────────────────────────────┤
  │ B2: EXPIRED                         │ Cache MISS ✗
  ├─────────────────────────────────────┤
  │ B3: EXPIRED                         │ Cache MISS ✗
  └─────────────────────────────────────┘
  All recomputed, new TTLs: 12:12:00
```

---

## Independent Expiration Per Entry

### Scenario: Only Some Entries Change

```
Turn 10 (12:00:00):
  All boundaries created
  
Turn 11 (12:01:00):
  All cached, TTLs reset to 12:06:00
  
Turn 12 (12:02:00):
  Compress B2 (old history)
  ┌─────────────────────────────────────┐
  │ B1: System (last used 12:02:00)     │ TTL: 12:07:00 ← Reset!
  ├─────────────────────────────────────┤
  │ B2: Compressed (created 12:02:00)   │ TTL: 12:07:00 ← New entry!
  ├─────────────────────────────────────┤
  │ B3: Recent (last used 12:02:00)     │ TTL: 12:07:00 ← Reset!
  └─────────────────────────────────────┘
  
Turn 13 (12:09:00):
  7 minutes since turn 12
  ┌─────────────────────────────────────┐
  │ B1: EXPIRED                         │ Cache MISS ✗
  ├─────────────────────────────────────┤
  │ B2: EXPIRED                         │ Cache MISS ✗
  ├─────────────────────────────────────┤
  │ B3: EXPIRED                         │ Cache MISS ✗
  └─────────────────────────────────────┘
  All expired together (same last use time)
```

### Different Scenario: Partial Updates

```
Turn 10 (12:00:00):
  Create boundaries B1, B2, B3
  All TTLs: 12:05:00
  
Turn 11 (12:03:00):
  Only access B1 and B3 (skip B2 somehow - hypothetical)
  ┌─────────────────────────────────────┐
  │ B1: System (last used 12:03:00)     │ TTL: 12:08:00 ← Reset!
  ├─────────────────────────────────────┤
  │ B2: Old (last used 12:00:00)        │ TTL: 12:05:00 ← NOT reset
  ├─────────────────────────────────────┤
  │ B3: Recent (last used 12:03:00)     │ TTL: 12:08:00 ← Reset!
  └─────────────────────────────────────┘
  
Turn 12 (12:06:00):
  ┌─────────────────────────────────────┐
  │ B1: (last used 12:03:00)            │ TTL: 12:08:00 ✓ Still valid
  ├─────────────────────────────────────┤
  │ B2: EXPIRED                         │ Cache MISS ✗ (expired at 12:05)
  ├─────────────────────────────────────┤
  │ B3: (last used 12:03:00)            │ TTL: 12:08:00 ✓ Still valid
  └─────────────────────────────────────┘
  B2 expired, but B1 and B3 still cached!
```

**Note:** In practice, consecutive boundaries usually get accessed together, so they expire together.

---

## TTL Reset Behavior

### Question: Does cache READ reset the TTL?

**Answer: YES!**

```
12:00:00 - Create cache entry → TTL: 12:05:00
12:01:00 - Cache HIT (read) → TTL: 12:06:00 (reset!)
12:02:00 - Cache HIT (read) → TTL: 12:07:00 (reset!)
12:03:00 - Cache HIT (read) → TTL: 12:08:00 (reset!)
...
12:10:00 - Cache HIT (read) → TTL: 12:15:00 (reset!)
```

**As long as you keep using it within 5 minutes, it never expires!**

---

## TTL Clock: From Creation or Last Use?

### Answer: From LAST USE

```
Creation time: Irrelevant after first use
Clock starts from: Most recent cache hit

Example:
- Created: 12:00:00
- Last used: 12:10:00
- TTL expires: 12:15:00 (5 min from last use, not creation)
```

---

## Real Session Example

### Typical Cursor Session (Active Coding)

```
12:00:00 - Turn 1: Create cache → TTL: 12:05:00

12:01:30 - Turn 2: Cache hit → TTL: 12:06:30
12:02:45 - Turn 3: Cache hit → TTL: 12:07:45
12:04:20 - Turn 4: Cache hit → TTL: 12:09:20
12:06:00 - Turn 5: Cache hit → TTL: 12:11:00
12:08:15 - Turn 6: Cache hit → TTL: 12:13:15
12:10:30 - Turn 7: Cache hit → TTL: 12:15:30

... (continues as long as you keep coding)

12:20:00 - Turn 15: Still cached! TTL: 12:25:00
```

**As long as turns happen within 5 minutes, cache stays alive!**

### Session with Break

```
12:00:00 - Turn 1: Create cache → TTL: 12:05:00
12:01:00 - Turn 2: Cache hit → TTL: 12:06:00
12:02:00 - Turn 3: Cache hit → TTL: 12:07:00

[User takes coffee break - 10 minutes]

12:13:00 - Turn 4: ALL CACHES EXPIRED ✗
           Recompute everything
           New TTL: 12:18:00
```

---

## Per-Entry vs. All-Entries

### Question: Do all boundaries share one TTL?

**Answer: NO - Each boundary has independent TTL**

But in practice, they usually stay synchronized:

```
Typical request uses ALL boundaries:
┌─────────────────────────────────────┐
│ B1: System                          │ ← Read
├─────────────────────────────────────┤
│ B2: Old                             │ ← Read
├─────────────────────────────────────┤
│ B3: Mid                             │ ← Read
├─────────────────────────────────────┤
│ B4: Recent                          │ ← Read
└─────────────────────────────────────┘

All 4 entries accessed at same time
→ All 4 TTLs reset to same value
→ All 4 expire together (unless one changes)
```

---

## Special Case: Boundary Modification

### When One Boundary Changes

```
12:00:00 - Create B1, B2, B3 → All TTL: 12:05:00

12:02:00 - Access all → All TTL: 12:07:00

12:04:00 - Compress B2 (content changes)
           ┌─────────────────────────────────────┐
           │ B1: (last used 12:04:00)            │ TTL: 12:09:00
           ├─────────────────────────────────────┤
           │ B2: NEW CONTENT (created 12:04:00)  │ TTL: 12:09:00
           ├─────────────────────────────────────┤
           │ B3: (last used 12:04:00)            │ TTL: 12:09:00
           └─────────────────────────────────────┘
           
           All synchronized again!
```

---

## TTL Summary Table

| Question | Answer | Details |
|----------|--------|---------|
| **TTL duration?** | 5 minutes | Fixed by Anthropic |
| **Per-entry or all?** | Per-entry | Each boundary independent |
| **Clock starts when?** | Last use | NOT creation time |
| **Does read reset TTL?** | YES | Every cache hit resets the 5-min timer |
| **Different TTLs per entry?** | Possible | But usually synchronized in practice |
| **Can one expire while others stay?** | YES | If accessed separately |

---

## Practical Implications for Our Proxy

### Strategy: Keep Cache Alive

```python
class CacheManager:
    def __init__(self):
        self.last_access_times = {}  # Per session
        
    def should_warn_about_expiry(self, session_id):
        """
        Check if cache might expire soon
        """
        last_access = self.last_access_times.get(session_id)
        if not last_access:
            return False
            
        idle_time = time.time() - last_access
        
        # Warn if 4 minutes idle (1 min before expiry)
        if idle_time > 240:
            return True, f"Cache expires in {300 - idle_time:.0f}s"
        
        return False, None
        
    def on_request(self, session_id):
        """
        Track when cache was last accessed
        """
        self.last_access_times[session_id] = time.time()
        
        # Check for warning
        should_warn, message = self.should_warn_about_expiry(session_id)
        if should_warn:
            print(f"[CACHE WARNING] {message}")
```

### Optimization: Batch Operations

```python
# BAD: Spread out over time
12:00 - Compress B2 → B1,B3,B4 TTL reset
12:03 - Compress B3 → B1,B2,B4 TTL reset (B2 only had 2 min left!)
12:06 - Compress B4 → B1,B2,B3 TTL reset

# GOOD: Batch together
12:00 - Compress B2, B3, B4 in one request
        → All boundaries TTL reset together
        → All stay synchronized
```

---

## Edge Cases

### Case 1: Very Long Session (>5 hours)

```
Hour 1: Cache created, continuously used → stays alive
Hour 2: Cache still alive (reset every turn)
Hour 3: Cache still alive
...
Hour 5: Cache still alive (as long as turns < 5 min apart)

Cache can live FOREVER if continuously used!
```

### Case 2: Rapid Fire Requests

```
12:00:00.0 - Turn 1 → TTL: 12:05:00.0
12:00:00.5 - Turn 2 → TTL: 12:05:00.5
12:00:01.0 - Turn 3 → TTL: 12:05:01.0
12:00:01.5 - Turn 4 → TTL: 12:05:01.5

Each request resets TTL individually
Cache stays alive easily
```

### Case 3: Exactly 5 Minutes

```
12:00:00 - Create cache → TTL: 12:05:00
12:04:59 - Access cache → TTL: 12:09:59 (just in time!)
12:05:01 - Would have expired without that access!
```

---

## Cost Implications

### Scenario: Working Session with Breaks

**Session 1: No breaks (1 hour, 30 turns)**
```
All turns within 5 min of each other
→ Cache never expires
→ Only first turn pays write cost
→ All other turns: cache read ($0.30/M)

Cost: 1 write + 29 reads = very cheap!
```

**Session 2: With breaks (1 hour, 30 turns, 3 breaks >5 min)**
```
Break 1 at turn 10 → cache expires
Break 2 at turn 20 → cache expires  
Break 3 at turn 30 → cache expires

Cost: 4 writes (initial + 3 expirations) + 26 reads
      = 4× more cache write costs!
```

**Optimization:** If you know you'll take a break, compress aggressively BEFORE the break to minimize write cost when cache rebuilds.

---

## Final Answer to Your Questions

1. **How TTL works?**
   - 5 minutes from last use (not creation)
   
2. **Last cache hit or creation?**
   - Last cache hit (TTL resets on every read)
   
3. **Time from creation regardless?**
   - No, resets on every access
   
4. **Entry by entry or all?**
   - Entry by entry (independent timers)
   - But usually expire together in practice

**Key insight:** Keep coding consistently (turns < 5 min apart) and your cache stays alive indefinitely! Take a long break (>5 min) and pay the rebuild cost once.
