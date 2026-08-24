"""Playwright 真渲染：JS 壳页面最后的兜底。

用系统 Edge（channel=msedge，无需下载浏览器）无头渲染页面：
1. 捕获网络响应中的媒体直链（m3u8/mp4/音频）
2. 返回渲染后的 DOM（再走一遍嗅探器 L0-L1）
"""
from __future__ import annotations

import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_MEDIA_HINT = (".m3u8", ".mp4", ".webm", ".m4a", ".mp3", ".ts", ".mov", ".flv")
_MEDIA_CT = ("mpegurl", "video/", "audio/", "application/octet-stream")


def render_page(url: str, wait_ms: int = 6000, timeout_ms: int = 20000,
                extra_headers: dict | None = None) -> tuple[str | None, list[str]]:
    """渲染页面，返回 (渲染后 HTML, 捕获的媒体直链列表)。失败返回 (None, [])。

    懒加载 playwright：未安装时直接返回空结果，不影响其他功能。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, []

    media: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx = browser.new_context(user_agent=UA)
            if extra_headers:
                ctx.set_extra_http_headers(extra_headers)
            page = ctx.new_page()

            def _on_response(resp) -> None:
                try:
                    ct = (resp.headers.get("content-type") or "").lower()
                    u = resp.url.lower()
                    if any(h in u for h in _MEDIA_HINT) or any(c in ct for c in _MEDIA_CT):
                        if u.startswith(("http://", "https://")):
                            media.append(resp.url)
                except Exception:
                    pass

            page.on("response", _on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(wait_ms)
                # 额外等待 video 元素出现（最晚再等 6 秒）
                try:
                    page.wait_for_selector("video, source, audio", timeout=6000)
                except Exception:
                    pass
            except Exception:
                pass
            html = page.content()
            browser.close()
        return html, list(dict.fromkeys(media))
    except Exception:
        return None, []
