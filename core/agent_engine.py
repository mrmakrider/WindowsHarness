"""
Agent Engine for WindowsHarness.

Main agent execution loop that coordinates LLM, tools, and context management.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

from core.types import (
    AgentEvent,
    AgentEventType,
    ChatMessage,
    Role,
    ToolCallData,
    ToolCallStatus,
    ToolResult,
    TextDeltaEvent,
    ToolCallStartEvent,
    ToolCallCompleteEvent,
    ApprovalRequestedEvent,
    ProviderChangedEvent,
    TokenUsageEvent,
    ErrorEvent,
    DoneEvent,
)
from core.context import ContextHygiene, HistoryCompactor, TokenCounter, compact_context
from llm.base import LlmProvider, RequestOptions, StreamEventUnion, StreamEventType
from tools.registry import ToolRegistry, ToolContext, get_tool_registry
from workspace.fs import WorkspaceFs, create_workspace_fs
from config.settings import get_settings, AgentSettings, PermissionMode


class RunStatus(str, Enum):
    """Agent run status."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentRun:
    """Represents a single agent run."""

    id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    session_id: str = ""
    status: RunStatus = RunStatus.PENDING
    user_message: str = ""
    messages: list[ChatMessage] = field(default_factory=list)
    current_turn: int = 0
    max_turns: int = 50
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalManager:
    """Manages approval requests for tool execution."""

    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}

    def request_approval(
        self,
        approval_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        message: str,
        options: list[str] = None,
    ) -> asyncio.Future:
        """Request approval and return a future that resolves with the decision."""
        future = asyncio.get_event_loop().create_future()
        self._pending[approval_id] = future
        return future

    def resolve_approval(self, approval_id: str, approved: bool, always: bool = False) -> bool:
        """Resolve a pending approval."""
        future = self._pending.pop(approval_id, None)
        if future and not future.done():
            future.set_result({"approved": approved, "always": always})
            return True
        return False

    def get_pending(self) -> dict[str, asyncio.Future]:
        return self._pending.copy()


