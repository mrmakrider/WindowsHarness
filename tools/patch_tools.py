"""
Patch Tools for WindowsHarness.

Provides unified diff application, fuzzy editing, and patch utilities.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tools.registry import Tool, ToolContext, ToolResult, register_tool


@dataclass
class PatchHunk:
    """A single hunk in a unified diff."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[tuple[str, str]]  # (op, line) where op is ' ', '-', '+'


@dataclass
class Patch:
    """Parsed unified diff."""

    old_path: str
    new_path: str
    hunks: list[PatchHunk] = field(default_factory=list)

    @classmethod
    def parse(cls, diff_text: str) -> list["Patch"]:
        """Parse unified diff text into Patch objects."""
        patches = []
        lines = diff_text.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for diff header
            if line.startswith("--- "):
                old_path = line[4:].strip()
                i += 1
                if i >= len(lines):
                    break
                line = lines[i]
                if not line.startswith("+++ "):
                    continue
                new_path = line[4:].strip()
                i += 1

                patch = cls(old_path=old_path, new_path=new_path)

                # Parse hunks
                while i < len(lines):
                    line = lines[i]
                    if line.startswith("@@ "):
                        # Parse hunk header: @@ -old_start,old_lines +new_start,new_lines @@
                        match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
                        if match:
                            old_start = int(match.group(1))
                            old_lines = int(match.group(2)) if match.group(2) else 1
                            new_start = int(match.group(3))
                            new_lines = int(match.group(4)) if match.group(4) else 1
                            i += 1

                            hunk_lines = []
                            while i < len(lines):
                                hunk_line = lines[i]
                                if hunk_line.startswith("@@ ") or hunk_line.startswith("--- ") or hunk_line.startswith("+++ "):
                                    break
                                if hunk_line.startswith(" "):
                                    hunk_lines.append((" ", hunk_line[1:]))
                                elif hunk_line.startswith("-"):
                                    hunk_lines.append(("-", hunk_line[1:]))
                                elif hunk_line.startswith("+"):
                                    hunk_lines.append(("+", hunk_line[1:]))
                                else:
                                    # No prefix - treat as context
                                    hunk_lines.append((" ", hunk_line))
                                i += 1

                            patch.hunks.append(PatchHunk(
                                old_start=old_start,
                                old_lines=old_lines,
                                new_start=new_start,
                                new_lines=new_lines,
                                lines=hunk_lines,
                            ))
                        else:
                            i += 1
                    elif line.startswith("--- ") or line.startswith("+++ "):
                        # Next patch
                        break
                    else:
                        i += 1

                patches.append(patch)
            else:
                i += 1

        return patches

    def apply(self, content: str) -> tuple[str, bool]:
        """Apply patch to content. Returns (new_content, success)."""
        lines = content.splitlines(keepends=True)
        new_lines = lines[:]
        offset = 0

        for hunk in self.hunks:
            # Find the hunk location using context matching
            target_start = hunk.old_start - 1 + offset  # Convert to 0-indexed

            # Try exact match first
            match_start = self._find_hunk_match(new_lines, hunk, target_start)
            if match_start is None:
                # Try fuzzy match
                match_start = self._fuzzy_find_hunk(new_lines, hunk, target_start)
                if match_start is None:
                    return content, False

            # Apply the hunk
            new_lines, offset = self._apply_hunk(new_lines, hunk, match_start, offset)

        return "".join(new_lines), True

    def _find_hunk_match(self, lines: list[str], hunk: PatchHunk, start: int) -> Optional[int]:
        """Find exact match for hunk context."""
        # Extract context lines (unchanged lines)
        context = [line for op, line in hunk.lines if op == " "]
        if not context:
            return start if 0 <= start <= len(lines) else None

        # Try to find context in lines near start
        search_start = max(0, start - 10)
        search_end = min(len(lines), start + 10 + len(context))

        for i in range(search_start, search_end - len(context) + 1):
            if all(i + j < len(lines) and lines[i + j].rstrip("\n") == context[j] for j in range(len(context))):
                return i

        return None

    def _fuzzy_find_hunk(self, lines: list[str], hunk: PatchHunk, start: int) -> Optional[int]:
        """Fuzzy match using difflib."""
        context = [line for op, line in hunk.lines if op == " "]
        if not context:
            return start if 0 <= start <= len(lines) else None

        # Use difflib to find best match
        matcher = difflib.SequenceMatcher(None, [l.rstrip("\n") for l in lines], context)
        match = matcher.find_longest_match(0, len(lines), 0, len(context))

        if match.size >= len(context) * 0.7:  # At least 70% match
            return match.a
        return None

    def _apply_hunk(self, lines: list[str], hunk: PatchHunk, start: int, offset: int) -> tuple[list[str], int]:
        """Apply a single hunk at the given position."""
        new_lines = lines[:]
        delete_count = 0
        insert_lines = []

        for op, line in hunk.lines:
            if op == " ":
                # Context line - verify it matches
                if start + delete_count < len(new_lines):
                    delete_count += 1
            elif op == "-":
                # Delete line
                if start + delete_count < len(new_lines):
                    del new_lines[start + delete_count]
                    delete_count += 1
                    offset -= 1
            elif op == "+":
                # Insert line
                insert_lines.append((start + delete_count, line + "\n"))

        # Insert new lines
        for pos, line in reversed(insert_lines):
            new_lines.insert(pos, line)
            offset += 1

        return new_lines, offset


