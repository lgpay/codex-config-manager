# 参与贡献

感谢关注本项目。提交改动前请先阅读以下约定。

## 开发环境

- Windows 10/11
- Python 3.13
- Microsoft Edge WebView2 Runtime

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## 代码结构

- `src/core.py`：配置、预设、历史与安全写入逻辑
- `src/connection.py`：受限网络检查与模型请求
- `src/userenv.py`：Windows 用户环境变量事务
- `src/app.py`：GUI/CLI 入口和桥接
- `src/ui.py`：内联 HTML/CSS/JavaScript
- `tools/`：测试、构建辅助与部署工具

## 测试要求

所有写测试必须使用临时 `CODEX_HOME`、临时设置文件和假密钥，不得读写开发者真实配置或环境变量。网络测试只能使用本地 mock 或 monkeypatch。

核心测试可按 `.github/workflows/tests.yml` 中的命令运行。GUI 探针需要交互式 Windows 桌面，发布前应在本机完整运行 `tools/t_gui_*.py` 和 `tools/t_exe_gui.py`。

## 提交规范

- 一个提交聚焦一个目的。
- 不提交 API Key、真实配置、构建缓存、备份目录或个人路径。
- 修改 TOML 编辑逻辑时必须保留往返保真测试。
- 修改安全保护时不得通过弱化断言让测试通过。
- UI 变更需覆盖窄窗口和高 DPI 下的几何检查。
