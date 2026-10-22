#!/usr/bin/env python3
"""
WindowsHarness - AI Coding Agent for Windows.

Main entry point.
"""

import sys
import asyncio
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import qasync

from config.settings import get_settings, get_settings_manager
from ui.main_window import MainWindow


def setup_asyncio() -> None:
    """Setup asyncio event loop for Windows."""
    if sys.platform == "win32":
        # Use ProactorEventLoop for subprocess support on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def main() -> int:
    """Main entry point."""
    setup_asyncio()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("WindowsHarness")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("WindowsHarness")

    # Load settings
    settings_manager = get_settings_manager()
    settings = settings_manager.settings

    # Create main window
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow(settings)
    window.show()

    # Handle signals
    def signal_handler():
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Run event loop
    with loop:
        return loop.run_forever()


if __name__ == "__main__":
    sys.exit(main())
