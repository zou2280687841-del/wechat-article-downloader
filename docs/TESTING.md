# 测试说明

已验证环境：Windows 11 x64、Python 3.12、Microsoft Edge、PySide6 6.8.3。

v1.2.0 本地发布验证：20 项测试通过（15.56 秒），Windows EXE 的 GUI、暂停/继续、Edge PDF 和 Excel 冒烟测试通过。GitHub Actions 工作流已配置，尚未在远程仓库运行。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

测试覆盖：

- 模拟 95 次发表、10 页、190 篇多图文；模拟数据不是用户的真实文章。
- 删除记录、重复翻页、网络失败、停止操作与下载状态保留。
- 自有后台 `appmsg_info/content_url` 与旧式 `appmsgex/link`。
- 独立发表同级详情、标题实体、页面日期回退。
- HTML 内置列表、不同标签页、脱敏诊断。
- 真实 Edge 对本地服务的请求、离线图片与背景图、表格、颜色、PDF。
- Excel 字符串保护、文件校验、损坏文件重存与续传。

项目曾通过真实账号验证列表采集与下载。公开仓库不附带该账号、会话、文章目录或后台原始数据。测试不能代替对微信后续页面更新的实际验收。

Windows 打包版可运行独立冒烟测试：

```powershell
.\runtime\WechatBackup.exe --smoke-test .\build\smoke
```

成功时会生成 `build/smoke/smoke-result.json`，检查 GUI、暂停/继续、Edge PDF 和 Excel 导出。请使用独立测试目录。
