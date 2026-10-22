"""
Tool Registry for WindowsHarness.

Manages tool registration, schema generation, and execution.
"""

from __future__ import annotations

import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from core.types import ToolResult, ToolCallData, ToolCallStatus
from pydantic import BaseModel, Field


@dataclass
class ToolParameter:
    """Tool parameter definition."""

    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[list[Any]] = None


@dataclass
class ToolSchema:
    """Tool schema for LLM function calling."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    required: list[str] = field(default_factory=list)

    def to_openai_function(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters or {"type": "object", "properties": {}},
        }

    def to_gemini_tool(self) -> dict[str, Any]:
        """Convert to Gemini function declaration format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters or {"type": "object", "properties": {}},
        }


class ToolContext:
    """Context provided to tools during execution."""

    def __init__(
        self,
        workspace_root: str,
        session_id: str,
        approval_callback: Optional[Callable[[str, dict[str, Any]], Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.workspace_root = workspace_root
        self.session_id = session_id
        self.approval_callback = approval_callback
        self.metadata = metadata or {}

    def resolve_path(self, path: str) -> str:
        """Resolve a path relative to workspace root."""
        from pathlib import Path
        p = Path(path)
        if p.is_absolute():
            return str(p)
        return str(Path(self.workspace_root) / path)


class Tool(ABC):
    """Base class for all tools."""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}  # JSON Schema
    required_params: list[str] = []
    requires_approval: bool = False
    display_name: Optional[str] = None

    def __init__(self, context: Optional[ToolContext] = None):
        self.context = context

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        pass

    def get_schema(self) -> ToolSchema:
        """Get the tool schema for LLM function calling."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            required=self.required_params,
        )

    async def request_approval(self, arguments: dict[str, Any]) -> bool:
        """Request user approval for tool execution."""
        if self.approval_callback:
            return await self.approval_callback(self.name, arguments)
        return True  # Default to approved if no callback


class FunctionTool(Tool):
    """Tool created from a Python function."""

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[ToolContext] = None,
        requires_approval: bool = False,
    ):
        super().__init__(context)
        self._func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self.requires_approval = requires_approval
        self._build_schema()

    def _build_schema(self) -> None:
        """Build JSON schema from function signature."""
        sig = inspect.signature(self._func)
        type_hints = get_type_hints(self._func)

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "context"):
                continue

            param_type = type_hints.get(param_name, Any)
            json_type = self._python_type_to_json(param_type)

            param_schema = {"type": json_type}
            if param.default != inspect.Parameter.empty:
                param_schema["default"] = param.default
            else:
                required.append(param_name)

            # Add description from docstring if available
            if self._func.__doc__:
                # Simple extraction - could be enhanced
                param_schema["description"] = f"Parameter {param_name}"

            properties[param_name] = param_schema

        self.parameters = {"type": "object", "properties": properties}
        self.required_params = required

    def _python_type_to_json(self, py_type: Any) -> str:
        """Convert Python type to JSON schema type."""
        if py_type is str:
            return "string"
        elif py_type is int:
            return "integer"
        elif py_type is float:
            return "number"
        elif py_type is bool:
            return "boolean"
        elif py_type is list or py_type is list[Any]:
            return "array"
        elif py_type is dict or py_type is dict[str, Any]:
            return "object"
        return "string"

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Inject context if function accepts it
            sig = inspect.signature(self._func)
            if "context" in sig.parameters:
                kwargs["context"] = self.context

            result = self._func(**kwargs)
            if inspect.iscoroutine(result):
                result = await result

            if isinstance(result, ToolResult):
                return result
            return ToolResult.ok(output=result, display=str(result))
        except Exception as e:
            return ToolResult.err(error=str(e), display=f"Error: {e}")


class ToolRegistry:
    """Registry for managing tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, tool: Tool, category: str = "general") -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        if category not in self._categories:
            self._categories[category] = []
        if tool.name not in self._categories[category]:
            self._categories[category].append(tool.name)

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            for cat_tools in self._categories.values():
                if name in cat_tools:
                    cat_tools.remove(name)
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> list[Tool]:
        """List all tools, optionally filtered by category."""
        if category:
            return [self._tools[name] for name in self._categories.get(category, []) if name in self._tools]
        return list(self._tools.values())

    def get_categories(self) -> list[str]:
        """Get all categories."""
        return list(self._categories.keys())

    def get_schemas(self, category: Optional[str] = None) -> list[ToolSchema]:
        """Get schemas for all tools (for LLM function calling)."""
        tools = self.list_tools(category)
        return [t.get_schema() for t in tools]

    def get_openai_functions(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        """Get OpenAI function calling format."""
        return [s.to_openai_function() for s in self.get_schemas(category)]

    def get_anthropic_tools(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        """Get Anthropic tool format."""
        return [s.to_anthropic_tool() for s in self.get_schemas(category)]

    def get_gemini_tools(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        """Get Gemini function declaration format."""
        return [s.to_gemini_tool() for s in self.get_schemas(category)]

    async def execute(
        self,
        tool_call: ToolCallData,
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """Execute a tool call."""
        tool = self.get(tool_call.name)
        if not tool:
            return ToolResult.err(
                error=f"Tool '{tool_call.name}' not found",
                display=f"❌ Tool '{tool_call.name}' not found",
            )

        # Set context
        tool.context = context

        # Check approval
        if tool.requires_approval:
            approved = await tool.request_approval(tool_call.arguments)
            if not approved:
                return ToolResult.err(
                    error="User denied approval",
                    display=f"❌ {tool.display_name or tool.name} denied by user",
                )

        # Execute
        tool_call.status = ToolCallStatus.RUNNING
        try:
            result = await tool.execute(**tool_call.arguments)
            tool_call.status = ToolCallStatus.COMPLETED if result.success else ToolCallStatus.FAILED
            tool_call.result = result.output
            tool_call.error = result.error
            return result
        except Exception as e:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error = str(e)
            return ToolResult.err(error=str(e), display=f"❌ {tool.display_name or tool.name} failed: {e}")


# Global registry
_tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _tool_registry


def register_tool(tool: Tool, category: str = "general") -> None:
    _tool_registry.register(tool, category)


def create_function_tool(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: str = "general",
    requires_approval: bool = False,
) -> FunctionTool:
    """Create and register a function tool."""
    tool = FunctionTool(func, name, description, requires_approval=requires_approval)
    register_tool(tool, category)
    return tool
