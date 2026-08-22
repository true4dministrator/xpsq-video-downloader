"""主题模块：浅色/深色调色板 + 全局 QSS 生成 + 系统主题检测。

全局变量 C 保存当前主题色板，各界面组件在构建时读取，保证深浅色下样式一致。
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette

LIGHT_COLORS = {
    "bg": "#f5f6f8",
    "sidebar_bg": "#f5f7fa",
    "card": "#ffffff",
    "metric_bg": "#f4f6f8",
    "text": "#222222",
    "muted": "#666666",
    "faint": "#999999",
    "disabled_text": "#aaaaaa",
    "border": "#d5d9dd",
    "border_soft": "#e3e6e8",
    "input_bg": "#ffffff",
    "hover": "#f2f5f8",
    "pressed": "#e9edf2",
    "accent": "#3b82f6",
    "accent_hover": "#2f6fe0",
    "accent_text": "#ffffff",
    "selected_bg": "#e2ebfd",
    "selected_text": "#1d4ed8",
    "success": "#2e8b57",
    "danger": "#c0392b",
    "danger_bg": "#fdf3f2",
    "warn_bg": "#fdf6e3",
    "warn_text": "#8a6d3b",
    "scroll_handle": "#c9ced4",
    "scroll_handle_hover": "#b3bac2",
    "sidebar_title": "#1d2b3a",
}

DARK_COLORS = {
    "bg": "#1e2227",
    "sidebar_bg": "#1b1f24",
    "card": "#262b31",
    "metric_bg": "#2b3138",
    "text": "#e6e8ea",
    "muted": "#9aa3ad",
    "faint": "#6b737c",
    "disabled_text": "#5c646d",
    "border": "#3a4047",
    "border_soft": "#33383f",
    "input_bg": "#2b3138",
    "hover": "#2f363d",
    "pressed": "#353c44",
    "accent": "#4d94f5",
    "accent_hover": "#6aa7f7",
    "accent_text": "#ffffff",
    "selected_bg": "#24406b",
    "selected_text": "#8ab4ff",
    "success": "#3fb68b",
    "danger": "#e5534b",
    "danger_bg": "#3a2422",
    "warn_bg": "#3a3120",
    "warn_text": "#e8c766",
    "scroll_handle": "#454c54",
    "scroll_handle_hover": "#565f68",
    "sidebar_title": "#e6e8ea",
}

C: dict = dict(LIGHT_COLORS)  # 当前生效色板（独立副本，apply_theme 时原地更新）


def build_palette(dark: bool) -> QPalette:
    if dark:
        return _palette(
            window=QColor(0x1E, 0x22, 0x27), window_text=QColor(0xE6, 0xE8, 0xEA),
            base=QColor(0x2B, 0x31, 0x38), alt=QColor(0x24, 0x29, 0x2F),
            text=QColor(0xE6, 0xE8, 0xEA), button=QColor(0x2B, 0x31, 0x38),
            button_text=QColor(0xE6, 0xE8, 0xEA), highlight=QColor(0x4D, 0x94, 0xF5),
            highlighted_text=QColor(0xFF, 0xFF, 0xFF), disabled=QColor(0x5C, 0x64, 0x6D))
    return _palette(
        window=QColor(0xF5, 0xF6, 0xF8), window_text=QColor(0x22, 0x22, 0x22),
        base=QColor(0xFF, 0xFF, 0xFF), alt=QColor(0xF7, 0xF8, 0xFA),
        text=QColor(0x22, 0x22, 0x22), button=QColor(0xFF, 0xFF, 0xFF),
        button_text=QColor(0x22, 0x22, 0x22), highlight=QColor(0x3B, 0x82, 0xF6),
        highlighted_text=QColor(0xFF, 0xFF, 0xFF), disabled=QColor(0xAA, 0xAA, 0xAA))


def _palette(window, window_text, base, alt, text, button, button_text,
             highlight, highlighted_text, disabled) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, window)
    p.setColor(QPalette.WindowText, window_text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, alt)
    p.setColor(QPalette.ToolTipBase, base)
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, button)
    p.setColor(QPalette.ButtonText, button_text)
    p.setColor(QPalette.BrightText, QColor(0xE2, 0x4B, 0x4A))
    p.setColor(QPalette.Link, QColor(0x4D, 0x94, 0xF5) if window.lightness() < 128 else QColor(0x1A, 0x6F, 0xB5))
    p.setColor(QPalette.Highlight, highlight)
    p.setColor(QPalette.HighlightedText, highlighted_text)
    p.setColor(QPalette.PlaceholderText, QColor(0x99, 0x99, 0x99))
    p.setColor(QPalette.Disabled, QPalette.Text, disabled)
    p.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    p.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(0x4A, 0x55, 0x62))
    p.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled)
    return p


def build_qss(c: dict) -> str:
    return f"""
