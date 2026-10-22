"""
File Editor for WindowsHarness.

Syntax-highlighted code editor with tabs, using QScintilla.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QFileInfo
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTreeView,
    QFileSystemModel,
    QSplitter,
    QToolBar,
    QLineEdit,
    QPushButton,
    QMenu,
    QMessageBox,
    QInputDialog,
)

try:
    from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciLexerCPP, QsciLexerHTML, QsciLexerCSS, QsciLexerJavaScript, QsciLexerJSON, QsciLexerMarkdown, QsciLexerYAML
    HAS_QSCINTILLA = True
except ImportError:
    HAS_QSCINTILLA = False
    QsciScintilla = None

from config.settings import AppSettings


class CodeEditor(QsciScintilla if HAS_QSCINTILLA else object):
    """Syntax-highlighted code editor."""

    def __init__(self, settings: AppSettings, parent=None):
        if HAS_QSCINTILLA:
            super().__init__(parent)
        self.settings = settings
        self.file_path: Optional[Path] = None
        self._setup_editor()

    def _setup_editor(self) -> None:
        if not HAS_QSCINTILLA:
            return

        # Font
        font = QFont(self.settings.ui.font_family, self.settings.ui.editor_font_size)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setMarginsFont(font)

        # Line numbers
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000")
        self.setMarginsBackgroundColor(QColor("#2d2d2d"))
        self.setMarginsForegroundColor(QColor("#888"))

        # Caret line
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))

        # Selection
        self.setSelectionBackgroundColor(QColor("#264f78"))
        self.setSelectionForegroundColor(QColor("#ffffff"))

        # Whitespace
        self.setWhitespaceVisibility(QsciScintilla.WhitespaceVisibility.WsVisible)
        self.setWhitespaceSize(2)

        # Indentation
        self.setIndentationsUseTabs(False)
        self.setIndentationWidth(4)
        self.setTabWidth(4)
        self.setAutoIndent(True)
        self.setIndentationGuides(True)

        # Folding
        self.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
        self.setMarginWidth(2, 12)

        # Brace matching
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        # Colors (dark theme default)
        self._apply_dark_theme()

    def _apply_dark_theme(self) -> None:
        """Apply dark theme colors."""
        if not HAS_QSCINTILLA:
            return

        self.setPaper(QColor("#1e1e1e"))
        self.setColor(QColor("#d4d4d4"))
        self.setMarginsBackgroundColor(QColor("#2d2d2d"))
        self.setMarginsForegroundColor(QColor("#888"))
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))
        self.setSelectionBackgroundColor(QColor("#264f78"))
        self.setFoldMarginColors(QColor("#2d2d2d"), QColor("#1e1e1e"))

    def _apply_light_theme(self) -> None:
        """Apply light theme colors."""
        if not HAS_QSCINTILLA:
            return

        self.setPaper(QColor("#ffffff"))
        self.setColor(QColor("#1e1e1e"))
        self.setMarginsBackgroundColor(QColor("#f3f3f3"))
        self.setMarginsForegroundColor(QColor("#666"))
        self.setCaretLineBackgroundColor(QColor("#e8e8e8"))
        self.setSelectionBackgroundColor(QColor("#add6ff"))

    def set_lexer_for_file(self, path: Path) -> None:
        """Set appropriate lexer based on file extension."""
        if not HAS_QSCINTILLA:
            return

        ext = path.suffix.lower()
        lexer = None

        if ext == ".py":
            lexer = QsciLexerPython(self)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            lexer = QsciLexerJavaScript(self)
        elif ext in (".html", ".htm"):
            lexer = QsciLexerHTML(self)
        elif ext == ".css":
            lexer = QsciLexerCSS(self)
        elif ext in (".cpp", ".cc", ".cxx", ".h", ".hpp"):
            lexer = QsciLexerCPP(self)
        elif ext == ".json":
            lexer = QsciLexerJSON(self)
        elif ext in (".md", ".markdown"):
            lexer = QsciLexerMarkdown(self)
        elif ext in (".yaml", ".yml"):
            lexer = QsciLexerYAML(self)

        if lexer:
            font = QFont(self.settings.ui.font_family, self.settings.ui.editor_font_size)
            font.setFixedPitch(True)
            lexer.setFont(font)
            self.setLexer(lexer)

    def load_file(self, path: Path) -> bool:
        """Load file content."""
        self.file_path = path
        try:
            content = path.read_text(encoding="utf-8")
            self.setText(content)
            self.set_lexer_for_file(path)
            self.setModified(False)
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False

    def save_file(self) -> bool:
        """Save file content."""
        if not self.file_path:
            return False
        try:
            self.file_path.write_text(self.text(), encoding="utf-8")
            self.setModified(False)
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False


class FileEditor(QWidget):
    """File editor with explorer and tabbed editing."""

    file_opened = pyqtSignal(str)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.root_path: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for explorer and editor
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # File explorer
        self.explorer = QTreeView()
        self.explorer.setHeaderHidden(True)
        self.explorer.setAnimated(True)
        self.explorer.setIndentation(16)
        self.explorer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.explorer.customContextMenuRequested.connect(self._show_explorer_context_menu)
        self.explorer.doubleClicked.connect(self._on_explorer_double_click)
        splitter.addWidget(self.explorer)

        # Editor tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.tab_widget)

        # Set splitter sizes (30% explorer, 70% editor)
        splitter.setSizes([300, 700])

        # File system model
        self.fs_model = QFileSystemModel()
        self.fs_model.setReadOnly(False)
        self.explorer.setModel(self.fs_model)

        # Hide columns except name
        for i in range(1, self.fs_model.columnCount()):
            self.explorer.hideColumn(i)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setIconSize(self.style().standardIcon(QApplication.style().StandardPixmap.SP_FileIcon).actualSize(self.size()))

        new_file_btn = QPushButton("New File")
        new_file_btn.clicked.connect(self._new_file)
        toolbar.addWidget(new_file_btn)

        new_folder_btn = QPushButton("New Folder")
        new_folder_btn.clicked.connect(self._new_folder)
        toolbar.addWidget(new_folder_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter files...")
        self.search_box.textChanged.connect(self._filter_files)
        toolbar.addWidget(self.search_box)

        # Add toolbar above explorer
        explorer_widget = QWidget()
        explorer_layout = QVBoxLayout(explorer_widget)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        explorer_layout.addWidget(toolbar)
        explorer_layout.addWidget(self.explorer)

        splitter.replaceWidget(0, explorer_widget)

    def set_root(self, path: Path) -> None:
        """Set the root directory."""
        self.root_path = path
        self.fs_model.setRootPath(str(path))
        self.explorer.setRootIndex(self.fs_model.index(str(path)))

    def _on_explorer_double_click(self, index) -> None:
        """Handle double-click in explorer."""
        path = Path(self.fs_model.filePath(index))
        if path.is_file():
            self._open_file(path)

    def _open_file(self, path: Path) -> None:
        """Open a file in a new tab."""
        # Check if already open
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            if isinstance(editor, CodeEditor) and editor.file_path == path:
                self.tab_widget.setCurrentIndex(i)
                return

        editor = CodeEditor(self.settings)
        if editor.load_file(path):
            self.tab_widget.addTab(editor, path.name)
            self.tab_widget.setCurrentWidget(editor)
            self.file_opened.emit(str(path))
        else:
            editor.deleteLater()

    def _close_tab(self, index: int) -> None:
        """Close a tab."""
        editor = self.tab_widget.widget(index)
        if isinstance(editor, CodeEditor) and editor.isModified():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"Save changes to {editor.file_path.name}?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                editor.save_file()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.tab_widget.removeTab(index)
        editor.deleteLater()

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change."""
        editor = self.tab_widget.currentWidget()
        if isinstance(editor, CodeEditor) and editor.file_path:
            self.file_opened.emit(str(editor.file_path))

    def _show_explorer_context_menu(self, pos) -> None:
        """Show context menu in explorer."""
        index = self.explorer.indexAt(pos)
        menu = QMenu(self)

        if index.isValid():
            path = Path(self.fs_model.filePath(index))
            if path.is_file():
                menu.addAction("Open", lambda: self._open_file(path))
                menu.addSeparator()
            menu.addAction("Delete", lambda: self._delete_path(path))
        else:
            menu.addAction("New File", self._new_file)
            menu.addAction("New Folder", self._new_folder)

        menu.addAction("Refresh", self._refresh)
        menu.exec(self.explorer.viewport().mapToGlobal(pos))

    def _new_file(self) -> None:
        """Create a new file."""
        if not self.root_path:
            return
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            path = self.root_path / name
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                self._open_file(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create file: {e}")

    def _new_folder(self) -> None:
        """Create a new folder."""
        if not self.root_path:
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            path = self.root_path / name
            try:
                path.mkdir(parents=True, exist_ok=True)
                self._refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create folder: {e}")

    def _delete_path(self, path: Path) -> None:
        """Delete a file or folder."""
        reply = QMessageBox.question(
            self, "Delete", f"Delete {path.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if path.is_dir():
                    import shutil
                    shutil.rmtree(path)
                else:
                    path.unlink()
                self._refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete: {e}")

    def _refresh(self) -> None:
        """Refresh file explorer."""
        if self.root_path:
            self.fs_model.setRootPath("")
            self.fs_model.setRootPath(str(self.root_path))
            self.explorer.setRootIndex(self.fs_model.index(str(self.root_path)))

    def _filter_files(self, text: str) -> None:
        """Filter files in explorer."""
        self.fs_model.setNameFilters([f"*{text}*"] if text else [])
        self.fs_model.setNameFilterDisables(not bool(text))


# Import QApplication for style
from PyQt6.QtWidgets import QApplication
