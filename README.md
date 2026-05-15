# Context Optimizer

A smart proxy for reducing LLM API costs by intelligently compressing conversation context.

================================================================================
## Install
================================================================================

**Requirements:** Python 3.11+ recommended (match what you use for FastAPI / uvicorn).

From the repository root, use the project folder that contains `main.py` and `requirements.txt`:

```bash
cd context_optimizer
```

Create a virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure secrets from the template (see **Configuration** later for optional flags):

```bash
cp .env.example .env
# Edit .env: OPENROUTER_API_KEY=...  and, if you use direct Claude routing, ANTHROPIC_API_KEY=...
```

Run the server:

```bash
python main.py
```

By default this binds to `127.0.0.1` and port `8000`; override with `HOST` / `PORT` in the environment if needed. For Cursor, you often need a public URL (e.g. `ngrok http 8000`) because the IDE may block `localhost` for custom OpenAI endpoints.

Documentation index (planning vs research vs cache notes): **`docs/README.md`**.

================================================================================
## WHAT IS THIS?
================================================================================

Context Optimizer is a local HTTP proxy that sits between Cursor IDE (or any
OpenAI-compatible client) and LLM providers. It automatically compresses long
conversation histories before sending them to expensive models, potentially
saving 90%+ on API costs.

Think of it as a "smart middleware" that:
- Strips noise from tool outputs
- Compresses repetitive file paths  
- Removes stale content from old conversation rounds
- Routes simple tasks to cheaper models
- Preserves cache benefits when possible

All transparent to the IDE - Cursor doesn't know compression is happening.


================================================================================
## THE PROBLEM
================================================================================

Using Cursor with expensive models (GPT-4o, Claude Opus, etc.) gets costly:

- Long agentic sessions can reach 100K+ tokens per turn
- Cursor sends full conversation history + all file contents every time
- Tool outputs are full of boilerplate noise
- Same files get re-read and sent multiple times
- Most turns don't need the most expensive model

Result: $5-10+ per complex session, adding up fast.


================================================================================
## THE SOLUTION
================================================================================

This proxy implements a multi-phase compression strategy:

**Phase 1: Pre-send Preprocessing (ACTIVE)**
✓ Strip boilerplate noise from tool outputs (~8% savings)
✓ Compress repetitive file paths (~4% savings)
✓ Applied BEFORE sending (no cache to break)

**Phase 2: Context Limits + TTL Tracking (PLANNED)**
- Prevent "prompt too long" errors
- Track cache expiry (5-minute TTL)
- Switch to aggressive compression when cache is gone

**Phase 3: Cache-Aware Compression (PLANNED)**
- Compress old history into stable boundaries
- Preserve cache benefits (85%+ hit rate target)
- Deduplicate stale file reads
- Provider-specific cache markers (Anthropic, OpenAI, Google)

**Phase 4: A/B Testing (PLANNED)**
- Empirically discover optimal strategy per provider
- Test continuously from Phase 1 onwards
- Measure: cost, cache effectiveness, quality

**Phase 5: Dynamic Model Routing (PLANNED)**
- Route simple tasks to cheap models (Gemini Flash)
- Route complex tasks to expensive models (Claude Opus)
- 90%+ cost savings potential


================================================================================
## ARCHITECTURE
================================================================================

    [Cursor IDE]
        |
        | Custom OpenAI endpoint: http://localhost:8000/v1
        v
    [Context Optimizer Proxy]
        |
        ├─> Preprocessing (noise, paths)
        ├─> TTL tracking (cache expiry)
        ├─> Boundary compression (old history)
        ├─> Provider routing (Anthropic/OpenAI/OpenRouter)
        |
        v
    [LLM Provider API]
        |
        v
    [Streaming response back to Cursor]


================================================================================
## CURRENT STATUS
================================================================================

