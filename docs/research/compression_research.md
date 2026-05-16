# Compression Research — Findings Log

Analysis based on 2 real agentic sessions captured via the proxy logger.

**Sessions analyzed:**
- `session_43895d83` — 22 turns, GPT-5.5, task: build calculator app from scratch
- `session_d12edddd` — 14 turns, DeepSeek v4 Flash, task: restyle + fix bug (carries over session 1 history)

---

## Finding 1 — Tool result noise (boilerplate stripping)

**What:** Tool results from Cursor's shell/file runners contain repeating boilerplate that carries zero information for the LLM.

**Patterns identified:**

| Pattern | Example | Occurrences (last turn) | Chars |
|---|---|---|---|
| Shell timing | `Command completed in 299 ms.` | 10 | 287 |
| Shell state note | `Shell state (cwd, env vars) persists for subsequent calls.` | 10 | 580 |
| CWD note | `Current directory: /Users/...` | 10 | 761 |
| Exit code header | `Exit code: 0\n\nCommand output:\n\n\`\`\`` | 10 | 350 |
| Code fence close | `\`\`\`\n\n` | 20 | 100 |
| TODO boilerplate | `Make sure to follow and update your TODO list...` | 4 | 652 |
| TODO header | `Here are the latest contents of your todo list:` | 4 | 192 |
| Sandbox note | `This command ran outside the sandbox (no restrictions)...` | 10 | 2,723 |

**Total identifiable noise: ~5,645 chars = 8% of full context (last turn)**

**Implementation:** Pure regex substitution, no LLM call, applied to tool_result content blocks only.

**Risk:** Very low. These strings appear in tool results, never in LLM-generated text or user messages.

**Status:** Not yet implemented.

---

## Finding 1b — Vertical whitespace & commented code (tool output only)

**What:** Source and tool output often contain extra vertical padding (blank lines, lines with only spaces) and sometimes large blocks of commented-out code. Stripping these before the payload reaches the model can shave tokens with almost no semantic loss — but savings are **small per file** and only add up over many reads or long sessions.

**Empty / whitespace lines:**

| Action | Typical savings | Risk |
|---|---|---|
| Collapse 2+ consecutive blank lines → 1 | ~0–1 token per removed `\n` | Very low if applied to **tool_result text only** |
| Trim trailing spaces per line | Small | Low |
| Remove **all** newlines in Python | N/A | **Breaks syntax** — do not do this on real source |

**Rule of thumb:** ~**4 chars ≈ 1 token** (our estimator). One extra blank line is often **~0–1 token**; 100 blank lines in a repeated `Read` might save **~25–100 tokens** — noticeable in huge logs, not next to a 4k-token shell dump.

**Commented code (optional, higher risk):**

- **Maybe useful** when tool output is clearly *for reading* (e.g. `Read` of a file the model is inspecting), not when it is the payload for `Write` / `StrReplace`.
- **Do not strip comments from tool *inputs*** or from content the user asked to keep — that would change what gets written to disk and violates “don’t remove lines from the user’s code.”
- **Line-number problem:** If we drop commented lines without a **line map** (`original_line → compressed_line`), any message like “fix line 42” or stack traces with line numbers become wrong. Safer options:
  - Only collapse blank lines (preserve line numbers), or
  - Strip comments but prefix each kept line with `L123:` (heavy), or
  - Defer comment stripping until we have explicit line mapping.

**Where to apply:** Same boundary as Finding 1 — **`tool_result` content blocks only** (and similar read-only context), never user messages, never assistant text, never `tool_use` arguments that will be executed or written.

**Implementation sketch (Layer 1, optional):**

```python
def compress_vertical_whitespace(text: str) -> str:
    # Collapse 3+ newlines to 2; strip trailing whitespace per line
    ...

# Comment stripping: OFF by default; enable only with line-preserving strategy
ENABLE_COMMENT_STRIP_IN_TOOL_RESULTS=false
```

**Status:** Not yet implemented. **Priority:** low — add after noise/path stripping; validate on A/B `Read`-heavy scenarios. Good “long tail” win, not a primary lever.

---

## Finding 2 — Path stem repetition

**What:** The base path `/Users/amir/Dropbox/CodingProjects` (36 chars) repeats on every file path in tool calls, tool results, and assistant messages.

**Data:**

| Session | Occurrences of stem | Total stem chars | Saved if → `$C` (2 chars) | % of context |
|---|---|---|---|---|
| Session 1 (22 turns) | 75 | 5,217 | 2,400 chars | 2.4% |
| Session 2 (14 turns) | 114 | 8,170 | 3,648 chars | 2.4% |

**Top full paths (session 2, most repeated):**

| Count | Full path |
|---|---|
| 33x | `$C/personal_tools/test_app` |
| 22x | `$C/personal_tools/test_app/src/App.tsx` |
| 12x | `$C/personal_tools/test_app/eslint.config.js` |
| 10x | `$C/personal_tools/test_app/node_modules/vite/...` |

**Note:** Savings scale with how many times the same file is repeatedly touched. In a bug-fix session where the LLM edits the same file 10+ times, this matters more.

**Implementation approach:**
1. Detect workspace root from the request's `workspacePath` field in the system prompt (Cursor always includes it).
2. Replace `workspacePath` value → `$W` (workspace), base CodingProjects stem → `$C`.
3. Add a legend line to the system message: `$W = /Users/amir/.../test_app, $C = /Users/amir/Dropbox/CodingProjects`
4. No need for dynamic per-session variable mapping — just two fixed aliases per session.

**Risk:** Low, but must be careful not to replace inside JSON strings being written to files (would corrupt file content tool inputs). Only apply to tool_result text, not tool_use inputs.

**Status:** Not yet implemented.

---

## Finding 3 — Old turn summarization

**What:** In a multi-task session, earlier completed tasks accumulate as dead weight in the history.

**Data (session 2):**
- Turn 1 starts with 64 messages already (carried from session 1).
- At turn 11 (new task: fix bug), turns 1–10 are a fully completed styling task — irrelevant to the debug.
- Old messages (turns 1–15): **95.3% of full context** (66,852 / 70,175 chars).
- Recent messages (turns 16–22): only **4.7%** (3,322 chars).

**Key constraint:** Cannot split tool_use / tool_result pairs. Must summarize complete "rounds" (one tool_use + its tool_result = one round). Splitting a pair causes "Tool '' not found" errors from the LLM provider.

**Potential savings:** Up to ~20% on long sessions, but only applies to conversation history — the ~12K system prompt + tool definitions overhead is untouchable.

**Trigger point:** When a new user task begins (last user message differs from previous), compress all fully resolved prior rounds.

