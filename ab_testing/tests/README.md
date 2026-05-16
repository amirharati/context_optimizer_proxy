# A/B Testing Scripts

This directory contains various scripts to test and validate compression strategies (like noise stripping). They are numbered in order of complexity and integration level.

## The Scripts

### 1. `1_local_regex_test.py`
**What it does:** The simplest test. It applies the regex/compression strategy directly to a hardcoded conversation trace (loaded from a scenario).
**No external dependencies:** It does **not** call any API, nor does it use the proxy.
**Use it for:** Quickly verifying that your regex actually removes the characters you expect without waiting for network calls.

### 2. `2_local_simulation_test.py`
**What it does:** Simulates a realistic multi-turn interaction locally. It pretends an LLM generates a tool call, executes that tool call using the in-memory `RuntimeSimulator`, and then applies the compression strategy.
**No external dependencies:** It does **not** call any API or the proxy.
**Use it for:** Checking if the full logic flow (simulation + compression) works on realistic data without costing any API tokens.

### 3. `3_proxy_api_test.py`
**What it does:** An end-to-end walkthrough. It builds a conversation with simulator output, and then sends it **through the local proxy server** to a real LLM API (like OpenAI/OpenRouter). It sends one baseline request and one compressed request, then compares the actual API token counts.
**Dependencies:** Requires the proxy server (`main.py`) to be running.
**Use it for:** Proving that the character savings translate into actual API token savings and verifying proxy compatibility.

### 4. `run_cli.py` (formerly `run_ab_test.py`)
**What it does:** A comprehensive command-line runner that executes scenarios against the proxy server using the `TestRunner` class. It can run single scenarios or all scenarios in a loop, generating a comparison report.
**Dependencies:** Requires the proxy server (`main.py`) to be running.
**Use it for:** Batch testing strategies across multiple scenarios automatically.

### 5. `run_interactive.py`
**What it does:** An interactive prompt that lets you choose which model to test (e.g., cheap vs expensive) and which scenario to run. It then performs the full test through the proxy.
**Dependencies:** Requires the proxy server (`main.py`) to be running.
**Use it for:** Manual, exploratory testing when you want to see how different LLM providers handle the compressed context.

## How to use them dynamically
Most scripts have been updated to accept a scenario path as an argument. If none is provided, they default to `../scenarios/simple_shell_noise.json`.

```bash
python ab_testing/tests/1_local_regex_test.py ab_testing/scenarios/file_read_noise.json
```