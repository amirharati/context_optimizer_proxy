# Files Guide - What Each File Does

## Quick Navigation

### 📚 Documentation (START HERE)
- **QUICKSTART.md** - Step-by-step guide to run tests
- **README_TESTING.md** - Complete reference
- **ab_test/README.md** - Framework architecture
- **scenarios/README.md** - How to write scenarios

### 🧪 Test Scripts (RUN THESE)
- **1_local_regex_test.py** - Quick validation (free, instant)
- **2_local_simulation_test.py** - Simulation demo (free, instant)
- **3_proxy_api_test.py** - Real API test (costs $, 2 sec)
- **4_tight_replay_test.py** - Turn-by-turn log replay (free, instant)
- **run_cli.py** - Batch test runner across multiple scenarios
- **run_interactive.py** - Choose scenario + model (interactive)

### 📋 Scenarios (MODIFY THESE)
- **scenarios/simple_shell_noise.json** - Minimal (2 commands)
- **scenarios/file_read_noise.json** - Mixed tools
- **scenarios/multi_turn_debug.json** - Complex
- **scenarios/fix_bug_execution.json** - Tests real code execution and success criteria

### 📁 Artifacts (GENERATED HERE)
- **runs/run_YYYYMMDD_HHMMSS/** - Unified directory for each test run
  - `report.json` - Token savings and success evaluation
  - `sessions/` - The `.jsonl` traces from the proxy
  - `virtual_fs/` - The AI's final generated code

### 🔧 Core Framework (DON'T TOUCH YET)
- **ab_test/strategies.py** - Compression logic (shared with main.py)
- **ab_test/simulator.py** - Virtual tool execution (Read, Shell with **Real Docker Sandbox**, Write, StrReplace, Grep). Note: Every run gets a completely fresh environment and container.
- **ab_test/scenario.py** - Scenario loading and deepcopy state isolation.
- **ab_test/tool_schemas.py** - Tool definitions (5 implemented, 2 future)
- **ab_test/runner.py** - Full test orchestration with pristine sub-runs (run_001, run_002, etc.)

### 🛠️ Implemented Tools
| Tool | Usage | Output Format |
|------|-------|---------------|
| **Shell** | Execute commands | Exit code + fenced output + timing |
| **Read** | Read files | Line numbers `     1\|code` |
| **Write** | Create files | `Wrote contents to {path}` |
| **StrReplace** | Edit files (30% of all edits!) | `The file {path} has been updated.` |
| **Grep** | Search code | `<workspace_result>...</workspace_result>` |

See **TOOL_COMPARISON.md** for full comparison with Cursor's 19 tools.

### ⚙️ Integration
- **main.py** - Proxy server (uses strategies.py)
- **.env.example** - Configuration template

---

## Recommended Workflow

### First Time Setup
```bash
1. Read QUICKSTART.md (5 min)
2. Run: python 1_local_regex_test.py (instant)
3. Run: python 2_local_simulation_test.py (instant)
4. Run: python run_interactive.py (interactive)
```

### Creating Custom Tests
```bash
1. Copy scenarios/simple_shell_noise.json → scenarios/my_test.json
2. Edit your scenario JSON
3. Run: python run_interactive.py and select your scenario
```

### Production Integration
```bash
1. Review noise_strip strategy results
2. Uncomment strategy in main.py
3. Set ENABLE_NOISE_STRIPPING=true in .env
4. Restart main.py
5. Test with live proxy
```

---

## File Details

### 🔴 1_local_regex_test.py
**What it does:** Tests noise stripping without any external calls
**Time:** <1 second
**Cost:** $0
**Good for:** Verifying setup, quick testing
**Output:** Shows significant character reduction

### 🟠 2_local_simulation_test.py
**What it does:** Simulates complete LLM conversation
**Time:** <1 second
**Cost:** $0
**Good for:** Understanding message flow
**Output:** Baseline vs compressed comparison

### 🟡 3_proxy_api_test.py
**What it does:** Sends real requests to LLM API
**Time:** 2-5 seconds
**Cost:** ~$0.0001 per run
**Good for:** Measuring actual token savings
**Output:** Real tokens from API showing measurable reduction

### 🟢 run_interactive.py
**What it does:** Interactive model and scenario selection
**Time:** 2-5 seconds (depends on model)
**Cost:** Depends on model chosen
**Good for:** Comparing different models/scenarios
**Output:** Token savings with selected model

---

## Test Output Examples

### 1_local_regex_test.py Output
```
Baseline chars:    550
Compressed chars:  29
Savings:           Measurable reduction (exact numbers depend on scenario)
Est. tokens saved: ~130
```

### 3_proxy_api_test.py Output
```
Input tokens (baseline):    265
Input tokens (compressed):  130
Total token savings:        Measurable reduction
Cost saved:                 Varies by scenario length and tool usage
```

### run_interactive.py Output
```
SELECT SCENARIO
1. simple_shell_noise.json - Minimal (2 shell commands)
2. file_read_noise.json - Mixed (read + shell)
3. multi_turn_debug.json - Complex (debugging scenario)

SELECT MODEL
1. openai/gpt-4o-mini    $0.15/M  (CHEAP - Best for testing)
2. openai/gpt-4o         $5/M     (MEDIUM - Good quality)
3. anthropic/claude-3-5-sonnet  $3/M (MEDIUM - Anthropic)
4. google/gemini-flash   CHEAP    (BUDGET - Fastest)

[Test runs and shows token savings...]
```

---

## When to Use Each File

| Task | Use This | Time | Cost |
|------|----------|------|------|
| Quick validation | 1_local_regex_test.py | <1s | $0 |
| Understand flow | 2_local_simulation_test.py | <1s | $0 |
| Measure tokens | 3_proxy_api_test.py | 2-5s | $0.0001 |
| Try different models | run_interactive.py | 2-5s | varies |
| Create test case | scenarios/simple_shell_noise.json | N/A | N/A |
| Add new strategy | ab_test/strategies.py | N/A | N/A |

---

## Common Tasks

### "I want to see if noise stripping works"
```bash
python 1_local_regex_test.py
```

### "I want real token measurements"
```bash
python 3_proxy_api_test.py
```

### "I want to test a different model"
```bash
python run_interactive.py
# Select model at prompt
```

### "I want to create my own test scenario"
```bash
cp scenarios/simple_shell_noise.json scenarios/my_test.json
# Edit my_test.json
python run_interactive.py
# Select your new scenario
```

### "I want to add a new strategy"
```bash
# Edit ab_test/strategies.py
# Add new function
# Register in STRATEGIES dict
# Test with: python 1_local_regex_test.py
```

---

## File Dependencies

```
1_local_regex_test.py
  ├─ ab_test/strategies.py
  ├─ ab_test/simulator.py
  └─ ab_test/scenario.py

2_local_simulation_test.py
  ├─ ab_test/strategies.py
  ├─ ab_test/simulator.py
  └─ ab_test/scenario.py

3_proxy_api_test.py
  ├─ ab_test/strategies.py
  ├─ ab_test/simulator.py
  ├─ ab_test/scenario.py
  ├─ main.py (running on localhost:8000)
  └─ httpx (HTTP client)

run_interactive.py
  ├─ ab_test/scenario.py
  ├─ ab_test/simulator.py
  ├─ ab_test/strategies.py
  ├─ main.py (running on localhost:8000)
  └─ httpx (HTTP client)

main.py
  ├─ ab_test/strategies.py ← USES THIS
  ├─ compressor.py
  ├─ logger.py
  └─ ui.py
```

---

## Production Checklist

- [ ] Run 1_local_regex_test.py ✓
- [ ] Run 2_local_simulation_test.py ✓
- [ ] Run 3_proxy_api_test.py ✓
- [ ] Measure token savings in 3_proxy_api_test.py
- [ ] Review noise_strip strategy in ab_test/strategies.py
- [ ] Uncomment strategy integration in main.py
- [ ] Set ENABLE_NOISE_STRIPPING=true in .env
- [ ] Restart main.py
- [ ] Test with live proxy: python run_interactive.py
- [ ] Monitor actual API token usage

