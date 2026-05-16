# Test Scenarios

This directory contains test scenarios for A/B testing compression strategies.

## Scenario Format

Each scenario is a JSON file with the following structure:

```json
{
  "name": "Scenario name",
  "description": "What this scenario tests",
  "system_prompt": "System prompt for the LLM",
  "available_tools": ["Read", "Write", "Shell"],
  "virtual_fs": {
    "/path/to/file": "file contents..."
  },
  "shell_responses": {
    "command": {
      "exit_code": 0,
      "stdout": "output...",
      "stderr": "",
      "duration_ms": 100
    }
  },
  "initial_cwd": "/workspace",
  "cache_mode": "on",
  "disable_cache": false,
  "turns": [
    {"role": "user", "content": "User message..."}
  ],
  "success_criteria": [
    {
      "type": "file_contains",
      "path": "/path/to/file",
      "expected_text": "correct code"
    },
    {
      "type": "run_command",
      "command": "python test.py",
      "timeout": 5
    }
  ]
}
```

## Fields

- **name**: Short name for the scenario
- **description**: What the scenario tests
- **system_prompt**: System prompt sent to the LLM (optional, defaults to basic assistant prompt)
- **available_tools**: List of tool names available (currently: "Read", "Write", "Shell")
- **virtual_fs**: Dictionary mapping file paths to contents
- **shell_responses**: Dictionary mapping shell commands to their outputs
- **initial_cwd**: Initial working directory (default: "/workspace")
- **cache_mode**: Optional `"on"` or `"off"`; controls cache behavior for this scenario when CLI does not override it.
- **disable_cache**: Optional boolean shortcut (`true` forces cache busting, `false` keeps cache behavior). Takes precedence over `cache_mode` inside the scenario.
- **turns**: Initial conversation turns (must start with user message)
- **success_criteria**: Array of checks to run at the end of the scenario to objectively evaluate if the AI succeeded.
  - `file_contains`: Checks if `expected_text` exists in `path`
  - `run_command`: Dumps the virtual filesystem to disk and runs a real shell command. Fails if exit code is not 0.
  - `max_turns`: Fails if the AI takes more than `value` turns (thrashing).

## Cache control precedence

1. `--disable-cache` CLI flag (global override)
2. Scenario `disable_cache` field
3. Scenario `cache_mode` field (`off` means cache busting)
4. Default is cache-on

## Shell Response Format

Shell responses include boilerplate that mirrors Cursor's actual output:

```json
{
  "exit_code": 0,
  "stdout": "command output",
  "stderr": "error output (if any)",
  "duration_ms": 100
}
```

The simulator will automatically add boilerplate like:
- "Command completed in X ms."
- "Shell state (cwd, env vars) persists..."
- "Current directory: /path"
- Exit code headers
- Sandbox notes

This boilerplate is what the `noise_strip` strategy removes.

## Available Scenarios

1. **simple_shell_noise.json** - Minimal scenario with shell commands
2. **file_read_noise.json** - Mix of Read and Shell tools
3. **fix_bug_execution.json** - Advanced scenario using the Write tool and real code execution success criteria

Add more scenarios as needed!
