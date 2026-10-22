"""
Workspace Filesystem Abstraction for WindowsHarness.

Provides a unified interface for file operations with support for
chat-scoped workspaces, git-aware operations, and unbounded access.
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Optional


@dataclass
class FileInfo:
    """File metadata."""

    path: str
    name: str
    is_dir: bool
    size: int
    modified: datetime
    permissions: str = ""


class WorkspaceFs(ABC):
    """Abstract filesystem interface."""

    @abstractmethod
    def resolve(self, path: str) -> str:
        """Resolve a path to absolute."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    def is_file(self, path: str) -> bool:
        """Check if path is a file."""
        pass

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        pass

    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read text file."""
        pass

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read binary file."""
        pass

    @abstractmethod
    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """Write text file."""
        pass

    @abstractmethod
    def write_bytes(self, path: str, content: bytes) -> None:
        """Write binary file."""
        pass

    @abstractmethod
    def list(self, path: str, recursive: bool = False, include_hidden: bool = False) -> list[FileInfo]:
        """List directory contents."""
        pass

    @abstractmethod
    def glob(self, pattern: str, path: str = ".") -> list[str]:
        """Find files matching glob pattern."""
        pass

    @abstractmethod
    def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        """Create directory."""
        pass

    @abstractmethod
    def delete(self, path: str, recursive: bool = False) -> None:
        """Delete file or directory."""
        pass

    @abstractmethod
    def move(self, src: str, dst: str, overwrite: bool = False) -> None:
        """Move/rename file."""
        pass

    @abstractmethod
    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        """Copy file."""
        pass

    @abstractmethod
    def stat(self, path: str) -> FileInfo:
        """Get file info."""
        pass


