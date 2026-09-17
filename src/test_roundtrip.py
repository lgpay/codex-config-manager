# -*- coding: utf-8 -*-
"""隔离核心测试（IMP-001 配套）：全程使用临时 CODEX_HOME，不触碰真实配置。

重点验证「往返保真」——这是产品化承诺「不会破坏用户真实配置」的最强证据：
对一个预设提交一份「与现状完全相同」的编辑表单，输出必须与原文逐字节一致。
同时覆盖 切换 / 回收 / 另存 的基本正确性，并断言真实配置未被改动。
"""
import hashlib
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core  # noqa: E402

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [× ] ") + name + (("  -> " + extra) if (extra and not cond) else ""))


REAL = os.path.join(os.path.expanduser("~"), ".codex")
REAL_SMOKE = os.environ.get("CODEX_REAL_CONFIG_SMOKE") == "1"
real_before = None
if REAL_SMOKE and os.path.exists(os.path.join(REAL, "config.toml")):
    with open(os.path.join(REAL, "config.toml"), "rb") as stream:
        real_before = hashlib.sha256(stream.read()).hexdigest()

print("=" * 72)
print("0. 准备隔离环境（自带合成数据，不依赖真实配置）")
root = tempfile.mkdtemp(prefix="cxs-rt-")
p = core.Paths(root)
core.ensure_layout(p)
# 测试隔离：给临时目录一个不会命中的守卫名单，避免被本机正在运行的宿主进程拦截
# （仅影响本测试目录；真实 DEFAULT_GUARD 与连接安全断言不受影响）。
p.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
print("   CODEX_HOME =", root)

# 一个有注释、多行、外部段 [windows] 的配置文件，用来检验「只改目标键」的保真
PRESET = '''# Codex 配置（用户手写注释应保留）
model = "gpt-5.6-luna"
model_provider = "example"
model_reasoning_effort = "medium"

[model_providers.example]
name = "Example Provider"
base_url = "https://example.eu.org/v1"
env_key = "EXAMPLE_API_KEY"
wire_api = "responses"

[windows]
sandbox = "unelevated"   # 宿主写入，绝不能被清掉
'''
(p.lib / "example.toml").write_text(PRESET, encoding="utf-8")
(p.lib / "official.toml").write_text(
    'model_reasoning_effort = "medium"\n', encoding="utf-8")
p.live.write_text(PRESET, encoding="utf-8")
core.write_state(p, "example")

print("\n1. 往返保真：提交「与现状完全相同」的表单，输出应逐字节不变")
f = core.read_preset_form(p, "example")
# 用表单里现有的真实值构造一份「无改动」表单
form = {
    "preset": "example", "new_name": "example",
    "model": f["model"], "model_provider": f["model_provider"],
    "reasoning": f["reasoning"], "prov_name": f["prov_name"],
    "base_url": f["base_url"], "env_key": f["env_key"], "wire_api": f["wire_api"],
    "edit_provider": f.get("orig_provider_id") or "", "drop_provider": "",
}
new_text = core.apply_form_to_text(PRESET, form)
check("无改动表单 → 输出与原文逐字节相同", new_text == PRESET,
      "len %d vs %d" % (len(new_text), len(PRESET)))
pv = core.preview_edit(p, "example", form)
check("preview_edit 判定为完全一致 (same)", pv.get("same") is True)
check("preview_edit 无差异行", pv.get("changed", 1) == 0)
# 注释与 [windows] 段必须原样保留
check("用户注释保留", "# Codex 配置" in new_text and "用户手写注释应保留" in new_text)
check("宿主 [windows] 段保留", core.read_key(new_text, "windows", "sandbox") == "unelevated")

print("\n2. 只有改动写入，且结构不破")
form2 = dict(form, model="gpt-6-probe", base_url="https://new.eu.org/v2")
rt2 = core.apply_form_to_text(PRESET, form2)
check("model 已更新", core.read_key(rt2, None, "model") == "gpt-6-probe")
check("base_url 已更新", core.read_key(rt2, "model_providers.example", "base_url") == "https://new.eu.org/v2")
check("未改键 model_provider 仍在", core.read_key(rt2, None, "model_provider") == "example")
check("供应商块 name 仍在", core.read_key(rt2, "model_providers.example", "name") == "Example Provider")
check("宿主 [windows] sandbox 仍在", core.read_key(rt2, "windows", "sandbox") == "unelevated")
check("注释未被清掉", "# Codex 配置" in rt2)

print("\n3. 切换：example -> official（含自动回收）")
core.atomic_write_bytes(p.live, (PRESET + "\n# host-wrote\n").encode())
rep = core.Reporter()
r = core.run_switch(p, "official", rep=rep)
check("切换成功", r["ok"])
check("发生了回收", r.get("harvested") is True)
check("example.toml 含宿主写入", b"host-wrote" in p.lib.joinpath("example.toml").read_bytes())
check("现役 == official", p.live.read_bytes() == (p.lib / "official.toml").read_bytes())
check(".state = official", core.read_state(p)[0] == "official")

print("\n4. 只回收不切换：现役改动回写当前预设，现役/状态不变")
core.write_state(p, "official")
core.atomic_write_bytes(p.live, (PRESET + "\n# only-harvest\n").encode())
st_before = core.read_state(p)
live_before = p.live.read_bytes()
rep = core.Reporter()
r = core.run_harvest_only(p, rep=rep)
check("回收成功", r["ok"] and r.get("harvested") is True)
check("现役未改动", p.live.read_bytes() == live_before)
check("状态未改动", core.read_state(p) == st_before)
check("official.toml 含 only-harvest", b"only-harvest" in (p.lib / "official.toml").read_bytes())

print("\n5. 另存为新预设 + 拒绝覆盖")
rep = core.Reporter()
check("另存成功", core.run_save_as(p, "snapshot-x", rep=rep)["ok"])
check("重复另存被拒绝", not core.run_save_as(p, "snapshot-x")["ok"])
check("保留名被拒绝", not core.run_save_as(p, "state")["ok"])
check("非法名被拒绝", not core.run_save_as(p, "bad name")["ok"])

print("\n6. 隔离与可选真实只读 smoke")
if real_before is not None:
    with open(os.path.join(REAL, "config.toml"), "rb") as stream:
        after = hashlib.sha256(stream.read()).hexdigest()
    check("真实 config.toml 逐字节不变", real_before == after)
else:
    print("   （默认跳过真实配置读取；设置 CODEX_REAL_CONFIG_SMOKE=1 可启用只读指纹核对）")
check("测试全程在临时目录", str(p.root).startswith(tempfile.gettempdir()))

print("\n" + "=" * 72)
print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
if FAIL:
    for x in FAIL:
        print("  FAILED:", x)
shutil.rmtree(root, ignore_errors=True)
sys.exit(1 if FAIL else 0)
