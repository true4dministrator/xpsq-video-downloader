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
    from xpsq.config import load_config
    from xpsq.ui.main_window import MainWindow
    from xpsq.ui.theme import apply_theme

    cfg = load_config()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app, cfg.get("general", {}).get("theme", "system"))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
