# Quick Start Guide: Running A/B Tests

## Installation & Setup

### 1. Make sure proxy is running

```bash
# In terminal 1
cd context_optimizer
python main.py
```

You should see:
```
Starting Context Optimizer Proxy on http://127.0.0.1:8000
```

### 2. Verify proxy is working

```bash
curl http://localhost:8000/v1/models | head -20
```

You should see a list of available models.

---

## Running Tests

### Option 1: Simple Direct Test (NO API CALLS, NO COSTS)

Shows noise stripping works without any API interaction:

```bash
cd context_optimizer
python 1_local_regex_test.py
```

**What it does:**
- Loads scenario
- Simulates tool calls
- Applies strategy
- Shows character savings

**Time:** ~1 second
**Cost:** $0.00

---

### Option 2: Full End-to-End Simulation

Simulates complete LLM conversation (tool calls decided by script, not LLM):

```bash
cd context_optimizer
python 2_local_simulation_test.py
```

**What it does:**
- Loads scenario
- Simulates LLM deciding to call tools
- Simulator returns fake results
- Compares baseline vs compressed

**Time:** ~1 second
**Cost:** $0.00

---

### Option 3: Real Proxy + Real API (TOKEN MEASUREMENTS)

**⚠️ This costs money - you'll make actual API calls!**

Sends real requests to proxy and gets actual token counts from LLM API:

```bash
cd context_optimizer
python 3_proxy_api_test.py
```

**What it does:**
- Builds conversation with tool results
- Sends BASELINE to proxy → LLM → measures tokens
- Applies noise stripping
- Sends COMPRESSED to proxy → LLM → measures tokens
- Shows token savings

**Cost:** ~$0.0001 per run (very cheap)
**Model used:** `openai/gpt-4o-mini` (default)

### Option 4: Full A/B Testing CLI (BATCH TESTING)

The main tool for running comprehensive A/B tests across strategies and scenarios:

```bash
cd context_optimizer/ab_testing/tests
python run_cli.py ../scenarios/simple_shell_noise.json
```

**What it does:**
- Runs the full dynamic evaluation loop
- Tests multiple strategies side-by-side
- Generates a detailed comparison report
- Saves artifacts (logs, virtual FS) to a `runs/` directory

**Time:** Varies (depends on scenario length and model)
**Cost:** Varies (real API calls made)

---

### Option 5: Interactive Runner

Choose scenario and model interactively:

```bash
cd context_optimizer/ab_testing/tests
python run_interactive.py
```

---

## Selecting Different Models

You can change the model in several ways:

### Method 1: Using CLI Arguments (for run_cli.py)

```bash
python run_cli.py ../scenarios/simple_shell_noise.json \
  --model "openai/gpt-4o" \
  --max-turns 5 \
  --strategies none noise_strip
```

### Method 2: Modify the Script

Edit `3_proxy_api_test.py` or `2_local_simulation_test.py` and change:

```python
# Current (line in 3_proxy_api_test.py)
baseline_request = {
    "model": "openai/gpt-4o-mini",
    ...
}

# Change to:
baseline_request = {
    "model": "openai/gpt-4o",  # More expensive but better
    ...
}
```

### Method 3: Using Environment Variable

```bash
# Set via .env (persistent)
echo "TEST_MODEL=anthropic/claude-3-5-sonnet-20241022" >> .env

# Then in Python:
import os
model = os.getenv("TEST_MODEL", "openai/gpt-4o-mini")
```

---

## Available Models

### Cheap (Good for Testing)
- `openai/gpt-4o-mini` - $0.15/M input tokens ← **Default**
- `google/gemini-flash-1.5` - Very cheap

### Medium
- `openai/gpt-4o` - $5/M input tokens
- `anthropic/claude-3-5-sonnet-20241022` - $3/M input tokens

### Expensive (Better Quality)
- `anthropic/claude-3-opus-20240229` - $15/M input tokens

**Cost Calculator:**
```
139 tokens saved per test × $3/M = $0.00042 saved
If you run 100 tests: 13,900 tokens × $3/M = $0.042 saved from compression

Test cost (gpt-4o-mini): ~$0.0001
Test cost (gpt-4o): ~$0.001
```

---

## Running Your Own Scenario

### Step 1: Create New Scenario File

Create `scenarios/my_test.json`:

```json
{
  "name": "My test scenario",
  "description": "What this tests",
  "system_prompt": "You are a helpful assistant.",
  "available_tools": ["Read", "Shell"],
  "virtual_fs": {
    "/workspace/app.py": "def hello():\n    print('Hello')\n",
    "/workspace/config.json": "{\"version\": \"1.0\"}"
  },
  "shell_responses": {
    "python app.py": {
      "exit_code": 0,
      "stdout": "Hello\n",
      "stderr": "",
      "duration_ms": 234
    },
    "cat config.json": {
      "exit_code": 0,
      "stdout": "{\"version\": \"1.0\"}\n",
      "stderr": "",
      "duration_ms": 89
    }
  },
  "turns": [
    {"role": "user", "content": "Run my app and check config"}
  ]
}
```