* {{ font-family: "Microsoft YaHei UI","Microsoft YaHei","Segoe UI",sans-serif; font-size: 13px; }}
QMainWindow, QWidget {{ background: {c['bg']}; color: {c['text']}; }}
QLabel {{ color: {c['text']}; background: transparent; }}
QLineEdit, QComboBox, QSpinBox {{
  padding: 6px 10px; border: 1px solid {c['border']}; border-radius: 8px;
  background: {c['input_bg']}; color: {c['text']}; selection-background-color: {c['accent']};
  selection-color: {c['accent_text']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c['accent']}; }}
QLineEdit:disabled {{ background: {c['hover']}; color: {c['disabled_text']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
  width: 0; height: 0; border-left: 4px solid transparent;
  border-right: 4px solid transparent; border-top: 5px solid {c['muted']}; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
  background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']};
  selection-background-color: {c['selected_bg']}; selection-color: {c['selected_text']}; outline: 0;
}}
QSpinBox::up-button, QSpinBox::down-button {{ background: {c['input_bg']}; border: none; width: 18px; }}
QSpinBox::up-arrow {{ width: 0; height: 0; border-left: 4px solid transparent;
  border-right: 4px solid transparent; border-bottom: 5px solid {c['muted']}; }}
QSpinBox::down-arrow {{ width: 0; height: 0; border-left: 4px solid transparent;
  border-right: 4px solid transparent; border-top: 5px solid {c['muted']}; }}
QPushButton {{
  padding: 7px 16px; border: 1px solid {c['border']}; border-radius: 8px;
  background: {c['card']}; color: {c['text']};
}}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
QPushButton:pressed {{ background: {c['pressed']}; }}
QPushButton:disabled {{ color: {c['disabled_text']}; background: {c['hover']}; border-color: {c['border_soft']}; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['accent_text']}; border: none; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {c['border']}; color: {c['disabled_text']}; }}
QProgressBar {{
  border: 1px solid {c['border']}; border-radius: 8px; height: 14px;
  background: {c['hover']}; color: {c['text']}; text-align: center; font-size: 10px;
}}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 7px; }}
QCheckBox {{ color: {c['text']}; spacing: 6px; background: transparent; }}
QCheckBox::indicator {{
  width: 16px; height: 16px; border: 1px solid {c['border']};
  border-radius: 4px; background: {c['input_bg']};
}}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QListWidget {{
  background: {c['card']}; border: 1px solid {c['border_soft']}; border-radius: 10px;
  color: {c['text']}; outline: 0;
}}
QListWidget::item {{ padding: 6px 10px; border-radius: 6px; color: {c['text']}; }}
QListWidget::item:selected {{ background: {c['selected_bg']}; color: {c['selected_text']}; }}
QListWidget::item:hover {{ background: {c['hover']}; }}
QGroupBox {{
  color: {c['muted']}; font-size: 12px; border: 1px solid {c['border_soft']};
  border-radius: 8px; margin-top: 10px; padding-top: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QScrollBar:vertical {{ background: {c['bg']}; width: 10px; border-radius: 5px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['scroll_handle']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scroll_handle_hover']}; }}
QScrollBar:horizontal {{ background: {c['bg']}; height: 10px; border-radius: 5px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {c['scroll_handle']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px 8px; border-radius: 6px; }}
QMessageBox {{ background: {c['bg']}; }}
QMenu {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QMenu::item {{ padding: 6px 18px; }}
QMenu::item:selected {{ background: {c['selected_bg']}; color: {c['selected_text']}; }}
"""


def system_dark() -> bool:
    """Windows: 读取注册表应用浅色模式开关；其他平台默认浅色。"""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return val == 0
        except Exception:
            return False
    return False


def resolve_dark(theme: str) -> bool:
    if theme == "dark":
        return True
    if theme == "light":
        return False
    return system_dark()


def apply_theme(app, theme: str) -> None:
    global C
    dark = resolve_dark(theme)
    # 原地更新 C，而不是重新绑定：所有 `from .theme import C` 的模块引用都会同步看到新值
    new_colors = DARK_COLORS if dark else LIGHT_COLORS
    C.clear()
    C.update(new_colors)
    app.setStyle("Fusion")
    app.setPalette(build_palette(dark))
    app.setStyleSheet(build_qss(C))