**Status:** Deferred. Requires round grouping + LLM summarization call. Needs careful implementation to avoid breaking tool call chains.

---

## Finding 4 — Incremental turn growth is tiny

**What:** After the initial 12K system prompt overhead, each proxy turn only adds 22–628 tokens of new content.

**Data (session 1):**
- Turn 1: 12,156 tokens (system prompt + tool defs dominate)
- Turn 22: 17,528 tokens
- **Net conversation growth over 22 turns: only 5,372 tokens**

**Implication:** Compression ROI is limited on short sessions. It becomes significant only when:
- Sessions run long (30+ turns), OR
- A new task starts while carrying old history (cross-task growth)

---

---

## Finding 5 — Model can re-fetch dropped content

**Insight:** If we remove an old tool_result (e.g. "read App.tsx → 300 lines"), the expensive model will simply re-call `Read("App.tsx")` if it needs it again. Cursor executes tools locally — the re-fetch cost is near-zero.

**Implication:** We don't need to summarize old tool results. We can drop them entirely and let the model re-request if needed. This is safer than summarization (no hallucination risk) and cheaper (no LLM output tokens).

**What to keep vs drop:**
- Keep: `tool_use` block (so model knows what was called)
- Drop: `tool_result` content → replace with `[removed — re-call tool if needed]`
- Never drop: user messages, assistant reasoning text, last N turns

---

## Finding 6 — Relevance classification architecture

**Design:** Use the cheap model as a **relevance classifier**, not a summarizer. Much cheaper and safer.

**Pipeline (layered, cheapest first):**

```
Layer 1 — Always on, free (<1ms, pure regex)
  • Strip noise patterns from tool results (saves ~8%)
  • Collapse extra blank lines / trim trailing whitespace in tool results (small; accumulates on long sessions)
  • Replace path stem /Users/amir/Dropbox/CodingProjects → $C (saves ~2.4%)
  • Replace workspace root → $W (saves ~1.4%)
  Total guaranteed savings: ~12%, zero LLM cost

Layer 2 — Triggered when tokens > threshold (e.g. 16K)
  Input to cheap model (~500 tokens):
    "Current task: [last 2 user messages]
     Old rounds (headers only): 
       Round 1: Read(App.tsx) → 287 lines
       Round 2: Shell(npm install) → ok
       ...
     Return comma-separated round numbers still relevant."
  Output (~10 tokens): "1, 3, 7"
  Action: strip tool_result content from all other rounds → [removed]
  Cost: essentially free

Layer 3 — Future, for very long sessions (tokens still > 30K after layer 2)
  Summarize remaining old rounds into a single context note
```

**Server-side full history store:**
- Server always keeps the complete unmodified history in memory (per session)
- Layers 2 and 3 are filters on what gets forwarded, not on what gets stored
- If a round marked irrelevant becomes relevant again, the server can restore it from its store
- No data is ever permanently lost

**Round header format (for cheap model input):**
```
Round 3: Read("/path/App.tsx") → 287 lines [assistant decided to fix line 18]
Round 4: Write("/path/App.tsx") → ok
Round 5: Shell("npm run build") → exit 2, error: TS2882
```
Only tool name + args + brief result + any assistant reasoning. Never the full content.

**Preprocessing — Deterministic stale file deduplication (free, before cheap model):**

Before asking the cheap model about relevance, auto-detect and remove stale file reads:
```python
# If the same file was Read() multiple times, keep only the MOST RECENT
# Mark older reads: tool_result content → "[stale — file re-read at turn X]"
```

Example:
```
Turn 5:  Read(App.tsx) → [287 lines v1]
Turn 7:  Write(App.tsx)
Turn 9:  Read(App.tsx) → [287 lines v2]
Turn 22: (current)

After deduplication:
Turn 5:  Read(App.tsx) → [stale — file re-read at turn 9]
Turn 9:  Read(App.tsx) → [287 lines v2] ← kept if relevant
```

This preprocessing happens before the cheap model sees the rounds, so the model never wastes tokens asking about stale file content. **Benefit:** not just saving tokens — avoiding confusion from outdated code.

**Status:** Not yet implemented. Planned after Layer 1 is validated.

---

---

## Finding 7 — Rule/MCP gating via cached index

**What:** Cursor sends ALL workspace rules, user rules, and MCP descriptions on every request. Most are irrelevant to the current task. They dominate the system prompt cost.

**Cost breakdown (session 1, turn 1 — 12,156 tokens total):**

| Section | Chars | Tokens | Controllable |
|---|---|---|---|
| `<rules>` (book-agent rule) | 21,673 | ~5,400 | Yes — yours |
| `<mcp_file_system>` | 9,678 | ~2,400 | Partially |
| `<citing_code>` | 4,499 | ~1,100 | No — Cursor |
| `<agent_skills>` | 4,949 | ~1,200 | Yes — yours |
| `<user_rules>` (Tailwind + coding) | 4,828 | ~1,200 | Yes — yours |
| Everything else | ~3,000 | ~750 | No — Cursor |

**Key insight:** ~8,400 tokens per request are your own rules/skills — sent even when completely irrelevant (book-agent on a calculator task).

### Design: Unified cheap model call for rule gating + history relevance

**Combined evaluation** — one cheap model prompt handles both:
1. Which rules/MCPs are relevant to the current task
2. Which old rounds are still relevant (when history is long)

**Step 1 — Build index (once per rule change, cached):**

```python
cache_key = md5(rules_content + mcp_content)
if cache_exists(cache_key):
    index = load_cache(cache_key)
else:
    # Send to cheap model: extract name, description, keywords, importance for each section
    index = cheap_model_build_index(system_prompt_sections)
    save_cache(cache_key, index)
```

Cache persists across sessions. Only rebuilt when rules actually change on disk.

**Step 2 — Per-turn unified gating (cheap model, triggered selectively):**

Cheap model call triggered when:
- New user task detected (last user message differs from previous)
- OR history exceeds threshold (e.g. >16K tokens) AND hasn't been evaluated recently

```python
# Input to cheap model (~1,000 tokens)
prompt = f"""
Current task: {last_user_message}
Workspace: {workspace_path}

PART A — Rule relevance
Available rules: {list_of_rules_with_descriptions_from_index}
Which rules apply? Reply with names only.

PART B — History relevance (if history > threshold)
Recent work (last 3 turns): {recent_summary}
Old rounds (headers only):
  Round 1: Read(App.tsx) → 287 lines
  Round 2: Shell(npm install) → ok
  ...
Which old rounds are still relevant? Reply with numbers only.
"""

# Output (~20 tokens): "Rules: coding-principles | Rounds: 1, 3, 7"
```

