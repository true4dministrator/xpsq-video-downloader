"""设置页：通用 / 网络与代理 / 下载 / 文章提取 / Cookies / 关于。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, APP_TAGLINE, APP_VERSION
from ..config import load_config, save_config
from ..core.ffmpeg import check_ffmpeg
from ..logging_setup import open_log_dir
from .theme import C, apply_theme

GITHUB_URL = "https://github.com/true4dministrator/xpsq-video-downloader"
BLOG_URL = "https://zchlab.space"

CATEGORIES = ["通用", "网络与代理", "下载", "文章提取", "Cookies 登录", "浏览器会话", "关于"]


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(10)

        lay = QHBoxLayout()

        # 左：分类
        self.cat_list = QListWidget()
        self.cat_list.setFixedWidth(140)
        for c in CATEGORIES:
            QListWidgetItem(c, self.cat_list)
        self.cat_list.currentRowChanged.connect(self._switch)
        lay.addWidget(self.cat_list)

        # 右：内容
        self.stack = QStackedWidget()
        self._pages = {
            "通用": self._page_general(),
            "网络与代理": self._page_network(),
            "下载": self._page_download(),
            "文章提取": self._page_article(),
            "Cookies 登录": self._page_cookies(),
            "浏览器会话": self._page_browser(),
            "关于": self._page_about(),
        }
        for name in CATEGORIES:
            self.stack.addWidget(self._pages[name])
        lay.addWidget(self.stack, 1)

        outer.addLayout(lay, 1)

        # 底部操作栏
        btn_row = QHBoxLayout()
        b_reset = QPushButton("恢复默认")
        b_reset.clicked.connect(self._reset_defaults)
        b_save = QPushButton("保存设置")
        b_save.setObjectName("primary")
        b_save.clicked.connect(lambda: self.save())
        btn_row.addWidget(b_reset)
        btn_row.addStretch()
        btn_row.addWidget(b_save)
        outer.addLayout(btn_row)

        # 主题切换即时生效
        self.cb_theme.currentIndexChanged.connect(lambda _: self.save())

        self.cat_list.setCurrentRow(0)

    def _reset_defaults(self) -> None:
        from PySide6.QtWidgets import QApplication
        from ..config import DEFAULT_CONFIG, CONFIG_FILE
        try:
            CONFIG_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        self.cfg = dict(DEFAULT_CONFIG)
        save_config(self.cfg)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, DEFAULT_CONFIG["general"]["theme"])
        win = self.window()
        if win is not None and hasattr(win, "rebuild_theme"):
            win.rebuild_theme()

    def _scrolled(self, widget: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _switch(self, row: int) -> None:
        if 0 <= row < len(CATEGORIES):
            self.stack.setCurrentIndex(row)

    def _page(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(8, 4, 20, 8)
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft)
        return w, form

    def _row(self, form: QFormLayout, label: str, widget: QWidget, hint: str = "") -> None:
        form.addRow(label, widget)
        if hint:
            h = QLabel(hint)
            h.setStyleSheet("color:#999;font-size:11px;")
            h.setWordWrap(True)
            form.addRow("", h)

    # ---------------- 通用 ----------------
    def _page_general(self) -> QWidget:
        w, form = self._page()
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["跟随系统", "浅色", "深色"])
        self.cb_theme.setCurrentIndex({"system": 0, "light": 1, "dark": 2}.get(
            self.cfg.get("general", {}).get("theme", "system"), 0))
        self._row(form, "主题", self.cb_theme)
        self.sp_history = QSpinBox()
        self.sp_history.setRange(20, 1000)
        self.sp_history.setValue(int(self.cfg.get("general", {}).get("history_limit", 200)))
        self._row(form, "历史记录条数", self.sp_history)
        self.cb_loglevel = QComboBox()
        self.cb_loglevel.addItems(["INFO", "DEBUG"])
        self.cb_loglevel.setCurrentText(self.cfg.get("general", {}).get("log_level", "INFO"))
        self._row(form, "日志级别", self.cb_loglevel, "DEBUG 会记录更多请求细节，便于排查问题")
        w = self._scrolled(w)
        return w

    # ---------------- 网络与代理 ----------------
    def _page_network(self) -> QWidget:
        w, form = self._page()
        net = self.cfg.get("network", {})
        self.cb_imp = QComboBox()
        self.cb_imp.addItems(["chrome", "edge", "safari", "off"])
        self.cb_imp.setCurrentText(net.get("impersonate", "chrome"))
        self._row(form, "伪装目标", self.cb_imp, "模仿真实浏览器 TLS 指纹，绕过站点识别")
        self.sp_conc = QSpinBox()
        self.sp_conc.setRange(1, 32)
        self.sp_conc.setValue(int(net.get("concurrency", 8)))
        self._row(form, "并发分片数", self.sp_conc, "越大越快，越容易被站点限速")
        self.sp_sleep = QSpinBox()
        self.sp_sleep.setRange(0, 60)
        self.sp_sleep.setValue(int(net.get("sleep_interval", 2)))
        self._row(form, "请求间隔(秒)", self.sp_sleep, "缓解风控，建议 ≥ 2s")
        self.ed_proxy = QLineEdit(net.get("proxy", ""))
        self.ed_proxy.setPlaceholderText("http://127.0.0.1:7890 · 留空为直连")
        self._row(form, "HTTP 代理", self.ed_proxy)
        self.cb_tls = QCheckBox("启用 TLS 指纹伪装")
        self.cb_tls.setChecked(bool(net.get("tls_impersonation", True)))
        self._row(form, "TLS 伪装", self.cb_tls)
        return self._scrolled(w)

    # ---------------- 下载 ----------------
    def _page_download(self) -> QWidget:
        w, form = self._page()
        dl = self.cfg.get("download", {})
        self.ed_dir = QLineEdit(dl.get("default_dir", str(Path.home() / "Downloads")))
        b = QPushButton("浏览")
        def pick():
            d = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self.ed_dir.text())
            if d:
                self.ed_dir.setText(d)
        b.clicked.connect(pick)
        row = QHBoxLayout()
        row.addWidget(self.ed_dir, 1)
        row.addWidget(b)
        self._row(form, "默认保存目录", self._h(row))
        self.cb_quality = QComboBox()
        self.cb_quality.addItems(["最佳画质", "1080p", "720p"])
        self.cb_quality.setCurrentIndex({"best": 0, "1080": 1, "720": 2}.get(
            dl.get("default_quality", "best"), 0))
        self._row(form, "默认画质", self.cb_quality)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(["mp4", "mkv", "原始格式"])
        self.cb_fmt.setCurrentText({"mp4": "mp4", "mkv": "mkv"}.get(dl.get("default_format", "mp4"), "原始格式"))
        self._row(form, "默认封装", self.cb_fmt)
        self.cb_audio = QCheckBox("默认仅音频（MP3）")
        self.cb_audio.setChecked(bool(dl.get("audio_only", False)))
        self._row(form, "音频模式", self.cb_audio, "勾选后下载时只提取音频，保存为 MP3")
        self.cb_sb = QCheckBox("跳过赞助段落 (SponsorBlock)")
        self.cb_sb.setChecked(bool(dl.get("sponsorblock", False)))
        self._row(form, "SponsorBlock", self.cb_sb, "仅部分站点支持，自动剪掉视频内赞助片段")
        self.cb_sub = QCheckBox("下载字幕")
        self.cb_sub.setChecked(bool(dl.get("subtitles", False)))
        self._row(form, "字幕", self.cb_sub)
        self.sp_mt = QSpinBox()
        self.sp_mt.setRange(1, 5)
        self.sp_mt.setValue(int(dl.get("max_concurrent", 3)))
        self._row(form, "同时下载任务数", self.sp_mt,
                 "多任务并行数：几个下载同时进行，其余自动排队（同站点最多 2 个并行，防封）")
        self.cb_pl = QCheckBox("默认整批下载播放列表/歌单")
        self.cb_pl.setChecked(bool(dl.get("playlist", False)))
        self._row(form, "播放列表", self.cb_pl, "勾选后链接是播放列表/歌单时默认下载全部")
        return self._scrolled(w)

    def _h(self, lay: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(lay)
        return w

    # ---------------- 文章提取 ----------------
    def _page_article(self) -> QWidget:
        w, form = self._page()
        art = self.cfg.get("article", {})
        self.cb_a_fmt = QComboBox()
        self.cb_a_fmt.addItems(["HTML（含插图，推荐）", "Markdown", "纯文本"])
        self.cb_a_fmt.setCurrentIndex({"html": 0, "markdown": 1, "txt": 2}.get(
            art.get("default_output_format", "html"), 0))
        self._row(form, "默认输出格式", self.cb_a_fmt)
        self.cb_a_img = QCheckBox("下载插图到本地")
        self.cb_a_img.setChecked(bool(art.get("download_images", True)))
        self._row(form, "插图", self.cb_a_img)
        self.sp_max_img = QSpinBox()
        self.sp_max_img.setRange(1, 200)
        self.sp_max_img.setValue(int(art.get("max_image_size_mb", 20)))
        self._row(form, "单张图片上限(MB)", self.sp_max_img, "超过上限的图片跳过，避免撑爆磁盘")
        return self._scrolled(w)

    # ---------------- Cookies ----------------
    def _page_cookies(self) -> QWidget:
        w, form = self._page()
        ck = self.cfg.get("cookies", {})
        self.ed_cookies = QLineEdit(ck.get("cookies_file", ""))
        self.ed_cookies.setPlaceholderText("cookies.txt 路径，留空表示未导入")
        b = QPushButton("选择文件")
        def pick():
            d = QFileDialog.getOpenFileName(self, "选择 cookies.txt",
                                            str(Path.home()), "Cookies (*.txt);;所有文件 (*)")
            if d[0]:
                self.ed_cookies.setText(d[0])
        b.clicked.connect(pick)
        row = QHBoxLayout()
        row.addWidget(self.ed_cookies, 1)
        row.addWidget(b)
        self._row(form, "cookies.txt", self._h(row),
                  "从浏览器导出 cookies.txt（Netscape 格式），用于下载你有权限访问的会员/登录内容")
        tip = QLabel("重要：仅导入你自己的账号 cookies，用于保存你有权查看的内容。"
                     "软件不做任何付费墙绕过。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{C['warn_text']};background:{C['warn_bg']};border-radius:8px;padding:10px;")
        form.addRow(tip)
        return self._scrolled(w)

    # ---------------- 浏览器会话 ----------------
    def _page_browser(self) -> QWidget:
        w, form = self._page()
        from ..config import BROWSER_STATE
        self.ed_bs_url = QLineEdit()
        self.ed_bs_url.setPlaceholderText("粘贴要登录的网站地址，如 https://example.com")
        b_paste = QPushButton("粘贴")

        def paste_url() -> None:
            from PySide6.QtGui import QGuiApplication
            self.ed_bs_url.setText(QGuiApplication.clipboard().text().strip())

        b_paste.clicked.connect(paste_url)
        url_row = QHBoxLayout()
        url_row.addWidget(self.ed_bs_url, 1)
        url_row.addWidget(b_paste)
        self.lab_bs_state = QLabel("")
        b_login = QPushButton("登录并保存会话")
        b_login.setObjectName("primary")

        def refresh_state() -> None:
            if BROWSER_STATE.exists():
                import time as _t
                mt = _t.localtime(BROWSER_STATE.stat().st_mtime)
                self.lab_bs_state.setText(f"已保存会话：{_t.strftime('%Y-%m-%d %H:%M', mt)}（{BROWSER_STATE.stat().st_size} 字节）")
            else:
                self.lab_bs_state.setText("未保存会话")

        def do_login() -> None:
            url = self.ed_bs_url.text().strip()
            if not url.startswith(("http://", "https://")):
                self.lab_bs_state.setText("请先输入以 http(s):// 开头的网站地址")
                return
            from ..core.render import login_session
            self.lab_bs_state.setText("已弹出浏览器窗口，请在窗口中登录/访问目标站后关闭窗口…")
            ok = login_session(url, str(BROWSER_STATE))
            refresh_state()
            self.lab_bs_state.setText(
                ("会话已保存 ✅ 之后真渲染会自动带上" if ok else "未保存（超时或出错），请重试"))

        def clear_state() -> None:
            try:
                BROWSER_STATE.unlink(missing_ok=True)
            except Exception:
                pass
            refresh_state()

        b_login.clicked.connect(do_login)
        self._row(form, "一键登录", self._h(url_row),
                  "粘贴网址（可用\"粘贴\"键从剪贴板取）→ 弹出真实浏览器窗口，你登录/访问目标站一次并关闭窗口，"
                  "软件自动保存登录态。之后 JS 壳页面/风控站（如 ukdevilz）真渲染时会自动带上，无需手动导出 cookies")
        form.addRow("", b_login)
        self.lab_bs_state.setStyleSheet(f"color:{C['muted']};font-size:12px;")
        form.addRow("", self.lab_bs_state)
        b_clear = QPushButton("清除已保存会话")
        b_clear.clicked.connect(clear_state)
        self._row(form, "管理", b_clear)
        tip = QLabel("会话只保存在本机（AppData 下），不上传。仅用于访问你有权查看的内容。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{C['warn_text']};background:{C['warn_bg']};border-radius:8px;padding:10px;")
        form.addRow(tip)
        refresh_state()
        return self._scrolled(w)

    # ---------------- 关于 ----------------
    def _page_about(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(30, 30, 30, 30)
        v.setAlignment(Qt.AlignHCenter)

        icon = QLabel("▶")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:28px;color:#fff;background:#3b82f6;"
                           "border-radius:18px;max-width:56px;max-height:56px;min-width:56px;min-height:56px;")
        icon.setFixedSize(56, 56)
        v.addWidget(icon, 0, Qt.AlignHCenter)

        name = QLabel(APP_NAME)
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet("font-size:20px;font-weight:600;margin-top:10px;")
        v.addWidget(name)

        sub = QLabel("视频下载 · 文章提取 · 双模式桌面工具")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{C['muted']};font-size:12px;")
        v.addWidget(sub)
        v.addSpacing(14)

        tag = QLabel(APP_TAGLINE)
        tag.setAlignment(Qt.AlignCenter)
        tag.setWordWrap(True)
        tag.setStyleSheet(f"color:{C['warn_text']};background:{C['warn_bg']};border-radius:10px;"
                          "font-size:14px;font-weight:600;padding:12px 20px;")
        v.addWidget(tag)
        v.addSpacing(18)

        ff_ok, ff_info = check_ffmpeg()
        info = QLabel(f"版本 v{APP_VERSION} · ffmpeg：{'正常' if ff_ok else '缺失'}"
                      + (f"\n{ff_info}" if not ff_ok else ""))
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet(f"color:{C['muted']};font-size:12px;line-height:1.6;")
        v.addWidget(info)
        v.addSpacing(6)

        # 网站引流 + 开源仓库
        blog = self._link_label("访问 zchlab.space！", BLOG_URL)
        blog.setStyleSheet(f"color:{C['accent']};font-size:14px;font-weight:600;")
        blog.setAlignment(Qt.AlignCenter)
        v.addWidget(blog)
        gh = self._link_label("GitHub：开源仓库", GITHUB_URL)
        gh.setAlignment(Qt.AlignCenter)
        gh.setStyleSheet(f"color:{C['muted']};font-size:12px;")
        v.addWidget(gh)
        v.addSpacing(10)

        btn_lay = QHBoxLayout()
        b_check = QPushButton("检查更新")
        b_check.clicked.connect(lambda: QMessageBox.information(
            self, APP_NAME, "当前已是最新版本 v" + APP_VERSION))
        b_log = QPushButton("打开日志目录")
        b_log.clicked.connect(lambda: open_log_dir())
        b_share = QPushButton("分享给朋友")
        b_share.clicked.connect(self._share)
        for b in (b_check, b_log, b_share):
            btn_lay.addWidget(b)
        v.addLayout(btn_lay)
        v.addStretch()

        note = QLabel("仅供个人学习使用 · 请遵守各平台服务条款")
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color:{C['faint']};font-size:11px;")
        v.addWidget(note)
        return self._scrolled(w)

    def _link_label(self, text: str, url: str) -> QLabel:
        lab = QLabel(f'<a href="{url}" style="text-decoration:none;">{text}</a>')
        lab.setOpenExternalLinks(True)
        lab.setCursor(Qt.PointingHandCursor)
        return lab

    def _share(self) -> None:
        text = (f"推荐一个工具：{APP_NAME}，{APP_TAGLINE}（v{APP_VERSION}）\n"
                f"开源地址：{GITHUB_URL}\n{BLOG_URL}")
        QGuiApplication.clipboard().setText(text)
        QMessageBox.information(self, APP_NAME, "已复制分享文案（含 GitHub 链接）到剪贴板")

    # ---------------- 保存 ----------------
    def save(self, rebuild: bool = True) -> None:
        g, n, d, a, c = (self.cfg.setdefault(k, {}) for k in
                         ("general", "network", "download", "article", "cookies"))
        theme_changed = g.get("theme") != ("system", "light", "dark")[self.cb_theme.currentIndex()]
        g["theme"] = ("system", "light", "dark")[self.cb_theme.currentIndex()]
        g["history_limit"] = self.sp_history.value()
        g["log_level"] = self.cb_loglevel.currentText()

        n["impersonate"] = self.cb_imp.currentText()
        n["concurrency"] = self.sp_conc.value()
        n["sleep_interval"] = self.sp_sleep.value()
        n["proxy"] = self.ed_proxy.text().strip()
        n["tls_impersonation"] = self.cb_tls.isChecked()

        d["default_dir"] = self.ed_dir.text().strip()
        d["default_quality"] = ("best", "1080", "720")[self.cb_quality.currentIndex()]
        d["default_format"] = ("mp4", "mkv", "best")[self.cb_fmt.currentIndex()]
        d["audio_only"] = self.cb_audio.isChecked()
        d["sponsorblock"] = self.cb_sb.isChecked()
        d["subtitles"] = self.cb_sub.isChecked()
        d["max_concurrent"] = self.sp_mt.value()
        d["playlist"] = self.cb_pl.isChecked()

        a["default_output_format"] = ("html", "markdown", "txt")[self.cb_a_fmt.currentIndex()]
        a["download_images"] = self.cb_a_img.isChecked()
        a["max_image_size_mb"] = self.sp_max_img.value()

        c["cookies_file"] = self.ed_cookies.text().strip()
        save_config(self.cfg)

        if rebuild and theme_changed:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, g["theme"])
                win = self.window()
                if win is not None and hasattr(win, "rebuild_theme"):
                    win.rebuild_theme()
