"""
Video Reup Studio Rebuild — Dark Theme (QSS)
Inspired by NAVTools dark theme + Spotify-like aesthetic.
"""

DARK_THEME = """
/* === Global === */
QWidget {
    background-color: #121212;
    color: #f0f0f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #121212;
}

/* === Sidebar === */
#Sidebar {
    background-color: #1a1a1a;
    border-right: 1px solid #2a2a2a;
}

#SidebarTitle {
    color: #1ed760;
    font-size: 18px;
    font-weight: bold;
    padding: 16px;
}

#SidebarVersion {
    color: #646464;
    font-size: 10px;
    padding: 0 16px 16px 16px;
}

/* === Nav Buttons === */
QPushButton#NavButton {
    background: transparent;
    color: #a0a0a0;
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-left: 3px solid transparent;
    font-size: 13px;
}

QPushButton#NavButton:hover {
    background: #222222;
    color: #f0f0f0;
}

QPushButton#NavButton[active="true"] {
    color: #f0f0f0;
    border-left: 3px solid #1ed760;
    font-weight: bold;
}

/* === Content Area === */
#ContentArea {
    background-color: #121212;
}

/* === Cards === */
QFrame#Card {
    background-color: #1a1a1a;
    border-radius: 8px;
    padding: 14px;
}

/* === Section Headers === */
QLabel#SectionHeader {
    color: #1ed760;
    font-size: 16px;
    font-weight: bold;
    padding-bottom: 8px;
}

QLabel#SubHeader {
    color: #f0f0f0;
    font-size: 14px;
    font-weight: bold;
}

/* === Labels === */
QLabel {
    color: #a0a0a0;
    font-size: 12px;
}

QLabel#FieldLabel {
    color: #a0a0a0;
    font-size: 11px;
    padding-bottom: 4px;
}

/* === Buttons === */
QPushButton#PrimaryButton {
    background-color: #1ed760;
    color: #1a1a1a;
    font-weight: bold;
    font-size: 13px;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
}

QPushButton#PrimaryButton:hover {
    background-color: #1fdf64;
}

QPushButton#PrimaryButton:disabled {
    opacity: 0.5;
    background-color: #155d30;
}

QPushButton#SecondaryButton {
    background-color: #282828;
    color: #f0f0f0;
    font-size: 13px;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
}

QPushButton#SecondaryButton:hover {
    background-color: #333333;
}

QPushButton#DangerButton {
    background-color: #e74c3c;
    color: white;
    font-weight: bold;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
}

/* === TextBox / LineEdit === */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #2a2a2a;
    color: #f0f0f0;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 13px;
    selection-background-color: #1ed760;
    selection-color: #1a1a1a;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #1ed760;
}

/* === ComboBox === */
QComboBox {
    background-color: #2a2a2a;
    color: #f0f0f0;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:hover {
    border-color: #1ed760;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #a0a0a0;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #111111;
    border: 1px solid #cccccc;
    selection-background-color: #d0d0d0;
    selection-color: #000000;
    font-size: 13px;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    padding: 6px 8px;
    color: #111111;
    background-color: #ffffff;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #e0e0e0;
    color: #000000;
}

QComboBox QAbstractItemView::item:selected {
    background-color: #c8e6ff;
    color: #000000;
}

/* === CheckBox === */
QCheckBox {
    color: #f0f0f0;
    font-size: 13px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555;
    border-radius: 3px;
    background: #2a2a2a;
}

QCheckBox::indicator:checked {
    background: #1ed760;
    border-color: #1ed760;
}

/* === ProgressBar === */
QProgressBar {
    background-color: #333333;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    font-size: 1px;
}

QProgressBar::chunk {
    background-color: #1ed760;
    border-radius: 3px;
}

/* === ScrollBar === */
QScrollBar:vertical {
    background: #1a1a1a;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #444444;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #555555;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #1a1a1a;
    height: 8px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #444444;
    border-radius: 4px;
    min-width: 30px;
}

/* === Slider === */
QSlider::groove:horizontal {
    background: #333333;
    height: 4px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #1ed760;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::sub-page:horizontal {
    background: #1ed760;
    border-radius: 2px;
}

/* === TabWidget === */
QTabWidget::pane {
    border: none;
    background: #121212;
}

QTabBar::tab {
    background: #1a1a1a;
    color: #a0a0a0;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:selected {
    color: #f0f0f0;
    border-bottom: 2px solid #1ed760;
}

QTabBar::tab:hover {
    color: #f0f0f0;
}

/* === Separator === */
QFrame#Separator {
    background-color: #333333;
    max-height: 1px;
}

/* === Table === */
QTableWidget {
    background-color: #1a1a1a;
    color: #f0f0f0;
    gridline-color: #333333;
    border: none;
    font-size: 12px;
}

QTableWidget::item {
    padding: 6px;
}

QTableWidget::item:selected {
    background-color: #1ed760;
    color: #1a1a1a;
}

QHeaderView::section {
    background-color: #222222;
    color: #a0a0a0;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #333333;
    font-weight: bold;
    font-size: 11px;
}

/* === Tooltip === */
QToolTip {
    background-color: #282828;
    color: #f0f0f0;
    border: 1px solid #444444;
    padding: 4px 8px;
    font-size: 12px;
}

/* === StatusBar === */
#StatusBar {
    background-color: #0f0f0f;
    color: #646464;
    font-size: 11px;
    padding: 4px 12px;
}

/* === Splitter === */
QSplitter::handle {
    background-color: #333333;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}
"""
