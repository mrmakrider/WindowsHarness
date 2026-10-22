"""
LLM Provider Abstraction for WindowsHarness.

Defines the base interface and stream event types for all LLM providers.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional, Union

from core.types import ToolCallData, ToolCallStatus


class StreamEventType(str, Enum):
    """Types of streaming events from LLM providers."""

    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    PROVIDER_CHANGED = "provider_changed"
    RETRYING = "retrying"
    ERROR = "error"
    DONE = "done"
    USAGE = "usage"


@dataclass
class StreamEvent:
    """Base stream event."""

    type: StreamEventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextDeltaEvent(StreamEvent):
    text: str = ""

    def __post_init__(self):
        self.type = StreamEventType.TEXT_DELTA
        self.data = {"text": self.text}


@dataclass
class ThinkingDeltaEvent(StreamEvent):
    thinking: str = ""

    def __post_init__(self):
        self.type = StreamEventType.THINKING_DELTA
        self.data = {"thinking": self.thinking}


@dataclass
class ToolCallStartEvent(StreamEvent):
    tool_call: ToolCallData = field(default_factory=ToolCallData)

    def __post_init__(self):
        self.type = StreamEventType.TOOL_CALL_START
        self.data = {"tool_call": self.tool_call}


@dataclass
class ToolCallDeltaEvent(StreamEvent):
    tool_call_id: str = ""
    arguments_delta: str = ""

    def __post_init__(self):
        self.type = StreamEventType.TOOL_CALL_DELTA
        self.data = {"tool_call_id": self.tool_call_id, "arguments_delta": self.arguments_delta}


@dataclass
class ToolCallCompleteEvent(StreamEvent):
    tool_call: ToolCallData = field(default_factory=ToolCallData)

    def __post_init__(self):
        self.type = StreamEventType.TOOL_CALL_COMPLETE
        self.data = {"tool_call": self.tool_call}


@dataclass
class ProviderChangedEvent(StreamEvent):
    provider_name: str = ""
    model: str = ""
    reason: str = ""

    def __post_init__(self):
        self.type = StreamEventType.PROVIDER_CHANGED
        self.data = {"provider_name": self.provider_name, "model": self.model, "reason": self.reason}


@dataclass
class RetryingEvent(StreamEvent):
    attempt: int = 0
    delay_ms: int = 0
    reason: str = ""

    def __post_init__(self):
        self.type = StreamEventType.RETRYING
        self.data = {"attempt": self.attempt, "delay_ms": self.delay_ms, "reason": self.reason}


@dataclass
class ErrorEvent(StreamEvent):
    message: str = ""
    recoverable: bool = True

    def __post_init__(self):
        self.type = StreamEventType.ERROR
        self.data = {"message": self.message, "recoverable": self.recoverable}


@dataclass
class UsageEvent(StreamEvent):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""

    def __post_init__(self):
        self.type = StreamEventType.USAGE
        self.data = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
        }


@dataclass
class DoneEvent(StreamEvent):
    finish_reason: str = "stop"

    def __post_init__(self):
        self.type = StreamEventType.DONE
        self.data = {"finish_reason": self.finish_reason}


# Union type for all stream events
StreamEventUnion = Union[
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallStartEvent,
    ToolCallDeltaEvent,
    ToolCallCompleteEvent,
    ProviderChangedEvent,
    RetryingEvent,
    ErrorEvent,
    UsageEvent,
    DoneEvent,
]


@dataclass
class RequestOptions:
    """Options for LLM requests."""

    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    top_k: Optional[int] = None
    stop_sequences: list[str] = field(default_factory=list)
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    response_format: Optional[dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Information about a model."""

    id: str
    name: str
    provider: str
    context_window: int = 4096
    max_output_tokens: int = 2048
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = True
    supports_thinking: bool = False
    pricing: Optional[dict[str, float]] = None  # input/output per 1M tokens
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Provider configuration."""

    name: str
    type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    default_model: Optional[str] = None
    models: list[str] = field(default_factory=list)
    enabled: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120
    max_retries: int = 3


class LlmProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._available_models: Optional[list[ModelInfo]] = None

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Provider type identifier."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream chat completion."""
        pass

    @abstractmethod
    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> dict[str, Any]:
        """Non-streaming chat completion."""
        pass

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate API connection and credentials."""
        pass

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info by ID."""
        if self._available_models is None:
            return None
        for m in self._available_models:
            if m.id == model_id:
                return m
        return None

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)

    def prepare_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prepare messages for provider API (override if needed)."""
        return messages

    def prepare_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prepare tools for provider API (override if needed)."""
        return tools


class ProviderRegistry:
    """Registry of LLM providers."""

    def __init__(self):
        self._providers: dict[str, type[LlmProvider]] = {}

    def register(self, provider_type: str, provider_class: type[LlmProvider]) -> None:
        self._providers[provider_type] = provider_class

    def get(self, provider_type: str) -> Optional[type[LlmProvider]]:
        return self._providers.get(provider_type)

    def create(self, config: ProviderConfig) -> Optional[LlmProvider]:
        provider_class = self._providers.get(config.type)
        if provider_class:
            return provider_class(config)
        return None

    def list_types(self) -> list[str]:
        return list(self._providers.keys())


# Global registry
_provider_registry = ProviderRegistry()


def register_provider(provider_type: str, provider_class: type[LlmProvider]) -> None:
    _provider_registry.register(provider_type, provider_class)


def get_provider_class(provider_type: str) -> Optional[type[LlmProvider]]:
    return _provider_registry.get(provider_type)


def create_provider(config: ProviderConfig) -> Optional[LlmProvider]:
    return _provider_registry.create(config)


def list_provider_types() -> list[str]:
    return _provider_registry.list_types()
