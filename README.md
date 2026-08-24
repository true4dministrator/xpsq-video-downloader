# 下片神器 (XpsqDownloader)

> 卧槽这么好的软件你怎么不早点告诉我 —— 视频下载 · 音乐下载 · 文章提取，一个软件全搞定。

基于 yt-dlp 内核的开源桌面工具，支持 1000+ 视频站点、主流音乐平台、网页正文提取，深/浅色主题，Windows 免安装 exe 直接运行。

## 功能特性

### 🎬 视频下载
- 粘贴含视频的网页链接即下载，内核基于 **yt-dlp**（支持 1000+ 站点提取器）
- **多任务下载中心**：右侧常驻任务栏，可连续添加多个链接，有界并行（默认 3 个同时下载、同站点限 2 防封），每个任务独立进度/取消
- **播放列表/歌单整批下载**：B站收藏夹、YouTube 播放列表、网易云歌单一键全下
- 不支持的站点自动落到**万能兜底嗅探器**，多层流水线找直链：
  1. 语义提取（video/og:video/JSON-LD/srcset）
  2. 内嵌 JSON 状态挖掘（`__INITIAL_STATE__` 等）
  3. m3u8 智能解析（master 多码率自动选最高）
  4. iframe 递归 + JS 资源扫描 + **SPA API 接口探测**（JS 壳页面从 JS 挖 API 端点拿直链）
  5. **无头浏览器真渲染**（Edge/Chrome/Firefox，捕获网络直链，带已保存的登录会话）
- **浏览器一键登录会话**：设置 → 浏览器会话 → 粘贴网址登录一次，之后风控站/JS 壳站真渲染自动带上你的登录态，无需手动导出 cookies
- 直链响应自动识别（content-type 判断），mp4 / m3u8 / 音频直链直接可下
- 画质可选（最佳 / 1080p / 720p），封装可选（mp4 / mkv / 原始）
- **直链多线程分块下载**（HTTP Range，类 IDM）：服务器支持断点续传且文件较大时自动按并发数并行加速
- **仅音频 (MP3)**：从视频中提取音轨，VBR 最高质量
- 可选 SponsorBlock 自动跳过视频内赞助片段、下载字幕

### 🎵 音乐下载
- 粘贴歌曲链接直接下载为音频，与视频下载同样简单的交互
- 原生支持 **网易云音乐**（单曲/专辑/歌单/歌手）、**QQ音乐**（单曲/专辑/歌单/排行）、**SoundCloud**、**Bandcamp**、**Jamendo**、**YandexMusic** 等
- 音质可选：MP3（VBR 最高）/ MP3 320kbps / M4A（AAC 256k）/ 原始格式

### 📄 文章提取
- 提取网页正文（标题/作者/日期），**插图自动下载到本地**，离线可读
- 输出格式：HTML（含插图）/ Markdown / 纯文本
- 基于 trafilatura，自动剔除导航、广告、评论区噪声

### 🛡️ 反爬与隐私
- TLS 指纹伪装（curl_cffi 模拟 Chrome/Edge/**Firefox**/Safari）、Cloudflare 挑战自动绕过
- 请求限速、HTTP 代理、cookies.txt 导入（仅用于下载**你自己有权限**访问的内容）
- 浏览器会话仅保存在本机（`%APPDATA%/XpsqDownloader/browser_state.json`），不上传
- 页面广告自动剔除；不做 DRM 破解、不做付费墙绕过

### 🎨 体验
- 深色 / 浅色 / 跟随系统 三档主题，选择持久化，切换即时生效
- 下载中实时显示**总大小 / 已下载 / 速度 / 预计剩余时间**（300ms 节流不刷屏）
- 完整结果信息：成功卡片展示文件大小/分辨率/速度，失败展示错误码 + 折叠开发者详情（原始异常、traceback、日志路径），一键复制
- 新任务自动清空上一次的结果卡片，不会混淆
- 结构化 JSONL 任务日志，按天分目录，方便排查

## 快速开始

**方式一：直接下载 exe（推荐）**

