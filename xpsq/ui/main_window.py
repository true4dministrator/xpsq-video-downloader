"""主窗口：左侧栏双模式切换 + 设置。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, APP_VERSION
from .panels import ArticlePanel, VideoPanel
from .settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(880, 620)
        self.setMinimumSize(720, 520)
        self._build()

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # 左侧栏
        sidebar = QWidget()
        sidebar.setFixedWidth(140)
        sidebar.setStyleSheet(
            "QWidget#sidebar{background:#f5f7fa;border-radius:12px;}"
            "QListWidget{border:none;background:transparent;font-size:13px;outline:0;}"
            "QListWidget::item{padding:10px 12px;border-radius:8px;margin:2px 6px;}"
            "QListWidget::item:selected{background:#e2ebfd;color:#1d4ed8;font-weight:600;}"
            "QListWidget::item:hover{background:#eef1f5;}")
        sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 12, 0, 12)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size:16px;font-weight:700;padding:4px 16px 12px;color:#1d2b3a;")
        sl.addWidget(title)

        self.nav = QListWidget()
        self.nav.addItem(QListWidgetItem("视频下载"))
        self.nav.addItem(QListWidgetItem("文章提取"))
        self.nav.addItem(QListWidgetItem("设置"))
        self.nav.setCurrentRow(0)
        sl.addWidget(self.nav, 1)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet("color:#bbb;font-size:11px;padding:4px 16px;")
        sl.addWidget(ver)

        lay.addWidget(sidebar)

        # 主区域
        self.stack = QStackedWidget()
        self.video_panel = VideoPanel()
        self.article_panel = ArticlePanel()
        self.settings_page = SettingsPage()
        for p in (self.video_panel, self.article_panel, self.settings_page):
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings_page.save()
        super().closeEvent(event)
