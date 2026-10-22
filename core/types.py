"""
Core type definitions for WindowsHarness.

Mirrors AndroidHarness core types: ChatMessage, ToolCallData, Diff, etc.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Message roles in conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallStatus(str, Enum):
    """Status of a tool call."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_APPROVAL = "needs_approval"


class ApprovalDecision(str, Enum):
    """User decision on approval prompt."""

    APPROVE = "approve"
    APPROVE_ALWAYS = "approve_always"
    DENY = "deny"


@dataclass
class ToolCallData:
    """Represents a tool call from the LLM."""

    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    approval_id: Optional[str] = None  # For approval flow
    metadata: dict[str, Any] = field(default_factory=dict)

    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None


@dataclass
class ChatMessage:
    """A single message in the conversation."""

    role: Role
    content: str = ""
    tool_calls: list[ToolCallData] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # For tool result messages
    name: Optional[str] = None  # For function/tool messages
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> ChatMessage:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: list[ToolCallData] = None) -> ChatMessage:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, tool_call_id: str, name: str, content: str) -> ChatMessage:
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id, name=name)


class DiffOp(str, Enum):
    """Diff operation types."""

    ADD = "add"
    REMOVE = "remove"
    UNCHANGED = "unchanged"


@dataclass
class DiffHunk:
    """A single hunk in a unified diff."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[tuple[DiffOp, str]] = field(default_factory=list)


@dataclass
class Diff:
    """Unified diff representation."""

    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)

    def to_unified(self, context_lines: int = 3) -> str:
        """Generate unified diff format."""
        lines = [
            f"--- {self.old_path}",
            f"+++ {self.new_path}",
        ]
        for hunk in self.hunks:
            lines.append(
                f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@"
            )
            for op, line in hunk.lines:
                prefix = {"add": "+", "remove": "-", "unchanged": " "}[op.value]
                lines.append(f"{prefix}{line}")
        return "\n".join(lines) + "\n"


class AgentEventType(str, Enum):
    """Types of events emitted by the agent engine."""

    # Lifecycle
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"

    # Streaming
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TOOL_CALL_FAILED = "tool_call_failed"

    # Approvals
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"

    # Provider
    PROVIDER_CHANGED = "provider_changed"
    MODEL_CHANGED = "model_changed"

    # Context
    CONTEXT_COMPACTED = "context_compacted"
    TOKEN_USAGE = "token_usage"

    # Code drafts
    CODE_DRAFT = "code_draft"
    CODE_DRAFTS_CLEARED = "code_drafts_cleared"

    # Errors
    ERROR = "error"
    WARNING = "warning"

    # Custom
    CUSTOM = "custom"
    DONE = "done"


@dataclass
class AgentEvent:
    """Base agent event."""

    type: AgentEventType
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextDeltaEvent(AgentEvent):
    text: str = ""
    full_text: str = ""

    def __post_init__(self):
        self.type = AgentEventType.TEXT_DELTA
        self.data = {"text": self.text, "full_text": self.full_text}


@dataclass
class ThinkingDeltaEvent(AgentEvent):
    thinking: str = ""

    def __post_init__(self):
        self.type = AgentEventType.THINKING_DELTA
        self.data = {"thinking": self.thinking}


@dataclass
class ToolCallStartEvent(AgentEvent):
    tool_call: ToolCallData = field(default_factory=ToolCallData)

    def __post_init__(self):
        self.type = AgentEventType.TOOL_CALL_START
        self.data = {"tool_call": self.tool_call.__dict__}


@dataclass
class ToolCallCompleteEvent(AgentEvent):
    tool_call: ToolCallData = field(default_factory=ToolCallData)

    def __post_init__(self):
        self.type = AgentEventType.TOOL_CALL_COMPLETE
        self.data = {"tool_call": self.tool_call.__dict__}


@dataclass
class ToolCallDeltaEvent(AgentEvent):
    tool_call_id: str = ""
    arguments_delta: str = ""

    def __post_init__(self):
        self.type = AgentEventType.TOOL_CALL_DELTA
        self.data = {"tool_call_id": self.tool_call_id, "arguments_delta": self.arguments_delta}


@dataclass
class ToolCallFailedEvent(AgentEvent):
    tool_call_id: str = ""
    error: str = ""

    def __post_init__(self):
        self.type = AgentEventType.TOOL_CALL_FAILED
        self.data = {"tool_call_id": self.tool_call_id, "error": self.error}


@dataclass
class ApprovalRequestedEvent(AgentEvent):
    approval_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    options: list[str] = field(default_factory=list)  # Predefined options

    def __post_init__(self):
        self.type = AgentEventType.APPROVAL_REQUESTED
        self.data = {
            "approval_id": self.approval_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "message": self.message,
            "options": self.options,
        }


@dataclass
class ProviderChangedEvent(AgentEvent):
    provider_name: str = ""
    model: str = ""
    reason: str = ""

    def __post_init__(self):
        self.type = AgentEventType.PROVIDER_CHANGED
        self.data = {"provider_name": self.provider_name, "model": self.model, "reason": self.reason}


@dataclass
class TokenUsageEvent(AgentEvent):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""

    def __post_init__(self):
        self.type = AgentEventType.TOKEN_USAGE
        self.data = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
        }


@dataclass
class ErrorEvent(AgentEvent):
    message: str = ""
    recoverable: bool = True

    def __post_init__(self):
        self.type = AgentEventType.ERROR
        self.data = {"message": self.message, "recoverable": self.recoverable}


@dataclass
class DoneEvent(AgentEvent):
    finish_reason: str = "stop"

    def __post_init__(self):
        self.type = AgentEventType.DONE
        self.data = {"finish_reason": self.finish_reason}


# --- Tool Result Types ---


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    display: Optional[str] = None  # Human-readable summary for chat

    @classmethod
    def ok(cls, output: Any = None, display: str = None, **metadata) -> ToolResult:
        return cls(success=True, output=output, display=display, metadata=metadata)

    @classmethod
    def err(cls, error: str, display: str = None, **metadata) -> ToolResult:
        return cls(success=False, error=error, display=display, metadata=metadata)


# --- Pydantic Models for Serialization ---


class ToolCallDataModel(BaseModel):
    """Pydantic model for ToolCallData serialization."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    approval_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageModel(BaseModel):
    """Pydantic model for ChatMessage serialization."""

    role: Role
    content: str = ""
    tool_calls: list[ToolCallDataModel] = Field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiffHunkModel(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[tuple[str, str]]  # (op, line)


class DiffModel(BaseModel):
    old_path: str
    new_path: str
    hunks: list[DiffHunkModel] = Field(default_factory=list)


# --- Conversion Helpers ---


def tool_call_to_model(tc: ToolCallData) -> ToolCallDataModel:
    return ToolCallDataModel(
        id=tc.id,
        name=tc.name,
        arguments=tc.arguments,
        status=tc.status,
        result=tc.result,
        error=tc.error,
        started_at=tc.started_at,
        completed_at=tc.completed_at,
        approval_id=tc.approval_id,
        metadata=tc.metadata,
    )


def tool_call_from_model(m: ToolCallDataModel) -> ToolCallData:
    return ToolCallData(
        id=m.id,
        name=m.name,
        arguments=m.arguments,
        status=m.status,
        result=m.result,
        error=m.error,
        started_at=m.started_at,
        completed_at=m.completed_at,
        approval_id=m.approval_id,
        metadata=m.metadata,
    )


def chat_message_to_model(msg: ChatMessage) -> ChatMessageModel:
    return ChatMessageModel(
        role=msg.role,
        content=msg.content,
        tool_calls=[tool_call_to_model(tc) for tc in msg.tool_calls],
        tool_call_id=msg.tool_call_id,
        name=msg.name,
        timestamp=msg.timestamp,
        metadata=msg.metadata,
    )


def chat_message_from_model(m: ChatMessageModel) -> ChatMessage:
    return ChatMessage(
        role=m.role,
        content=m.content,
        tool_calls=[tool_call_from_model(tc) for tc in m.tool_calls],
        tool_call_id=m.tool_call_id,
        name=m.name,
        timestamp=m.timestamp,
        metadata=m.metadata,
    )
