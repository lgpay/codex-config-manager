# -*- coding: utf-8 -*-
"""
部署脚本：把构建产物铺到目标位置。

  * 复制 exe 到 %USERPROFILE%\\bin\\
  * 创建桌面 / 开始菜单快捷方式（.lnk，属性见需求文档 §8.2）
  * 生成无界面通道转发脚本（bash / PowerShell / cmd），统一转发到主程序
  * 首次建立预设库的 .state / .guard

用法：
  python tools/deploy.py [--exe <路径>] [--skip-shortcuts] [--dry-run]
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "src"))
import core  # noqa: E402

APP_NAME = "Codex 配置管理器"
EXE_NAME = "CodexConfigManager.exe"
LNK_NAME = f"{APP_NAME}.lnk"


# --------------------------------------------------------------------------
# 系统路径（按需求 §7.9：不得硬编码用户名）
# --------------------------------------------------------------------------

def shell_folder(name: str, fallback: Path) -> Path:
    """从 HKCU\\...\\User Shell Folders 读，展开变量后校验；失败退回 fallback。"""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            raw, _ = winreg.QueryValueEx(k, name)
        val = os.path.expandvars(raw)
        p = Path(core.to_win_path(val))
        if p.is_dir():
            return p
    except Exception:
        pass
    return fallback


def desktop_dir() -> Path:
    return shell_folder("Desktop", Path(core.home_dir()) / "Desktop")


def start_menu_dir() -> Path:
    return shell_folder(
        "Programs",
        Path(os.environ.get("APPDATA", str(Path(core.home_dir()) / "AppData/Roaming")))
        / "Microsoft/Windows/Start Menu/Programs")


def bin_dir() -> Path:
    return Path(core.home_dir()) / "bin"


# --------------------------------------------------------------------------
# 快捷方式（纯 ctypes 直调 IShellLinkW / IPersistFile，不依赖 PowerShell）
# --------------------------------------------------------------------------

CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
IID_IPersistFile = "{0000010b-0000-0000-C000-000000000046}"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "GUID":
        s = s.strip("{}")
        a, b, c, d, e = s.split("-")
        g = cls()
        g.Data1 = int(a, 16)
        g.Data2 = int(b, 16)
        g.Data3 = int(c, 16)
        rest = bytes.fromhex(d + e)
        for i in range(8):
            g.Data4[i] = rest[i]
        return g


def create_lnk(lnk_path: Path, target: str, workdir: str,
               description: str, icon: str | None) -> None:
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long

    hr = ole32.CoInitializeEx(None, 0x2)   # APARTMENTTHREADED
    need_uninit = hr in (0, 1)

    clsid = GUID.parse(CLSID_ShellLink)
    iid_link = GUID.parse(IID_IShellLinkW)
    iid_persist = GUID.parse(IID_IPersistFile)

    p = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1,   # CLSCTX_INPROC_SERVER
                                ctypes.byref(iid_link), ctypes.byref(p))
    if hr != 0:
        if need_uninit:
            ole32.CoUninitialize()
        raise OSError(f"CoCreateInstance(ShellLink) 失败: 0x{hr & 0xffffffff:08X}")

    def vtbl(obj, index):
        vt = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return vt[index]

    def call(obj, index, restype, *argtypes):
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl(obj, index))
        return fn

    METHOD_QUERY_INTERFACE = 0
    # IShellLinkW 方法表：0..2 IUnknown, 3 GetPath ... 20 SetPath
    SetPath = call(p, 20, ctypes.c_long, ctypes.c_wchar_p)
    SetWorkingDirectory = call(p, 9, ctypes.c_long, ctypes.c_wchar_p)
    SetDescription = call(p, 7, ctypes.c_long, ctypes.c_wchar_p)
    SetIconLocation = call(p, 17, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)
    SetShowCmd = call(p, 15, ctypes.c_long, ctypes.c_int)

    SetPath(p, target)
    SetWorkingDirectory(p, workdir)
    SetDescription(p, description)
    if icon:
        SetIconLocation(p, icon, 0)
    SetShowCmd(p, 1)                       # SW_SHOWNORMAL

    # QueryInterface -> IPersistFile
    qifn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                              ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(vtbl(p, 0))
    persist = ctypes.c_void_p()
    hr = qifn(p, ctypes.byref(iid_persist), ctypes.byref(persist))
    if hr != 0:
        rel = call(p, 2, ctypes.c_ulong)
        rel(p)
        if need_uninit:
            ole32.CoUninitialize()
        raise OSError(f"QueryInterface(IPersistFile) 失败: 0x{hr & 0xffffffff:08X}")

    Save = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p,
                              ctypes.c_int)(vtbl(persist, 6))
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    hr = Save(persist, str(lnk_path), 1)   # TRUE = 记住路径
    rel = call(p, 2, ctypes.c_ulong)
    rel(p)
    if need_uninit:
        ole32.CoUninitialize()
    if hr != 0:
        raise OSError(f"IPersistFile::Save 失败: 0x{hr & 0xffffffff:08X}")


# --------------------------------------------------------------------------
# 无界面通道（转发脚本）
# --------------------------------------------------------------------------

BASH_FWD = """#!/usr/bin/env bash
# Codex 配置管理器 —— 无界面通道
# 本脚本只做转发：真正的逻辑在主程序里，保证与图形界面行为完全一致。
set -euo pipefail
EXE="$HOME/bin/CodexConfigManager.exe"
if [ ! -f "$EXE" ]; then
  echo "找不到主程序：$EXE" >&2
  exit 127
