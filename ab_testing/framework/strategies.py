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


# Registry of available strategies
STRATEGIES = {
    "none": no_compression,
    "noise_strip": strip_tool_noise,
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
