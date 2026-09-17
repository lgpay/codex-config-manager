# -*- coding: utf-8 -*-
"""无头 GUI 探针：验证配置编辑器的渲染、实时差异、校验与保存链路。

截图无法直接判读，因此改为读取 DOM 文本、控件值与元素几何量。
全程在临时 CODEX_HOME 中运行。
"""

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os

import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import app    # noqa: E402
import core   # noqa: E402
import ui     # noqa: E402

OK = FAIL = 0
LOG = []


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def same_len_url(orig):
    """构造一个与原 URL **等长**、形态合法的替换 URL。

    用于验证「等长替换不改变字节数」。骨架为 `https://probe<pad>.example/v1`，
    pad 按长度差补齐，因此不依赖任何硬编码长度。
    """
    base = "https://probe.example/v1"                       # 24 字符
    if len(orig) >= len(base):
        return "https://probe" + "x" * (len(orig) - len(base)) + ".example/v1"
    return base


def parse_byte_pair(text):
    """从差异提示里取出 `旧 → 新` 的字节数；取不到返回 (None, None)。"""
    m = re.search(r"(\d+)\s*→\s*(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


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

root = tempfile.mkdtemp(prefix="codegui_")
os.environ["CODEX_HOME"] = root
paths = core.Paths(root)
core.ensure_layout(paths)
# 测试隔离：给临时目录一个不会命中的守卫名单，避免被本机正在运行的宿主进程拦截
# （仅影响本测试目录；真实 DEFAULT_GUARD 与连接安全断言不受影响）。
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "example.toml").write_text(PRESET, encoding="utf-8")
core.write_state(paths, "example")
paths.live.write_text(PRESET, encoding="utf-8")

import webview  # noqa: E402


api = app.Api(paths)
win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api,
                            width=980, height=720, min_size=(780, 560))

RES = {}


def js(code, default=None):
    try:
        return win.evaluate_js(code)
    except Exception as e:                                      # noqa: BLE001
        return f"<js error: {e}>"


def wait_ready(timeout=12):
    # 注意：脚本里用的是顶层 let，不会挂到 window 上，只能按作用域判断
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0") == 1:
            return True
        time.sleep(0.2)
    return False


