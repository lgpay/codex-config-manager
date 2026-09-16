# -*- coding: utf-8 -*-
"""验证打包后的 exe：`edit <名>` 能弹出窗口并停在编辑器上，且只读不写盘。"""
import ctypes
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXE = os.environ.get("CODEX_MANAGER_EXE", str(ROOT / "dist" / "CodexConfigManager.exe"))
REAL_SMOKE = os.environ.get("CODEX_REAL_CONFIG_SMOKE") == "1"
HOME = Path.home()
TARGETS = ([HOME / ".codex" / "config.toml",
            HOME / ".codex" / "configs" / "example.toml",
            HOME / ".codex" / "configs" / "official.toml",
            HOME / ".codex" / "configs" / ".state"] if REAL_SMOKE else [])

OK = FAIL = 0


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def fingerprint():
    return {str(p): hashlib.md5(p.read_bytes()).hexdigest() for p in TARGETS if p.exists()}


u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32.FindWindowW.restype = wintypes.HWND
u32.IsWindowVisible.argtypes = [wintypes.HWND]
u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]


def find_window(title_frag):
    """按标题片段找顶层窗口。返回 (hwnd, 标题, 可见)。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        n = u32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if title_frag in buf.value:
                found.append((hwnd, buf.value, bool(u32.IsWindowVisible(hwnd))))
        return True

    u32.EnumWindows(cb, 0)
    return found


def proc_list():
    """用 core 里已验证过的 ctypes 实现，避免自己瞎写结构体布局。"""
    return [nm for _pid, nm, _p in core.list_processes(with_path=False)]


print("== 打包后 GUI：edit example ==")
before = fingerprint()
settings_probe = tempfile.TemporaryDirectory(prefix="exe-settings-")
env = dict(os.environ)
env[core.SETTINGS_ENV] = str(Path(settings_probe.name) / "settings.json")
p = subprocess.Popen([EXE, "edit", "example"], cwd=str(HOME), env=env)
hwnd = None
t0 = time.time()
while time.time() - t0 < 25:
    hits = find_window("Codex 配置管理器")
    if hits:
        hwnd, title, vis = hits[0]
        break
    time.sleep(0.3)

chk("窗口在 25s 内出现", hwnd is not None, "未找到窗口")
if hwnd:
    # 窗口刚 CreateWindow 时还没 ShowWindow，等它真正可见
    t1 = time.time()
    vis = False
    while time.time() - t1 < 6:
        hits = find_window("Codex 配置管理器")
        if hits and any(v for _h, _t, v in hits):
            vis = True
            break
        time.sleep(0.25)
    hits = find_window("Codex 配置管理器")
    chk("窗口变为可见", vis, hits)
    chk("窗口标题正确", "Codex 配置管理器" in hits[0][1], hits[0][1])
    print(f"      出现用时 {time.time()-t0:.1f}s   hwnd={hwnd}  标题={hits[0][1]!r}")
    time.sleep(4.0)                      # 留时间给 WebView2 加载 + 编辑器打开
    procs = proc_list()
    chk("exe 进程存活", any("CodexConfigManager.exe" in x for x in procs))
    chk("WebView2 已起", any("msedgewebview2.exe" in x for x in procs))
    still = find_window("Codex 配置管理器")
    chk("窗口仍在（未崩溃）", bool(still) and still[0][2], still)
    # 关闭窗口
    u32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
    t0 = time.time()
    while time.time() - t0 < 15:
        if not p.poll():
            pass
        if not find_window("Codex 配置管理器"):
            break
        time.sleep(0.3)
    chk("窗口已关闭", not find_window("Codex 配置管理器"))
    # onefile 两进程模型 + WebView2 拆栈需要几秒：轮询等待进程真正清空，
    # 不要写死 1.2s（否则会把正常的拆栈延迟误判为残留进程）。
    t0 = time.time()
    while time.time() - t0 < 10:
        if not any("CodexConfigManager.exe" in x for x in proc_list()):
            if p.poll() is not None:
                break
        time.sleep(0.3)
    procs = proc_list()
    chk("无残留 CodexConfigManager 进程",
        not any("CodexConfigManager.exe" in x for x in procs),
        [x for x in procs if "Codex" in x])

    chk("父进程已退出", p.poll() is not None, p.poll())

print("== 只读性：配置文件指纹未变 ==")
after = fingerprint()
chk("全部目标文件 md5 未变", before == after,
    {k: (before.get(k), after.get(k)) for k in before if before.get(k) != after.get(k)})
for k, v in sorted(after.items()):
    print(f"      {v[:12]}  {k}")

print("== 打包后 GUI：edit 不存在的预设应报错退出 ==")
r = subprocess.run([EXE, "edit", "ghost"], capture_output=True, timeout=30, env=env)
chk("退出码非 0", r.returncode != 0, r.returncode)
chk("无窗口弹出", not find_window("Codex 配置管理器"))
print("      stderr/stdout:", (r.stdout or b"").decode("utf-8", "replace").strip()[:200])

settings_probe.cleanup()
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