**Step 3 — Apply decisions:**
- Strip non-relevant rules from system prompt
- Strip tool_result content from non-relevant old rounds → `[removed]`

**Frequency in practice (22-turn session, 3 tasks):**

| Turn range | Trigger | Cheap model calls |
|---|---|---|
| Turns 1-10 (task 1) | Index build + initial gate | 1 |
| Turn 7 | History > 16K | 1 |
| Turn 11 (new task) | New user message | 1 |
| Turn 18 | History > 24K | 1 |

Total: **4 cheap model calls across 22 turns** instead of 22 separate calls. Each call handles both rule gating and history relevance, so the model has full context to make better decisions.

**Expected savings (non-book session):**
- Strip book-agent rule: ~15,800 chars (~3,950 tokens)
- Strip book-agent MCP description: ~4,200 chars (~1,050 tokens)
- Strip Tailwind rule (Python/backend task): ~2,800 chars (~700 tokens)
- **Total: ~5,700 tokens saved per turn, every turn**

Combined with Layer 1 (noise + paths): potentially **~50% reduction on system prompt overhead**.

**Status:** Not yet implemented. Highest priority — applies to every turn regardless of session length.

---

## Summary Table

| Impl Order | Layer | Technique | Savings | LLM needed | Notes |
|---|---|---|---|---|---|
| **Phase 1: Data Collection** | — | Enhanced session logging | — | No | Add metadata: task keywords, file counts, model performance |
| **Phase 2: Deterministic (safe, immediate)** |
| 1 | 1 | Strip tool noise (8 patterns) | ~8% of history | No | Safe, pure regex, zero risk |
| 1b | 1 | Collapse blank lines / trim WS (tool results) | Small; long-session tail | No | Do not strip all `\n`; comment strip needs line map |
| 2 | 1 | Path stem → `$C` / workspace → `$W` | ~3.8% of history | No | Combine with noise |
| 3 | 1 | Dedupe stale file reads | Variable | No | Improves quality, removes confusion |
| **Phase 3: Prompt optimization (needs minimal data)** |
| 4 | 0 | **Adaptive system prompt (task templates)** | **~8,000-10,000 tok/turn** | Cheap (heuristics initially) | **Highest token savings** — start with keyword rules |
| 5 | 0 | Rule/MCP gating via cached index | ~5,700 tok/turn | Once per rule change (cheap) | **Subsumed by #4** if implemented |
| **Phase 4: History compression (needs validation data)** |
| 6 | 2 | Relevance classification → drop old tool_result content | up to ~40% on long sessions | Cheap (headers in, numbers out) | Validate on collected sessions |
| 7 | 2 | Old turn summarization | up to ~20% | Yes (summarizer) | Only if classification insufficient |
| **Phase 5: Model routing (needs significant data + possibly ML)** |
| 8 | 0 | **Dynamic model routing per turn** | **90-99% cost savings** | **Train classifier on real data** | **Highest cost impact** — implement LAST after data collection |
| — | — | Per-file path variables | <1% | No | Skip |

---

## Finding 8 — Dynamic model routing per turn

**What:** Not all turns need an expensive model. Most agentic turns are simple (scaffold files, fix typos, run commands). The cheap model can route each turn to an appropriate-tier model based on difficulty.

**The opportunity:** In a typical 22-turn session building a calculator app, most turns are straightforward. Only a few require deep reasoning. Routing simple turns to Flash and medium turns to Sonnet (vs always using Opus) saves 10-100x per turn on model cost.

**Combined with compression:** Routing and compression compound. A turn that would be 17K tokens on Opus becomes:
- 8.5K tokens (compressed) on Flash (if simple)
- 8.5K tokens on Sonnet (if medium)
- 17K tokens on Opus (if truly hard) ← only when necessary

**Design: Unified cheap model call (extended)**

The same cheap model that gates rules and history also decides routing:

```
Cheap model input (~1,200 tokens):
  "Current task: fix decimal button bug
   Recent work: [last 3 turns summary]
   
   PART A: Which rules apply?
   PART B: Which old rounds relevant?
   PART C: Difficulty assessment for THIS specific turn:
     - simple: typo fix, add comment, scaffold boilerplate, run commands
     - medium: implement feature, refactor component, debug logic
     - hard: architecture design, complex algorithm, security/performance deep-dive
   
   Reply: difficulty=simple|medium|hard"

Output (~30 tokens):
  "Rules: coding-principles | Rounds: 3, 7 | Difficulty: simple"

→ Route to gemini-2.0-flash instead of opus
```

**Model tier table (.env):**

```bash
# User-requested model (from Cursor) acts as the CEILING — never route higher
# Example: User picks sonnet → can route to flash/sonnet, never opus
MODEL_TIER_SIMPLE=openrouter/google/gemini-2.0-flash
MODEL_TIER_MEDIUM=openrouter/anthropic/claude-3.5-sonnet
MODEL_TIER_HARD=openrouter/anthropic/claude-3-opus

# Override rules (force tier regardless of cheap model decision)
FORCE_HARD_KEYWORDS=architecture, design system, refactor everything, security audit, performance analysis
FORCE_SIMPLE_KEYWORDS=typo, add comment, format code, lint fix, run command
```

**Auto-escalation** — if the cheap model makes a mistake:

```python
# If model gets stuck on "simple" turn after 3 attempts, escalate
if turn_count > 3 and same_error_repeated:
    escalate_tier()  # simple → medium → hard
```

**Estimated savings (22-turn calculator session):**

Assume user picked `claude-3-opus` in Cursor (ceiling = opus):

| Turns | Task | Classified as | Routed to | Tokens (compressed) | Cost |
|---|---|---|---|---|---|
| 1-8 | Scaffold files, npm install | simple | flash | 8 × 6K = 48K | $0.01 |
| 9-12 | Fix eslint errors | simple | flash | 4 × 7K = 28K | $0.01 |
| 13-18 | Style UI (iterative) | medium | sonnet | 6 × 8K = 48K | $0.14 |
| 19-22 | Debug decimal bug | simple | flash | 4 × 8K = 32K | $0.01 |

**Total: 156K tokens, ~$0.17** (vs 374K tokens on opus without compression/routing = $5.61)

**Savings: 97% cost reduction**

**IMPORTANT: Implementation approach (data-driven)**

This finding describes the theoretical opportunity, but **routing should be implemented LAST** after collecting real usage data.

**Why data-driven approach is critical:**

1. **Quality risk**: Misrouting a hard task to a cheap model causes errors, wasted retries, and user frustration
2. **Cost of mistakes**: False negatives (routing "hard" to "simple") cost more than false positives
3. **Unknown patterns**: We don't yet know what truly predicts task difficulty in real usage
4. **Model self-awareness**: The LLM itself might be better at predicting what the *next* turn needs

