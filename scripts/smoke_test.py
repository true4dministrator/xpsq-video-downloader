#!/usr/bin/env python3
"""核心功能冒烟测试（无 GUI）：视频下载 / 文章提取 / 兜底嗅探。"""
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / "test_output"
OUT.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent.parent))


def hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    from xpsq.config import load_config
    from xpsq.core.ffmpeg import check_ffmpeg

    cfg = load_config()
    ok, info = check_ffmpeg()
    print(f"[env] ffmpeg: {'OK - ' + info if ok else 'MISSING'}")

    # ---- 1. 文章提取 ----
    hr("1. 文章提取 (Wikipedia)")
    from xpsq.core.article import ArticleExtractor
    ex = ArticleExtractor(cfg, progress_cb=lambda d: print(f"   [progress] {d.get('event')}"))
    r = ex.extract("https://zh.wikipedia.org/wiki/%E5%A4%A7%E7%86%8A%E7%8C%AB",
                   str(OUT / "article"), "html")
    print(f"   status={r.status} code={r.error_code} title={r.title!r}")
    print(f"   path={r.path} imgs={r.img_ok}/{r.img_total} friendly={r.friendly!r}")
    if r.status != "success" and r.error_code != "ERR_IMG_PARTIAL":
        print("   [FAIL]", r.raw_exception[-300:])

    # ---- 2. 视频下载（直链 mp4，走 yt-dlp）----
    hr("2. 视频下载 (yt-dlp 直链)")
    from xpsq.core.video import VideoDownloader
    dl = VideoDownloader(cfg, progress_cb=lambda d: print(
        f"   [progress] {d.get('event')} pct={d.get('percent', 0):.0f}%"))
    r2 = dl.download("https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/"
                     "Big_Buck_Bunny_360_10s_1MB.mp4", str(OUT / "video"))
    print(f"   status={r2.status} code={r2.error_code} title={r2.title!r}")
    print(f"   path={r2.path} size={r2.size_bytes} fmt={r2.media_format}")
    if r2.status != "success":
        print("   [FAIL]", r2.raw_exception[-300:])

    # ---- 3. 兜底嗅探 ----
    hr("3. 兜底嗅探")
    from xpsq.core.video import FallbackSniffer
    sn = FallbackSniffer(cfg)
    media, kind = sn.sniff("https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/"
                           "Big_Buck_Bunny_360_10s_1MB.mp4")
    print(f"   sniff -> kind={kind} media={media}")

    print("\n[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
