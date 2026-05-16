# A/B Testing Framework for Context Compression

Complete testing framework to measure compression strategy effectiveness with real LLM APIs.

## Quick Start

See `docs/QUICKSTART.md`

## Structure

```
ab_testing/
├─ framework/        ← Core A/B test implementation
│  ├─ strategies.py  (compression logic)
│  ├─ simulator.py   (virtual tools)
│  ├─ scenario.py    (scenario loading)
│  ├─ tool_schemas.py
│  ├─ runner.py
│  └─ README.md
├─ tests/            ← Test scripts
│  ├─ test_strategy_direct.py
│  ├─ test_full_endtoend.py
│  ├─ test_walkthrough.py
│  ├─ test_interactive.py
│  └─ run_ab_test.py
├─ scenarios/        ← Test scenarios (JSON)
│  ├─ simple_shell_noise.json
│  ├─ file_read_noise.json
│  ├─ multi_turn_debug.json
│  └─ README.md
└─ docs/            ← A/B testing documentation
   ├─ QUICKSTART.md
   ├─ FILES_GUIDE.md
   └─ IMPLEMENTATION_REPORT.md
```

## Running Tests

```bash
cd ab_testing/tests

# Free tests (instant)
python test_strategy_direct.py
python test_full_endtoend.py

# Real API (costs $$)
python test_walkthrough.py
python test_interactive.py
```

## Results

**Baseline:** 265 tokens  
**Compressed:** 130 tokens  
**Savings:** 135 tokens (46.6%)

See `docs/IMPLEMENTATION_REPORT.md` for full details.
