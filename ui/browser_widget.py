"""
Browser Widget for WindowsHarness.

WebEngine-based browser for preview and automation.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QProgressBar,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
    QWebEngineView = None

from config.settings import AppSettings


class BrowserWidget(QWidget):
    """Web browser widget for preview and automation."""

    url_changed = pyqtSignal(str)
    load_finished = pyqtSignal(bool)
    console_message = pyqtSignal(str, int, str)  # message, level, source

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)

        self.back_btn = QPushButton("←")
        self.back_btn.setToolTip("Back")
        self.back_btn.clicked.connect(self._go_back)
        toolbar.addWidget(self.back_btn)

        self.forward_btn = QPushButton("→")
        self.forward_btn.setToolTip("Forward")
        self.forward_btn.clicked.connect(self._go_forward)
        toolbar.addWidget(self.forward_btn)

        self.reload_btn = QPushButton("⟳")
        self.reload_btn.setToolTip("Reload")
        self.reload_btn.clicked.connect(self._reload)
        toolbar.addWidget(self.reload_btn)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL...")
        self.url_bar.returnPressed.connect(self._navigate)
        self.url_bar.setFont(QFont(self.settings.ui.font_family, self.settings.ui.font_size))
        toolbar.addWidget(self.url_bar)

        self.go_btn = QPushButton("Go")
        self.go_btn.clicked.connect(self._navigate)
        toolbar.addWidget(self.go_btn)

        layout.addLayout(toolbar)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(2)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Web view
        if HAS_WEBENGINE:
            self.web_view = QWebEngineView()
            self._setup_webengine()
        else:
            from PyQt6.QtWidgets import QLabel
            self.web_view = QLabel("WebEngine not available. Install PyQt6-WebEngine.")
            self.web_view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.web_view)

    def _setup_webengine(self) -> None:
        """Configure WebEngine settings."""
        if not HAS_WEBENGINE:
            return

        # Settings
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

        # Profile
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath("")

        # Page
        self.page = QWebEnginePage(profile, self.web_view)
        self.web_view.setPage(self.page)

        # Connect signals
        self.web_view.urlChanged.connect(self._on_url_changed)
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.loadFinished.connect(self._on_load_finished)

        # Console messages
        self.page.javaScriptConsoleMessage.connect(self._on_console_message)

        # Set user agent
        if self.settings.browser.user_agent:
            profile.setHttpUserAgent(self.settings.browser.user_agent)

        # Load initial page
        self.web_view.setUrl(QUrl("about:blank"))

    def _on_url_changed(self, url: QUrl) -> None:
        """Handle URL change."""
        self.url_bar.setText(url.toString())
        self.url_changed.emit(url.toString())

    def _on_load_progress(self, progress: int) -> None:
        """Handle load progress."""
        self.progress.setValue(progress)
        if progress < 100:
            self.progress.show()
        else:
            QTimer.singleShot(500, self.progress.hide)

    def _on_load_finished(self, ok: bool) -> None:
        """Handle load finished."""
        self.load_finished.emit(ok)
        if not ok:
            self.web_view.setHtml(f"""
                <html><body style="font-family: sans-serif; padding: 20px;">
                <h1>Failed to load page</h1>
                <p>{self.web_view.url().toString()}</p>
                </body></html>
            """)

    def _on_console_message(self, level: int, message: str, line: int, source: str) -> None:
        """Handle JavaScript console messages."""
        level_names = ["Info", "Warning", "Error"]
        level_name = level_names[level] if level < len(level_names) else "Debug"
        self.console_message.emit(message, level, f"{source}:{line}")

    def _navigate(self) -> None:
        """Navigate to URL in address bar."""
        url_text = self.url_bar.text().strip()
        if not url_text:
            return

        # Add scheme if missing
        if not url_text.startswith(("http://", "https://", "file://", "data:")):
            url_text = "https://" + url_text

        self.web_view.setUrl(QUrl(url_text))

    def _go_back(self) -> None:
        """Go back in history."""
        self.web_view.back()

    def _go_forward(self) -> None:
        """Go forward in history."""
        self.web_view.forward()

    def _reload(self) -> None:
        """Reload current page."""
        self.web_view.reload()

    def navigate(self, url: str) -> None:
        """Programmatically navigate to URL."""
        self.url_bar.setText(url)
        self._navigate()

    def run_javascript(self, script: str, callback=None) -> None:
        """Execute JavaScript in the page."""
        if HAS_WEBENGINE:
            self.web_view.page().runJavaScript(script, callback)

    def get_dom(self, callback) -> None:
        """Get page DOM as HTML."""
        if HAS_WEBENGINE:
            self.run_javascript("document.documentElement.outerHTML", callback)

    def screenshot(self, path: str) -> None:
        """Take screenshot of current page."""
        if HAS_WEBENGINE:
            # This would need a QWebEngineView grab
            pass

    def set_zoom(self, factor: float) -> None:
        """Set zoom factor."""
        if HAS_WEBENGINE:
            self.web_view.setZoomFactor(factor)