class AgentEngine:
    """Main agent execution engine."""

    def __init__(
        self,
        provider: LlmProvider,
        tool_registry: Optional[ToolRegistry] = None,
        workspace_fs: Optional[WorkspaceFs] = None,
        settings: Optional[AgentSettings] = None,
        event_callback: Optional[Callable[[AgentEvent], None]] = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry or get_tool_registry()
        self.workspace_fs = workspace_fs
        self.settings = settings or get_settings().agent
        self.event_callback = event_callback
        self.approval_manager = ApprovalManager()
        self.context_hygiene = ContextHygiene(
            max_tokens=self.settings.max_context_tokens,
            auto_compact_threshold=self.settings.auto_compact_threshold,
        )
        self.history_compactor = HistoryCompactor(llm_provider=provider)
        self._current_run: Optional[AgentRun] = None
        self._cancelled = False

    def _emit(self, event: AgentEvent) -> None:
        """Emit an event to callback."""
        if self.event_callback:
            self.event_callback(event)

    async def run(
        self,
        user_message: str,
        session_id: str = "",
        messages: Optional[list[ChatMessage]] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run the agent with a user message."""
        run = AgentRun(
            session_id=session_id or f"session_{uuid.uuid4().hex[:8]}",
            user_message=user_message,
            messages=messages or [],
            max_turns=self.settings.max_turns,
        )
        self._current_run = run
        self._cancelled = False

        # Add user message
        user_msg = ChatMessage(role=Role.USER, content=user_message)
        run.messages.append(user_msg)

        # Emit run started
        self._emit(AgentEvent(type=AgentEventType.RUN_STARTED, session_id=run.session_id, data={"run_id": run.id}))

        try:
            run.status = RunStatus.RUNNING

            for turn in range(run.max_turns):
                if self._cancelled:
                    self._emit(AgentEvent(type=AgentEventType.RUN_CANCELLED, session_id=run.session_id))
                    break

                run.current_turn = turn + 1

                # Check context budget
                if self.context_hygiene.should_compact(run.messages):
                    self._emit(AgentEvent(
                        type=AgentEventType.CONTEXT_COMPACTED,
                        session_id=run.session_id,
                        data={"turn": turn, "action": "compacting"},
                    ))
                    run.messages = await self.history_compactor.compact(
                        run.messages,
                        keep_recent=20,
                        system_prompt=system_prompt,
                    )

                # Get LLM response
                async for event in self._run_turn(run, system_prompt):
                    yield event

                    # Check for completion
                    if event.type == AgentEventType.DONE:
                        run.status = RunStatus.COMPLETED
                        run.completed_at = datetime.now()
                        self._emit(AgentEvent(type=AgentEventType.RUN_COMPLETED, session_id=run.session_id))
                        return

                    # Check for error
                    if event.type == AgentEventType.ERROR:
                        run.status = RunStatus.FAILED
                        run.error = event.data.get("message", "Unknown error")
                        run.completed_at = datetime.now()
                        self._emit(AgentEvent(type=AgentEventType.RUN_FAILED, session_id=run.session_id, data={"error": run.error}))
                        return

            # Max turns reached
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now()
            self._emit(AgentEvent(type=AgentEventType.RUN_COMPLETED, session_id=run.session_id, data={"max_turns_reached": True}))

        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now()
            self._emit(ErrorEvent(message=str(e), session_id=run.session_id))
            yield ErrorEvent(message=str(e), session_id=run.session_id)

    async def _run_turn(
        self,
        run: AgentRun,
        system_prompt: Optional[str],
    ) -> AsyncIterator[AgentEvent]:
        """Execute a single turn of the agent loop."""
        # Prepare messages for LLM
        llm_messages = self._prepare_messages(run.messages, system_prompt)
        tools = self.tool_registry.get_openai_functions()

        # Stream from LLM
        options = RequestOptions(
            model=self.provider.default_model,
            temperature=0.7,
            max_tokens=4096,
        )

        accumulated_text = ""
        tool_calls_buffer: dict[str, ToolCallData] = {}

        async for event in self.provider.stream_chat(llm_messages, tools, options):
            if self._cancelled:
                break

            # Convert provider events to agent events
            if isinstance(event, TextDeltaEvent):
                accumulated_text += event.text
                yield TextDeltaEvent(
                    type=AgentEventType.TEXT_DELTA,
                    session_id=run.session_id,
                    text=event.text,
                    full_text=accumulated_text,
                )

            elif isinstance(event, ToolCallStartEvent):
                tool_calls_buffer[event.tool_call.id] = event.tool_call
                yield ToolCallStartEvent(
                    type=AgentEventType.TOOL_CALL_START,
                    session_id=run.session_id,
                    tool_call=event.tool_call,
                )

            elif isinstance(event, ToolCallDeltaEvent):
                if event.tool_call_id in tool_calls_buffer:
                    tc = tool_calls_buffer[event.tool_call_id]
                    # Update arguments (simple concatenation for streaming)
                    yield ToolCallDeltaEvent(
                        type=AgentEventType.TOOL_CALL_DELTA,
                        session_id=run.session_id,
                        tool_call_id=event.tool_call_id,
                        arguments_delta=event.arguments_delta,
                    )

            elif isinstance(event, ToolCallCompleteEvent):
                if event.tool_call.id in tool_calls_buffer:
                    tool_calls_buffer[event.tool_call.id] = event.tool_call
                    yield ToolCallCompleteEvent(
                        type=AgentEventType.TOOL_CALL_COMPLETE,
                        session_id=run.session_id,
                        tool_call=event.tool_call,
                    )

            elif isinstance(event, StreamEventUnion) and event.type == StreamEventType.DONE:
                # Process tool calls if any
                if tool_calls_buffer:
                    # Add assistant message with tool calls
                    assistant_msg = ChatMessage(
                        role=Role.ASSISTANT,
                        content=accumulated_text,
                        tool_calls=list(tool_calls_buffer.values()),
                    )
                    run.messages.append(assistant_msg)

                    # Execute each tool call
                    for tc in tool_calls_buffer.values():
                        yield await self._execute_tool_call(tc, run)

                    # Continue to next turn
                    return

                # No tool calls - just text response
                assistant_msg = ChatMessage(
                    role=Role.ASSISTANT,
                    content=accumulated_text,
                )
                run.messages.append(assistant_msg)
                yield DoneEvent(type=AgentEventType.DONE, session_id=run.session_id, finish_reason="stop")
                return

            elif isinstance(event, StreamEventUnion) and event.type == StreamEventType.ERROR:
                yield ErrorEvent(
                    type=AgentEventType.ERROR,
                    session_id=run.session_id,
                    message=event.data.get("message", "LLM error"),
                )
                return

            elif isinstance(event, StreamEventUnion) and event.type == StreamEventType.USAGE:
                yield TokenUsageEvent(
                    type=AgentEventType.TOKEN_USAGE,
                    session_id=run.session_id,
                    input_tokens=event.data.get("input_tokens", 0),
                    output_tokens=event.data.get("output_tokens", 0),
                    total_tokens=event.data.get("total_tokens", 0),
                    model=event.data.get("model", ""),
                )

    async def _execute_tool_call(
        self,
        tool_call: ToolCallData,
        run: AgentRun,
    ) -> AgentEvent:
        """Execute a single tool call with approval handling."""
        tool = self.tool_registry.get(tool_call.name)
        requires_approval = tool.requires_approval if tool else False

        # Check permission mode
        if self.settings.permission_mode == PermissionMode.CONFIRM_ALL:
            requires_approval = True
        elif self.settings.permission_mode == PermissionMode.ALLOW_LIST:
            requires_approval = tool_call.name not in self.settings.allowed_tools

        if requires_approval:
            run.status = RunStatus.WAITING_APPROVAL
            approval_id = f"approval_{uuid.uuid4().hex[:8]}"
            tool_call.approval_id = approval_id
            tool_call.status = ToolCallStatus.NEEDS_APPROVAL

            # Emit approval request
            approval_event = ApprovalRequestedEvent(
                type=AgentEventType.APPROVAL_REQUESTED,
                session_id=run.session_id,
                approval_id=approval_id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                message=f"Execute {tool_call.name}?",
                options=["Approve", "Approve Always", "Deny"],
            )
            self._emit(approval_event)
            yield approval_event

            # Wait for approval
            future = self.approval_manager.request_approval(
                approval_id, tool_call.name, tool_call.arguments, approval_event.message
            )
            decision = await future

            if not decision.get("approved", False):
                tool_call.status = ToolCallStatus.CANCELLED
                tool_result = ToolResult.err("User denied approval")
                tool_msg = ChatMessage(
                    role=Role.TOOL,
                    content="User denied approval",
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                )
                run.messages.append(tool_msg)
                yield ToolCallCompleteEvent(
                    type=AgentEventType.TOOL_CALL_COMPLETE,
                    session_id=run.session_id,
                    tool_call=tool_call,
                )
                run.status = RunStatus.RUNNING
                return

            if decision.get("always", False):
                # Add to allowed tools
                if tool_call.name not in self.settings.allowed_tools:
                    self.settings.allowed_tools.append(tool_call.name)

        # Execute tool
        tool_call.status = ToolCallStatus.RUNNING
        tool_context = ToolContext(
            workspace_root=self.workspace_fs.root if self.workspace_fs else ".",
            session_id=run.session_id,
        )

        result = await self.tool_registry.execute(tool_call, context=tool_context)
        tool_call.status = ToolCallStatus.COMPLETED if result.success else ToolCallStatus.FAILED
        tool_call.result = result.output
        tool_call.error = result.error
        tool_call.completed_at = datetime.now()

        # Add tool result message
        tool_msg = ChatMessage(
            role=Role.TOOL,
            content=result.display or str(result.output) or result.error or "Tool completed",
            tool_call_id=tool_call.id,
            name=tool_call.name,
        )
        run.messages.append(tool_msg)

        run.status = RunStatus.RUNNING

        yield ToolCallCompleteEvent(
            type=AgentEventType.TOOL_CALL_COMPLETE,
            session_id=run.session_id,
            tool_call=tool_call,
        )

        # Emit approval decided event
        self._emit(AgentEvent(
            type=AgentEventType.APPROVAL_DECIDED,
            session_id=run.session_id,
            data={"approval_id": tool_call.approval_id, "approved": True},
        ))

    def _prepare_messages(
        self,
        messages: list[ChatMessage],
        system_prompt: Optional[str],
    ) -> list[dict[str, Any]]:
        """Prepare messages for LLM API."""
        llm_messages = []

        if system_prompt:
            llm_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == Role.SYSTEM:
                llm_messages.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                llm_messages.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                if msg.tool_calls:
                    llm_messages.append({
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })
                else:
                    llm_messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == Role.TOOL:
                llm_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                    "name": msg.name,
                })

        return llm_messages

    def cancel(self) -> None:
        """Cancel the current run."""
        self._cancelled = True

    @property
    def current_run(self) -> Optional[AgentRun]:
        return self._current_run


# Import json for serialization
import json
