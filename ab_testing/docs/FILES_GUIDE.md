# Files Guide - What Each File Does

## Quick Navigation

### 📚 Documentation (START HERE)
- **QUICKSTART.md** - Step-by-step guide to run tests
- **README_TESTING.md** - Complete reference
- **framework/README.md** - Framework architecture
- **scenarios/README.md** - How to write scenarios

### 🧪 Test Scripts (RUN THESE)
- **1_local_regex_test.py** - Quick validation (free, instant)
- **2_local_simulation_test.py** - Simulation demo (free, instant)
- **3_proxy_api_test.py** - Real API test (costs $, 2 sec)
- **4_tight_replay_test.py** - Turn-by-turn log replay (free, instant)
- **run_cli.py** - Batch test runner across multiple scenarios
- **run_cli.py -i** - Interactive runner (scenario(s), strategy, model, runs, cache)

### 📋 Scenarios (MODIFY THESE)
- **scenarios/simple_shell_noise.json** - Minimal (2 commands)
- **scenarios/file_read_noise.json** - Mixed tools
- **scenarios/multi_turn_debug.json** - Complex
- **scenarios/fix_bug_execution.json** - Tests real code execution and success criteria

### 📁 Artifacts (GENERATED HERE)
- **runs/YYYY-MM-DD/cache_mode/run_YYYYMMDD_HHMMSS_cache_mode/** - Unified directory for each test run
  - `report.json` - Token savings and success evaluation
  - `cli_output.txt` - Full CLI output for the entire run
  - `sessions/` - The `.jsonl` traces from the proxy
  - `virtual_fs/` - The AI's final generated code

### 🔧 Core Framework (DON'T TOUCH YET)
- **framework/strategies.py** - Compression logic (shared with main.py)
- **framework/simulator.py** - Virtual tool execution (Read, Shell with **Real Docker Sandbox**, Write, StrReplace, Grep). Note: Every run gets a completely fresh environment and container.
- **framework/scenario.py** - Scenario loading and deepcopy state isolation.
- **framework/tool_schemas.py** - Tool definitions (5 implemented, 2 future)
- **framework/runner.py** - Full test orchestration with pristine sub-runs (run_001, run_002, etc.)

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
4. Run: python run_cli.py -i (interactive)
```

### Creating Custom Tests
```bash
1. Copy scenarios/simple_shell_noise.json → scenarios/my_test.json
2. Edit your scenario JSON
3. Run: python run_cli.py -i and select your scenario
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

### 🟢 run_cli.py -i
**What it does:** Interactive scenario/strategy/model/runs/cache selection
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

### run_cli.py -i Output
```
SELECT SCENARIO
1. simple_shell_noise.json - Minimal (2 shell commands)
2. file_read_noise.json - Mixed (read + shell)
3. multi_turn_debug.json - Complex (debugging scenario)

SELECT MODEL
1. [loaded dynamically from ab_testing/config/models.json]

[Test runs and shows token savings...]
```

---

## When to Use Each File

| Task | Use This | Time | Cost |
|------|----------|------|------|
| Quick validation | 1_local_regex_test.py | <1s | $0 |
| Understand flow | 2_local_simulation_test.py | <1s | $0 |
| Measure tokens | 3_proxy_api_test.py | 2-5s | $0.0001 |
| Try different models | run_cli.py -i | 2-5s | varies |
| Create test case | scenarios/simple_shell_noise.json | N/A | N/A |
| Add new strategy | framework/strategies.py | N/A | N/A |

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
python run_cli.py -i
# Select model at prompt
```

### "I want to create my own test scenario"
```bash
cp scenarios/simple_shell_noise.json scenarios/my_test.json
# Edit my_test.json
python run_cli.py -i
# Select your new scenario
```

### "I want to add a new strategy"
```bash
# Edit framework/strategies.py
# Add new function
# Register in STRATEGIES dict
# Test with: python 1_local_regex_test.py
```

---

## File Dependencies

```
1_local_regex_test.py
  ├─ framework/strategies.py
  ├─ framework/simulator.py
  └─ framework/scenario.py

2_local_simulation_test.py
  ├─ framework/strategies.py
  ├─ framework/simulator.py
  └─ framework/scenario.py

3_proxy_api_test.py
  ├─ framework/strategies.py
  ├─ framework/simulator.py
  ├─ framework/scenario.py
  ├─ main.py (running on localhost:8000)
  └─ httpx (HTTP client)

run_cli.py
  ├─ framework/scenario.py
  ├─ framework/simulator.py
  ├─ framework/strategies.py
  ├─ main.py (running on localhost:8000)
  └─ httpx (HTTP client)

main.py
  ├─ framework/strategies.py ← USES THIS
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
- [ ] Review noise_strip strategy in framework/strategies.py
- [ ] Uncomment strategy integration in main.py
- [ ] Set ENABLE_NOISE_STRIPPING=true in .env
- [ ] Restart main.py
- [ ] Test with live proxy: python run_cli.py -i
- [ ] Monitor actual API token usage