def worker():
    # 隔离：核心层用 os.environ 判断「密钥已设置」，这里显式设一个假的隔离值，
    # 使该断言不依赖本机真实用户环境变量；只影响本进程，结束时恢复。
    prev_api_key = os.environ.get("EXAMPLE_API_KEY")
    os.environ["EXAMPLE_API_KEY"] = "probe-isolated-value-not-a-real-key"
    try:
        chk("界面就绪（STATE 已加载）", wait_ready(), "STATE 未就绪")
        time.sleep(0.4)

        print("== 入口 ==")
        chk("有「编辑配置…」按钮", js("!!document.getElementById('b-edit')"))
        chk("预设已选中", js("SELECTED") == "example", js("SELECTED"))
        chk("按钮已启用", js("!document.getElementById('b-edit').disabled"))
        chk("卡片带 title 提示", "双击" in (js("document.querySelector('.card').title") or ""))
        chk("卡片显示 url", "example.eu.org" in (js("document.querySelector('.card').textContent") or ""),
            js("document.querySelector('.card').textContent"))
        chk("JS 无异常（renderStatus 可用）", js("document.getElementById('status').children.length") > 0)

        print("== 打开编辑器 ==")
        js("openEditor('example');")
        t0 = time.time()
        while time.time() - t0 < 8:
            if js("document.getElementById('backdrop').classList.contains('on')") is True:
                break
            time.sleep(0.2)
        chk("弹层已打开", js("document.getElementById('backdrop').classList.contains('on')") is True)
        time.sleep(1.0)                      # 等 220ms 防抖的实时预览跑完
        title = js("document.getElementById('m-title').textContent") or ""
        chk("标题含预设名", "example" in title, title)
        chk("标题标出正在使用", "正在使用" in title, title)

        print("== 字段初值 ==")
        for fid, want in (("e-name", "example"), ("e-model", "gpt-5.6-luna"),
                          ("e-provider", "example"), ("e-pname", "Example Provider"),
                          ("e-url", "https://example.eu.org/v1"),
                          ("e-envkey", "EXAMPLE_API_KEY")):
            got = js(f"document.getElementById('{fid}').value")
            chk(f"{fid} = {want}", got == want, repr(got))
        chk("推理强度下拉已选中", js("document.getElementById('e-reason').value") == "medium",
            js("document.getElementById('e-reason').value"))
        chk("接口协议下拉已选中", js("document.getElementById('e-wire').value") == "responses")
        chk("段名标签正确",
            js("document.getElementById('e-sectag').textContent") == "[model_providers.example]",
            js("document.getElementById('e-sectag').textContent"))
        chk("密钥已设置提示（隔离环境变量下）",
            "已设置" in (js("document.getElementById('m-body').textContent") or ""),
            (js("document.getElementById('m-body').textContent") or "")[:200])
        chk("当前预设提示为 warn", js("!!document.querySelector('#m-body .fnote.warn')"))

        print("== 布局不裁切 ==")
        geo = js("""(() => {
          const m = document.querySelector('.modal'), b = document.getElementById('m-body'),
                f = document.getElementById('m-foot'), d = document.getElementById('e-diff');
          const r = f.getBoundingClientRect();
          return {vw: innerWidth, vh: innerHeight,
                  modalH: Math.round(m.getBoundingClientRect().height),
                  bodyScroll: b.scrollHeight, bodyClient: b.clientHeight,
                  footTop: Math.round(r.top), footBottom: Math.round(r.bottom),
                  diffH: Math.round(d.getBoundingClientRect().height)};
        })()""")
        RES["geo"] = geo
        chk("弹层在窗口内", geo["modalH"] <= geo["vh"], geo)
        chk("底部按钮可见（未溢出视口）", geo["footBottom"] <= geo["vh"] - 4, geo)
        chk("底部按钮未被压到顶", geo["footTop"] < geo["vh"], geo)
        chk("差异区已渲染出高度", geo["diffH"] > 16, geo)

        print("== 实时差异预览：初始无改动 ==")
        info0 = js("document.getElementById('e-diffinfo').textContent") or ""
        chk("提示无差异", "完全一致" in info0, info0)

        print("== 实时差异预览：改 URL ==")
        # 构造与原值**等长**的替换 URL：断言只考察「等长替换不改字节数」，
        # 不把 URL 长度差混进字节数校验。
        orig_url = js("document.getElementById('e-url').value") or ""
        probe_url = same_len_url(orig_url)
        chk("替换 URL 与原值等长", len(probe_url) == len(orig_url),
            "%r(%d) vs %r(%d)" % (probe_url, len(probe_url), orig_url, len(orig_url)))
        js("""(() => { const e = document.getElementById('e-url');
              e.value = %s;
              e.dispatchEvent(new Event('input')); return 1; })()""" % repr(probe_url))
        time.sleep(0.9)
        info1 = js("document.getElementById('e-diffinfo').textContent") or ""
        chk("只算一处改动", "改动 1 处" in info1, info1)
        chk("提示字节数", "字节" in info1, info1)
        b_before, b_after = parse_byte_pair(info1)
        chk("字节数可解析", b_before is not None, info1)
        if b_before is not None:
            chk("等长替换后字节数持平（差值 = 0）", b_after - b_before == 0, info1)
            # 基数必须来自当前真实内容，而不是写死的 255
            disk = (paths.lib / "example.toml").stat().st_size
            chk("字节数基数取自真实文件而非硬编码", abs(b_before - disk) <= 2,
                "info=%s disk=%d" % (info1, disk))
        rows = js("[...document.querySelectorAll('#e-diff .r')].map(x=>x.className+':'+x.textContent)")
        joined = "\n".join(rows or [])
        chk("差异里出现删除行", any(r.startswith("r del") for r in (rows or [])), joined)
        chk("差异里出现新增行", any(r.startswith("r add") for r in (rows or [])), joined)
        chk("新 URL 在差异中", probe_url in joined, joined)

        print("== 段名标签跟随输入 ==")
        js("""(() => { const e = document.getElementById('e-provider');
              e.value = 'kimi'; e.dispatchEvent(new Event('input')); return 1; })()""")
        time.sleep(0.5)
        chk("标签变为 kimi",
            js("document.getElementById('e-sectag').textContent") == "[model_providers.kimi]",
            js("document.getElementById('e-sectag').textContent"))
        info2 = js("document.getElementById('e-diffinfo').textContent") or ""
        chk("改 ID 时差异里新建段",
            any("model_providers.kimi" in r for r in
                (js("[...document.querySelectorAll('#e-diff .r')].map(x=>x.textContent)") or [])),
            info2)

        print("== 校验：非法 URL ==")
        js("""(() => { const e = document.getElementById('e-url');
              e.value = 'ftp://bad'; e.dispatchEvent(new Event('input')); return 1; })()""")
        time.sleep(0.7)
        chk("差异区显示校验失败",
            "需要修正" in (js("document.getElementById('e-diffinfo').textContent") or ""),
            js("document.getElementById('e-diffinfo').textContent"))
        chk("URL 框标红", js("document.getElementById('e-url').classList.contains('input-bad')") is True)
        js("document.querySelector('#m-foot button:last-child').click();")
        time.sleep(0.6)
        chk("非法时拒绝保存（错误框出现）",
            js("document.getElementById('e-err').classList.contains('on')") is True,
            js("document.getElementById('e-err').textContent"))
        chk("错误文案提到 Base URL",
            "Base URL" in (js("document.getElementById('e-err').textContent") or ""))

        print("== 恢复并改回正确值 ==")
        js("""(() => { const p = document.getElementById('e-provider'); p.value='example';
              p.dispatchEvent(new Event('input'));
              const e = document.getElementById('e-url'); e.value='https://sync.example/v2';
              e.dispatchEvent(new Event('input'));
              const m = document.getElementById('e-model'); m.value='gpt-5.9-probe';
              m.dispatchEvent(new Event('input')); return 1; })()""")
        time.sleep(0.9)
        chk("错误框已清空", js("document.getElementById('e-err').classList.contains('on')") is False)
        chk("标红已清除", js("!!document.querySelector('.input-bad')") is False)

        print("== 保存（走完整 run_edit 链路） ==")
        btns = js("[...document.querySelectorAll('#m-foot button')].map(b=>b.textContent)")
        chk("底部按钮为 取消/保存", btns == ["取消", "保存并启用…", "保存"], btns)
        js("document.querySelector('#m-foot button:last-child').click();")
        t0 = time.time()
        while time.time() - t0 < 12:
            if js("document.getElementById('backdrop').classList.contains('on')") is False:
                break
            time.sleep(0.2)
        chk("弹层已关闭", js("document.getElementById('backdrop').classList.contains('on')") is False)
        t0 = time.time()
        while time.time() - t0 < 15:
            if js("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1") == 1:
                break
            time.sleep(0.25)
        time.sleep(0.6)

        t = (paths.lib / "example.toml").read_text(encoding="utf-8")
        RES["saved"] = t
        chk("预设文件 URL 已改", 'https://sync.example/v2' in t, t[:300])
        chk("预设文件 model 已改", core.read_key(t, None, "model") == "gpt-5.9-probe")
        chk("宿主原有段未被破坏", core.read_key(t, "windows", "sandbox") == "unelevated")
        chk("现役已同步", paths.live.read_text(encoding="utf-8") == t)
        logtxt = js("document.getElementById('log').textContent") or ""
        LOG.append(logtxt)
        chk("日志出现 [4/4] 同步", "[4/4]" in logtxt, logtxt[-400:])
        chk("日志出现 [OK]", "[OK]" in logtxt)
        chk("状态区不再提示未回收变化",
            js("!!document.querySelector('#status .banner.warn')") is False)

        print("== 重新打开：编辑器应显示新值 ==")
        js("openEditor('example');")
        t0 = time.time()
        while time.time() - t0 < 8:
            if js("document.getElementById('e-url')") is not None:
                break
            time.sleep(0.2)
        time.sleep(0.3)
        chk("URL 回显为新值", js("document.getElementById('e-url').value") == "https://sync.example/v2",
            js("document.getElementById('e-url').value"))
        chk("model 回显为新值", js("document.getElementById('e-model').value") == "gpt-5.9-probe")
        chk("卡片已刷新 url",
            "sync.example" in (js("document.querySelector('.card').textContent") or ""),
            js("document.querySelector('.card').textContent"))
        # Escape 关闭
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        time.sleep(0.3)
        chk("Esc 可关闭弹层",
            js("document.getElementById('backdrop').classList.contains('on')") is False)

        print("== 官方预设（无 model / model_provider） ==")
        (paths.lib / "official.toml").write_text(
            'model_reasoning_effort = "medium"\n'
            '[model_providers.example]\n'
            'name = "Example Provider"\n'
            'base_url = "https://example.eu.org/v1"\n'
            'env_key = "EXAMPLE_API_KEY"\n'
            'wire_api = "responses"\n', encoding="utf-8")
        js("refresh(false);")
        time.sleep(1.2)
        chk("新预设已进入列表", "official" in (js("[...document.querySelectorAll('.card')].map(c=>c.dataset.name)") or []),
            js("[...document.querySelectorAll('.card')].map(c=>c.dataset.name)"))
        js("openEditor('official');")
        t0 = time.time()
        while time.time() - t0 < 8:
            if js("document.getElementById('backdrop').classList.contains('on')") is True:
                break
            time.sleep(0.2)
        time.sleep(1.0)
        chk("弹层打开", js("document.getElementById('backdrop').classList.contains('on')") is True)
        title2 = js("document.getElementById('m-title').textContent") or ""
        chk("标为未在使用", "未在使用" in title2, title2)
        chk("模型 ID 为空", js("document.getElementById('e-model').value") == "")
        chk("供应商 ID 为空", js("document.getElementById('e-provider').value") == "")
        chk("供应商块字段已置灰", js("document.getElementById('e-url').disabled") is True)
        chk("显示名称已置灰", js("document.getElementById('e-pname').disabled") is True)
        chk("接口协议已置灰", js("document.getElementById('e-wire').disabled") is True)
        chk("段头进入 off 态", js("document.querySelector('#m-body .fsec').classList.contains('off')") is True)
        chk("提示文案可见（不会被写入）",
            "不会被写入" in (js("document.querySelector('#m-body .fsec .offnote').textContent") or ""))
        chk("置灰仍能看到已有块内容",
            js("document.getElementById('e-url').value") == "https://example.eu.org/v1",
            js("document.getElementById('e-url').value"))
        chk("未在使用提示为普通态", js("!!document.querySelector('#m-body .fnote.warn')") is False)
        info3 = js("document.getElementById('e-diffinfo').textContent") or ""
        chk("开局无校验错误、无差异", "完全一致" in info3, info3)
        chk("错误框未出现", js("document.getElementById('e-err').classList.contains('on')") is False)

        print("== 填入供应商 ID 后应解禁 ==")
        js("""(() => { const e = document.getElementById('e-provider');
              e.value = 'example'; e.dispatchEvent(new Event('input')); return 1; })()""")
        time.sleep(0.9)
        chk("供应商块字段解禁", js("document.getElementById('e-url').disabled") is False)
        chk("段头 off 态已解除", js("document.querySelector('#m-body .fsec').classList.contains('off')") is False)
        info4 = js("document.getElementById('e-diffinfo').textContent") or ""
        chk("提示写回 model_provider（1 处）", "改动 1 处" in info4, info4)

        print("== 保存：官方预设启用 example ==")
        js("document.querySelector('#m-foot button:last-child').click();")
        t0 = time.time()
        while time.time() - t0 < 15:
            if js("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1") == 1:
                break
            time.sleep(0.25)
        time.sleep(0.7)
        off_txt = (paths.lib / "official.toml").read_text(encoding="utf-8")
        RES["official"] = off_txt
        chk("已写入 model_provider", core.read_key(off_txt, None, "model_provider") == "example",
            off_txt)
        chk("供应商块未被重复写入", off_txt.count("[model_providers.example]") == 1, off_txt)
        chk("改的是预设文件而非现役", paths.live.read_text(encoding="utf-8") != off_txt)
        chk("状态记录未变（official 非当前）", core.read_state(paths)[0] == "example",
            core.read_state(paths))
        chk("结果仍是合法 TOML", (lambda: (__import__("tomllib").loads(off_txt), True)[1])())
    except Exception as e:                                      # noqa: BLE001
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-900:])
    finally:
        if prev_api_key is None:
            os.environ.pop("EXAMPLE_API_KEY", None)
        else:
            os.environ["EXAMPLE_API_KEY"] = prev_api_key
        try:
            win.destroy()
        except Exception:                                       # noqa: BLE001
            pass


webview.start(worker)

print("\n== 几何量 ==")
print(" ", RES.get("geo"))
print("\n== 保存后文件 ==")
print(RES.get("saved", "")[:420])
shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
