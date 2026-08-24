"""主窗口：左侧栏双模式切换 + 设置。"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, APP_VERSION
from ..core.ffmpeg import check_ffmpeg, find_ffmpeg
from ..logging_setup import LOGS_DIR
from .panels import ArticlePanel, MusicPanel, VideoPanel
from .settings_page import SettingsPage
from .tasks_view import TasksView
from .theme import C


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(980, 640)
        self.setMinimumSize(640, 460)
        self._startup_selfcheck()
        self._build()

    def _startup_selfcheck(self) -> None:
        """启动自检：ffmpeg 探测结果写入日志，便于排查。"""
        try:
            ok, info = check_ffmpeg()
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOGS_DIR / "startup.log", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat(timespec='seconds')}] "
                        f"ffmpeg={'OK' if ok else 'MISSING'} path={find_ffmpeg()} info={info}\n")
        except Exception:
            pass

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # 左侧栏
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(140)
        self.sidebar.setObjectName("sidebar")
        self._style_sidebar()
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(0, 12, 0, 12)

        title = QLabel(APP_NAME)
        title.setStyleSheet(f"font-size:16px;font-weight:700;padding:4px 16px 12px;color:{C['sidebar_title']};")
        sl.addWidget(title)

        self.nav = QListWidget()
        self.nav.addItem(QListWidgetItem("视频下载"))
        self.nav.addItem(QListWidgetItem("音乐下载"))
        self.nav.addItem(QListWidgetItem("文章提取"))
        self.nav.addItem(QListWidgetItem("设置"))
        self.nav.setCurrentRow(0)
        sl.addWidget(self.nav, 1)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet(f"color:{C['faint']};font-size:11px;padding:4px 16px;")
        sl.addWidget(ver)

        lay.addWidget(self.sidebar)

        # 主区域
        self.stack = QStackedWidget()
        self.video_panel = VideoPanel()
        self.music_panel = MusicPanel()
        self.article_panel = ArticlePanel()
        self.settings_page = SettingsPage()
        for p in (self.video_panel, self.music_panel, self.article_panel, self.settings_page):
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)

        # 右侧任务栏（常驻）
        self.tasks_view = TasksView()
        self.tasks_view.setFixedWidth(260)
        lay.addWidget(self.tasks_view)

        self.nav.currentRowChanged.connect(lambda i: self.stack.setCurrentIndex(i))

    def _style_sidebar(self) -> None:
        """按当前主题色板刷新侧栏样式（切换主题时调用）。"""
        self.sidebar.setStyleSheet(
            f"QWidget#sidebar{{background:{C['sidebar_bg']};border-radius:12px;}}"
            "QListWidget{border:none;background:transparent;font-size:13px;outline:0;}"
            "QListWidget::item{padding:10px 12px;border-radius:8px;margin:2px 6px;}"
            f"QListWidget::item:selected{{background:{C['selected_bg']};color:{C['selected_text']};font-weight:600;}}"
            f"QListWidget::item:hover{{background:{C['hover']};}}")

    def rebuild_theme(self) -> None:
        """主题切换后重建主界面，保留输入框内容与当前页面。"""
        idx = self.nav.currentRow()
        saved = {
            "video": (self.video_panel.url_edit.text(), self.video_panel.dir_edit.text()),
            "music": (self.music_panel.url_edit.text(), self.music_panel.dir_edit.text()),
            "article": (self.article_panel.url_edit.text(), self.article_panel.dir_edit.text()),
        }
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.video_panel = VideoPanel()
        self.music_panel = MusicPanel()
        self.article_panel = ArticlePanel()
        self.settings_page = SettingsPage()
        for p in (self.video_panel, self.music_panel, self.article_panel, self.settings_page):
            self.stack.addWidget(p)
        self.video_panel.url_edit.setText(saved["video"][0])
        self.video_panel.dir_edit.setText(saved["video"][1])
        self.music_panel.url_edit.setText(saved["music"][0])
        self.music_panel.dir_edit.setText(saved["music"][1])
        self.article_panel.url_edit.setText(saved["article"][0])
        self.article_panel.dir_edit.setText(saved["article"][1])
        self._style_sidebar()
        if 0 <= idx < self.stack.count():
            self.stack.setCurrentIndex(idx)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.settings_page.save(rebuild=False)
        except Exception:
            pass
        super().closeEvent(event)
