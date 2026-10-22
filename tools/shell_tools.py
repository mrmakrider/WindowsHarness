"""
Shell Tools for WindowsHarness.

Provides shell command execution, background processes, and terminal interaction.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Optional

from shell.executor import ShellCommand, ShellExecutor, run_command, run_command_streaming
from tools.registry import Tool, ToolContext, ToolResult, register_tool


class ShellTool(Tool):
    """Execute a shell command."""

    name = "shell"
    description = "Execute a shell command and return its output."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 300},
            "use_pty": {"type": "boolean", "description": "Use PTY for interactive commands", "default": False},
        },
        "required": ["command"],
    }
    required_params = ["command"]
    requires_approval = True
    display_name = "Shell Command"

    async def execute(self, command: str, cwd: str = ".", timeout: float = 300, use_pty: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_cwd = self.context.resolve_path(cwd)

        try:
            result = await run_command(
                command,
                cwd=full_cwd,
                timeout=timeout,
                use_pty=use_pty,
            )

            output = result.combined
            display = f"💻 {command}\n{output[:1000]}{'...' if len(output) > 1000 else ''}"

            if result.returncode == 0:
                return ToolResult.ok(
                    output={"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
                    display=display,
                )
            else:
                return ToolResult.err(
                    error=f"Command exited with code {result.returncode}",
                    display=display,
                    metadata={"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
                )
        except TimeoutError:
            return ToolResult.err(
                error=f"Command timed out after {timeout}s",
                display=f"⏱️ {command} (timed out)",
            )
        except Exception as e:
            return ToolResult.err(f"Error executing command: {e}", display=f"❌ {command}: {e}")


class BackgroundShellTool(Tool):
    """Start a background shell process."""

    name = "bg_shell"
    description = "Start a long-running shell process in the background."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "name": {"type": "string", "description": "Optional name for the process"},
        },
        "required": ["command"],
    }
    required_params = ["command"]
    requires_approval = True
    display_name = "Background Shell"

    async def execute(self, command: str, cwd: str = ".", name: Optional[str] = None, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_cwd = self.context.resolve_path(cwd)
        executor = ShellExecutor(default_cwd=full_cwd)

        try:
            shell_cmd = ShellCommand(cmd=command, cwd=full_cwd)
            bg_proc = await executor.start_background(shell_cmd)

            proc_name = name or f"bg_{bg_proc.id}"
            return ToolResult.ok(
                output={"process_id": bg_proc.id, "name": proc_name, "command": command},
                display=f"🔄 Started background process: {proc_name} ({bg_proc.id})\nCommand: {command}",
            )
        except Exception as e:
            return ToolResult.err(f"Error starting background process: {e}", display=f"❌ bg_shell: {e}")


class WaitBackgroundTool(Tool):
    """Wait for a background process to complete."""

    name = "wait_bg"
    description = "Wait for a background process to complete and get its output."
    parameters = {
        "type": "object",
        "properties": {
            "process_id": {"type": "string", "description": "Background process ID"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 300},
        },
        "required": ["process_id"],
    }
    required_params = ["process_id"]
    display_name = "Wait Background"

    async def execute(self, process_id: str, timeout: float = 300, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        # We need access to the executor - this would need to be passed via context
        # For now, return an error indicating this needs proper integration
        return ToolResult.err(
            error="Background process management requires executor context",
            display="❌ wait_bg needs executor integration",
        )


class KillBackgroundTool(Tool):
    """Kill a background process."""

    name = "kill_bg"
    description = "Kill a running background process."
    parameters = {
        "type": "object",
        "properties": {
            "process_id": {"type": "string", "description": "Background process ID"},
        },
        "required": ["process_id"],
    }
    required_params = ["process_id"]
    requires_approval = True
    display_name = "Kill Background"

    async def execute(self, process_id: str, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        return ToolResult.err(
            error="Background process management requires executor context",
            display="❌ kill_bg needs executor integration",
        )


class ListBackgroundTool(Tool):
    """List all background processes."""

    name = "list_bg"
    description = "List all background processes."
    parameters = {"type": "object", "properties": {}}
    required_params = []
    display_name = "List Background"

    async def execute(self, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        return ToolResult.err(
            error="Background process management requires executor context",
            display="❌ list_bg needs executor integration",
        )


# Register shell tools
def register_shell_tools():
    register_tool(ShellTool(), "shell")
    register_tool(BackgroundShellTool(), "shell")
    register_tool(WaitBackgroundTool(), "shell")
    register_tool(KillBackgroundTool(), "shell")
    register_tool(ListBackgroundTool(), "shell")
