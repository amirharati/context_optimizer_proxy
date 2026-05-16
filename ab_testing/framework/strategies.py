"""
Compression strategies for context optimization.

This module is shared between the test harness and live proxy.
Each strategy is a pure function: messages_in -> messages_out
"""

import re
import copy
from typing import List, Dict, Any


def strip_tool_noise(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove boilerplate noise from tool result messages.
    
    Based on Finding 1 from compression_research.md:
    - Shell timing: "Command completed in X ms."
    - Shell state: "Shell state (cwd, env vars) persists..."
    - CWD notes: "Current directory: /path"
    - Exit code headers: "Exit code: 0\\n\\nCommand output:\\n\\n```"
    - Code fence closures: "```\\n\\n"
    - TODO boilerplate: "Make sure to follow and update your TODO list..."
    - TODO headers: "Here are the latest contents of your todo list:"
    - Sandbox notes: "This command ran outside the sandbox..."
    
    Args:
        messages: List of message dicts (OpenAI format)
        
    Returns:
        Deep copy of messages with noise patterns removed from tool results
    """
    # Deep copy to avoid mutating input
    messages = copy.deepcopy(messages)
    
    # Regex patterns to strip (order matters for some patterns)
    patterns = [
        # Shell timing
        (r'Command completed in \d+ ms\.\n*', ''),
        
        # Shell state note (multi-line)
        (r'Shell state \(cwd, env vars\) persists for subsequent calls\.\n*', ''),
        
        # Current directory
        (r'Current directory: [^\n]+\n*', ''),
        
        # Exit code header with code fence opener
        (r'Exit code: \d+\n+Command output:\n+```[a-z]*\n', ''),
        
        # Standalone code fence closures (at end of content)
        (r'\n*```\n*$', ''),
        
        # TODO boilerplate (long multi-line pattern)
        (r'Make sure to follow and update your TODO list.*?(?=\n\n|\Z)', '', re.DOTALL),
        
        # TODO header
        (r'Here are the latest contents of your todo list:\n*', ''),
        
        # Sandbox note (can be very long)
        (r'This command ran (?:outside|inside) the sandbox[^\n]*(?:\n(?!Command|Exit|Shell)[^\n]*)*', ''),
        
        # Generic "no restrictions" / "because it matched" fragments
        (r'\(no restrictions\)[^\n]*\n*', ''),
        (r'because it matched[^\n]*\n*', ''),
    ]
    
    for msg in messages:
        # Only process tool result messages
        if msg.get("role") != "tool":
            continue
            
        content = msg.get("content", "")
        
        # Handle both string content and list-of-blocks content (multimodal)
        if isinstance(content, str):
            # Apply all patterns
            for pattern, replacement, *flags in patterns:
                regex_flags = flags[0] if flags else 0
                content = re.sub(pattern, replacement, content, flags=regex_flags)
            
            # Clean up excessive whitespace
            content = re.sub(r'\n{3,}', '\n\n', content)  # Max 2 newlines
            content = content.strip()
            
            msg["content"] = content
            
        elif isinstance(content, list):
            # Multimodal content - process text blocks
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    for pattern, replacement, *flags in patterns:
                        regex_flags = flags[0] if flags else 0
                        text = re.sub(pattern, replacement, text, flags=regex_flags)
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    text = text.strip()
                    block["text"] = text
    
    return messages


def no_compression(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Baseline strategy: no compression, return messages as-is.
    
    Used for A/B comparison to measure compression impact.
    """
    return copy.deepcopy(messages)


def path_compression(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compress file paths by aliasing common stems.
    
    Based on Finding 2 from compression_research.md:
    - Workspace path → $W
    - Common parent directory → $C
    - Adds legend to system prompt for LLM understanding
    
    Args:
        messages: List of message dicts (OpenAI format)
        
    Returns:
        Deep copy of messages with paths aliased
    """
    messages = copy.deepcopy(messages)
    
    # Step 1: Detect workspace root and common stem
    workspace_path = None
    common_stem = None
    
    # Try to find workspace path in system prompt or early messages
    for msg in messages[:3]:  # Check first few messages
        content = msg.get("content", "")
        if isinstance(content, str):
            # Look for common patterns
            # Pattern 1: "Workspace Path: /path/to/workspace"
            match = re.search(r'[Ww]orkspace[:\s]+([/\w\-_.]+)', content)
            if match:
                workspace_path = match.group(1)
                break
            
            # Pattern 2: Find paths in content (e.g., /Users/username/Dropbox/...)
            paths = re.findall(r'(/(?:Users|home)/[/\w\-_.]+)', content)
            if paths:
                workspace_path = paths[0]
                break
    
    # If still no workspace, try to infer from file paths in tool messages
    if not workspace_path:
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str):
                    paths = re.findall(r'(/(?:Users|home)/[/\w\-_.]+)', content)
                    if paths:
                        workspace_path = paths[0]
                        break
    
    # Extract common stem (parent directories)
    if workspace_path:
        parts = workspace_path.split('/')
        # Take up to the 4th level (e.g., /Users/username/Dropbox/CodingProjects)
        if len(parts) >= 4:
            common_stem = '/'.join(parts[:5])  # /Users/username/Dropbox/CodingProjects
    
    # If we couldn't detect paths, return unchanged
    if not workspace_path and not common_stem:
        return messages
    
    # Step 2: Replace occurrences in all messages
    replacements_made = False
    
    for msg in messages:
        content = msg.get("content", "")
        
        if isinstance(content, str):
            original_content = content
            
            # Replace workspace path first (more specific)
            if workspace_path:
                content = content.replace(workspace_path, "$W")
            
            # Then replace common stem
            if common_stem and common_stem != workspace_path:
                content = content.replace(common_stem, "$C")
            
            if content != original_content:
                replacements_made = True
                msg["content"] = content
                
        elif isinstance(content, list):
            # Multimodal content - process text blocks
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    original_text = text
                    
                    if workspace_path:
                        text = text.replace(workspace_path, "$W")
                    
                    if common_stem and common_stem != workspace_path:
                        text = text.replace(common_stem, "$C")
                    
                    if text != original_text:
                        replacements_made = True
                        block["text"] = text
    
    # Step 3: Add legend to system prompt if we made replacements
    if replacements_made:
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    legend_parts = []
                    if workspace_path:
                        legend_parts.append(f"$W = {workspace_path}")
                    if common_stem and common_stem != workspace_path:
                        legend_parts.append(f"$C = {common_stem}")
                    
                    legend = "\n[System Note: Paths are aliased. " + ", ".join(legend_parts) + "]"
                    msg["content"] = content + legend
                break
    
    return messages


def noise_and_paths(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Combined strategy: strip noise then compress paths.
    
    Applies strategies in sequence:
    1. strip_tool_noise - Remove boilerplate
    2. path_compression - Alias common paths
    
    Args:
        messages: List of message dicts (OpenAI format)
        
    Returns:
        Messages with both optimizations applied
    """
    messages = strip_tool_noise(messages)
    messages = path_compression(messages)
    return messages


# Registry of available strategies
STRATEGIES = {
    "none": no_compression,
    "noise_strip": strip_tool_noise,
    "path_compression": path_compression,
    "noise_and_paths": noise_and_paths,
}


def apply_strategy(strategy_name: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply a named compression strategy to messages.
    
    Args:
        strategy_name: Strategy identifier (e.g., "none", "noise_strip")
        messages: Input messages
        
    Returns:
        Compressed messages
        
    Raises:
        ValueError: If strategy_name is not recognized
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(STRATEGIES.keys())}")
    
    return STRATEGIES[strategy_name](messages)