**Proposed data collection (Phase 1):**

Enhance session logging to capture routing-relevant metadata:

```python
# Add to each turn log entry:
{
  "turn": 5,
  "model": "claude-3-opus",
  "tokens": 7100,
  "user_message_length": 45,
  "file_count_in_context": 3,
  "tool_calls_in_turn": 2,
  "errors_in_previous_turn": false,
  "task_keywords": ["debug", "decimal", "button"],
  "time_to_first_token_ms": 1234,
  "total_response_time_ms": 5678,
  # Quality indicators:
  "user_edited_result": false,  # Did user immediately correct output?
  "retry_same_task": false,     # Did user ask to redo?
  "escalated_to_harder_model": false
}
```

**Phase 5 implementation options:**

**Option A: Train simple classifier**

After collecting 50-100 sessions:

```python
# Features for classification:
- user_message_keywords (typo, fix, add, refactor, architecture, etc.)
- file_count (1 file = simple, 10+ files = complex)
- history_length (new task vs 20-turn deep session)
- tool_types_requested (Read only = simple, Write+Shell+Git = complex)
- previous_turn_errors (stuck = escalate)

# Labels:
- simple (flash worked without retry)
- medium (sonnet worked)
- hard (opus needed, or flash/sonnet failed)

# Simple model: sklearn RandomForestClassifier or even decision tree
```

**Option B: LLM self-assessment**

Ask the model at the END of each turn what the next turn should use:

```python
# After model completes turn N, append to response:
assistant_message += """

[Internal routing decision for next turn:
 Based on this interaction, I assess the next turn will likely be:
 - simple (if: typo fix, add comment, run command)
 - medium (if: implement feature, debug logic)
 - hard (if: architecture, complex algorithm)
 
 My assessment: medium
 Confidence: 0.8
]
"""
# Proxy intercepts this, removes from user-visible output, uses for next turn routing
```

**Option C: Hybrid (keywords + ML + model input)**

```python
# Priority order:
1. Check FORCE_HARD_KEYWORDS / FORCE_SIMPLE_KEYWORDS (override)
2. If last turn model said "next: hard" → use that
3. Else: classifier prediction from collected data
4. Auto-escalate if model gets stuck
```

**Logging for validation:**

```json
{
  "turn": 5,
  "user_requested_model": "claude-3-opus",
  "cheap_model_decision": "simple",
  "routed_to": "gemini-2.0-flash",
  "tokens_before_compression": 14200,
  "tokens_after_compression": 7100,
  "cost_without_routing": "$0.21 (14200 tok opus)",
  "actual_cost": "$0.002 (7100 tok flash)",
  "savings": "99%"
}
```

**Status:** **Phase 5 — Implement LAST after data collection.** Requires 50-100 logged sessions to train classifier or validate LLM self-assessment. Highest cost savings but also highest quality risk if done prematurely.

---

## Finding 9 — Adaptive system prompt (task-specific templates)

**Observation:**

Looking at the system prompt structure in our logs, Cursor sends a comprehensive system prompt that includes:
- Coding principles and best practices (~2,000 tokens)
- Tool usage instructions (~1,500 tokens)
- Mode selection guidance (~800 tokens)
- MCP server descriptions (~1,200 tokens per server)
- Git workflow instructions (~600 tokens)
- Rules (user-defined, workspace-defined) (~500-5,000 tokens)
- Agent skills (~300 tokens per skill)
- Professional objectivity notes (~200 tokens)
- Task management guidance (~300 tokens)
- Ambition / multi-turn instructions (~400 tokens)

**Total system prompt: ~8,000-15,000 tokens** (varies by workspace)

**Key insight:** Not all sections are relevant to every task.

**Examples of mismatched sections:**

| Task | Irrelevant sections | Wasted tokens |
|---|---|---|
| "Fix typo in README" | Git workflow, mode selection, ambition, task management | ~2,300 |
| "Run npm install" | Coding principles, tool instructions, skills | ~3,800 |
| "Read this file" | Git workflow, mode selection, professional objectivity | ~1,600 |
| "Explain this code" | Git workflow, task management, ambition | ~1,300 |

**Simple tasks (typo fixes, single reads, command execution) don't need complex multi-turn planning, git instructions, or mode switching.**

**Proposal: Task-based prompt library**

Build a library of curated system prompts for common task categories:

1. **Minimal prompt** (read-only, explanations, simple edits):
   - Tool basics (Read, Grep, Glob only)
   - Citing code rules
   - Skip: git, mode selection, task management, ambition
   - **Size: ~2,000 tokens**

2. **Standard prompt** (typical coding tasks):
   - Tool instructions (all tools)
   - Coding principles
   - Linter handling
   - Skip: git workflow details, ambition notes
   - **Size: ~4,500 tokens**

3. **Full prompt** (complex multi-file refactors, architecture):
   - Everything (current behavior)
   - **Size: ~8,000-15,000 tokens**

4. **Git-focused prompt** (PR work, commits, branches):
   - Git workflow (full detail)
   - Tool instructions
   - Coding principles
   - Skip: mode selection, ambition
   - **Size: ~5,000 tokens**

**Classification:** Use the cheap model (same unified call as rule gating / model routing) to classify task into one of these categories based on the user's first message.

**Cheap model prompt (add Part D to unified call):**

```
D. Classify this task into one of these prompt templates:
   - minimal (read/explain/simple edit)
   - standard (typical coding)
   - full (architecture/refactor/complex)
   - git (PR/commit/branch work)

   Output: {"template": "standard"}
```

**Estimated savings:**

Assume 40% of turns are "minimal" or "standard" tasks:

- Minimal template: saves 6,000-13,000 tokens vs full prompt
- Standard template: saves 3,500-10,500 tokens vs full prompt

**Example (22-turn calculator session):**

| Turns | Task | Template | Tokens saved |
|---|---|---|---|
| 1-8 | Scaffold files | standard | 8 × 5K = 40K |
| 9-12 | Fix eslint | minimal | 4 × 8K = 32K |
| 13-18 | Style UI | standard | 6 × 5K = 30K |
| 19-22 | Debug bug | standard | 4 × 5K = 20K |

**Total saved: ~122K tokens** (vs full prompt every turn)

Combined with Finding 7 (rule gating within a template), this could save **8,000-10,000 tokens per turn** on average.

**Additional benefit: Prompt quality**

Task-specific prompts can be *better* than one-size-fits-all:
- Minimal prompt → faster inference, less distraction for simple tasks
- Git prompt → more detailed git guidance when needed
- Full prompt → all context for complex work

