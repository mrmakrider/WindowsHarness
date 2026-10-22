"""
WindowsHarness - AI Coding Agent for Windows.

A native Windows port of AndroidHarness, built with Python/PyQt6.
"""

__version__ = "0.1.0"
__author__ = "WindowsHarness Team"
__description__ = "AI Coding Agent for Windows"

# Core exports
from core.types import (
    ChatMessage,
    Role,
    ToolCallData,
    ToolCallStatus,
    ToolResult,
    Diff,
    AgentEvent,
    AgentEventType,
)

from core.agent_engine import AgentEngine, RunStatus
from core.context import ContextHygiene, HistoryCompactor, TokenCounter

from config.settings import (
    AppSettings,
    get_settings,
    save_settings,
    PermissionMode,
    ThemeMode,
    ProviderConfig,
)

from tools.registry import (
    Tool,
    ToolRegistry,
    ToolContext,
    get_tool_registry,
    register_tool,
    create_function_tool,
)

from workspace.fs import WorkspaceFs, create_workspace_fs

from llm.base import LlmProvider, ProviderRegistry, RequestOptions, ModelInfo
