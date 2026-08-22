"""任务结果结构：用户层信息 + 开发者层信息。"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .. import version
from ..config import load_config


def _env_summary() -> str:
    cfg = load_config()
    return (
        f"{version.APP_NAME_EN} v{version.APP_VERSION} · Python {platform.python_version()} · "
        f"{platform.system()} {platform.release()} · impersonate={cfg.get('network', {}).get('impersonate')}"
    )


@dataclass
class TaskResult:
    """一次任务（视频下载 / 文章提取）的完整结果。"""

    mode: str                      # video / article
    task_id: str = ""
    status: str = "running"        # running / success / failed / cancelled
    title: str = ""
    error_code: str = ""
    friendly: str = ""             # 用户层一句话
    raw_exception: str = ""        # 原始异常摘要
    traceback: str = ""            # 开发者层
    stage: str = ""                # 失败发生在哪个阶段: extract/download/merge/postprocess
    url: str = ""
    extractor: str = ""
    env: str = ""

    # 成功信息
    filename: str = ""
    path: str = ""
    size_bytes: int = 0
    duration: str = ""
    resolution: str = ""
    media_format: str = ""
    segments: int = 0
    elapsed_s: float = 0.0
    avg_speed: str = ""
    img_total: int = 0
    img_ok: int = 0
    img_failed: list[str] = field(default_factory=list)
    log_file: str = ""

    start_time: datetime = field(default_factory=datetime.now)

    def to_dev_text(self) -> str:
        lines = [
            f"task_id      : {self.task_id}",
            f"mode         : {self.mode}",
            f"status       : {self.status}",
            f"error_code   : {self.error_code}",
            f"friendly     : {self.friendly}",
            f"stage        : {self.stage}",
            f"url          : {self.url}",
            f"extractor    : {self.extractor}",
            f"title        : {self.title}",
            f"filename     : {self.filename}",
            f"path         : {self.path}",
            f"size         : {self.size_bytes}",
            f"duration     : {self.duration}",
            f"resolution   : {self.resolution}",
            f"format       : {self.media_format}",
            f"segments     : {self.segments}",
            f"elapsed_s    : {self.elapsed_s}",
            f"images       : {self.img_ok}/{self.img_total}",
            f"env          : {self.env or _env_summary()}",
            f"log_file     : {self.log_file}",
        ]
        if self.raw_exception:
            lines.append(f"raw_exception: {self.raw_exception}")
        if self.traceback:
            lines.append("traceback    :")
            lines.append(self.traceback)
        return "\n".join(lines)

    def mark_success(self, **kw: Any) -> None:
        self.status = "success"
        self.elapsed_s = (datetime.now() - self.start_time).total_seconds()
        for k, v in kw.items():
            setattr(self, k, v)

    def mark_failed(self, error_code: str, friendly: str = "", raw: str = "", tb: str = "", stage: str = "") -> None:
        self.status = "failed"
        self.error_code = error_code
        self.friendly = friendly or error_code
        self.raw_exception = (raw or "")[:500]
        self.traceback = tb
        self.stage = stage
        self.elapsed_s = (datetime.now() - self.start_time).total_seconds()
