"""视频下载面板 / 文章提取面板。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME
from ..config import load_config, save_config
from ..core.result import TaskResult
from .result_card import ResultCard
from .theme import C
from .workers import ArticleWorker, VideoWorker


def _dir_row(label_text: str, default_dir: str) -> tuple[QHBoxLayout, QLineEdit]:
    lay = QHBoxLayout()
    lab = QLabel(label_text)
    lab.setFixedWidth(70)
    edit = QLineEdit(default_dir)
    btn = QPushButton("浏览")
    def pick():
        d = QFileDialog.getExistingDirectory(None, "选择保存目录", edit.text() or str(Path.home()))
        if d:
            edit.setText(d)
    btn.clicked.connect(pick)
    lay.addWidget(lab)
    lay.addWidget(edit, 1)
    lay.addWidget(btn)
    return lay, edit


class _BasePanel(QWidget):
    mode = "video"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self.worker = None
        self._history: list[TaskResult] = []
        self._build()

    def _build(self) -> None:
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 18)
        self.root.setSpacing(10)

        # 网址行
        url_lay = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴含视频的网页链接，如 https://example.com/video/123")
        self.url_edit.returnPressed.connect(self.start_task)
        b_paste = QPushButton("粘贴")
        b_paste.clicked.connect(self._paste)
        url_lay.addWidget(self.url_edit, 1)
        url_lay.addWidget(b_paste)
        self.root.addLayout(url_lay)

        # 保存目录行
        dl_cfg = self.cfg.get("download", {})
        default_dir = dl_cfg.get("default_dir", str(Path.home() / "Downloads"))
        self.dir_lay, self.dir_edit = _dir_row("保存到", default_dir)
        self.root.addLayout(self.dir_lay)

        # 选项行（子类扩展）
        self.opt_lay = QHBoxLayout()
        self.root.addLayout(self.opt_lay)

        # 按钮行
        btn_lay = QHBoxLayout()
        self.btn_start = QPushButton("开始下载" if self.mode == "video" else "提取文章")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start_task)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_lay.addWidget(self.btn_start)
        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addStretch()
        self.root.addLayout(btn_lay)

        # 进度
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("就绪")
        self.status.setStyleSheet(f"color:{C['muted']};font-size:12px;")
        self.root.addWidget(self.progress)
        self.root.addWidget(self.status)

        # 结果区
        self.result_stack = QStackedWidget()
        self.empty_lab = QLabel("下载结果将显示在这里")
        self.empty_lab.setAlignment(Qt.AlignCenter)
        self.empty_lab.setStyleSheet(f"color:{C['faint']};font-size:13px;padding:30px;")
        self.result_stack.addWidget(self.empty_lab)
        self.result_stack.addWidget(QWidget())  # 占位，卡片直接插入
        self.root.addWidget(self.result_stack, 1)

        # 历史
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(110)
        self.history_list.itemClicked.connect(self._history_clicked)
        self.root.addWidget(self.history_list)

    def _paste(self) -> None:
        from PySide6.QtGui import QGuiApplication
        self.url_edit.setText(QGuiApplication.clipboard().text().strip())

    def start_task(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self.status.setText("请先输入网址")
            return
        if self.worker and self.worker.isRunning():
            return
        save_dir = self.dir_edit.text().strip() or str(Path.home() / "Downloads")
        self._on_start(url, save_dir)

    def _on_start(self, url: str, save_dir: str) -> None:
        self.cfg = load_config()
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("正在启动…")
        self.worker = self._make_worker(url, save_dir)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.start()

    def _make_worker(self, url: str, save_dir: str):  # noqa: ANN201 (subclass)
        raise NotImplementedError

    def _on_progress(self, d: dict) -> None:
        ev = d.get("event")
        if ev == "extracting":
            self.status.setText("正在解析页面，识别内容…" if self.mode == "video" else "正在识别正文…")
            self.progress.setRange(0, 0)
        elif ev == "sniffing":
            self.status.setText(d.get("note", "尝试万能嗅探…"))
        elif ev == "downloading":
            self.progress.setRange(0, 100)
            pct = d.get("percent", 0) or 0
            self.progress.setValue(int(pct))
            sp = d.get("speed") or 0
            speed = f"{sp/1024/1024:.1f} MB/s" if sp else ""
            size = d.get("downloaded", 0) or 0
            note = d.get("note", "")
            self.status.setText(f"下载中 {size/1024/1024:.1f} MB · {speed} {note}".strip())
        elif ev == "fetching":
            self.status.setText("正在抓取网页…")
        elif ev == "images":
            self.status.setText(d.get("note", "正在下载插图…"))
        elif ev == "image_progress":
            self.status.setText(d.get("note", ""))
        elif ev == "writing":
            self.status.setText("正在生成文件…")
        elif ev == "postprocessing":
            self.status.setText("正在合并/转码…")
        elif ev == "finished":
            self.status.setText("下载完成，正在处理…")

    def _on_finished(self, result: TaskResult) -> None:
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if result.status == "success" else 0)
        self._history.insert(0, result)
        self._refresh_history()
        card = ResultCard(result)
        idx = self.result_stack.count() - 1
        old = self.result_stack.widget(idx)
        self.result_stack.removeWidget(old)
        old.deleteLater()
        self.result_stack.insertWidget(idx, card)
        self.result_stack.setCurrentWidget(card)
        self.status.setText("完成" if result.status == "success" else (
            "已取消" if result.status == "cancelled" else f"失败：{result.error_code}"))

    def _cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.status.setText("正在取消…")

    def _refresh_history(self) -> None:
        self.history_list.clear()
        for r in self._history[:20]:
            mark = "✓" if r.status == "success" else "✗"
            item = QListWidgetItem(f"{mark} {r.title or r.url[:40]}")
            item.setToolTip(r.url)
            self.history_list.addItem(item)

    def _history_clicked(self, item: QListWidgetItem) -> None:
        idx = self.history_list.row(item)
        if idx < len(self._history):
            card = ResultCard(self._history[idx])
            pos = self.result_stack.count() - 1
            old = self.result_stack.widget(pos)
            self.result_stack.removeWidget(old)
            old.deleteLater()
            self.result_stack.insertWidget(pos, card)
            self.result_stack.setCurrentWidget(card)


class VideoPanel(_BasePanel):
    mode = "video"

    def _build(self) -> None:
        super()._build()
        self.url_edit.setPlaceholderText("粘贴含视频的网页链接，如 https://example.com/video/123")
        dl = self.cfg.get("download", {})
        self.q_combo = QComboBox()
        self.q_combo.addItems(["最佳画质", "1080p", "720p"])
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["mp4", "mkv", "原始格式"])
        self.sb_check = QCheckBox("跳过赞助段落 (SponsorBlock)")
        self.sub_check = QCheckBox("下载字幕")
        for w in (QLabel("画质"), self.q_combo, QLabel("格式"), self.fmt_combo,
                  self.sb_check, self.sub_check):
            self.opt_lay.addWidget(w)
        self.opt_lay.addStretch()

    def _make_worker(self, url: str, save_dir: str):
        q = self.q_combo.currentIndex()
        quality = ("best", "1080", "720")[q]
        fmt = self.fmt_combo.currentText()
        fmt = "best" if fmt == "原始格式" else fmt
        self.cfg.setdefault("download", {})["default_quality"] = quality
        self.cfg["download"]["default_format"] = fmt
        self.cfg["download"]["sponsorblock"] = self.sb_check.isChecked()
        self.cfg["download"]["subtitles"] = self.sub_check.isChecked()
        save_config(self.cfg)
        return VideoWorker(url, save_dir, self.cfg)


class ArticlePanel(_BasePanel):
    mode = "article"

    def _build(self) -> None:
        super()._build()
        self.url_edit.setPlaceholderText("粘贴文章网页链接，正文和插图都会被提取保存")
        art = self.cfg.get("article", {})
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["HTML（含插图，推荐）", "Markdown", "纯文本"])
        self.img_check = QCheckBox("下载插图")
        self.img_check.setChecked(art.get("download_images", True))
        for w in (QLabel("输出格式"), self.fmt_combo, self.img_check):
            self.opt_lay.addWidget(w)
        self.opt_lay.addStretch()

    def _make_worker(self, url: str, save_dir: str):
        fmt = ("html", "markdown", "txt")[self.fmt_combo.currentIndex()]
        self.cfg.setdefault("article", {})["default_output_format"] = fmt
        self.cfg["article"]["download_images"] = self.img_check.isChecked()
        save_config(self.cfg)
        return ArticleWorker(url, save_dir, self.cfg, fmt)
