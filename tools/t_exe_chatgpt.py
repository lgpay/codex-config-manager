# -*- coding: utf-8 -*-
"""IMP-016 打包产物烟测：确认带「启动 ChatGPT」的新 exe 能正常起界面。

为什么单独写一个：原 `t_exe_gui.py` 依赖**真实预设库中存在名为 `example` 的预设**，
用户删除该预设后它就退化为「窗口不出现」的假失败（见待办 IMP-017），
导致打包后的 GUI 路径实际失去覆盖。本脚本用**隔离的临时 CODEX_HOME**，
自带 `example` 预设，因此与本机真实预设库解耦。

只做只读烟测：不点击启动按钮、不真的启动 ChatGPT、不写任何配置。
"""

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXE = os.path.join(ROOT, "dist", "CodexConfigManager.exe")
TITLE = "Codex 配置管理器"

OK = FAIL = 0


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  ok   " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + (" " + extra if extra else ""))


PRESET = '''model_provider = "example"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
[model_providers.example]
name = "Example Provider"
base_url = "https://example.eu.org/v1"
env_key = "EXAMPLE_API_KEY"
wire_api = "responses"
'''

u32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def _collect(hwnd, _lparam):
    buf = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(hwnd, buf, 512)
    if buf.value:
        _found.append((hwnd, buf.value))
    return True


_CB = WNDENUMPROC(_collect)
_found = []


def windows():
    """枚举当前所有带标题的顶层窗口，返回 [(hwnd, title)]。"""
    _found.clear()
    u32.EnumWindows(_CB, None)
    return list(_found)


def tasklist_has(image):
    """tasklist 在中文系统上输出 GBK，必须按字节解码，不能用默认 utf-8。"""
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % image],
                       capture_output=True)
    out = (r.stdout or b"").decode("gbk", errors="replace").lower()
    return image.lower() in out


home = tempfile.mkdtemp(prefix="exe-chatgpt-")
codex = os.path.join(home, ".codex")
os.makedirs(os.path.join(codex, "configs"), exist_ok=True)
with open(os.path.join(codex, "configs", "example.toml"), "w", encoding="utf-8") as f:
    f.write(PRESET)
with open(os.path.join(codex, "config.toml"), "w", encoding="utf-8") as f:
    f.write(PRESET)

before = {p: hashlib.md5(open(p, "rb").read()).hexdigest()
          for p in (os.path.join(codex, "config.toml"),
                    os.path.join(codex, "configs", "example.toml"))}

env = dict(os.environ)
env["CODEX_HOME"] = codex
env["CODEX_CONFIG_MANAGER_SETTINGS"] = os.path.join(home, "settings.json")

chk("打包产物存在", os.path.isfile(EXE))
proc = subprocess.Popen([EXE, "edit", "example"], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    hit = None
    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(0.5)
        titles = [t for _, t in windows()]
        if any(TITLE in t for t in titles):
            hit = True
            break
    chk("带编辑器的窗口 25s 内出现", bool(hit))

    if hit:
        # WebView2 起来才算界面真的在渲染（不是空壳窗口）
        web = False
        deadline = time.time() + 15
        while time.time() < deadline:
            if tasklist_has("msedgewebview2.exe"):
                web = True
                break
            time.sleep(0.5)
        chk("WebView2 渲染进程已启动", web)

    # 正常关闭：向标题匹配的窗口发 WM_CLOSE
    sent = 0
    for h, t in windows():
        if TITLE in t:
            u32.PostMessageW(h, 0x0010, 0, 0)
            sent += 1
    chk("已发出关闭请求", sent >= 1, "sent=%d" % sent)

    gone = False
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(0.5)
        titles = [t for _, t in windows()]
        if not any(TITLE in t for t in titles):
            gone = True
            break
    chk("窗口已关闭", gone)

    time.sleep(2.0)
    chk("关闭后无残留进程", not tasklist_has("CodexConfigManager.exe"))
finally:
    try:
        proc.terminate()
    except Exception:
        pass
    time.sleep(1.0)

after = {p: hashlib.md5(open(p, "rb").read()).hexdigest() for p in before}
chk("隔离配置文件的 md5 未变", before == after, str((before, after)))

after_files = sorted(
    os.path.relpath(os.path.join(dp, fn), codex)
    for dp, _dn, fns in os.walk(codex) for fn in fns)
chk("隔离目录未新增/删除文件", after_files == ["config.toml", "configs\\example.toml"],
    str(after_files))

shutil.rmtree(home, ignore_errors=True)
print("\n通过 %d / 失败 %d" % (OK, FAIL))
sys.exit(1 if FAIL else 0)
