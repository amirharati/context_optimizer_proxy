"""
Scenario loader and validator.

Loads test scenarios from JSON files and validates their structure.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


class Scenario:
    """
    Represents a test scenario with virtual environment and conversation flow.
    """
    
    def __init__(self, data: Dict[str, Any], filepath: str = None):
        """
        Initialize scenario from parsed JSON data.
        
        Args:
            data: Scenario dictionary
            filepath: Optional path to source file (for error messages)
        """
        self.filepath = filepath
        self.name = data.get("name", "Unnamed scenario")
        self.description = data.get("description", "")
        self.system_prompt = data.get("system_prompt", "You are a helpful coding assistant.")
        self.available_tools = data.get("available_tools", ["Read", "Shell"])
        import copy
        self.virtual_fs = copy.deepcopy(data.get("virtual_fs", {}))
        self.shell_responses = copy.deepcopy(data.get("shell_responses", {}))
        self.initial_cwd = data.get("initial_cwd", "/workspace")
        self.turns = copy.deepcopy(data.get("turns", []))
        self.success_criteria = copy.deepcopy(data.get("success_criteria", []))
        self.cache_mode = data.get("cache_mode")
        self.disable_cache = data.get("disable_cache")
        
        # Validate
        self._validate()
    
    def _validate(self):
        """
        Validate scenario structure.
        
        Raises:
            ValueError: If scenario is invalid
        """
        if not self.name:
            raise ValueError("Scenario must have a name")
        
        if not self.turns:
            raise ValueError("Scenario must have at least one turn")
        
        # Check first turn is from user
        if self.turns[0].get("role") != "user":
            raise ValueError("First turn must be from user")
        
        # Validate available_tools
        valid_tools = {"Read", "Shell", "Write", "StrReplace", "Grep"}
        for tool in self.available_tools:
            if tool not in valid_tools:
                raise ValueError(f"Unknown tool in available_tools: {tool}")

        if self.cache_mode is not None and self.cache_mode not in {"on", "off"}:
            raise ValueError("cache_mode must be 'on' or 'off' when provided")

        if self.disable_cache is not None and not isinstance(self.disable_cache, bool):
            raise ValueError("disable_cache must be a boolean when provided")
    
    def get_initial_messages(self) -> List[Dict[str, Any]]:
        """
        Get initial message list (system prompt + turns).
        
        Returns:
            List of messages in OpenAI format
        """
        messages = []
        
        # Add system prompt
        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })
        
        # Add any user/assistant turns from scenario
        messages.extend(self.turns)
        
        return messages
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert scenario back to dict for simulator."""
        import copy
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "available_tools": copy.deepcopy(self.available_tools),
            "virtual_fs": copy.deepcopy(self.virtual_fs),
            "shell_responses": copy.deepcopy(self.shell_responses),
            "initial_cwd": self.initial_cwd,
            "turns": copy.deepcopy(self.turns),
            "success_criteria": copy.deepcopy(self.success_criteria),
            "cache_mode": self.cache_mode,
            "disable_cache": self.disable_cache,
        }

    def resolve_disable_cache(self, cli_disable_cache: bool = False) -> bool:
        """
        Resolve effective cache behavior for this scenario.

        Priority:
        1) CLI --disable-cache (global override)
        2) Scenario disable_cache boolean
        3) Scenario cache_mode ('off' => disable cache)
        4) Default cache-on
        """
        if cli_disable_cache:
            return True
        if isinstance(self.disable_cache, bool):
            return self.disable_cache
        if self.cache_mode == "off":
            return True
        return False


def load_scenario(filepath: str) -> Scenario:
    """
    Load a scenario from JSON file.
    
    Args:
        filepath: Path to scenario JSON file
        
    Returns:
        Scenario object
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or scenario is malformed
    """
    path = Path(filepath)
    
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {filepath}")
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")
    
    return Scenario(data, filepath=str(path))


def list_scenarios(scenarios_dir: str = "scenarios") -> List[str]:
    """
    List all scenario files in a directory.
    
    Args:
        scenarios_dir: Directory containing scenario JSON files
        
    Returns:
        List of scenario file paths
    """
    path = Path(scenarios_dir)
    if not path.exists():
        return []
    
    return [str(f) for f in path.glob("*.json")]
