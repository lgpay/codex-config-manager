# -*- coding: utf-8 -*-
"""IMP-001 产品化界面：无头 DOM 探针。

验证产品化改动（不改动核心层与配置保护逻辑）：
  * 顶部「当前配置」hero 正确渲染正在使用的预设（IMP-032 起为两行排版）；
  * 低频操作收纳进顶部「工具」菜单（IMP-021 起取代原 <details class="adv">；
    IMP-031 起工具菜单只留 同步预设 / 历史恢复 / 进程诊断 / 设置）；
  * 首次空态引导（.empty.onboard）出现；
  * 读取报错时给出友好提示；
  * 既有 selector 仍保留（.card / #b-switch.primary），保证旧探针不回归。

断言迁移说明（IMP-031 ~ IMP-036 文案统一后）：
  * 「配置」下拉被拆掉：新建提成顶栏直按钮 `#b-new`，编辑/另存/复制/删除进卡片右键菜单。
    因此不再断言 `b-edit` / `b-diff` / `b-dry` 这类已被有意删除的元素存在，
    改为断言它们**确实不在顶栏**、且对应能力**仍在右键菜单里可达**。
  * 全局术语「切换」→「启用」，所有相关文案断言同步更新。

全程在临时 CODEX_HOME 中运行，只读/写临时目录，不触碰真实配置。
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
        chk("hero 显示当前预设名", "example" in (js("document.getElementById('hero').textContent") or ""))
        # IMP-024：hero 变成纯信息区，不再挂常驻按钮；动作统一到列表标题行与菜单
        chk("hero 不再挂常驻按钮（b-edit-cur/b-switch-cur 已移除）",
            js("!document.getElementById('b-edit-cur') && !document.getElementById('b-switch-cur')"))
        # IMP-030/032：hero 收成两行 —— 第一行「当前配置：<名>」，第二行「模型 / 供应商 / 应用时间」。
        # 断言迁移（不是删除）：原来的「正在使用」角标取消了，改锁新的两行结构。
        _hero = js("document.getElementById('hero').textContent") or ""
        chk("hero 以「当前配置：」开头（IMP-032 两行排版）", "当前配置" in _hero, _hero)
        chk("hero 第二行含模型 / 供应商 / 应用时间",
            all(k in _hero for k in ["模型", "供应商", "应用时间"]), _hero)
        chk("hero 不再重复操作引导（引导统一在日志区）",
            "启用" not in _hero, _hero)
        chk("日志区含使用引导文案（已迁到这里）",
            "启用" in (js("document.getElementById('log').textContent") or ""),
            js("document.getElementById('log').textContent"))
        # 布局不裁切：hero 在视口内
        geo = js("""(() => { const h = document.getElementById('hero');
          const r = h.getBoundingClientRect();
          return {top: Math.round(r.top), bottom: Math.round(r.bottom), vh: innerHeight}; })()""")
        chk("hero 未被挤出视口", geo and geo["top"] >= 0 and geo["bottom"] <= geo["vh"] + 1, geo)

        print("== IMP-021/031：低频/诊断收纳进顶部「工具」菜单 ==")
        chk("工具菜单面板存在", js("!!document.querySelector('#menubar .mpanel')"))
        # IMP-031/037：工具菜单精简为三项，且都在面板里（不再散落在常驻区）
        chk("低频项都在工具菜单里",
            all(js("!!document.querySelector('#menubar .mpanel #%s')" % i)
                for i in ["b-harvest", "b-history", "b-guard"]))
        chk("工具菜单含 同步预设", js("!!document.getElementById('b-harvest')"))
        chk("工具菜单含 进程诊断", js("!!document.getElementById('b-guard')"))
        chk("工具菜单含 历史恢复", js("!!document.getElementById('b-history')"))
        # IMP-037：设置从工具菜单里提出来，成为顶栏直按钮（无需下拉，直接进入设置）
        chk("设置已提出工具菜单，改作顶栏直按钮",
            js("!!document.getElementById('b-paths')")
            and js("document.getElementById('b-paths').classList.contains('mact')")
            and not js("!!document.querySelector('#menubar .mpanel #b-paths')"))
        # IMP-031：查看差异 / 演练已从顶栏移除 —— 查看差异收进右键菜单，演练直接删掉不留入口。
        # 断言迁移：改为锁「顶栏确实没有它们」+「差异能力仍在右键菜单可达」。
        chk("顶栏不再有 查看差异（收进右键菜单）",
            not js("!!document.getElementById('b-diff')"))
        chk("顶栏不再有 演练（IMP-031 直接删除不留入口）",
            not js("!!document.getElementById('b-dry')"))
        chk("差异能力仍在卡片右键菜单可达",
            js("""(function(){
                  SELECTED='example'; renderPresets();
                  openCtx('example', 10, 10);
                  var t=document.getElementById('ctxmenu').textContent||'';
                  closeCtx();
                  return t.indexOf('对比') >= 0;
                })()"""))
        # 工具菜单项无「选中依赖」的禁用态：这四项都随时可用（同步预设有自己的前置条件）
        chk("工具菜单项默认可用（进程诊断 / 历史恢复）",
            all(js("document.getElementById('%s').disabled" % i) is False
                for i in ["b-guard", "b-history"]))
        chk("顶栏直按钮「设置」默认可用",
            js("document.getElementById('b-paths').disabled") is False)

        print("== 既有 selector 保留（旧探针不回归） ==")
        chk("保留 .card", js("!!document.querySelector('.card')"))
        chk("保留 #b-switch.primary（启用配置主按钮）",
            js("!!document.querySelector('#b-switch.primary')"))
        chk("保留 #b-new 直按钮", js("!!document.getElementById('b-new')"))

        print("== 卡片右键菜单「编辑」真的能打开编辑器 ==")
        # 断言迁移：原来走顶栏 b-edit，现在走右键菜单的「编辑」（同一份 openEditor）。
        js("SELECTED='example'; renderPresets(); renderButtons();"
           " openCtx('example', 10, 10);")
        js("""(function(){
          var bs=document.querySelectorAll('#ctxmenu button[data-i]');
          for (var b of bs){ if ((b.textContent||'').trim()==='编辑'){ b.click(); return 1; } }
          return 0;
        })()""")
        chk("编辑器弹层打开", wait_modal(True))
        time.sleep(0.8)
        chk("编辑器标题含预设名", "example" in (js("document.getElementById('m-title').textContent") or ""))
        chk("编辑器字段名已中文化（模型 / 供应商）",
            all(k in (js("document.getElementById('backdrop').textContent") or "")
                for k in ["模型", "供应商"]))
        chk("编辑器按钮为「检查配置」/「测试模型」",
            "检查配置" in (js("document.getElementById('backdrop').textContent") or "")
            and "测试模型" in (js("document.getElementById('backdrop').textContent") or ""))
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        time.sleep(0.3)
        chk("Esc 关闭弹层", js("document.getElementById('backdrop').classList.contains('on')") is False)

        print("== 边栏「启用配置」接通启用流程 ==")
        js("document.getElementById('b-switch').click();")
        chk("启用确认弹层打开", wait_modal(True))
        t = js("document.getElementById('m-title').textContent") or ""
        chk("弹层为「确认启用」", "确认启用" in t, t)
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
        _empty = js("document.querySelector('.empty.onboard').textContent") or ""
        chk("空态含「还没有预设」开场", "还没有预设" in _empty, _empty)
        chk("空态引导指向顶栏「新建」", "「新建」" in _empty, _empty)
        chk("空态引导指向卡片右键", "右键" in _empty, _empty)
        chk("空态引导指向边栏「启用配置」", "启用配置" in _empty, _empty)
        chk("空态下 hero 显示「当前配置：未记录」",
            "未记录" in (js("document.getElementById('hero').textContent") or ""))

        print("== IMP-001：友好错误（读取失败提示） ==")
        # renderStatus/renderHero 读取 STATE.error；用真实异常触发 get_state 的 error 分支
        _orig_snapshot = core.snapshot
        def _boom(p):  # noqa: ANN001
            raise RuntimeError("模拟配置目录不可读")
        core.snapshot = _boom
        js("refresh(false);")
        time.sleep(1.0)
        htxt = js("document.getElementById('hero').textContent") or ""
        # IMP-034：错误文案统一为「读取配置：<原因> 时出错。请检查配置目录权限后重新打开。」
        chk("hero 报出读取失败", "读取失败" in htxt, htxt)
        chk("hero 给出排查指引", "权限" in htxt, htxt)
        core.snapshot = _orig_snapshot
        api.p.lib = paths.lib
        js("refresh(false);")
        time.sleep(0.8)

        print("== 布局不裁切：主区域 / 右侧边栏未被挤出视口 ==")
        geo2 = js("""(() => {
          const s = document.querySelector('.status'), b = document.querySelector('.body');
          const sb = document.querySelector('#sidebar');
          const rb = b.getBoundingClientRect(), rs = s.getBoundingClientRect();
          const rsb = sb.getBoundingClientRect();
          return {bh: Math.round(rb.height), sv: Math.round(rs.bottom), vh: innerHeight,
                  sbw: Math.round(rsb.width), sbb: Math.round(rsb.bottom)}; })()""")
        chk("主区有高度且状态条底部在视口内",
            geo2 and isinstance(geo2, dict) and geo2.get("bh", 0) > 0 and geo2["sv"] <= geo2["vh"] + 1,
            geo2)
        chk("右侧边栏宽度合理且底部在视口内",
            isinstance(geo2, dict) and 0 < geo2.get("sbw", 0) < 260 and geo2.get("sbb", 10 ** 6) <= geo2["vh"] + 1,
            geo2)
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
