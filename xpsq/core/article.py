"""文章提取内核：trafilatura 提取正文 + 插图下载 + HTML/Markdown/纯文本输出。"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable

import requests

from .. import version
from ..config import load_config
from ..errors import (ERR_EXTRACT_EMPTY, ERR_FS, ERR_IMG_PARTIAL,
                      ERR_INTERNAL, ERR_NETWORK, AppError, make_error)
from ..logging_setup import TaskLogger, new_task_id
from .result import TaskResult

ProgressCb = Callable[[dict], None]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class ArticleExtractor:
    def __init__(self, cfg: dict | None = None, progress_cb: ProgressCb | None = None,
                 cancel_flag: Callable[[], bool] | None = None):
        self.cfg = cfg or load_config()
        self.progress_cb = progress_cb or (lambda d: None)
        self.cancel_flag = cancel_flag

    def extract(self, url: str, save_dir: str, output_format: str = "html") -> TaskResult:
        import trafilatura
        task_id = new_task_id()
        result = TaskResult(mode="article", task_id=task_id, url=url, env=version.APP_NAME_EN)
        logger = TaskLogger(task_id)
        result.log_file = logger.file
        started = time.time()
        try:
            self.progress_cb({"event": "fetching", "note": "正在抓取网页…"})
            html = self._fetch(url)
            if not html:
                raise AppError(ERR_NETWORK, "网页抓取失败或内容为空")
            logger.log("article_fetch_ok", {"size": len(html)})

            self.progress_cb({"event": "extracting", "note": "正在识别正文…"})
            meta = trafilatura.extract_metadata(html)
            body_html = trafilatura.extract(html, output_format="html",
                                            include_images=True, with_metadata=False)
            if not body_html or len(body_html) < 80:
                raise AppError(ERR_EXTRACT_EMPTY, "未识别到文章正文")

            title = (meta.title if meta and meta.title else "") or _guess_title(html) or "未命名文章"
            author = meta.author if meta and meta.author else ""
            date = meta.date if meta and meta.date else ""
            if not date and meta and meta.date_modified:
                date = meta.date_modified

            out_root = Path(save_dir) / _sanitize(title)
            out_root.mkdir(parents=True, exist_ok=True)
            assets_dir = out_root / "assets"
            assets_dir.mkdir(exist_ok=True)

            cfg_a = self.cfg.get("article", {})
            img_total, img_ok, failed = 0, 0, []
            if cfg_a.get("download_images", True):
                self.progress_cb({"event": "images", "note": "正在下载插图…"})
                body_html, img_total, img_ok, failed = self._process_images(
                    body_html, assets_dir, url, result, logger)

            self.progress_cb({"event": "writing", "note": "正在生成文件…"})
            if output_format == "html":
                final_path = out_root / "index.html"
                final_path.write_text(_wrap_html(title, author, date, body_html), encoding="utf-8")
            elif output_format == "markdown":
                final_path = out_root / "article.md"
                final_path.write_text(_build_markdown(title, author, date, body_html),
                                      encoding="utf-8")
            else:
                final_path = out_root / "article.txt"
                text = trafilatura.extract(html, output_format="txt", include_images=False) or ""
                final_path.write_text(text, encoding="utf-8")

            result.mark_success(
                title=title, filename=final_path.name, path=str(final_path),
                img_total=img_total, img_ok=img_ok, img_failed=failed,
                extractor="trafilatura", elapsed_s=time.time() - started,
            )
            if failed:
                result.friendly = "部分插图下载失败，正文已保存"
                result.error_code = ERR_IMG_PARTIAL
            logger.log("article_success", {"path": str(final_path), "imgs": f"{img_ok}/{img_total}"})
            return result
        except AppError as exc:
            result.mark_failed(exc.code, exc.friendly, exc.message, exc.dev_detail)
            logger.log("article_failed", {"code": exc.code, "raw": str(exc)[:500]})
            return result
        except Exception as exc:
            app_err = make_error(ERR_INTERNAL, str(exc), exc)
            result.mark_failed(app_err.code, app_err.friendly, app_err.message, app_err.dev_detail)
            logger.log("article_failed", {"code": app_err.code, "raw": str(exc)[:500]})
            return result
        finally:
            logger.close()

    def _fetch(self, url: str) -> str:
        proxy = self.cfg.get("network", {}).get("proxy") or None
        headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
                   "Referer": url}
        cookies = None
        ck = self.cfg.get("cookies", {}).get("cookies_file")
        if ck and Path(ck).exists():
            from .video import _load_cookies_file
            cookies = _load_cookies_file(ck)
        try:
            resp = requests.get(url, headers=headers, timeout=25, cookies=cookies,
                                proxies={"http": proxy, "https": proxy} if proxy else None)
            resp.encoding = resp.apparent_encoding or resp.encoding
            if resp.status_code >= 400:
                raise AppError(ERR_NETWORK, f"HTTP {resp.status_code}")
            return resp.text
        except AppError:
            raise
        except Exception as exc:
            raise AppError(ERR_NETWORK, f"抓取失败: {exc}") from exc

    def _process_images(self, body_html: str, assets_dir: Path, page_url: str,
                        result: TaskResult, logger: TaskLogger) -> tuple[str, int, int, list[str]]:
        try:
            import lxml.html
        except ImportError:
            return body_html, 0, 0, []

        proxy = self.cfg.get("network", {}).get("proxy") or None
        max_mb = float(self.cfg.get("article", {}).get("max_image_size_mb", 20))
        doc = lxml.html.fromstring(body_html)
        imgs = doc.xpath("//img")
        total, ok, failed = len(imgs), 0, []
        for i, img in enumerate(imgs, 1):
            if self.cancel_flag and self.cancel_flag():
                break
            src = img.get("src") or img.get("data-src") or ""
            if not src or src.startswith("data:"):
                failed.append(src[:60])
                continue
            from urllib.parse import urljoin
            abs_url = urljoin(page_url, src)
            if not abs_url.startswith("http"):
                failed.append(abs_url[:60])
                continue
            ext = _guess_img_ext(abs_url)
            fname = f"img_{i:03d}{ext}"
            dest = assets_dir / fname
            try:
                resp = requests.get(abs_url, headers={"User-Agent": UA, "Referer": page_url},
                                    timeout=20, stream=True,
                                    proxies={"http": proxy, "https": proxy} if proxy else None)
                resp.raise_for_status()
                size_limit = max_mb * 1024 * 1024
                total_bytes = 0
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        if chunk:
                            f.write(chunk)
                            total_bytes += len(chunk)
                            if total_bytes > size_limit:
                                f.close()
                                dest.unlink(missing_ok=True)
                                raise AppError(ERR_FS, "图片超过体积上限")
                img.set("src", f"assets/{fname}")
                ok += 1
                self.progress_cb({"event": "image_progress", "done": ok, "total": total,
                                  "note": f"下载插图 {ok}/{total}"})
            except Exception as exc:
                failed.append(f"{abs_url[:70]} ({type(exc).__name__})")
                logger.log("img_failed", {"url": abs_url[:200], "err": str(exc)[:200]})
        new_html = lxml.html.tostring(doc, encoding="unicode")
        return new_html, total, ok, failed


def _sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .")
    return name[:60] or "article"


def _guess_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        if t:
            return t[:80]
    return ""


def _guess_img_ext(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".bmp"):
        if p.endswith(ext):
            return ext
    return ".jpg"


def _wrap_html(title: str, author: str, date: str, body: str) -> str:
    meta = " · ".join(x for x in (author, date) if x)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>body{{max-width:760px;margin:0 auto;padding:2rem 1.5rem;font:16px/1.8 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#222}}
h1{{font-size:1.8rem;margin-bottom:.3rem}}img{{max-width:100%;height:auto;border-radius:8px}}a{{color:#1a6fb5}}
.meta{{color:#777;font-size:.9rem;margin-bottom:1.5rem}}</style></head>
<body><h1>{_esc(title)}</h1>
<p class="meta">{_esc(meta)}</p>
{body}
<hr><p style="color:#999;font-size:.85rem">由 下片神器 提取保存</p></body></html>"""


def _build_markdown(title: str, author: str, date: str, body_html: str) -> str:
    meta = " · ".join(x for x in (author, date) if x)
    text = re.sub(r"<[^>]+>", "", body_html)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', body_html)
    lines = [f"# {title}", ""]
    if meta:
        lines += [f"> {meta}", ""]
    lines.append(text)
    if imgs:
        lines += ["", "## 插图", ""]
        for i, src in enumerate(imgs, 1):
            lines.append(f"![图{i}]({src})")
    return "\n".join(lines)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))