前往 [Releases](https://github.com/true4dministrator/xpsq-video-downloader/releases) 下载最新版压缩包，解压后双击 `XpsqDownloader.exe` 即可。

> 提示：首次运行如被杀毒软件拦截，请在 Windows 安全中心 → 病毒和威胁防护 → 排除项中添加软件所在文件夹（PyInstaller 打包程序的常见误报，非病毒）。

**方式二：源码运行**

```bash
pip install -r requirements.txt
python main.py
```

**方式三：自行打包**

```bash
# 需先将 ffmpeg.exe 放入 ffmpeg/ 目录（或系统 PATH）
build.bat
# 产物在 dist/XpsqDownloader/
```

## 配置与日志

- 配置文件：`%APPDATA%/XpsqDownloader/config.json`
- 任务日志：`%APPDATA%/XpsqDownloader/logs/YYYY-MM-DD/task_xxx.jsonl`
- 关于页可一键打开日志目录

## 错误码

| 错误码 | 含义 |
|---|---|
| ERR_UNSUPPORTED | 不支持的站点，或站点改版导致解析器失效（如 Yandex，见"已知限制"） |
| ERR_NETWORK | 网络/超时/HTTP 错误 |
| ERR_ANTIBOT | 被站点风控拦截 |
| ERR_COOKIE | 需要登录/会员（请导入 cookies） |
| ERR_DRM | 受版权保护（DRM），无法下载 |
| ERR_FFMPEG | ffmpeg 缺失/合并或转码失败 |
| ERR_FS | 磁盘/权限/文件名问题 |
| ERR_EXTRACT_EMPTY | 未识别到文章正文 |
| ERR_IMG_PARTIAL | 部分插图下载失败 |
| ERR_INTERNAL | 未知内部错误（请复制开发者详情反馈） |

## 已知限制

- **Yandex 视频**：yt-dlp 上游提取器失效（Yandex 改版导致 `Unable to extract data_raw`，见 yt-dlp issues #15912 / #13653 / #16047）。可先到 设置 → 浏览器会话 登录一次，再用无头浏览器真渲染兜底；或粘贴直链下载。
- **VIP / 付费歌曲**：需在设置中导入你自己的 cookies 才能下载，且仅限你**拥有访问权限**的内容。
- **DRM 保护**（Widevine / FairPlay）：密钥在加密黑盒中，正路无法下载，界面会明确提示。
- **纯 JS 渲染的文章页**：正文不在原始 HTML 中时可能提取失败（提示未识别到正文）。
- 部分境外站点（YouTube、SoundCloud 等）在你所在网络环境下可能无法连接，属网络问题。

## 常见问题

**Q：杀毒软件拦截 exe？**
A：PyInstaller 打包程序的常见误报，非病毒。请在 Windows 安全中心 → 病毒和威胁防护 → 排除项中添加软件所在文件夹。

**Q：支持哪些音乐网站？**
A：网易云音乐、QQ音乐、SoundCloud、Bandcamp、Jamendo、YandexMusic 等（yt-dlp 原生提取器）。

**Q：下载失败显示 ERR_UNSUPPORTED？**
A：站点可能改版导致解析器失效（上游修复中），或确实不支持；可尝试粘贴视频/音频直链。

## 开源致谢

本项目站在巨人的肩膀上，核心能力全部来自以下开源项目：

| 项目 | 用途 | 许可证 |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频/音乐解析与下载内核（1000+ 站点提取器） | [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) |
| [trafilatura](https://github.com/adbar/trafilatura) | 网页正文提取（文章模式） | Apache-2.0 |
| [PySide6 / Qt](https://doc.qt.io/qtforpython/) | 桌面 GUI 框架 | LGPL-3.0 |
| [requests](https://github.com/psf/requests) | HTTP 请求 | Apache-2.0 |
| [curl_cffi](https://github.com/lexiforest/curl_cffi) | TLS 指纹伪装 | MIT |
| [lxml](https://lxml.de/) | HTML/XML 解析 | BSD-3-Clause |
| [ffmpeg](https://ffmpeg.org/) | 视频合并、音频转码（随包内置） | LGPL-2.1+ / GPL-2.0+（构建版本而定） |
| [PyInstaller](https://pyinstaller.org/) | Windows exe 打包 | GPL-2.0+（含例外条款） |

各项目的完整许可证文本见其官方仓库。

## 许可证

本项目采用 **GNU General Public License v3.0（GPL-3.0）**，详见 [LICENSE](LICENSE) 文件。

## 免责声明

使用本软件前请知悉：

1. **仅供个人学习、研究和技术交流使用**，请勿用于商业用途或任何侵权行为。
2. 本软件**不提供任何 DRM 破解、付费墙绕过**手段；仅能下载你拥有合法访问权限的内容（含通过导入自己的 cookies 访问的会员内容）。
3. 下载内容的版权归原作者及所属平台所有，请勿传播、贩卖或用于其他侵权用途。
4. 使用本软件时请遵守相关平台的服务条款以及当地法律法规。
5. 本项目与各视频/音乐/新闻平台**无任何关联，未获得其授权或背书**。
6. 因使用本软件产生的任何版权、法律问题，由使用者自行承担，项目作者不承担任何责任。

---

**仓库地址**：<https://github.com/true4dministrator/xpsq-video-downloader> · **作者博客**：<https://zchlab.space>
