"""
Settings Dialog for WindowsHarness.

Comprehensive settings UI for all configuration options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
)

from config.settings import (
    AppSettings,
    PermissionMode,
    ThemeMode,
    LogLevel,
    ProviderType,
    ProviderConfig,
    AgentSettings,
    UISettings,
    TerminalSettings,
    BrowserSettings,
    ShellSettings,
    LoggingSettings,
    GitHubSettings,
    SkillsSettings,
)
import keyring


class SettingsDialog(QDialog):
    """Main settings dialog."""

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("WindowsHarness Settings")
        self.resize(700, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self._create_general_tab()
        self._create_agent_tab()
        self._create_ui_tab()
        self._create_terminal_tab()
        self._create_providers_tab()
        self._create_github_tab()
        self._create_skills_tab()
        self._create_advanced_tab()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(buttons)

    def _create_general_tab(self) -> None:
        """Create general settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Workspace
        self.workspace_edit = QLineEdit(self.settings.agent.default_workspace or "")
        self.workspace_edit.setPlaceholderText("Default workspace path")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_folder(self.workspace_edit))
        ws_layout = QHBoxLayout()
        ws_layout.addWidget(self.workspace_edit)
        ws_layout.addWidget(browse_btn)
        layout.addRow("Default Workspace:", ws_layout)

        # Language
        self.language_combo = QComboBox()
        self.language_combo.addItems(["en", "zh", "ja", "ko"])
        self.language_combo.setCurrentText(self.settings.ui.language)
        layout.addRow("Language:", self.language_combo)

        # Log level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems([l.value for l in LogLevel])
        self.log_level_combo.setCurrentText(self.settings.logging.level.value)
        layout.addRow("Log Level:", self.log_level_combo)

        self.tabs.addTab(widget, "General")

    def _create_agent_tab(self) -> None:
        """Create agent settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Permission mode
        self.permission_combo = QComboBox()
        self.permission_combo.addItems([p.value for p in PermissionMode])
        self.permission_combo.setCurrentText(self.settings.agent.permission_mode.value)
        layout.addRow("Permission Mode:", self.permission_combo)

        # Max turns
        self.max_turns_spin = QSpinBox()
        self.max_turns_spin.setRange(1, 200)
        self.max_turns_spin.setValue(self.settings.agent.max_turns)
        layout.addRow("Max Turns:", self.max_turns_spin)

        # Max context tokens
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(4096, 1000000)
        self.max_tokens_spin.setSingleStep(1024)
        self.max_tokens_spin.setValue(self.settings.agent.max_context_tokens)
        layout.addRow("Max Context Tokens:", self.max_tokens_spin)

        # Auto compact threshold
        self.compact_threshold_spin = QDoubleSpinBox()
        self.compact_threshold_spin.setRange(0.5, 0.99)
        self.compact_threshold_spin.setSingleStep(0.01)
        self.compact_threshold_spin.setValue(self.settings.agent.auto_compact_threshold)
        layout.addRow("Auto Compact Threshold:", self.compact_threshold_spin)

        # Show thinking
        self.show_thinking_check = QCheckBox()
        self.show_thinking_check.setChecked(self.settings.agent.show_thinking)
        layout.addRow("Show Thinking:", self.show_thinking_check)

        # Stream tool calls
        self.stream_tools_check = QCheckBox()
        self.stream_tools_check.setChecked(self.settings.agent.stream_tool_calls)
        layout.addRow("Stream Tool Calls:", self.stream_tools_check)

        self.tabs.addTab(widget, "Agent")

    def _create_ui_tab(self) -> None:
        """Create UI settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([t.value for t in ThemeMode])
        self.theme_combo.setCurrentText(self.settings.ui.theme.value)
        layout.addRow("Theme:", self.theme_combo)

        # Font family
        self.font_family_edit = QLineEdit(self.settings.ui.font_family)
        layout.addRow("Font Family:", self.font_family_edit)

        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(self.settings.ui.font_size)
        layout.addRow("Font Size:", self.font_size_spin)

        # Editor font size
        self.editor_font_size_spin = QSpinBox()
        self.editor_font_size_spin.setRange(8, 24)
        self.editor_font_size_spin.setValue(self.settings.ui.editor_font_size)
        layout.addRow("Editor Font Size:", self.editor_font_size_spin)

        # Terminal font size
        self.terminal_font_size_spin = QSpinBox()
        self.terminal_font_size_spin.setRange(8, 24)
        self.terminal_font_size_spin.setValue(self.settings.ui.terminal_font_size)
        layout.addRow("Terminal Font Size:", self.terminal_font_size_spin)

        # Line numbers
        self.line_numbers_check = QCheckBox()
        self.line_numbers_check.setChecked(self.settings.ui.show_line_numbers)
        layout.addRow("Show Line Numbers:", self.line_numbers_check)

        # Word wrap
        self.word_wrap_check = QCheckBox()
        self.word_wrap_check.setChecked(self.settings.ui.word_wrap)
        layout.addRow("Word Wrap:", self.word_wrap_check)

        # Minimap
        self.minimap_check = QCheckBox()
        self.minimap_check.setChecked(self.settings.ui.minimap)
        layout.addRow("Minimap:", self.minimap_check)

        # Compact mode
        self.compact_mode_check = QCheckBox()
        self.compact_mode_check.setChecked(self.settings.ui.compact_mode)
        layout.addRow("Compact Mode:", self.compact_mode_check)

        self.tabs.addTab(widget, "Appearance")

    def _create_terminal_tab(self) -> None:
        """Create terminal settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Shell
        self.shell_combo = QComboBox()
        self.shell_combo.setEditable(True)
        self.shell_combo.addItems(["auto", "pwsh", "powershell", "cmd", "bash", "zsh", "sh"])
        self.shell_combo.setCurrentText(self.settings.terminal.shell or "auto")
        layout.addRow("Default Shell:", self.shell_combo)

        # Cursor blink
        self.cursor_blink_check = QCheckBox()
        self.cursor_blink_check.setChecked(self.settings.terminal.cursor_blink)
        layout.addRow("Cursor Blink:", self.cursor_blink_check)

        # Cursor shape
        self.cursor_shape_combo = QComboBox()
        self.cursor_shape_combo.addItems(["block", "underline", "bar"])
        self.cursor_shape_combo.setCurrentText(self.settings.terminal.cursor_shape)
        layout.addRow("Cursor Shape:", self.cursor_shape_combo)

        # Scrollback lines
        self.scrollback_spin = QSpinBox()
        self.scrollback_spin.setRange(1000, 100000)
        self.scrollback_spin.setSingleStep(1000)
        self.scrollback_spin.setValue(self.settings.terminal.scrollback_lines)
        layout.addRow("Scrollback Lines:", self.scrollback_spin)

        # Bell
        self.bell_check = QCheckBox()
        self.bell_check.setChecked(self.settings.terminal.bell)
        layout.addRow("Bell:", self.bell_check)

        # Copy on select
        self.copy_on_select_check = QCheckBox()
        self.copy_on_select_check.setChecked(self.settings.terminal.copy_on_select)
        layout.addRow("Copy on Select:", self.copy_on_select_check)

        self.tabs.addTab(widget, "Terminal")

    def _create_providers_tab(self) -> None:
        """Create LLM providers tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Provider list
        self.providers_list = QListWidget()
        self.providers_list.currentItemChanged.connect(self._on_provider_selected)
        layout.addWidget(self.providers_list)

        # Provider details
        details_group = QGroupBox("Provider Details")
        details_layout = QFormLayout(details_group)

        self.provider_name_edit = QLineEdit()
        details_layout.addRow("Name:", self.provider_name_edit)

        self.provider_type_combo = QComboBox()
        self.provider_type_combo.addItems([t.value for t in ProviderType])
        details_layout.addRow("Type:", self.provider_type_combo)

        self.provider_base_url_edit = QLineEdit()
        details_layout.addRow("Base URL:", self.provider_base_url_edit)

        self.provider_org_edit = QLineEdit()
        details_layout.addRow("Organization:", self.provider_org_edit)

        self.provider_default_model_edit = QLineEdit()
        details_layout.addRow("Default Model:", self.provider_default_model_edit)

        self.provider_enabled_check = QCheckBox()
        details_layout.addRow("Enabled:", self.provider_enabled_check)

        self.provider_timeout_spin = QSpinBox()
        self.provider_timeout_spin.setRange(10, 600)
        self.provider_timeout_spin.setValue(120)
        details_layout.addRow("Timeout (s):", self.provider_timeout_spin)

        self.provider_max_retries_spin = QSpinBox()
        self.provider_max_retries_spin.setRange(0, 10)
        self.provider_max_retries_spin.setValue(3)
        details_layout.addRow("Max Retries:", self.provider_max_retries_spin)

        # API Key
        key_layout = QHBoxLayout()
        self.provider_api_key_edit = QLineEdit()
        self.provider_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.provider_api_key_edit.setPlaceholderText("Enter API key (stored securely)")
        key_layout.addWidget(self.provider_api_key_edit)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(lambda checked: self.provider_api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        ))
        key_layout.addWidget(self.show_key_btn)
        details_layout.addRow("API Key:", key_layout)

        layout.addWidget(details_group)

        # Provider buttons
        btn_layout = QHBoxLayout()
        self.add_provider_btn = QPushButton("Add")
        self.add_provider_btn.clicked.connect(self._add_provider)
        btn_layout.addWidget(self.add_provider_btn)

        self.remove_provider_btn = QPushButton("Remove")
        self.remove_provider_btn.clicked.connect(self._remove_provider)
        btn_layout.addWidget(self.remove_provider_btn)

        self.test_provider_btn = QPushButton("Test")
        self.test_provider_btn.clicked.connect(self._test_provider)
        btn_layout.addWidget(self.test_provider_btn)

        layout.addLayout(btn_layout)

        # Populate list
        self._refresh_providers_list()

        self.tabs.addTab(widget, "Providers")

    def _create_github_tab(self) -> None:
        """Create GitHub settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Token
        key_layout = QHBoxLayout()
        self.github_token_edit = QLineEdit()
        self.github_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.github_token_edit.setPlaceholderText("GitHub token (stored securely)")
        key_layout.addWidget(self.github_token_edit)
        self.show_github_key_btn = QPushButton("Show")
        self.show_github_key_btn.setCheckable(True)
        self.show_github_key_btn.toggled.connect(lambda checked: self.github_token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        ))
        key_layout.addWidget(self.show_github_key_btn)
        layout.addRow("GitHub Token:", key_layout)

        # Default owner/repo
        self.github_owner_edit = QLineEdit(self.settings.github.default_owner)
        layout.addRow("Default Owner:", self.github_owner_edit)

        self.github_repo_edit = QLineEdit(self.settings.github.default_repo)
        layout.addRow("Default Repo:", self.github_repo_edit)

        # Test button
        self.test_github_btn = QPushButton("Test Connection")
        self.test_github_btn.clicked.connect(self._test_github)
        layout.addRow("", self.test_github_btn)

        self.tabs.addTab(widget, "GitHub")

    def _create_skills_tab(self) -> None:
        """Create skills settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        self.skills_enabled_check = QCheckBox()
        self.skills_enabled_check.setChecked(self.settings.skills.enabled)
        layout.addRow("Enable Skills:", self.skills_enabled_check)

        self.custom_skills_edit = QLineEdit(self.settings.skills.custom_skills_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_folder(self.custom_skills_edit))
        skills_layout = QHBoxLayout()
        skills_layout.addWidget(self.custom_skills_edit)
        skills_layout.addWidget(browse_btn)
        layout.addRow("Custom Skills Dir:", skills_layout)

        self.auto_update_check = QCheckBox()
        self.auto_update_check.setChecked(self.settings.skills.auto_update_builtin)
        layout.addRow("Auto-update Built-in:", self.auto_update_check)

        self.tabs.addTab(widget, "Skills")

    def _create_advanced_tab(self) -> None:
        """Create advanced settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Browser settings
        browser_group = QGroupBox("Browser")
        browser_layout = QFormLayout(browser_group)

        self.browser_headless_check = QCheckBox()
        self.browser_headless_check.setChecked(self.settings.browser.headless)
        browser_layout.addRow("Headless:", self.browser_headless_check)

        self.browser_width_spin = QSpinBox()
        self.browser_width_spin.setRange(800, 3840)
        self.browser_width_spin.setValue(self.settings.browser.viewport_width)
        browser_layout.addRow("Viewport Width:", self.browser_width_spin)

        self.browser_height_spin = QSpinBox()
        self.browser_height_spin.setRange(600, 2160)
        self.browser_height_spin.setValue(self.settings.browser.viewport_height)
        browser_layout.addRow("Viewport Height:", self.browser_height_spin)

        layout.addRow(browser_group)

        # Shell settings
        shell_group = QGroupBox("Shell")
        shell_layout = QFormLayout(shell_group)

        self.shell_timeout_spin = QSpinBox()
        self.shell_timeout_spin.setRange(30, 3600)
        self.shell_timeout_spin.setValue(self.settings.shell.timeout_seconds)
        shell_layout.addRow("Default Timeout (s):", self.shell_timeout_spin)

        self.shell_max_output_spin = QSpinBox()
        self.shell_max_output_spin.setRange(1000, 50000)
        self.shell_max_output_spin.setValue(self.settings.shell.max_output_lines)
        shell_layout.addRow("Max Output Lines:", self.shell_max_output_spin)

        layout.addRow(shell_group)

        # Logging
        log_group = QGroupBox("Logging")
        log_layout = QFormLayout(log_group)

        self.log_file_check = QCheckBox()
        self.log_file_check.setChecked(self.settings.logging.file_enabled)
        log_layout.addRow("File Logging:", self.log_file_check)

        self.log_file_edit = QLineEdit(self.settings.logging.file_path)
        log_layout.addRow("Log File:", self.log_file_edit)

        self.log_max_size_spin = QSpinBox()
        self.log_max_size_spin.setRange(1, 100)
        self.log_max_size_spin.setValue(self.settings.logging.max_file_size_mb)
        log_layout.addRow("Max File Size (MB):", self.log_max_size_spin)

        self.log_max_files_spin = QSpinBox()
        self.log_max_files_spin.setRange(1, 20)
        self.log_max_files_spin.setValue(self.settings.logging.max_files)
        log_layout.addRow("Max Files:", self.log_max_files_spin)

        layout.addRow(log_group)

        self.tabs.addTab(widget, "Advanced")

    def _refresh_providers_list(self) -> None:
        """Refresh the providers list."""
        self.providers_list.clear()
        for provider in self.settings.providers:
            item = QListWidgetItem(f"{provider.name} ({provider.type.value})")
            item.setData(Qt.ItemDataRole.UserRole, provider)
            self.providers_list.addItem(item)

    def _on_provider_selected(self, current, previous) -> None:
        """Handle provider selection."""
        if current:
            provider = current.data(Qt.ItemDataRole.UserRole)
            self.provider_name_edit.setText(provider.name)
            self.provider_type_combo.setCurrentText(provider.type.value)
            self.provider_base_url_edit.setText(provider.base_url or "")
            self.provider_org_edit.setText(provider.organization or "")
            self.provider_default_model_edit.setText(provider.default_model or "")
            self.provider_enabled_check.setChecked(provider.enabled)
            self.provider_timeout_spin.setValue(provider.timeout_seconds)
            self.provider_max_retries_spin.setValue(provider.max_retries)
            # Don't show API key for security
            self.provider_api_key_edit.clear()

    def _add_provider(self) -> None:
        """Add a new provider."""
        name = self.provider_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Provider name is required")
            return

        provider = ProviderConfig(
            name=name,
            type=ProviderType(self.provider_type_combo.currentText()),
            base_url=self.provider_base_url_edit.text().strip() or None,
            organization=self.provider_org_edit.text().strip() or None,
            default_model=self.provider_default_model_edit.text().strip() or None,
            enabled=self.provider_enabled_check.isChecked(),
            timeout_seconds=self.provider_timeout_spin.value(),
            max_retries=self.provider_max_retries_spin.value(),
        )

        # Store API key
        api_key = self.provider_api_key_edit.text()
        if api_key:
            provider.set_api_key(api_key)

        self.settings.add_provider(provider)
        self._refresh_providers_list()

    def _remove_provider(self) -> None:
        """Remove selected provider."""
        current = self.providers_list.currentItem()
        if current:
            provider = current.data(Qt.ItemDataRole.UserRole)
            self.settings.remove_provider(provider.name)
            self._refresh_providers_list()

    def _test_provider(self) -> None:
        """Test provider connection."""
        # Would test async connection
        QMessageBox.information(self, "Test", "Provider test not yet implemented.")

    def _test_github(self) -> None:
        """Test GitHub connection."""
        QMessageBox.information(self, "Test", "GitHub test not yet implemented.")

    def _browse_folder(self, line_edit: QLineEdit) -> None:
        """Browse for folder."""
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            line_edit.setText(path)

    def _apply(self) -> None:
        """Apply settings without closing."""
        self._update_settings()
        # Save would be called by parent

    def _update_settings(self) -> None:
        """Update settings object from UI."""
        # General
        self.settings.agent.default_workspace = self.workspace_edit.text() or None
        self.settings.ui.language = self.language_combo.currentText()
        self.settings.logging.level = LogLevel(self.log_level_combo.currentText())

        # Agent
        self.settings.agent.permission_mode = PermissionMode(self.permission_combo.currentText())
        self.settings.agent.max_turns = self.max_turns_spin.value()
        self.settings.agent.max_context_tokens = self.max_tokens_spin.value()
        self.settings.agent.auto_compact_threshold = self.compact_threshold_spin.value()
        self.settings.agent.show_thinking = self.show_thinking_check.isChecked()
        self.settings.agent.stream_tool_calls = self.stream_tools_check.isChecked()

        # UI
        self.settings.ui.theme = ThemeMode(self.theme_combo.currentText())
        self.settings.ui.font_family = self.font_family_edit.text()
        self.settings.ui.font_size = self.font_size_spin.value()
        self.settings.ui.editor_font_size = self.editor_font_size_spin.value()
        self.settings.ui.terminal_font_size = self.terminal_font_size_spin.value()
        self.settings.ui.show_line_numbers = self.line_numbers_check.isChecked()
        self.settings.ui.word_wrap = self.word_wrap_check.isChecked()
        self.settings.ui.minimap = self.minimap_check.isChecked()
        self.settings.ui.compact_mode = self.compact_mode_check.isChecked()

        # Terminal
        self.settings.terminal.shell = self.shell_combo.currentText() or ""
        self.settings.terminal.cursor_blink = self.cursor_blink_check.isChecked()
        self.settings.terminal.cursor_shape = self.cursor_shape_combo.currentText()
        self.settings.terminal.scrollback_lines = self.scrollback_spin.value()
        self.settings.terminal.bell = self.bell_check.isChecked()
        self.settings.terminal.copy_on_select = self.copy_on_select_check.isChecked()

        # GitHub
        token = self.github_token_edit.text()
        if token:
            self.settings.github.set_token(token)
        self.settings.github.default_owner = self.github_owner_edit.text()
        self.settings.github.default_repo = self.github_repo_edit.text()

        # Skills
        self.settings.skills.enabled = self.skills_enabled_check.isChecked()
        self.settings.skills.custom_skills_dir = self.custom_skills_edit.text()
        self.settings.skills.auto_update_builtin = self.auto_update_check.isChecked()

        # Browser
        self.settings.browser.headless = self.browser_headless_check.isChecked()
        self.settings.browser.viewport_width = self.browser_width_spin.value()
        self.settings.browser.viewport_height = self.browser_height_spin.value()

        # Shell
        self.settings.shell.timeout_seconds = self.shell_timeout_spin.value()
        self.settings.shell.max_output_lines = self.shell_max_output_spin.value()

        # Logging
        self.settings.logging.file_enabled = self.log_file_check.isChecked()
        self.settings.logging.file_path = self.log_file_edit.text()
        self.settings.logging.max_file_size_mb = self.log_max_size_spin.value()
        self.settings.logging.max_files = self.log_max_files_spin.value()

    def accept(self) -> None:
        """Accept dialog and save settings."""
        self._update_settings()
        super().accept()
