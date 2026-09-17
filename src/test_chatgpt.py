# -*- coding: utf-8 -*-
"""IMP-018：「启动 ChatGPT」联动判定（core 层）单元测试。

重点验证**两套状态不混用**：
  * `guard.running`    —— 宿主合并名单（ChatGPT.exe + codex.exe + codex-*.exe，且可自定义）
  * `chatgpt_state()`  —— 只看 ChatGPT 自身，并区分「界面已打开」与「仅后台驻留」

进程数据全部**注入**，不依赖本机真实安装；窗口枚举只做只读调用。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [OK] " + name)
    else:
        FAIL += 1
        print("  [FAIL] " + name + ("  " + extra if extra else ""))


PROCS = [
    (101, "ChatGPT.exe", r"C:\x\ChatGPT.exe"),
    (102, "codex.exe", r"C:\x\codex.exe"),
    (103, "codex-code-mode-host.exe", r"C:\x\codex-code-mode-host.exe"),
    (104, "chatgpt.exe", r"C:\x\chatgpt.exe"),          # 大小写不同的同名进程
    (105, "explorer.exe", r"C:\Windows\explorer.exe"),
]

print("\n1. 只匹配 ChatGPT 自身，不吞并 codex.exe")
hits = core.chatgpt_processes(PROCS)
pids = sorted(h["pid"] for h in hits)
check("命中两个 ChatGPT 进程（大小写不敏感）", pids == [101, 104], str(pids))
check("不把 codex.exe 算作 ChatGPT",
      all(h["pid"] not in (102, 103) for h in hits), str(pids))
check("不把无关进程算进来",
      all(h["name"].lower() == "chatgpt.exe" for h in hits), str([h["name"] for h in hits]))

print("\n2. 与宿主守卫名单语义不同（不可互换）")
guard_hits = core.match_processes(list(core.DEFAULT_GUARD), PROCS)
check("守卫名单命中的更多（含 codex 系列）", len(guard_hits) > len(hits),
      "guard=%d chatgpt=%d" % (len(guard_hits), len(hits)))
check("守卫运行不代表 ChatGPT 已打开",
      bool(guard_hits) and len([h for h in guard_hits
                                if h["name"].lower() == "chatgpt.exe"]) < len(guard_hits),
      str([h["name"] for h in guard_hits]))

print("\n3. 仅有 codex.exe 时，ChatGPT 判定必须为未运行")
only_codex = [(201, "codex.exe", ""), (202, "codex-computer-use-swift.exe", "")]
st = core.chatgpt_state(procs=only_codex)
check("running 为假", st["running"] is False, str(st))
check("windowed 为假", st["windowed"] is False, str(st))
check("count 为 0", st["count"] == 0, str(st))

print("\n4. chatgpt_state 结构与环境无关断言")
st = core.chatgpt_state(procs=[])
check("空进程表 → 全假且计数 0",
      st == {"running": False, "windowed": False, "count": 0}, str(st))
check("键集合固定", set(st) == {"running", "windowed", "count"}, str(sorted(st)))
st2 = core.chatgpt_state(procs=PROCS)
check("注入 ChatGPT 进程 → running 为真且计数正确",
      st2["running"] is True and st2["count"] == 2, str(st2))
check("不存在的 pid 不会被当成「有窗口」", st2["windowed"] is False, str(st2))
live = core.chatgpt_state()
check("真实调用不抛异常且结构完整",
      isinstance(live, dict) and set(live) == {"running", "windowed", "count"}, str(live))
print("       （本机实际：running=%s windowed=%s count=%s）"
      % (live["running"], live["windowed"], live["count"]))

print("\n5. 窗口判定的边界")
check("空 pid 集合直接返回空", core.visible_window_pids([]) == set())
check("纯伪造 pid 返回空集合", core.visible_window_pids([999999999]) == set())
check("返回值类型为集合", isinstance(core.visible_window_pids([os.getpid()]), set))

print("\n6. snapshot 带上联动字段，且不影响既有字段")
tmp = Path(tempfile.mkdtemp(prefix="t_chatgpt_"))
os.environ["CODEX_HOME"] = str(tmp)
os.environ["CODEX_CONFIG_MANAGER_SETTINGS"] = str(tmp / "settings.json")
p = core.Paths(tmp)
core.ensure_layout(p)
p.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
PRESET = 'model_provider = "mock"\nmodel = "m"\n'
(p.lib / "mock.toml").write_text(PRESET, encoding="utf-8")
p.live.write_text(PRESET, encoding="utf-8")
core.write_state(p, "mock")
snap = core.snapshot(p)
check("snapshot 含 chatgpt 字段", "chatgpt" in snap, str(sorted(snap))[:200])
check("chatgpt 字段结构正确",
      set(snap["chatgpt"]) == {"running", "windowed", "count"}, str(snap.get("chatgpt")))
check("既有 guard 字段未受影响", "running" in snap["guard"] and "hits" in snap["guard"])
check("中性守卫名单下守卫未运行（未误伤真实进程）", snap["guard"]["running"] is False,
      str([h["name"] for h in snap["guard"]["hits"]]))
check("预设列表仍正常", [x["name"] for x in snap["presets"]] == ["mock"],
      str(snap["presets"]))

# 清理
import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 72)
print("通过 %d / 失败 %d" % (OK, FAIL))
sys.exit(1 if FAIL else 0)