**Implementation:**

```python
# Part D of unified cheap model call
cheap_model_prompt += """
D. Select the appropriate system prompt template for this task:
   - minimal: read/explain/simple single-file edit/run command
   - standard: typical coding (multiple files, moderate complexity)
   - full: architecture/refactor/security audit/complex multi-step
   - git: PR review/commit/branch management/git operations

   Consider: task complexity, number of files, planning required, git operations mentioned

   Output: {"prompt_template": "standard"}
"""

# After cheap model response
template_name = cheap_response["prompt_template"]
system_prompt = load_prompt_template(template_name, relevant_rules, relevant_mcps)
```

**Prompt template files:**

```
prompts/
  minimal.txt        # Core tool usage + citing code
  standard.txt       # + coding principles + linter handling
  full.txt          # + mode selection + task mgmt + ambition
  git.txt           # + full git workflow details
  
  # Shared sections (injected as needed):
  _rules_header.txt
  _mcp_header.txt
  _tools_section.txt
```

**Caching strategy:**

- Template files are static (rarely change) → cache in memory
- Rules/MCPs are dynamic → inject based on cheap model decision (Finding 7)
- Final prompt = `base_template + relevant_rules + relevant_mcps`

**Relationship to Finding 7:**

| Finding | Scope | Granularity | Savings |
|---|---|---|---|
| Finding 7 | Rules/MCPs only | Per-rule gating | ~5,700 tok/turn |
| Finding 9 | Full system prompt | Template selection | ~8,000-10,000 tok/turn |

Finding 9 subsumes Finding 7 (template selection includes rule gating).

**Status:** Not yet implemented. Can be added as Part D to the unified cheap model call. Requires building prompt template library.

---

## Implementation Plan

### CRITICAL: Cache-Aware Implementation

**Before implementing ANY compression strategy, understand that prompt caching fundamentally changes the cost equation.**

#### The Cache Reality

Most major LLM providers (Anthropic, OpenAI, Google) now support prompt caching:
- Cached tokens: ~$0.30/M (90% discount)
- New tokens: ~$3/M (full price)
- TTL: 5 minutes from last use
- Resets on every access (stays alive during active sessions)

**Key insight:** Compression that breaks cache can INCREASE costs instead of reducing them.

#### Cache-Aware Rules (MUST FOLLOW)

1. **Establish stable boundaries** (see `cache/cache_boundaries_explained.md`)
   - Compress once per layer, then freeze
   - Don't recompress constantly (breaks cache every turn)
   - Use cache_control markers (Anthropic) to create independent cache entries

2. **Bundle compressions together**
   - Compress multiple boundaries in ONE turn
   - Don't spread compressions across turns (causes repeated cache rebuilds)

3. **Compression timing strategy**
   ```
   Turn 1-9:  No compression (let cache build)
   Turn 10:   Compress layers 1-3 together → one-time cache rebuild
   Turn 11+:  All layers cached again, compression pays off
   Turn 20:   Compress next layer → only that layer rebuilds
   Turn 21+:  Back to high cache hit rate
   ```

4. **Cost calculation with cache**
   ```
   Without compression (20 turns, 18K tokens/turn):
   - 360K total tokens
   - 92% cached: 331K × $0.30/M = $0.099
   - 8% new: 29K × $3/M = $0.087
   - Total: $0.186

   With naive compression (breaks cache every turn):
   - 280K total tokens (compressed)
   - 60% cached: 168K × $0.30/M = $0.050
   - 40% recomputed: 112K × $3/M = $0.336
   - Total: $0.386 ← WORSE! 2× more expensive

   With cache-aware compression (stable boundaries):
   - 240K total tokens (compressed)
   - 88% cached: 211K × $0.30/M = $0.063
   - 12% new: 29K × $3/M = $0.087
   - Total: $0.150 ← BETTER! 20% savings
   ```

5. **Test compression strategies**
   - Always measure: cache hit rate BEFORE and AFTER compression
   - Target: maintain >85% cache hit rate
   - If hit rate drops below 70%: compression strategy is TOO aggressive

6. **Session breaks kill cache**
   - Coffee break (>5 min) → cache expires → rebuild cost
   - Solution: Compress aggressively BEFORE breaks to minimize rebuild tokens

7. **Model routing cache impact**
   - Switching models CAN break cache (provider-dependent)
   - Route to SAME model family when possible (Claude 3.5 Sonnet → Claude 3 Opus = different caches)
   - Measure cache hit rate drop after routing changes

#### Cache-Aware Implementation Checklist

Before implementing compression:
- [ ] Read `cache/cache_boundaries_explained.md`
- [ ] Read `cache/cache_ttl_behavior.md`
- [ ] Understand your provider's caching behavior (see Provider Comparison below)
- [ ] Design compression as layered boundaries (not rolling window)
- [ ] Plan to compress once and freeze (not continuously recompress)
- [ ] Add cache hit rate monitoring to logs
- [ ] Test on real sessions: measure cost with/without compression

#### Provider-Specific Caching Comparison

| Provider | Cache Support | TTL | Cost | Notes |
|----------|---------------|-----|------|-------|
| **Anthropic** | ✅ Excellent | 5 min | $0.30/M read, $3.75/M write | Explicit cache_control markers, up to 4 boundaries |
| **OpenAI** | ✅ Yes | 5-10 min | ~$0.50/M read (varies) | Automatic (no control), less documented |
| **Google (Gemini)** | ✅ Yes | ~5 min | Varies by model | Automatic context caching |
| **OpenRouter** | ⚠️ Maybe | Unknown | Unknown | Depends on upstream provider, often NO caching passthrough |
| **AWS Bedrock** | ✅ Yes | Varies | Provider-dependent | Passes through provider caching |
| **Azure OpenAI** | ✅ Yes | ~10 min | Similar to OpenAI | Enterprise caching |

**CRITICAL for our proxy:**
- If using OpenRouter: Likely NO caching benefits (compression helps more)
- If using Anthropic direct: Excellent caching (compression must be cache-aware)
- If using OpenAI direct: Good caching (compression strategy should consider it)

**See `cache/provider_caching_comparison.md` for detailed analysis.**

---

### Phased rollout approach

Instead of implementing all optimizations at once, use a phased approach to minimize risk and validate each layer with real data.

**Each phase MUST include cache hit rate monitoring to ensure we're not degrading cache performance.**

---

### Phase 1: Enhanced data collection (Week 1)

**Goal:** Collect rich session data to inform later phases

**IMPORTANT: Disk space management**

Session logging can generate large files. Use the `ENABLE_FULL_SESSION_LOGGING` flag to control verbosity:

