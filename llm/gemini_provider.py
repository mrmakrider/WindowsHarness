"""
Google Gemini Provider Implementation for WindowsHarness.

Supports Gemini API with streaming and function calling.
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
    ToolCallCompleteEvent,
    ToolCallDeltaEvent,
    ToolCallStartEvent,
    UsageEvent,
)

# Optional imports
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig, Tool, FunctionDeclaration
    HAS_GEMINI = True
except ImportError:
    genai = None
    HAS_GEMINI = False


class GeminiProvider(LlmProvider):
    """Google Gemini API provider."""

    @property
    def provider_type(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self.config.default_model or "gemini-1.5-pro"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not HAS_GEMINI:
            raise ImportError("google-generativeai package is required for GeminiProvider. Install with: pip install google-generativeai")
        api_key = config.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        genai.configure(api_key=api_key, transport="rest")
        self.client = genai.GenerativeModel(config.default_model or "gemini-1.5-pro")

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> AsyncIterator[StreamEventUnion]:
        """Stream chat completion using Gemini API."""
        gemini_messages = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools) if tools else None

        generation_config = GenerationConfig(
            temperature=options.temperature,
            max_output_tokens=options.max_tokens,
            top_p=options.top_p,
            top_k=options.top_k,
            stop_sequences=options.stop_sequences or None,
        )

        try:
            chat = self.client.start_chat(history=gemini_messages[:-1], tools=gemini_tools)
            response_stream = await chat.send_message_async(
                gemini_messages[-1]["parts"][0] if gemini_messages else "",
                generation_config=generation_config,
                stream=True,
            )

            accumulated_text = ""
            tool_calls_buffer: dict[str, dict] = {}

            async for chunk in response_stream:
                if not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue

                for part in candidate.content.parts:
                    if part.text:
                        accumulated_text += part.text
                        yield TextDeltaEvent(text=part.text, full_text=accumulated_text)

                    if part.function_call:
                        fc = part.function_call
                        call_id = fc.id or f"call_{len(tool_calls_buffer)}"

                        if call_id not in tool_calls_buffer:
                            # New tool call
                            tool_calls_buffer[call_id] = {
                                "id": call_id,
                                "name": fc.name,
                                "arguments": dict(fc.args) if fc.args else {},
                            }
                            yield ToolCallStartEvent(
                                tool_call=ToolCallData(
                                    id=call_id,
                                    name=fc.name,
                                    arguments=dict(fc.args) if fc.args else {},
                                    status=ToolCallStatus.RUNNING,
                                )
                            )
                        else:
                            # Update arguments (Gemini sends complete args each time)
                            tool_calls_buffer[call_id]["arguments"] = dict(fc.args) if fc.args else {}

                # Check finish reason
                if candidate.finish_reason:
                    for call_id, buf in tool_calls_buffer.items():
                        yield ToolCallCompleteEvent(
                            tool_call=ToolCallData(
                                id=buf["id"],
                                name=buf["name"],
                                arguments=buf["arguments"],
                                status=ToolCallStatus.COMPLETED,
                            )
                        )

                    yield DoneEvent(finish_reason=str(candidate.finish_reason))

                    # Usage metadata
                    if chunk.usage_metadata:
                        yield UsageEvent(
                            input_tokens=chunk.usage_metadata.prompt_token_count,
                            output_tokens=chunk.usage_metadata.candidates_token_count,
                            total_tokens=chunk.usage_metadata.total_token_count,
                            model=options.model,
                        )
                    break

        except Exception as e:
            yield ErrorEvent(message=str(e), recoverable=True)

    async def complete_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: RequestOptions,
    ) -> dict[str, Any]:
        gemini_messages = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools) if tools else None

        generation_config = GenerationConfig(
            temperature=options.temperature,
            max_output_tokens=options.max_tokens,
            top_p=options.top_p,
            top_k=options.top_k,
            stop_sequences=options.stop_sequences or None,
        )

        chat = self.client.start_chat(history=gemini_messages[:-1], tools=gemini_tools)
        response = await chat.send_message_async(
            gemini_messages[-1]["parts"][0] if gemini_messages else "",
            generation_config=generation_config,
            stream=False,
        )

        tool_calls = []
        text_content = ""

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text_content += part.text
                if part.function_call:
                    tool_calls.append({
                        "id": part.function_call.id or f"call_{len(tool_calls)}",
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args) if part.function_call.args else {},
                    })

        return {
            "content": text_content,
            "tool_calls": tool_calls,
            "usage": {
                "input_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
                "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0,
            },
        }

    async def list_models(self) -> list[ModelInfo]:
        if self._available_models is not None:
            return self._available_models

        try:
            models = genai.list_models()
            self._available_models = [
                ModelInfo(
                    id=m.name.replace("models/", ""),
                    name=m.display_name or m.name,
                    provider=self.provider_type,
                    context_window=self._get_context_window(m.name),
                    max_output_tokens=self._get_max_output(m.name),
                    supports_tools="generateContent" in m.supported_generation_methods,
                    supports_vision=self._supports_vision(m.name),
                    supports_streaming=True,
                )
                for m in models
                if "generateContent" in m.supported_generation_methods
            ]
        except Exception:
            self._available_models = self._get_fallback_models()

        return self._available_models

    async def validate_connection(self) -> bool:
        try:
            list(genai.list_models())  # Just test connection
            return True
        except Exception:
            return False

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert standard messages to Gemini format."""
        gemini_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                # Gemini doesn't have system role, prepend to first user message
                gemini_messages.append({
                    "role": "user",
                    "parts": [{"text": f"System: {content}"}],
                })
            elif role == "user":
                if isinstance(content, list):
                    parts = []
                    for part in content:
                        if part.get("type") == "text":
                            parts.append({"text": part["text"]})
                        elif part.get("type") == "image_url":
                            # Gemini expects inline data or file URI
                            parts.append({"text": f"[Image: {part['image_url']['url']}]"})
                    gemini_messages.append({"role": "user", "parts": parts})
                else:
                    gemini_messages.append({"role": "user", "parts": [{"text": str(content)}]})
            elif role == "assistant":
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        gemini_messages.append({
                            "role": "model",
                            "parts": [{
                                "function_call": {
                                    "name": tc["name"],
                                    "args": tc["arguments"],
                                    "id": tc["id"],
                                }
                            }],
                        })
                elif content:
                    gemini_messages.append({"role": "model", "parts": [{"text": str(content)}]})
            elif role == "tool":
                gemini_messages.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": msg.get("name", ""),
                            "response": {"result": content},
                            "id": msg.get("tool_call_id"),
                        }
                    }],
                })

        return gemini_messages

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[Tool]:
        """Convert standard tools to Gemini format."""
        function_decls = []
        for tool in tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                function_decls.append(FunctionDeclaration(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=fn.get("parameters", {"type": "object", "properties": {}}),
                ))
        return [Tool(function_declarations=function_decls)] if function_decls else None

    def _get_context_window(self, model_name: str) -> int:
        if "1.5-pro" in model_name:
            return 2000000
        elif "1.5-flash" in model_name:
            return 1000000
        elif "1.0-pro" in model_name:
            return 32768
        return 32768

    def _get_max_output(self, model_name: str) -> int:
        if "1.5-pro" in model_name or "1.5-flash" in model_name:
            return 8192
        return 2048

    def _supports_vision(self, model_name: str) -> bool:
        return "vision" in model_name or "1.5" in model_name

    def _get_fallback_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="gemini-1.5-pro", name="Gemini 1.5 Pro", provider=self.provider_type, context_window=2000000, max_output_tokens=8192, supports_tools=True, supports_vision=True),
            ModelInfo(id="gemini-1.5-flash", name="Gemini 1.5 Flash", provider=self.provider_type, context_window=1000000, max_output_tokens=8192, supports_tools=True, supports_vision=True),
            ModelInfo(id="gemini-1.0-pro", name="Gemini 1.0 Pro", provider=self.provider_type, context_window=32768, max_output_tokens=2048, supports_tools=True),
        ]


from llm.base import register_provider
register_provider("gemini", GeminiProvider)