class ApplyPatchTool(Tool):
    """Apply a unified diff patch."""

    name = "apply_patch"
    description = "Apply a unified diff patch to a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to patch"},
            "patch": {"type": "string", "description": "Unified diff patch text"},
            "reverse": {"type": "boolean", "description": "Apply patch in reverse", "default": False},
        },
        "required": ["path", "patch"],
    }
    required_params = ["path", "patch"]
    requires_approval = True
    display_name = "Apply Patch"

    async def execute(self, path: str, patch: str, reverse: bool = False, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"File not found: {path}", display=f"❌ File not found: {path}")

        try:
            content = path_obj.read_text(encoding="utf-8")
            patches = Patch.parse(patch)

            if not patches:
                return ToolResult.err("No valid patches found", display="❌ No valid patches in input")

            # Apply all patches
            new_content = content
            for p in patches:
                if reverse:
                    # Swap old/new for reverse
                    p.old_path, p.new_path = p.new_path, p.old_path
                    for hunk in p.hunks:
                        hunk.old_start, hunk.new_start = hunk.new_start, hunk.old_start
                        hunk.old_lines, hunk.new_lines = hunk.new_lines, hunk.old_lines
                        hunk.lines = [("+" if op == "-" else "-" if op == "+" else " ", line) for op, line in hunk.lines]

                new_content, success = p.apply(new_content)
                if not success:
                    return ToolResult.err(
                        f"Failed to apply patch to {path}",
                        display=f"❌ Patch failed to apply to {path}",
                    )

            path_obj.write_text(new_content, encoding="utf-8")
            return ToolResult.ok(
                output="Patch applied successfully",
                display=f"✅ Applied patch to {path}",
            )
        except Exception as e:
            return ToolResult.err(f"Error applying patch: {e}", display=f"❌ apply_patch: {e}")


class CreatePatchTool(Tool):
    """Create a unified diff between two strings."""

    name = "create_patch"
    description = "Create a unified diff between old and new content."
    parameters = {
        "type": "object",
        "properties": {
            "old_content": {"type": "string", "description": "Original content"},
            "new_content": {"type": "string", "description": "New content"},
            "old_path": {"type": "string", "description": "Original file path", "default": "a/file"},
            "new_path": {"type": "string", "description": "New file path", "default": "b/file"},
            "context_lines": {"type": "integer", "description": "Context lines in diff", "default": 3},
        },
        "required": ["old_content", "new_content"],
    }
    required_params = ["old_content", "new_content"]
    display_name = "Create Patch"

    async def execute(
        self,
        old_content: str,
        new_content: str,
        old_path: str = "a/file",
        new_path: str = "b/file",
        context_lines: int = 3,
        **kwargs
    ) -> ToolResult:
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path,
            tofile=new_path,
            n=context_lines,
            lineterm="",
        )

        patch = "\n".join(diff)
        if not patch.endswith("\n"):
            patch += "\n"

        return ToolResult.ok(
            output={"patch": patch},
            display=f"📝 Generated patch ({len(patch)} chars)",
        )


class FuzzyEditTool(Tool):
    """Apply a fuzzy edit (approximate string replacement)."""

    name = "fuzzy_edit"
    description = "Apply an edit using fuzzy matching when exact match fails."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to edit"},
            "old_text": {"type": "string", "description": "Approximate text to find"},
            "new_text": {"type": "string", "description": "Replacement text"},
            "threshold": {"type": "number", "description": "Similarity threshold (0-1)", "default": 0.8},
        },
        "required": ["path", "old_text", "new_text"],
    }
    required_params = ["path", "old_text", "new_text"]
    requires_approval = True
    display_name = "Fuzzy Edit"

    async def execute(self, path: str, old_text: str, new_text: str, threshold: float = 0.8, **kwargs) -> ToolResult:
        if not self.context:
            return ToolResult.err("No context available")

        full_path = self.context.resolve_path(path)
        path_obj = Path(full_path)

        if not path_obj.exists():
            return ToolResult.err(f"File not found: {path}", display=f"❌ File not found: {path}")

        try:
            content = path_obj.read_text(encoding="utf-8")

            # Try exact match first
            if old_text in content:
                new_content = content.replace(old_text, new_text, 1)
                path_obj.write_text(new_content, encoding="utf-8")
                return ToolResult.ok(
                    output="Exact match replaced",
                    display=f"✅ Fuzzy edit (exact) applied to {path}",
                )

            # Fuzzy match using difflib
            old_lines = old_text.splitlines()
            content_lines = content.splitlines()

            best_match = None
            best_ratio = 0

            for i in range(len(content_lines) - len(old_lines) + 1):
                window = "\n".join(content_lines[i:i + len(old_lines)])
                ratio = difflib.SequenceMatcher(None, old_text, window).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = i

            if best_match is not None and best_ratio >= threshold:
                # Replace the matched window
                new_content_lines = content_lines[:]
                new_content_lines[best_match:best_match + len(old_lines)] = new_text.splitlines()
                new_content = "\n".join(new_content_lines)
                if content.endswith("\n"):
                    new_content += "\n"

                path_obj.write_text(new_content, encoding="utf-8")
                return ToolResult.ok(
                    output=f"Fuzzy match at line {best_match + 1} (ratio: {best_ratio:.2f})",
                    display=f"✅ Fuzzy edit applied to {path} (match: {best_ratio:.0%})",
                )

            return ToolResult.err(
                f"No match found (best: {best_ratio:.0%})",
                display=f"❌ Fuzzy edit failed: no match for '{old_text[:50]}...'",
            )
        except Exception as e:
            return ToolResult.err(f"Error in fuzzy edit: {e}", display=f"❌ fuzzy_edit: {e}")


# Register patch tools
def register_patch_tools():
    register_tool(ApplyPatchTool(), "patch")
    register_tool(CreatePatchTool(), "patch")
    register_tool(FuzzyEditTool(), "patch")