```bash
# .env configuration
ENABLE_FULL_SESSION_LOGGING=true   # Turn ON for data collection phase
ENABLE_FULL_SESSION_LOGGING=false  # Turn OFF (default) for production use
```

**When `ENABLE_FULL_SESSION_LOGGING=true` (data collection mode):**
- Saves complete message history for each turn
- Includes full system prompts, user messages, assistant responses, tool calls, tool results
- Required for training compression/routing models
- WARNING: Can use 10-100 MB per session (50+ turns)

**When `ENABLE_FULL_SESSION_LOGGING=false` (minimal logging, default):**
- Saves only metadata: session_id, turn, timestamp, model, token_count, message_count
- Includes user message preview (first 200 chars)
- Suitable for production monitoring
- Uses ~1-5 KB per session

**Changes to `logger.py`:**

```python
# Current implementation (already done)
ENABLE_FULL_SESSION_LOGGING = os.getenv("ENABLE_FULL_SESSION_LOGGING", "false").lower() == "true"

# In log_turn method:
entry = {
    "session_id": self._session_id,
    "turn": self._turn,
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "model": model,
    "message_count": len(messages),
    "estimated_tokens": token_count,
}

if ENABLE_FULL_SESSION_LOGGING:
    entry["messages"] = messages  # Full content
else:
    entry["user_message_preview"] = messages[-1]["content"][:200]  # Minimal preview
```

**Future enhancements (when starting Phase 5):**

Add routing-relevant metadata:

```python
# When ENABLE_FULL_SESSION_LOGGING=true, also collect:
entry["user_message_length"] = len(messages[-1].get("content", "")) if messages else 0
entry["file_count_in_context"] = count_unique_files(messages)
entry["tool_types_requested"] = extract_tool_types(messages)
entry["task_keywords"] = extract_keywords(messages[-1].get("content", ""))
entry["errors_in_previous_turn"] = detect_error_patterns(messages)
```

**Deliverable:** 
1. Run proxy with `ENABLE_FULL_SESSION_LOGGING=true` for 1-2 weeks
2. Collect 50-100 logged sessions covering diverse tasks
3. Switch to `ENABLE_FULL_SESSION_LOGGING=false` for normal use

**Success criteria:** 
- 50-100 logged sessions with diverse tasks
- Sessions cover: simple edits, complex refactors, debugging, multi-file changes
- Disk usage monitored and acceptable (or compressed with tar/gzip between collection periods)

---

### Phase 2: Deterministic preprocessing (Week 2)

**Goal:** Immediate, risk-free token savings via pure regex

**Implementation order:**

1. **Noise stripping** (`preprocessor.py`):
   ```python
   def strip_tool_noise(messages: list) -> list:
       # Apply 8 regex patterns to tool_result content blocks
       # Save before/after for validation
   ```

2. **Path compression** (same file):
   ```python
   def compress_paths(messages: list, workspace_path: str) -> list:
       # Replace path stems with $C, $W
       # Add legend to system prompt
   ```

3. **Stale file deduplication**:
   ```python
   def dedupe_file_reads(messages: list) -> list:
       # Keep only latest Read tool result per file path
   ```

**Integration:** Call in `main.py` before forwarding to LLM

**Validation:** Compare token counts before/after, verify no quality degradation

**Deliverable:** `preprocessor.py` module with unit tests

**Expected savings:** 10-15% token reduction with zero LLM cost

---

### Phase 3: Adaptive prompt templates (Week 3-4)

**Goal:** Template-based prompt optimization with keyword heuristics

**Step 1: Build prompt library**

Create `prompts/` directory:
```
prompts/
  minimal.txt      # ~2,000 tokens: Read/Grep/citing code only
  standard.txt     # ~4,500 tokens: + coding principles + linter
  full.txt         # ~8,000+ tokens: current behavior (everything)
  git.txt          # ~5,000 tokens: + git workflow details
```

**Step 2: Keyword-based classification** (no LLM yet)

```python
def classify_template(user_message: str) -> str:
    keywords = extract_keywords(user_message.lower())
    
    if any(kw in keywords for kw in ["read", "explain", "show", "what"]):
        return "minimal"
    if any(kw in keywords for kw in ["commit", "pr", "push", "branch"]):
        return "git"
    if any(kw in keywords for kw in ["architecture", "refactor", "design"]):
        return "full"
    return "standard"  # default
```

**Step 3: Rule gating** (optional, subsumed by templates)

If adaptive prompts alone don't save enough, add rule gating within templates using keyword matching.

**Integration:** Load selected template in `main.py`, replace system prompt

**Validation:** Log template used per turn, verify quality on test tasks

**Deliverable:** `prompt_selector.py` module with template loader

**Expected savings:** 5,000-8,000 tokens per turn (varies by task type)

---

### Phase 4: History relevance compression (Week 5-6)

**Goal:** Use cheap model to identify and remove stale conversation content

**Prerequisites:** Phase 2 validated, 50+ sessions collected

**Implementation:**

```python
async def compress_history(messages: list, cheap_model: str) -> list:
    if len(messages) < KEEP_LAST_N_TURNS * 2:
        return messages  # Too short, skip
    
    # Build round headers (tool_use + tool_result pairs)
    rounds = group_into_rounds(messages[:-KEEP_LAST_N_TURNS])
    headers = [build_round_header(r) for r in rounds]
    
    # Ask cheap model: which rounds still relevant?
    prompt = f"""Recent task: {messages[-1]['content']}
    
Old conversation rounds:
{format_headers(headers)}

Which round numbers are still relevant to the current task?
Reply with just the numbers: 3, 7, 12"""
    
    relevant_ids = await call_cheap_model(prompt, cheap_model)
    
    # Drop tool_result content from irrelevant rounds
    return filter_messages(messages, relevant_ids, KEEP_LAST_N_TURNS)
```

**Integration:** Call in `main.py` after preprocessing, before forwarding

**Validation:**
- Compare before/after token counts
- Manually review compressed sessions to verify no critical context lost
- Track if LLM needs to re-fetch dropped content (measure re-read rate)

**Deliverable:** `history_compressor.py` module

**Expected savings:** 20-40% on long sessions (>15 turns)

---

### Phase 5: Data-driven model routing (Week 7-10)

**Goal:** Route turns to appropriate model tier based on empirical patterns

**Prerequisites:** 100+ logged sessions from Phases 1-4 with quality metadata

**Step 1: Analyze collected data**

```python
# scripts/analyze_routing_data.py
# Extract features from sessions:
# - Which turns succeeded on which models?
# - What keywords/patterns predict difficulty?
# - How often do users retry/correct output?

# Build training dataset:
# features: [keyword_counts, file_count, history_length, tool_types]
# label: "simple" | "medium" | "hard"
```

