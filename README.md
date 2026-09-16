# Codex 配置管理器

一个面向 Windows 的 Codex 配置预设管理工具，提供图形界面和命令行双通道。

> **非官方项目**：本项目与 OpenAI 无隶属、赞助或官方认可关系。“Codex”“OpenAI”及相关标识属于其各自权利人。

## 功能

- 新建、编辑、复制、删除和切换配置预设
- 切换前回收 Codex 对当前 `config.toml` 的修改，减少配置丢失
- 文本级修改 TOML，保留注释、字段顺序、多行结构和换行风格
- 可视化历史版本、差异预览和安全恢复
- 直接填写 API Key，并写入 Windows 当前用户环境变量
- 自动获取兼容服务的模型列表
- 支持 Responses API 与 Chat Completions 的最小调用测试
- 首次路径探测、自定义 Codex 配置目录和预设目录
- Codex 运行状态保护、未保存提醒和脱敏错误信息
- 单文件 Windows GUI；同一程序也支持 CLI 子命令

## 系统要求

- Windows 10 或 Windows 11
- Microsoft Edge WebView2 Runtime
- 使用源码运行：Python 3.13

## 快速使用

### 使用发布版

从 GitHub Releases 下载 `CodexConfigManager.exe`，双击运行。程序是免安装单文件，不需要管理员权限。

> 当前发布文件尚未进行商业代码签名，Windows SmartScreen 可能显示提示。请仅从可信的仓库 Release 页面下载，并核对发布页提供的 SHA-256。

### 配置位置

GUI 会在首次运行时探测配置位置，也可在“更多操作 → 配置位置”中修改。

优先级如下：

1. 显式命令行/测试路径
2. `CODEX_HOME`
3. `%LOCALAPPDATA%\CodexConfigManager\settings.json`
4. `%USERPROFILE%\.codex`

默认结构：

```text
.codex/
├─ config.toml
└─ configs/
   ├─ example.toml
   ├─ .state
   ├─ .guard
   └─ .history/
```

切换配置目录只改变管理器今后的读写位置，不会自动移动或删除旧目录数据。

## API Key 与网络行为

- 预设 TOML 只保存环境变量名，不保存 API Key 原文。
- API Key 可由程序写入 Windows 当前用户环境变量。
- 用户环境变量不是加密保险箱；同一 Windows 用户下的其他程序通常可以读取。
- 获取模型列表或测试模型调用前，程序会显示目标地址并要求确认。
- 默认只允许 HTTPS；`localhost` 和 `127.0.0.1` 可使用 HTTP。
- 请求不自动跟随重定向，并限制超时、响应大小和错误输出长度。
- 模型调用测试会发送固定短文本，可能产生少量费用。

## 从源码运行

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\app.py
```

## 构建单文件 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean CodexConfigManager.spec
```

产物位于 `dist\CodexConfigManager.exe`。

## 测试

核心测试可参考 `.github/workflows/tests.yml`。GUI 探针需要交互式 Windows 桌面，因此不在普通 CI 中执行。

```powershell
.\.venv\Scripts\python.exe src\test_core.py
.\.venv\Scripts\python.exe src\test_roundtrip.py
.\.venv\Scripts\python.exe src\test_userenv.py
.\.venv\Scripts\python.exe src\test_paths.py
.\.venv\Scripts\python.exe src\test_priority1.py
.\.venv\Scripts\python.exe src\test_models.py
.\.venv\Scripts\python.exe tools\t_toml.py
.\.venv\Scripts\python.exe tools\t_edit.py
.\.venv\Scripts\python.exe tools\t_cli.py
```

真实用户配置的只读冒烟检查默认关闭。只有显式设置 `CODEX_REAL_CONFIG_SMOKE=1` 时，部分测试才会读取 `%USERPROFILE%\.codex\config.toml` 的哈希用于前后对比。

## 项目结构

```text
src/                         核心逻辑、GUI/CLI 入口及核心测试
tools/                       GUI 探针、构建和部署辅助工具
assets/                      应用图标资源
docs/ARCHITECTURE.md         架构与安全设计
docs/RELEASE_CHECKLIST.md    发布检查清单
CodexConfigManager.spec      PyInstaller 构建配置
```

## 已知限制

- 仅验证 Windows 10/11。
- 未完成正式代码签名和安装包。
- GUI 自动化探针依赖可用的交互式桌面，云端 CI 只运行核心测试。
- 第三方服务对 OpenAI 接口的兼容程度不同，模型列表成功不代表模型调用一定成功。
- 当前图标的授权状态需要发布者在公开分发前再次确认，详见 `THIRD_PARTY_NOTICES.md`。

## 隐私

程序不包含遥测或分析 SDK。除非用户主动执行“获取模型”或“测试模型调用”，程序不会连接模型服务。配置、历史记录和用户设置均保存在本机。

## 贡献与安全

- 贡献指南：[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 安全报告：[`SECURITY.md`](SECURITY.md)
- 第三方声明：[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
- 架构说明：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## 许可证

代码采用 [MIT License](LICENSE)。第三方组件、名称、商标和图标不一定适用 MIT，详见 `THIRD_PARTY_NOTICES.md`。
