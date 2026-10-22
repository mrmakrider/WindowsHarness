"""
File Tools for WindowsHarness.

Provides file system operations: read, write, edit, list, glob, grep.
"""

from __future__ import annotations

import os
import re
import fnmatch
from pathlib import Path
from typing import Any, Optional

from tools.registry import Tool, ToolContext, ToolResult, create_function_tool, register_tool


class ReadTool(Tool):
    """Read a file's contents."""

    name = "read"
    description = "Read the contents of a file. Supports text files with optional line range."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "offset": {"type": "integer", "description": "Starting line number (0-indexed)", "default": 0},
            "limit": {"type": "integer", "description": "Maximum number of lines to read", "default": 2000},
        },
        "required": ["path"],
    }
    required_params = ["path"]
    display_name = "Read File"

    async def execute(self, path: str, offset: int = 0, limit: int = 2000, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"File not found: {path}", display=f"❌ File not found: {path}")

        if not path_obj.is_file():
            return ToolResult.err(f"Not a file: {path}", display=f"❌ Not a file: {path}")

        try:
            content = path_obj.read_text(encoding="utf-8")
            lines = content.splitlines()

            if offset < 0:
                offset = 0
            if offset >= len(lines):
                return ToolResult.ok(
                    output="",
                    display=f"📄 {path} (empty or offset beyond end)",
                )

            end = min(offset + limit, len(lines))
            selected = lines[offset:end]

            output = "\n".join(selected)
            display = f"📄 {path} (lines {offset+1}-{end} of {len(lines)})"

            return ToolResult.ok(output=output, display=display, metadata={"total_lines": len(lines)})
        except UnicodeDecodeError:
            return ToolResult.err(f"Cannot read binary file: {path}", display=f"❌ Binary file: {path}")
        except Exception as e:
            return ToolResult.err(f"Error reading file: {e}", display=f"❌ Error reading {path}: {e}")


