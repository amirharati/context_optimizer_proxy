# Tool Comparison: Cursor vs A/B Test Simulator

This document tracks the implementation status of tools compared to real Cursor sessions.

## Tool Usage Statistics (from real session_316c3647.jsonl)

| Tool | Usage Count | % of Total |
|------|-------------|------------|
| Shell | 1554 | 38.7% |
| StrReplace | 1202 | 30.0% |
| AwaitShell | 504 | 12.6% |
| Read | 420 | 10.5% |
| Write | 168 | 4.2% |
| TodoWrite | 123 | 3.1% |
| Grep | 42 | 1.0% |

## Implementation Status

### ✅ Implemented (5 tools)

| Tool | Output Format | Notes |
|------|---------------|-------|
| **Shell** | Exit code, output fence, timing, state note | Timing hardcoded to 100ms for determinism |
| **Read** | `     1\|code...` (line numbers) | Matches Cursor format exactly |
| **Write** | `Wrote contents to {path}` | For creating new files |
| **StrReplace** | `The file {path} has been updated.` | Primary edit tool - 30% of all tool calls! |
| **Grep** | `<workspace_result>...</workspace_result>` | Basic regex search |

### 🔜 Future (14 tools)

| Tool | Priority | Description |
|------|----------|-------------|
| **AwaitShell** | HIGH | Wait for background shell (12.6% usage) |
| **Glob** | MEDIUM | Find files by pattern |
| **Delete** | LOW | Delete files |
| **TodoWrite** | LOW | Task management (3.1% usage) |
| **EditNotebook** | LOW | Jupyter notebook editing |
| **ReadLints** | LOW | Linter errors |
| **SemanticSearch** | LOW | Semantic code search |
| **WebSearch** | LOW | Web search |
| **WebFetch** | LOW | URL fetching |
| **AskQuestion** | LOW | User interaction |
| **Task** | LOW | Subagent spawning |
| **FetchMcpResource** | LOW | MCP resources |
| **SwitchMode** | LOW | Mode switching |
| **CallMcpTool** | LOW | MCP tool calls |

## Output Format Verification

All implemented tools have been verified against real Cursor session logs to ensure output formats match exactly:

### Shell Output
```
Exit code: 0

Command output:

```
<actual output>
```

Command completed in 100 ms.

Shell state (cwd, env vars) persists for subsequent calls.

This command ran inside the sandbox with default restrictions.
```

### Read Output
```
     1|import os
     2|import json
     3|...
```
(Line numbers right-aligned to 6 chars with pipe separator)

### Write Output
```
Wrote contents to /path/to/file.py
```

### StrReplace Output
```
The file /path/to/file.py has been updated.
```

### Grep Output
```
<workspace_result workspace_path="/workspace">
path/to/file.py
  12:matching line content
  45:another match
</workspace_result>
```

## Schema Verbosity

Tool schemas now include verbose descriptions matching Cursor's actual prompts:

| Tool | Cursor Desc Length | Our Desc Length | Match |
|------|-------------------|-----------------|-------|
| Shell | ~12,500 chars | ~1,200 chars | Abbreviated |
| Read | ~1,000 chars | ~800 chars | Good |
| Write | ~375 chars | ~350 chars | Good |
| StrReplace | ~775 chars | ~700 chars | Good |
| Grep | ~1,200 chars | ~500 chars | Abbreviated |

Note: We use abbreviated descriptions for Shell and Grep to reduce token overhead while maintaining essential guidance.

## Coverage Analysis

With 5 implemented tools, we cover:
- **83.4%** of tool usage by count (Shell + StrReplace + Read + Write + Grep)
- The main editing workflow (Read → StrReplace → Shell for testing)
- The main file creation workflow (Write)

Adding AwaitShell would bring coverage to **96%**.
