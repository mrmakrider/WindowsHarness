"""
Basic tests for WindowsHarness core modules.
"""

import pytest
import tempfile
from pathlib import Path

from core.types import (
    ChatMessage, Role, ToolCallData, ToolCallStatus, ToolResult,
    Diff, DiffHunk, DiffOp
)
from core.context import TokenCounter, ContextHygiene
from tools.registry import ToolRegistry, ToolContext, Tool, FunctionTool
from workspace.fs import LocalWorkspaceFs, create_workspace_fs


class TestCoreTypes:
    """Test core data types."""

    def test_chat_message_creation(self):
        msg = ChatMessage.user("Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"

    def test_tool_call_data(self):
        tc = ToolCallData(name="read", arguments={"path": "test.py"})
        assert tc.name == "read"
        assert tc.arguments["path"] == "test.py"
        assert tc.status == ToolCallStatus.PENDING

    def test_tool_result(self):
        result = ToolResult.ok(output="content", display="File read")
        assert result.success
        assert result.output == "content"
        assert result.display == "File read"

        error_result = ToolResult.err(error="Not found")
        assert not error_result.success
        assert error_result.error == "Not found"


class TestTokenCounter:
    """Test token counting."""

    def test_estimate(self):
        assert TokenCounter.estimate("") == 0
        assert TokenCounter.estimate("hello") == 1  # 5 chars / 3.5 ≈ 1.4 → int(1.4) = 1
        assert TokenCounter.estimate("x" * 100) == 28  # 100 / 3.5 ≈ 28.5 → int(28.5) = 28

    def test_estimate_message(self):
        msg = ChatMessage.user("Hello world")
        tokens = TokenCounter.estimate_message(msg)
        assert tokens > 0

        msg_with_tools = ChatMessage.assistant(
            tool_calls=[ToolCallData(name="read", arguments={"path": "test.py"})]
        )
        tokens = TokenCounter.estimate_message(msg_with_tools)
        assert tokens > 0


class TestContextHygiene:
    """Test context hygiene."""

    def test_should_compact(self):
        hygiene = ContextHygiene(max_tokens=1000, auto_compact_threshold=0.8)
        messages = [ChatMessage.user("x" * 1000) for _ in range(10)]
        # Should be over threshold
        assert hygiene.should_compact(messages)

    def test_shrink_tool_results(self):
        hygiene = ContextHygiene(max_tokens=1000, max_tool_result_tokens=50)
        long_content = "x" * 500
        msg = ChatMessage(role=Role.TOOL, content=long_content, tool_call_id="1", name="read")
        result = hygiene.shrink_tool_results([msg])
        assert len(result[0].content) < len(long_content)
        assert "truncated" in result[0].metadata


class TestToolRegistry:
    """Test tool registry."""

    def test_register_and_execute(self):
        registry = ToolRegistry()

        def my_tool(path: str, context: ToolContext = None) -> ToolResult:
            return ToolResult.ok(output=f"Read {path}")

        tool = FunctionTool(my_tool, name="my_read", description="Read a file")
        registry.register(tool)

        assert registry.get("my_read") is not None
        schemas = registry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0].name == "my_read"

    def test_openai_functions_format(self):
        registry = ToolRegistry()

        def my_tool(path: str) -> ToolResult:
            return ToolResult.ok(output="done")

        tool = FunctionTool(my_tool, name="read_file", description="Read file")
        registry.register(tool)

        functions = registry.get_openai_functions()
        assert len(functions) == 1
        assert functions[0]["function"]["name"] == "read_file"
        assert "path" in functions[0]["function"]["parameters"]["properties"]


class TestWorkspaceFs:
    """Test filesystem abstraction."""

    def test_local_fs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = LocalWorkspaceFs(tmpdir)

            # Write and read
            fs.write_text("test.txt", "Hello World")
            content = fs.read_text("test.txt")
            assert content == "Hello World"

            # List
            files = fs.list(".", recursive=False)
            assert len(files) == 1
            assert files[0].name == "test.txt"

            # Glob
            matches = fs.glob("*.txt")
            assert "test.txt" in matches

            # Delete
            fs.delete("test.txt")
            assert not fs.exists("test.txt")

    def test_create_workspace_fs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = create_workspace_fs(tmpdir)
            assert isinstance(fs, LocalWorkspaceFs)

            fs_chat = create_workspace_fs(tmpdir, chat_id="test")
            from workspace.fs import ChatWorkspaceFs
            assert isinstance(fs_chat, ChatWorkspaceFs)

            fs_unbounded = create_workspace_fs(tmpdir, unbounded=True)
            from workspace.fs import UnboundedFileFs
            assert isinstance(fs_unbounded, UnboundedFileFs)


class TestDiff:
    """Test diff functionality."""

    def test_diff_creation(self):
        hunk = DiffHunk(
            old_start=1, old_lines=3,
            new_start=1, new_lines=3,
            lines=[
                (DiffOp.UNCHANGED, "line 1"),
                (DiffOp.REMOVE, "old line"),
                (DiffOp.ADD, "new line"),
                (DiffOp.UNCHANGED, "line 3"),
            ]
        )
        diff = Diff(old_path="a.txt", new_path="b.txt", hunks=[hunk])
        unified = diff.to_unified()
        assert "--- a.txt" in unified
        assert "+++ b.txt" in unified
        assert "-old line" in unified
        assert "+new line" in unified


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
