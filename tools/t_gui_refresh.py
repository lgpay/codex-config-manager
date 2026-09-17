# -*- coding: utf-8 -*-
"""UI 刷新（2026-09-15）无头 GUI 探针；IMP-024 迁移到新界面结构。

验证「简洁界面」重构不破坏功能、选择器与安全逻辑：
  * 首页只含「当前配置(hero) / 配置列表(plist)」，常驻动作只剩「切换」与「启动 ChatGPT」；
  * 大段说明收纳进「使用帮助」(b-help，按需打开)，低频/诊断收进顶部「工具」菜单
    （IMP-021 起取代原 `details.adv`；本探针同步迁移到菜单内定位）；
  * 全部原功能可达：b-diff / b-guard / b-recovery / b-new(向导) / b-edit / b-switch 均可用；
  * 连接安全文案（TLS / 不跟随跳转 / 超时 / 费用）在向导连接确认弹层仍显式列出；
  * 覆盖配置确认（保存并启用）文案不变。

全程在临时 CODEX_HOME 中运行；用测试本地中性 .guard 隔离本机正在运行的宿主，
不触碰真实配置、不联网、不弱化任何安全断言。
"""

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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
        # IMP-032：hero 改两行排版，第一行「当前配置：<名>」，原来的「正在使用」角标取消。
        _hero = js("document.getElementById('hero').textContent") or ""
        chk("hero 以「当前配置：」报出正在用的预设", "当前配置" in _hero, _hero)
        chk("plist（配置列表）渲染卡片", js("!!document.querySelector('.card')"))
        # IMP-021~025/033：常驻动作只剩两个按钮，且都进预设右侧的操作边栏
        chk("启用按钮在右侧边栏内", js("!!document.querySelector('#sidebar #b-switch')"))
        chk("启动按钮也在同一个边栏内", js("!!document.querySelector('#sidebar #b-chatgpt')"))
        chk("主区只有这两个按钮", js("document.querySelectorAll('.body button').length") == 2)
        chk("原右侧「操作」栏已移除", js("!document.getElementById('actions')"))

        print("== 功能分布：顶栏直按钮 + 两个下拉 + 右键菜单（IMP-031/037）==")
        chk("菜单栏存在且只剩 2 个下拉（工具 / 帮助）",
            js("document.querySelectorAll('#menubar .mgroup').length") == 2,
            js("document.querySelectorAll('#menubar .mgroup').length"))
        # IMP-037：直按钮从 1 个（新建）增到 2 个（新建 / 设置）。
        chk("「新建」「设置」都是顶栏直按钮（都不在下拉里）",
            js("[...document.querySelectorAll('#menubar .mact')].map(x=>x.textContent.trim())")
            == ["新建", "设置"]
            and not js("!!document.querySelector('.mpanel .mact')"),
            js("[...document.querySelectorAll('#menubar .mact')].map(x=>x.textContent.trim())"))
        # IMP-031：原「配置」下拉里的单条动作全部收进卡片右键菜单。
        # 断言迁移（不是删除）：这里锁「它们确实不在顶栏」，能力由右键菜单断言兜住。
        # IMP-037：设置已从工具菜单提出，故不在 in_menu 里。
        in_menu = {
            "b-harvest": "工具", "b-history": "工具", "b-guard": "工具",
            "b-help": "帮助", "b-recovery": "帮助", "b-about": "帮助",
        }
        for bid, menu in in_menu.items():
            chk(f"{bid} 在「{menu}」菜单内",
                js("""(() => { const t=[...document.querySelectorAll('#menubar .mtitle')]
                          .find(x=>x.textContent.trim()===%r);
                        if(!t) return false;
                        return !!t.parentElement.querySelector('.mpanel #%s'); })()""" % (menu, bid)))
        for gone in ["b-edit", "b-save", "b-copy", "b-delete", "b-diff", "b-dry", "m-config"]:
            chk(f"顶栏已移除 #{gone}（改由右键菜单承担）",
                not js("!!document.getElementById('%s')" % gone))
        chk("原 details.adv 折叠已移除", js("!document.querySelector('details.adv')"))
        chk("顶栏不再有 h1 标题与 logo",
            js("!document.querySelector('.topbar h1')") and js("!document.querySelector('.topbar .logo')"))

        print("== 状态条紧凑（运行状态改为按钮提示，不再常驻 pill）==")
        chk("状态条存在且有内容", (js("document.getElementById('status').children.length") or 0) > 0)
        chk("状态条已无运行状态 pill", js("document.querySelectorAll('#status .pill').length") == 0)

        print("== 使用帮助（按需打开，收纳原内联说明 + 安全信息）==")
        js("document.getElementById('b-help').click();")
        chk("帮助弹层打开", wait_modal(True))
        time.sleep(0.4)
        hb = js("document.getElementById('m-body').textContent") or ""
        chk("帮助标题为「使用帮助」",
            "使用帮助" in (js("document.getElementById('m-title').textContent") or ""))
        chk("帮助含 启用/编辑/新建 说明", all(k in hb for k in ("启用", "编辑", "新建")))
        chk("帮助含 自动备份 安全提示", "自动备份" in hb, hb[:60])
        chk("帮助含 不跟随跳转 安全说明", "不跟随跳转" in hb, hb[:60])
        chk("帮助含 超时 安全说明", "超时" in hb, hb[:60])
        chk("帮助含 费用 安全说明", "费用" in hb, hb[:60])
        chk("帮助含 不会替你登录 说明", "不会替你登录" in hb, hb[:60])
        close_modal()
        time.sleep(0.4)

        print("== 全部原功能可达 ==")
        # 查看差异（IMP-031 起从顶栏移到卡片右键菜单）
        js("SELECTED='example'; renderPresets(); openCtx('example', 10, 10);")
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='对比').click();""")
        chk("对比弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("对比弹层标题含「差异」", "差异" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)
        # 诊断宿主进程
        js("document.getElementById('b-guard').click();")
        chk("进程诊断弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("诊断标题为「进程诊断」", "进程诊断" in (js("document.getElementById('m-title').textContent") or ""))
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
        # 编辑（IMP-031 起从顶栏移到卡片右键菜单）
        js("SELECTED='example'; renderPresets(); openCtx('example', 10, 10);")
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='编辑').click();""")
        chk("编辑弹层打开", wait_modal(True))
        time.sleep(0.8)
        chk("编辑器标题含预设名", "example" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.5)

        print("== 边栏「启用配置」接通启用确认（中性守卫下可用）==")
        js("document.getElementById('b-switch').click();")
        chk("启用确认弹层打开", wait_modal(True))
        time.sleep(0.3)
        chk("弹层为「确认启用」", "确认启用" in (js("document.getElementById('m-title').textContent") or ""))
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

        print("== 布局不裁切：主区域 / 右侧边栏都在视口内 ==")
        geo = js("""(() => {
          const s = document.querySelector('.status'), b = document.querySelector('.body');
          const sb = document.querySelector('#sidebar');
          const rb = b.getBoundingClientRect(), rs = s.getBoundingClientRect();
          const rsb = sb.getBoundingClientRect();
          return {bh: Math.round(rb.height), sv: Math.round(rs.bottom), vh: innerHeight,
                  sbh: Math.round(rsb.height), sbb: Math.round(rsb.bottom)}; })()""")
        chk("主区有高度且状态条底部在视口内",
            geo and geo["bh"] > 0 and geo["sv"] <= geo["vh"] + 1, geo)
        chk("右侧边栏有高度且底部在视口内",
            geo and geo["sbh"] > 0 and geo["sbb"] <= geo["vh"] + 1, geo)
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
