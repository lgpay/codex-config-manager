# -*- coding: utf-8 -*-
"""核心层隔离测试：全程使用临时 CODEX_HOME，不触碰真实配置。"""
import hashlib, os, sys, shutil, tempfile, textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core

REAL = Path.home() / ".codex"
REAL_SMOKE = os.environ.get("CODEX_REAL_CONFIG_SMOKE") == "1"
PASS, FAIL = [], []

def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [× ] ") + name + (("  " + extra) if extra and not cond else ""))

def show(rep):
    for l in rep:
        print("       | " + l["text"])

print("=" * 72)
print("0. 准备隔离环境（默认只使用合成数据）")
root = Path(tempfile.mkdtemp(prefix="cxs-test-"))
(root / "configs").mkdir(parents=True)
example = '''# 合成测试配置\nmodel = "example-model"\nmodel_provider = "example"\n\n[model_providers.example]\nname = "Example Provider"\nbase_url = "https://provider.example/v1"\nenv_key = "EXAMPLE_API_KEY"\nwire_api = "responses"\n'''
official = 'model_reasoning_effort = "medium"\n'
(root / "config.toml").write_text(example, encoding="utf-8")
(root / "configs" / "example.toml").write_text(example, encoding="utf-8")
(root / "configs" / "official.toml").write_text(official, encoding="utf-8")
os.environ["CODEX_HOME"] = str(root)
print("   CODEX_HOME =", root)
print("   预设:", [f.stem for f in (root / "configs").glob("*.toml")])

p = core.Paths()
# 隔离测试：默认不匹配用户真实宿主；第13节会改成 ChatGPT.exe 专门验证拦截。
core.atomic_write_bytes(p.guard, b"__test_neutral_guard__.exe\n")
real_before = (hashlib.sha256((REAL / "config.toml").read_bytes()).hexdigest()
               if REAL_SMOKE and (REAL / "config.toml").is_file() else None)

print("\n1. 路径解析与快照")
st = core.snapshot(p)
check("snapshot 可用", st["presets"] and st["live_exists"])
check("预设数量 >= 2", len(st["presets"]) >= 2, str(len(st["presets"])))
print("   当前预设 =", st["current"], "| 有未回收变化 =", st["changed"])

print("\n2. 首次建立状态（§12.2：把现役配置对应的预设设为当前）")
check("既有 example 预设存在", core.preset_path(p, "example").exists())
core.write_state(p, "example")
r = core.run_save_as(p, "work-copy")
check("另存为新预设", r["ok"], str(r["lines"]))
check("重复另存被拒绝", not core.run_save_as(p, "work-copy")["ok"])
check("非法名被拒绝", not core.run_save_as(p, "a b/c")["ok"])
check("保留名被拒绝", not core.run_save_as(p, "state")["ok"])
core.preset_path(p, "work-copy").unlink()
check(".state 指向 example", core.read_state(p)[0] == "example")

print("\n3. 切换 example -> official（先制造‘未回收变化’）")
core.atomic_write_bytes(p.live, core.read_bytes(p.live) + b"\n# simulated-host-write\n")
before_live = core.read_bytes(p.live)
rep = core.Reporter()
r = core.run_switch(p, "official", rep=rep)
show(rep.lines)
check("切换成功", r["ok"])
check("发生了回收", r.get("harvested"))
check("example.toml 已被回收（含宿主写入）", b"simulated-host-write" in core.read_bytes(core.preset_path(p, "example")))
check("回收前版本已备份", any(p.hist_presets.glob("example/*.toml")))
check("现役 == official（逐字节）", core.read_bytes(p.live) == core.read_bytes(core.preset_path(p, "official")))
check(".state = official", core.read_state(p)[0] == "official")
check("现役快照已存", any(p.hist_live.iterdir()))

print("\n4. 无变化时跳过回收")
rep = core.Reporter()
r = core.run_switch(p, "example", rep=rep)
show(rep.lines)
check("切换成功", r["ok"])
check("本次未回收", not r.get("harvested"))

print("\n5. 演练模式（零写入）")
snap_before = {str(x.relative_to(root)): core.read_bytes(x)
               for x in root.rglob("*") if x.is_file()}
rep = core.Reporter()
r = core.run_switch(p, "official", dry=True, rep=rep)
show(rep.lines)
snap_after = {str(x.relative_to(root)): core.read_bytes(x)
              for x in root.rglob("*") if x.is_file()}
check("演练成功", r["ok"])
check("演练零写入", snap_before == snap_after)

print("\n6. 跳过回收 --no-harvest")
core.atomic_write_bytes(p.live, core.read_bytes(p.live) + b"\n# another-write\n")
example_before = core.read_bytes(core.preset_path(p, "example"))
rep = core.Reporter()
r = core.run_switch(p, "example", no_harvest=True, rep=rep)
show(rep.lines)
check("切换成功", r["ok"])
check("预设未被回收改写", core.read_bytes(core.preset_path(p, "example")) == example_before)
check("仍有现役保底快照", len(list(p.hist_live.iterdir())) >= 2)

