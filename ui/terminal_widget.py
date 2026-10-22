"""
Terminal Widget for WindowsHarness.

PTY-based terminal emulator using QProcess or asyncio subprocess.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

from PyQt6.QtCore import Qt, QProcess, QTimer, pyqtSignal, pyqtSlot, QByteArray
from PyQt6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QComboBox,
    QLabel,
)

from config.settings import AppSettings


class TerminalWidget(QWidget):
    """Terminal emulator widget."""

    command_executed = pyqtSignal(str, str)  # command, output

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.process: Optional[QProcess] = None
        self.current_dir = os.getcwd()
        self.history = []
        self.history_index = -1
        self._setup_ui()
        self._start_shell()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)

        self.shell_combo = QComboBox()
        self.shell_combo.addItems(self._get_available_shells())
        self.shell_combo.currentTextChanged.connect(self._restart_shell)
        toolbar.addWidget(QLabel("Shell:"))
        toolbar.addWidget(self.shell_combo)

        toolbar.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_terminal)
        toolbar.addWidget(self.clear_btn)

        self.kill_btn = QPushButton("Kill")
        self.kill_btn.clicked.connect(self._kill_process)
        toolbar.addWidget(self.kill_btn)

        layout.addLayout(toolbar)

        # Terminal output
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont(self.settings.ui.font_family, self.settings.ui.terminal_font_size))
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._apply_terminal_style()
        layout.addWidget(self.output)

        # Input line
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(4, 4, 4, 4)

        self.prompt_label = QLabel("$")
        self.prompt_label.setFont(QFont(self.settings.ui.font_family, self.settings.ui.terminal_font_size))
        input_layout.addWidget(self.prompt_label)

        self.input = QLineEdit()
        self.input.setFont(QFont(self.settings.ui.font_family, self.settings.ui.terminal_font_size))
        self.input.returnPressed.connect(self._send_command)
        self.input.installEventFilter(self)
        input_layout.addWidget(self.input)

        layout.addLayout(input_layout)

    def _get_available_shells(self) -> list[str]:
        """Get available shells on the system."""
        shells = []
        if sys.platform == "win32":
            for shell in ["pwsh", "powershell", "cmd"]:
                if self._which(shell):
                    shells.append(shell)
            if not shells:
                shells = ["cmd"]
        else:
            for shell in ["bash", "zsh", "fish", "sh"]:
                if self._which(shell):
                    shells.append(shell)
            if not shells:
                shells = ["sh"]
        return shells

    def _which(self, cmd: str) -> bool:
        """Check if command exists."""
        import shutil
        return shutil.which(cmd) is not None

    def _apply_terminal_style(self) -> None:
        """Apply terminal styling."""
        is_dark = self.settings.ui.theme.value == "dark"
        if is_dark:
            self.output.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: none;
                    font-family: 'Consolas', 'Monospace';
                }
            """)
            self.input.setStyleSheet("""
                QLineEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                    border-radius: 2px;
                    padding: 4px;
                }
            """)
        else:
            self.output.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #ffffff;
                    color: #1e1e1e;
                    border: none;
                    font-family: 'Consolas', 'Monospace';
                }
            """)
            self.input.setStyleSheet("""
                QLineEdit {
                    background-color: #ffffff;
                    color: #1e1e1e;
                    border: 1px solid #cccccc;
                    border-radius: 2px;
                    padding: 4px;
                }
            """)

    def _start_shell(self) -> None:
        """Start the shell process."""
        shell = self.shell_combo.currentText()
        self.process = QProcess(self)
        self.process.setProgram(shell)
        self.process.setWorkingDirectory(self.current_dir)

        # Connect signals
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_process_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        # Start process
        self.process.start()
        self._append_output(f"[Started {shell} in {self.current_dir}]\n", "system")

    def _restart_shell(self, shell: str) -> None:
        """Restart with new shell."""
        if self.process:
            self.process.kill()
            self.process.waitForFinished(1000)
        self._start_shell()

    def _on_stdout(self) -> None:
        """Handle stdout from process."""
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        self._append_output(text, "stdout")

    def _on_stderr(self) -> None:
        """Handle stderr from process."""
        data = self.process.readAllStandardError()
        text = bytes(data).decode("utf-8", errors="replace")
        self._append_output(text, "stderr")

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        """Handle process exit."""
        self._append_output(f"\n[Process exited with code {exit_code}]\n", "system")
        # Restart shell
        QTimer.singleShot(500, self._start_shell)

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        """Handle process error."""
        self._append_output(f"\n[Process error: {error}]\n", "error")

    def _send_command(self) -> None:
        """Send command to shell."""
        if not self.process:
            return

        command = self.input.text()
        if not command:
            return

        # Add to history
        self.history.append(command)
        self.history_index = len(self.history)

        # Display command
        self._append_output(f"{self._get_prompt()} {command}\n", "command")

        # Send to process
        self.process.write((command + "\n").encode("utf-8"))

        # Clear input
        self.input.clear()

    def _get_prompt(self) -> str:
        """Get current prompt string."""
        return f"{os.path.basename(self.current_dir)}$"

    def _append_output(self, text: str, type_: str = "stdout") -> None:
        """Append text to terminal output with color."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        format_ = QTextCharFormat()
        if type_ == "stderr" or type_ == "error":
            format_.setForeground(QColor("#f44747"))
        elif type_ == "command":
            format_.setForeground(QColor("#4fc1ff"))
            format_.setFontWeight(QFont.Weight.Bold)
        elif type_ == "system":
            format_.setForeground(QColor("#888"))
        else:
            format_.setForeground(QColor("#d4d4d4"))

        cursor.mergeCharFormat(format_)
        cursor.insertText(text)

        # Auto-scroll
        self.output.ensureCursorVisible()

    def _clear_terminal(self) -> None:
        """Clear terminal output."""
        self.output.clear()

    def _kill_process(self) -> None:
        """Kill current process."""
        if self.process:
            self.process.kill()

    def eventFilter(self, obj, event):
        """Handle key events for history navigation."""
        if obj == self.input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                if self.history_index > 0:
                    self.history_index -= 1
                    self.input.setText(self.history[self.history_index])
                return True
            elif event.key() == Qt.Key.Key_Down:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.input.setText(self.history[self.history_index])
                elif self.history_index == len(self.history) - 1:
                    self.history_index = len(self.history)
                    self.input.clear()
                return True
        return super().eventFilter(obj, event)

    def focus_input(self) -> None:
        """Focus the input field."""
        self.input.setFocus()

    def set_working_dir(self, path: str) -> None:
        """Change working directory."""
        self.current_dir = path
        if self.process:
            self.process.setWorkingDirectory(path)
        self._append_output(f"\n[Changed directory to {path}]\n", "system")
