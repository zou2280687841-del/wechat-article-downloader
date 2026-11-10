# 参与贡献

1. Fork 仓库并创建功能分支。
2. 按 README 安装依赖；浏览器测试需要 Microsoft Edge。
3. 修改后运行 `python -m pytest tests -q -p no:cacheprovider`。
4. 后台结构适配请增加匿名回归用例，覆盖多图文、删除、缺链接或分页变化。
5. 提交 PR 时说明问题、行为变化和验证结果。

请保持扫码、验证码和验证页面由用户自己完成。后台操作保持只读。

不要提交真实登录会话、Cookie、token、真实文章目录、日志、截图或采集证据。示例中的账号、链接和文章内容应使用虚构数据。

版本发布需要同步 `wxbackup/__init__.py`、`pyproject.toml`、README 和 CHANGELOG。依赖修改时同步 `requirements.txt` 与 `pyproject.toml`。
