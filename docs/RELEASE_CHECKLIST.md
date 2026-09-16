# 发布检查清单

## 版本和文档

- [ ] 更新 `src/core.py` 中的版本号
- [ ] 更新 `CHANGELOG.md`
- [ ] README 与实际界面、路径和安全行为一致
- [ ] 检查第三方依赖版本与许可证

## 安全与隐私

- [ ] 搜索 API Key、令牌、私钥、邮箱、本机绝对路径和真实配置内容
- [ ] 确认 `outputs/`、`.workbuddy/`、`build/`、`dist/` 未进入 Git
- [ ] 所有网络测试仅访问本地 mock
- [ ] 真实配置只读冒烟检查保持默认关闭
- [ ] 确认发布日志和诊断报告不包含密钥

## 图标和商标

- [ ] 确认 `assets/codex-icon.png` 及 ICO 的公开分发授权
- [ ] 若无法确认，改用拥有完整权利的原创图标
- [ ] 保留“非官方项目”声明

## 测试

- [ ] GitHub Actions 核心测试通过
- [ ] 本地完整核心/CLI 测试通过
- [ ] 本地全部 `tools/t_gui_*.py` 通过
- [ ] `tools/t_exe_gui.py` 通过，关闭后无残留进程
- [ ] 在干净 Windows 10/11 环境测试首次启动
- [ ] 测试无 WebView2、中文用户名、非 C 盘、高 DPI 和受限权限场景

## 构建与发布

- [ ] 使用干净虚拟环境安装 `requirements-dev.txt`
- [ ] 用 `CodexConfigManager.spec` 构建
- [ ] 计算并发布 SHA-256
- [ ] 检查文件是否带意外的 `Zone.Identifier`
- [ ] 可选：提交 VirusTotal（不得包含私有密钥或私有构建内容）
- [ ] 可选：为 EXE 添加可信代码签名
- [ ] Release 页面注明系统要求、已知限制和升级注意事项
