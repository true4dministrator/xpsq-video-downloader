"""结果卡片：成功/失败两种形态，用户层 + 开发者层信息。"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ..core.result import TaskResult
from ..errors import ERR_IMG_PARTIAL
from ..logging_setup import open_log_dir
from .theme import C


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _metric(parent: QWidget, label: str, value: str) -> QWidget:
    box = QFrame(parent)
    box.setStyleSheet(
        f"QFrame{{background:{C['metric_bg']};border-radius:8px;}}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(12, 8, 12, 8)
    lab = QLabel(label)
    lab.setStyleSheet(f"color:{C['muted']};font-size:11px;")
    val = QLabel(value or "-")
    val.setStyleSheet(f"font-size:16px;font-weight:600;color:{C['text']};")
    lay.addWidget(lab)
    lay.addWidget(val)
    return box


class ResultCard(QFrame):
    def __init__(self, result: TaskResult, parent=None):
        super().__init__(parent)
        self.result = result
        self.setStyleSheet(
            f"QFrame{{border:1px solid {C['border_soft']};border-radius:12px;background:{C['card']};}}"
            "QLabel{background:transparent;}")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)

        # 头部：状态 + 标题
        head = QHBoxLayout()
        ok = self.result.status == "success" or self.result.error_code == ERR_IMG_PARTIAL
        color = C["success"] if ok else C["danger"]
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color};font-size:14px;")
        status_text = "下载完成" if self.result.mode == "video" else "提取完成"
        if not ok:
            status_text = "任务失败" if self.result.status != "cancelled" else "任务已取消"
        st = QLabel(status_text)
        st.setStyleSheet(f"color:{color};font-size:15px;font-weight:600;")
        head.addWidget(dot)
        head.addWidget(st)
        head.addStretch()
        if not ok:
            chip = QLabel(self.result.error_code)
            chip.setStyleSheet(
                f"color:{color};border:1px solid {color};border-radius:10px;"
                f"padding:2px 10px;font-size:11px;background:{C['card']};")
            head.addWidget(chip)
        outer.addLayout(head)

        title = QLabel(self.result.title or "(无标题)")
        title.setStyleSheet(f"font-size:13px;color:{C['muted']};")
        title.setWordWrap(True)
        outer.addWidget(title)

        if ok:
            outer.addSpacing(8)
            grid = QGridLayout()
            grid.setSpacing(10)
            if self.result.mode == "video":
                grid.addWidget(_metric(self, "文件大小",
                                       _human_size(self.result.size_bytes)), 0, 0)
                grid.addWidget(_metric(self, "分辨率", self.result.resolution), 0, 1)
                grid.addWidget(_metric(self, "平均速度", self.result.avg_speed), 0, 2)
                grid.addWidget(_metric(self, "时长", self.result.duration), 1, 0)
                grid.addWidget(_metric(self, "格式", self.result.media_format), 1, 1)
                grid.addWidget(_metric(self, "分片数", str(self.result.segments)), 1, 2)
            else:
                grid.addWidget(_metric(self, "插图",
                                       f"{self.result.img_ok}/{self.result.img_total}"), 0, 0)
                grid.addWidget(_metric(self, "格式", self.result.media_format), 0, 1)
                grid.addWidget(_metric(self, "耗时", f"{self.result.elapsed_s:.1f}s"), 0, 2)
            outer.addLayout(grid)
            outer.addSpacing(8)
            info = QLabel()
            lines = [f"保存路径：{self.result.path}"]
            if self.result.mode == "video":
                lines.append(f"来源提取器：{self.result.extractor or '未知'}")
            else:
                lines.append(f"输出：{self.result.filename}")
            if self.result.img_failed:
                lines.append(f"失败插图 {len(self.result.img_failed)} 张：{'；'.join(self.result.img_failed[:3])}")
            info.setText("\n".join(lines))
            info.setStyleSheet(f"color:{C['muted']};font-size:12px;")
            info.setWordWrap(True)
            outer.addWidget(info)
        else:
            outer.addSpacing(8)
            msg = QLabel(self.result.friendly)
            msg.setStyleSheet(f"color:{C['text']};font-size:13px;")
            msg.setWordWrap(True)
            outer.addWidget(msg)

            # 开发者详情（可折叠）
            box = QGroupBox("开发者详情")
            box.setCheckable(True)
            box.setChecked(False)
            box.setStyleSheet(
                f"QGroupBox{{font-size:12px;color:{C['muted']};border:1px solid {C['border_soft']};"
                "border-radius:8px;margin-top:8px;padding-top:10px;}"
                "QGroupBox::indicator{width:14px;height:14px;}")
            dev = QLabel(self.result.to_dev_text())
            dev.setTextInteractionFlags(Qt.TextSelectableByMouse)
            dev.setStyleSheet(
                f"font-family:Consolas,'Courier New',monospace;"
                f"font-size:11px;color:{C['text']};background:{C['metric_bg']};"
                "border-radius:6px;padding:8px;")
            dev.setTextFormat(Qt.PlainText)
            dev.setWordWrap(True)
            scroll = QScrollArea()
            scroll.setWidget(dev)
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(180)
            scroll.setFrameShape(QFrame.NoFrame)
            dev_inner = QVBoxLayout()
            dev_inner.addWidget(scroll)
            box.setLayout(dev_inner)
            outer.addWidget(box)

        # 按钮
        btns = QHBoxLayout()
        btns.addStretch()
        if ok:
            b_open = QPushButton("打开所在文件夹")
            b_open.clicked.connect(self._open_folder)
            b_open.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b_open)
        if not ok:
            b_copy = QPushButton("复制完整日志")
            b_copy.clicked.connect(self._copy_log)
            b_copy.setCursor(Qt.PointingHandCursor)
            btns.addWidget(b_copy)
        b_log = QPushButton("打开日志目录")
        b_log.clicked.connect(lambda: open_log_dir())
        b_log.setCursor(Qt.PointingHandCursor)
        btns.addWidget(b_log)
        outer.addLayout(btns)

    def _open_folder(self) -> None:
        p = self.result.path
        if not p:
            return
        try:
            if os.name == "nt":
                subprocess.Popen(f'explorer /select,"{p}"')
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(p)])
        except Exception:
            pass

    def _copy_log(self) -> None:
        text = f"{self.result.friendly}\n\n{self.result.to_dev_text()}"
        QGuiApplication.clipboard().setText(text, QClipboard.Clipboard)
