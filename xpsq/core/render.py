"""Playwright 真渲染：JS 壳页面最后的兜底 + 浏览器一键登录会话。

用系统 Edge（channel=msedge，无需下载浏览器）：
- render_page：无头渲染页面 + 捕获网络媒体直链；若存在已保存的浏览器会话则自动带上 cookies
- login_session：弹出真实 Edge 窗口让用户登录目标站一次，把 storage state（cookies/登录态）
  保存到本地文件，之后渲染/嗅探自动复用，能救 ukdevilz 这类 WAF 站
"""
from __future__ import annotations

import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_MEDIA_HINT = (".m3u8", ".mp4", ".webm", ".m4a", ".mp3", ".ts", ".mov", ".flv")
_MEDIA_CT = ("mpegurl", "video/", "audio/", "application/octet-stream")

render_last_error = ""  # 最近一次渲染失败的原因（诊断用）


def login_session(target_url: str, state_path: str, close_timeout_s: int = 300) -> bool:
    """弹出真实 Edge 窗口，用户访问/登录目标站后关闭窗口即完成，保存会话。

    state_path 保存 storage state（含 cookies / localStorage）。
    返回是否成功保存。超时（close_timeout_s）未关闭窗口视为取消。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=False)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            # 等用户操作完并关闭浏览器窗口
            deadline = time.time() + close_timeout_s
            while browser.is_connected():
                if time.time() > deadline:
                    break
                time.sleep(0.5)
            ctx.storage_state(path=state_path)
            try:
                browser.close()
            except Exception:
                pass
        return True
    except Exception:
        return False


def render_page(url: str, wait_ms: int = 6000, timeout_ms: int = 20000,
                extra_headers: dict | None = None,
                state_path: str | None = None) -> tuple[str | None, list[str]]:
    """渲染页面，返回 (渲染后 HTML, 捕获的媒体直链列表)。失败返回 (None, [])。

    state_path：已保存的浏览器会话（storage state JSON），传入则自动带 cookies/登录态。
    懒加载 playwright：未安装时直接返回空结果，不影响其他功能。
    失败原因记录到模块级 render_last_error（供诊断）。
    """
    global render_last_error
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        render_last_error = f"playwright import: {e}"
        return None, []

    media: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            ctx_kwargs = {"user_agent": UA}
            if state_path:
                try:
                    ctx_kwargs["storage_state"] = state_path
                except Exception:
                    pass
            ctx = browser.new_context(**ctx_kwargs)
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
    except Exception as e:
        render_last_error = f"render: {e}"
        return None, []
