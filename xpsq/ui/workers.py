"""QThread 工作线程：视频下载 / 文章提取，避免阻塞界面。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..errors import ERR_CANCELLED, ERR_UNSUPPORTED
from ..logging_setup import open_log_dir  # noqa: F401  (re-export convenience)


class BaseWorker(QThread):
    progress = Signal(dict)
    finished_ok = Signal(object)   # TaskResult

    def __init__(self, url: str, save_dir: str, cfg: dict, parent=None):
        super().__init__(parent)
        self.url = url
        self.save_dir = save_dir
        self.cfg = cfg
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True


class VideoWorker(BaseWorker):
    """yt-dlp 主引擎；失败且为不支持的站点时，自动落到万能兜底嗅探器。"""

    def __init__(self, url: str, save_dir: str, cfg: dict, use_fallback: bool = True,
                 audio_only: bool = False, audio_format: str = "mp3", playlist: bool = False,
                 parent=None):
        super().__init__(url, save_dir, cfg, parent)
        self.use_fallback = use_fallback
        self.audio_only = audio_only
        self.audio_format = audio_format
        self.playlist = playlist

    def run(self) -> None:
        from ..core.video import FallbackSniffer, VideoDownloader
        try:
            dl = VideoDownloader(self.cfg,
                                 progress_cb=lambda d: self.progress.emit(d),
                                 cancel_flag=lambda: self._cancel)
            result = dl.download(self.url, self.save_dir, audio_only=self.audio_only,
                                 audio_format=self.audio_format, playlist=self.playlist)
            if (result.status == "failed" and result.error_code == ERR_UNSUPPORTED
                    and self.use_fallback and not self.playlist):
                self.progress.emit({"event": "sniffing", "note": "主引擎不支持，尝试万能嗅探…"})
                sniffer = FallbackSniffer(self.cfg,
                                          progress_cb=lambda d: self.progress.emit(d),
                                          cancel_flag=lambda: self._cancel)
                media, kind = sniffer.sniff(self.url)
                if media:
                    result = sniffer.download(media, kind, self.save_dir, self.url)
                else:
                    if kind == "blob":
                        result.friendly = "该页面视频以 blob 流播放，暂无法直接嗅探到直链"
                    else:
                        diag = getattr(sniffer, "diag", {}) or {}
                        if diag.get("render_error"):
                            result.friendly = (
                                f"无头浏览器渲染失败（{diag['render_error'][:120]}）。"
                                "请先在 设置 → 浏览器会话 登录该站点一次；"
                                "或浏览器 F12 → Network → Media 找直链粘贴回来")
                        elif diag.get("page_state"):
                            result.friendly = (
                                f"页面处于异常状态（{diag['page_state']}），"
                                "视频数据未返回，请稍后重试或换浏览器打开确认")
                        elif diag.get("html_len", 0) < 2000:
                            result.friendly = (
                                "该页面是纯 JS 渲染（内容由脚本动态加载），已尝试 API 接口探测仍未找到直链。"
                                "自救方法：浏览器按 F12 → Network → 筛选 Media → 播放视频，"
                                "把出现的 mp4/m3u8 链接复制粘贴回来即可下载")
                        elif diag.get("error"):
                            result.friendly = f"嗅探页面失败：{diag['error']}"
                        else:
                            result.friendly = "该网址暂不支持且嗅探未找到直链，请反馈给开发者"
            elif result.status == "failed" and self._cancel:
                result.status = "cancelled"
                result.error_code = ERR_CANCELLED
            self.finished_ok.emit(result)
        except Exception as exc:  # 兜底：任何意外异常都转成带信息的失败结果
            from ..core.result import TaskResult
            from ..errors import ERR_INTERNAL, make_error
            r = TaskResult(mode="video", url=self.url)
            err = make_error(ERR_INTERNAL, str(exc), exc)
            r.mark_failed(err.code, err.friendly, err.message, err.dev_detail)
            self.finished_ok.emit(r)


class ArticleWorker(BaseWorker):
    def __init__(self, url: str, save_dir: str, cfg: dict, output_format: str = "html", parent=None):
        super().__init__(url, save_dir, cfg, parent)
        self.output_format = output_format

    def run(self) -> None:
        from ..core.article import ArticleExtractor
        try:
            ex = ArticleExtractor(self.cfg,
                                  progress_cb=lambda d: self.progress.emit(d),
                                  cancel_flag=lambda: self._cancel)
            result = ex.extract(self.url, self.save_dir, self.output_format)
            if self._cancel and result.status != "success":
                result.status = "cancelled"
                result.error_code = ERR_CANCELLED
            self.finished_ok.emit(result)
        except Exception as exc:
            from ..core.result import TaskResult
            from ..errors import ERR_INTERNAL, make_error
            r = TaskResult(mode="article", url=self.url)
            err = make_error(ERR_INTERNAL, str(exc), exc)
            r.mark_failed(err.code, err.friendly, err.message, err.dev_detail)
            self.finished_ok.emit(r)
