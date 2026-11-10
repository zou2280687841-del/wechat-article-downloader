# 发布到 GitHub

本地目录已经整理好；此交付不会替你创建远程仓库或上传任何文件。

## 首次上传源码

1. 在 GitHub 创建空仓库，名称可用 `wechat-official-account-backup`。不要在网页中重复生成 README、LICENSE 或 `.gitignore`。
2. 推荐解压 `release-assets/WechatBackup-v1.2.0-source.zip`，上传压缩包内部的项目文件；也可以将当前目录作为本地 Git 工作区。
3. 仓库根目录应直接包含 `README.md`、`LICENSE`、`main.py`、`wxbackup/` 和 `.github/`。
4. 使用网页上传时，要包含隐藏的 `.github/`、`.gitignore` 和 `.gitattributes`。不上传 `release-assets/`、`runtime/` 或任何本地用户数据。

使用 Git 推送时，在当前目录执行（将 `YOUR_NAME` 改成自己的 GitHub 用户名）：

```powershell
git init -b main
git add .
git status
git commit -m "Release v1.2.0"
git remote add origin https://github.com/YOUR_NAME/wechat-official-account-backup.git
git push -u origin main
```

首次使用 Git 时，如提示身份未配置，请自行设置自己的 Git 用户名和提交邮箱。这里不预填个人信息。

## 发布 Windows 运行包

1. 在仓库的 **Releases → Draft a new release** 新建 `v1.2.0` 标签。
2. 发布标题可用 `微信公众号下载工具 v1.2.0`。
3. 将根目录 `RELEASE_NOTES.md` 的内容复制到发布说明。
4. 上传本地 `release-assets/` 内的 Windows ZIP、源码 ZIP 和 `SHA256SUMS.txt`。
5. 检查附件与说明后发布。

这些 ZIP 应作为 Release 附件，避免将大型 EXE / DLL 提交进 Git 历史。

## 后续构建

- 本地：运行 `build.cmd`。
- GitHub：在 **Actions → Build Windows release → Run workflow** 手动构建，下载生成的 artifact，再作为 Release 附件上传。该工作流不会自动发布 Release。

发布前运行完整测试，并用一份独立浏览器配置验证实际后台；保留所有第三方许可证声明。建议在 GitHub 仓库设置中启用 **Private vulnerability reporting**，对应 `SECURITY.md` 中的私密报告流程。
