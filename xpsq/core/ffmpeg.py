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
        meipass = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else Path(sys.executable).parent
        exe_dir = Path(sys.executable).parent
        bases = {meipass, exe_dir, exe_dir / "_internal", exe_dir / "ffmpeg"}
        for base in bases:
            cands.append(base / FFMPEG_BIN)
            cands.append(base / "ffmpeg" / FFMPEG_BIN)
    # 开发模式：项目根目录 ffmpeg/
    root = Path(__file__).resolve().parent.parent.parent
    cands.append(root / "ffmpeg" / FFMPEG_BIN)
    cands.append(root / FFMPEG_BIN)
    # 去重（保持顺序）
    seen: set[str] = set()
    out: list[Path] = []
    for c in cands:
        s = str(c)
        if s not in seen:
            seen.add(s)
            out.append(c)
    return out


def find_ffmpeg() -> str | None:
    for p in _bundled_candidates():
        if p.is_file():
            return str(p)
    which = shutil.which("ffmpeg")
    if which:
        return which
    if os.environ.get("FFMPEG_BINARY"):
        return os.environ["FFMPEG_BINARY"]
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


def ffmpeg_debug() -> str:
    """返回 ffmpeg 探测全过程，供排查。"""
    lines = [f"frozen={getattr(sys, 'frozen', False)}",
             f"executable={sys.executable}",
             f"_MEIPASS={getattr(sys, '_MEIPASS', '')}"]
    for c in _bundled_candidates():
        lines.append(f"  {'OK ' if c.is_file() else 'NO '} {c}")
    found = find_ffmpeg()
    lines.append(f"resolved={found}")
    return "\n".join(lines)