**Step 2: Train classifier (Option A)**

```python
from sklearn.ensemble import RandomForestClassifier

# Train on collected sessions
clf = RandomForestClassifier(n_estimators=100)
clf.fit(features, labels)

# Save model
joblib.dump(clf, "models/routing_classifier.pkl")
```

**Step 3: LLM self-assessment (Option B)**

```python
# After each turn, ask model:
# "For the NEXT turn, I recommend routing to: [simple|medium|hard]"
# Store in response metadata, use for next turn
```

**Step 4: Hybrid approach (recommended)**

```python
def route_model(user_message, history, previous_model_suggestion):
    # Priority order:
    1. Check FORCE_HARD/SIMPLE_KEYWORDS → override
    2. If previous turn suggested tier → use that
    3. Else: classifier.predict(features)
    4. Cap at user-requested ceiling (never route higher)
    5. Auto-escalate if stuck (3+ retries → bump tier)
```

**Integration:** Call in `main.py` Layer 0, apply routing decision before LLM call

**Validation:**
- A/B test: 50% sessions with routing, 50% without
- Measure: cost savings, quality (user retry rate), escalation rate
- Iterate on classifier if false negatives (wrong downgrades) are frequent

**Deliverable:** 
- `routing_classifier.py` module
- `scripts/train_routing_model.py`
- `models/routing_classifier.pkl` trained model

**Expected savings:** 90-99% cost reduction (compounds with compression)

**Risk mitigation:**
- Conservative initial thresholds (prefer false positives over false negatives)
- Manual override flags for production sessions
- Monitoring dashboard to track routing decisions and quality

---

### Configuration flags (.env)

Flags organized by implementation phase:

```bash
# ============ PHASE 1: Data collection ============
LOG_DIR=logs
SESSIONS_DIR=logs/sessions
DEBUG_BUFFER_SIZE=5

# Full session logging (WARNING: uses significant disk space!)
# Turn ON for data collection, turn OFF for production monitoring
ENABLE_FULL_SESSION_LOGGING=false  # Default: false (minimal logging)
# When true: saves complete messages (~10-100 MB per session)
# When false: saves only metadata (~1-5 KB per session)

# Future: Enhanced metadata for routing training (Phase 5)
SAVE_ROUTING_METADATA=false  # Not yet implemented

# ============ PHASE 2: Deterministic preprocessing ============
ENABLE_NOISE_STRIPPING=true
ENABLE_PATH_COMPRESSION=true
ENABLE_FILE_DEDUPLICATION=true
PATH_STEM=/Users/amir/Dropbox/CodingProjects  # auto-detected if empty

# ============ PHASE 3: Adaptive prompts ============
ENABLE_ADAPTIVE_PROMPTS=false  # Enable when templates are ready
PROMPT_TEMPLATES_DIR=prompts/
DEFAULT_TEMPLATE=standard  # fallback if classification fails

# Optional: Rule gating within templates (if template alone insufficient)
ENABLE_RULE_GATING=false
RULE_INDEX_CACHE_DIR=logs/rule_cache

# ============ PHASE 4: History compression ============
ENABLE_HISTORY_COMPRESSION=false  # Enable after Phase 2 validated
MAX_TOKENS_BEFORE_COMPRESS=16000
KEEP_LAST_N_TURNS=3  # Always keep recent turns verbatim
CHEAP_MODEL_HISTORY_RELEVANCE=openrouter/google/gemini-2.0-flash-lite-001

# ============ PHASE 5: Model routing (data-driven) ============
ENABLE_MODEL_ROUTING=false  # Enable LAST, after data collection
MODEL_ROUTING_CLASSIFIER=models/routing_classifier.pkl  # Path to trained model

# Model tier definitions (user-requested model acts as ceiling)
MODEL_TIER_SIMPLE=openrouter/google/gemini-2.0-flash
MODEL_TIER_MEDIUM=openrouter/anthropic/claude-3.5-sonnet
MODEL_TIER_HARD=openrouter/anthropic/claude-3-opus

# Override keywords (manual rules)
FORCE_HARD_KEYWORDS=architecture,design system,refactor everything,security audit
FORCE_SIMPLE_KEYWORDS=typo,add comment,format,lint fix,run command

# LLM self-assessment (if using Option B)
USE_MODEL_SELF_ASSESSMENT=false

# ============ General settings ============
CHEAP_MODEL_NAME=openrouter/google/gemini-2.0-flash-lite-001
OPENROUTER_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here
DEFAULT_BACKEND=openrouter
BYPASS_COMPRESSION=false  # Emergency kill switch

# Debug/logging
LOG_COMPRESSION_DECISIONS=true
SAVE_BEFORE_AFTER_PAYLOADS=true  # For analysis
```

---

### Final pipeline (after all phases implemented)

```
Incoming request from Cursor
         ↓
┌─ Phase 1: Collect metadata ────────────────────────────────┐
│ Log enhanced session data for routing analysis             │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─ Phase 2: Deterministic preprocessing (free) ──────────────┐
│ 1. Dedupe file reads: keep only latest per path            │
│ 2. Strip noise patterns (8 regex)                          │
│ 3. Replace path stems ($C, $W)                             │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─ Phase 3: Adaptive prompt selection ───────────────────────┐
│ 1. Classify task: minimal/standard/full/git                │
│ 2. Load selected template                                  │
│ 3. (Optional) Gate rules within template                   │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─ Phase 4: History relevance (cheap model, conditional) ────┐
│ IF history > threshold:                                     │
│   1. Build round headers                                    │
│   2. Cheap model: which old rounds still relevant?         │
│   3. Strip tool_result content from irrelevant rounds      │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─ Phase 5: Model routing (classifier or self-assessment) ───┐
│ 1. Extract features (keywords, file count, history, etc.)  │
│ 2. Check override keywords                                 │
│ 3. Apply classifier or use previous turn's suggestion      │
│ 4. Cap at user-requested model ceiling                     │
│ 5. Log routing decision                                    │
└─────────────────────────────────────────────────────────────┘
         ↓
Forward compressed payload to routed model
         ↓
Stream response back to Cursor
         ↓
(Optional: Append routing suggestion for next turn)
```

---

### Testing approach (per phase)

Each phase should be validated before proceeding to the next:

**Phase 1: Data collection**
- Run proxy with enhanced logging for 1-2 weeks
- Verify metadata is captured correctly
- Ensure 50-100 diverse sessions collected
- Check log file sizes and storage growth