class LocalWorkspaceFs(WorkspaceFs):
    """Local filesystem implementation."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p.resolve())
        return str((self.root / path).resolve())

    def exists(self, path: str) -> bool:
        return Path(self.resolve(path)).exists()

    def is_file(self, path: str) -> bool:
        return Path(self.resolve(path)).is_file()

    def is_dir(self, path: str) -> bool:
        return Path(self.resolve(path)).is_dir()

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return Path(self.resolve(path)).read_text(encoding=encoding)

    def read_bytes(self, path: str) -> bytes:
        return Path(self.resolve(path)).read_bytes()

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        p = Path(self.resolve(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)

    def write_bytes(self, path: str, content: bytes) -> None:
        p = Path(self.resolve(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def list(self, path: str, recursive: bool = False, include_hidden: bool = False) -> list[FileInfo]:
        base = Path(self.resolve(path))
        results = []

        if recursive:
            for entry in base.rglob("*"):
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    results.append(FileInfo(
                        path=str(entry.relative_to(self.root)),
                        name=entry.name,
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    ))
                except (OSError, PermissionError):
                    continue
        else:
            for entry in base.iterdir():
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    results.append(FileInfo(
                        path=str(entry.relative_to(self.root)),
                        name=entry.name,
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    ))
                except (OSError, PermissionError):
                    continue

        results.sort(key=lambda f: (f.is_dir, f.name.lower()))
        return results

    def glob(self, pattern: str, path: str = ".") -> list[str]:
        base = Path(self.resolve(path))
        matches = base.rglob(pattern) if "**" in pattern else base.glob(pattern)
        return [str(m.relative_to(self.root)) for m in matches if m.is_file()]

    def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        Path(self.resolve(path)).mkdir(parents=parents, exist_ok=exist_ok)

    def delete(self, path: str, recursive: bool = False) -> None:
        p = Path(self.resolve(path))
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()

    def move(self, src: str, dst: str, overwrite: bool = False) -> None:
        src_p = Path(self.resolve(src))
        dst_p = Path(self.resolve(dst))
        if dst_p.exists() and not overwrite:
            raise FileExistsError(f"Destination exists: {dst}")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        src_p.rename(dst_p)

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        src_p = Path(self.resolve(src))
        dst_p = Path(self.resolve(dst))
        if dst_p.exists() and not overwrite:
            raise FileExistsError(f"Destination exists: {dst}")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        if src_p.is_dir():
            shutil.copytree(src_p, dst_p)
        else:
            shutil.copy2(src_p, dst_p)

    def stat(self, path: str) -> FileInfo:
        p = Path(self.resolve(path))
        stat = p.stat()
        return FileInfo(
            path=str(p.relative_to(self.root)),
            name=p.name,
            is_dir=p.is_dir(),
            size=stat.st_size if p.is_file() else 0,
            modified=datetime.fromtimestamp(stat.st_mtime),
        )


class ChatWorkspaceFs(WorkspaceFs):
    """Chat-scoped workspace with checkpoint support."""

    def __init__(self, base_fs: WorkspaceFs, chat_id: str):
        self.base_fs = base_fs
        self.chat_id = chat_id
        self._checkpoints: dict[str, dict[str, str]] = {}  # checkpoint_id -> {path: content}

    def resolve(self, path: str) -> str:
        return self.base_fs.resolve(path)

    def exists(self, path: str) -> bool:
        return self.base_fs.exists(path)

    def is_file(self, path: str) -> bool:
        return self.base_fs.is_file(path)

    def is_dir(self, path: str) -> bool:
        return self.base_fs.is_dir(path)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return self.base_fs.read_text(path, encoding)

    def read_bytes(self, path: str) -> bytes:
        return self.base_fs.read_bytes(path)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        # Track for potential checkpoint
        resolved = self.resolve(path)
        self.base_fs.write_text(path, content, encoding)

    def write_bytes(self, path: str, content: bytes) -> None:
        self.base_fs.write_bytes(path, content)

    def list(self, path: str, recursive: bool = False, include_hidden: bool = False) -> list[FileInfo]:
        return self.base_fs.list(path, recursive, include_hidden)

    def glob(self, pattern: str, path: str = ".") -> list[str]:
        return self.base_fs.glob(pattern, path)

    def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        self.base_fs.mkdir(path, parents, exist_ok)

    def delete(self, path: str, recursive: bool = False) -> None:
        self.base_fs.delete(path, recursive)

    def move(self, src: str, dst: str, overwrite: bool = False) -> None:
        self.base_fs.move(src, dst, overwrite)

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        self.base_fs.copy(src, dst, overwrite)

    def stat(self, path: str) -> FileInfo:
        return self.base_fs.stat(path)

    # Checkpoint methods
    def create_checkpoint(self, checkpoint_id: str) -> None:
        """Create a checkpoint of all tracked files."""
        # This would track files written since last checkpoint
        pass

    def restore_checkpoint(self, checkpoint_id: str) -> None:
        """Restore files from a checkpoint."""
        pass

    def list_checkpoints(self) -> list[str]:
        return list(self._checkpoints.keys())


class UnboundedFileFs(WorkspaceFs):
    """Filesystem with no root restriction (use with caution)."""

    def __init__(self):
        pass

    def resolve(self, path: str) -> str:
        return str(Path(path).resolve())

    def exists(self, path: str) -> bool:
        return Path(self.resolve(path)).exists()

    def is_file(self, path: str) -> bool:
        return Path(self.resolve(path)).is_file()

    def is_dir(self, path: str) -> bool:
        return Path(self.resolve(path)).is_dir()

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return Path(self.resolve(path)).read_text(encoding=encoding)

    def read_bytes(self, path: str) -> bytes:
        return Path(self.resolve(path)).read_bytes()

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        p = Path(self.resolve(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)

    def write_bytes(self, path: str, content: bytes) -> None:
        p = Path(self.resolve(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def list(self, path: str, recursive: bool = False, include_hidden: bool = False) -> list[FileInfo]:
        base = Path(self.resolve(path))
        results = []
        if recursive:
            for entry in base.rglob("*"):
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    results.append(FileInfo(
                        path=str(entry),
                        name=entry.name,
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    ))
                except (OSError, PermissionError):
                    continue
        else:
            for entry in base.iterdir():
                if not include_hidden and entry.name.startswith("."):
                    continue
                try:
                    stat = entry.stat()
                    results.append(FileInfo(
                        path=str(entry),
                        name=entry.name,
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    ))
                except (OSError, PermissionError):
                    continue
        results.sort(key=lambda f: (f.is_dir, f.name.lower()))
        return results

    def glob(self, pattern: str, path: str = ".") -> list[str]:
        base = Path(self.resolve(path))
        matches = base.rglob(pattern) if "**" in pattern else base.glob(pattern)
        return [str(m) for m in matches if m.is_file()]

    def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> None:
        Path(self.resolve(path)).mkdir(parents=parents, exist_ok=exist_ok)

    def delete(self, path: str, recursive: bool = False) -> None:
        p = Path(self.resolve(path))
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()

    def move(self, src: str, dst: str, overwrite: bool = False) -> None:
        src_p = Path(self.resolve(src))
        dst_p = Path(self.resolve(dst))
        if dst_p.exists() and not overwrite:
            raise FileExistsError(f"Destination exists: {dst}")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        src_p.rename(dst_p)

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        src_p = Path(self.resolve(src))
        dst_p = Path(self.resolve(dst))
        if dst_p.exists() and not overwrite:
            raise FileExistsError(f"Destination exists: {dst}")
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        if src_p.is_dir():
            shutil.copytree(src_p, dst_p)
        else:
            shutil.copy2(src_p, dst_p)

    def stat(self, path: str) -> FileInfo:
        p = Path(self.resolve(path))
        stat = p.stat()
        return FileInfo(
            path=str(p),
            name=p.name,
            is_dir=p.is_dir(),
            size=stat.st_size if p.is_file() else 0,
            modified=datetime.fromtimestamp(stat.st_mtime),
        )


def create_workspace_fs(root: str, chat_id: Optional[str] = None, unbounded: bool = False) -> WorkspaceFs:
    """Factory function to create appropriate filesystem."""
    if unbounded:
        return UnboundedFileFs()
    base = LocalWorkspaceFs(root)
    if chat_id:
        return ChatWorkspaceFs(base, chat_id)
    return base
