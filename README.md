# 下片神器 (XpsqDownloader)

卧槽这么好的软件你怎么不早点告诉我 —— 视频下载 + 文章提取双模式桌面工具。

## 功能

- **视频下载**：输入含视频的网页链接，自动解析并下载。内核基于 yt-dlp（支持 1000+ 站点提取器），
  不支持的站点自动落到「万能兜底嗅探器」，从页面 HTML/JS 中抓取 mp4 / m3u8 直链。
- **文章提取**：输入文章链接，提取正文（标题/作者/日期）并下载全部插图到本地，
  输出 HTML（含插图）/ Markdown / 纯文本 三种格式。
- **完整结果信息**：成功/失败卡片展示用户层信息（文件大小、分辨率、速度、错误码、友好文案），
  折叠区展示开发者层信息（原始异常、traceback、环境版本、日志文件路径），一键复制完整日志。
- **反爬对抗**：TLS 指纹伪装（curl_cffi）、Cloudflare 自动绕过、请求限速、代理、cookies 导入。
- **广告处理**：页面广告自动剔除；可选 SponsorBlock 跳过视频内赞助片段。
- **cookies 导入**：仅用于下载你自己有权限访问的登录/会员内容。**软件不提供任何付费墙绕过手段。**

## 运行

```bash
pip install -r requirements.txt
python main.py
```

## 打包 exe

```bash
# 需要先把 ffmpeg.exe 放到 ffmpeg/ 目录下（或系统 PATH）
build.bat
# 产物在 dist/XpsqDownloader/，运行 XpsqDownloader.exe
```

## 配置与日志

- 配置：`%APPDATA%/XpsqDownloader/config.json`
- 日志：`%APPDATA%/XpsqDownloader/logs/YYYY-MM-DD/task_xxx.jsonl`（结构化 JSONL，按天分目录）

## 错误码

| 错误码 | 含义 |
|---|---|
| ERR_UNSUPPORTED | 不支持的站点 |
| ERR_NETWORK | 网络/超时/HTTP 错误 |
| ERR_ANTIBOT | 被站点风控拦截 |
| ERR_COOKIE | 需要登录/会员 |
| ERR_DRM | 受版权保护（DRM） |
| ERR_FFMPEG | ffmpeg 缺失/合并失败 |
| ERR_FS | 磁盘/权限/文件名问题 |
| ERR_EXTRACT_EMPTY | 未识别到文章正文 |
| ERR_IMG_PARTIAL | 部分插图下载失败 |
| ERR_INTERNAL | 未知内部错误 |

## 合规声明

仅供个人学习与合法用途。请遵守各平台服务条款；软件不破解 DRM、不绕过付费墙。