### Step 2: Run Tests with Your Scenario

```bash
# Direct test
python 1_local_regex_test.py

# Full end-to-end (edit script to use your scenario)
# Change line in 2_local_simulation_test.py:
# scenario = load_scenario(f"scenarios/my_test.json")

# Real API test (edit script)
# Change line in 3_proxy_api_test.py:
# scenario = load_scenario("scenarios/my_test.json")
python 3_proxy_api_test.py
```

---

## Creating Multi-Turn Scenarios

For more complex scenarios with multiple turns, edit your scenario JSON:

```json
{
  "name": "Multi-turn debugging",
  "description": "Debugging with multiple tool interactions",
  "system_prompt": "You are a debugging expert.",
  "available_tools": ["Read", "Shell"],
  "virtual_fs": {
    "/app/main.py": "x = 1\ny = 'hello'\nz = x + y  # This will error",
    "/app/test.py": "from main import *\nprint('Testing...')"
  },
  "shell_responses": {
    "python /app/test.py": {
      "exit_code": 1,
      "stdout": "",
      "stderr": "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
      "duration_ms": 456
    },
    "python -m py_compile /app/main.py": {
      "exit_code": 0,
      "stdout": "",
      "stderr": "",
      "duration_ms": 123
    }
  },
  "turns": [
    {"role": "user", "content": "Debug this error"},
    {"role": "user", "content": "Fix line 3"}
  ]
}
```

---

## Measuring Different Metrics

### Character Savings (Quick Check)
```bash
python 1_local_regex_test.py
# Shows character savings
```

### Token Savings (Real Measurement)
```bash
python 3_proxy_api_test.py
# Shows actual token savings from API
```

### Cost Impact
```
Token savings × Price per token = Cost saved

Example:
139 tokens × ($0.15 / 1,000,000) = $0.0000209 per test

Per conversation (assume 10 tool calls):
139 × 10 × $0.15 / 1,000,000 = $0.000209 saved
```

---

## Comparing Strategies

To compare multiple strategies (once we add more):

### Using the CLI Runner (`run_cli.py`)

The CLI runner is the primary tool for batch testing and generating reports.

```bash
cd context_optimizer/ab_testing/tests
python run_cli.py ../scenarios/simple_shell_noise.json \
  --strategies none noise_strip \
  --model openai/gpt-4o-mini \
  --max-turns 5 \
  --runs 3 \
  --output results.json
```

**Key Arguments:**
- `scenario`: Path to the scenario JSON file (positional argument)
- `--all`: Run all scenarios found in the `scenarios/` directory
- `--model`: Model to use (default: `openai/gpt-4o-mini`)
- `--strategies`: Space-separated list of strategies to compare (default: `none noise_strip`)
- `--max-turns`: Maximum conversation turns per run (default: `10`)
- `--runs`: Number of times to run each scenario for averaging results (default: `1`)
- `--temperature`: LLM temperature (default: `0.0` for determinism)
- `--output`: Save results to a specific JSON file (defaults to `runs/run_YYYYMMDD_HHMMSS/report.json`)
- `--no-full-logging`: Disable full logging of requests (full logging is enabled by default)

**Example: Run all scenarios multiple times to get average savings**
```bash
python run_cli.py --all --runs 3 --model anthropic/claude-3-5-sonnet-20241022
```

Then check the generated report:
```bash
cat runs/run_*/report.json | python -m json.tool
```

---

## Troubleshooting

### "Connection refused" - Proxy not running
```bash
ps aux | grep "python main.py"
# If nothing shows, start it:
cd context_optimizer && python main.py
```

### "Model not found" - Using wrong model name
```bash
curl http://localhost:8000/v1/models | grep model | head -20
# Pick a model from the list
```

### High API costs - Script ran too long
```bash
# Limit turns to reduce cost
python run_cli.py ../scenarios/simple_shell_noise.json --max-turns 2
```

### Proxy returns error - Check logs
```bash
tail -50 /tmp/proxy_server.log
# or check the terminal running main.py
```

---

## Next Steps

1. **Run direct test to verify setup works:**
   ```bash
   python 1_local_regex_test.py
   ```

2. **Run real proxy test to see token savings:**
   ```bash
   python 3_proxy_api_test.py
   ```

3. **Create your own scenario** (see section above)

4. **Run tests on your scenario** with different models to compare costs

5. **Once happy with results**, we can integrate into production pipeline

---

## Questions?

- **How do I measure tokens for [tool name]?** Add it to `ab_test/tool_schemas.py`
- **Can I add a new strategy?** Add function to `ab_test/strategies.py` and register in `STRATEGIES`
- **How do I use a different provider?** Change model name (e.g., `anthropic/claude-3-5-sonnet-20241022`)
- **Can I run multiple tests in parallel?** Not yet (would need async support), but can run sequentially

