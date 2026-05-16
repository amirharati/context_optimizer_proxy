# Evaluation Modes for A/B Testing

Our framework supports advanced methodologies for evaluating how well Large Language Models perform when context compression is applied. In the field of AI Agent Evaluation (similar to SWE-bench), we categorize these testing patterns into three distinct modes.

---

## 1. Dynamic Mode (End-to-End Agentic Evaluation)

**Status:** ✅ Fully Implemented (`run_cli.py` & `TestRunner`)

**Industry Name:** End-to-End Agentic Evaluation (or SWE-bench style evaluation)

**What it does:** 
The AI is given a prompt and runs autonomously in a simulated loop until it decides it is finished. The LLM interacts dynamically with the simulated environment (like reading or writing files and executing shell commands). If compression causes the AI to get confused, it might take more turns to recover or fail entirely.

*Note on Execution Safety:* To ensure safety while executing arbitrary shell commands from the LLM, the `Shell` tool runs commands inside a completely isolated **Docker container** (`python:3.11-alpine`) with no network access. It falls back to local execution (with warnings) if Docker is unavailable.

**How we evaluate it (Real Eval):** 
At the end of the dynamic run, the framework validates objective **success criteria**.
- **File State Verification (`file_contains`):** Checks if the final virtual filesystem contains a specific string (e.g., did the AI fix the bug in the code?).
- **Real Code Execution (`run_command`):** Dumps the AI's final virtual filesystem to a real temporary directory on disk and executes a real shell command (e.g., running `python test.py`). If the exit code is 0, the task passed.
- **Efficiency (`max_turns`):** Fails the run if the LLM thrashes and takes too long to solve the problem.

**Use Case:** The "Gold Standard". Answers the ultimate business question: *If I deploy this compression strategy, will my AI still be able to code correctly, and will it actually save money?*

---

## 2. Tight Mode (Trajectory Replay)

**Status:** 🚧 Partially Implemented (`4_tight_replay_test.py`)

**Industry Name:** Trajectory Replay (or Offline Step-wise Evaluation)

**What it does:** 
It takes a historical, recorded conversation (from a `.jsonl` session log) and rigidly steps through it turn-by-turn. At every turn, it forces the AI context to exactly match the historical ground truth, applying compression turn-by-turn to compare the mathematical token savings of the baseline vs. compressed context without any LLM drift.

**How we evaluate it (LLM-as-a-Judge):** 
*(Pending Implementation for AI Eval)* 
Because we are replaying a historical log, we force the AI to look at the context at Turn `N`. We then ask it: *"What is your next tool call?"* 
We do not use strict string matching (e.g. `ls -l` vs `ls -la`). Instead, we present the historical tool call and the compressed AI's tool call to an **LLM Judge** (like GPT-4o) and ask: *"Are these semantically equivalent steps toward solving the problem?"* If the Judge says yes, the turn passes.

**Use Case:** A granular debugging tool. It gives you the **theoretical upper bound** of your compression ratio and identifies exactly *which* turn caused the AI's reasoning to break.

---

## 3. Perturbation Testing (Single-Step Replacement)

**Status:** ❌ Not Yet Implemented

**Industry Name:** Perturbation Testing (or Counterfactual Evaluation)

**What it does:** 
Instead of compressing the entire history, we compress **only one specific step** (e.g., Turn 4) and let the rest of the dynamic simulation run normally. This scientifically isolates whether compressing a specific context block causes a cascade failure later.

**How we evaluate it (Real Eval + Self-Healing Check):** 
We run the full dynamic task and check the final result (using the same real code execution and success criteria as Mode 1). 
Crucially, **we want to see if self-healing occurs.** If compressing Turn 4 destroys context, but the AI realizes it's missing data, re-queries the file, and then passes the final test, the strategy is deemed safe. We grade this on **Efficiency Penalty**: Did compressing Turn 4 cause the AI to take 4 extra recovery turns? If so, the strategy is too aggressive for that step.

**Use Case:** Deep analysis. Testing the AI's "context healing" ability and fine-tuning how aggressive a compression strategy can safely be.
