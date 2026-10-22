"""
Main Window for WindowsHarness.

PyQt6-based main application window with chat, file editor, terminal, and browser panels.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTabWidget,
    QToolBar,
    QStatusBar,
    QMenuBar,
    QMenu,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QDockWidget,
)

from ui.chat_panel import ChatPanel
from ui.file_editor import FileEditor
from ui.terminal_widget import TerminalWidget
from ui.browser_widget import BrowserWidget
from ui.settings_dialog import SettingsDialog
from config.settings import get_settings, save_settings, AppSettings


class MainWindow(QMainWindow):
    """Main application window."""

    # Signals
    run_agent_requested = pyqtSignal(str)  # user message
    workspace_changed = pyqtSignal(str)  # workspace path

    def __init__(self, settings: Optional[AppSettings] = None):
        super().__init__()
        self.settings = settings or get_settings()
        self.setWindowTitle("WindowsHarness - AI Coding Agent")
        self.resize(1600, 1000)

        # Apply theme
        self._apply_theme()

        # Setup UI
        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_dock_widgets()
        self._setup_status_bar()
        self._setup_shortcuts()

        # Load workspace
        self._load_workspace()

    def _apply_theme(self) -> None:
        """Apply the current theme."""
        theme = self.settings.ui.theme
        if theme.value == "dark":
            self._apply_dark_theme()
        elif theme.value == "light":
            self._apply_light_theme()
        # System theme uses default

    def _apply_dark_theme(self) -> None:
        """Apply dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QMenuBar {
                background-color: #2d2d2d;
                color: #d4d4d4;
            }
            QMenuBar::item:selected {
                background-color: #094771;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: none;
                spacing: 4px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
            QSplitter::handle {
                background-color: #3c3c3c;
            }
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 8px 16px;
                border: 1px solid #3c3c3c;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-bottom: 1px solid #1e1e1e;
            }
            QTabBar::tab:hover {
                background-color: #3c3c3c;
            }
            QDockWidget {
                titlebar-close-icon: url(close.png);
                titlebar-normal-icon: url(undock.png);
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 4px;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #3c3c3c;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4c4c4c;
            }
        """)

    def _apply_light_theme(self) -> None:
        """Apply light theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #ffffff;
                color: #1e1e1e;
            }
            QMenuBar {
                background-color: #f3f3f3;
                color: #1e1e1e;
            }
            QMenuBar::item:selected {
                background-color: #094771;
                color: white;
            }
            QMenu {
                background-color: #ffffff;
                color: #1e1e1e;
                border: 1px solid #cccccc;
            }
            QMenu::item:selected {
                background-color: #094771;
                color: white;
            }
            QToolBar {
                background-color: #f3f3f3;
                border: none;
                spacing: 4px;
            }
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
            }
            QToolButton:pressed {
                background-color: #094771;
                color: white;
            }
            QStatusBar {
                background-color: #007acc;
                color: white;
            }
            QSplitter::handle {
                background-color: #cccccc;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: #ffffff;
            }
            QTabBar::tab {
                background-color: #f3f3f3;
                color: #1e1e1e;
                padding: 8px 16px;
                border: 1px solid #cccccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                border-bottom: 1px solid #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #e0e0e0;
            }
        """)

    def _setup_menu_bar(self) -> None:
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self._create_action("New Workspace", "Ctrl+N", self._new_workspace))
        file_menu.addAction(self._create_action("Open Workspace...", "Ctrl+O", self._open_workspace))
        file_menu.addSeparator()
        file_menu.addAction(self._create_action("Settings...", "Ctrl+,", self._show_settings))
        file_menu.addSeparator()
        file_menu.addAction(self._create_action("Exit", "Ctrl+Q", self.close))

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self._create_action("Undo", "Ctrl+Z", lambda: self._active_editor().undo() if self._active_editor() else None))
        edit_menu.addAction(self._create_action("Redo", "Ctrl+Y", lambda: self._active_editor().redo() if self._active_editor() else None))
        edit_menu.addSeparator()
        edit_menu.addAction(self._create_action("Cut", "Ctrl+X", lambda: self._active_editor().cut() if self._active_editor() else None))
        edit_menu.addAction(self._create_action("Copy", "Ctrl+C", lambda: self._active_editor().copy() if self._active_editor() else None))
        edit_menu.addAction(self._create_action("Paste", "Ctrl+V", lambda: self._active_editor().paste() if self._active_editor() else None))

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._create_action("Toggle Chat", "Ctrl+1", lambda: self._toggle_dock(self.chat_dock)))
        view_menu.addAction(self._create_action("Toggle Files", "Ctrl+2", lambda: self._toggle_dock(self.files_dock)))
        view_menu.addAction(self._create_action("Toggle Terminal", "Ctrl+3", lambda: self._toggle_dock(self.terminal_dock)))
        view_menu.addAction(self._create_action("Toggle Browser", "Ctrl+4", lambda: self._toggle_dock(self.browser_dock)))
        view_menu.addSeparator()
        view_menu.addAction(self._create_action("Toggle Theme", "Ctrl+T", self._toggle_theme))

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self._create_action("Run Doctor", "F1", self._run_doctor))
        tools_menu.addAction(self._create_action("Open Shell", "`", self._focus_terminal))

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._create_action("Documentation", "F1", self._show_docs))
        help_menu.addAction(self._create_action("About", "", self._show_about))

    def _create_action(self, text: str, shortcut: str, slot) -> QAction:
        """Create a QAction with text and shortcut."""
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _setup_tool_bar(self) -> None:
        """Create main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(self.style().standardIcon(QApplication.style().StandardPixmap.SP_FileIcon).actualSize(self.size()))
        self.addToolBar(toolbar)

        # Workspace selector
        self.workspace_combo = QComboBox()
        self.workspace_combo.setMinimumWidth(200)
        self.workspace_combo.currentTextChanged.connect(self._on_workspace_changed)
        toolbar.addWidget(self.workspace_combo)

        toolbar.addSeparator()

        # Agent controls
        self.run_action = self._create_action("Run Agent", "Ctrl+R", self._run_agent)
        self.run_action.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaPlay))
        toolbar.addAction(self.run_action)

        self.stop_action = self._create_action("Stop", "Ctrl+Shift+R", self._stop_agent)
        self.stop_action.setIcon(self.style().standardIcon(QApplication.style().StandardPixmap.SP_MediaStop))
        self.stop_action.setEnabled(False)
        toolbar.addAction(self.stop_action)

        toolbar.addSeparator()

        # Provider selector
        from PyQt6.QtWidgets import QComboBox
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumWidth(150)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        toolbar.addWidget(self.provider_combo)

        # Model selector
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        toolbar.addWidget(self.model_combo)

    def _setup_central_widget(self) -> None:
        """Create central widget with chat panel."""
        self.chat_panel = ChatPanel(self.settings)
        self.chat_panel.send_message.connect(self.run_agent_requested.emit)
        self.setCentralWidget(self.chat_panel)

    def _setup_dock_widgets(self) -> None:
        """Create dockable panels."""
        # Files panel
        self.files_dock = QDockWidget("Files", self)
        self.files_dock.setObjectName("files_dock")
        self.file_editor = FileEditor(self.settings)
        self.file_editor.file_opened.connect(self._on_file_opened)
        self.files_dock.setWidget(self.file_editor)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.files_dock)

        # Terminal panel
        self.terminal_dock = QDockWidget("Terminal", self)
        self.terminal_dock.setObjectName("terminal_dock")
        self.terminal_widget = TerminalWidget(self.settings)
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock)

        # Browser panel
        self.browser_dock = QDockWidget("Browser", self)
        self.browser_dock.setObjectName("browser_dock")
        self.browser_widget = BrowserWidget(self.settings)
        self.browser_dock.setWidget(self.browser_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.browser_dock)

        # Tabify terminal and browser
        self.tabifyDockWidget(self.terminal_dock, self.browser_dock)
        self.terminal_dock.raise_()

    def _setup_status_bar(self) -> None:
        """Create status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        self.token_label = QLabel("Tokens: 0/128k")
        self.status_bar.addPermanentWidget(self.token_label)

        self.provider_label = QLabel("No provider")
        self.status_bar.addPermanentWidget(self.provider_label)

    def _setup_shortcuts(self) -> None:
        """Setup global shortcuts."""
        # Ctrl+Shift+P: Command palette (future)
        # Ctrl+`: Focus terminal
        pass

    def _load_workspace(self) -> None:
        """Load the default workspace."""
        workspace = self.settings.agent.default_workspace or str(Path.cwd())
        self._set_workspace(workspace)

    def _set_workspace(self, path: str) -> None:
        """Set the current workspace."""
        path_obj = Path(path).resolve()
        if path_obj.exists() and path_obj.is_dir():
            self.file_editor.set_root(path_obj)
            self.workspace_combo.setCurrentText(str(path_obj))
            self.workspace_changed.emit(str(path_obj))
            self.status_label.setText(f"Workspace: {path_obj}")

    def _on_workspace_changed(self, path: str) -> None:
        self._set_workspace(path)

    def _on_provider_changed(self, provider_name: str) -> None:
        """Handle provider selection change."""
        # Update model combo
        self.model_combo.clear()
        # Would populate from provider's models
        self.provider_label.setText(f"Provider: {provider_name}")

    def _on_file_opened(self, path: str) -> None:
        """Handle file opened in editor."""
        self.status_label.setText(f"Editing: {path}")

    def _active_editor(self) -> Optional[FileEditor]:
        """Get the currently active editor widget."""
        return self.file_editor

    def _new_workspace(self) -> None:
        """Create new workspace."""
        path = QFileDialog.getExistingDirectory(self, "Select Workspace Directory")
        if path:
            self._set_workspace(path)

    def _open_workspace(self) -> None:
        """Open existing workspace."""
        self._new_workspace()

    def _show_settings(self) -> None:
        """Show settings dialog."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            save_settings()
            self._apply_theme()
            self.chat_panel.update_settings(self.settings)

    def _toggle_dock(self, dock: QDockWidget) -> None:
        """Toggle dock widget visibility."""
        dock.setVisible(not dock.isVisible())

    def _toggle_theme(self) -> None:
        """Toggle between light/dark theme."""
        current = self.settings.ui.theme
        if current.value == "dark":
            self.settings.ui.theme = self.settings.ui.theme.LIGHT
        else:
            self.settings.ui.theme = self.settings.ui.theme.DARK
        save_settings()
        self._apply_theme()

    def _run_agent(self) -> None:
        """Trigger agent run from chat input."""
        self.chat_panel.focus_input()

    def _stop_agent(self) -> None:
        """Stop current agent run."""
        # Would connect to agent engine
        pass

    def _run_doctor(self) -> None:
        """Run environment diagnostics."""
        QMessageBox.information(self, "Doctor", "Doctor functionality not yet implemented.")

    def _focus_terminal(self) -> None:
        """Focus terminal input."""
        self.terminal_dock.setVisible(True)
        self.terminal_dock.raise_()
        self.terminal_widget.focus_input()

    def _show_docs(self) -> None:
        """Show documentation."""
        QMessageBox.information(self, "Documentation", "Documentation not yet available.")

    def _show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(self, "About WindowsHarness",
            "WindowsHarness - AI Coding Agent for Windows\n\n"
            "A native port of AndroidHarness to Windows using Python/PyQt6.\n\n"
            "Version 0.1.0 (Alpha)")

    def closeEvent(self, event) -> None:
        """Handle window close."""
        save_settings()
        event.accept()


# Import QLabel and QComboBox
from PyQt6.QtWidgets import QLabel, QComboBox
