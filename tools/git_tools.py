"""
Git Tools for WindowsHarness.

Provides Git operations: status, diff, log, commit, push, etc.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from tools.registry import Tool, ToolContext, ToolResult, register_tool


class GitTool(Tool):
    """Base class for Git tools."""

    def __init__(self, context: Optional[ToolContext] = None):
        super().__init__(context)
        self._repo = None

    def _get_repo(self, cwd: str) -> "git.Repo":
        import git
        if self._repo is None or self._repo.working_dir != cwd:
            self._repo = git.Repo(cwd, search_parent_directories=True)
        return self._repo


class GitStatusTool(GitTool):
    """Show git status."""

    name = "git_status"
    description = "Show git working tree status."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
        },
        "required": [],
    }
    required_params = []
    display_name = "Git Status"

    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)
            status = repo.git.status(porcelain=True)
            branch = repo.active_branch.name

            if not status:
                return ToolResult.ok(
                    output={"branch": branch, "clean": True},
                    display=f"✅ Git status: {branch} (clean)",
                )

            lines = status.strip().split("\n")
            output = {"branch": branch, "clean": False, "files": []}

            for line in lines:
                if len(line) >= 3:
                    index_status = line[0]
                    work_status = line[1]
                    filepath = line[3:]
                    output["files"].append({
                        "path": filepath,
                        "index": index_status,
                        "worktree": work_status,
                    })

            display_lines = [f"📋 Git status: {branch}"]
            for f in output["files"]:
                display_lines.append(f"  {f['index']}{f['worktree']} {f['path']}")

            return ToolResult.ok(
                output=output,
                display="\n".join(display_lines),
            )
        except Exception as e:
            return ToolResult.err(f"Error getting git status: {e}", display=f"❌ git_status: {e}")


class GitDiffTool(GitTool):
    """Show git diff."""

    name = "git_diff"
    description = "Show git diff for working tree or staged changes."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "staged": {"type": "boolean", "description": "Show staged changes", "default": False},
            "file": {"type": "string", "description": "Specific file to diff"},
        },
        "required": [],
    }
    required_params = []
    display_name = "Git Diff"

    async def execute(self, path: str = ".", staged: bool = False, file: Optional[str] = None, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if staged:
                diff = repo.git.diff("--cached", file) if file else repo.git.diff("--cached")
            else:
                diff = repo.git.diff(file) if file else repo.git.diff()

            if not diff:
                return ToolResult.ok(
                    output={"diff": "", "staged": staged},
                    display="✅ No changes",
                )

            return ToolResult.ok(
                output={"diff": diff, "staged": staged},
                display=f"📝 Git diff ({'staged' if staged else 'unstaged'}){' for ' + file if file else ''}:\n{diff}",
            )
        except Exception as e:
            return ToolResult.err(f"Error getting git diff: {e}", display=f"❌ git_diff: {e}")


class GitLogTool(GitTool):
    """Show git log."""

    name = "git_log"
    description = "Show git commit history."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "limit": {"type": "integer", "description": "Maximum commits to show", "default": 20},
            "oneline": {"type": "boolean", "description": "One line per commit", "default": True},
            "file": {"type": "string", "description": "Show history for specific file"},
        },
        "required": [],
    }
    required_params = []
    display_name = "Git Log"

    async def execute(self, path: str = ".", limit: int = 20, oneline: bool = True, file: Optional[str] = None, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            args = ["--oneline"] if oneline else []
            args += ["-n", str(limit)]
            if file:
                args += ["--", file]

            log_output = repo.git.log(*args)

            commits = []
            for line in log_output.strip().split("\n"):
                if line:
                    parts = line.split(" ", 1)
                    commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})

            display = f"📜 Git log ({len(commits)} commits):\n" + "\n".join(
                f"  {c['hash']} {c['message']}" for c in commits
            )

            return ToolResult.ok(
                output={"commits": commits},
                display=display,
            )
        except Exception as e:
            return ToolResult.err(f"Error getting git log: {e}", display=f"❌ git_log: {e}")


class GitAddTool(GitTool):
    """Stage files for commit."""

    name = "git_add"
    description = "Stage files for commit."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "files": {"type": "array", "items": {"type": "string"}, "description": "Files to stage (empty = all)"},
        },
        "required": [],
    }
    required_params = []
    requires_approval = True
    display_name = "Git Add"

    async def execute(self, path: str = ".", files: list[str] = None, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if files:
                repo.index.add(files)
                staged = files
            else:
                repo.git.add(".")
                staged = ["all changes"]

            return ToolResult.ok(
                output={"staged": staged},
                display=f"✅ Staged: {', '.join(staged)}",
            )
        except Exception as e:
            return ToolResult.err(f"Error staging files: {e}", display=f"❌ git_add: {e}")


class GitCommitTool(GitTool):
    """Create a commit."""

    name = "git_commit"
    description = "Create a git commit with a message."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "message": {"type": "string", "description": "Commit message"},
            "amend": {"type": "boolean", "description": "Amend previous commit", "default": False},
        },
        "required": ["message"],
    }
    required_params = ["message"]
    requires_approval = True
    display_name = "Git Commit"

    async def execute(self, path: str = ".", message: str = "", amend: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if amend:
                commit = repo.index.commit(message, amend=True)
            else:
                commit = repo.index.commit(message)

            return ToolResult.ok(
                output={"hash": commit.hexsha[:8], "message": message},
                display=f"✅ Committed {commit.hexsha[:8]}: {message}",
            )
        except Exception as e:
            return ToolResult.err(f"Error committing: {e}", display=f"❌ git_commit: {e}")


class GitPushTool(GitTool):
    """Push commits to remote."""

    name = "git_push"
    description = "Push commits to a remote repository."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "remote": {"type": "string", "description": "Remote name", "default": "origin"},
            "branch": {"type": "string", "description": "Branch name (default: current)"},
            "force": {"type": "boolean", "description": "Force push", "default": False},
        },
        "required": [],
    }
    required_params = []
    requires_approval = True
    display_name = "Git Push"

    async def execute(self, path: str = ".", remote: str = "origin", branch: Optional[str] = None, force: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if branch is None:
                branch = repo.active_branch.name

            push_info = repo.git.push(remote, branch, force=force)

            return ToolResult.ok(
                output={"remote": remote, "branch": branch, "output": push_info},
                display=f"✅ Pushed to {remote}/{branch}",
            )
        except Exception as e:
            return ToolResult.err(f"Error pushing: {e}", display=f"❌ git_push: {e}")


class GitPullTool(GitTool):
    """Pull commits from remote."""

    name = "git_pull"
    description = "Pull commits from a remote repository."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "remote": {"type": "string", "description": "Remote name", "default": "origin"},
            "branch": {"type": "string", "description": "Branch name (default: current)"},
            "rebase": {"type": "boolean", "description": "Rebase instead of merge", "default": False},
        },
        "required": [],
    }
    required_params = []
    display_name = "Git Pull"

    async def execute(self, path: str = ".", remote: str = "origin", branch: Optional[str] = None, rebase: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if branch is None:
                branch = repo.active_branch.name

            if rebase:
                pull_info = repo.git.pull(remote, branch, rebase=True)
            else:
                pull_info = repo.git.pull(remote, branch)

            return ToolResult.ok(
                output={"remote": remote, "branch": branch, "output": pull_info},
                display=f"✅ Pulled from {remote}/{branch}",
            )
        except Exception as e:
            return ToolResult.err(f"Error pulling: {e}", display=f"❌ git_pull: {e}")


class GitBranchTool(GitTool):
    """Manage git branches."""

    name = "git_branch"
    description = "List, create, or delete git branches."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository path", "default": "."},
            "action": {"type": "string", "enum": ["list", "create", "delete", "switch"], "description": "Action to perform"},
            "name": {"type": "string", "description": "Branch name (for create/delete/switch)"},
            "force": {"type": "boolean", "description": "Force delete", "default": False},
        },
        "required": ["action"],
    }
    required_params = ["action"]
    requires_approval = True
    display_name = "Git Branch"

    async def execute(self, path: str = ".", action: str = "list", name: Optional[str] = None, force: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        try:
            repo = self._get_repo(full_path)

            if action == "list":
                branches = [b.name for b in repo.branches]
                current = repo.active_branch.name
                display = f"🌿 Branches (current: {current}):\n" + "\n".join(f"  {'*' if b == current else ' '} {b}" for b in branches)
                return ToolResult.ok(output={"branches": branches, "current": current}, display=display)

            elif action == "create":
                if not name:
                    return ToolResult.err("Branch name required for create")
                new_branch = repo.create_head(name)
                return ToolResult.ok(output={"branch": name}, display=f"✅ Created branch {name}")

            elif action == "delete":
                if not name:
                    return ToolResult.err("Branch name required for delete")
                repo.delete_head(name, force=force)
                return ToolResult.ok(output={"branch": name}, display=f"🗑️ Deleted branch {name}")

            elif action == "switch":
                if not name:
                    return ToolResult.err("Branch name required for switch")
                repo.git.checkout(name)
                return ToolResult.ok(output={"branch": name}, display=f"🔄 Switched to branch {name}")

            return ToolResult.err(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.err(f"Error with branch: {e}", display=f"❌ git_branch: {e}")


# Register git tools
def register_git_tools():
    register_tool(GitStatusTool(), "git")
    register_tool(GitDiffTool(), "git")
    register_tool(GitLogTool(), "git")
    register_tool(GitAddTool(), "git")
    register_tool(GitCommitTool(), "git")
    register_tool(GitPushTool(), "git")
    register_tool(GitPullTool(), "git")
    register_tool(GitBranchTool(), "git")
