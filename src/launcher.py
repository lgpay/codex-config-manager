# -*- coding: utf-8 -*-
"""
应用启动器 —— 在 Windows 上发现并启动已安装的应用（用于界面里的“启动 ChatGPT”）。

设计约束（安全相关，改动前请先读）：

* **只通过系统登记的应用标识（AUMID）启动**。AUMID 由 Windows 的「开始菜单应用列表」
  提供，是系统自己登记的入口；不猜测、不拼接 WindowsApps 目录里的 exe 路径
  （该目录带 ACL 保护且随版本变化，硬编码会随升级失效）。
* **不读取任何凭据**。本模块只读应用名称与标识，不碰登录缓存、token、配置文件。
* **不用 shell 解析**。启动一律走 argv 数组，不使用 shell=True，避免命令注入。
* 名称匹配以「显示名」为准；找不到明确唯一的 ChatGPT 入口时**返回失败**，
  不做模糊兜底，避免误启动无关程序。

本模块不 import 任何界面库，可被核心测试直接调用。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

# 系统「开始菜单应用列表」查询。用 PowerShell 读取，输出 JSON 便于稳定解析。
# 注意：不使用 -Command 拼接用户输入，本查询完全静态。
_PS_QUERY = (
    "[Console]::OutputEncoding=[Text.UTF8Encoding]::new();"
    "$ErrorActionPreference='SilentlyContinue';"
    "@(Get-StartApps | ForEach-Object { [pscustomobject]@{ name=$_.Name; id=$_.AppID } })"
    " | ConvertTo-Json -Compress"
)

# 视为“已安装应用标识”的形态：AppX 应用为 `<包族名>!<应用Id>`。
# 路径型条目（如 `C:\...\x.exe`、`Microsoft.VisualStudioCode`）不是 AppX，但同样可用，
# 因此这里不强制带 `!`，只用它来区分「明显是文件路径」的条目。
_AUMID_MAX_LEN = 200
_QUERY_TIMEOUT = 12            # 秒；超时不阻塞界面
_START_MAX_LEN = 260           # 启动标识长度上限，防止异常输入


class LaunchError(Exception):
    """启动失败（入口不存在、系统调用失败等）。"""


def _powershell_exe() -> str:
    """返回可用的 PowerShell 绝对路径；找不到则退回 `powershell.exe` 交给 PATH。"""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    cand = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return cand if os.path.isfile(cand) else "powershell.exe"


def list_start_apps(timeout: int = _QUERY_TIMEOUT) -> list[dict[str, str]]:
    """只读返回系统「开始菜单应用列表」。

    返回 `[{"name": 显示名, "id": 应用标识}]`；查询失败返回空列表
    （调用方据此给出“未检测到入口”的提示，不伪造结果）。
    """
    if not sys.platform.startswith("win"):
        return []
    try:
        proc = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", _PS_QUERY],
            capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    raw = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    # 单个结果时 PowerShell 会退化为对象而不是数组，统一成列表。
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        app_id = str(item.get("id") or "").strip()
        if not name or not app_id or len(app_id) > _AUMID_MAX_LEN:
            continue
        out.append({"name": name, "id": app_id})
    return out


def _is_launchable_id(app_id: str) -> bool:
    """基本形态校验：不含换行/引号等会被误解析的字符，长度合理。

    注意：合法的应用标识**可以**包含反斜杠（例如开始菜单里的
    `{6D809377-...}\\nodejs\\node.exe` 这类桌面应用条目），所以不能一律禁止 `\\`。
    但 `..` 只可能来自构造出来的路径穿越，系统登记的应用标识不会出现，直接拒绝。
    """
    if not app_id or len(app_id) > _START_MAX_LEN:
        return False
    if any(ch in app_id for ch in ("\r", "\n", "\t", '"', "'")):
        return False
    if ".." in app_id:
        return False
    return True


def find_chatgpt(entries: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """在应用列表中定位 ChatGPT 桌面应用入口。

    匹配规则（从严到宽，命中即返回）：

    1. 显示名**恰好**是 `ChatGPT`（忽略大小写与首尾空白）→ 唯一命中直接用；
    2. 显示名以 `ChatGPT` 开头（如本地化后缀）→ 仅当只有一个候选时采用。

    刻意**不**匹配 `Codex`：本机 Codex 与 ChatGPT 桌面应用同属一个包，但显示名不同；
    把 Codex 当成 ChatGPT 启动属于猜测，宁可失败并提示用户。
    """
    items = list_start_apps() if entries is None else list(entries)

    exact: list[dict[str, str]] = []
    prefix: list[dict[str, str]] = []
    for item in items:
        name = (item.get("name") or "").strip()
        app_id = (item.get("id") or "").strip()
        if not _is_launchable_id(app_id):
            continue
        low = name.lower()
        if low == "chatgpt":
            exact.append({"name": name, "id": app_id})
        elif low.startswith("chatgpt"):
            prefix.append({"name": name, "id": app_id})

    if exact:
        # 多个同名条目时取第一个（系统列表顺序稳定），仍视为可用入口。
        return {"ok": True, "entry": exact[0], "matched": "name_exact",
                "candidates": exact + prefix}
    if len(prefix) == 1:
        return {"ok": True, "entry": prefix[0], "matched": "name_prefix",
                "candidates": prefix}
    if prefix:
        return {"ok": False, "error": "检测到多个可能的 ChatGPT 入口，无法确定要启动哪一个。",
                "matched": "", "candidates": prefix}
    return {"ok": False, "error": "未检测到 ChatGPT 应用入口，请先在系统中安装 ChatGPT 桌面应用。",
            "matched": "", "candidates": []}


def launch(app_id: str, timeout: int = _QUERY_TIMEOUT) -> dict[str, Any]:
    """通过系统应用标识启动应用。

    使用 `explorer.exe shell:AppsFolder\\<AppID>`：这是 Windows 打开已安装应用的
    官方方式，对 AppX 应用与部分桌面应用都有效，且不需要知道真实安装路径。
    `explorer.exe` 会很快返回，因此这里不等待应用真正启动完毕。
    """
    app_id = (app_id or "").strip()
    if not _is_launchable_id(app_id):
        return {"ok": False, "error": "应用标识无效，无法启动。"}
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "当前系统不支持通过应用标识启动。"}
    target = "shell:AppsFolder\\" + app_id
    try:
        subprocess.Popen(  # noqa: S603 - 参数为数组，无 shell 解析
            ["explorer.exe", target],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return {"ok": False, "error": "调用系统启动应用失败，请稍后重试。"}
    except Exception:
        return {"ok": False, "error": "启动应用时出现未知错误。"}
    return {"ok": True, "method": "shell:AppsFolder", "app_id": app_id}


def launch_chatgpt(entries: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """发现并启动 ChatGPT；未找到明确入口时返回可读失败信息。"""
    found = find_chatgpt(entries)
    if not found.get("ok"):
        return {"ok": False, "error": found.get("error") or "未检测到 ChatGPT 应用入口。",
                "candidates": found.get("candidates") or []}
    entry = found["entry"]
    result = launch(entry["id"])
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "启动 ChatGPT 失败。",
                "candidates": found.get("candidates") or []}
    return {"ok": True, "name": entry["name"], "app_id": entry["id"],
            "method": result.get("method", ""),
            "message": "已请求启动 ChatGPT，请查看任务栏。"}
