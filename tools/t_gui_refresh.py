# -*- coding: utf-8 -*-
"""UI 刷新（2026-09-15）无头 GUI 探针。

验证「简洁界面」重构不破坏功能、选择器与安全逻辑：
  * 首页只含「当前配置(hero) / 配置列表(plist) / 主要操作(新建·编辑·启用…)」；
  * 大段说明收纳进「使用帮助」(b-help，按需打开)，低频/诊断收进「更多操作」(details.adv)；
  * 全部原功能可达：b-diff / b-guard / b-recovery / b-new(向导) / b-edit / b-switch 均可用；
  * 连接安全文案（TLS / 不跟随跳转 / 超时 / 费用）在向导连接确认弹层仍显式列出；
  * 覆盖配置确认（保存并启用）文案不变。

全程在临时 CODEX_HOME 中运行；用测试本地中性 .guard 隔离本机正在运行的宿主，
不触碰真实配置、不联网、不弱化任何安全断言。
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

root = tempfile.mkdtemp(prefix="codegui_refresh_")
os.environ["CODEX_HOME"] = root
# 让本地检查通过（不真正联网）：env_key 名必须存在于环境
os.environ["P_KEY"] = "synthetic-probe-key-not-real"
paths = core.Paths(root)
core.ensure_layout(paths)
# 测试隔离：中性守卫名单，避免被本机正在运行的宿主拦截（不改动真实 DEFAULT_GUARD）。
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


def close_modal():
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
    time.sleep(0.4)


def worker():
    try:
        chk("界面就绪（STATE 已加载）", wait_ready(), "STATE 未就绪")
        time.sleep(0.5)

        print("== 首页结构：当前配置 / 配置列表 / 主要操作 ==")
        chk("hero（当前配置）节点存在", js("!!document.getElementById('hero')"))
        chk("hero 显示「正在使用」", "正在使用" in (js("document.getElementById('hero').textContent") or ""))
        chk("plist（配置列表）渲染卡片", js("!!document.querySelector('.card')"))
        chk("主要操作：切换到（b-switch）", js("!!document.getElementById('b-switch')"))
        chk("主要操作：新建（b-new）", js("!!document.getElementById('b-new')"))
        chk("主要操作：编辑（b-edit）", js("!!document.getElementById('b-edit')"))
        chk("主要操作：另存（b-save）", js("!!document.getElementById('b-save')"))
        chk("主要操作：只同步（b-harvest）", js("!!document.getElementById('b-harvest')"))
        # 主要操作直接可见（不在 details.adv 内）
        chk("b-new 不在「更多操作」折叠内",
            js("!document.getElementById('b-new').closest('details.adv')"))
        chk("b-edit 不在「更多操作」折叠内",
            js("!document.getElementById('b-edit').closest('details.adv')"))

        print("== 低频/诊断收纳进「更多操作」==")
        chk("「更多操作」details.adv 存在", js("!!document.querySelector('#actions details.adv')"))
        chk("次级含 查看差异", js("!!document.getElementById('b-diff')"))
        chk("次级含 诊断宿主进程", js("!!document.getElementById('b-guard')"))
        chk("次级含 演练", js("!!document.getElementById('b-dry')"))
        chk("次级含 如何恢复", js("!!document.getElementById('b-recovery')"))
        # 这些按钮在 details.adv 内
        chk("b-diff 在「更多操作」折叠内",
            js("!!document.getElementById('b-diff').closest('details.adv')"))

        print("== 状态条紧凑（无大段说明常驻）==")
        chk("状态条存在且有内容", (js("document.getElementById('status').children.length") or 0) > 0)
        chk("状态条含守卫 pill", js("!!document.querySelector('#status .pill')"))

        print("== 使用帮助（按需打开，收纳原内联说明 + 安全信息）==")
        js("document.getElementById('b-help').click();")
        chk("帮助弹层打开", wait_modal(True))
        time.sleep(0.4)
        hb = js("document.getElementById('m-body').textContent") or ""
        chk("帮助标题为「使用帮助」",
            "使用帮助" in (js("document.getElementById('m-title').textContent") or ""))
        chk("帮助含 切换/编辑/新建 说明", all(k in hb for k in ("切换", "编辑", "新建")))
        chk("帮助含 自动备份 安全提示", "自动备份" in hb, hb[:60])
        chk("帮助含 不跟随跳转 安全说明", "不跟随跳转" in hb, hb[:60])
        chk("帮助含 超时 安全说明", "超时" in hb, hb[:60])
        chk("帮助含 费用 安全说明", "费用" in hb, hb[:60])
        chk("帮助含 不会替你登录 说明", "不会替你登录" in hb, hb[:60])
        close_modal()
        time.sleep(0.4)

        print("== 全部原功能可达 ==")
        # 查看差异
        js("document.getElementById('b-diff').click();")
        chk("查看差异弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("差异弹层标题含「差异」", "差异" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)
        # 诊断宿主进程
        js("document.getElementById('b-guard').click();")
        chk("诊断宿主进程弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("诊断标题为简洁的「运行状态」", "运行状态" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)
        # 如何恢复
        js("document.getElementById('b-recovery').click();")
        chk("恢复弹层打开", wait_modal(True))
        time.sleep(0.3)
        rb = js("document.getElementById('m-body').textContent") or ""
        chk("恢复步骤含 复制（不要移动）", "复制" in rb, rb[:60])
        chk("恢复步骤含 recovery.toml", "recovery.toml" in rb, rb[:60])
        close_modal()
        time.sleep(0.4)
        # 编辑
        js("document.getElementById('b-edit').click();")
        chk("编辑弹层打开", wait_modal(True))
        time.sleep(0.8)
        chk("编辑器标题含预设名", "example" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.5)

        print("== 切换到所选预设 接通切换确认（中性守卫下启用）==")
        js("document.getElementById('b-switch-cur').click();")
        chk("切换确认弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("弹层为「确认切换」", "确认切换" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.5)

        print("== 新建向导：第三方连接确认仍显式列出安全项 ==")
        js("document.getElementById('b-new').click();")
        chk("向导弹层打开", wait_modal(True))
        time.sleep(0.4)
        js("""(() => { const s=document.getElementById('w-kind');
              s.value='third_party'; s.dispatchEvent(new Event('change'));
              document.getElementById('w-new_name').value='wiz_tp';
              document.getElementById('w-model').value='m';
              document.getElementById('w-model_provider').value='p';
              document.getElementById('w-base_url').value='https://p.example/v1';
              document.getElementById('w-env_key').value='P_KEY'; document.getElementById('w-env_key').dispatchEvent(new Event('input'));
              document.getElementById('w-wire_api').value='responses'; return 1; })()""")
        time.sleep(0.6)
        js("document.getElementById('w-connect').click();")
        chk("连接确认弹层打开", wait_modal(True))
        time.sleep(0.4)
        cbody = js("document.getElementById('m-body').textContent") or ""
        chk("连接确认含 TLS 校验", "TLS" in cbody, cbody[:80])
        chk("连接确认含 不跟随跳转", "不跟随" in cbody, cbody[:80])
        chk("连接确认含 超时", "超时" in cbody, cbody[:80])
        chk("连接确认含 费用提醒", "费用" in cbody, cbody[:80])
        close_modal()
        time.sleep(0.5)

        print("== 覆盖配置确认（保存并启用）文案保留 ==")
        js("openEditor('example');")
        chk("编辑器打开（覆盖配置）", wait_modal(True))
        time.sleep(0.8)
        js("document.querySelectorAll('#m-foot button')[1].click();")  # 保存并启用…
        chk("保存并启用弹确认框", wait_modal(True))
        time.sleep(0.3)
        chk("确认框为「确认保存并启用」",
            "确认保存并启用" in (js("document.getElementById('m-title').textContent") or ""))
        c2 = js("document.getElementById('m-body').textContent") or ""
        chk("确认框含 恢复方法", "恢复方法" in c2 or "历史" in c2, c2[:60])
        close_modal()
        time.sleep(0.5)

        print("== 布局不裁切：主区域在视口内 ==")
        geo = js("""(() => {
          const a = document.querySelector('#actions'), b = document.querySelector('.body');
          const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
          return {av: Math.round(ra.bottom), bv: Math.round(rb.bottom), vh: innerHeight}; })()""")
        chk("操作区底部在视口内", geo and geo["av"] <= geo["vh"] + 1, geo)
    except Exception as e:  # noqa: BLE001
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-900:])
    finally:
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass


webview.start(worker)

shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
