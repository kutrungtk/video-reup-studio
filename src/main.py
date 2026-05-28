"""
Video Reup Studio Rebuild — Main Entry Point
PySide6 desktop app for automated video reup workflow.
"""

import sys
import os

# Force UTF-8 encoding on Windows (prevents cp1252 crashes with Unicode filenames)
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

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
