"""
Video Reup Studio Rebuild — Main Window
Sidebar navigation + stacked pages layout (learned from NAVTools).
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from config.constants import (
    APP_NAME, APP_VERSION, SIDEBAR_WIDTH,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
)


class MainWindow(QMainWindow):
    """Main application window with sidebar + page stack."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(1400, 850)

        # Init state
        self._nav_buttons = []
        self._pages = {}

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        self._sidebar = self._create_sidebar()
        layout.addWidget(self._sidebar)

        # Page stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentArea")
        layout.addWidget(self._stack)

        # Create pages (lazy-loaded pattern)
        self._pages = {}
        self._nav_buttons = []
        self._create_pages()

        # Navigate to first page
        self._navigate("source")

    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title
        title = QLabel(APP_NAME)
        title.setObjectName("SidebarTitle")
        layout.addWidget(title)

        version = QLabel(f"v{APP_VERSION} — PySide6 Rebuild")
        version.setObjectName("SidebarVersion")
        layout.addWidget(version)

        # Navigation buttons — Main workflow (simplified, 1 flow)
        nav_items = [
            ("download", "📥  Download"),
            ("source", "📥  Source"),
            ("script", "📝  Script"),
            ("voice", "🎙  Voice"),
            ("visuals", "🖼  Visuals"),
            ("compose", "🎬  Compose"),
            ("export", "📤  Export"),
        ]

        for page_id, label in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("page_id", page_id)
            btn.clicked.connect(lambda checked, pid=page_id: self._navigate(pid))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Separator — Tools
        sep1 = QFrame()
        sep1.setObjectName("Separator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFixedHeight(1)
        layout.addWidget(sep1)

        tools_label = QLabel("  TOOLS")
        tools_label.setStyleSheet("color: #646464; font-size: 10px; font-weight: bold; padding: 6px 0 2px 0;")
        layout.addWidget(tools_label)

        # Utility pages
        tool_items = [
            ("quick_edit", "⚡  Quick Edit"),
            ("watermark", "🧹  Watermark"),
            ("upscale", "🔍  Upscale"),
            ("bg_remove", "🖼  BG Remove"),
            ("batch_resize", "📐  Resize"),
            ("thumbnail", "📸  Thumbnail"),
        ]

        for page_id, label in tool_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("page_id", page_id)
            btn.clicked.connect(lambda checked, pid=page_id: self._navigate(pid))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        # Separator — Settings
        sep2 = QFrame()
        sep2.setObjectName("Separator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # Settings button
        btn_settings = QPushButton("⚙  Settings")
        btn_settings.setObjectName("NavButton")
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.setProperty("page_id", "settings")
        btn_settings.clicked.connect(lambda: self._navigate("settings"))
        layout.addWidget(btn_settings)
        self._nav_buttons.append(btn_settings)

        # Spacer
        layout.addStretch()

        # Status bar at bottom
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("StatusBar")
        layout.addWidget(self._status_label)

        return sidebar

    def _create_pages(self):
        """Create all pages and add to stack."""
        from ui.pages.batch_download_page import BatchDownloadPage
        from ui.pages.source_page import SourcePage
        from ui.pages.script_page import ScriptPage
        from ui.pages.voice_page import VoicePage
        from ui.pages.visuals_page import VisualsPage
        from ui.pages.compose_page import ComposePage
        from ui.pages.export_page import ExportPage
        from ui.pages.settings_page import SettingsPage
        from ui.pages.watermark_page import WatermarkPage
        from ui.pages.upscale_page import UpscalePage
        from ui.pages.bg_remove_page import BgRemovePage
        from ui.pages.batch_resize_page import BatchResizePage
        from ui.pages.thumbnail_page import ThumbnailProPage
        from ui.pages.batch_quick_edit_page import BatchQuickEditPage

        pages = [
            ("download", BatchDownloadPage(self)),
            ("source", SourcePage(self)),
            ("script", ScriptPage(self)),
            ("voice", VoicePage(self)),
            ("visuals", VisualsPage(self)),
            ("compose", ComposePage(self)),
            ("export", ExportPage(self)),
            ("settings", SettingsPage(self)),
            ("watermark", WatermarkPage(self)),
            ("upscale", UpscalePage(self)),
            ("bg_remove", BgRemovePage(self)),
            ("batch_resize", BatchResizePage(self)),
            ("thumbnail", ThumbnailProPage(self)),
            ("quick_edit", BatchQuickEditPage(self)),
        ]

        for page_id, page_widget in pages:
            self._pages[page_id] = page_widget
            self._stack.addWidget(page_widget)

    def _navigate(self, page_id: str):
        """Navigate to a page by ID."""
        if page_id not in self._pages:
            return

        # Update stack
        self._stack.setCurrentWidget(self._pages[page_id])

        # Update nav button states
        for btn in self._nav_buttons:
            is_active = btn.property("page_id") == page_id
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Save last page
        from config.settings import get_settings
        get_settings().set("last_page", page_id)

    def set_status(self, text: str):
        """Update status bar text."""
        self._status_label.setText(text)

    def get_page(self, page_id: str):
        """Get a page widget by ID."""
        return self._pages.get(page_id)
