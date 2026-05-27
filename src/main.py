"""
Video Reup Studio Rebuild — Main Entry Point
PySide6 desktop app for automated video reup workflow.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.main_window import MainWindow
from ui.themes.dark import DARK_THEME
from config.constants import APP_NAME, APP_VERSION


def main():
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply dark theme
    app.setStyleSheet(DARK_THEME)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
