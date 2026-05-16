"""
A/B Testing Framework for Context Compression Strategies

This package provides infrastructure to test compression strategies against real LLM providers
using simulated tool execution environments.

Core modules:
- simulator: Virtual filesystem and tool execution
- tool_schemas: OpenAI-format tool definitions
- strategies: Compression strategy implementations
- scenario: Test scenario loader and validator
- runner: Test orchestration and metrics collection
"""

__version__ = "0.1.0"
