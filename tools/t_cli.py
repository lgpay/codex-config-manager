# -*- coding: utf-8 -*-
"""命令行通道自检：info / set / edit 的参数处理，全程隔离。"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import app  # noqa: E402
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
[model_providers.example]
name = "Example Provider"
base_url = "https://example.eu.org/v1"
env_key = "EXAMPLE_API_KEY"
wire_api = "responses"

[windows]
sandbox = "unelevated"
'''

root = tempfile.mkdtemp(prefix="codecli_")
os.environ["CODEX_HOME"] = root
p = core.Paths(root)
core.ensure_layout(p)
# 隔离测试：不匹配用户真实宿主；守卫分支由核心专项测试覆盖。
p.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(p.lib / "example.toml").write_text(PRESET, encoding="utf-8")
core.write_state(p, "example")
(p.live).write_text(PRESET, encoding="utf-8")

buf = []
app._out = lambda text="": buf.append(text)


def run(*argv):
    buf.clear()
    return app.main(list(argv))


print("== info ==")
rc = run("info", "example")
txt = "\n".join(buf)
for l in buf:
    print("      |", l)
chk("退出码 0", rc == 0, rc)
chk("标出正在使用", "[正在使用中]" in txt, txt)
chk("列出 URL", "https://example.eu.org/v1" in txt)
chk("列出模型", "gpt-5.6-luna" in txt)
chk("密钥变量已显示", "EXAMPLE_API_KEY" in txt)

print("== set 官方预设（无 model_provider）的 url ==")
(p.lib / "ofc.toml").write_text(
    'model_reasoning_effort = "medium"\n'
    '[model_providers.example]\n'
    'name = "Example Provider"\n'
    'base_url = "https://example.eu.org/v1"\n'
    'env_key = "EXAMPLE_API_KEY"\n'
    'wire_api = "responses"\n', encoding="utf-8")
rc = run("set", "ofc", "url", "https://ofc.example/v3")
for l in buf:
    print("      |", l)
_t = (p.lib / "ofc.toml").read_text(encoding="utf-8")
chk("退出码 0", rc == 0, rc)
chk("块 URL 已改", core.read_key(_t, "model_providers.example", "base_url")
    == "https://ofc.example/v3", _t)
chk("没有偷偷加上 model_provider", core.read_key(_t, None, "model_provider") is None, _t)
chk("现役未被动（ofc 非当前）",
    core.read_key(p.live.read_text(encoding="utf-8"), None, "model") != "gpt-9",
    core.read_key(p.live.read_text(encoding="utf-8"), None, "model"))
rc = run("set", "ofc", "wire_api", "chat")
_t = (p.lib / "ofc.toml").read_text(encoding="utf-8")
chk("wire_api 也已改", core.read_key(_t, "model_providers.example", "wire_api") == "chat", _t)

print("== info 不存在的预设 ==")
rc = run("info", "nope")
chk("退出码非 0", rc == 1, rc)
chk("有报错", "找不到预设" in "\n".join(buf), buf)

print("== set url ==")
rc = run("set", "example", "url", "https://new.example/v1", "--force")
for l in buf:
    print("      |", l)
chk("退出码 0", rc == 0, rc)
t = (p.lib / "example.toml").read_text(encoding="utf-8")
chk("url 已改", 'base_url = "https://new.example/v1"' in t)
chk("宿主的 windows 段还在", core.read_key(t, "windows", "sandbox") == "unelevated")
chk("现役已同步", p.live.read_text(encoding="utf-8") == t)

print("== set 中文别名 ==")
rc = run("set", "example", "模型", "kimi-k2", "--force")
chk("退出码 0", rc == 0, rc)
t = (p.lib / "example.toml").read_text(encoding="utf-8")
chk("model 已改", core.read_key(t, None, "model") == "kimi-k2", core.read_key(t, None, "model"))

print("== set rename ==")
rc = run("set", "example", "rename", "example-pro", "--force")
for l in buf:
    print("      |", l)
chk("退出码 0", rc == 0, rc)
chk("文件已改名", (p.lib / "example-pro.toml").exists())
chk("状态跟到新名", core.read_state(p)[0] == "example-pro", core.read_state(p))

print("== set 未知字段 ==")
rc = run("set", "example-pro", "nonsense", "x")
chk("退出码 2", rc == 2, rc)
chk("提示可用字段", "可用字段" in "\n".join(buf), buf)

print("== set 非法值应被拒 ==")
rc = run("set", "example-pro", "url", "not-a-url", "--force")
chk("退出码非 0", rc == 1, rc)
chk("有报错", "Base URL" in "\n".join(buf), buf)
chk("文件未被写坏", core.read_key(
    (p.lib / "example-pro.toml").read_text(encoding="utf-8"), None, "model") == "kimi-k2")

print("== set 演练 ==")
before = (p.lib / "example-pro.toml").read_bytes()
rc = run("set", "example-pro", "url", "https://dry.example/v1", "-n", "--force")
chk("退出码 0", rc == 0, rc)
chk("演练未写盘", (p.lib / "example-pro.toml").read_bytes() == before)

print("== set 参数不足 ==")
rc = run("set", "example-pro", "url")
chk("退出码 2", rc == 2, rc)
chk("给出用法", "用法：set" in "\n".join(buf), buf)

print("== edit 指向不存在的预设 ==")
rc = run("edit", "ghost")
chk("退出码非 0", rc == 1, rc)
chk("有报错", "找不到预设" in "\n".join(buf), buf)

print("== edit 非法名 ==")
rc = run("edit", "../evil")
chk("退出码 2", rc == 2, rc)

print("== list 带出 url ==")
rc = run("list")
txt = "\n".join(buf)
chk("退出码 0", rc == 0)
chk("列表含新预设", "example-pro" in txt, txt)

print("== --help 含新命令 ==")
rc = run("--help")
txt = "\n".join(buf)
chk("help 提到 edit", "edit <名>" in txt)
chk("help 提到 set", "set <名> <字段> <值>" in txt)
chk("help 提到 info", "info <名>" in txt)

print("== Api 层：preset_form / preview_edit / run(edit) ==")
api = app.Api(p)
f = api.preset_form("example-pro")
chk("preset_form ok", f.get("ok") is True and not f.get("error"), f.get("error"))
chk("带出 guard_running", "guard_running" in f)
chk("带出 blocks", isinstance(f.get("blocks"), dict) and "example" in f["blocks"], f.get("blocks"))
chk("带出 is_current", f["is_current"] is True)
pv = api.preview_edit("example-pro", dict(
    {k: f.get(k) or "" for k in app.SET_FIELDS},
    preset="example-pro", new_name="example-pro"))
chk("preview 无改动", pv.get("same") is True, pv)
r = api.run("edit", "example-pro", {"form_json": "not json"})
chk("坏 JSON 被拒", "error" in r, r)
r = api.run("edit", "example-pro", {"form_json": '"a string"'})
chk("非对象被拒", "error" in r, r)

import time  # noqa: E402
r = api.run("edit", "example-pro", {"form_json": __import__("json").dumps(dict(
    {k: f.get(k) or "" for k in app.SET_FIELDS},
    preset="example-pro", new_name="example-pro", base_url="https://api2.example/v1"))})
chk("异步已启动", r.get("started") is True, r)
for _ in range(80):
    j = api.poll()
    if not j["running"]:
        break
    time.sleep(0.05)
chk("异步已完成", api.poll()["result"] is not None)
chk("异步结果 ok", api.poll()["result"]["ok"] is True, api.poll()["result"])
chk("异步写盘生效", "api2.example" in (p.lib / "example-pro.toml").read_text(encoding="utf-8"))

print("== initial() ==")
chk("无初始预设 -> 空", app.Api(p).initial() == {})
chk("有初始预设 -> 带出", app.Api(p, initial="kimi").initial() == {"preset": "kimi"})

shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
