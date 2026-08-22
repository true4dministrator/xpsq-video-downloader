"""错误码体系：用户看友好文案，开发者看原始异常。"""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any


# 错误码常量
ERR_UNSUPPORTED = "ERR_UNSUPPORTED"
ERR_NETWORK = "ERR_NETWORK"
ERR_ANTIBOT = "ERR_ANTIBOT"
ERR_COOKIE = "ERR_COOKIE"
ERR_DRM = "ERR_DRM"
ERR_FFMPEG = "ERR_FFMPEG"
ERR_FS = "ERR_FS"
ERR_INTERNAL = "ERR_INTERNAL"
ERR_EXTRACT_EMPTY = "ERR_EXTRACT_EMPTY"
ERR_IMG_PARTIAL = "ERR_IMG_PARTIAL"
ERR_CANCELLED = "ERR_CANCELLED"

# 错误码 -> 用户友好文案
FRIENDLY_MESSAGES = {
    ERR_UNSUPPORTED: "该网址暂不支持，可尝试其他链接或反馈给开发者",
    ERR_NETWORK: "网络出错：连接失败、超时或被服务器拒绝，请检查网络后重试",
    ERR_ANTIBOT: "被网站风控拦截，已自动重试仍失败，可尝试稍后再试或更换网络",
    ERR_COOKIE: "该内容需要登录/会员权限，请先在设置中导入 cookies 后重试",
    ERR_DRM: "该视频受版权保护（DRM），无法下载",
    ERR_FFMPEG: "视频合并/转码失败，请确认 ffmpeg 已随程序正确安装",
    ERR_FS: "文件系统错误：空间不足、目录不可写或文件名非法",
    ERR_INTERNAL: "发生未知内部错误，请复制完整日志反馈给开发者",
    ERR_EXTRACT_EMPTY: "未识别到文章正文，可能是纯 JS 渲染页面或页面结构特殊",
    ERR_IMG_PARTIAL: "部分插图下载失败，正文已正常保存",
    ERR_CANCELLED: "任务已取消",
}


@dataclass
class AppError(Exception):
    """统一应用错误。code 为机器可读错误码，dev_detail 为开发者信息。"""

    code: str = ERR_INTERNAL
    message: str = ""
    dev_detail: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    @property
    def friendly(self) -> str:
        return FRIENDLY_MESSAGES.get(self.code, FRIENDLY_MESSAGES[ERR_INTERNAL])


def classify_ytdlp_error(exc: BaseException) -> AppError:
    """把 yt-dlp 抛出的异常归类为 AppError。"""
    text = str(exc).lower()
    ctx = {"raw": str(exc)}
    # 站点改版导致提取器失效（yt-dlp 上游 bug，如 Yandex "Unable to extract data_raw"）
    if "unable to extract" in text or "please report this issue" in text:
        return AppError(
            code=ERR_UNSUPPORTED,
            message="该站点的解析器已失效（站点可能改版，上游 yt-dlp 已知问题待修复）。"
                    "可尝试粘贴视频/音频的直链下载，或等待软件升级后重试",
            dev_detail="".join(__import__("traceback").format_exception(
                type(exc), exc, exc.__traceback__))[-3000:],
            context=ctx)
    if "unsupportedurl" in text or "unsupported" in text or "not supported" in text or "no video" in text:
        code = ERR_UNSUPPORTED
    elif "drm" in text or "widevine" in text or "fairplay" in text or "playready" in text:
        code = ERR_DRM
    elif ("login" in text or "member" in text or "only available" in text or "cookies" in text
          or "sign in" in text or "premium" in text or "private video" in text):
        code = ERR_COOKIE
    elif "cloudflare" in text or "captcha" in text or "bot" in text or "challenge" in text or "403" in text or "429" in text:
        code = ERR_ANTIBOT
    elif "ffmpeg" in text or "merge" in text or "postprocess" in text:
        code = ERR_FFMPEG
    elif ("disk" in text or "no space" in text or "permission" in text or "not enough" in text
          or "filename" in text and "illegal" in text):
        code = ERR_FS
    elif ("timeout" in text or "connection" in text or "network" in text or "ssl" in text
          or "resolve" in text or "http error" in text):
        code = ERR_NETWORK
    else:
        code = ERR_INTERNAL
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:]
    return AppError(code=code, message=str(exc)[:500], dev_detail=tb, context=ctx)


def make_error(code: str, message: str = "", exc: BaseException | None = None) -> AppError:
    tb = ""
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:]
    return AppError(code=code, message=message or FRIENDLY_MESSAGES.get(code, ""), dev_detail=tb)
