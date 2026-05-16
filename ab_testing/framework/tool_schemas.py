"""
Tool schema definitions in OpenAI format.

These schemas define the tools available to the LLM during test scenarios.
Descriptions match Cursor's actual tool descriptions for realistic simulation.

Implemented: Read, Shell, Write, StrReplace, Grep
Future: AwaitShell, Glob, Delete, TodoWrite, EditNotebook, ReadLints, etc.
"""

from typing import List, Dict, Any


def get_read_tool_schema() -> Dict[str, Any]:
    """
    Read tool: Read file contents from virtual filesystem.
    Description matches Cursor's actual Read tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "Read",
            "description": """Reads a file from the local filesystem. You can access any file directly by using this tool.
If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters
- Lines in the output are numbered starting at 1, using following format: LINE_NUMBER|LINE_CONTENT
- You have the capability to call multiple tools in a single response. It is always better to speculatively read multiple files as a batch that are potentially useful.
- If you read a file that exists but has empty contents you will receive 'File is empty.'""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path of the file to read."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "The line number to start reading from. Only provide if the file is too large to read at once."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "The number of lines to read. Only provide if the file is too large to read at once."
                    }
                },
                "required": ["path"]
            }
        }
    }


def get_shell_tool_schema() -> Dict[str, Any]:
    """
    Shell tool: Execute shell commands.
    Description matches Cursor's actual Shell tool (abbreviated).
    """
    return {
        "type": "function",
        "function": {
            "name": "Shell",
            "description": """Executes a given command in a shell session with optional foreground timeout.

IMPORTANT: This tool is for terminal operations like git, npm, docker, etc. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead.

Usage notes:
- The command argument is required.
- The shell starts in the workspace root and is stateful across sequential calls. Current working directory and environment variables persist between calls.
- It is very helpful if you write a clear, concise description of what this command does in 5-10 words.
- VERY IMPORTANT: You MUST avoid using search commands like `find` and `grep`. Instead use Grep, Glob to search. You MUST avoid read tools like `cat`, `head`, and `tail`, and use Read to read files.
- When issuing multiple commands that are independent and can run in parallel, make multiple Shell tool calls in a single message.
- If the commands depend on each other and must run sequentially, use a single Shell call with '&&' to chain them together.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute"
                    },
                    "working_directory": {
                        "type": "string",
                        "description": "The absolute path to the working directory to execute the command in (defaults to current directory)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Clear, concise description of what this command does in 5-10 words"
                    }
                },
                "required": ["command"]
            }
        }
    }


def get_write_tool_schema() -> Dict[str, Any]:
    """
    Write tool: Write contents to a file in the virtual filesystem.
    Description matches Cursor's actual Write tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "Write",
            "description": """Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to modify"
                    },
                    "contents": {
                        "type": "string",
                        "description": "The contents to write to the file"
                    }
                },
                "required": ["path", "contents"]
            }
        }
    }


def get_str_replace_tool_schema() -> Dict[str, Any]:
    """
    StrReplace tool: Cursor's primary tool for editing existing files.
    This is the MOST USED edit tool in real Cursor sessions.
    Description matches Cursor's actual StrReplace tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "StrReplace",
            "description": """Performs exact string replacements in files.

Usage:
- When editing text, ensure you preserve the exact indentation (tabs/spaces) as it appears before.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if old_string is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use replace_all to change every instance of old_string.
- Use replace_all for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance.
- Optional parameter: replace_all (boolean, default false) — if true, replaces all occurrences of old_string in the file.

If you want to create a new file, use the Write tool instead.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to modify"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The text to replace"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with (must be different from old_string)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences of old_string (default false)"
                    }
                },
                "required": ["path", "old_string", "new_string"]
            }
        }
    }


def get_grep_tool_schema() -> Dict[str, Any]:
    """
    Grep tool: Search for patterns in files.
    Description matches Cursor's actual Grep tool (abbreviated).
    """
    return {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": """A powerful search tool built on ripgrep.

Usage:
- Prefer using Grep for search tasks when you know the exact symbols or strings to search for.
- Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
- Filter files with glob parameter (e.g., "*.js", "**/*.tsx") or type parameter (e.g., "js", "py", "rust")
- Output modes: "content" shows matching lines (default), "files_with_matches" shows only file paths
- Results are capped for responsiveness; when truncation occurs, the results report "at least" counts.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regular expression pattern to search for in file contents"
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in. Defaults to workspace root."
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\")"
                    }
                },
                "required": ["pattern"]
            }
        }
    }


