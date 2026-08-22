"""配置管理：JSON 配置文件，开箱即用的默认值。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "XpsqDownloader"
CONFIG_FILE = APP_DIR / "config.json"
LOGS_DIR = APP_DIR / "logs"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads"

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "language": "zh",
        "theme": "system",
        "history_limit": 200,
        "log_level": "INFO",
    },
    "network": {
        "impersonate": "chrome",          # chrome / edge / safari / off
        "concurrency": 8,                 # 并发分片数
        "sleep_interval": 2,              # 请求间隔(秒)
        "proxy": "",                      # 留空 = 直连
        "tls_impersonation": True,
    },
    "download": {
        "default_dir": str(DEFAULT_DOWNLOAD_DIR),
        "default_quality": "best",        # best / 1080 / 720
        "default_format": "mp4",          # mp4 / mkv / best
        "filename_template": "%(title)s.%(ext)s",
        "subtitles": False,
        "thumbnail": False,
        "sponsorblock": False,
    },
    "article": {
        "default_output_format": "html",  # html / markdown / txt
        "download_images": True,
        "max_image_size_mb": 20,
    },
    "cookies": {
        "cookies_file": "",               # cookies.txt 路径
    },
}


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    out = dict(defaults)
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return _deep_merge(DEFAULT_CONFIG, json.load(f))
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        merged = _deep_merge(DEFAULT_CONFIG, cfg)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get(name: str) -> Any:
    """点号路径读取，如 network.proxy"""
    cfg = load_config()
    cur: Any = cfg
    for part in name.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur
