# -*- coding: utf-8 -*-
"""TOML 文本级编辑的快速自检（纯文本，不碰真实配置）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
import core  # noqa: E402

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


OK = FAIL = 0


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


SRC = '''# 顶部注释
model_provider = "example"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
notify = [ "a.exe", "turn-ended" ]
multi = [
  "a",
  "b",
]
[model_providers.example]
name = "Example Provider"          # 行尾注释
base_url = "https://example.eu.org/v1"
env_key = "EXAMPLE_API_KEY"
wire_api = "responses"

[windows]
sandbox = "unelevated"

[model_providers.kimi]
name = "Kimi"
base_url = "https://api.moonshot.cn/v1"
'''

print("== 解析结构 ==")
blocks = core.parse_blocks(SRC)
secs = [core._canon(b["section"]) for b in blocks]
chk("顶层块存在", secs[0] == "", secs)
chk("段顺序", secs[1:] == ["model_providers.example", "windows", "model_providers.kimi"], secs)
chk("provider_ids", core.provider_ids(SRC) == ["example", "kimi"], core.provider_ids(SRC))

print("== 读值 ==")
chk("顶层 model", core.read_key(SRC, None, "model") == "gpt-5.6-luna",
    core.read_key(SRC, None, "model"))
chk("段内 base_url", core.read_key(SRC, "model_providers.example", "base_url")
    == "https://example.eu.org/v1")
chk("行尾注释被剥掉", core.read_key(SRC, "model_providers.example", "name") == "Example Provider",
    repr(core.read_key(SRC, "model_providers.example", "name")))
chk("多行数组不被误当键", core.block_key_lines(
    SRC.split("\n"), core.find_block(blocks, None)) == [1, 2, 3, 4, 5],
    core.block_key_lines(SRC.split("\n"), core.find_block(blocks, None)))
chk("不存在的键 -> None", core.read_key(SRC, None, "nope") is None)

print("== 改值（保留其余字节） ==")
t1 = core.set_key(SRC, "model_providers.example", "base_url", "https://new.example/v1")
chk("只改了一行", t1.replace("https://new.example/v1", "https://example.eu.org/v1") == SRC)
chk("注释仍在", "# 顶部注释" in t1 and "# 行尾注释" in t1)
chk("多行数组仍在", 'multi = [\n  "a",\n  "b",\n]' in t1)

print("== 新增键 ==")
t2 = core.set_key(SRC, "model_providers.kimi", "env_key", "MOONSHOT_API_KEY")
chk("插到段末", 'base_url = "https://api.moonshot.cn/v1"\nenv_key = "MOONSHOT_API_KEY"' in t2)
chk("未串到别的段", core.read_key(t2, "windows", "sandbox") == "unelevated"
    and core.read_key(t2, "model_providers.example", "env_key") == "EXAMPLE_API_KEY"
    and core.provider_ids(t2) == ["example", "kimi"])
t3 = core.set_key(SRC, None, "model_reasoning_effort", "high")
chk("顶层改值不换位", t3.index('model_reasoning_effort = "high"') < t3.index("[model_providers.example]"))
t4 = core.set_key(SRC, None, "service_tier", "priority")
chk("顶层新增插在段前", t4.index("service_tier") < t4.index("[model_providers.example]"))

print("== 新建段 ==")
t5 = core.set_key(SRC, "model_providers.zzz", "base_url", "https://zzz/v1")
chk("新段已建", "[model_providers.zzz]" in t5 and t5.rstrip().endswith('base_url = "https://zzz/v1"'))

print("== 删除 ==")
t6 = core.set_key(SRC, None, "model_reasoning_effort", None)
chk("键已删", 'model_reasoning_effort' not in t6)
chk("其余未动", SRC.replace('model_reasoning_effort = "medium"\n', "") == t6)
t7 = core.remove_block(SRC, "model_providers.kimi")
chk("段已删", "kimi" not in t7 and "[windows]" in t7)
chk("删段后仍是合法结构", core.parse_blocks(t7)[-1]["section"] == "windows",
    core.parse_blocks(t7)[-1]["section"])

print("== 值转义 ==")
t8 = core.set_key(SRC, None, "model", 'a"b\\c')
chk("转义写回可读", core.read_key(t8, None, "model") == 'a"b\\c',
    repr(core.read_key(t8, None, "model")))
chk("toml 语法有效", (lambda: (__import__("tomllib").loads(t8), True)[1])())

print("== 表单 -> 文本 ==")
form = {
    "preset": "example", "new_name": "example-pro",
    "model": "gpt-5.6-pro", "model_provider": "kimi", "reasoning": "high",
    "prov_name": "Kimi", "base_url": "https://api.moonshot.cn/v1",
    "env_key": "MOONSHOT_API_KEY", "wire_api": "chat",
    "drop_provider": "example",
}
t9 = core.apply_form_to_text(SRC, form)
chk("顶层 model 已改", core.read_key(t9, None, "model") == "gpt-5.6-pro")
chk("model_provider 已改", core.read_key(t9, None, "model_provider") == "kimi")
chk("新块写入", core.read_key(t9, "model_providers.kimi", "wire_api") == "chat")
chk("旧块被移除", "example" not in t9)
chk("结果仍是合法 TOML", (lambda: (__import__("tomllib").loads(t9), True)[1])())
chk("windows 段未受影响", core.read_key(t9, "windows", "sandbox") == "unelevated")

print("== 校验 ==")
bad = dict(form, base_url="ftp://x", env_key="1bad", wire_api="grpc",
           model="a b", model_provider="a/b")
errs = core.validate_llm_form(bad)
chk("base_url 报错", "base_url" in errs)
chk("env_key 报错", "env_key" in errs)
chk("wire_api 报错", "wire_api" in errs)
chk("model 报错", "model" in errs)
chk("provider id 报错", "model_provider" in errs)
chk("合法表单无错", core.validate_llm_form(form) == {},
    core.validate_llm_form(form))

print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
