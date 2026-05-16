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
python test_strategy_direct.py
```

**What it does:**
- Loads scenario
- Simulates tool calls
- Applies strategy
- Shows character savings (94.7%)

**Time:** ~1 second
**Cost:** $0.00

---

### Option 2: Full End-to-End Simulation

Simulates complete LLM conversation (tool calls decided by script, not LLM):

```bash
cd context_optimizer
python test_full_endtoend.py
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
python test_walkthrough.py
```

**What it does:**
- Builds conversation with tool results
- Sends BASELINE to proxy → LLM → measures tokens
- Applies noise stripping
- Sends COMPRESSED to proxy → LLM → measures tokens
- Shows token savings

**Cost:** ~$0.0001 per run (very cheap)
**Model used:** `openai/gpt-4o-mini` (default)

---

## Selecting Different Models

You can change the model in several ways:

### Method 1: Using CLI Arguments (for run_ab_test.py)

```bash
python run_ab_test.py scenarios/simple_shell_noise.json \
  --model "openai/gpt-4o" \
  --max-turns 5 \
  --strategies none noise_strip
```

### Method 2: Modify the Script

Edit `test_walkthrough.py` or `test_full_endtoend.py` and change:

```python
# Current (line in test_walkthrough.py)
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
python test_strategy_direct.py

# Full end-to-end (edit script to use your scenario)
# Change line in test_full_endtoend.py:
# scenario = load_scenario(f"scenarios/my_test.json")

# Real API test (edit script)
# Change line in test_walkthrough.py:
# scenario = load_scenario("scenarios/my_test.json")
python test_walkthrough.py
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
python test_strategy_direct.py
# Shows: "Savings: 521 chars (94.7%)"
```

### Token Savings (Real Measurement)
```bash
python test_walkthrough.py
# Shows actual tokens from API: "Token savings: 139 tokens (46.6%)"
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

```bash
python run_ab_test.py scenarios/simple_shell_noise.json \
  --strategies none noise_strip path_compression file_dedupe \
  --model openai/gpt-4o-mini \
  --max-turns 5 \
  --output results.json
```

Then check results:
```bash
cat results.json | python -m json.tool
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
python run_ab_test.py scenario.json --max-turns 2
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
   python test_strategy_direct.py
   ```

2. **Run real proxy test to see token savings:**
   ```bash
   python test_walkthrough.py
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