print("\n7. 只回收不切换")
core.atomic_write_bytes(p.live, core.read_bytes(p.live) + b"\n# harness-only\n")
state_before = core.read_state(p)
live_before = core.read_bytes(p.live)
rep = core.Reporter()
r = core.run_harvest_only(p, rep=rep)
show(rep.lines)
check("回收成功", r["ok"] and r.get("harvested"))
check("现役未改动", core.read_bytes(p.live) == live_before)
check("状态未改动", core.read_state(p) == state_before)
check("预设已更新", b"harness-only" in core.read_bytes(core.preset_path(p, "example")))

print("\n8. 无状态保底分支")
core.Paths().state.unlink()
core.atomic_write_bytes(p.live, b'model = "unheard-of"\n# nobody owns this\n')
rep = core.Reporter()
r = core.run_switch(p, "official", rep=rep)
show(rep.lines)
check("切换成功（保底不崩）", r["ok"])
check("含 no-state 警告码", "no-state" in r.get("warns", []))

print("\n9. 差异对比")
d = core.run_diff(p, "example")
check("diff 可用", d["ok"])
print("   改动行数 =", d["changed"], "| 行数 =", len(d["rows"]))
print("   " + "\n   ".join(("+ " if x["kind"] == "add" else "- " if x["kind"] == "del"
                            else "  ") + x["text"] for x in d["rows"][:8]))

print("\n10. 切换到不存在的预设")
rep = core.Reporter()
r = core.run_switch(p, "no-such-preset", rep=rep)
show(rep.lines)
check("明确报错", not r["ok"])

print("\n11. 历史目录不可写 → 中止且零写入")
hist = p.history
ro = root / "ro-hist"
shutil.copytree(hist, ro)
shutil.rmtree(hist)
# 用一个文件占位，使 mkdir 失败
with open(hist, "wb") as f:
    f.write(b"x")
core.atomic_write_bytes(p.live, b'model = "x"\n# xx\n')
live_before = core.read_bytes(p.live)
state_before = core.read_state(p)
rep = core.Reporter()
r = core.run_switch(p, "official", rep=rep)
show(rep.lines)
check("已中止", not r["ok"])
check("现役未被改动", core.read_bytes(p.live) == live_before)
check("状态未被写入", core.read_state(p) == state_before)
hist.unlink(); shutil.move(str(ro), str(hist))

print("\n12. 进程名单")
p.guard.unlink(missing_ok=True)
pats, src = core.guard_list(p)
check("无 .guard 时回退默认", src == "default" and set(pats) == set(core.DEFAULT_GUARD), f"{src} {pats}")
core.atomic_write_bytes(p.guard, "# 自定义\nChatGPT.exe\nnotepad.exe\n".encode())
pats, src = core.guard_list(p)
check("自定义名单生效", src == "file" and pats == ["ChatGPT.exe", "notepad.exe"], str(pats))
g = core.run_guard(p)
check("诊断可运行", "patterns" in g)
print("   扫描进程数 =", g["scanned"], "| 命中 =", g["total"],
      "|", [(h["name"], h["count"]) for h in g["hits"]])
core.atomic_write_bytes(p.guard, b"")
pats, src = core.guard_list(p)
check("空名单回退默认", src == "default-empty" and set(pats) == set(core.DEFAULT_GUARD))

print("\n13. 同名进程占位模拟（ChatGPT.exe 拦截）")
core.atomic_write_bytes(p.guard, b"ChatGPT.exe\n")
import subprocess, time
sys32 = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32")
dummy = root / "ChatGPT.exe"
shutil.copy2(os.path.join(sys32, "ping.exe"), dummy)
holder = subprocess.Popen([str(dummy), "-n", "40", "127.0.0.1"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
g = core.run_guard(p)
print("   命中:", [(h["name"], h["count"]) for h in g["hits"]])
hit = any(h["name"].lower() == "chatgpt.exe" for h in g["hits"])
check("占位 ChatGPT.exe 被识别", hit, str(g["hits"]))
rep = core.Reporter()
r = core.run_switch(p, "official", rep=rep)
show(rep.lines)
check("运行中被拦截", r["blocked"])
rep = core.Reporter()
r = core.run_switch(p, "official", dry=True, rep=rep)
check("演练不触发拦截", r["ok"])
rep = core.Reporter()
r = core.run_switch(p, "official", force=True, rep=rep)
check("强制后可执行", r["ok"])
holder.kill(); holder.wait()
time.sleep(0.4)
# 用户可能正在运行真实 ChatGPT/Codex；改回中性名单，只验证占位进程不再造成拦截。
core.atomic_write_bytes(p.guard, b"__test_neutral_guard__.exe\n")
check("进程结束后不再拦截", not core.run_guard(p)["running"])
dummy.unlink()

print("\n14. 隔离与可选真实只读 smoke")
if real_before is not None:
    real_after = hashlib.sha256((REAL / "config.toml").read_bytes()).hexdigest()
    check("真实 config.toml 逐字节不变", real_before == real_after)
else:
    print("   （默认跳过真实配置读取；设置 CODEX_REAL_CONFIG_SMOKE=1 可启用只读指纹核对）")
check("临时目录内确为测试内容", str(root) in str(p.live))

print("\n" + "=" * 72)
print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
shutil.rmtree(root, ignore_errors=True)
print("临时目录已清理:", not root.exists())
sys.exit(1 if FAIL else 0)
