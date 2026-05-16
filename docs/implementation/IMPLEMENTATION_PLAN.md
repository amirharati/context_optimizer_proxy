# Implementation Plan - Context Optimizer

Practical step-by-step plan from safest/obvious to complex. Each phase delivers immediate value.

---

## Guiding Principles

1. **Safe first**: Start with preprocessing (happens BEFORE provider, so no cache to break)
2. **Validate each phase**: Measure impact before moving to next
3. **Incremental value**: Each phase reduces costs immediately
4. **Data-driven**: Use A/B testing to validate assumptions

**References:**
- Research: `docs/research/compression_research.md`
- Backlog: `docs/planning/backlog.md`
- Caching: `docs/research/cache/cache_boundaries_explained.md`, `docs/research/cache/provider_caching_comparison.md`
- Testing: `docs/research/ab_testing_strategy.md`

---

## Phase 0: Foundation (Already Done ✓)

✅ Basic proxy working (FastAPI, streaming, OpenRouter + Anthropic direct)
✅ Session logging (detect turns, save to JSONL)
✅ Web UI for session viewing
✅ Token estimation and basic metrics
✅ Human-readable logging structure (date-based folders, time-stamped files)

---

## Phase 1: Pre-Send Preprocessing (SAFEST - Week 1)

**Goal:** Reduce tokens BEFORE sending to provider (no cache exists yet, 100% safe)

**Why this is safest:**
- Happens before first API call
- No existing cache to break
- Pure deterministic transformations
- Immediate cost savings (10-15%)

### ✅ Task 1.1: Noise Stripping (1-2 days) - COMPLETED

**File:** Create `context_optimizer/preprocessor.py`

**What:** Remove boilerplate from tool results using regex patterns

**Patterns to strip** (from `docs/research/compression_research.md` Finding 1):
- "Command completed in X ms."
- "Shell state (cwd, env vars) persists..."
- "Current directory: /path"
- "Exit code: 0\n\nCommand output:\n\n```"
- "Make sure to follow and update your TODO list..."
- "This command ran outside the sandbox..."

**Strategy:**
- Apply regex patterns to strip noise from tool_result messages
- Only modify content, preserve message structure
- Must be deterministic (same input → same output always)

**Expected savings:** ~8% of history tokens

**Validation:**
- Test on logged sessions
- Verify: No information lost, ~8% token reduction
- Check: LLM doesn't ask for missing information

---

### ✅ Task 1.2: Path Compression (1 day) - IN PROGRESS

**File:** `context_optimizer/preprocessor.py`

**What:** Replace path stems with aliases (from `docs/research/compression_research.md` Finding 2)

**Strategy:**
- Detect common path stem from system prompt (e.g., `/Users/amir/Dropbox/CodingProjects`)
- Detect workspace path (e.g., `/Users/amir/.../test_app`)
- Replace all occurrences:
  - path_stem → `$C` (coding projects root)
  - workspace_path → `$W` (workspace root)
- Add legend to system prompt: `$C=/path/to/coding`, `$W=/path/to/workspace`
- Must be deterministic and reversible

**Expected savings:** ~3.8% of history tokens

**Validation:**
- Test on logged sessions
- Verify: Paths still readable by LLM
- Check: No file resolution errors

---

### Task 1.3: Integration (1 day)

**File:** `context_optimizer/main.py`

**What:** Apply all preprocessing before forwarding

**Strategy:**
- Hook into `/v1/chat/completions` endpoint
- Apply noise stripping (if enabled)
- Apply path compression (if enabled)
- Log original vs. processed token counts
- Forward modified messages to provider

**Configuration flags (.env):**
```bash
ENABLE_NOISE_STRIPPING=true
ENABLE_PATH_COMPRESSION=true
```