**Phase 2: Deterministic preprocessing**
- Enable Phase 2 flags only
- Test on 10-20 sample sessions from Phase 1
- Compare before/after token counts
- Manually verify:
  - Noise stripping doesn't remove real content
  - Path compression preserves meaning
  - File deduplication keeps correct (latest) version
- Run full agentic sessions and verify quality
- Measure: avg token savings, no quality degradation

**Phase 3: Adaptive prompts**
- Build 4 template files
- Test keyword classifier on sample tasks
- Verify each template loads correctly
- Run sessions with each template type
- Compare:
  - Token counts vs full prompt
  - Quality (does minimal prompt work for simple tasks?)
  - Misclassification rate
- Iterate on classification keywords if needed

**Phase 4: History compression**
- Enable Phase 4 flag (requires Phase 2 working)
- Test on long sessions (>15 turns)
- Verify cheap model prompt works
- Check relevance classification accuracy:
  - Does it preserve important context?
  - Does it drop truly stale rounds?
- Measure re-fetch rate (how often LLM asks to re-read dropped content)
- If high re-fetch rate → adjust prompt or relevance threshold

**Phase 5: Model routing**
- Analyze Phase 1-4 collected data
- Train/validate classifier on 80/20 split
- Test classifier accuracy on held-out sessions
- A/B test: 50% with routing, 50% without
- Measure:
  - Cost savings
  - Quality (user retry/edit rate)
  - Escalation frequency
  - False negative rate (tasks that fail on cheap model)
- Iterate on classifier or use hybrid approach if needed
- Conservative rollout: start with 10% traffic, monitor quality

**For each phase, save:**
- Original payload (before optimization)
- Optimized payload (after optimization)  
- Token counts (before/after)
- LLM response quality (track errors, retries, user edits)
- Cost impact


---

## Finding 6 — Context Size Management & Error Recovery

**Problem:** Real-world observation from production testing (2026-05-15):
- Proxy estimated **64,475 tokens** (messages only)
- Actual token count: **200,826 tokens** (3.1x higher!)
- Reason: Tool definitions not included in estimate (~40k tokens for 18 tools)
- Result: Request exceeded Claude's 200k limit and failed

**Key Insights:**

1. **Token estimation must include tools:**
   - Messages: ~64k tokens (text content)
   - Tools: ~40k tokens (18 tool definitions with JSON schemas)
   - Total: ~104k tokens realistic estimate
   - Tools have **worse char-to-token ratio** (JSON structure overhead)

2. **Cursor's behavior differs by routing:**
   - **Cursor's direct models** (Sonnet via Cursor): Cursor compresses context automatically
   - **Custom endpoints** (our proxy): Cursor sends **full uncompressed context**
   - This is why our compression is critical — we replicate what Cursor does internally

3. **Error handling is essential:**
   - "Prompt too long" errors should trigger auto-retry with compression
   - Silent failures (empty responses) occur when streaming errors aren't caught
   - Need graceful degradation: compress → truncate → fail with clear message

**Implementation Requirements:**

### 1. Accurate Token Estimation
```python
# Current (broken):
estimate_tokens(messages_text)  # Only counts message content

# Fixed:
messages_tokens = estimate_tokens(messages_text)
tools_tokens = estimate_tokens(json.dumps(tools), multiplier=1.5)  # JSON overhead
total_tokens = messages_tokens + tools_tokens
```

### 2. Proactive Compression Trigger
```python
MODEL_TOKEN_LIMIT = 150000  # Safety margin for 200k Claude limit

if estimated_total > MODEL_TOKEN_LIMIT:
    # Force compression BEFORE sending to API
    truncated = truncate_messages_aggressively(messages, target_ratio=0.3)
    compressed = compress_with_summarization(truncated)
```

### 3. Reactive Error Recovery
```python
try:
    response = await api.chat(messages)
except PromptTooLongError as e:
    # Extract actual token count from error message
    actual_tokens = parse_token_count(e.message)  # "200826 tokens > 200000 maximum"
    
    # Calculate compression ratio needed
    target_ratio = MODEL_TOKEN_LIMIT / actual_tokens  # e.g., 150k / 200k = 0.75
    
    # Retry with aggressive compression
    compressed = truncate_messages_aggressively(messages, target_ratio * 0.8)
    response = await api.chat(compressed)
```

### 4. Multi-Stage Fallback Strategy
```
Attempt 1: Send as-is (if estimated < limit)
  ↓ fails with "prompt too long"
Attempt 2: Keep last 50% of messages, summarize middle
  ↓ still too long
Attempt 3: Keep last 30% of messages, summarize middle
  ↓ still too long
Attempt 4: Emergency truncation — last 20% only, no summarization
  ↓ still too long
Fail with error: "Session too large even after maximum compression"
```

### 5. Per-Model Context Limits
```python
MODEL_LIMITS = {
    "anthropic/claude-sonnet-4-5": 200000,
    "openai/gpt-4o": 128000,
    "openai/gpt-4o-mini": 128000,
    "deepseek/deepseek-r1": 64000,
    "google/gemini-2.0-flash": 1000000,
}

# Apply 75% safety margin
def get_safe_limit(model: str) -> int:
    max_limit = MODEL_LIMITS.get(model, 100000)
    return int(max_limit * 0.75)
```

### 6. Streaming Error Handling
**Critical for production:** Streaming responses that fail must return errors properly.

**Before (broken):**
```python
async for line in resp.aiter_lines():
    yield line  # If error occurs, yields nothing → "empty response"
```

**After (fixed):**
```python
if resp.status_code >= 400:
    error_body = await resp.aread()
    error_data = json.loads(error_body)
    # Send error as SSE chunk so Cursor sees it
    yield f"data: {json.dumps(error_data)}\n\n"
    return
```

**Metrics to Track:**
- Estimated tokens vs actual tokens (from API response)
- Compression ratio needed on retry
- Success rate of each retry stage
- Session size distribution (histogram)
- Tool token contribution % by model

**Config Variables:**
```bash
# Context management
MODEL_TOKEN_LIMIT=150000  # Per-model override supported
ENABLE_AUTO_RETRY=true
MAX_RETRY_ATTEMPTS=3
COMPRESSION_RATIO_PER_RETRY=0.7,0.5,0.3  # Successive attempts

# Token estimation
TOOL_JSON_MULTIPLIER=1.5  # Accounts for JSON overhead
INCLUDE_TOOLS_IN_ESTIMATE=true
```

**Status:** 
- ✅ Accurate token estimation (implemented 2026-05-15)
- ✅ Proactive compression trigger (implemented 2026-05-15)
- ✅ Streaming error handling (implemented 2026-05-15)
- ⏳ Auto-retry with compression (backlog)
- ⏳ Multi-stage fallback (backlog)
- ⏳ Per-model limits (backlog)
