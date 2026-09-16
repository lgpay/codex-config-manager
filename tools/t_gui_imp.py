# -*- coding: utf-8 -*-
"""IMP-001 产品化界面：无头 DOM 探针。

验证本轮产品化改动（不改动核心层与配置保护逻辑）：
  * 顶部「当前配置」hero 正确渲染正在使用的预设与快捷操作；
  * 低频操作收纳进「高级操作」<details>，且 b-diff/b-guard/b-dry 仍可用；
  * 首次空态引导（.empty.onboard）出现；
  * 读取报错时给出友好提示（hero 显示「配置状态读取失败」）；
  * 既有测试 selector 仍保留（.card / .primary / b-edit），保证旧探针不回归。

全程在临时 CODEX_HOME 中运行，只读/写临时目录，不触碰真实配置。
"""
import os
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

root = tempfile.mkdtemp(prefix="codegui_imp_")
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


def js(code, default=None):
    try:
        return win.evaluate_js(code)
    except Exception as e:  # noqa: BLE001
        return f"<js error: {e}>"


def wait_ready(timeout=12):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0") == 1:
            return True
        time.sleep(0.2)
    return False


def wait_modal(open_, timeout=8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js("document.getElementById('backdrop').classList.contains('on')") is open_:
            return True
        time.sleep(0.2)
    return False


def worker():
    try:
        chk("界面就绪（STATE 已加载）", wait_ready(), "STATE 未就绪")
        time.sleep(0.5)

        print("== IMP-001：顶部「当前配置」hero ==")
        chk("hero 节点存在", js("!!document.getElementById('hero')"))
        chk("hero 显示正在使用", "正在使用" in (js("document.getElementById('hero').textContent") or ""))
        chk("hero 显示当前预设名", "example" in (js("document.getElementById('hero').textContent") or ""))
        chk("hero 有「编辑当前预设」按钮", js("!!document.getElementById('b-edit-cur')"))
        chk("hero 有「切换到所选预设」按钮", js("!!document.getElementById('b-switch-cur')"))
        chk("hero 含使用引导文案", "切换到此预设" in (js("document.getElementById('hero').textContent") or ""))
        # 布局不裁切：hero 在视口内
        geo = js("""(() => { const h = document.getElementById('hero');
          const r = h.getBoundingClientRect();
          return {top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight}; })()""")
        chk("hero 未被挤出视口", geo and geo["top"] >= 0 and geo["bottom"] <= geo["vh"] + 1, geo)

        print("== IMP-001：高级操作收纳（保持 selector 与安全机制） ==")
        chk("高级操作 details 存在", js("!!document.querySelector('#actions details.adv')"))
        chk("高级操作含 查看差异", js("!!document.getElementById('b-diff')"))
        chk("高级操作含 诊断宿主进程", js("!!document.getElementById('b-guard')"))
        chk("高级操作含 演练", js("!!document.getElementById('b-dry')"))
        # 这些按钮仍在原 ID，renderButtons 仍会按「是否选中」管理禁用态
        chk("有选中时 查看差异 可用", js("document.getElementById('b-diff').disabled") is False)
        chk("有选中时 演练 可用", js("document.getElementById('b-dry').disabled") is False)
        # 取消选中后应被禁用（验证 selector 安全机制仍生效）
        js("SELECTED=null; renderButtons();")
        time.sleep(0.2)
        chk("取消选中后 查看差异 禁用", js("document.getElementById('b-diff').disabled") is True)
        chk("取消选中后 演练 禁用", js("document.getElementById('b-dry').disabled") is True)
        js("SELECTED='example'; renderButtons();")
        time.sleep(0.2)

        print("== 既有 selector 保留（旧探针不回归） ==")
        chk("保留 .card", js("!!document.querySelector('.card')"))
        chk("保留 .primary（切换到）", js("!!document.querySelector('#b-switch.primary')"))
        chk("保留 b-edit", js("!!document.getElementById('b-edit')"))

        print("== hero 的「编辑当前预设」真的能打开编辑器 ==")
        js("document.getElementById('b-edit-cur').click();")
        chk("编辑器弹层打开", wait_modal(True))
        time.sleep(0.8)
        chk("编辑器标题含预设名", "example" in (js("document.getElementById('m-title').textContent") or ""))
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        time.sleep(0.3)
        chk("Esc 关闭弹层", js("document.getElementById('backdrop').classList.contains('on')") is False)

        print("== hero 的「切换到所选预设」接通切换流程 ==")
        js("document.getElementById('b-switch-cur').click();")
        chk("切换确认弹层打开", wait_modal(True))
        t = js("document.getElementById('m-title').textContent") or ""
        chk("弹层为「确认切换」", "确认切换" in t, t)
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        time.sleep(0.3)

        print("== IMP-001：首次空态引导（预设库为空） ==")
        for f in paths.lib.glob("*.toml"):
            f.unlink()
        paths.state.unlink(missing_ok=True)
        js("refresh(false);")
        time.sleep(1.0)
        chk("出现空态引导 .empty.onboard",
            js("!!document.querySelector('.empty.onboard')"))
        chk("空态含步骤列表", js("!!document.querySelector('.empty.onboard ol.steps')"))
        chk("空态含欢迎文案", "欢迎使用" in (js("document.querySelector('.empty.onboard').textContent") or ""))
        chk("空态含「另存为新预设」按钮", js("!!document.getElementById('b-save-empty')"))
        chk("空态下 hero 显示「尚未记录当前预设」",
            "尚未记录" in (js("document.getElementById('hero').textContent") or ""))

        print("== IMP-001：友好错误（读取失败提示） ==")
        # renderStatus/renderHero 读取 STATE.error；用真实异常触发 get_state 的 error 分支
        _orig_snapshot = core.snapshot
        def _boom(p):  # noqa: ANN001
            raise RuntimeError("模拟配置目录不可读")
        core.snapshot = _boom
        js("refresh(false);")
        time.sleep(1.0)
        htxt = js("document.getElementById('hero').textContent") or ""
        chk("hero 显示「配置状态读取失败」", "配置状态读取失败" in htxt, htxt)
        core.snapshot = _orig_snapshot
        api.p.lib = paths.lib
        js("refresh(false);")
        time.sleep(0.8)

        print("== 布局不裁切：主区域未被挤出视口 ==")
        geo2 = js("""(() => {
          const a = document.querySelector('#actions'), b = document.querySelector('.body');
          const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
          return {av: Math.round(ra.bottom), bv: Math.round(rb.bottom), vh: innerHeight}; })()""")
        chk("操作区底部在视口内", geo2 and geo2["av"] <= geo2["vh"] + 1, geo2)
        LOG.append(geo2)
    except Exception as e:  # noqa: BLE001
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-900:])
    finally:
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass


webview.start(worker)

print("\n== 几何量 ==")
print(" ", LOG[-1] if LOG else None)
shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