**Implemented (V1):**
✓ OpenAI-compatible API endpoint (/v1/chat/completions)
✓ Streaming responses
✓ Direct Anthropic routing (bypasses OpenRouter for Claude models)
✓ OpenRouter support for other models
✓ Session logging (full + minimal modes)
✓ Web UI for viewing session logs
✓ Basic token estimation and metrics
✓ Model aliases for Cursor compatibility

**In Progress:**
- Phase 1 implementation (noise stripping, path compression)
- A/B testing framework

**Planned:**
- Phase 2: TTL tracking and context limits
- Phase 3: Cache-aware boundary compression
- Phase 4: Comprehensive A/B testing per provider
- Phase 5: Dynamic model routing


================================================================================
## QUICK START
================================================================================

1. Follow **Install** above (venv, `pip install -r requirements.txt`, `.env` from `.env.example`).

2. Start the proxy (from `context_optimizer` with venv activated):
   ```bash
   python main.py
   ```
   If Cursor cannot use `localhost`, expose it (example):
   ```bash
   ngrok http 8000
   ```
   Use that public base URL wherever you configure the OpenAI-compatible endpoint (append `/v1` as needed).

3. Configure Cursor:
   - Settings → Models → OpenAI API Key / custom endpoint section
   - Base URL: `http://localhost:8000/v1` or `https://<your-ngrok-host>/v1`
   - Use model aliases such as: `co-gpt-4o`, `co-claude-sonnet-4-5`, etc.

4. Optional: open the session UI in a browser:
   `http://localhost:8000/ui`


================================================================================
## DOCUMENTATION STRUCTURE
================================================================================

docs/
├── README.md                        - Index / where to start
├── planning/
│   ├── goal.md                      - Problem statement and requirements
│   ├── design.md                    - System architecture (overview)
│   ├── backlog.md                   - Deferred features
│   └── fixes_2026-05-15.md         - Session notes / fixes log
├── guides/
│   ├── terminology.md               - Session vs turn vs round
│   └── logging_guide.md             - Session logging modes and disk use
├── research/
│   ├── compression_research.md      - Findings from real sessions
│   ├── ab_testing_strategy.md       - Experimental testing plan
│   └── cache/                       - Prompt caching engineering notes
│       ├── prompt_caching_explained.md
│       ├── cache_granularity.md
│       ├── cache_boundaries_explained.md
│       ├── cache_ttl_behavior.md
│       ├── proxy_boundary_management.md
│       ├── removal_vs_compression.md
│       └── provider_caching_comparison.md
└── implementation/
    └── IMPLEMENTATION_PLAN.md         - Phased build order and tasks


================================================================================
## KEY INSIGHTS FROM RESEARCH
================================================================================

From analyzing real agentic sessions (see `docs/research/compression_research.md`):

1. Tool noise: 8% of history is boilerplate we can safely strip
2. Path compression: 3.8% savings by aliasing common paths  
3. System prompt bloat: 8K-10K tokens, can use adaptive templates
4. Stale file reads: Same files read 3-5 times, keep only latest
5. Old conversation history: 40%+ of old rounds become irrelevant
6. Model routing opportunity: 90% of turns could use cheaper models
7. Cache-aware design is CRITICAL: naive compression breaks cache benefits
8. TTL tracking matters: cache expires after 5 min idle (coffee break cost!)
9. OpenRouter disables caching: must use aggressive compression there


================================================================================
## CONFIGURATION
================================================================================

Key .env settings:

# Logging
ENABLE_LOGGING=true
ENABLE_FULL_SESSION_LOGGING=false  # Set true to collect training data
LOG_DIR=logs
DEBUG_BUFFER_SIZE=5

# Models  
CHEAP_MODEL_NAME=openrouter/google/gemini-2.0-flash-lite-001
DEFAULT_BACKEND=openrouter

# Compression (Phase 1)
ENABLE_NOISE_STRIPPING=true
ENABLE_PATH_COMPRESSION=true
BYPASS_COMPRESSION=false  # Debug flag

