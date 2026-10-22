"""
Context Hygiene and History Compaction for WindowsHarness.

Manages conversation context, token counting, and automatic compaction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from core.types import ChatMessage, Role, ToolCallData, ToolCallStatus


@dataclass
class TokenBudget:
    """Token budget for context management."""

    max_tokens: int
    reserved_tokens: int = 2000  # Reserved for response
    system_tokens: int = 0
    message_tokens: int = 0
    tool_tokens: int = 0

    @property
    def used_tokens(self) -> int:
        return self.system_tokens + self.message_tokens + self.tool_tokens

    @property
    def available_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens - self.reserved_tokens)

    @property
    def usage_ratio(self) -> float:
        if self.max_tokens == 0:
            return 0.0
        return self.used_tokens / self.max_tokens


class TokenCounter:
    """Token counting utilities."""

    # Rough estimation: 1 token ≈ 4 characters for English, 2-3 for code
    CHARS_PER_TOKEN = 3.5

    @classmethod
    def estimate(cls, text: str) -> int:
        """Estimate token count for text."""
        if not text:
            return 0
        return max(1, int(len(text) / cls.CHARS_PER_TOKEN))

    @classmethod
    def estimate_message(cls, message: ChatMessage) -> int:
        """Estimate tokens for a chat message."""
        tokens = cls.estimate(message.content)
        for tc in message.tool_calls:
            tokens += cls.estimate(tc.name)
            tokens += cls.estimate(json.dumps(tc.arguments))
            if tc.result:
                tokens += cls.estimate(json.dumps(tc.result))
        return tokens

    @classmethod
    def estimate_messages(cls, messages: list[ChatMessage]) -> int:
        """Estimate total tokens for message list."""
        return sum(cls.estimate_message(m) for m in messages)


class ContextHygiene:
    """Manages context hygiene: compaction, tool result shrinking, etc."""

    def __init__(
        self,
        max_tokens: int = 128000,
        auto_compact_threshold: float = 0.85,
        shrink_tool_results: bool = True,
        max_tool_result_tokens: int = 5000,
    ):
        self.max_tokens = max_tokens
        self.auto_compact_threshold = auto_compact_threshold
        self._shrink_tool_results = shrink_tool_results
        self.max_tool_result_tokens = max_tool_result_tokens
        self.token_counter = TokenCounter()

    def should_compact(self, messages: list[ChatMessage]) -> bool:
        """Check if context should be compacted."""
        tokens = self.token_counter.estimate_messages(messages)
        return tokens >= self.max_tokens * self.auto_compact_threshold

    def shrink_tool_results(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Shrink large tool results in messages."""
        if not self._shrink_tool_results:
            return messages

        new_messages = []
        for msg in messages:
            if msg.role == Role.TOOL:
                # Tool result message - shrink if too large
                content = msg.content
                tokens = self.token_counter.estimate(content)
                if tokens > self.max_tool_result_tokens:
                    # Truncate with indicator
                    keep_chars = int(self.max_tool_result_tokens * self.token_counter.CHARS_PER_TOKEN)
                    truncated = content[:keep_chars] + f"\n\n[... truncated, {tokens} tokens total ...]"
                    new_msg = ChatMessage(
                        role=msg.role,
                        content=truncated,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                        timestamp=msg.timestamp,
                        metadata={**msg.metadata, "truncated": True, "original_tokens": tokens},
                    )
                    new_messages.append(new_msg)
                else:
                    new_messages.append(msg)
            else:
                new_messages.append(msg)

        return new_messages

    def remove_old_tool_results(self, messages: list[ChatMessage], keep_last: int = 10) -> list[ChatMessage]:
        """Remove old tool results, keeping only the most recent."""
        tool_messages = [m for m in messages if m.role == Role.TOOL]
        if len(tool_messages) <= keep_last:
            return messages

        # Keep system, user, assistant messages + last N tool messages
        keep_tool_ids = set(m.tool_call_id for m in tool_messages[-keep_last:])

        new_messages = []
        for msg in messages:
            if msg.role == Role.TOOL and msg.tool_call_id not in keep_tool_ids:
                continue
            new_messages.append(msg)

        return new_messages


class HistoryCompactor:
    """Compacts conversation history by summarizing old messages."""

    def __init__(
        self,
        llm_provider: Any = None,  # LlmProvider for summarization
        summary_model: str = "gpt-4o-mini",
        max_summary_tokens: int = 2000,
    ):
        self.llm_provider = llm_provider
        self.summary_model = summary_model
        self.max_summary_tokens = max_summary_tokens

    async def compact(
        self,
        messages: list[ChatMessage],
        keep_recent: int = 20,
        system_prompt: Optional[str] = None,
    ) -> list[ChatMessage]:
        """Compact history by summarizing old messages."""
        if len(messages) <= keep_recent:
            return messages

        # Split into old and recent
        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        # Generate summary
        summary = await self._generate_summary(old_messages, system_prompt)

        # Create summary message
        summary_msg = ChatMessage(
            role=Role.SYSTEM,
            content=f"[Conversation Summary]\n{summary}",
            metadata={"is_summary": True, "original_count": len(old_messages)},
        )

        # Combine: system prompt + summary + recent messages
        result = []
        if system_prompt:
            result.append(ChatMessage(role=Role.SYSTEM, content=system_prompt))
        result.append(summary_msg)
        result.extend(recent_messages)

        return result

    async def _generate_summary(
        self,
        messages: list[ChatMessage],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a summary of old messages."""
        if self.llm_provider:
            return await self._llm_summarize(messages, system_prompt)
        return self._heuristic_summarize(messages)

    async def _llm_summarize(
        self,
        messages: list[ChatMessage],
        system_prompt: Optional[str],
    ) -> str:
        """Use LLM to generate summary."""
        try:
            from llm.base import RequestOptions, StreamEventType
            from core.types import ChatMessage

            # Build summarization prompt
            prompt = "Summarize the following conversation concisely, preserving key decisions, code changes, and outcomes:\n\n"
            for msg in messages:
                if msg.role == Role.USER:
                    prompt += f"User: {msg.content[:500]}\n"
                elif msg.role == Role.ASSISTANT:
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            prompt += f"Assistant used {tc.name}: {json.dumps(tc.arguments)[:200]}\n"
                    elif msg.content:
                        prompt += f"Assistant: {msg.content[:500]}\n"
                elif msg.role == Role.TOOL:
                    prompt += f"Tool result ({msg.name}): {msg.content[:300]}\n"

            prompt += "\nSummary:"

            options = RequestOptions(
                model=self.summary_model,
                temperature=0.3,
                max_tokens=self.max_summary_tokens,
            )

            summary_text = ""
            stream = self.llm_provider.stream_chat(
                [{"role": "user", "content": prompt}],
                [],
                options,
            )

            async for event in stream:
                if event.type == StreamEventType.TEXT_DELTA:
                    summary_text += event.text

            return summary_text.strip() or "Summary generation failed"

        except Exception as e:
            return f"Summary failed: {e}. {self._heuristic_summarize(messages)}"

    def _heuristic_summarize(self, messages: list[ChatMessage]) -> str:
        """Heuristic summarization without LLM."""
        stats = {
            "user_messages": 0,
            "tool_calls": 0,
            "tools_used": set(),
            "files_modified": set(),
        }

        for msg in messages:
            if msg.role == Role.USER:
                stats["user_messages"] += 1
            elif msg.role == Role.ASSISTANT:
                for tc in msg.tool_calls:
                    stats["tool_calls"] += 1
                    stats["tools_used"].add(tc.name)
                    if tc.name in ("write", "edit", "delete", "move"):
                        # Try to extract file path
                        if "path" in tc.arguments:
                            stats["files_modified"].add(tc.arguments["path"])

        summary_lines = [
            f"Conversation with {stats['user_messages']} user messages and {stats['tool_calls']} tool calls.",
        ]

        if stats["tools_used"]:
            summary_lines.append(f"Tools used: {', '.join(sorted(stats['tools_used']))}")

        if stats["files_modified"]:
            summary_lines.append(f"Files modified: {', '.join(sorted(stats['files_modified']))}")

        # Include first and last user messages for context
        user_msgs = [m for m in messages if m.role == Role.USER]
        if user_msgs:
            summary_lines.append(f"First request: {user_msgs[0].content[:200]}")
            if len(user_msgs) > 1:
                summary_lines.append(f"Last request: {user_msgs[-1].content[:200]}")

        return "\n".join(summary_lines)


def compact_context(
    messages: list[ChatMessage],
    max_tokens: int = 128000,
    threshold: float = 0.85,
    llm_provider: Any = None,
    keep_recent: int = 20,
) -> list[ChatMessage]:
    """Full context compaction pipeline."""
    hygiene = ContextHygiene(max_tokens=max_tokens, auto_compact_threshold=threshold)

    # Step 1: Shrink tool results
    messages = hygiene.shrink_tool_results(messages)

    # Step 2: Remove old tool results if still over budget
    tokens = TokenCounter.estimate_messages(messages)
    if tokens > max_tokens * threshold:
        messages = hygiene.remove_old_tool_results(messages)

    # Step 3: Compact history if still over budget
    tokens = TokenCounter.estimate_messages(messages)
    if tokens > max_tokens * threshold:
        compactor = HistoryCompactor(llm_provider=llm_provider)
        # Note: async, would need to be awaited in real usage
        # messages = await compactor.compact(messages, keep_recent=keep_recent)

    return messages
