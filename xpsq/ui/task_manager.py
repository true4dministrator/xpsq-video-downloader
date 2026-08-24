"""多任务下载中心：全局队列 + 有界并行调度。

调度规则：
- 并发上限 max_concurrent（设置里可调，默认 3，上限 5）
- 同域名最多 max_per_domain 个任务并行（默认 2，防封）
- 手动任务按添加顺序排队，先到先启动
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from ..config import load_config


@dataclass
class TaskItem:
    task_id: str
    mode: str          # video / music / article
    url: str
    save_dir: str
    make_worker: callable  # () -> BaseWorker
    panel: object = None   # 提交任务的面板，用于回传进度/结果
    status: str = "queued"  # queued / running / success / failed / cancelled
    worker: object = None
    progress: dict = field(default_factory=dict)
    result: object = None
    added_at: float = field(default_factory=time.time)
    domain: str = field(default="")


class TaskManager(QObject):
    """全局任务调度器（单例）。"""

    task_added = Signal(object)     # TaskItem
    task_updated = Signal(object)   # TaskItem（进度/状态变化）
    task_finished = Signal(object)  # TaskItem

    _instance: "TaskManager | None" = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: list[TaskItem] = []
        self._seq = 0

    @classmethod
    def instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    # ---------- 配置 ----------
    def _max_concurrent(self) -> int:
        try:
            n = int(load_config().get("download", {}).get("max_concurrent", 3))
            return max(1, min(n, 5))
        except Exception:
            return 3

    # ---------- 提交 ----------
    def submit(self, panel, make_worker: callable, url: str, save_dir: str) -> TaskItem:
        self._seq += 1
        domain = urlparse(url).netloc or ""
        item = TaskItem(
            task_id=f"t{self._seq}",
            mode=panel.mode if panel else "video",
            url=url, save_dir=save_dir,
            make_worker=make_worker, panel=panel, domain=domain,
        )
        self._tasks.append(item)
        self.task_added.emit(item)
        self._schedule()
        return item

    # ---------- 调度 ----------
    def _schedule(self) -> None:
        limit = self._max_concurrent()
        while True:
            running = [t for t in self._tasks if t.status == "running"]
            if len(running) >= limit:
                return
            candidate = None
            for t in self._tasks:
                if t.status != "queued":
                    continue
                same_domain = sum(1 for r in running if r.domain and r.domain == t.domain)
                if same_domain < 2:  # 同域名限流
                    candidate = t
                    break
            if candidate is None:
                return
            self._start(candidate)

    def _start(self, item: TaskItem) -> None:
        item.status = "running"
        try:
            item.worker = item.make_worker()
        except Exception:
            item.status = "failed"
            self.task_updated.emit(item)
            self.task_finished.emit(item)
            self._schedule()
            return
        item.worker.progress.connect(lambda d, it=item: self._on_progress(it, d))
        item.worker.finished_ok.connect(lambda r, it=item: self._on_finished(it, r))
        item.worker.start()
        self.task_updated.emit(item)

    def _on_progress(self, item: TaskItem, d: dict) -> None:
        item.progress = d
        panel = item.panel
        if panel is not None and hasattr(panel, "_on_progress"):
            try:
                panel._on_progress(d)
            except Exception:
                pass
        self.task_updated.emit(item)

    def _on_finished(self, item: TaskItem, result) -> None:
        item.status = result.status if result else "failed"
        item.result = result
        item.worker = None
        panel = item.panel
        if panel is not None and hasattr(panel, "_on_finished"):
            try:
                panel._on_finished(result)
            except Exception:
                pass
        self.task_finished.emit(item)
        self._schedule()  # 有空位则启动下一个排队任务

    # ---------- 取消 ----------
    def cancel(self, task_id: str) -> None:
        for t in self._tasks:
            if t.task_id != task_id:
                continue
            if t.status == "queued":
                t.status = "cancelled"
                self.task_updated.emit(t)
                self.task_finished.emit(t)
            elif t.status == "running" and t.worker is not None:
                t.worker.cancel()
            return

    def cancel_panel(self, panel) -> None:
        """取消指定面板最近提交且未完成的任务。"""
        for t in reversed(self._tasks):
            if t.panel is panel and t.status in ("queued", "running"):
                self.cancel(t.task_id)
                return

    # ---------- 查询 ----------
    def tasks(self) -> list[TaskItem]:
        return list(self._tasks)

    def active_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == "running")

    def queued_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == "queued")
