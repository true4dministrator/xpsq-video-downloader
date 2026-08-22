"""视频下载内核：yt-dlp 主引擎 + 万能兜底嗅探器。"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import requests

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
                    audio_only: bool = False) -> dict:
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
        "noplaylist": True,
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

    def download(self, url: str, save_dir: str, audio_only: bool = False) -> TaskResult:
        import yt_dlp
        task_id = new_task_id()
        result = TaskResult(mode="video", task_id=task_id, url=url, env=version.APP_NAME_EN)
        logger = TaskLogger(task_id)
        result.log_file = logger.file
        logger.log("video_start", {"url": url, "save_dir": save_dir, "audio_only": audio_only})
        try:
            self._started = time.time()
            self._downloaded = 0.0
            opts = _build_ydl_opts(self.cfg, save_dir, self._hook, logger, self.cancel_flag,
                                   audio_only=audio_only)
            if not find_ffmpeg():
                opts["nopart"] = False  # 无 ffmpeg 时单文件流可直接下载
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.progress_cb({"event": "extracting"})
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise AppError(ERR_UNSUPPORTED, "未解析到任何视频信息")
                filename = ydl.prepare_filename(info)
                final = info.get("_filename") or filename
                path = final if os.path.exists(final) else (
                    _find_actual_file(save_dir, info.get("id"), info.get("title"), audio_only))
                # 音频模式：下载完音频流后自行转 MP3（不依赖 ffprobe）
                if audio_only and path:
                    self.progress_cb({"event": "postprocessing",
                                      "postprocessor": "提取音频", "note": "正在转换为 MP3…"})
                    mp3_path = _extract_audio_mp3(path)
                    if mp3_path:
                        path = mp3_path
                    else:
                        raise AppError(ERR_FFMPEG, "音频提取失败")
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


def _extract_audio_mp3(src: str) -> str | None:
    """用 ffmpeg 把音频文件转成 MP3（VBR 最高质量），成功后删除中间文件。"""
    ff = find_ffmpeg()
    if not ff:
        raise AppError(ERR_FFMPEG, "需要 ffmpeg 提取音频")
    dst = Path(src).with_suffix(".mp3")
    cmd = [ff, "-y", "-i", src, "-vn", "-c:a", "libmp3lame", "-q:a", "0", str(dst)]
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kwargs)
    except Exception as exc:
        raise AppError(ERR_FFMPEG, f"音频提取失败: {exc}") from exc
    if proc.returncode != 0 or not dst.exists():
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass
        err_tail = (proc.stderr or "")[-200:]
        raise AppError(ERR_FFMPEG, f"音频提取失败: {err_tail}")
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


# ---------------- 万能兜底嗅探器 ----------------

_MEDIA_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.(?:mp4|webm|m4v|mov|flv|ts|mp3|m4a|aac|ogg|opus)(?:\?[^\s"\'<>\\]*)?', re.I)
_M3U8_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.m3u8(?:\?[^\s"\'<>\\]*)?', re.I)
_BLOB_RE = re.compile(r'blob:https?://[^\s"\'<>]+', re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class FallbackSniffer:
    """yt-dlp 不支持时：从页面 HTML/JS 中嗅探直链。"""

    def __init__(self, cfg: dict | None = None, progress_cb: ProgressCb | None = None,
                 cancel_flag: Callable[[], bool] | None = None):
        self.cfg = cfg or load_config()
        self.progress_cb = progress_cb or (lambda d: None)
        self.cancel_flag = cancel_flag
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        ck = self.cfg.get("cookies", {}).get("cookies_file")
        if ck and Path(ck).exists():
            self._session.cookies = _load_cookies_file(ck)

    def sniff(self, url: str) -> tuple[str | None, str]:
        """返回 (直链, 类型)，类型为 mp4/m3u8/blob/None"""
        try:
            proxy = self.cfg.get("network", {}).get("proxy") or None
            resp = self._session.get(url, timeout=20, allow_redirects=True,
                                     headers={"Referer": url}, proxies={"http": proxy, "https": proxy} if proxy else None)
            html = resp.text
            for m in _M3U8_RE.findall(html):
                return m, "m3u8"
            cands = _MEDIA_RE.findall(html)
            if cands:
                return cands[0], "mp4"
            if _BLOB_RE.search(html):
                return None, "blob"
            return None, None
        except Exception:
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
        proxy = self.cfg.get("network", {}).get("proxy") or None
        started = time.time()
        with self._session.get(url, stream=True, timeout=60,
                               headers={"Referer": referer},
                               proxies={"http": proxy, "https": proxy} if proxy else None) as r:
            if r.status_code >= 400:
                raise AppError(ERR_NETWORK, f"HTTP {r.status_code}")
            total = int(r.headers.get("content-length", 0) or 0)
            done = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if self.cancel_flag and self.cancel_flag():
                        raise AppError(ERR_CANCELLED, "用户取消")
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        self.progress_cb({"event": "downloading",
                                          "percent": (done / total * 100) if total else 0.0,
                                          "downloaded": done, "total": total,
                                          "speed": None, "eta": None,
                                          "filename": dest.name})
        elapsed = time.time() - started
        result.mark_success(title=dest.stem, filename=dest.name, path=str(dest),
                            size_bytes=done, media_format=dest.suffix.lstrip("."),
                            elapsed_s=elapsed,
                            avg_speed=_avg_speed(done, elapsed),
                            extractor="fallback-sniffer")
        logger.log("video_success", {"path": str(dest)})
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
            started = time.time()
            while proc.poll() is None:
                if self.cancel_flag and self.cancel_flag():
                    proc.kill()
                    raise AppError(ERR_CANCELLED, "用户取消")
                time.sleep(0.3)
            if proc.returncode != 0:
                raise AppError(ERR_NETWORK, "ffmpeg 下载失败")
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
