"""
OpenAI Provider Implementation for WindowsHarness.

Supports both Chat Completions API and Responses API.
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
    from openai import AsyncOpenAI
    from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageToolCall
    HAS_OPENAI = True
except ImportError:
    AsyncOpenAI = None
    ChatCompletionChunk = None
    ChatCompletionMessageToolCall = None
    HAS_OPENAI = False


class OpenAIProvider(LlmProvider):
    """OpenAI Chat Completions API provider."""

    @property
    def provider_type(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return self.config.default_model or "gpt-4o-mini"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ImportError("openai package is required for OpenAIProvider. Install with: pip install openai")
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.base_url,
            organization=config.organization,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream chat completion using Chat Completions API."""
        prepared_messages = self.prepare_messages(messages)
        prepared_tools = self.prepare_tools(tools) if tools else None

        try:
            stream = await self.client.chat.completions.create(
                model=options.model,
                messages=prepared_messages,
                tools=prepared_tools,
                tool_choice="auto" if tools else None,
                temperature=options.temperature,
                max_tokens=options.max_tokens,
                top_p=options.top_p,
                stop=options.stop_sequences or None,
                presence_penalty=options.presence_penalty,
                frequency_penalty=options.frequency_penalty,
                response_format=options.response_format,
                seed=options.seed,
                user=options.user,
                stream=True,
            )

            tool_calls_buffer: dict[int, ChatCompletionMessageToolCall] = {}
            accumulated_text = ""

            async for chunk in stream:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Text delta
                if delta.content:
                    accumulated_text += delta.content
                    yield TextDeltaEvent(text=delta.content, full_text=accumulated_text)

                # Tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        index = tc_delta.index
                        if index not in tool_calls_buffer:
                            # New tool call starting
                            tool_calls_buffer[index] = tc_delta
                            tc_data = ToolCallData(
                                id=tc_delta.id or f"call_{index}",
                                name=tc_delta.function.name or "",
                                arguments={},
                                status=ToolCallStatus.RUNNING,
                            )
                            yield ToolCallStartEvent(tool_call=tc_data)
                        else:
                            # Existing tool call - append arguments
                            existing = tool_calls_buffer[index]
                            if tc_delta.function.arguments:
                                existing.function.arguments += tc_delta.function.arguments
                            if tc_delta.function.name:
                                existing.function.name = tc_delta.function.name

                            # Emit delta
                            yield ToolCallDeltaEvent(
                                tool_call_id=tc_delta.id or f"call_{index}",
                                arguments_delta=tc_delta.function.arguments or "",
                            )

                # Finish reason
                if choice.finish_reason:
                    # Complete any pending tool calls
                    for index, tc in tool_calls_buffer.items():
                        if tc.function.arguments:
                            try:
                                args = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                args = {"_raw": tc.function.arguments}
                            yield ToolCallCompleteEvent(
                                tool_call=ToolCallData(
                                    id=tc.id or f"call_{index}",
                                    name=tc.function.name or "",
                                    arguments=args,
                                    status=ToolCallStatus.COMPLETED,
                                )
                            )

                    yield DoneEvent(finish_reason=choice.finish_reason)
                    break

            # Usage (from final chunk if available)
            if chunk.usage:
                yield UsageEvent(
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
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
        """Non-streaming chat completion."""
        prepared_messages = self.prepare_messages(messages)
        prepared_tools = self.prepare_tools(tools) if tools else None

        response = await self.client.chat.completions.create(
            model=options.model,
            messages=prepared_messages,
            tools=prepared_tools,
            tool_choice="auto" if tools else None,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            top_p=options.top_p,
            stop=options.stop_sequences or None,
            presence_penalty=options.presence_penalty,
            frequency_penalty=options.frequency_penalty,
            response_format=options.response_format,
            seed=options.seed,
            user=options.user,
            stream=False,
        )

        return {
            "content": response.choices[0].message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in (response.choices[0].message.tool_calls or [])
            ],
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        }

    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        if self._available_models is not None:
            return self._available_models

        try:
            models = await self.client.models.list()
            self._available_models = [
                ModelInfo(
                    id=m.id,
                    name=m.id,
                    provider=self.provider_type,
                    context_window=self._get_context_window(m.id),
                    max_output_tokens=self._get_max_output(m.id),
                    supports_tools=self._supports_tools(m.id),
                    supports_vision=self._supports_vision(m.id),
                    supports_streaming=True,
                    pricing=self._get_pricing(m.id),
                )
                for m in models.data
                if not m.id.startswith(("text-", "whisper-", "tts-", "dall-e", "embedding"))
            ]
        except Exception:
            # Fallback to known models
            self._available_models = self._get_fallback_models()

        return self._available_models

    async def validate_connection(self) -> bool:
        """Validate API connection."""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    # --- Model metadata helpers ---

    def _get_context_window(self, model_id: str) -> int:
        if "gpt-4o" in model_id or "gpt-4.1" in model_id:
            return 128000
        elif "gpt-4-turbo" in model_id or "gpt-4-0125" in model_id:
            return 128000
        elif "gpt-4-32k" in model_id:
            return 32768
        elif "gpt-4" in model_id:
            return 8192
        elif "gpt-3.5-turbo" in model_id:
            return 16384
        return 4096

    def _get_max_output(self, model_id: str) -> int:
        if "gpt-4o" in model_id or "gpt-4.1" in model_id:
            return 16384
        elif "gpt-4" in model_id:
            return 4096
        return 2048

    def _supports_tools(self, model_id: str) -> bool:
        return not any(x in model_id for x in ["instruct", "babbage", "davinci", "curie", "ada"])

    def _supports_vision(self, model_id: str) -> bool:
        return any(x in model_id for x in ["gpt-4o", "gpt-4.1", "gpt-4-turbo", "gpt-4-vision"])

    def _get_pricing(self, model_id: str) -> Optional[dict[str, float]]:
        # Prices per 1M tokens (approximate, update as needed)
        pricing_map = {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        }
        for key, val in pricing_map.items():
            if key in model_id:
                return val
        return None

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="gpt-4o", name="GPT-4o", provider=self.provider_type, context_window=128000, max_output_tokens=16384, supports_tools=True, supports_vision=True, pricing={"input": 2.50, "output": 10.00}),
            ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", provider=self.provider_type, context_window=128000, max_output_tokens=16384, supports_tools=True, supports_vision=True, pricing={"input": 0.15, "output": 0.60}),
            ModelInfo(id="gpt-4-turbo", name="GPT-4 Turbo", provider=self.provider_type, context_window=128000, max_output_tokens=4096, supports_tools=True, supports_vision=True, pricing={"input": 10.00, "output": 30.00}),
            ModelInfo(id="gpt-3.5-turbo", name="GPT-3.5 Turbo", provider=self.provider_type, context_window=16384, max_output_tokens=4096, supports_tools=True, pricing={"input": 0.50, "output": 1.50}),
        ]


class OpenAIResponsesProvider(LlmProvider):
    """OpenAI Responses API provider (newer API with built-in tools)."""

    @property
    def provider_type(self) -> str:
        return "openai_responses"

    @property
    def default_model(self) -> str:
        return self.config.default_model or "gpt-4o"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.base_url,
            organization=config.organization,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream using Responses API."""
        # Convert messages to Responses API format
        input_items = self._messages_to_input(messages)
        prepared_tools = self._tools_to_responses(tools) if tools else None

        try:
            stream = await self.client.responses.create(
                model=options.model,
                input=input_items,
                tools=prepared_tools,
                temperature=options.temperature,
                max_output_tokens=options.max_tokens,
                top_p=options.top_p,
                stream=True,
            )

            accumulated_text = ""
            tool_calls_buffer: dict[str, dict] = {}

            async for event in stream:
                if event.type == "response.output_text.delta":
                    accumulated_text += event.delta
                    yield TextDeltaEvent(text=event.delta, full_text=accumulated_text)

                elif event.type == "response.output_item.added" and event.item.type == "function_call":
                    # Tool call starting
                    item = event.item
                    tool_calls_buffer[item.call_id] = {
                        "id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments or "{}",
                    }
                    yield ToolCallStartEvent(
                        tool_call=ToolCallData(
                            id=item.call_id,
                            name=item.name,
                            arguments=json.loads(item.arguments or "{}"),
                            status=ToolCallStatus.RUNNING,
                        )
                    )

                elif event.type == "response.function_call_arguments.delta":
                    # Tool call arguments delta
                    call_id = event.call_id
                    if call_id in tool_calls_buffer:
                        tool_calls_buffer[call_id]["arguments"] += event.delta
                        yield ToolCallDeltaEvent(
                            tool_call_id=call_id,
                            arguments_delta=event.delta,
                        )

                elif event.type == "response.output_item.done" and event.item.type == "function_call":
                    # Tool call complete
                    call_id = event.item.call_id
                    if call_id in tool_calls_buffer:
                        buf = tool_calls_buffer[call_id]
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

                elif event.type == "response.completed":
                    if event.response.usage:
                        yield UsageEvent(
                            input_tokens=event.response.usage.input_tokens,
                            output_tokens=event.response.usage.output_tokens,
                            total_tokens=event.response.usage.total_tokens,
                            model=options.model,
                        )
                    yield DoneEvent(finish_reason=event.response.status)
                    break

        except Exception as e:
            yield ErrorEvent(message=str(e), recoverable=True)

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> dict[str, Any]:
        input_items = self._messages_to_input(messages)
        prepared_tools = self._tools_to_responses(tools) if tools else None

        response = await self.client.responses.create(
            model=options.model,
            input=input_items,
            tools=prepared_tools,
            temperature=options.temperature,
            max_output_tokens=options.max_tokens,
            top_p=options.top_p,
        )

        tool_calls = []
        text_content = ""
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        text_content += content.text
            elif item.type == "function_call":
                tool_calls.append({
                    "id": item.call_id,
                    "name": item.name,
                    "arguments": json.loads(item.arguments),
                })

        return {
            "content": text_content,
            "tool_calls": tool_calls,
            "usage": {
                "input_tokens": response.usage.input_tokens if response.usage else 0,
                "output_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        }

    async def list_models(self) -> list[ModelInfo]:
        return await OpenAIProvider(self.config).list_models()

    async def validate_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    def _messages_to_input(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert chat messages to Responses API input format."""
        input_items = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                input_items.append({"type": "input_text", "text": content})
            elif role == "user":
                if isinstance(content, list):
                    # Multi-modal content
                    for part in content:
                        if part.get("type") == "text":
                            input_items.append({"type": "input_text", "text": part["text"]})
                        elif part.get("type") == "image_url":
                            input_items.append({
                                "type": "input_image",
                                "image_url": part["image_url"]["url"],
                            })
                else:
                    input_items.append({"type": "input_text", "text": str(content)})
            elif role == "assistant":
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        input_items.append({
                            "type": "function_call",
                            "call_id": tc["id"],
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        })
                elif content:
                    input_items.append({"type": "output_text", "text": content})
            elif role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id"),
                    "output": content,
                })
        return input_items

    def _tools_to_responses(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to Responses API format."""
        responses_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                responses_tools.append({
                    "type": "function",
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                })
        return responses_tools


class OpenAICompatProvider(LlmProvider):
    """OpenAI-compatible provider (Ollama, LM Studio, LocalAI, etc.)."""

    @property
    def provider_type(self) -> str:
        return "openai_compat"

    @property
    def default_model(self) -> str:
        return self.config.default_model or "llama3"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        api_key = config.api_key or "not-needed"  # Most local servers don't require auth
        base_url = config.base_url or "http://localhost:11434/v1"  # Default Ollama
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream using OpenAI-compatible API."""
        # Most compatible APIs support the Chat Completions format
        provider = OpenAIProvider(self.config)
        provider.client = self.client
        async for event in provider.stream_chat(messages, tools, options):
            yield event

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> dict[str, Any]:
        provider = OpenAIProvider(self.config)
        provider.client = self.client
        return await provider.complete_chat(messages, tools, options)

    async def list_models(self) -> list[ModelInfo]:
        try:
            models = await self.client.models.list()
            self._available_models = [
                ModelInfo(
                    id=m.id,
                    name=m.id,
                    provider=self.provider_type,
                    context_window=4096,  # Unknown for local models
                    max_output_tokens=2048,
                    supports_tools=True,  # Assume supported
                    supports_streaming=True,
                )
                for m in models.data
            ]
        except Exception:
            self._available_models = [
                ModelInfo(id="llama3", name="Llama 3", provider=self.provider_type, context_window=8192, supports_tools=True),
                ModelInfo(id="codellama", name="Code Llama", provider=self.provider_type, context_window=16384, supports_tools=True),
                ModelInfo(id="mistral", name="Mistral", provider=self.provider_type, context_window=32768, supports_tools=True),
            ]
        return self._available_models

    async def validate_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False


# Register providers
from llm.base import register_provider

register_provider("openai", OpenAIProvider)
register_provider("openai_responses", OpenAIResponsesProvider)
register_provider("openai_compat", OpenAICompatProvider)
