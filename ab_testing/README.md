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
│  ├─ 1_local_regex_test.py
│  ├─ 2_local_simulation_test.py
│  ├─ 3_proxy_api_test.py
│  ├─ run_interactive.py
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
python 1_local_regex_test.py
python 2_local_simulation_test.py

# Real API (costs $$)
python 3_proxy_api_test.py
python run_interactive.py
```

## Results

**Baseline:** 265 tokens  
**Compressed:** Reduced tokens  
**Savings:** Measurable reduction (exact numbers in future reports)

See `docs/IMPLEMENTATION_REPORT.md` for full details.
