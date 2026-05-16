"""
Runtime simulator for tool execution.

Provides virtual filesystem and shell responses for test scenarios.
All tool execution is in-memory - no real file I/O or shell commands.
"""

import json
from typing import Dict, Any, Optional


import copy

class RuntimeSimulator:
    """
    Simulates Cursor's runtime environment for A/B testing.
    
    Provides:
    - Virtual filesystem (in-memory file contents)
    - Virtual shell (predefined command responses)
    - Tool execution handlers
    """
    
    def __init__(self, scenario: Dict[str, Any], run_dir: str = None):
        """
        Initialize simulator from scenario definition.
        
        Args:
            scenario: Scenario dict with virtual_fs and shell_responses
            run_dir: Optional absolute path to run directory for real execution
        """
        self.virtual_fs = copy.deepcopy(scenario.get("virtual_fs", {}))
        self.shell_responses = copy.deepcopy(scenario.get("shell_responses", {}))
        self.cwd = scenario.get("initial_cwd", "/workspace")
        self.run_dir = run_dir
        self.docker_container_id = None
        self.temp_exec_dir = None
        
        # Start a long-running Docker container if we'll be executing commands
        if self.run_dir:
            self._start_docker_container()

    @staticmethod
    def _to_disk_rel_path(vfs_path: str) -> str:
        """
        Convert virtual fs path to path relative to mounted /workspace.
        """
        if not vfs_path:
            return ""
        if vfs_path == "/workspace":
            return ""
        if vfs_path.startswith("/workspace/"):
            return vfs_path[len("/workspace/"):]
        if vfs_path.startswith("workspace/"):
            return vfs_path[len("workspace/"):]
        return vfs_path.lstrip("/")

    def _lookup_vfs_content(self, path: str) -> Optional[str]:
        """
        Resolve file content for both absolute and relative path styles.
        """
        candidates = [path]
        rel = self._to_disk_rel_path(path)
        if rel:
            candidates.extend([rel, f"/{rel}", f"/workspace/{rel}", f"workspace/{rel}"])
        for candidate in candidates:
            if candidate in self.virtual_fs:
                return self.virtual_fs[candidate]
        return None

    def _resolve_vfs_key(self, path: str) -> Optional[str]:
        """
        Resolve the canonical key currently present in virtual_fs for a path.
        """
        candidates = [path]
        rel = self._to_disk_rel_path(path)
        if rel:
            candidates.extend([rel, f"/{rel}", f"/workspace/{rel}", f"workspace/{rel}"])
        for candidate in candidates:
            if candidate in self.virtual_fs:
                return candidate
        return None
    
    def _start_docker_container(self):
        """Start a long-running Docker container for command execution."""
        import subprocess
        import tempfile
        
        # Create a temp directory that will live for the duration of the test
        self.temp_exec_dir = tempfile.mkdtemp()
        
        # Write initial virtual_fs to temp dir
        import os
        for fpath, content in self.virtual_fs.items():
            rel = self._to_disk_rel_path(fpath)
            full = os.path.join(self.temp_exec_dir, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        
        try:
            # Start container in detached mode with sleep infinity to keep it alive
            result = subprocess.run([
                "docker", "run", "-d",
                "--network", "none",
                "-v", f"{self.temp_exec_dir}:/workspace",
                "-w", "/workspace",
                "python:3.11-alpine",
                "sleep", "infinity"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.docker_container_id = result.stdout.strip()
                print(f"🐳 Started Docker container: {self.docker_container_id[:12]}")
            else:
                print(f"❌ Failed to start Docker container: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Docker error: {e}")
    
    def cleanup(self):
        """Stop and remove the Docker container."""
        if self.docker_container_id:
            import subprocess
            import shutil
            
            try:
                # Force remove container (kills and removes in one step)
                result = subprocess.run(
                    ["docker", "rm", "-f", self.docker_container_id], 
                    capture_output=True, 
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print(f"🐳 Cleaned up Docker container: {self.docker_container_id[:12]}")
                else:
                    print(f"⚠️  Failed to remove container: {result.stderr.strip()}")
            except subprocess.TimeoutExpired:
                print(f"⚠️  Timeout removing container {self.docker_container_id[:12]}")
            except Exception as e:
                print(f"⚠️  Error removing container: {e}")
            finally:
                # Always set to None so we don't try again
                self.docker_container_id = None
            
            # Clean up temp dir
            if self.temp_exec_dir:
                try:
                    shutil.rmtree(self.temp_exec_dir)
                except Exception as e:
                    print(f"⚠️  Error cleaning temp dir: {e}")
                finally:
                    self.temp_exec_dir = None
    
    def handle_read(self, path: str) -> str:
        """
        Handle Read tool call - return file contents from virtual FS.
        
        Formats output to match Cursor's Read tool format:
        Line numbers are right-aligned to 6 characters with pipe separator.
        Example: "     1|import os\n     2|import json\n"
        
        Args:
            path: File path to read
            
        Returns:
            File contents with line numbers (Cursor format)
        """
        content = self._lookup_vfs_content(path)
        if content is not None:
            # Format with line numbers like Cursor: "     1|code"
            lines = content.split('\n')
            numbered_lines = []
            for i, line in enumerate(lines, 1):
                # Right-align line number to 6 characters
                numbered_lines.append(f"{i:>6}|{line}")
            return '\n'.join(numbered_lines)
        else:
            # File not found
            return f"Error: File not found: {path}"
            
    def handle_write(self, path: str, contents: str) -> str:
        """
        Handle Write tool call - write file contents to virtual FS.
        
        Args:
            path: File path to write
            contents: Content to write
            
        Returns:
            Success message
        """
        existing_key = self._resolve_vfs_key(path)
        if existing_key:
            self.virtual_fs[existing_key] = contents
        else:
            self.virtual_fs[path] = contents
        return f"Wrote contents to {path}"
    
    def handle_shell(self, command: str) -> str:
        """
        Handle Shell tool call.
        If a run_dir is provided and the command isn't explicitly mocked,
        execute it for real using Docker exec on the long-running container.
        
        Args:
            command: Shell command to execute
            
        Returns:
            Formatted shell output with boilerplate (to test noise stripping)
        """
        import time
        import subprocess
        import os
        
        # Check if we should execute for real
        if self.docker_container_id and command not in self.shell_responses:
            start_t = time.time()
            
            # Sync current virtual_fs to temp dir before executing
            for fpath, content in self.virtual_fs.items():
                rel = self._to_disk_rel_path(fpath)
                full = os.path.join(self.temp_exec_dir, rel)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, 'w') as f:
                    f.write(content)
            
            try:
                # Execute command in the running container
                result = subprocess.run(
                    ["docker", "exec", self.docker_container_id, "sh", "-c", command],
                    capture_output=True, text=True, timeout=15
                )
                
                exit_code = result.returncode
                stdout = result.stdout
                stderr = result.stderr
                
                # Read any modified/new files back into virtual_fs.
                # Track which on-disk paths exist so we can detect deletions.
                if exit_code != 124: # Not timed out
                    seen_paths = set()
                    for root, dirs, files in os.walk(self.temp_exec_dir):
                        for file in files:
                            # Skip python cache
                            if file.endswith('.pyc') or '__pycache__' in root:
                                continue
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, self.temp_exec_dir)
                            try:
                                with open(full_path, 'r') as f:
                                    content = f.read()
                                # Normalize path to match virtual_fs format and record both
                                # variants so deletion detection covers either form.
                                if rel_path in self.virtual_fs:
                                    self.virtual_fs[rel_path] = content
                                    seen_paths.add(rel_path)
                                elif "/" + rel_path in self.virtual_fs:
                                    self.virtual_fs["/" + rel_path] = content
                                    seen_paths.add("/" + rel_path)
                                elif "/workspace/" + rel_path in self.virtual_fs:
                                    self.virtual_fs["/workspace/" + rel_path] = content
                                    seen_paths.add("/workspace/" + rel_path)
                                else:
                                    # New file created by the shell command
                                    self.virtual_fs[rel_path] = content
                                    seen_paths.add(rel_path)
                            except (UnicodeDecodeError, FileNotFoundError):
                                # Skip binary files / race conditions
                                pass
                    
                    # Detect deletions: any file in virtual_fs that previously existed
                    # but isn't on disk anymore should be removed.
                    for vfs_path in list(self.virtual_fs.keys()):
                        if vfs_path in seen_paths:
                            continue
                        # Check both rel and absolute forms on disk
                        rel = self._to_disk_rel_path(vfs_path)
                        on_disk = os.path.join(self.temp_exec_dir, rel)
                        if not os.path.exists(on_disk):
                            del self.virtual_fs[vfs_path]
                    
                    # Copy all files to run_dir for archival
                    if self.run_dir:
                        for fpath, content in self.virtual_fs.items():
                            rel = self._to_disk_rel_path(fpath)
                            full = os.path.join(self.run_dir, rel)
                            os.makedirs(os.path.dirname(full), exist_ok=True)
                            with open(full, 'w') as f:
                                f.write(content)
                                
            except subprocess.TimeoutExpired:
                exit_code = 124
                stdout = ""
                stderr = "Command timed out."
            except FileNotFoundError:
                return "Error: Docker executable not found. Please install Docker to execute shell commands."
                
            duration_ms = int((time.time() - start_t) * 1000)
            # Use a stable sandbox note that matches Cursor's output verbosity pattern.
            # The actual duration is captured in metrics but not exposed to the LLM to avoid noise.
            sandbox_note = "This command ran inside the sandbox with default restrictions."
            
        elif command in self.shell_responses:
            # Use predefined mock response
            response = self.shell_responses[command]
            exit_code = response.get("exit_code", 0)
            stdout = response.get("stdout", "")
            stderr = response.get("stderr", "")
            duration_ms = response.get("duration_ms", 100)
            sandbox_note = "This is a predefined mock response."
        else:
            # Command not in scenario and no run_dir to execute it for real
            return f"Error: Command not found in scenario and real execution disabled: {command}"
            
        # Construct full response with boilerplate patterns
        output_parts = []
        
        # Exit code header
        output_parts.append(f"Exit code: {exit_code}")
        output_parts.append("")
        output_parts.append("Command output:")
        output_parts.append("")
        output_parts.append("```")
        
        # Actual output
        if stdout:
            output_parts.append(stdout.rstrip())
        if stderr:
            output_parts.append(stderr.rstrip())
        
        output_parts.append("```")
        output_parts.append("")
        
        # Timing boilerplate. We keep this NOISE pattern (so compression strategies have
        # something to strip), but use a fixed value to ensure determinism across A/B test
        # runs. The real duration is recorded internally but not surfaced to the LLM.
        output_parts.append(f"Command completed in 100 ms.")
        output_parts.append("")
        
        # State persistence note
        output_parts.append("Shell state (cwd, env vars) persists for subsequent calls.")
        output_parts.append("")
        
        # Current directory
        output_parts.append(f"Current directory: {self.cwd}")
        output_parts.append("")
        
        # Sandbox note
        output_parts.append(sandbox_note)
        
        return "\n".join(output_parts)
    
    def handle_str_replace(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """
        Handle StrReplace tool call - replace text in a file (Cursor's primary edit tool).
        
        Output format matches Cursor exactly:
        "The file {path} has been updated."
        
        Args:
            path: File path to modify
            old_string: Text to find
            new_string: Replacement text
            replace_all: If True, replace all occurrences
            
        Returns:
            Success or error message
        """
        resolved_key = self._resolve_vfs_key(path)
        if not resolved_key:
            return f"Error: File not found: {path}"
        
        content = self.virtual_fs[resolved_key]
        
        if old_string not in content:
            return f"Error: old_string not found in {path}. The edit will FAIL if old_string is not unique in the file."
        
        # Check uniqueness if not replace_all
        if not replace_all and content.count(old_string) > 1:
            return f"Error: old_string appears {content.count(old_string)} times in {path}. Either provide more context to make it unique or use replace_all=true."
        
        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        
        self.virtual_fs[resolved_key] = new_content
        return f"The file {path} has been updated."
    
    def handle_grep(self, pattern: str, path: str = None) -> str:
        """
        Handle Grep tool call - search for pattern in virtual filesystem.
        
        Output format matches Cursor's Grep tool:
        <workspace_result workspace_path="...">
        filepath
          linenum:content
        </workspace_result>
        
        Args:
            pattern: Regex pattern to search for
            path: Optional path filter
            
        Returns:
            Search results in Cursor format
        """
        import re
        
        results = []
        workspace = "/workspace"
        
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"
        
        for fpath, content in self.virtual_fs.items():
            # Apply path filter if provided
            if path:
                normalized_filter = self._to_disk_rel_path(path)
                normalized_file = self._to_disk_rel_path(fpath)
                if not (fpath.startswith(path) or normalized_file.startswith(normalized_filter)):
                    continue
            
            lines = content.split('\n')
            file_matches = []
            
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    file_matches.append(f"  {i}:{line}")
            
            if file_matches:
                results.append(fpath.lstrip('/'))
                results.extend(file_matches)
        
        if not results:
            return f"No matches found for pattern: {pattern}"
        
        return f'<workspace_result workspace_path="{workspace}">\n' + '\n'.join(results) + '\n</workspace_result>'
    
    def handle_tool_call(self, tool_name: str, tool_arguments: Dict[str, Any]) -> str:
        """
        Generic tool call handler - routes to specific handlers.
        
        Args:
            tool_name: Name of tool being called (e.g., "Read", "Shell", "StrReplace")
            tool_arguments: Tool arguments as dict
            
        Returns:
            Tool result as string
        """
        if tool_name == "Read":
            return self.handle_read(tool_arguments.get("path", ""))
        elif tool_name == "Shell":
            return self.handle_shell(tool_arguments.get("command", ""))
        elif tool_name == "Write":
            return self.handle_write(tool_arguments.get("path", ""), tool_arguments.get("contents", ""))
        elif tool_name == "StrReplace":
            return self.handle_str_replace(
                tool_arguments.get("path", ""),
                tool_arguments.get("old_string", ""),
                tool_arguments.get("new_string", ""),
                tool_arguments.get("replace_all", False)
            )
        elif tool_name == "Grep":
            return self.handle_grep(
                tool_arguments.get("pattern", ""),
                tool_arguments.get("path")
            )
        else:
            return f"Error: Unknown tool: {tool_name}"
