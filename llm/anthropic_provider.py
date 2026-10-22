"""
Anthropic Provider Implementation for WindowsHarness.

Supports Anthropic Messages API with streaming.
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from llm.base import (
    DoneEvent,
    ErrorEvent,
    LlmProvider,
    ModelInfo,
    ProviderConfig,
    RequestOptions,
    StreamEventUnion,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallCompleteEvent,
    ToolCallDeltaEvent,
    ToolCallStartEvent,
    UsageEvent,
)

# Optional imports
try:
    from anthropic import AsyncAnthropic
    from anthropic.types import MessageDeltaEvent, MessageStartEvent, ContentBlockDeltaEvent, ContentBlockStartEvent, ContentBlockStopEvent
    HAS_ANTHROPIC = True
except ImportError:
    AsyncAnthropic = None
    HAS_ANTHROPIC = False


class AnthropicProvider(LlmProvider):
    """Anthropic Messages API provider."""

    @property
    def provider_type(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return self.config.default_model or "claude-3-5-sonnet-20241022"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package is required for AnthropicProvider. Install with: pip install anthropic")
        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream chat completion using Messages API."""
        system, anthropic_messages = self._convert_messages(messages)
        prepared_tools = self._convert_tools(tools) if tools else None

        try:
            stream = await self.client.messages.create(
                model=options.model,
                messages=anthropic_messages,
                system=system,
                tools=prepared_tools,
                tool_choice={"type": "auto"} if tools else None,
                temperature=options.temperature,
                max_tokens=options.max_tokens or 4096,
                top_p=options.top_p,
                stop_sequences=options.stop_sequences or None,
                stream=True,
            )

            accumulated_text = ""
            tool_calls_buffer: dict[int, dict] = {}
            current_block_index: Optional[int] = None

            async for event in stream:
                if isinstance(event, MessageStartEvent):
                    # Message started, usage info available
                    if event.message.usage:
                        yield UsageEvent(
                            input_tokens=event.message.usage.input_tokens,
                            output_tokens=0,  # Will update at end
                            total_tokens=event.message.usage.input_tokens,
                            model=options.model,
                        )

                elif isinstance(event, ContentBlockStartEvent):
                    if event.content_block.type == "tool_use":
                        current_block_index = event.index
                        tool_calls_buffer[event.index] = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "arguments": "",
                        }
                        yield ToolCallStartEvent(
                            tool_call=ToolCallData(
                                id=event.content_block.id,
                                name=event.content_block.name,
                                arguments={},
                                status=ToolCallStatus.RUNNING,
                            )
                        )

                elif isinstance(event, ContentBlockDeltaEvent):
                    if event.delta.type == "text_delta":
                        accumulated_text += event.delta.text
                        yield TextDeltaEvent(text=event.delta.text, full_text=accumulated_text)
                    elif event.delta.type == "input_json_delta":
                        if current_block_index is not None and current_block_index in tool_calls_buffer:
                            tool_calls_buffer[current_block_index]["arguments"] += event.delta.partial_json
                            yield ToolCallDeltaEvent(
                                tool_call_id=tool_calls_buffer[current_block_index]["id"],
                                arguments_delta=event.delta.partial_json,
                            )

                elif isinstance(event, ContentBlockStopEvent):
                    if current_block_index is not None and current_block_index in tool_calls_buffer:
                        buf = tool_calls_buffer[current_block_index]
                        try:
                            args = json.loads(buf["arguments"])
                        except json.JSONDecodeError:
                            args = {"_raw": buf["arguments"]}
                        yield ToolCallCompleteEvent(
                            tool_call=ToolCallData(
                                id=buf["id"],
                                name=buf["name"],
                                arguments=args,
                                status=ToolCallStatus.COMPLETED,
                            )
                        )
                        current_block_index = None

                elif isinstance(event, MessageDeltaEvent):
                    if event.delta.stop_reason:
                        yield DoneEvent(finish_reason=event.delta.stop_reason)
                    if event.usage:
                        yield UsageEvent(
                            input_tokens=0,  # Already sent at start
                            output_tokens=event.usage.output_tokens,
                            total_tokens=event.usage.output_tokens,
                            model=options.model,
                        )

        except Exception as e:
            yield ErrorEvent(message=str(e), recoverable=True)

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> dict[str, Any]:
        system, anthropic_messages = self._convert_messages(messages)
        prepared_tools = self._convert_tools(tools) if tools else None

        response = await self.client.messages.create(
            model=options.model,
            messages=anthropic_messages,
            system=system,
            tools=prepared_tools,
            tool_choice={"type": "auto"} if tools else None,
            temperature=options.temperature,
            max_tokens=options.max_tokens or 4096,
            top_p=options.top_p,
            stop_sequences=options.stop_sequences or None,
            stream=False,
        )

        tool_calls = []
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return {
            "content": text_content,
            "tool_calls": tool_calls,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
        }

    async def list_models(self) -> list[ModelInfo]:
        if self._available_models is not None:
            return self._available_models

        # Anthropic doesn't have a models list endpoint, use known models
        self._available_models = [
            ModelInfo(
                id="claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet",
                provider=self.provider_type,
                context_window=200000,
                max_output_tokens=8192,
                supports_tools=True,
                supports_vision=True,
                supports_thinking=True,
                pricing={"input": 3.00, "output": 15.00},
            ),
            ModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider=self.provider_type,
                context_window=200000,
                max_output_tokens=8192,
                supports_tools=True,
                supports_vision=True,
                pricing={"input": 0.80, "output": 4.00},
            ),
            ModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus",
                provider=self.provider_type,
                context_window=200000,
                max_output_tokens=4096,
                supports_tools=True,
                supports_vision=True,
                pricing={"input": 15.00, "output": 75.00},
            ),
            ModelInfo(
                id="claude-3-sonnet-20240229",
                name="Claude 3 Sonnet",
                provider=self.provider_type,
                context_window=200000,
                max_output_tokens=4096,
                supports_tools=True,
                supports_vision=True,
                pricing={"input": 3.00, "output": 15.00},
            ),
            ModelInfo(
                id="claude-3-haiku-20240307",
                name="Claude 3 Haiku",
                provider=self.provider_type,
                context_window=200000,
                max_output_tokens=4096,
                supports_tools=True,
                supports_vision=True,
                pricing={"input": 0.25, "output": 1.25},
            ),
        ]
        return self._available_models

    async def validate_connection(self) -> bool:
        try:
            # Try a minimal request
            await self.client.messages.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Convert standard messages to Anthropic format."""
        system = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system = content if isinstance(content, str) else str(content)
            elif role == "user":
                if isinstance(content, list):
                    # Multi-modal content
                    anthropic_content = []
                    for part in content:
                        if part.get("type") == "text":
                            anthropic_content.append({"type": "text", "text": part["text"]})
                        elif part.get("type") == "image_url":
                            anthropic_content.append({
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": part["image_url"]["url"],
                                },
                            })
                    anthropic_messages.append({"role": "user", "content": anthropic_content})
                else:
                    anthropic_messages.append({"role": "user", "content": str(content)})
            elif role == "assistant":
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        anthropic_messages.append({
                            "role": "assistant",
                            "content": [{
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": tc["arguments"],
                            }],
                        })
                elif content:
                    anthropic_messages.append({"role": "assistant", "content": str(content)})
            elif role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id"),
                        "content": str(content),
                    }],
                })

        return system, anthropic_messages

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert standard tools to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                anthropic_tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
        return anthropic_tools


from llm.base import register_provider
register_provider("anthropic", AnthropicProvider)