# ============================================================================
# FUTURE TOOLS (not yet implemented in simulator)
# ============================================================================

def get_await_shell_tool_schema() -> Dict[str, Any]:
    """
    AwaitShell tool: Check or poll a backgrounded shell job.
    NOT YET IMPLEMENTED in simulator.
    """
    return {
        "type": "function",
        "function": {
            "name": "AwaitShell",
            "description": """Check or poll a backgrounded shell job. For work that does not have a task id, you can omit the task_id arg to sleep for the full block_until_ms duration.

Usage:
- Prefer NOT to poll reflexively with Await. Multitask on independent work while backgrounded jobs run.
- Poll with Await only when your very next step is blocked on this specific job's result.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Optional shell id to poll."
                    },
                    "block_until_ms": {
                        "type": "number",
                        "description": "Max sleep time to block before returning (in milliseconds). Defaults to 30000ms."
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Block until the regex matches stdout/stderr stream."
                    }
                },
                "required": []
            }
        }
    }


def get_glob_tool_schema() -> Dict[str, Any]:
    """
    Glob tool: Search for files matching a glob pattern.
    NOT YET IMPLEMENTED in simulator.
    """
    return {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": """Tool to search for files matching a glob pattern.

- Works fast with codebases of any size
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns""",
            "parameters": {
                "type": "object",
                "properties": {
                    "glob_pattern": {
                        "type": "string",
                        "description": "The glob pattern to match files against."
                    },
                    "target_directory": {
                        "type": "string",
                        "description": "Absolute path to directory to search in. Defaults to workspace root."
                    }
                },
                "required": ["glob_pattern"]
            }
        }
    }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

# Implemented tools (handlers exist in simulator.py)
IMPLEMENTED_TOOLS = {
    "Read": get_read_tool_schema,
    "Shell": get_shell_tool_schema,
    "Write": get_write_tool_schema,
    "StrReplace": get_str_replace_tool_schema,
    "Grep": get_grep_tool_schema,
}

# Future tools (schemas defined but no handlers yet)
FUTURE_TOOLS = {
    "AwaitShell": get_await_shell_tool_schema,
    "Glob": get_glob_tool_schema,
    # More to add: Delete, EditNotebook, TodoWrite, ReadLints, etc.
}

ALL_TOOLS = {**IMPLEMENTED_TOOLS, **FUTURE_TOOLS}


def get_tool_schemas(tool_names: List[str]) -> List[Dict[str, Any]]:
    """
    Get tool schemas for the specified tool names.
    
    Args:
        tool_names: List of tool names (e.g., ["Read", "Shell", "Write", "StrReplace"])
        
    Returns:
        List of tool schemas in OpenAI format
        
    Raises:
        ValueError: If a tool name is not recognized
    """
    schemas = []
    for name in tool_names:
        if name not in ALL_TOOLS:
            raise ValueError(f"Unknown tool: {name}. Available: {list(ALL_TOOLS.keys())}")
        schemas.append(ALL_TOOLS[name]())
    
    return schemas


def list_implemented_tools() -> List[str]:
    """Return list of tools with working handlers in simulator."""
    return list(IMPLEMENTED_TOOLS.keys())


def list_future_tools() -> List[str]:
    """Return list of tools with schemas but no handlers yet."""
    return list(FUTURE_TOOLS.keys())
