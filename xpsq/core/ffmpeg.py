"""ffmpeg 定位与检测。打包后优先使用内置 ffmpeg。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

FFMPEG_BIN = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _bundled_candidates() -> list[Path]:
    cands: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cands.append(base / FFMPEG_BIN)
        cands.append(Path(sys.executable).parent / FFMPEG_BIN)
        cands.append(Path(sys.executable).parent / "ffmpeg" / FFMPEG_BIN)
    # 开发模式：项目根目录 ffmpeg/
    root = Path(__file__).resolve().parent.parent.parent
    cands.append(root / "ffmpeg" / FFMPEG_BIN)
    cands.append(root / FFMPEG_BIN)
    return cands


def find_ffmpeg() -> str | None:
    for p in _bundled_candidates():
        if p.is_file():
            return str(p)
    which = shutil.which("ffmpeg")
    if which:
        return which
    for env in ("FFMPEG_BINARY",):
        if os.environ.get(env):
            return os.environ[env]
    return None


def check_ffmpeg() -> tuple[bool, str]:
    path = find_ffmpeg()
    if not path:
        return False, "未找到 ffmpeg"
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10)
        first = out.stdout.splitlines()[0] if out.stdout else "ffmpeg"
        return True, first
    except Exception as e:
        return False, f"ffmpeg 运行失败: {e}"
