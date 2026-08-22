#!/usr/bin/env python3
"""下片神器 - 入口。"""
import os
import sys


def _bootstrap_dpi() -> None:
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _light_palette():
    """强制浅色调色板，避免系统深色主题下出现白底白字/明暗混杂。"""
    from PySide6.QtGui import QColor, QPalette
    p = QPalette()
    p.setColor(QPalette.Window, QColor(0xF5, 0xF6, 0xF8))
    p.setColor(QPalette.WindowText, QColor(0x22, 0x22, 0x22))
    p.setColor(QPalette.Base, QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.AlternateBase, QColor(0xF7, 0xF8, 0xFA))
    p.setColor(QPalette.ToolTipBase, QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.ToolTipText, QColor(0x22, 0x22, 0x22))
    p.setColor(QPalette.Text, QColor(0x22, 0x22, 0x22))
    p.setColor(QPalette.Button, QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.ButtonText, QColor(0x22, 0x22, 0x22))
    p.setColor(QPalette.BrightText, QColor(0xE2, 0x4B, 0x4A))
    p.setColor(QPalette.Link, QColor(0x1A, 0x6F, 0xB5))
    p.setColor(QPalette.Highlight, QColor(0x3B, 0x82, 0xF6))
    p.setColor(QPalette.HighlightedText, QColor(0xFF, 0xFF, 0xFF))
    p.setColor(QPalette.PlaceholderText, QColor(0x99, 0x99, 0x99))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(0xAA, 0xAA, 0xAA))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(0xAA, 0xAA, 0xAA))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(0xAA, 0xAA, 0xAA))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(0xD5, 0xE4, 0xF7))
    p.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(0x88, 0x88, 0x88))
    return p


def main() -> int:
    _bootstrap_dpi()
    from PySide6.QtWidgets import QApplication
    from xpsq import APP_NAME
    from xpsq.ui.main_window import MainWindow
    from xpsq.ui.panels import BASE_QSS

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setStyleSheet(BASE_QSS)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
