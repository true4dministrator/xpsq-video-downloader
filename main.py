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


def main() -> int:
    _bootstrap_dpi()
    from PySide6.QtWidgets import QApplication
    from xpsq import APP_NAME
    from xpsq.ui.main_window import MainWindow
    from xpsq.ui.panels import BASE_QSS

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(BASE_QSS)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
