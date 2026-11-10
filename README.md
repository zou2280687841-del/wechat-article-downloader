# 微信公众号下载工具

![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20x64-blue)
![License](https://img.shields.io/badge/License-MIT-green)

使用 Python、Playwright 和 PySide6 开发的微信公众号历史文章本地备份工具。手动扫码登录自有公众号后台，遍历发表记录，将文章保存为离线 HTML 和 PDF，并生成 Excel 目录与统计报告。

当前版本：**v1.2.0**。

## 功能

- 扫码登录；独立 Edge 浏览器配置，显示连接状态。
- 遍历全部发表记录，识别多图文、已删除文章并去重。
- 支持后台接口响应与页面内置数据两种来源，自动选择已登录的发表记录标签页。
- 每篇文章单独保存 HTML、PDF，按发表日期整理。
- 图片及 CSS 背景图片内嵌，HTML 可离线阅读。
- Excel 文章目录、异常记录和备份统计。
- 进度、日志、暂停、继续、失败重试；已完成文件通过 SHA-256 校验后跳过。
- 发现重复页、数量变化、空页或未知文章结构时，不将结果标记为完整。

## 快速开始

### Windows 运行包

从本仓库的 **Releases** 下载 `WechatBackup-v1.2.0-windows-x64.zip`，完整解压后双击 **启动备份.cmd**。

运行包已包含 Python 运行时，需要电脑安装 Microsoft Edge。不要只复制 EXE，必须保留 `runtime/_internal`。

> 维护者发布首个 Release 前，运行包位于本地 `release-assets/`，需要按[发布指南](docs/PUBLISHING.md)作为 Release 附件上传。

### 从源码运行

环境：Windows 10/11 x64、Microsoft Edge、64 位 Python 3.11 或 3.12。

双击 `setup.cmd` 安装项目依赖，完成后双击 `启动备份.cmd`。也可以在项目目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

源代码压缩包不包含 EXE；未安装依赖时请先运行 `setup.cmd`。

## 使用方法

1. 点击「① 打开登录浏览器」，自己扫码登录。
2. 在程序打开的 Edge 中进入「内容管理 → 发表记录」，清空搜索和日期筛选。
3. 选择下载目录，点击「② 获取全部文章列表」。
4. 核对发表次数、文章条数、标题和链接。一次发表可能包含多篇文章。
5. 选择 HTML、PDF 或两者，点击「③ 开始 / 重试失败项」。
6. 下载完成后查看 `文章目录.xlsx`、`备份统计.txt` 和 `异常记录.json`。

关闭或停止后，重新启动并使用同一个下载目录，可以继续未完成任务。暂停在当前网络请求结束后生效。

详见[使用说明](docs/USER_GUIDE.md)与[常见问题](docs/FAQ.md)。

## 保存结果

```text
备份/
├── catalog.json                 # 列表、校验值与进度
├── 文章目录.xlsx
├── 备份统计.txt / 备份统计.json
├── 异常记录.json
├── 采集诊断.json                 # 路径、字段名等脱敏诊断
├── 采集证据/                    # 原始列表数据，留在本机
└── YYYY-MM-DD/标题_唯一ID/
    ├── article.html
    └── article.pdf
```

## 项目结构

```text
main.py                    程序入口
wxbackup/
  backend.py               标签页、后台响应和内置列表识别
  collector.py             分页采集与完整性核对
  model.py                 数据解析、文件命名与持久化
  downloader.py            正文、图片、离线 HTML、PDF
  report.py                Excel 与统计导出
  worker.py                后台线程
  gui.py                   PySide6 界面
tests/                     匿名测试数据与浏览器集成测试
scripts/make_release.py    生成源码包、Windows 包和 SHA-256 清单
.github/                   Windows CI、问题模板、PR 模板
docs/                      使用、测试、发布与第三方许可证说明
```

## 开发、测试和打包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

浏览器集成测试需要本机 Edge。测试只使用模拟后台与本地 HTTP 服务，不要求登录真实账号，不使用真实文章数据。

双击 `build.cmd` 构建 Windows 目录版，随后生成发布压缩包。也可以仅生成源码包：

```powershell
.\.venv\Scripts\python.exe scripts/make_release.py
```

本项目使用 GitHub Actions 运行 Windows 测试，另提供手动触发的 Windows 构建工作流。详见[测试说明](docs/TESTING.md)和[发布指南](docs/PUBLISHING.md)。

## 已知限制

- 只适用于有权访问的公众号后台，不支持绕过扫码、验证码或访问限制。
- 已删除、违规不可访问或后台已清空详情的文章，无法还原正文或推算原篇数。
- A4 PDF 的分页与手机长页面不同；缺少字体时使用本机备用字体。
- 视频、音频、小程序和其他动态交互不能保证离线还原，已识别的嵌入媒体会提示核对。
- 微信后台不是稳定公开 API；页面变化时可能需要更新适配。
- 列表数量核对通过后，仍建议抽查实际 HTML、图片和 PDF。

## 隐私

`data/browser/` 含浏览器登录会话。`data/`、文章备份、采集证据、运行日志和真实目录均不得提交到公开仓库。项目已通过 `.gitignore` 排除这些内容，源码包和运行包采用文件白名单生成。

提交 Issue 前，请删除账号、文章信息、完整后台地址和任何 Cookie、token；不要上传整个 `data` 文件夹。参见 [SECURITY.md](SECURITY.md)。

## 许可证

项目自有代码使用 [MIT License](LICENSE)。PySide6 / Qt、Playwright、Python 和其他依赖保留各自的许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目与腾讯、微信无隶属或官方合作关系。请仅备份有权处理的内容。