class WriteTool(Tool):
    """Write content to a file."""

    name = "write"
    description = "Write content to a file. Creates parent directories if needed."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write"},
            "create_dirs": {"type": "boolean", "description": "Create parent directories", "default": True},
        },
        "required": ["path", "content"],
    }
    required_params = ["path", "content"]
    requires_approval = True
    display_name = "Write File"

    async def execute(self, path: str, content: str, create_dirs: bool = True, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if create_dirs:
            path_obj.parent.mkdir(parents=True, exist_ok=True)

        try:
            path_obj.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            return ToolResult.ok(
                output=f"Written {size} bytes",
                display=f"✅ Written {path} ({size} bytes)",
            )
        except Exception as e:
            return ToolResult.err(f"Error writing file: {e}", display=f"❌ Error writing {path}: {e}")


class EditTool(Tool):
    """Edit a file using string replacement."""

    name = "edit"
    description = "Edit a file by replacing a specific string. More precise than write for small changes."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_string": {"type": "string", "description": "Exact string to replace"},
            "new_string": {"type": "string", "description": "Replacement string"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    }
    required_params = ["path", "old_string", "new_string"]
    requires_approval = True
    display_name = "Edit File"

    async def execute(self, path: str, old_string: str, new_string: str, replace_all: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"File not found: {path}", display=f"❌ File not found: {path}")

        try:
            content = path_obj.read_text(encoding="utf-8")

            if replace_all:
                if old_string not in content:
                    return ToolResult.err(f"String not found: {old_string[:50]}...", display=f"❌ String not found in {path}")
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                count = content.count(old_string)
                if count == 0:
                    return ToolResult.err(f"String not found: {old_string[:50]}...", display=f"❌ String not found in {path}")
                if count > 1:
                    return ToolResult.err(
                        f"String found {count} times, use replace_all=true or provide more context",
                        display=f"❌ Multiple matches in {path} (use replace_all or more context)",
                    )
                new_content = content.replace(old_string, new_string, 1)

            path_obj.write_text(new_content, encoding="utf-8")
            return ToolResult.ok(
                output=f"Replaced {count} occurrence(s)",
                display=f"✅ Edited {path} ({count} replacement(s))",
            )
        except Exception as e:
            return ToolResult.err(f"Error editing file: {e}", display=f"❌ Error editing {path}: {e}")


class ListTool(Tool):
    """List directory contents."""

    name = "list"
    description = "List files and directories in a path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list", "default": "."},
            "recursive": {"type": "boolean", "description": "List recursively", "default": False},
            "include_hidden": {"type": "boolean", "description": "Include hidden files", "default": False},
        },
        "required": [],
    }
    required_params = []
    display_name = "List Directory"

    async def execute(self, path: str = ".", recursive: bool = False, include_hidden: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"Path not found: {path}", display=f"❌ Path not found: {path}")

        if not path_obj.is_dir():
            return ToolResult.err(f"Not a directory: {path}", display=f"❌ Not a directory: {path}")

        try:
            entries = []
            if recursive:
                for entry in path_obj.rglob("*"):
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    rel = entry.relative_to(path_obj)
                    entries.append({
                        "path": str(rel),
                        "name": entry.name,
                        "type": "directory" if entry.is_dir() else "file",
                        "size": entry.stat().st_size if entry.is_file() else None,
                    })
            else:
                for entry in path_obj.iterdir():
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    entries.append({
                        "path": entry.name,
                        "name": entry.name,
                        "type": "directory" if entry.is_dir() else "file",
                        "size": entry.stat().st_size if entry.is_file() else None,
                    })

            # Sort: directories first, then files, alphabetically
            entries.sort(key=lambda e: (e["type"] == "file", e["name"].lower()))

            lines = []
            for e in entries:
                icon = "📁" if e["type"] == "directory" else "📄"
                size = f" ({e['size']} bytes)" if e["size"] is not None else ""
                lines.append(f"{icon} {e['path']}{size}")

            output = "\n".join(lines) if lines else "(empty)"
            return ToolResult.ok(
                output={"entries": entries},
                display=f"📂 {path} ({len(entries)} entries)\n{output}",
            )
        except Exception as e:
            return ToolResult.err(f"Error listing directory: {e}", display=f"❌ Error listing {path}: {e}")


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = "Find files matching a glob pattern (e.g., **/*.py)."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g., **/*.py)"},
            "path": {"type": "string", "description": "Base directory", "default": "."},
        },
        "required": ["pattern"],
    }
    required_params = ["pattern"]
    display_name = "Glob Files"

    async def execute(self, pattern: str, path: str = ".", **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"Path not found: {path}", display=f"❌ Path not found: {path}")

        try:
            matches = list(path_obj.rglob(pattern)) if "**" in pattern else list(path_obj.glob(pattern))
            matches = [m for m in matches if m.is_file()]

            rel_paths = [str(m.relative_to(path_obj)) for m in matches]
            rel_paths.sort()

            output = "\n".join(rel_paths) if rel_paths else "(no matches)"
            return ToolResult.ok(
                output={"matches": rel_paths},
                display=f"🔍 {pattern} in {path} ({len(rel_paths)} matches)\n{output}",
            )
        except Exception as e:
            return ToolResult.err(f"Error globbing: {e}", display=f"❌ Error globbing {pattern}: {e}")


class GrepTool(Tool):
    """Search file contents using regex."""

    name = "grep"
    description = "Search for a regex pattern in files."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory to search", "default": "."},
            "include": {"type": "string", "description": "File pattern to include (e.g., *.py)"},
            "exclude": {"type": "string", "description": "File pattern to exclude"},
            "case_sensitive": {"type": "boolean", "description": "Case sensitive search", "default": False},
        },
        "required": ["pattern"],
    }
    required_params = ["pattern"]
    display_name = "Grep Search"

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        include: Optional[str] = None,
        exclude: Optional[str] = None,
        case_sensitive: bool = False,
        **kwargs
    ) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"Path not found: {path}", display=f"❌ Path not found: {path}")

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult.err(f"Invalid regex: {e}", display=f"❌ Invalid regex: {e}")

        matches = []
        files_searched = 0

        for file_path in path_obj.rglob("*"):
            if not file_path.is_file():
                continue

            if include and not fnmatch.fnmatch(file_path.name, include):
                continue
            if exclude and fnmatch.fnmatch(file_path.name, exclude):
                continue

            files_searched += 1
            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(file_path.relative_to(path_obj)),
                            "line": i,
                            "text": line.strip(),
                        })
            except (UnicodeDecodeError, PermissionError):
                continue  # Skip binary/unreadable files

        # Limit output
        display_matches = matches[:50]
        lines = [f"📍 {m['file']}:{m['line']}: {m['text']}" for m in display_matches]
        output = "\n".join(lines) if lines else "(no matches)"

        return ToolResult.ok(
            output={"matches": matches, "files_searched": files_searched},
            display=f"🔎 grep '{pattern}' in {path} ({len(matches)} matches in {files_searched} files)\n{output}",
        )


class DeleteTool(Tool):
    """Delete a file or directory."""

    name = "delete"
    description = "Delete a file or directory (with recursive option)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to delete"},
            "recursive": {"type": "boolean", "description": "Delete directories recursively", "default": False},
        },
        "required": ["path"],
    }
    required_params = ["path"]
    requires_approval = True
    display_name = "Delete"

    async def execute(self, path: str, recursive: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"Path not found: {path}", display=f"❌ Path not found: {path}")

        try:
            if path_obj.is_dir():
                if recursive:
                    import shutil
                    shutil.rmtree(path_obj)
                    return ToolResult.ok(
                        output="Directory deleted",
                        display=f"🗑️ Deleted directory {path} (recursive)",
                    )
                else:
                    path_obj.rmdir()
                    return ToolResult.ok(
                        output="Directory deleted",
                        display=f"🗑️ Deleted empty directory {path}",
                    )
            else:
                path_obj.unlink()
                return ToolResult.ok(
                    output="File deleted",
                    display=f"🗑️ Deleted file {path}",
                )
        except OSError as e:
            return ToolResult.err(f"Error deleting: {e}", display=f"❌ Error deleting {path}: {e}")


class MoveTool(Tool):
    """Move or rename a file."""

    name = "move"
    description = "Move or rename a file or directory."
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite if destination exists", "default": False},
        },
        "required": ["source", "destination"],
    }
    required_params = ["source", "destination"]
    requires_approval = True
    display_name = "Move/Rename"

    async def execute(self, source: str, destination: str, overwrite: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        src = self.context.resolve_path(source)
        dst = self.context.resolve_path(destination)
        src_obj = Path(src)
        dst_obj = Path(dst)

        if not src_obj.exists():
            return ToolResult.err(f"Source not found: {source}", display=f"❌ Source not found: {source}")

        if dst_obj.exists() and not overwrite:
            return ToolResult.err(f"Destination exists: {destination}", display=f"❌ Destination exists (use overwrite=true)")

        try:
            dst_obj.parent.mkdir(parents=True, exist_ok=True)
            src_obj.rename(dst_obj)
            return ToolResult.ok(
                output="Moved successfully",
                display=f"📦 Moved {source} → {destination}",
            )
        except Exception as e:
            return ToolResult.err(f"Error moving: {e}", display=f"❌ Error moving {source}: {e}")


# Register all file tools
def register_file_tools():
    register_tool(ReadTool(), "file")
    register_tool(WriteTool(), "file")
    register_tool(EditTool(), "file")
    register_tool(ListTool(), "file")
    register_tool(GlobTool(), "file")
    register_tool(GrepTool(), "file")
    register_tool(DeleteTool(), "file")
    register_tool(MoveTool(), "file")