# Future phases (not yet implemented)
ENABLE_CONTEXT_LIMIT_CHECK=false
ENABLE_TTL_TRACKING=false
ENABLE_BOUNDARY_COMPRESSION=false
ENABLE_DYNAMIC_ROUTING=false


================================================================================
## TESTING
================================================================================

Run test script:
python test_proxy.py

View session logs in browser:
http://localhost:8000/ui

Enable full logging for data collection:
# In .env:
ENABLE_FULL_SESSION_LOGGING=true

# WARNING: Uses significant disk space!
# Only enable when collecting training data


================================================================================
## MODEL ALIASES
================================================================================

Use these model names in Cursor to route through the proxy:

Prefixed with "co-" (Cursor-friendly):
- co-gpt-4o
- co-gpt-4o-mini  
- co-claude-sonnet-4-5
- co-claude-opus-4
- co-deepseek-chat
- co-gemini-2.0-flash

Direct OpenRouter format (if Cursor allows):
- openrouter/anthropic/claude-3.5-sonnet
- openrouter/google/gemini-2.0-flash-001
- etc.


================================================================================
## WHY THIS APPROACH?
================================================================================

**Why not use existing tools?**
- Context-Gateway: Requires proprietary API, limited customization
- LiteLLM: Great for routing, but no compression logic
- Provider-side compression: Cursor doesn't compress for custom endpoints

**Why build our own?**
- Full control over compression strategy
- Can implement cache-aware compression
- Can do A/B testing to find optimal strategy
- Can route dynamically based on task difficulty
- Learning opportunity from real session analysis


================================================================================
## COST SAVINGS ESTIMATES
================================================================================

Based on research (see `docs/research/compression_research.md`):

Phase 1 (preprocessing):           10-12% token reduction
Phase 2 (context limits + TTL):    Prevents errors, enables aggressive mode
Phase 3 (boundary compression):    20-30% additional savings
Phase 4 (optimal strategies):      Provider-specific tuning
Phase 5 (dynamic routing):         90%+ total cost reduction

Example: 22-turn calculator app session
- Without optimization: 374K tokens on Opus = $5.61
- With full optimization: 156K tokens routed intelligently = $0.17
- Savings: 97%


================================================================================
## NEXT STEPS
================================================================================

1. Implement Phase 1 (Week 1):
   - Task 1.1: Noise stripping
   - Task 1.2: Path compression
   - Task 1.3: Integration
   - Task 1.4: A/B testing

2. Collect more session data:
   - Enable ENABLE_FULL_SESSION_LOGGING=true
   - Run several complex coding sessions
   - Analyze patterns for Phase 3 optimization

3. Continue with Phase 2:
   - Implement TTL tracking
   - Add context limit safety
   - Test TTL-aware compression strategies

See `docs/implementation/IMPLEMENTATION_PLAN.md` for the detailed roadmap.


================================================================================
## CONTRIBUTING
================================================================================

This is a personal tool/research project. If you find it useful:

1. Star the repo
2. Share your session analysis findings
3. Test different compression strategies
4. Report what works best for your use case


================================================================================
## LICENSE
================================================================================

MIT License - Use freely, modify as needed.


================================================================================
## RESOURCES
================================================================================

Documentation: Start at `docs/README.md`, then `docs/implementation/IMPLEMENTATION_PLAN.md`.

Session Viewer: http://localhost:8000/ui

Logs Directory: `logs/sessions/` (gitignored — see `.gitignore`)

Key docs:
- `docs/research/compression_research.md` — What to compress and why
- `docs/research/cache/provider_caching_comparison.md` — Provider caching behavior
- `docs/research/ab_testing_strategy.md` — How to test strategies empirically


================================================================================
Last updated: May 15, 2026
Version: 0.1.0 (Phase 1 in progress)
================================================================================