**Validation:**
- Run for 1 week on real usage
- Measure: 10-12% token reduction
- Confirm: No quality degradation (LLM doesn't ask to re-read files)

**Why Phase 1 is cache-safe:**
- These transformations are applied BEFORE first send to provider
- Cache is built on the PREPROCESSED content
- As long as preprocessing is deterministic, cache remains valid

---

### ✅ Task 1.4: A/B Testing for Phase 1 (2 days) - COMPLETED

**File:** `context_optimizer/ab_tester.py` (initial version)

**What:** Start A/B testing from Phase 1, progressively add strategies

**Phase 1 strategies to test:**
- **None:** No preprocessing (baseline)
- **Noise only:** Just noise stripping
- **Paths only:** Just path compression
- **Both:** Noise + paths (recommended)

**Test approach:**
- Run 10 sessions per strategy
- Measure: token reduction, cost, quality (retry rate)
- Select winner for Phase 1
- **Build testing framework now, reuse for all phases**

**Output:** `phase1_results.json`

**Why test from Phase 1:**
- Validates our assumptions early
- Builds testing infrastructure incrementally
- Each phase adds new strategies to test
- Continuous optimization vs. big-bang at Phase 4

---

## Phase 2: Emergency Context Limits + TTL Tracking (SAFE - Week 2)

**Goal:** Never hit "prompt too long" errors + detect cache expiry (from `docs/planning/backlog.md` item 3)

**Why this is important:**
- Cursor doesn't compress when using custom endpoints
- Long sessions will fail without this
- Gives us automatic fallback compression
- TTL tracking lets us optimize when cache is expired

### Task 2.1: TTL Tracking (1 day)

**File:** `context_optimizer/ttl_tracker.py`

**What:** Track session idle time to detect cache expiry

**Strategy:**
- Track last request timestamp per session
- Cache TTL = 5 minutes from last use (resets on each access)
- If `(now - last_request) > 5 minutes`: cache is expired
- Return: `cache_likely_valid` boolean

**Why this matters:**
- Cache expires after 5 minutes of inactivity
- If cache is gone, no point preserving boundaries
- Can switch to aggressive compression without penalty
- Especially important for "coffee break" scenarios

**Reference:** `docs/research/cache/cache_ttl_behavior.md`

**Usage example:**
- User works actively: cache valid, use conservative compression
- User takes 10-minute break: cache expired, use aggressive compression
- User returns: next request has no cache benefit anyway

---

### Task 2.2: Token Limit Monitoring (1 day)

**File:** `context_optimizer/token_limiter.py`

**What:** Check if request will exceed model's context limit

**Strategy:**
- Maintain model limits dictionary (Claude: 200k, GPT-4o: 128k, DeepSeek: 64k, etc.)
- Use safety margin (e.g., 75% of limit)
- Estimate tokens in current request
- Return: (will_exceed, current_count, safe_limit)

---

### Task 2.3: Emergency Compression (2 days)

**File:** `context_optimizer/emergency_compressor.py`

**What:** Aggressive compression to fit within limit

**Strategies (progressive):**
1. **Level 1:** Keep system + last 50% messages, drop middle
2. **Level 2:** Keep system + last 30% messages
3. **Level 3 (emergency):** Keep system + last 20% messages

**Logic:**
- Try Level 1, check if under limit
- If still over, try Level 2
- If still over, apply Level 3 (emergency)
- Always preserve system prompt + most recent context

**Note:** This is a safety fallback. Quality degrades, but prevents hard failures.

---

### Task 2.4: Auto-Retry on Error + TTL-Aware Compression (2 days)

**File:** Update `context_optimizer/main.py`

**What:** Integrate limit checking, TTL awareness, and error recovery

**Flow:**
1. Apply Phase 1 preprocessing
2. **Check TTL:** Is cache still valid?
3. If cache expired (>5 min idle): use aggressive compression
4. If cache valid: use conservative compression
5. Check if over model's safe limit
6. If yes: apply emergency compression proactively
7. Forward to provider
8. If provider still rejects with "prompt too long":
   - Apply even more aggressive compression (80% of limit)
   - Retry once
9. Log all compression events + TTL state

**Configuration (.env):**
```bash
ENABLE_CONTEXT_LIMIT_CHECK=true
ENABLE_TTL_TRACKING=true
EMERGENCY_COMPRESS_THRESHOLD=0.75
CACHE_TTL_MINUTES=5
```

**Validation:**
- Test with very long sessions (100+ turns)
- Test with breaks (simulate coffee breaks >5 min)
- Confirm: No "prompt too long" errors reach user
- Confirm: Aggressive compression used after breaks (no cache to preserve)
- Measure: Emergency compression triggered how often?
- Measure: TTL expiry detection accuracy
- Alert: If triggered >5% of time, Phase 3 compression needed sooner

---

### Task 2.5: A/B Testing for Phase 2 (2 days)

**What:** Test TTL-aware strategies

**Strategies:**
- **Phase 1 winner** (baseline from Task 1.4)
- **TTL-aware conservative:** Switch to aggressive only if TTL expired
- **TTL-aware aggressive:** Always aggressive after 3-minute idle
- **TTL-ignore:** Never consider TTL (to measure impact)

**Test approach:**
- 10 sessions with natural breaks
- Measure: cost savings, cache effectiveness
- Compare: TTL-aware vs. TTL-ignore

**Output:** `phase2_results.json`

---

## Phase 3: Cache-Aware Compression (MEDIUM - Week 3-4)

**Goal:** Compress history while preserving cache benefits

**Why now:** Phase 1+2 give us baseline. Now optimize for caching.

**Reference:** `docs/research/cache/cache_boundaries_explained.md`, `docs/research/cache/proxy_boundary_management.md`

### Task 3.1: Boundary Tracker (2 days)

**File:** `context_optimizer/boundary_manager.py`

**What:** Track compression boundaries per session for stable cache layers

**Responsibilities:**
- Track which message ranges have been compressed in each session
- Decide when to compress next layer (e.g., every N turns)
- Return compression ranges that don't overlap
- Record boundary positions for cache marker placement

**State per session:**
- `layers`: List of compressed ranges with their boundary positions
- `last_compression_turn`: When last compression happened
- `stable_since`: How long each boundary has been unchanged

**Strategy:**
- First compression: messages[1] to recent-5 (keep recent context fresh)
- Next compressions: after last compressed layer to recent-5
- Never compress system prompt or last ~5 messages

---

### Task 3.2: Stable Layer Compression + File Deduplication (3 days)

**File:** `context_optimizer/layer_compressor.py`

**What:** Compress old message ranges into compact summaries

**THIS IS WHERE FILE DEDUPLICATION BELONGS** (moved from Phase 1)

**Strategy: Removal + Markers**
- Replace tool_result content with `[Content removed - re-call if needed]`
- Keep tool structure (tool_use + tool_result pairs intact)
- For file reads: keep ONLY the most recent read of each file, dedupe older reads
- Count what was removed and add summary

**Example output:**
```
[Compressed history: turns 5-15]
- 12 file reads (deduplicated to 5 unique files)
- 8 shell commands
- 3 write operations
(Re-call tools if needed - all content available on request)
```

**Why deduplication belongs here (not Phase 1):**
- Modifying old messages breaks cache prefix
- Must be done within explicit boundary management
- Can be cached as a single stable layer after compression

**Expected savings:** 20-40% on old history (variable)

---

### Task 3.3: Provider-Specific Cache Markers (2 days)

**File:** `context_optimizer/cache_marker.py`

**What:** Apply cache breakpoints based on provider capabilities

**Anthropic (explicit control):**
- Add `cache_control: {type: "ephemeral"}` markers
- Place at compression boundaries
- Allows independent cache entries per layer

**OpenAI (automatic, no explicit control):**
- Insert stable separator messages at boundaries
- Use consistent text: `--- Layer {i} ---`
- Hope these create natural cache breakpoints
- Less control, but better than nothing

**Google Gemini (automatic):**
- Similar to OpenAI
- No explicit markers supported
- Use stable separators

**OpenRouter:**
- No caching benefits passed through
- Skip cache markers entirely
- Rely on aggressive preprocessing (Phase 1) only

**Reference:** `docs/research/cache/provider_caching_comparison.md`

---

### Task 3.4: Integration with Boundaries (2 days)

**File:** Update `context_optimizer/main.py`

**What:** Integrate boundary management into request flow

**Flow:**
1. Apply Phase 1 preprocessing
2. Apply Phase 2 limit checking
3. **Phase 3:** Check if it's time to compress a layer
4. If yes:
   - Get compression range from boundary manager
   - Compress that range (includes file deduplication)
   - Replace original range with compressed message
   - Record new boundary
5. Apply provider-specific cache markers at all boundaries
6. Forward to provider

**Configuration (.env):**
```bash
ENABLE_BOUNDARY_COMPRESSION=false  # Enable after Phase 4 validates
COMPRESS_EVERY_N_TURNS=10
```

**Validation:**
- Run for 1 week
- Measure cache hit rate by provider (target >85% for Anthropic)
- Measure cost savings (20-30% additional beyond Phase 1)
- Monitor: Does cache remain valid across compressions?
- Alert: If cache hit rate <70%, strategy needs tuning

---

### Task 3.5: A/B Testing for Phase 3 (3 days)

**What:** Test boundary compression strategies

**Strategies:**
- **Phase 2 winner** (baseline)
- **Conservative boundaries:** Compress every 15 turns
- **Balanced boundaries:** Compress every 10 turns
- **Aggressive boundaries:** Compress every 8 turns
- **With dedup:** Add file deduplication to balanced
- **TTL-aware boundaries:** Adjust frequency based on TTL

**Test approach:**
- 10 long sessions (50+ turns each) per strategy
- Measure: cache hit rate, cost, quality
- Validate: Boundaries preserve cache (>80% hit rate target)

**Critical metrics:**
- Cache hit rate per provider (Anthropic vs OpenAI vs Google)
- Cost reduction vs. Phase 2
- Quality: Does LLM ask to re-read files?

**Output:** `phase3_results.json`

---

## Phase 4: Comprehensive A/B Testing (COMPLEX - Week 5-6)

**Goal:** Empirically discover optimal strategy per provider across all phases

**Note:** We've been testing progressively (Task 1.4, 2.5, 3.5), now combine learnings

**Reference:** `docs/research/ab_testing_strategy.md`

### Task 4.1: Unified Testing Framework (2 days)

**File:** `context_optimizer/ab_tester.py` (enhanced version)

**What:** Combine all previous test learnings into comprehensive framework

**Key features:**
- Parallel strategy execution across all implemented phases
- Real cost tracking per strategy per provider
- Cache effectiveness detection (by comparing actual vs. expected costs)
- Winner selection based on cost × quality metric
- Automated result reporting
- **Reuse infrastructure from Tasks 1.4, 2.5, 3.5**

**Reference:** Full design in `docs/research/ab_testing_strategy.md`

**Comprehensive strategies to test:**
- **Baseline:** No compression
- **Phase 1 winner** (from Task 1.4)
- **Phase 2 winner** (from Task 2.5)
- **Phase 3 winner** (from Task 3.5)
- **Combined optimal:** Best combination across phases
- **Per-provider tuned:** Different strategy per provider

---

### Task 4.2: Cross-Provider Validation (1 week)

**Process:**
1. Test Anthropic direct (20 sessions × all strategies)
2. Test OpenAI direct (20 sessions × all strategies)
3. Test OpenRouter (20 sessions × all strategies)
4. Test Google Gemini (20 sessions × all strategies)
5. Compare: Does same strategy win across providers?
6. Analyze: Cache effectiveness per provider
7. Generate: Per-provider optimal configs

**Deliverable:** `optimal_strategies_by_provider.json`

---

### Task 4.3: Deploy Optimal Configs (1 day)

**File:** Update `context_optimizer/main.py`

**What:** Load and apply winner strategies per provider

**Strategy:**
- Load `optimal_strategies.json` (generated by A/B testing)
- Lookup strategy by provider
- Apply corresponding compression settings
- Fall back to "conservative" if provider not tested

**Example config:**
```json
{
  "anthropic": {
    "strategy": "balanced_boundaries",
    "compress_every_n_turns": 10,
    "enable_dedup": true,
    "ttl_aware": true
  },
  "openai": {
    "strategy": "conservative",
    "compress_every_n_turns": 15,
    "enable_dedup": false,
    "ttl_aware": true
  },
  "openrouter": {
    "strategy": "aggressive",
    "compress_every_n_turns": 5,
    "enable_dedup": true,
    "ttl_aware": false
  },
  "google": {
    "strategy": "balanced",
    "compress_every_n_turns": 10,
    "enable_dedup": true,
    "ttl_aware": true
  }
}
```

---

## Phase 5: Dynamic Model Routing (MOST COMPLEX - Week 7+)

**Goal:** Route turns to appropriate model tier based on difficulty

**Reference:** `docs/research/compression_research.md` Finding 8

**Prerequisites:**
- 100+ logged sessions with quality indicators
- Phases 1-4 complete and validated

### Task 5.1: Enhanced Session Logging (1 week)

Add routing-relevant metadata:
- Task keywords
- File counts
- Tool types
- User edits (quality indicator)
- Retries (quality indicator)

---

### Task 5.2: Train Routing Classifier (2 weeks)

Options:
- Simple ML (sklearn RandomForest)
- LLM self-assessment
- Hybrid approach

**Deliverable:** `routing_classifier.pkl`

---

### Task 5.3: Integrate Routing (1 week)

**File:** `context_optimizer/router.py`

**What:** Route each turn to appropriate model tier

**Strategy:**
- Load routing classifier (trained in Task 5.2)
- Extract features from current turn: user message, recent history, task type
- Classify as: simple / medium / hard
- Route to tier (never above user's chosen ceiling)
- Log routing decisions for analysis

**Example:**
- User picks `claude-3-opus` (ceiling = opus)
- Turn classified as "simple" → route to `gemini-2.0-flash`
- Turn classified as "medium" → route to `claude-3.5-sonnet`
- Turn classified as "hard" → route to `claude-3-opus`

**Validation:**
- A/B test: routing vs. no routing
- Measure: cost savings (target 90%+ combined with compression)
- Measure: quality via retry rate (target <5% escalations)
- Implement auto-escalation: if model gets stuck, escalate tier
- Monitor: classification accuracy over time

---

## Implementation Timeline

```
Week 1:   Phase 1 (Preprocessing + A/B test) ✓
Week 2:   Phase 2 (Context limits + TTL + A/B test) ✓
Week 3-4: Phase 3 (Boundary compression + A/B test) ✓
Week 5-6: Phase 4 (Comprehensive A/B testing) ✓
Week 7+:  Phase 5 (Routing) ✓

Total: ~7-10 weeks for full implementation

Note: A/B testing integrated into every phase (progressive validation)
```

---

## Success Metrics per Phase

| Phase | Primary Metric | Target | Validation | A/B Test |
|-------|----------------|--------|------------|----------|
| 1 | Token reduction | 10-12% | No quality loss | Task 1.4: Test noise/paths separately |
| 2 | Zero "prompt too long" + TTL detection | 100% error prevention, >90% TTL accuracy | Auto-recovery works | Task 2.5: Test TTL-aware strategies |
| 3 | Cache hit rate + cost | >85% cache (Anthropic), 20-30% savings | Provider-specific | Task 3.5: Test boundary frequencies |
| 4 | Optimal strategy per provider | Per provider | Cost + quality validation | Task 4.2: Cross-provider comprehensive |
| 5 | Cost reduction via routing | 90%+ combined | Quality maintained (<5% retry) | Task 5.2: Test routing accuracy |

---

## Configuration Management

Each phase adds `.env` flags:

```bash
# Phase 1: Pre-send preprocessing (safe)
ENABLE_NOISE_STRIPPING=true
ENABLE_PATH_COMPRESSION=true

# Phase 2: Context limit safety + TTL tracking
ENABLE_CONTEXT_LIMIT_CHECK=true
ENABLE_TTL_TRACKING=true
CACHE_TTL_MINUTES=5
EMERGENCY_COMPRESS_THRESHOLD=0.75

# Phase 3: Cache-aware compression
ENABLE_BOUNDARY_COMPRESSION=false  # Enable after Task 3.5 validates
COMPRESS_EVERY_N_TURNS=10
ENABLE_FILE_DEDUPLICATION=false  # Part of boundary compression
TTL_AWARE_BOUNDARIES=true  # Adjust compression based on TTL

# Phase 4: A/B testing
ENABLE_AB_TESTING=false  # Only during testing period
AB_TEST_PROVIDER=anthropic
AB_TEST_DURATION_SESSIONS=10

# Phase 5: Dynamic routing
ENABLE_DYNAMIC_ROUTING=false  # Enable after training
ROUTING_CLASSIFIER_PATH=models/routing_classifier.pkl
ROUTING_MIN_CONFIDENCE=0.75
```

---

## Summary: Implementation Order

1. ✅ **Safest first**: Pre-send preprocessing (no cache to break) + **A/B test**
2. ✅ **Safety net**: Context limit + TTL tracking (prevent errors, detect cache expiry) + **A/B test**
3. ✅ **Optimization**: Cache-aware compression (preserve cache) + **A/B test**
4. ✅ **Validation**: Comprehensive A/B testing (discover optimal per provider)
5. ✅ **Advanced**: Dynamic routing (maximize savings)

**Key principle: Progressive A/B testing**
- Don't wait until Phase 4 to test
- Test at every phase, validate assumptions early
- Build testing infrastructure incrementally
- Each phase inherits winner from previous phase

Each phase delivers immediate value. Can ship after any phase and still have useful cost savings!