fi
exec "$EXE" "$@"
"""

PS1_FWD = """# Codex 配置管理器 —— 无界面通道（PowerShell）
# 本脚本只做转发：真正的逻辑在主程序里，保证与图形界面行为完全一致。
$exe = Join-Path $env:USERPROFILE 'bin\\CodexConfigManager.exe'
if (-not (Test-Path $exe)) {
    Write-Error "找不到主程序：$exe"
    exit 127
}
& $exe @args
exit $LASTEXITCODE
"""

CMD_FWD = """@echo off
rem Codex Config Manager - console front-end (forwards to the main program).
setlocal
set "EXE=%USERPROFILE%\\bin\\CodexConfigManager.exe"
if not exist "%EXE%" (
  echo Main program not found: "%EXE%"
  exit /b 127
)
if "%~1"=="" (
  start "" "%EXE%"
  exit /b 0
)
"%EXE%" %*
exit /b %ERRORLEVEL%
"""


def write_text(path: Path, text: str, bom: bool = False, dry: bool = False) -> None:
    if dry:
        print(f"    [dry] 写入 {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    with open(path, "wb") as f:
        f.write(data)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(PROJECT / "dist" / EXE_NAME))
    ap.add_argument("--skip-shortcuts", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    dry = a.dry_run
    exe_src = Path(a.exe)
    if not exe_src.exists() and not dry:
        print(f"[×] 找不到构建产物：{exe_src}")
        return 2

    bd = bin_dir()
    exe_dst = bd / EXE_NAME
    print(f"主程序目录 : {bd}")
    print(f"桌面       : {desktop_dir()}")
    print(f"开始菜单   : {start_menu_dir()}")

    # 1) 复制 exe
    if dry:
        print(f"    [dry] 复制 {exe_src} -> {exe_dst}")
    else:
        bd.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe_src, exe_dst)
        print(f"[1/4] exe 已部署 -> {exe_dst}  ({exe_dst.stat().st_size/1048576:.1f} MB)")

    # 2) 快捷方式
    #    TargetPath 用环境变量写法（shell 会自动展开，已实测）；
    #    图标不单独指定 —— Windows 默认取目标 exe 内嵌的图标（§8.2）；
    #    WorkingDirectory 用展开后的实际路径 —— shell 不展开该字段。
    if not a.skip_shortcuts:
        target = "%USERPROFILE%\\bin\\" + EXE_NAME
        workdir = str(Path(core.home_dir()) / ".codex")
        made = []
        for d in (desktop_dir(), start_menu_dir()):
            lnk = d / LNK_NAME
            if dry:
                print(f"    [dry] 快捷方式 {lnk} -> {target}  (wd={workdir})")
                continue
            try:
                create_lnk(lnk, target, workdir, APP_NAME, None)
                made.append((lnk, lnk.stat().st_size))
            except Exception as e:                              # noqa: BLE001
                print(f"[!] 创建快捷方式失败（{lnk}）：{e}")
        for lnk, size in made:
            print(f"[2/4] 快捷方式 -> {lnk}  ({size} B)")
        if not made:
            print("[2/4] 快捷方式：未创建")
    else:
        print("[2/4] 快捷方式：已跳过")

    # 3) 无界面通道转发脚本
    scripts = [
        (bd / "codex-switch", BASH_FWD, False, 0o755),
        (bd / "codex-switch.ps1", PS1_FWD, True, None),
        (bd / "codex-switch.cmd", CMD_FWD, False, None),
    ]
    for path, text, bom, mode in scripts:
        if path.exists() and not dry:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(path, bak)
                print(f"      旧脚本已备份 -> {bak.name}")
        write_text(path, text, bom=bom, dry=dry)
        if mode and not dry:
            os.chmod(path, mode)
        print(f"[3/4] 无界面通道 -> {path.name}")

    # 4) 预设库首次初始化（§12.2）
    p = core.Paths()
    if not dry:
        core.ensure_layout(p)
        if not p.guard.exists():
            core.atomic_write_bytes(
                p.guard,
                ("# 命中任一即视为宿主应用正在运行\n"
                 "# 一行一个进程名或通配模式，# 开头为注释，空行忽略\n"
                 "# 缺失本文件时会回退到内置默认名单\n"
                 "ChatGPT.exe\n"
                 "codex.exe\n"
                 "codex-*.exe\n").encode("utf-8"))
            print(f"[4/4] 已写入进程名单 -> {p.guard}")
        else:
            print(f"[4/4] 进程名单已存在，未改动 -> {p.guard}")
        cur, _ = core.read_state(p)
        if not cur:
            presets = core.list_presets(p)
            match, how = None, ""
            if p.live.exists():
                live = core.read_bytes(p.live)
                # 先严格比对
                for x in presets:
                    if core.read_bytes(Path(x["path"])) == live:
                        match, how = x["name"], "逐字节一致"
                        break
                # 再退一步：只看用户关心的 model / model_provider
                # （宿主会在现役配置里写随机 pipe GUID，属预期噪音，见 §7.7）
                if not match:
                    lm, lp = core.peek_model(p.live)
                    cands = [x["name"] for x in presets
                             if x["model"] == lm and x["provider"] == lp]
                    if len(cands) == 1:
                        match, how = cands[0], "model/model_provider 一致（其余差异为宿主运行时噪音）"
            if match:
                core.write_state(p, match)
                print(f"      已初始化状态：当前预设 = {match}（{how}）")
            else:
                print("      无法唯一判定当前预设，未写入状态；"
                      "可在界面里用「另存为新预设」固化，或手工编辑 "
                      f"{p.state}")
        else:
            print(f"      状态已存在：当前预设 = {cur}")
    else:
        print("[4/4] [dry] 预设库初始化")

    print("\n部署完成。" if not dry else "\n演练完成，未做任何改动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
