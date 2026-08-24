"""任务中心：全局多任务列表（排队/下载中/完成），每个任务独立进度与取消。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .task_manager import TaskItem, TaskManager
from .theme import C

_STATUS_TEXT = {
    "queued": "排队中",
    "running": "下载中",
    "success": "完成",
    "failed": "失败",
    "cancelled": "已取消",
}


def _fmt_eta(sec) -> str:
    try:
        sec = max(0, int(sec))
    except Exception:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class TasksView(QWidget):
    """任务中心页面：列出全部任务，随 TaskManager 信号自动刷新。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, QListWidgetItem] = {}
        self._build()
        mgr = TaskManager.instance()
        mgr.task_added.connect(self._on_added)
        mgr.task_updated.connect(self._on_updated)
        mgr.task_finished.connect(self._on_finished)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 12, 12)
        root.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("任务")
        title.setStyleSheet(f"font-size:14px;font-weight:600;color:{C['text']};")
        self.count_lab = QLabel("")
        self.count_lab.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        b_clear = QPushButton("清除")
        b_clear.clicked.connect(self._clear_done)
        head.addWidget(title)
        head.addWidget(self.count_lab)
        head.addStretch()
        head.addWidget(b_clear)
        root.addLayout(head)

        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget{border:none;outline:0;}")
        root.addWidget(self.list, 1)
        self._refresh_count()

    # ---------- 信号 ----------
    def _on_added(self, item: TaskItem) -> None:
        row = QListWidgetItem()
        self.list.addItem(row)
        w = self._make_row_widget(item)
        row.setSizeHint(w.sizeHint())
        self.list.setItemWidget(row, w)
        self._rows[item.task_id] = row
        self._refresh_count()

    def _on_updated(self, item: TaskItem) -> None:
        row = self._rows.get(item.task_id)
        if row is not None:
            w = self.list.itemWidget(row)
            if w is not None:
                self._update_row_widget(w, item)
                # 行高随内容变化刷新，避免按钮/文字被裁剪
                row.setSizeHint(w.sizeHint())
        self._refresh_count()

    def _on_finished(self, item: TaskItem) -> None:
        self._on_updated(item)

    # ---------- UI ----------
    def _make_row_widget(self, item: TaskItem) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        # 顶行：名称 + 状态 + 取消
        top = QHBoxLayout()
        short = item.url if len(item.url) <= 22 else item.url[:20] + "…"
        name = QLabel(short)
        name.setObjectName("task_name")
        name.setStyleSheet(f"color:{C['text']};font-size:12px;")
        name.setToolTip(item.url)
        st = QLabel(_STATUS_TEXT.get(item.status, item.status))
        st.setObjectName("task_status")
        st.setFixedWidth(52)  # 固定宽度，避免被"取消"按钮挤掉文字
        st.setStyleSheet(f"color:{C['muted']};font-size:11px;")
        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(lambda: TaskManager.instance().cancel(item.task_id))
        top.addWidget(name, 1)
        top.addWidget(st)
        top.addWidget(b_cancel)
        lay.addLayout(top)
        # 进度条
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        lay.addWidget(bar)
        # 详情行
        detail = QLabel("")
        detail.setObjectName("task_detail")
        detail.setStyleSheet(f"color:{C['faint']};font-size:11px;")
        lay.addWidget(detail)
        return w

    def _update_row_widget(self, w: QWidget, item: TaskItem) -> None:
        name = w.findChild(QLabel, "task_name")
        st = w.findChild(QLabel, "task_status")
        detail = w.findChild(QLabel, "task_detail")
        bars = w.findChildren(QProgressBar)
        bar = bars[0] if bars else None
        if bar is not None:
            bar.setValue(0)
        if item.status == "running":
            d = item.progress or {}
            ev = d.get("event")
            pct = int(d.get("percent", 0) or 0)
            if bar is not None:
                bar.setValue(pct)
            sp = d.get("speed") or 0
            done = d.get("downloaded", 0) or 0
            total = d.get("total", 0) or 0
            eta = d.get("eta")
            sp_txt = f"{sp/1024:.0f} KB/s" if sp < 1048576 else f"{sp/1048576:.1f} MB/s"
            parts = [f"{done/1048576:.1f} MB"]
            if total:
                parts.append(f"/ {total/1048576:.1f} MB")
            parts.append(sp_txt)
            if eta:
                parts.append(f"剩余 {_fmt_eta(eta)}")
            if ev == "extracting":
                detail.setText("正在解析页面…")
            elif ev == "postprocessing":
                detail.setText("正在合并/转码…")
            else:
                detail.setText(" · ".join(parts))
            st.setText(_STATUS_TEXT["running"])
        elif item.status == "success":
            if bar is not None:
                bar.setValue(100)
            size = item.result.size_bytes if item.result else 0
            detail.setText(f"{size/1048576:.1f} MB" if size else "完成")
            st.setText("完成")
        elif item.status == "failed":
            code = item.result.error_code if item.result else "ERR"
            detail.setText(f"失败：{code}")
            st.setText("失败")
        elif item.status == "cancelled":
            st.setText("已取消")
            detail.setText("")
        else:
            st.setText("排队中")
            detail.setText("等待空闲位置…")

    def _refresh_count(self) -> None:
        tasks = TaskManager.instance().tasks()
        running = sum(1 for t in tasks if t.status == "running")
        queued = sum(1 for t in tasks if t.status == "queued")
        self.count_lab.setText(f"{running} 个下载中 · {queued} 个排队中")

    def _clear_done(self) -> None:
        mgr = TaskManager.instance()
        done_ids = [t.task_id for t in mgr.tasks()
                    if t.status in ("success", "failed", "cancelled")]
        for tid in done_ids:
            row = self._rows.pop(tid, None)
            if row is not None:
                self.list.takeItem(self.list.row(row))
        self._refresh_count()
