"""视频下载内核：yt-dlp 主引擎 + 万能兜底嗅探器。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests
from lxml import html as lhtml

from .. import version
from ..config import load_config
from ..errors import (ERR_CANCELLED, ERR_FFMPEG, ERR_FS, ERR_INTERNAL,
                      ERR_NETWORK, ERR_UNSUPPORTED, AppError, classify_ytdlp_error)
from ..logging_setup import TaskLogger, new_task_id
from .ffmpeg import find_ffmpeg
from .result import TaskResult

ProgressCb = Callable[[dict], None]


def _build_ydl_opts(cfg: dict, save_dir: str, progress_cb: ProgressCb, task_logger: TaskLogger,
                    cancel_flag: Callable[[], bool] | None = None,
                    audio_only: bool = False, playlist: bool = False) -> dict:
    net = cfg.get("network", {})
    dl = cfg.get("download", {})
    ck = cfg.get("cookies", {})

    if audio_only:
        fmt_sel = "bestaudio/best"
    else:
        quality = dl.get("default_quality", "best")
        fmt = dl.get("default_format", "mp4")
        fmt_sel = "bestvideo*+bestaudio/best"
        if quality == "1080":
            fmt_sel = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        elif quality == "720":
            fmt_sel = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        if fmt == "mp4":
            fmt_sel += "/bestvideo*+bestaudio/best"

    opts: dict = {
        "outtmpl": str(Path(save_dir) / dl.get("filename_template", "%(title)s.%(ext)s")),
        "format": fmt_sel,
        "merge_output_format": None if audio_only else (
            "mp4" if fmt == "mp4" else "mkv" if fmt == "mkv" else None),
        "noplaylist": not playlist,
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": int(net.get("concurrency", 8)),
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "progress_hooks": [progress_cb],
        "logger": _YdlLogger(task_logger),
        "noprogress": True,
        "windowsfilenames": True,
    }
    if playlist:
        opts["ignoreerrors"] = True  # 列表里单个失败不中断整体
        try:
            pmax = int(dl.get("playlist_max", 0))
        except Exception:
            pmax = 0
        if pmax > 0:
            opts["playlistend"] = pmax
    # 显式告知 yt-dlp ffmpeg 位置（打包版不在 PATH 上，必须显式传入）
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
        task_logger.log("ffmpeg_found", {"path": ffmpeg_path})
    else:
        task_logger.log("ffmpeg_missing", {"hint": "ffmpeg 未定位到，需要合并的视频将失败"})
    if net.get("sleep_interval"):
        opts["sleep_interval"] = int(net.get("sleep_interval", 2))
    if net.get("proxy"):
        opts["proxy"] = net["proxy"]
    imp = net.get("impersonate")
    if imp and imp != "off" and net.get("tls_impersonation", True):
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            opts["impersonate"] = ImpersonateTarget.from_str(imp)
        except Exception:
            opts["impersonate"] = None
    if ck.get("cookies_file"):
        opts["cookiefile"] = ck["cookies_file"]
    if dl.get("subtitles"):
        opts.update({"writesubtitles": True, "writeautomaticsub": True,
                     "subtitleslangs": ["zh-Hans", "zh", "en", "zh-CN"]})
    if dl.get("thumbnail"):
        opts["writethumbnail"] = True
    if dl.get("sponsorblock"):
        opts["sponsorblock"] = {"remove": ["sponsor", "selfpromo"]}
    # 注意：音频提取不用 yt-dlp 的 FFmpegExtractAudio（它需要 ffprobe），
    # 由 download() 在下载完成后自行用 ffmpeg 转 MP3
    return opts


class _YdlLogger:
    def __init__(self, task_logger: TaskLogger):
        self._l = task_logger

    def debug(self, msg): self._l.log("ytdlp_debug", {"msg": str(msg)[:400]})
    def info(self, msg): self._l.log("ytdlp_info", {"msg": str(msg)[:400]})
    def warning(self, msg): self._l.log("ytdlp_warning", {"msg": str(msg)[:400]})
    def error(self, msg): self._l.log("ytdlp_error", {"msg": str(msg)[:400]})


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_speed(bps: float) -> str:
    return _human_size(bps) + "/s" if bps else ""


class VideoDownloader:
    def __init__(self, cfg: dict | None = None, progress_cb: ProgressCb | None = None,
                 cancel_flag: Callable[[], bool] | None = None):
        self.cfg = cfg or load_config()
        self.progress_cb = progress_cb or (lambda d: None)
        self.cancel_flag = cancel_flag
        self._downloaded = 0.0
        self._started = 0.0

    def _hook(self, d: dict) -> None:
        if self.cancel_flag and self.cancel_flag():
            raise AppError(ERR_CANCELLED, "用户取消")
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0) or 0
            self._downloaded = done
            self.progress_cb({
                "event": "downloading",
                "percent": (done / total * 100) if total else 0.0,
                "downloaded": done,
                "total": total,
                "speed": d.get("speed", 0) or 0,
                "eta": d.get("eta"),
                "filename": os.path.basename(d.get("filename", "") or ""),
            })
        elif d.get("status") == "finished":
            self.progress_cb({"event": "finished"})
        elif d.get("status") == "postprocessing":
            self.progress_cb({"event": "postprocessing",
                              "postprocessor": d.get("postprocessor", "")})

    def download(self, url: str, save_dir: str, audio_only: bool = False,
                 audio_format: str = "mp3", playlist: bool = False) -> TaskResult:
        import yt_dlp
        task_id = new_task_id()
        result = TaskResult(mode="video", task_id=task_id, url=url, env=version.APP_NAME_EN)
        logger = TaskLogger(task_id)
        result.log_file = logger.file
        logger.log("video_start", {"url": url, "save_dir": save_dir, "audio_only": audio_only,
                                   "audio_format": audio_format, "playlist": playlist})
        try:
            self._started = time.time()
            self._downloaded = 0.0
            opts = _build_ydl_opts(self.cfg, save_dir, self._hook, logger, self.cancel_flag,
                                   audio_only=audio_only, playlist=playlist)
            if not find_ffmpeg():
                opts["nopart"] = False  # 无 ffmpeg 时单文件流可直接下载
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.progress_cb({"event": "extracting"})
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise AppError(ERR_UNSUPPORTED, "未解析到任何视频信息")
                # 播放列表模式：返回的是 playlist 信息，取下载文件数
                if info.get("_type") == "playlist" or info.get("entries"):
                    entries = [e for e in (info.get("entries") or []) if e]
                    done = sum(1 for e in entries if e.get("_filename")
                               or (e.get("requested_downloads") and e["requested_downloads"][0].get("filepath")))
                    total = len(entries)
                    title = info.get("title") or "播放列表"
                    filename = f"{title}（{done}/{total} 个视频）"
                    path = str(Path(save_dir)) if Path(save_dir).exists() else ""
                    result.mark_success(
                        title=title, extractor=str(info.get("extractor") or "playlist"),
                        filename=filename, path=path, size_bytes=int(self._downloaded),
                        media_format="playlist", segments=total,
                        elapsed_s=time.time() - self._started,
                    )
                    logger.log("video_success", {"playlist": True, "done": done, "total": total})
                    return result
                filename = ydl.prepare_filename(info)
                final = info.get("_filename") or filename
                path = final if os.path.exists(final) else (
                    _find_actual_file(save_dir, info.get("id"), info.get("title"), audio_only))
                # 音频模式：下载完音频流后自行转码（不依赖 ffprobe）
                if audio_only and path:
                    self.progress_cb({"event": "postprocessing",
                                      "postprocessor": "转码音频", "note": "正在转码…"})
                    if audio_format == "raw":
                        pass  # 保留原始音频格式
                    else:
                        converted = _convert_audio(path, audio_format)
                        if converted:
                            path = converted
                        else:
                            raise AppError(ERR_FFMPEG, "音频转码失败")
                ext = Path(path).suffix.lstrip(".") if path else ("mp3" if audio_only else "")
                result.mark_success(
                    title=info.get("title") or info.get("id") or "",
                    extractor=str(info.get("extractor") or info.get("extractor_key") or ""),
                    filename=os.path.basename(path or ""),
                    path=path or "",
                    size_bytes=os.path.getsize(path) if path and os.path.exists(path) else int(
                        self._downloaded),
                    duration=_fmt_duration(info.get("duration")),
                    resolution="" if audio_only else _fmt_resolution(
                        info.get("width"), info.get("height"), info.get("resolution")),
                    media_format=ext,
                    segments=_count_segments(info),
                    avg_speed=_avg_speed(self._downloaded, time.time() - self._started),
                    elapsed_s=time.time() - self._started,
                )
                logger.log("video_success", {"path": result.path, "title": result.title})
                return result
        except Exception as exc:
            if isinstance(exc, AppError) and exc.code == ERR_CANCELLED:
                result.mark_failed(ERR_CANCELLED, "任务已取消", stage="downloading")
            else:
                app_err = classify_ytdlp_error(exc)
                result.mark_failed(app_err.code, app_err.friendly, app_err.message,
                                   app_err.dev_detail, stage="download")
                logger.log("video_failed", {"code": app_err.code, "raw": str(exc)[:500]})
            return result
        finally:
            logger.close()


def _convert_audio(src: str, target: str) -> str | None:
    """用 ffmpeg 把音频转成目标格式（mp3 VBR / mp3 320k / m4a），成功后删除中间文件。"""
    ff = find_ffmpeg()
    if not ff:
        raise AppError(ERR_FFMPEG, "需要 ffmpeg 转码音频")
    ext_map = {"mp3": ".mp3", "mp3-320": ".mp3", "m4a": ".m4a"}
    dst = Path(src).with_suffix(ext_map.get(target, ".mp3"))
    # 源文件已是目标格式（如网易云源就是 mp3）→ 直接保留，不重复转码
    if Path(src).suffix.lower() == dst.suffix.lower():
        return src
    if target == "m4a":
        codec_args = ["-c:a", "aac", "-b:a", "256k"]
    elif target == "mp3-320":
        codec_args = ["-c:a", "libmp3lame", "-b:a", "320k"]
    else:
        codec_args = ["-c:a", "libmp3lame", "-q:a", "0"]
    cmd = [ff, "-y", "-i", src, "-vn", *codec_args, str(dst)]
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, **kwargs)
    except Exception as exc:
        raise AppError(ERR_FFMPEG, f"音频转码失败: {exc}") from exc
    if proc.returncode != 0 or not dst.exists():
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass
        err_tail = (proc.stderr or "")[-200:]
        raise AppError(ERR_FFMPEG, f"音频转码失败: {err_tail}")
    try:
        os.remove(src)
    except Exception:
        pass
    return str(dst)


def _find_actual_file(save_dir: str, video_id: str | None, title: str | None,
                      audio_only: bool = False) -> str:
    try:
        exts = (".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac") if audio_only else \
               (".mp4", ".mkv", ".webm", ".flv", ".mov", ".mp3", ".m4a")
        files = list(Path(save_dir).iterdir())
        for f in files:
            if f.is_file() and f.suffix.lower() in exts:
                if title and title[:20] in f.name:
                    return str(f)
        return ""
    except Exception:
        return ""


def _fmt_duration(sec: int | None) -> str:
    if not sec:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _fmt_resolution(w: int | None, h: int | None, res: str | None) -> str:
    if res:
        return str(res)
    if w and h:
        return f"{w}x{h}"
    return ""


def _count_segments(info: dict) -> int:
    try:
        for fmt in info.get("formats") or []:
            if fmt.get("protocol") and "m3u8" in str(fmt.get("protocol")):
                return len(fmt.get("fragments") or [])
        return len(info.get("fragments") or [])
    except Exception:
        return 0


def _avg_speed(bytes_done: float, seconds: float) -> str:
    if seconds <= 0 or bytes_done <= 0:
        return ""
    return _human_speed(bytes_done / seconds)


# ---------------- 万能兜底嗅探器（四层强化版） ----------------

_MEDIA_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.(?:mp4|webm|m4v|mov|flv|ts|mp3|m4a|aac|ogg|opus)(?:\?[^\s"\'<>\\]*)?', re.I)
_M3U8_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.m3u8(?:\?[^\s"\'<>\\]*)?', re.I)
_BLOB_RE = re.compile(r'blob:https?://[^\s"\'<>]+', re.I)

# L1 内嵌 JSON 状态窗口变量（React/Nuxt/Next 等前端框架的通用约定）
_STATE_PATTERNS = [
    re.compile(r'window\.__INITIAL_STATE__\s*=\s*', re.I),
    re.compile(r'window\.__NUXT__\s*=\s*', re.I),
    re.compile(r'window\.__NEXT_DATA__\s*=\s*', re.I),
    re.compile(r'window\.__INITIAL_DATA__\s*=\s*', re.I),
    re.compile(r'window\.__PRELOADED_STATE__\s*=\s*', re.I),
    re.compile(r'window\.__APOLLO_STATE__\s*=\s*', re.I),
    re.compile(r'__INITIAL_STATE__\s*[:=]\s*', re.I),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _balanced_json(text: str, start: int) -> str | None:
    """从 text[start]（应为 { 或 [）开始做括号配对扫描，返回完整 JSON 片段。"""
    if start >= len(text):
        return None
    open_ch = text[start]
    close_ch = '}' if open_ch == '{' else ']' if open_ch == '[' else None
    if close_ch is None:
        return None
    depth = 0
    in_str = False
    esc = False
    i = start
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def _walk_media(obj, out: list) -> None:
    """递归遍历 JSON 结构，收集看起来像媒体直链的字符串。"""
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_media(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_media(v, out)
    elif isinstance(obj, str):
        if _M3U8_RE.search(obj) or _MEDIA_RE.search(obj):
            out.append(obj)


def _collect_ld_video(obj, out: list) -> None:
    """递归遍历 JSON-LD，收集 VideoObject 的 contentUrl/embedUrl/url。"""
    if isinstance(obj, dict):
        t = str(obj.get('@type') or '')
        if 'VideoObject' in t or 'MusicVideoObject' in t:
            for k in ('contentUrl', 'embedUrl', 'url'):
                u = obj.get(k)
                if isinstance(u, str) and u:
                    out.append(u)
            v = obj.get('video')
            if isinstance(v, (dict, list)):
                _collect_ld_video(v, out)
        for val in obj.values():
            if isinstance(val, (dict, list)):
                _collect_ld_video(val, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_ld_video(v, out)


def _pick_srcset(srcset: str, base_url: str) -> str | None:
    """从 srcset 里挑分辨率标记最高（xxxw）的那个 URL。"""
    best_url, best_w = None, -1
    for part in srcset.split(','):
        toks = [t for t in part.strip().split() if t]
        if not toks:
            continue
        w = -1
        if len(toks) > 1:
            m = re.search(r'(\d+)w', toks[1])
            if m:
                w = int(m.group(1))
        if w > best_w:
            best_w, best_url = w, toks[0]
    return urljoin(base_url, best_url) if best_url else None


def _parse_master_streams(text: str, base_url: str) -> list[tuple[int, str]]:
    """解析 master 级 m3u8，返回 [(BANDWIDTH, 子流 URL), ...]。"""
    streams: list[tuple[int, str]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('#EXT-X-STREAM-INF'):
            continue
        bw = 0
        m = re.search(r'BANDWIDTH=(\d+)', line)
        if m:
            bw = int(m.group(1))
        if i + 1 < len(lines):
            uri = lines[i + 1].strip()
            if uri and not uri.startswith('#'):
                streams.append((bw, urljoin(base_url, uri)))
    return streams


class FallbackSniffer:
    """yt-dlp 不支持时：四层流水线嗅探直链。

    L0 语义提取(video/og/JSON-LD) → L1 内嵌 JSON 状态 → L2 m3u8 智能解析 → L3 递归(iframe/JS)
    """

    def __init__(self, cfg: dict | None = None, progress_cb: ProgressCb | None = None,
                 cancel_flag: Callable[[], bool] | None = None):
        self.cfg = cfg or load_config()
        self.progress_cb = progress_cb or (lambda d: None)
        self.cancel_flag = cancel_flag
        self.diag: dict = {}
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        ck = self.cfg.get("cookies", {}).get("cookies_file")
        if ck and Path(ck).exists():
            self._session.cookies = _load_cookies_file(ck)

    # ---------- 网络 ----------
    def _fetch(self, url: str, referer: str | None = None, timeout: int = 20) -> requests.Response:
        proxy = self.cfg.get("network", {}).get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        return self._session.get(url, timeout=timeout, allow_redirects=True,
                                 headers={"Referer": referer or url}, proxies=proxies)

    # ---------- L0 语义提取 ----------
    def _extract_l0(self, html: str, base_url: str) -> list[str]:
        """优先级：JSON-LD > og:video/twitter > video/source 标签 > srcset。"""
        hits: list[tuple[int, str]] = []
        try:
            doc = lhtml.fromstring(html)
        except Exception:
            doc = None
        if doc is not None:
            for node in doc.xpath('//script[@type="application/ld+json"]'):
                txt = (node.text or '').strip()
                if not txt:
                    continue
                try:
                    data = json.loads(txt)
                except Exception:
                    continue
                found: list[str] = []
                _collect_ld_video(data, found)
                for u in found:
                    hits.append((0, u))
            for meta in doc.xpath('//meta'):
                prop = (meta.get('property') or meta.get('name') or '').lower()
                if prop in ('og:video', 'og:video:url', 'og:video:secure_url',
                            'twitter:player', 'twitter:player:stream',
                            'twitter:player:url'):
                    content = (meta.get('content') or '').strip()
                    if content and content not in ('video/mp4', 'video/webm', 'video/ogg'):
                        hits.append((1, content))
            for v in doc.xpath('//video/@src | //video/source/@src | //source/@src'):
                if v.strip():
                    hits.append((2, v.strip()))
            for v in doc.xpath('//video/@srcset | //video/source/@srcset | //source/@srcset'):
                best = _pick_srcset(v, base_url)
                if best:
                    hits.append((2, best))
        seen: set[str] = set()
        out: list[str] = []
        for pri, u in sorted(hits, key=lambda x: x[0]):
            fu = urljoin(base_url, u.strip())
            if fu in seen or not fu.startswith(('http://', 'https://')):
                continue
            seen.add(fu)
            # 高优先级来源(JSON-LD/og)即使无扩展名也接受（CDN 常见）
            if pri <= 1 or _M3U8_RE.search(fu) or _MEDIA_RE.search(fu):
                out.append(fu)
        return out

    # ---------- L1 内嵌 JSON 状态挖掘 ----------
    def _extract_l1(self, html: str) -> list[str]:
        out: list[str] = []
        for pat in _STATE_PATTERNS:
            for m in pat.finditer(html):
                s = m.end()
                while s < len(html) and html[s] in ' \t\r\n':
                    s += 1
                if s >= len(html) or html[s] not in '{[':
                    continue
                seg = _balanced_json(html, s)
                if not seg:
                    continue
                try:
                    data = json.loads(seg)
                except Exception:
                    continue
                _walk_media(data, out)
        return list(dict.fromkeys(out))

    # ---------- L2 m3u8 智能解析 ----------
    def _resolve_m3u8(self, url: str, referer: str, depth: int = 0) -> str:
        """master 级播放列表自动选最高码率子流，最多递归 3 层。"""
        if depth >= 3:
            return url
        try:
            resp = self._fetch(url, referer=referer)
            text = resp.text
        except Exception:
            return url
        if '#EXT-X-STREAM-INF' in text:
            streams = _parse_master_streams(text, url)
            if streams:
                best = max(streams, key=lambda s: s[0])
                self.progress_cb({"event": "sniffing",
                                  "note": f"m3u8 多码率流，自动选择 {best[0] // 1000}kbps…"})
                return self._resolve_m3u8(best[1], referer, depth + 1)
        return url

    # ---------- L3 递归扫描（iframe + JS 资源） ----------
    def _extract_l3(self, page_url: str, html: str, visited: set[str],
                    depth: int, max_depth: int = 2) -> tuple[str | None, str]:
        if depth >= max_depth:
            return None, None
        try:
            doc = lhtml.fromstring(html)
            frames = [f for f in doc.xpath('//iframe/@src | //frame/@src') if f.strip()][:6]
            js_urls = [j for j in doc.xpath('//script/@src') if j.strip()][:6]
        except Exception:
            frames, js_urls = [], []
        for f in frames:
            fu = urljoin(page_url, f.strip())
            if not fu.startswith(('http://', 'https://')) or fu in visited:
                continue
            visited.add(fu)
            self.progress_cb({"event": "sniffing",
                              "note": f"发现内嵌播放器，深入解析 {fu[:40]}…"})
            try:
                resp = self._fetch(fu, referer=page_url)
                media, kind = self._sniff_content(fu, resp.text, visited, depth + 1)
                if media:
                    return media, kind
            except Exception:
                continue
        for j in js_urls:
            ju = urljoin(page_url, j.strip())
            if not ju.startswith(('http://', 'https://')) or ju in visited:
                continue
            visited.add(ju)
            try:
                resp = self._fetch(ju, referer=page_url, timeout=15)
                js = resp.text
                for m in _M3U8_RE.findall(js):
                    return m, 'm3u8'
                cands = _MEDIA_RE.findall(js)
                if cands:
                    return cands[0], 'mp4'
            except Exception:
                continue
        return None, None

    # ---------- L4 SPA API 接口探测（JS 壳页面专用） ----------
    _API_EP_RE = [
        re.compile(r'["\'](/[^"\']*?(?:api|play|video|media|stream|vod)[^"\']*)["\']', re.I),
        re.compile(r'(?:fetch|axios\.(?:get|post|put))\s*\(\s*["\']([^"\']+)["\']', re.I),
        re.compile(r'(?:url|endpoint|apiUrl)\s*:\s*["\']([^"\']*?(?:api|play|video|stream)[^"\']*)["\']', re.I),
    ]

    def _extract_l4_api(self, page_url: str, visited: set[str],
                        referer: str) -> tuple[str | None, str]:
        """从页面 JS 中挖 API 端点并请求，递归挖媒体直链。限同域。"""
        from urllib.parse import urlparse
        host = urlparse(page_url).netloc
        try:
            resp = self._fetch(page_url, referer=referer)
            html = resp.text
            doc = lhtml.fromstring(html)
            js_urls = [j for j in doc.xpath('//script/@src') if j.strip()][:4]
        except Exception:
            js_urls = []
        self.progress_cb({"event": "sniffing", "note": "页面疑似 JS 渲染，探测后端 API 接口…"})
        endpoints: list[str] = []
        for j in js_urls:
            ju = urljoin(page_url, j.strip())
            if not ju.startswith(('http://', 'https://')) or ju in visited:
                continue
            visited.add(ju)
            try:
                js_text = self._fetch(ju, referer=referer, timeout=15).text
            except Exception:
                continue
            for pat in self._API_EP_RE:
                for m in pat.findall(js_text):
                    ep = m.strip()
                    if not ep or len(ep) < 5 or ep.startswith(('//', '#')):
                        continue
                    fu = urljoin(page_url, ep)
                    if urlparse(fu).netloc != host:  # 只探测同域 API
                        continue
                    if fu not in endpoints:
                        endpoints.append(fu)
        for ep in endpoints[:8]:
            if ep in visited:
                continue
            visited.add(ep)
            try:
                ar = self._fetch(ep, referer=referer, timeout=15)
                body = ar.text
            except Exception:
                continue
            if ar.status_code >= 400 or len(body) < 8:
                continue
            # API 返回 JSON：递归挖媒体直链
            if body.lstrip().startswith(('{', '[')):
                try:
                    data = json.loads(body)
                    found: list[str] = []
                    _walk_media(data, found)
                    for u in found:
                        if _M3U8_RE.search(u):
                            return self._resolve_m3u8(u, page_url), 'm3u8'
                        if _MEDIA_RE.search(u):
                            return u, 'mp4'
                except Exception:
                    pass
            # 兜底：文本正则
            for m in _M3U8_RE.findall(body):
                return self._resolve_m3u8(m, page_url), 'm3u8'
            for m in _MEDIA_RE.findall(body):
                return m, 'mp4'
        return None, None

    # ---------- 单页内容嗅探（L0/L1/正则 + 递归 L3 + API L4） ----------
    def _sniff_content(self, page_url: str, html: str, visited: set[str],
                       depth: int = 0) -> tuple[str | None, str]:
        # 页面本身就是 m3u8 master 播放列表：直接用页面 URL 选最高码率
        if html.lstrip().startswith('#EXTM3U') and '#EXT-X-STREAM-INF' in html:
            return self._resolve_m3u8(page_url, page_url), 'm3u8'
        # 正则快速通道（m3u8 优先，兼容旧行为）
        for m in _M3U8_RE.findall(html):
            return self._resolve_m3u8(m, page_url), 'm3u8'
        for m in _MEDIA_RE.findall(html):
            return m, 'mp4'
        # L0 语义提取
        self.progress_cb({"event": "sniffing", "note": "语义解析页面结构…"})
        for u in self._extract_l0(html, page_url):
            if _M3U8_RE.search(u):
                return self._resolve_m3u8(u, page_url), 'm3u8'
            return u, 'mp4'
        # 相对路径兜底（src/href="xxx.mp4"）
        rel = re.findall(
            r'''(?:src|href|data-src)\s*=\s*["']([^"']+\.(?:mp4|webm|m4v|mov|flv|ts|mp3|m4a|aac|ogg|opus)(?:\?[^"']*)?)["']''',
            html, re.I)
        if rel:
            return urljoin(page_url, rel[0]), 'mp4'
        # L1 内嵌 JSON 状态
        self.progress_cb({"event": "sniffing", "note": "挖掘页面内嵌数据…"})
        for u in self._extract_l1(html):
            if _M3U8_RE.search(u):
                return self._resolve_m3u8(u, page_url), 'm3u8'
            if _MEDIA_RE.search(u):
                return u, 'mp4'
        is_blob = bool(_BLOB_RE.search(html))
        # L3 递归（iframe + JS 资源）
        if depth < 2:
            media, kind = self._extract_l3(page_url, html, visited, depth)
            if media:
                return media, kind
        # L4 SPA API 接口探测（页面内容少时，数据很可能在 API 里）
        if depth == 0 and len(html) < 20000:
            media, kind = self._extract_l4_api(page_url, set(), page_url)
            if media:
                return media, kind
        # L5 真渲染兜底（JS 壳页面：用系统 Edge 无头渲染 + 捕获网络直链）
        if depth == 0:
            media_url = self._render_fallback(page_url)
            if media_url:
                return media_url, ("m3u8" if ".m3u8" in media_url.lower() else "mp4")
        # blob 检测放最后：blob 页面也要先试完 L3/L4/L5（blob 流可能被渲染后转为真实直链）
        if is_blob:
            return None, 'blob'
        return None, None

    def _render_fallback(self, page_url: str) -> str | None:
        """L5：Playwright 驱动系统 Edge 渲染页面，优先取网络捕获的媒体直链，
        其次对渲染后 DOM 再跑一遍嗅探。带已保存的浏览器会话（若存在）。失败返回 None。"""
        self.progress_cb({"event": "sniffing", "note": "静态嗅探无果，尝试无头浏览器真渲染…"})
        try:
            from .render import render_page, render_last_error
        except Exception as e:
            self.diag["render_error"] = f"import: {e}"
            return None
        state_path = None
        try:
            from ..config import BROWSER_STATE
            if BROWSER_STATE.exists():
                state_path = str(BROWSER_STATE)
                self.diag["render_session"] = "已加载"
        except Exception:
            pass
        html, media_urls = render_page(page_url, state_path=state_path)
        if render_last_error:
            self.diag["render_error"] = render_last_error
        if media_urls:
            for u in media_urls:
                if _M3U8_RE.search(u):
                    return self._resolve_m3u8(u, page_url)
                if _MEDIA_RE.search(u):
                    return u
            return media_urls[0]  # 无扩展名但 content-type 判定的直链
        if html and html != page_url:
            media, kind = self._sniff_content(page_url, html, set(), 1)
            return media if media else None
        return None

    # ---------- 入口 ----------
    def sniff(self, url: str) -> tuple[str | None, str]:
        """四层流水线嗅探，返回 (直链, 类型)。诊断信息存 self.diag。"""
        self.diag = {}
        try:
            resp = self._fetch(url)
            html = resp.text
            self.diag = {
                "status": resp.status_code,
                "final_url": str(resp.url),
                "html_len": len(html),
                "content_type": resp.headers.get("content-type", ""),
            }
            # content-type 直判：响应本身就是媒体文件（直链 mp4/m3u8 等）
            ct = self.diag["content_type"].lower()
            if any(t in ct for t in ("video/", "audio/", "mpegurl")):
                kind = "m3u8" if "mpegurl" in ct else "mp4"
                self.progress_cb({"event": "sniffing", "note": f"识别到 {kind} 媒体直链…"})
                return str(resp.url), kind
            low = html.lower()
            for kw in ("under construction", "we will be back soon", "attention required",
                       "cf-challenge", "checking your browser"):
                if kw in low:
                    self.diag["page_state"] = kw
                    break
            self.progress_cb({"event": "sniffing", "note": "开始万能嗅探…"})
            return self._sniff_content(url, html, set(), 0)
        except Exception as exc:
            self.diag["error"] = str(exc)[:200]
            # 页面请求失败（TLS 指纹/反爬拦截）：仍尝试 L5 真渲染兜底，
            # 浏览器 Edge 是独立网络栈，可能绕过 requests/curl_cffi 被拒
            self.progress_cb({"event": "sniffing", "note": "页面请求被拦截，尝试无头浏览器渲染…"})
            media_url = self._render_fallback(url)
            if media_url:
                return media_url, ("m3u8" if ".m3u8" in media_url.lower() else "mp4")
            return None, None

    def download(self, media_url: str, kind: str, save_dir: str, referer: str) -> TaskResult:
        task_id = new_task_id()
        result = TaskResult(mode="video", task_id=task_id, url=referer, env=version.APP_NAME_EN)
        logger = TaskLogger(task_id)
        result.log_file = logger.file
        try:
            Path(save_dir).mkdir(parents=True, exist_ok=True)
            name = _fallback_filename(media_url)
            dest = Path(save_dir) / name
            if kind == "m3u8":
                return self._download_m3u8_ffmpeg(media_url, dest, referer, result, logger)
            return self._download_direct(media_url, dest, referer, result, logger)
        except Exception as exc:
            app_err = classify_ytdlp_error(exc)
            result.mark_failed(app_err.code, app_err.friendly, app_err.message, app_err.dev_detail)
            return result
        finally:
            logger.close()

    def _download_direct(self, url: str, dest: Path, referer: str, result: TaskResult,
                         logger: TaskLogger) -> TaskResult:
        """直链下载：支持 Range 时走多线程分块（类 IDM），否则单线程回退。"""
        proxy = self.cfg.get("network", {}).get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        started = time.time()

        # 探测是否支持 Range
        total = 0
        accept_ranges = False
        try:
            head = self._session.head(url, timeout=20, headers={"Referer": referer}, proxies=proxies)
            total = int(head.headers.get("content-length", 0) or 0)
            accept_ranges = (head.headers.get("accept-ranges", "") or "").lower() == "bytes"
        except Exception:
            pass

        concurrency = int(self.cfg.get("network", {}).get("concurrency", 8))
        if total > 2 * 1024 * 1024 and accept_ranges and concurrency > 1:
            return self._download_direct_mt(url, dest, referer, result, logger,
                                            total, concurrency, started)

        # 单线程回退
        with self._session.get(url, stream=True, timeout=60,
                               headers={"Referer": referer}, proxies=proxies) as r:
            if r.status_code >= 400:
                raise AppError(ERR_NETWORK, f"HTTP {r.status_code}")
            if not total:
                total = int(r.headers.get("content-length", 0) or 0)
            done = 0
            last = {"t": time.time(), "b": 0}
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if self.cancel_flag and self.cancel_flag():
                        raise AppError(ERR_CANCELLED, "用户取消")
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        self._emit_progress(dest.name, done, total, last, started)
        elapsed = time.time() - started
        result.mark_success(title=dest.stem, filename=dest.name, path=str(dest),
                            size_bytes=done, media_format=dest.suffix.lstrip("."),
                            elapsed_s=elapsed,
                            avg_speed=_avg_speed(done, elapsed),
                            extractor="fallback-sniffer")
        logger.log("video_success", {"path": str(dest)})
        return result

    def _emit_progress(self, filename: str, done: int, total: int, last: dict,
                       started: float, force: bool = False) -> None:
        """汇报进度（带速度与剩余时间），节流到约每 300ms 一次。"""
        now = time.time()
        if not force and now - last["t"] < 0.3:
            return
        speed = (done - last["b"]) / (now - last["t"]) if now > last["t"] else 0.0
        eta = int((total - done) / speed) if speed > 0 and total > done else None
        last["t"], last["b"] = now, done
        self.progress_cb({"event": "downloading",
                          "percent": (done / total * 100) if total else 0.0,
                          "downloaded": done, "total": total,
                          "speed": speed, "eta": eta,
                          "filename": filename})

    def _download_direct_mt(self, url: str, dest: Path, referer: str, result: TaskResult,
                            logger: TaskLogger, total: int, n: int,
                            started: float) -> TaskResult:
        """HTTP Range 多线程分块下载。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        proxy = self.cfg.get("network", {}).get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        n = max(1, min(n, 16))
        chunk = max(total // n, 1)
        ranges: list[tuple[int, int]] = []
        lo = 0
        while lo < total:
            hi = min(lo + chunk - 1, total - 1)
            ranges.append((lo, hi))
            lo = hi + 1

        with open(dest, "wb") as f:
            f.truncate(total)  # 预分配
        state = {"done": 0}
        lock = threading.Lock()
        last = {"t": time.time(), "b": 0}

        def worker(lo: int, hi: int) -> bool:
            headers = {"Range": f"bytes={lo}-{hi}", "Referer": referer, "User-Agent": UA}
            try:
                resp = self._session.get(url, headers=headers, stream=True,
                                         timeout=60, proxies=proxies)
                if resp.status_code not in (200, 206):
                    return False
                with open(dest, "rb+") as f:
                    f.seek(lo)
                    for chunk in resp.iter_content(256 * 1024):
                        if self.cancel_flag and self.cancel_flag():
                            return False
                        if chunk:
                            f.write(chunk)
                            with lock:
                                state["done"] += len(chunk)
                                cur = state["done"]
                            self._emit_progress(dest.name, cur, total, last, started)
                return True
            except Exception:
                return False

        ok = True
        with ThreadPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(worker, lo, hi) for lo, hi in ranges]
            for fut in as_completed(futures):
                if not fut.result():
                    ok = False

        elapsed = time.time() - started
        if self.cancel_flag and self.cancel_flag():
            raise AppError(ERR_CANCELLED, "用户取消")
        size = dest.stat().st_size if dest.exists() else 0
        if not ok or size < total * 0.95:
            raise AppError(ERR_NETWORK, "分块下载不完整，可降低并发数重试")
        self._emit_progress(dest.name, size, total, last, started, force=True)
        result.mark_success(title=dest.stem, filename=dest.name, path=str(dest),
                            size_bytes=size, media_format=dest.suffix.lstrip("."),
                            elapsed_s=elapsed, avg_speed=_avg_speed(size, elapsed),
                            extractor="fallback-sniffer-mt")
        logger.log("video_success", {"path": str(dest), "mt": True, "threads": len(ranges)})
        return result

    def _download_m3u8_ffmpeg(self, url: str, dest: Path, referer: str, result: TaskResult,
                              logger: TaskLogger) -> TaskResult:
        ff = find_ffmpeg()
        if not ff:
            raise AppError(ERR_FFMPEG, "需要 ffmpeg 合并 m3u8 分片")
        dest = dest.with_suffix(".mp4")
        cmd = [ff, "-y", "-headers", f"Referer: {referer}\r\nUser-Agent: {UA}\r\n",
               "-i", url, "-c", "copy", str(dest)]
        self.progress_cb({"event": "downloading", "percent": 0.0, "note": "ffmpeg 正在合并分片…"})
        try:
            popen_kwargs = {}
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # 不弹控制台窗口
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, **popen_kwargs)
            # 后台线程持续消费 stdout，避免 ffmpeg 进度输出写满 PIPE 缓冲区导致死锁
            buf: list[str] = []

            def _pump() -> None:
                try:
                    assert proc.stdout is not None
                    for line in proc.stdout:
                        buf.append(line)
                except Exception:
                    pass

            threading.Thread(target=_pump, daemon=True).start()
            started = time.time()
            while proc.poll() is None:
                if self.cancel_flag and self.cancel_flag():
                    proc.kill()
                    raise AppError(ERR_CANCELLED, "用户取消")
                time.sleep(0.3)
            if proc.returncode != 0:
                err_tail = "".join(buf)[-300:]
                raise AppError(ERR_NETWORK, f"ffmpeg 下载失败: {err_tail}")
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ERR_INTERNAL, str(exc)) from exc
        if not dest.exists():
            raise AppError(ERR_NETWORK, "未生成输出文件")
        size = dest.stat().st_size
        elapsed = time.time() - started
        result.mark_success(title=dest.stem, filename=dest.name, path=str(dest),
                            size_bytes=size, media_format="mp4", elapsed_s=elapsed,
                            avg_speed=_avg_speed(size, elapsed), extractor="fallback-sniffer",
                            segments=0)
        logger.log("video_success", {"path": str(dest)})
        return result


def _load_cookies_file(path: str) -> requests.cookies.RequestsCookieJar:
    """解析 Netscape 格式 cookies.txt。"""
    jar = requests.cookies.RequestsCookieJar()
    try:
        from http.cookiejar import MozillaCookieJar
        mj = MozillaCookieJar(path)
        mj.load(ignore_discard=True, ignore_expires=True)
        for c in mj:
            jar.set_cookie(c)
    except Exception:
        pass
    return jar


def _fallback_filename(url: str) -> str:
    from urllib.parse import urlparse
    base = os.path.basename(urlparse(url).path) or "video.mp4"
    base = re.sub(r'[\\/:*?"<>|]', "_", base)
    return base[:80]
