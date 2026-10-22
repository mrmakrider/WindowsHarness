"""
Chat Panel for WindowsHarness.

Displays conversation history with streaming support, markdown rendering,
and tool call visualization.
"""

from __future__ import annotations

import markdown
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QTextCharFormat, QColor, QSyntaxHighlighter
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QLabel,
    QSizePolicy,
)

from config.settings import AppSettings
from core.types import ChatMessage, Role, ToolCallData, ToolCallStatus


class MessageWidget(QFrame):
    """Widget for displaying a single chat message."""

    def __init__(self, message: ChatMessage, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.message = message
        self.settings = settings
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        role_label = QLabel(self._role_icon())
        role_label.setFont(QFont(self.settings.ui.font_family, 10, QFont.Weight.Bold))
        role_label.setStyleSheet(self._role_color())
        header.addWidget(role_label)

        time_label = QLabel(self.message.timestamp.strftime("%H:%M:%S"))
        time_label.setStyleSheet("color: #888; font-size: 10px;")
        header.addStretch()
        header.addWidget(time_label)
        layout.addLayout(header)

        # Content
        if self.message.role == Role.ASSISTANT and self.message.tool_calls:
            self._add_tool_calls(layout)
        else:
            self._add_content(layout)

    def _role_icon(self) -> str:
        icons = {
            Role.SYSTEM: "⚙",
            Role.USER: "👤",
            Role.ASSISTANT: "🤖",
            Role.TOOL: "🔧",
        }
        return icons.get(self.message.role, "❓")

    def _role_color(self) -> str:
        colors = {
            Role.SYSTEM: "color: #4ec9b0;",
            Role.USER: "color: #dcdcaa;",
            Role.ASSISTANT: "color: #4fc1ff;",
            Role.TOOL: "color: #ce9178;",
        }
        return colors.get(self.message.role, "")

    def _add_content(self, layout: QVBoxLayout) -> None:
        """Add message content as markdown."""
        from PyQt6.QtWidgets import QTextBrowser
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setFrameStyle(QFrame.Shape.NoFrame)
        browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        browser.setMinimumHeight(40)
        browser.setMaximumHeight(500)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Convert markdown to HTML
        html = markdown.markdown(
            self.message.content,
            extensions=['fenced_code', 'tables', 'codehilite'],
            extension_configs={
                'codehilite': {'css_class': 'highlight'}
            }
        )
        browser.setHtml(html)

        # Style
        browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: transparent;
                border: none;
                font-family: '{self.settings.ui.font_family}';
                font-size: {self.settings.ui.font_size}pt;
                color: {'#d4d4d4' if self.settings.ui.theme.value == 'dark' else '#1e1e1e'};
            }}
            QTextBrowser a {{ color: #4fc1ff; }}
            pre {{ background-color: #2d2d2d; padding: 8px; border-radius: 4px; overflow: auto; }}
            code {{ font-family: '{self.settings.ui.font_family}'; font-size: {self.settings.ui.editor_font_size}pt; }}
        """)

        # Adjust height to content
        doc_height = browser.document().size().height()
        browser.setFixedHeight(min(int(doc_height) + 20, 500))

        layout.addWidget(browser)

    def _add_tool_calls(self, layout: QVBoxLayout) -> None:
        """Add tool calls with their results."""
        for tc in self.message.tool_calls:
            tool_frame = QFrame()
            tool_frame.setFrameStyle(QFrame.Shape.StyledPanel)
            tool_frame.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
            tool_layout = QVBoxLayout(tool_frame)

            # Tool header
            header = QHBoxLayout()
            status_icon = self._tool_status_icon(tc.status)
            header.addWidget(QLabel(f"{status_icon} {tc.name}"))
            header.addStretch()
            if tc.duration_ms():
                header.addWidget(QLabel(f"{tc.duration_ms()}ms"))
            tool_layout.addLayout(header)

            # Arguments
            if tc.arguments:
                import json
                args_text = json.dumps(tc.arguments, indent=2)
                args_label = QLabel(args_text)
                args_label.setFont(QFont(self.settings.ui.font_family, 9))
                args_label.setStyleSheet("color: #888;")
                args_label.setWordWrap(True)
                tool_layout.addWidget(args_label)

            # Result/Error
            if tc.result is not None:
                result_label = QLabel(f"Result: {tc.result}")
                result_label.setStyleSheet("color: #4ec9b0;")
                result_label.setWordWrap(True)
                tool_layout.addWidget(result_label)
            elif tc.error:
                error_label = QLabel(f"Error: {tc.error}")
                error_label.setStyleSheet("color: #f44747;")
                error_label.setWordWrap(True)
                tool_layout.addWidget(error_label)

            layout.addWidget(tool_frame)

    def _tool_status_icon(self, status: ToolCallStatus) -> str:
        icons = {
            ToolCallStatus.PENDING: "⏳",
            ToolCallStatus.RUNNING: "🔄",
            ToolCallStatus.COMPLETED: "✅",
            ToolCallStatus.FAILED: "❌",
            ToolCallStatus.CANCELLED: "🚫",
            ToolCallStatus.NEEDS_APPROVAL: "❓",
        }
        return icons.get(status, "❓")


class ChatPanel(QWidget):
    """Main chat panel with message list and input."""

    send_message = pyqtSignal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self._messages: list[ChatMessage] = []
        self._streaming_message: Optional[MessageWidget] = None
        self._streaming_text = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Message area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameStyle(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(16, 16, 16, 16)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area)

        # Input area
        input_frame = QFrame()
        input_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        input_frame.setMaximumHeight(120)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message... (Ctrl+Enter to send)")
        self.input_field.setFont(QFont(self.settings.ui.font_family, self.settings.ui.font_size))
        self.input_field.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_field)

        self.send_button = QPushButton("Send")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_button)

        layout.addWidget(input_frame)

        # Style
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply styling based on theme."""
        is_dark = self.settings.ui.theme.value == "dark"
        bg = "#1e1e1e" if is_dark else "#ffffff"
        fg = "#d4d4d4" if is_dark else "#1e1e1e"
        input_bg = "#2d2d2d" if is_dark else "#f3f3f3"
        border = "#3c3c3c" if is_dark else "#cccccc"

        self.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; color: {fg}; }}
            QScrollArea {{ background-color: {bg}; border: none; }}
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 8px;
                font-size: {self.settings.ui.font_size}pt;
            }}
            QLineEdit:focus {{ border-color: #007acc; }}
            QPushButton {{
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #005a9e; }}
            QPushButton:pressed {{ background-color: #004578; }}
            QFrame {{ background-color: {bg}; }}
        """)

    def _on_send(self) -> None:
        """Handle send button click."""
        text = self.input_field.text().strip()
        if text:
            self.send_message.emit(text)
            self.input_field.clear()

    def add_message(self, message: ChatMessage) -> None:
        """Add a message to the chat."""
        self._messages.append(message)
        widget = MessageWidget(message, self.settings)
        # Insert before stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)
        self._scroll_to_bottom()

    def update_message(self, message: ChatMessage, index: int = -1) -> None:
        """Update an existing message (for streaming)."""
        if index == -1:
            index = len(self._messages) - 1
        if 0 <= index < len(self._messages):
            self._messages[index] = message
            # Rebuild message widget (simpler than incremental update)
            self._rebuild_messages()

    def start_streaming(self, message: ChatMessage) -> None:
        """Start streaming a new assistant message."""
        self._streaming_message = message
        self._streaming_text = ""
        self._messages.append(message)
        widget = MessageWidget(message, self.settings)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)
        self._streaming_widget = widget
        self._scroll_to_bottom()

    def append_streaming(self, text: str) -> None:
        """Append text to streaming message."""
        self._streaming_text += text
        self._streaming_message.content = self._streaming_text
        # Update widget content
        self._rebuild_messages()

    def end_streaming(self) -> None:
        """End streaming mode."""
        self._streaming_message = None
        self._streaming_widget = None
        self._scroll_to_bottom()

    def _rebuild_messages(self) -> None:
        """Rebuild all message widgets (used for streaming updates)."""
        # Remove all widgets except stretch
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Re-add messages
        for msg in self._messages:
            widget = MessageWidget(msg, self.settings)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, widget)

        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll to bottom of chat."""
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def focus_input(self) -> None:
        """Focus the input field."""
        self.input_field.setFocus()

    def update_settings(self, settings: AppSettings) -> None:
        """Update settings."""
        self.settings = settings
        self._apply_style()
        self._rebuild_messages()

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        self._rebuild_messages()
