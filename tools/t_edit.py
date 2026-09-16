# -*- coding: utf-8 -*-
"""run_edit 端到端自检：全程在临时 CODEX_HOME 里跑，不碰真实配置。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import core  # noqa: E402

OK = FAIL = 0


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


PRESET = '''model_provider = "example"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
[model_providers.example]
name = "Example Provider"
base_url = "https://example.eu.org/v1"
env_key = "EXAMPLE_API_KEY"
wire_api = "responses"

[windows]
sandbox = "unelevated"
'''

root = tempfile.mkdtemp(prefix="codedit_")
os.environ["CODEX_HOME"] = root
p = core.Paths(root)
core.ensure_layout(p)
(p.lib / "example.toml").write_text(PRESET, encoding="utf-8")
(p.lib / "official.toml").write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
core.write_state(p, "example")
# 现役 = example + 宿主运行期写进去的一行
(p.live).write_text(PRESET.replace('model = "gpt-5.6-luna"',
                                   'model = "gpt-5.6-luna"\napproval_policy = "never"'),
                    encoding="utf-8")

print("== 场景1：改当前预设（应 回收 -> 改 -> 同步现役） ==")
form = {
    "preset": "example", "new_name": "example",
    "model": "gpt-5.7-luna", "model_provider": "example", "reasoning": "high",
    "prov_name": "Example Provider", "base_url": "https://new.example.example/v1",
    "env_key": "EXAMPLE_API_KEY", "wire_api": "responses",
    "drop_provider": "",
}
rep = core.Reporter()
res = core.run_edit(p, "example", form, force=True, rep=rep)
for l in rep.lines:
    print("      |", l["text"])
chk("返回成功", res["ok"] and not res.get("blocked"))

preset_txt = (p.lib / "example.toml").read_text(encoding="utf-8")
live_txt = p.live.read_text(encoding="utf-8")
chk("预设里 base_url 已改", 'new.example.example' in preset_txt)
chk("预设里 model 已改", core.read_key(preset_txt, None, "model") == "gpt-5.7-luna")
chk("预设里 reasoning 已改", core.read_key(preset_txt, None, "model_reasoning_effort") == "high")
chk("宿主的 approval_policy 被回收保住", 'approval_policy = "never"' in preset_txt,
    repr(preset_txt[:200]))
chk("windows 段未受影响", core.read_key(preset_txt, "windows", "sandbox") == "unelevated")
chk("现役已同步（内容与预设一致）", live_txt == preset_txt)
chk("状态记录仍是 example", core.read_state(p)[0] == "example")
chk("现役无未回收差异", core.snapshot(p)["changed"] is False)
chk("历史里有回收前备份", len(list((p.hist_presets / "example").glob("*.toml"))) >= 1)
chk("历史里有现役快照", len(list(p.hist_live.glob("config.toml.*"))) >= 1)

print("== 场景2：改非当前预设 + 重命名 ==")
(p.lib / "official.toml").write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
form2 = {
    "preset": "official", "new_name": "kimi",
    "model": "kimi-k2", "model_provider": "kimi", "reasoning": "",
    "prov_name": "Kimi", "base_url": "https://api.moonshot.cn/v1",
    "env_key": "MOONSHOT_API_KEY", "wire_api": "chat",
    "drop_provider": "",
}
rep2 = core.Reporter()
res2 = core.run_edit(p, "official", form2, rep=rep2)
for l in rep2.lines:
    print("      |", l["text"])
chk("返回成功", res2["ok"])
chk("old 文件已消失", not (p.lib / "official.toml").exists())
chk("新文件已出现", (p.lib / "kimi.toml").exists())
new_txt = (p.lib / "kimi.toml").read_text(encoding="utf-8")
chk("新段已建", core.read_key(new_txt, "model_providers.kimi", "wire_api") == "chat")
chk("顶层 provider 指向 kimi", core.read_key(new_txt, None, "model_provider") == "kimi")
chk("新文件是合法 TOML", (lambda: (__import__("tomllib").loads(new_txt), True)[1])())
chk("现役未被改动", p.live.read_text(encoding="utf-8") == preset_txt)
chk("状态记录未被改动", core.read_state(p)[0] == "example")
chk("列表能列出 kimi", "kimi" in [x["name"] for x in core.list_presets(p)])
chk("列表带出 base_url",
    [x for x in core.list_presets(p) if x["name"] == "kimi"][0]["base_url"]
    == "https://api.moonshot.cn/v1")

print("== 场景3：改名当前预设（状态记录应跟着走） ==")
form3 = dict(form, new_name="example-pro", model="gpt-5.7-luna")
rep3 = core.Reporter()
res3 = core.run_edit(p, "example", form3, force=True, rep=rep3)
chk("返回成功", res3["ok"], res3)
chk("文件已改名", (p.lib / "example-pro.toml").exists() and not (p.lib / "example.toml").exists())
chk("状态记录跟到新名", core.read_state(p)[0] == "example-pro", core.read_state(p))
chk("现役与改名后预设一致", p.live.read_text(encoding="utf-8")
    == (p.lib / "example-pro.toml").read_text(encoding="utf-8"))

print("== 场景4：无改动不写盘 ==")
form4 = dict(form3, preset="example-pro", new_name="example-pro")
before = p.live.read_text(encoding="utf-8")
rep4 = core.Reporter()
res4 = core.run_edit(p, "example-pro", form4, force=True, rep=rep4)
chk("识别为无改动", res4.get("noop") is True, res4)
chk("现役未动", p.live.read_text(encoding="utf-8") == before)
chk("没有产生新备份",
    len(list((p.hist_presets / "example-pro").glob("*.toml"))) == 0,
    list((p.hist_presets / "example-pro").glob("*.toml")))

print("== 场景5：校验失败应拒绝 ==")
rep5 = core.Reporter()
res5 = core.run_edit(p, "kimi", dict(form2, preset="kimi", new_name="kimi",
                                     base_url="not-a-url"), rep=rep5)
chk("被拒绝", res5["ok"] is False)
chk("给出原因", any("Base URL" in l["text"] for l in rep5.lines), rep5.lines)

print("== 场景6：重名应拒绝 ==")
rep6 = core.Reporter()
res6 = core.run_edit(p, "kimi", dict(form2, preset="kimi", new_name="example-pro"), rep=rep6)
chk("被拒绝", res6["ok"] is False)
chk("给出原因", any("已存在" in l["text"] for l in rep6.lines), rep6.lines)

print("== 场景7：演练不落盘 ==")
snap_before = {f.name: f.read_bytes() for f in p.lib.glob("*.toml")}
rep7 = core.Reporter()
res7 = core.run_edit(p, "kimi", dict(form2, preset="kimi", new_name="dryrun",
                                     model="zzz"), dry=True, rep=rep7)
chk("演练成功", res7["ok"] and res7.get("dry"))
snap_after = {f.name: f.read_bytes() for f in p.lib.glob("*.toml")}
chk("预设库字节未变", snap_before == snap_after)
chk("没有新建 dryrun.toml", not (p.lib / "dryrun.toml").exists())

print("== 场景8：preview_edit 与 read_preset_form ==")
fm = core.read_preset_form(p, "kimi")
chk("读出 provider id", fm["model_provider"] == "kimi", fm)
chk("读出 base_url", fm["base_url"] == "https://api.moonshot.cn/v1")
chk("读出 env_set 字段", "env_set" in fm)
chk("is_current 正确（kimi 不是当前）", fm["is_current"] is False)
pv = core.preview_edit(p, "kimi", dict(form2, preset="kimi", new_name="kimi", model="kimi-k2.5"))
chk("预览成功", pv["ok"], pv)
# 改一行值算「一处」改动（一删一加配对计数）
chk("预览报出改动处数", pv["changed"] == 1, pv.get("changed"))
chk("预览差异行含删除与新增",
    {"del", "add"} <= {r["kind"] for r in pv["rows"]},
    [r["kind"] for r in pv["rows"]])
chk("预览不改盘", (p.lib / "kimi.toml").read_text(encoding="utf-8") == new_txt)
pv2 = core.preview_edit(p, "kimi", dict(form2, preset="kimi", new_name="kimi"))
chk("无改动预览 same=True", pv2["same"] is True)
pv3 = core.preview_edit(p, "kimi", dict(form2, preset="kimi", new_name="kimi",
                                       model_provider=""))
chk("供应商 ID 留空是合法的（走官方默认）", pv3["ok"] is True, pv3)
chk("留空会删掉顶层 model_provider", pv3["changed"] == 1, pv3.get("changed"))
pv4 = core.preview_edit(p, "kimi", {"preset": "kimi", "new_name": "kimi",
                                    "model_provider": "bad/id"})
chk("非法供应商 ID 仍被拒", pv4["ok"] is False and "model_provider" in pv4["errors"], pv4)

print("== 场景9：官方预设（无 model / model_provider） ==")
(p.lib / "official2.toml").write_text(
    'model_reasoning_effort = "medium"\n'
    '[model_providers.example]\n'
    'name = "Example Provider"\n'
    'base_url = "https://example.eu.org/v1"\n'
    'env_key = "EXAMPLE_API_KEY"\n'
    'wire_api = "responses"\n', encoding="utf-8")
fm2 = core.read_preset_form(p, "official2")
chk("model 读出为空", fm2["model"] == "", fm2["model"])
chk("provider 读出为空", fm2["model_provider"] == "", fm2["model_provider"])
chk("仍能发现已有供应商块", fm2["providers"] == ["example"], fm2["providers"])
chk("供应商块字段仍被读出", fm2["base_url"] == "https://example.eu.org/v1")
noop = {"model": "", "model_provider": "", "reasoning": "medium",
        "prov_name": "Example Provider", "base_url": "https://example.eu.org/v1",
        "env_key": "EXAMPLE_API_KEY", "wire_api": "responses",
        "preset": "official2", "new_name": "official2", "drop_provider": ""}
pv5 = core.preview_edit(p, "official2", noop)
chk("不改动时预览通过且无差异", pv5["ok"] is True and pv5["same"] is True, pv5)
_orig = (p.lib / "official2.toml").read_bytes()
_n = core.apply_form_to_text(_orig.decode("utf-8"), noop)
chk("官方预设往返逐字节相同", _n.encode("utf-8") == _orig)

# 官方预设改供应商块：走 edit_provider，绝不能顺手加上 model_provider
_edit = dict(noop, base_url="https://changed.example/v9", edit_provider="example")
pv6 = core.preview_edit(p, "official2", _edit)
chk("改块 URL 只算一处", pv6["ok"] and pv6["changed"] == 1, pv6)
_n2 = core.apply_form_to_text(_orig.decode("utf-8"), _edit)
chk("块 URL 已改", core.read_key(_n2, "model_providers.example", "base_url")
    == "https://changed.example/v9")
chk("没有偷偷加上 model_provider", core.read_key(_n2, None, "model_provider") is None,
    core.read_key(_n2, None, "model_provider"))
chk("未指定 edit_provider 时不动块", core.apply_form_to_text(
    _orig.decode("utf-8"), dict(noop, edit_provider="",
                                base_url="https://ignored.example/x"))
    .encode("utf-8") == _orig)

print("== 场景10：宿主运行时的守卫分支 ==")
# 用「当前解释器」冒充宿主：把它的进程名写进 .guard
_me = os.path.basename(sys.executable)
(p.guard).write_text(f"# test\n{_me}\n", encoding="utf-8")
_pats, _src = core.guard_list(p)
_hits = core.match_processes(_pats)
chk("守卫能命中当前解释器", bool(_hits), (_me, len(_hits)))

cur = core.read_state(p)[0]
chk("有当前预设可供测试", bool(cur), cur)

# 10a 改当前预设 -> 应被拦下
repA = core.Reporter()
resA = core.run_edit(p, cur, dict(
    {k: (core.read_preset_form(p, cur).get(k) or "") for k in
     ("model", "model_provider", "reasoning", "prov_name", "base_url", "env_key", "wire_api")},
    preset=cur, new_name=cur, model="blocked-value"), rep=repA)
chk("当前预设被拦下", resA["ok"] is False and resA.get("blocked") is True, resA)
chk("日志给出进程明细", any("可执行文件" in l["text"] for l in repA.lines),
    [l["text"] for l in repA.lines][:12])
_before = (p.lib / f"{cur}.toml").read_text(encoding="utf-8")
chk("被拦时未写盘", "blocked-value" not in _before)

# 10b 强制放行
repB = core.Reporter()
resB = core.run_edit(p, cur, dict(
    {k: (core.read_preset_form(p, cur).get(k) or "") for k in
     ("model", "model_provider", "reasoning", "prov_name", "base_url", "env_key", "wire_api")},
    preset=cur, new_name=cur, model="forced-value"), force=True, rep=repB)
chk("强制后成功", resB["ok"] is True, resB)
chk("强制写盘生效", core.read_key(
    (p.lib / f"{cur}.toml").read_text(encoding="utf-8"), None, "model") == "forced-value")
chk("强制时有告警", any("可能马上被覆盖" in l["text"] for l in repB.lines),
    [l["text"] for l in repB.lines])
chk("现役也被同步", core.read_key(p.live.read_text(encoding="utf-8"), None, "model")
    == "forced-value")

# 10c 非当前预设 -> 不需要守卫，不加 force 也能改
other = [x["name"] for x in core.list_presets(p) if x["name"] != cur][0]
repC = core.Reporter()
resC = core.run_edit(p, other, dict(
    {k: (core.read_preset_form(p, other).get(k) or "") for k in
     ("model", "model_provider", "reasoning", "prov_name", "base_url", "env_key", "wire_api")},
    preset=other, new_name=other, model="other-value"), rep=repC)
chk("非当前预设无需守卫", resC["ok"] is True and not resC.get("blocked"), resC)
chk("日志说明只改文件", any("只改动预设文件" in l["text"] for l in repC.lines),
    [l["text"] for l in repC.lines])
chk("现役未被动", core.read_key(p.live.read_text(encoding="utf-8"), None, "model")
    == "forced-value")

# 10d 演练模式即使在运行中也不拦截、不写盘
_snap = {f.name: f.read_bytes() for f in p.lib.glob("*.toml")}
repD = core.Reporter()
resD = core.run_edit(p, cur, dict(
    {k: (core.read_preset_form(p, cur).get(k) or "") for k in
     ("model", "model_provider", "reasoning", "prov_name", "base_url", "env_key", "wire_api")},
    preset=cur, new_name=cur, model="dry-value"), dry=True, rep=repD)
chk("演练不拦截", resD["ok"] is True, resD)
chk("演练未写盘", {f.name: f.read_bytes() for f in p.lib.glob("*.toml")} == _snap)

(p.guard).write_text("# test\n", encoding="utf-8")   # 清掉，避免影响后续

print("== 场景11：供应商块改名，字段必须跟着新名字走 ==")
SRC11 = ('model_provider = "example"\n'
         'model = "m1"\n'
         '[model_providers.example]\n'
         'name = "Example Provider"\n'
         'base_url = "https://old.example/v1"\n'
         'env_key = "OLD_KEY"\n'
         'wire_api = "responses"\n'
         '\n[windows]\nsandbox = "unelevated"\n')
form11 = {
    "preset": "rn", "new_name": "rn",
    "model": "m1", "model_provider": "kimi", "reasoning": "",
    "prov_name": "Kimi", "base_url": "https://renamed.example/v2",
    "env_key": "NEW_KEY", "wire_api": "chat",
    "edit_provider": "example",        # 界面里「当前正在编辑的块」
    "drop_provider": "example",        # 改名，旧块要删
}
t11 = core.apply_form_to_text(SRC11, form11)
chk("新块已建且带上了字段值",
    core.read_key(t11, "model_providers.kimi", "base_url") == "https://renamed.example/v2"
    and core.read_key(t11, "model_providers.kimi", "env_key") == "NEW_KEY"
    and core.read_key(t11, "model_providers.kimi", "wire_api") == "chat", t11)
chk("旧块已删除", "example" not in core.provider_ids(t11)
    and core.find_block(core.parse_blocks(t11), "model_providers.example") is None, t11)
chk("顶层 provider 已改", core.read_key(t11, None, "model_provider") == "kimi")
chk("其他段未受影响", core.read_key(t11, "windows", "sandbox") == "unelevated")
chk("结果是合法 TOML", (lambda: (__import__("tomllib").loads(t11), True)[1])())
chk("只有一个供应商块", core.provider_ids(t11) == ["kimi"], core.provider_ids(t11))

shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
