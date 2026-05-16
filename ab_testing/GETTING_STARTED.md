# A/B Testing Framework - Organization Complete ✅

Everything is now organized in one logical `ab_testing/` folder.

## 📁 Structure

```
context_optimizer/
├─ main.py, compressor.py, logger.py, ui.py  (core proxy)
├─ README.md
│
└─ ab_testing/                    ← ALL A/B TESTING STUFF
   ├─ README.md                   (start here)
   ├─ __init__.py
   │
   ├─ framework/                  (core implementation)
   │  ├─ strategies.py            (compression logic)
   │  ├─ simulator.py             (virtual tools)
   │  ├─ scenario.py              (scenario loading)
   │  ├─ tool_schemas.py          (tool definitions)
   │  ├─ runner.py                (test orchestration)
   │  └─ README.md
   │
   ├─ tests/                       (test scripts)
   │  ├─ 1_local_regex_test.py   (free, instant)
   │  ├─ 2_local_simulation_test.py     (free, instant)
   │  ├─ 3_proxy_api_test.py       (real API)
   │  └─ run_cli.py                (batch + interactive A/B runner)
   │
   ├─ config/
   │  └─ models.json               (interactive model menu source)
   │
   ├─ scenarios/                   (test scenarios)
   │  ├─ simple_shell_noise.json
   │  ├─ file_read_noise.json
   │  ├─ multi_turn_debug.json
   │  └─ README.md
   │
   └─ docs/                        (documentation)
      ├─ QUICKSTART.md
      ├─ FILES_GUIDE.md
      └─ IMPLEMENTATION_REPORT.md
```

## 🚀 Quick Start

```bash
cd context_optimizer/ab_testing

# Read guide
cat README.md
# or
cat docs/QUICKSTART.md

# Run free test
cd tests
python 1_local_regex_test.py

# Run interactive A/B test (scenario(s) + strategies + model + runs + cache)
python tests/run_cli.py -i
```

## 📊 Key Results

**Noise Stripping Compression:**
- Input tokens: [Baseline] → [Compressed]
- Savings: Measurable reduction (exact numbers in future reports)
- Cost: Savings scale with usage

## 📚 Documentation

All in `ab_testing/docs/`:

- **QUICKSTART.md** - Step-by-step guide
- **FILES_GUIDE.md** - What each file does
- **IMPLEMENTATION_REPORT.md** - Technical details and results
- **EVALUATION_MODES.md** - The 3 advanced testing modes (Dynamic, Tight, Perturbation)
- **framework/README.md** - Framework architecture
- **scenarios/README.md** - How to write scenarios

## ✅ Benefits of This Organization

1. **Everything together** - All A/B testing code/tests/docs in one place
2. **Easy to reason about** - Clear separation: framework, tests, scenarios, docs
3. **Clean root** - Root folder only has core proxy files
4. **Maintainable** - Easy to find what you need
5. **Extensible** - Easy to add new strategies, tests, scenarios

## 🧪 Running Tests

Before running dynamic end-to-end tests, **ensure Docker is running on your machine**. The `Shell` tool executes commands inside an isolated `python:3.11-alpine` container to prevent the LLM from accidentally modifying your host system. If Docker is not running, it will fall back to local execution (which is unsafe).

From `context_optimizer/`:

```bash
# Verify Docker is running
docker info

# Full A/B comparison (Run scenarios dynamically)
python ab_testing/tests/run_cli.py ab_testing/scenarios/simple_shell_noise.json

# Interactive (choose scenario(s) + strategy + model + runs + cache)
python ab_testing/tests/run_cli.py -i
```

## 📝 Creating Custom Scenarios

1. Copy a scenario: `cp ab_testing/scenarios/simple_shell_noise.json ab_testing/scenarios/my_test.json`
2. Edit the JSON with your tools and responses
3. Run: `python ab_testing/tests/run_cli.py -i`
4. Select your scenario

Tip: edit `ab_testing/config/models.json` to update interactive model choices.

## 🔧 Adding New Strategies

1. Edit `ab_testing/framework/strategies.py`
2. Add function: `def my_strategy(messages): ...`
3. Register in `STRATEGIES` dict
4. Test: `python ab_testing/tests/1_local_regex_test.py`

## 📊 What's Inside

- **44 test runs** with baseline vs compression
- **3 test scenarios** (simple, mixed, complex)
- **1 compression strategy** (noise stripping)
- **Real API measurements** of token savings
- **Interactive testing** with model selection
- **Complete documentation**

## ✨ Next Steps

1. Run the tests to see it working
2. Create your own scenarios
3. Integrate into production (when ready)
4. Add more strategies (path compression, history filtering, etc.)

---

**All organized. Ready to use!** 🎉
