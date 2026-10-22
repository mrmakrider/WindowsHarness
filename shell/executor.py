"""
Async shell executor with PTY support for Windows.

Provides subprocess management with streaming output, PTY allocation,
and background process handling.
"""

from __future__ import annotations

import asyncio
import os
import signal
import shlex
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

try:
    import winpty
    HAS_WINPTY = True
except ImportError:
    HAS_WINPTY = False
    winpty = None  # type: ignore


@dataclass
class ShellCommand:
    """A command to execute."""

    cmd: str
    args: list[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Optional[dict[str, str]] = None
    timeout: float = 300.0
    use_pty: bool = False
    shell: bool = True  # Run through shell (cmd.exe /c or bash -c)

    def to_command_line(self) -> str:
        """Convert to shell command line."""
        if self.shell:
            return self.cmd + (" " + " ".join(shlex.quote(a) for a in self.args) if self.args else "")
        return " ".join([self.cmd] + [shlex.quote(a) for a in self.args])


@dataclass
class ProcessOutput:
    """Output from a process."""

    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    pid: Optional[int] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[int]:
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None

    @property
    def combined(self) -> str:
        return self.stdout + self.stderr


@dataclass
class BackgroundProcess:
    """A running background process."""

    id: str
    cmd: ShellCommand
    process: asyncio.subprocess.Process
    stdout_task: Optional[asyncio.Task] = None
    stderr_task: Optional[asyncio.Task] = None
    stdout_buffer: list[str] = field(default_factory=list)
    stderr_buffer: list[str] = field(default_factory=list)
    output_callback: Optional[Callable[[str, bool], None]] = None  # (text, is_stderr)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    returncode: Optional[int] = None

    def get_output(self, stderr: bool = False) -> str:
        return "".join(self.stderr_buffer if stderr else self.stdout_buffer)

    def get_combined_output(self) -> str:
        return "".join(self.stdout_buffer) + "".join(self.stderr_buffer)


class ShellExecutor:
    """Async shell command executor."""

    def __init__(
        self,
        default_cwd: Optional[str] = None,
        default_env: Optional[dict[str, str]] = None,
        default_shell: Optional[str] = None,
    ):
        self.default_cwd = default_cwd or os.getcwd()
        self.default_env = default_env or os.environ.copy()
        self.default_shell = default_shell or self._detect_default_shell()
        self._background_processes: dict[str, BackgroundProcess] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _detect_default_shell() -> str:
        """Detect the default shell for the platform."""
        if sys.platform == "win32":
            # Prefer PowerShell Core, then Windows PowerShell, then cmd
            for shell in ["pwsh", "powershell", "cmd"]:
                if ShellExecutor._which(shell):
                    return shell
            return "cmd"
        else:
            # Unix-like: prefer bash, then sh
            for shell in ["bash", "zsh", "sh"]:
                if ShellExecutor._which(shell):
                    return shell
            return "sh"

    @staticmethod
    def _which(cmd: str) -> bool:
        """Check if command exists in PATH."""
        from shutil import which
        return which(cmd) is not None

    def _build_env(self, extra_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        env = self.default_env.copy()
        if extra_env:
            env.update(extra_env)
        return env

    def _build_cwd(self, cwd: Optional[str] = None) -> str:
        return cwd or self.default_cwd

    async def run(
        self,
        cmd: ShellCommand,
        stdout_callback: Optional[Callable[[str], None]] = None,
        stderr_callback: Optional[Callable[[str], None]] = None,
    ) -> ProcessOutput:
        """Run a command and return its output."""
        env = self._build_env(cmd.env)
        cwd = self._build_cwd(cmd.cwd)

        if sys.platform == "win32" and cmd.use_pty and HAS_WINPTY:
            return await self._run_pty(cmd, env, cwd, stdout_callback, stderr_callback)
        else:
            return await self._run_subprocess(cmd, env, cwd, stdout_callback, stderr_callback)

    async def _run_subprocess(
        self,
        cmd: ShellCommand,
        env: dict[str, str],
        cwd: str,
        stdout_callback: Optional[Callable[[str], None]],
        stderr_callback: Optional[Callable[[str], None]],
    ) -> ProcessOutput:
        """Run using asyncio subprocess (no PTY)."""
        if cmd.shell:
            shell_cmd = [self.default_shell]
            if self.default_shell in ("pwsh", "powershell"):
                shell_cmd += ["-Command", cmd.to_command_line()]
            elif self.default_shell == "cmd":
                shell_cmd += ["/c", cmd.to_command_line()]
            else:
                shell_cmd += ["-c", cmd.to_command_line()]
            proc_cmd = shell_cmd
        else:
            proc_cmd = [cmd.cmd] + cmd.args

        proc = await asyncio.create_subprocess_exec(
            *proc_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        output = ProcessOutput(pid=proc.pid, started_at=datetime.now())

        async def read_stream(stream: asyncio.StreamReader, is_stderr: bool, callback: Optional[Callable[[str], None]]):
            buffer = []
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                buffer.append(text)
                if callback:
                    callback(text)
            return "".join(buffer)

        stdout_task = asyncio.create_task(read_stream(proc.stdout, False, stdout_callback))
        stderr_task = asyncio.create_task(read_stream(proc.stderr, True, stderr_callback))

        try:
            await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), timeout=cmd.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {cmd.timeout}s")

        output.stdout = stdout_task.result()
        output.stderr = stderr_task.result()
        output.returncode = proc.returncode
        output.completed_at = datetime.now()

        return output

    async def _run_pty(
        self,
        cmd: ShellCommand,
        env: dict[str, str],
        cwd: str,
        stdout_callback: Optional[Callable[[str], None]],
        stderr_callback: Optional[Callable[[str], None]],
    ) -> ProcessOutput:
        """Run using winpty for PTY support on Windows."""
        # winpty doesn't integrate well with asyncio, use subprocess with PTY
        # This is a simplified version - full PTY support needs more work
        return await self._run_subprocess(cmd, env, cwd, stdout_callback, stderr_callback)

    async def start_background(
        self,
        cmd: ShellCommand,
        output_callback: Optional[Callable[[str, bool], None]] = None,
    ) -> BackgroundProcess:
        """Start a background process."""
        env = self._build_env(cmd.env)
        cwd = self._build_cwd(cmd.cwd)

        if cmd.shell:
            shell_cmd = [self.default_shell]
            if self.default_shell in ("pwsh", "powershell"):
                shell_cmd += ["-Command", cmd.to_command_line()]
            elif self.default_shell == "cmd":
                shell_cmd += ["/c", cmd.to_command_line()]
            else:
                shell_cmd += ["-c", cmd.to_command_line()]
            proc_cmd = shell_cmd
        else:
            proc_cmd = [cmd.cmd] + cmd.args

        proc = await asyncio.create_subprocess_exec(
            *proc_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        bg_proc = BackgroundProcess(
            id=uuid.uuid4().hex[:8],
            cmd=cmd,
            process=proc,
            output_callback=output_callback,
        )

        async def read_stream(stream: asyncio.StreamReader, is_stderr: bool):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if is_stderr:
                    bg_proc.stderr_buffer.append(text)
                else:
                    bg_proc.stdout_buffer.append(text)
                if bg_proc.output_callback:
                    bg_proc.output_callback(text, is_stderr)

        bg_proc.stdout_task = asyncio.create_task(read_stream(proc.stdout, False))
        bg_proc.stderr_task = asyncio.create_task(read_stream(proc.stderr, True))

        async with self._lock:
            self._background_processes[bg_proc.id] = bg_proc

        # Monitor for completion
        asyncio.create_task(self._monitor_background(bg_proc))

        return bg_proc

    async def _monitor_background(self, bg_proc: BackgroundProcess) -> None:
        """Monitor background process for completion."""
        try:
            await bg_proc.process.wait()
        except Exception:
            pass
        finally:
            bg_proc.completed_at = datetime.now()
            bg_proc.returncode = bg_proc.process.returncode
            # Clean up tasks
            if bg_proc.stdout_task:
                await bg_proc.stdout_task
            if bg_proc.stderr_task:
                await bg_proc.stderr_task

    async def wait_background(self, proc_id: str, timeout: Optional[float] = None) -> BackgroundProcess:
        """Wait for a background process to complete."""
        async with self._lock:
            bg_proc = self._background_processes.get(proc_id)
        if not bg_proc:
            raise ValueError(f"Background process {proc_id} not found")

        if timeout:
            await asyncio.wait_for(self._wait_background_internal(bg_proc), timeout=timeout)
        else:
            await self._wait_background_internal(bg_proc)

        return bg_proc

    async def _wait_background_internal(self, bg_proc: BackgroundProcess) -> None:
        if bg_proc.process.returncode is None:
            await bg_proc.process.wait()
        bg_proc.completed_at = datetime.now()
        bg_proc.returncode = bg_proc.process.returncode

    def kill_background(self, proc_id: str) -> bool:
        """Kill a background process."""
        bg_proc = self._background_processes.get(proc_id)
        if not bg_proc:
            return False

        try:
            bg_proc.process.kill()
        except ProcessLookupError:
            pass
        return True

    def get_background(self, proc_id: str) -> Optional[BackgroundProcess]:
        """Get a background process by ID."""
        return self._background_processes.get(proc_id)

    def list_background(self) -> list[BackgroundProcess]:
        """List all background processes."""
        return list(self._background_processes.values())

    async def cleanup_completed(self) -> int:
        """Remove completed background processes from tracking."""
        async with self._lock:
            completed = [
                pid for pid, proc in self._background_processes.items()
                if proc.completed_at is not None
            ]
            for pid in completed:
                del self._background_processes[pid]
            return len(completed)


# --- High-level convenience functions ---


async def run_command(
    command: str,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: float = 300.0,
    use_pty: bool = False,
) -> ProcessOutput:
    """Run a simple shell command string."""
    executor = ShellExecutor(default_cwd=cwd, default_env=env)
    shell_cmd = ShellCommand(cmd=command, cwd=cwd, env=env, timeout=timeout, use_pty=use_pty)
    return await executor.run(shell_cmd)


async def run_command_streaming(
    command: str,
    on_stdout: Callable[[str], None],
    on_stderr: Callable[[str], None],
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: float = 300.0,
) -> ProcessOutput:
    """Run a command with streaming callbacks."""
    executor = ShellExecutor(default_cwd=cwd, default_env=env)
    shell_cmd = ShellCommand(cmd=command, cwd=cwd, env=env, timeout=timeout)
    return await executor.run(shell_cmd, stdout_callback=on_stdout, stderr_callback=on_stderr)
