"""任务日志：结构化 JSONL，按天分目录，便于用户与开发者排查。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from .config import LOGS_DIR


def _log_dir() -> Path:
    d = LOGS_DIR / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_task_id() -> str:
    return uuid.uuid4().hex[:8]


class TaskLogger:
    """一个任务一条 jsonl 文件。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.path = _log_dir() / f"task_{task_id}.jsonl"
        self._f = open(self.path, "a", encoding="utf-8")
        self.log("task_start", {"task_id": task_id})

    def log(self, event: str, data: dict | None = None) -> None:
        rec = {"ts": datetime.now().isoformat(timespec="milliseconds"),
               "event": event, "data": data or {}}
        try:
            self._f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            self._f.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass

    @property
    def file(self) -> str:
        return str(self.path)


def open_log_dir() -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(LOGS_DIR))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(LOGS_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(LOGS_DIR)])
    except Exception:
        pass
