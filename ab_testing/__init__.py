"""A/B Testing Framework for Context Compression Strategies"""

from .framework.strategies import STRATEGIES, apply_strategy, strip_tool_noise, no_compression
from .framework.simulator import RuntimeSimulator
from .framework.scenario import Scenario, load_scenario, list_scenarios
from .framework.tool_schemas import get_tool_schemas, get_read_tool_schema, get_shell_tool_schema

__all__ = [
    'STRATEGIES',
    'apply_strategy',
    'strip_tool_noise',
    'no_compression',
    'RuntimeSimulator',
    'Scenario',
    'load_scenario',
    'list_scenarios',
    'get_tool_schemas',
]
