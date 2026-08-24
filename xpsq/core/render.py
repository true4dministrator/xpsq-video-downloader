"""Playwright 真渲染：JS 壳页面最后的兜底 + 浏览器一键登录会话。

支持三种系统浏览器引擎（无需下载任何浏览器）：
- msedge：系统 Edge（Windows 自带，默认）
- chrome：系统 Chrome（如已安装）
- firefox：系统 Firefox（如已安装）

- render_page：无头渲染页面 + 捕获网络媒体直链；若存在已保存的浏览器会话则自动带上 cookies
- login_session：弹出真实浏览器窗口让用户登录目标站一次，把 storage state（cookies/登录态）
  保存到本地文件，之后渲染/嗅探自动复用，能救风控型 WAF 站
"""
from __future__ import annotations

import os
import sys
import threading
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_MEDIA_HINT = (".m3u8", ".mp4", ".webm", ".m4a", ".mp3", ".ts", ".mov", ".flv")
_MEDIA_CT = ("mpegurl", "video/", "audio/", "application/octet-stream")

render_last_error = ""  # 最近一次渲染失败的原因（诊断用）

# 登录/渲染过程日志（供排障）
_session_log: list[str] = []


def _slog(msg: str) -> None:
    """记录浏览器会话过程日志（内存 + 追加到 LOGS_DIR/browser_session.log）。"""
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    _session_log.append(line)
    try:
        from ..config import LOGS_DIR
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOGS_DIR / "browser_session.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# 引擎 → (playwright 启动器属性, channel)
_ENGINES = {
    "msedge": ("chromium", "msedge"),
    "chrome": ("chromium", "chrome"),
    "firefox": ("firefox", None),  # 用 playwright 内置 firefox 构建
}


def _ensure_browser_path() -> None:
    """PyInstaller 打包版：浏览器构建位于 _internal/ms-playwright，提前告知 playwright。"""
    if getattr(sys, "frozen", False):
        try:
            internal = os.path.join(os.path.dirname(sys.executable), "_internal", "ms-playwright")
            if os.path.isdir(internal):
                os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", internal)
        except Exception:
            pass


def _launch_browser(p, engine: str, headless: bool):
    """按引擎启动浏览器。返回 browser 或抛异常（原因写入 render_last_error）。"""
    global render_last_error
    name, channel = _ENGINES.get(engine, _ENGINES["msedge"])
    browser_type = getattr(p, name)
    kwargs: dict = {"headless": headless}
    if channel:
        kwargs["channel"] = channel
    try:
        return browser_type.launch(**kwargs)
    except Exception as e:
        render_last_error = f"启动 {engine} 失败: {e}"
        raise


def login_session(target_url: str, state_path: str, engine: str = "msedge",
                  close_timeout_s: int = 180) -> bool:
    """弹出真实浏览器窗口，用户访问/登录目标站后关闭窗口即完成，保存会话。

    state_path 保存 storage state（含 cookies / localStorage）。
    返回是否成功保存。超时（close_timeout_s）未关闭窗口视为取消。
    关窗检测三重保险：page close 事件 + browser disconnected + 后台轮询 ctx.pages。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _slog(f"playwright import 失败: {e}")
        return False
    _ensure_browser_path()
    _slog(f"启动登录会话 engine={engine} url={target_url[:60]}")
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p, engine, headless=False)
            _slog("浏览器已启动")
            ctx = browser.new_context()
            page = ctx.new_page()
            done = threading.Event()

            def _all_closed() -> bool:
                try:
                    return not ctx.pages
                except Exception:
                    return True

            def _on_close(_pg) -> None:
                _slog(f"页面关闭事件触发, 剩余页面: {len(ctx.pages)}")
                if _all_closed():
                    done.set()

            def _on_disconnected() -> None:
                _slog("浏览器断连事件触发")
                done.set()

            page.on("close", _on_close)
            browser.on("disconnected", _on_disconnected)

            def _poll() -> None:
                try:
                    while not done.is_set():
                        if _all_closed():
                            _slog("轮询检测到所有页面已关闭")
                            done.set()
                        time.sleep(0.5)
                except Exception:
                    done.set()

            threading.Thread(target=_poll, daemon=True).start()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                _slog("goto 完成")
            except Exception as e:
                _slog(f"goto 异常(继续等待关窗): {str(e)[:100]}")
            done.wait(timeout=close_timeout_s)
            _slog("检测到关窗/超时，保存会话")
            ctx.storage_state(path=state_path)
            _slog("会话已保存")
            try:
                browser.close()
            except Exception:
                pass
        return True
    except Exception as e:
        _slog(f"login_session 异常: {str(e)[:150]}")
        return False


def render_page(url: str, wait_ms: int = 6000, timeout_ms: int = 20000,
                extra_headers: dict | None = None,
                state_path: str | None = None,
                engine: str = "msedge") -> tuple[str | None, list[str]]:
    """渲染页面，返回 (渲染后 HTML, 捕获的媒体直链列表)。失败返回 (None, [])。

    state_path：已保存的浏览器会话（storage state JSON），传入则自动带 cookies/登录态。
    engine：msedge / chrome / firefox。
    懒加载 playwright：未安装时直接返回空结果，不影响其他功能。
    失败原因记录到模块级 render_last_error（供诊断）。
    """
    global render_last_error
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        render_last_error = f"playwright import: {e}"
        return None, []
    _ensure_browser_path()

    media: list[str] = []
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p, engine, headless=True)
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
