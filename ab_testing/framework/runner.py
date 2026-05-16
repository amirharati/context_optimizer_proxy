"""
A/B test runner with real LLM integration through the proxy.

Orchestrates test scenarios by:
1. Sending HTTP requests to the live proxy (main.py)
2. Intercepting tool calls and providing simulated results
3. Collecting metrics from actual API responses
4. Comparing different compression strategies
"""

import json
import time
import httpx
import tempfile
import subprocess
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from .scenario import Scenario
from .simulator import RuntimeSimulator
from .tool_schemas import get_tool_schemas
from .strategies import STRATEGIES


class TestMetrics:
    """Metrics collected during a test run."""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
        self.turns = 0
        self.duration_ms = 0
        self.tool_calls = 0
        self.success = None
        self.success_details = []
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dict for reporting."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "turns": self.turns,
            "duration_ms": self.duration_ms,
            "tool_calls": self.tool_calls,
            "success": self.success,
            "success_details": self.success_details,
        }


class TestRunner:
    """
    Runs A/B tests against the live proxy server.
    
    The proxy applies compression and forwards to real LLM APIs.
    This runner provides simulated tool execution responses.
    """
    
    def __init__(
        self,
        proxy_url: str = "http://localhost:8000",
        model: str = "anthropic/claude-3-haiku-20240307",
        max_turns: int = 10,
        timeout: float = 120.0,
        temperature: float = 0.0,
        force_full_logging: bool = True,
        custom_log_dir: str = None,
        artifacts_dir: str = None,
        run_index: int = 0,
    ):
        """
        Initialize test runner.
        
        Args:
            proxy_url: URL of the proxy server (main.py)
            model: Model to use for testing
            max_turns: Maximum conversation turns (safety limit)
            timeout: HTTP timeout in seconds
            temperature: LLM temperature (default 0.0 for deterministic testing)
            force_full_logging: Whether to force full session logging (bypassing server env var)
            custom_log_dir: Custom sub-directory for session logs (relative to proxy's LOG_DIR)
            artifacts_dir: Absolute path to directory where virtual_fs artifacts should be saved
        """
        self.proxy_url = proxy_url
        self.model = model
        self.max_turns = max_turns
        self.timeout = timeout
        self.temperature = temperature
        self.force_full_logging = force_full_logging
        self.custom_log_dir = custom_log_dir
        self.artifacts_dir = artifacts_dir
        self.run_index = run_index
        self.client = httpx.Client(timeout=timeout)
    
    def _check_docker(self) -> bool:
        """Check if Docker daemon is running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def run_scenario(
        self,
        scenario: Scenario,
        strategy_name: str = "none",
    ) -> Dict[str, Any]:
        """
        Run a single scenario with a specific compression strategy.
        
        Flow:
        1. Load initial messages from scenario
        2. Send to proxy (which applies strategy)
        3. LLM responds (might request tools)
        4. Intercept tool calls and use simulator
        5. Send tool results back to proxy
        6. Repeat until LLM stops requesting tools
        7. Collect actual tokens from API responses
        
        Args:
            scenario: Test scenario to run
            strategy_name: Compression strategy to use (e.g., "none", "noise_strip")
            
        Returns:
            Dict with metrics and results
        """
        print(f"\n{'='*70}")
        print(f"Running: {scenario.name}")
        print(f"Strategy: {strategy_name} | Model: {self.model}")
        print(f"{'='*70}\n")
        
        # Check if Docker is required and available
        needs_docker = (
            "Shell" in scenario.available_tools or
            any(c.get("type") == "run_command" for c in scenario.success_criteria)
        )
        
        if needs_docker and not self._check_docker():
            print("❌ ERROR: Docker is required but not running!")
            print("   Please start Docker Desktop and try again.")
            print("   Verify with: docker info")
            return {
                "error": "Docker daemon is not running",
                "scenario": scenario.name,
                "strategy": strategy_name
            }
        
        # Determine execution directory for this strategy
        run_temp_dir = None
        if self.artifacts_dir:
            import os
            scenario_safe_name = scenario.name.replace(" ", "_").lower()
            run_temp_dir = os.path.join(self.artifacts_dir, "virtual_fs", scenario_safe_name, strategy_name, f"run_{self.run_index:03d}")
            os.makedirs(run_temp_dir, exist_ok=True)
            
        simulator = RuntimeSimulator(scenario.to_dict(), run_dir=run_temp_dir)
        metrics = TestMetrics()
        start_time = time.time()
        
        # Initialize messages (keep system for now, remove before sending to proxy for non-Anthropic)
        messages = scenario.get_initial_messages()
        tools = get_tool_schemas(scenario.available_tools)
        
        print(f"Initial setup: {len(messages)} messages, {len(tools)} tools available")
        
        # Conversation loop
        for turn in range(self.max_turns):
            metrics.turns = turn + 1
            print(f"\n--- Turn {turn + 1} ---")
            
            # Prepare request: apply strategy and format for proxy
            messages_to_send = self._apply_strategy(messages, strategy_name)
            request_body = self._build_request(messages_to_send, tools)
            
            print(f"Sending: {len(request_body['messages'])} messages")
            
            headers = {"Content-Type": "application/json"}
            if self.force_full_logging:
                headers["x-proxy-full-logging"] = "true"
            if self.custom_log_dir:
                headers["x-proxy-log-dir"] = self.custom_log_dir
            # Force a fresh session per (scenario, strategy, run_index) so the session
            # logger doesn't merge them into one file via first-message hash detection.
            scenario_safe = scenario.name.replace(" ", "_").lower()
            session_key = f"{scenario_safe}__{strategy_name}__r{self.run_index:03d}"
            headers["x-proxy-session-key"] = session_key
            
            # Send to proxy
            try:
                response = self.client.post(
                    f"{self.proxy_url}/v1/chat/completions",
                    json=request_body,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()
            except Exception as e:
                print(f"❌ Proxy error: {e}")
                return {"error": str(e), "scenario": scenario.name, "strategy": strategy_name}
            
            # Check for API errors
            if "error" in result:
                print(f"❌ API error: {result['error']}")
                return {"error": result['error'], "scenario": scenario.name, "strategy": strategy_name}
            
            # Extract metrics
            usage = result.get("usage", {})
            in_tokens = usage.get("prompt_tokens", 0)
            out_tokens = usage.get("completion_tokens", 0)
            metrics.total_input_tokens += in_tokens
            metrics.total_output_tokens += out_tokens
            metrics.total_tokens += usage.get("total_tokens", 0)
            
            print(f"Tokens: {in_tokens} input, {out_tokens} output")
            
            # Get assistant response
            choices = result.get("choices", [])
            if not choices:
                print("❌ No response choices")
                break
            
            assistant_message = choices[0].get("message", {})
            if not assistant_message:
                print("❌ No message in choice")
                break
            
            # Add to message history
            messages.append(assistant_message)
            
            # Check for tool calls
            tool_calls = assistant_message.get("tool_calls", [])
            if not tool_calls:
                print("✓ LLM finished (no tool calls)")
                break
            
            print(f"LLM requested {len(tool_calls)} tool(s)")
            metrics.tool_calls += len(tool_calls)
            
            # Execute tool calls using simulator and add results
            for tool_call in tool_calls:
                tool_id = tool_call.get("id", "")
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                
                try:
                    tool_args = json.loads(function.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}
                
                print(f"  → {tool_name}({list(tool_args.keys())})")
                
                # Use simulator to execute
                tool_result = simulator.handle_tool_call(tool_name, tool_args)
                
                # Determine field name and content format based on model provider
                # OpenAI format: "tool_call_id" with string content
                # Anthropic format: "tool_use_id" with array content [{"type": "text", "text": "..."}]
                is_openai = self.model.startswith("openai/") or "gpt" in self.model.lower()
                
                if is_openai:
                    tool_id_field = "tool_call_id"
                    tool_content = tool_result
                else:
                    tool_id_field = "tool_use_id"
                    tool_content = [{"type": "text", "text": tool_result}]
                
                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    tool_id_field: tool_id,
                    "content": tool_content,
                })
        
        metrics.duration_ms = int((time.time() - start_time) * 1000)
        
        # Evaluate success criteria
        if scenario.success_criteria:
            success, details = self._evaluate_success(simulator, metrics, scenario.success_criteria, run_temp_dir)
            metrics.success = success
            metrics.success_details = details
            print(f"Success Evaluation: {'PASSED' if success else 'FAILED'}")
            for d in details:
                print(f"  {d}")
        
        print(f"\n{'='*70}")
        print(f"✓ Complete: {metrics.turns} turns, {metrics.tool_calls} tools called")
        print(f"  Input: {metrics.total_input_tokens} | Output: {metrics.total_output_tokens} | Total: {metrics.total_tokens}")
        print(f"  Time: {metrics.duration_ms}ms")
        print(f"{'='*70}\n")
        
        # Clean up Docker container
        simulator.cleanup()
        
        return {
            "scenario": scenario.name,
            "strategy": strategy_name,
            "model": self.model,
            "metrics": metrics.to_dict(),
        }
    
    def _evaluate_success(self, simulator: RuntimeSimulator, metrics: TestMetrics, criteria: List[Dict[str, Any]], run_temp_dir: str = None) -> tuple[bool, List[str]]:
        """Evaluate success criteria at the end of a scenario run."""
        success = True
        details = []
        for c in criteria:
            ctype = c.get("type")
            if ctype == "file_contains":
                path = c.get("path", "")
                expected = c.get("expected_text", "")
                content = simulator.virtual_fs.get(path, "")
                if expected in content:
                    details.append(f"✓ file_contains: {path}")
                else:
                    details.append(f"✗ file_contains: {path} missing expected text")
                    success = False
            elif ctype == "max_turns":
                max_t = c.get("value", 10)
                if metrics.turns <= max_t:
                    details.append(f"✓ max_turns: {metrics.turns} <= {max_t}")
                else:
                    details.append(f"✗ max_turns: {metrics.turns} > {max_t}")
                    success = False
            elif ctype == "run_command":
                command = c.get("command", "")
                if not command:
                    details.append(f"✗ run_command: No command specified")
                    success = False
                    continue
                
                # Always use a temp directory for Docker execution (avoids Dropbox/symlink issues)
                # We write files from virtual_fs to temp, then execute
                import contextlib
                
                @contextlib.contextmanager
                def get_execution_dir():
                    # Always create a temporary directory for Docker execution
                    with tempfile.TemporaryDirectory() as temp_dir:
                        for fpath, fcontent in simulator.virtual_fs.items():
                            # Make path relative for the temp dir
                            rel_path = fpath.lstrip("/")
                            full_path = os.path.join(temp_dir, rel_path)
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, 'w') as f:
                                f.write(fcontent)
                        yield temp_dir
                            
                with get_execution_dir() as execution_dir:
                    try:
                        # Use Docker with temp dir for sandboxed execution (avoids Dropbox symlink issues)
                        # NOTE: Removed --rm for debugging - containers will stay alive
                        docker_cmd = [
                            "docker", "run",
                            "--network", "none",
                            "-v", f"{execution_dir}:/workspace",
                            "-w", "/workspace",
                            "python:3.11-alpine",
                            "sh", "-c", command
                        ]
                        
                        result = subprocess.run(
                            docker_cmd,
                            capture_output=True,
                            text=True,
                            timeout=c.get("timeout", 10)
                        )
                        
                        # Check for Docker errors and fail immediately
                        if result.returncode != 0:
                            if "Cannot connect to the Docker daemon" in result.stderr:
                                details.append(f"✗ run_command: Docker daemon is not running. Please start Docker.")
                                success = False
                            elif "error while creating mount source path" in result.stderr or "operation not permitted" in result.stderr:
                                details.append(f"✗ run_command: Docker failed to mount directory.\nStderr: {result.stderr.strip()}")
                                success = False
                            else:
                                details.append(f"✗ run_command: '{command}' failed (exit {result.returncode})\nStderr: {result.stderr.strip()}")
                                success = False
                        else:
                            details.append(f"✓ run_command: '{command}' exited 0")
                    except subprocess.TimeoutExpired:
                        details.append(f"✗ run_command: '{command}' timed out")
                        success = False
                    except FileNotFoundError:
                        details.append(f"✗ run_command: Docker executable not found. Please install Docker.")
                        success = False
            else:
                details.append(f"? Unknown criteria type: {ctype}")
        return success, details
    
    def _apply_strategy(self, messages: List[Dict], strategy_name: str) -> List[Dict]:
        """Apply compression strategy to messages."""
        if strategy_name not in STRATEGIES:
            return messages
        try:
            return STRATEGIES[strategy_name](messages)
        except Exception as e:
            print(f"⚠ Strategy {strategy_name} failed: {e}, using original")
            return messages
    
    def _build_request(self, messages: List[Dict], tools: List[Dict]) -> Dict[str, Any]:
        """Build request body for proxy, handling model-specific formatting."""
        is_anthropic = self.model.startswith("anthropic/")
        
        if is_anthropic:
            # Anthropic: system as separate parameter
            system_prompt = None
            messages_without_system = []
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                else:
                    messages_without_system.append(msg)
            
            request = {
                "model": self.model,
                "messages": messages_without_system,
                "tools": tools,
                "stream": False,
                "max_tokens": 4096,
                "temperature": self.temperature,
            }
            if system_prompt:
                request["system"] = system_prompt
        else:
            # OpenRouter/OpenAI: system in messages
            request = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "max_tokens": 4096,
                "temperature": self.temperature,
            }
        
        return request
    
    def compare_strategies(
        self,
        scenario: Scenario,
        strategies: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the same scenario with multiple strategies and compare results.
        
        Args:
            scenario: Test scenario
            strategies: List of strategy names to test (default: ["none", "noise_strip"])
            
        Returns:
            Comparison results with metrics for each strategy
        """
        if strategies is None:
            strategies = ["none", "noise_strip"]
        
        results = {}
        
        for strategy in strategies:
            if strategy not in STRATEGIES:
                print(f"Warning: Unknown strategy '{strategy}', skipping")
                continue
            
            result = self.run_scenario(scenario, strategy)
            results[strategy] = result
        
        # Calculate deltas
        comparison = self._calculate_comparison(results)
        
        return {
            "scenario": scenario.name,
            "model": self.model,
            "strategies_tested": strategies,
            "results": results,
            "comparison": comparison,
        }
    
    def _calculate_comparison(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comparison metrics between strategies."""
        if "none" not in results or "error" in results["none"]:
            return {}
        
        baseline = results["none"].get("metrics")
        if not baseline:
            return {}
        
        comparison = {}
        
        for strategy, result in results.items():
            if strategy == "none" or "error" in result:
                continue
            
            metrics = result.get("metrics", {})
            if not metrics:
                continue
            
            # Calculate savings
            baseline_tokens = baseline.get("total_tokens", 0)
            compressed_tokens = metrics.get("total_tokens", 0)
            token_savings = baseline_tokens - compressed_tokens
            token_savings_pct = (token_savings / baseline_tokens * 100) if baseline_tokens > 0 else 0
            
            comparison[strategy] = {
                "baseline_tokens": baseline_tokens,
                "compressed_tokens": compressed_tokens,
                "token_savings": token_savings,
                "token_savings_pct": round(token_savings_pct, 2),
                # Keep an unrounded version for accurate aggregation across runs
                "token_savings_pct_raw": token_savings_pct,
            }
        
        return comparison
    
    def close(self):
        """Close HTTP client."""
        self.client.close()
