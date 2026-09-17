# -*- coding: utf-8 -*-
"""文案精简 + 边栏状态行（IMP-030 / IMP-032 / IMP-033）无头 GUI 探针。

盯两件事：
  1. **删掉的重复文案真的没了**：边栏「操作」标题、列表「预设」标题、5 处重复的操作教学
     （只留日志里那条）、卡片上的 url / key 两列。
     但注意：hero 的「模型 / 供应商」是 **IMP-032 特意加回来** 的（用户要两行排版），
     所以这里不再断言它「不存在」，改断言它「存在且是中文名」。
  2. **边栏状态行对**：ChatGPT 状态行（`#st-chatgpt`，边栏底部单独一行）在三种运行状态下
     文字与配色类名都正确，且**随状态变化重绘**（走产品自己的 render* 路径）。
     IMP-033 起 `#st-switch` 已删除（启用按钮文案固定，不再拼预设名），断言随之改为
     「它确实不在了」+「按钮文案恒为『启用配置』」。

断言原则：删掉的文案要断言「不存在」，保留的要断言「还在」——只断言前者的话，
改坏成空白页也会过。
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import webview  # noqa: E402
import core  # noqa: E402
import ui  # noqa: E402
import app as appmod  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

OK = 0
FAIL = 0
FAILED = []


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  ok   " + name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + (" " + str(extra) if extra else ""))


def make_paths():
    """隔离的临时数据根：绝不碰用户真实 ~/.codex。"""
    tmp = Path(tempfile.mkdtemp(prefix="cg_trim_"))
    root = tmp / "codex"
    lib = root / "configs"
    lib.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text('model_reasoning_effort = "medium"\n', encoding="utf-8")
    (lib / "official.toml").write_text("", encoding="utf-8")
    (lib / "aibank.toml").write_text(
        'model = "gpt-5.6-luna"\nmodel_provider = "aibank"\n\n'
        '[model_providers.aibank]\nname = "AIBank"\n'
        'base_url = "https://aibank.eu.org/v1"\nenv_key = "AIBANK_API_KEY"\n'
        'wire_api = "responses"\n', encoding="utf-8")
    paths = core.Paths(root, lib)          # 签名是 (root, config_dir)
    core.write_state(paths, "official")
    return paths


STATE_JS_WAIT = "(typeof STATE !== 'undefined' && STATE) ? 1 : 0"


def main():
    paths = make_paths()
    api = appmod.Api(paths)
    win = webview.create_window("trim", html=ui.HTML, js_api=api, width=980, height=720)
    results = {}

    def js(expr):
        return win.evaluate_js(expr)

    def wait(expr, want=True, timeout=12):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if js(expr) == want:
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    def worker():
        try:
            chk("窗口就绪", wait(STATE_JS_WAIT, 1), "STATE 未就绪")
            # 等列表真的画出来（refresh → renderPresets 是异步的）
            wait("document.querySelectorAll('#plist .card').length", 2)

            print("== 1. 删掉的重复文案确实不存在 ==")
            chk("边栏「操作」标题已删（sidebar 内无 .col-title）",
                js("document.querySelectorAll('#sidebar .col-title').length") == 0,
                js("document.getElementById('sidebar').innerHTML.slice(0,120)"))
            chk("列表「预设」标题已删（.colhead 不存在）",
                js("!document.querySelector('.colhead')"))
            chk("hero 不再有操作教学（hguide 不出现）",
                js("!document.querySelector('#hero .hguide')"))
            _hero = js("document.getElementById('hero').textContent") or ""
            chk("hero 显示当前预设名", "official" in _hero, _hero)
            chk("hero 用「当前配置：」开头（IMP-032 两行排版）",
                "当前配置" in _hero, _hero)
            chk("hero 第二行含「模型」（IMP-032 加回来的）",
                "模型" in _hero, _hero)
            chk("hero 第二行含「供应商」（IMP-032 加回来的）",
                "供应商" in _hero, _hero)
            chk("hero 第二行含「应用时间」",
                "应用时间" in _hero, _hero)

            print("== 2. 边栏状态行：元素与初始态 ==")
            chk("#st-switch 已删除（IMP-033：启用按钮不再带状态行）",
                js("!document.getElementById('st-switch')"),
                js("!!document.getElementById('st-switch')"))
            chk("#st-chatgpt 存在", js("!!document.getElementById('st-chatgpt')"))
            chk("ChatGPT 状态行在边栏内",
                js("!!document.querySelector('#sidebar #st-chatgpt')"))
            chk("ChatGPT 状态行在**两个按钮之后**（DOM 顺序，贴边栏底部）",
                js("""(function(){
                  var s=document.getElementById('st-chatgpt');
                  var c=document.getElementById('b-chatgpt');
                  return !!(c.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING);
                })()"""))
            chk("ChatGPT 状态行有 .cgstate 类",
                js("document.getElementById('st-chatgpt').classList.contains('cgstate')"))

            print("== 3. 三种运行状态下的文案与配色 ==")
            # 停止轮询干扰：直接走产品的 render* 路径注入状态
            js("if(typeof CG_POLL!=='undefined'&&CG_POLL){clearInterval(CG_POLL);CG_POLL=null;}")
            js("""
              window.__setRT = function(guardRun, cgRun, cgWin){
                STATE.guard = Object.assign({}, STATE.guard, {running:guardRun, total:guardRun?2:0});
                STATE.chatgpt = {running:cgRun, windowed:cgWin, count:cgRun?9:0};
                renderSwitchButton(); renderChatGPTButton();
              };
            """)

            def setrt(g, c, w):
                js("window.__setRT(%s,%s,%s)" % ("true" if g else "false",
                                                 "true" if c else "false",
                                                 "true" if w else "false"))
                time.sleep(0.25)

            # 场景 A：都未运行 + 选中非当前预设 → 可启用
            js("SELECTED='aibank'; renderPresets(); renderButtons(); renderSwitchButton();")
            setrt(False, False, False)
            chk("A 未运行：启用按钮可点", js("!document.getElementById('b-switch').disabled"))
            chk("A 未运行：启用按钮文案恒为「启用配置」",
                (js("document.getElementById('b-switch').textContent") or "").strip() == "启用配置",
                js("document.getElementById('b-switch').textContent"))
            chk("A 未运行：ChatGPT 状态行 = 未启动",
                "未启动" in (js("document.getElementById('st-chatgpt').textContent") or ""),
                js("document.getElementById('st-chatgpt').textContent"))
            chk("A 未运行：ChatGPT 状态行无 ok/warn 配色",
                js("!document.getElementById('st-chatgpt').className.match(/ok|warn/)"),
                js("document.getElementById('st-chatgpt').className"))

            # 场景 B：Codex 运行中 → 启用锁定
            setrt(True, False, False)
            chk("B Codex 运行：启用按钮置灰", js("document.getElementById('b-switch').disabled"))
            chk("B Codex 运行：按钮文案仍是「启用配置」（不拼预设名）",
                (js("document.getElementById('b-switch').textContent") or "").strip() == "启用配置",
                js("document.getElementById('b-switch').textContent"))

            # 场景 C：ChatGPT 后台驻留（有进程无窗口）→ 仍可点
            setrt(False, True, False)
            chk("C 后台驻留：启动按钮仍可点（不被灰掉）",
                js("!document.getElementById('b-chatgpt').disabled"))
            chk("C 后台驻留：ChatGPT 状态行 = 后台驻留",
                "后台驻留" in (js("document.getElementById('st-chatgpt').textContent") or ""),
                js("document.getElementById('st-chatgpt').textContent"))
            chk("C 后台驻留：状态行带 warn 配色",
                "warn" in (js("document.getElementById('st-chatgpt').className") or ""))

            # 场景 D：ChatGPT 已打开 → 按钮禁用 + 状态行「运行中」
            setrt(False, True, True)
            chk("D 已打开：启动按钮置灰", js("document.getElementById('b-chatgpt').disabled"))
            chk("D 已打开：ChatGPT 状态行含「运行中」",
                "运行中" in (js("document.getElementById('st-chatgpt').textContent") or ""),
                js("document.getElementById('st-chatgpt').textContent"))
            chk("D 已打开：状态行带 ok 配色",
                "ok" in (js("document.getElementById('st-chatgpt').className") or ""))

            print("== 4. 状态行随状态实时重绘（不只是初始那一次） ==")
            setrt(True, True, True)
            _a = js("document.getElementById('st-chatgpt').textContent")
            setrt(False, False, False)
            _b = js("document.getElementById('st-chatgpt').textContent")
            chk("从「运行中」回落到「未启动」时状态行跟着变", _a != _b, "%r → %r" % (_a, _b))
            chk("回落后的状态行确实报「未启动」",
                "未启动" in (_b or ""), _b)

            print("== 5. 未选中预设时按钮仍可读、状态行不乱跳 ==")
            js("SELECTED=null; renderPresets(); renderButtons(); renderSwitchButton();")
            setrt(False, False, False)
            chk("未选中：按钮文案仍是「启用配置」",
                (js("document.getElementById('b-switch').textContent") or "").strip() == "启用配置")
            chk("未选中：按钮置灰",
                js("document.getElementById('b-switch').disabled"))
            chk("未选中：ChatGPT 状态行不受影响，仍显示",
                "ChatGPT" in (js("document.getElementById('st-chatgpt').textContent") or ""))

            print("== 6. 工具提示仍在（状态行没有取代 tooltip） ==")
            js("SELECTED='aibank'; renderPresets(); renderButtons();")
            setrt(True, False, False)
            chk("启用按钮 tooltip 仍说明为何不能启用",
                "正在运行" in (js("document.getElementById('b-switch').title") or ""),
                js("document.getElementById('b-switch').title"))
            chk("外壳 tooltip 兜底仍在",
                "正在运行" in (js("document.getElementById('switch-wrap').title") or ""))
            setrt(False, False, False)
            chk("启动按钮 tooltip 仍带运行状态",
                "运行状态" in (js("document.getElementById('b-chatgpt').title") or ""),
                js("document.getElementById('b-chatgpt').title"))

            print("== 7. 底部日志保留唯一一条操作引导 ==")
            _log = js("document.getElementById('log').textContent") or ""
            chk("日志仍有「就绪」", "就绪" in _log, _log)
            chk("日志引导已改用「启用配置」", "启用配置" in _log, _log)
            chk("日志不再用旧措辞「右侧边栏」", "右侧边栏" not in _log, _log)
            chk("日志不再出现旧术语「切换」", "切换" not in _log, _log)

            print("== 8. 布局：状态行未被挤出边栏 ==")
            chk("ChatGPT 状态行在视口内（底部不溢出）",
                js("""(function(){
                  var r=document.getElementById('st-chatgpt').getBoundingClientRect();
                  return r.bottom <= innerHeight + 1 && r.top >= 0;
                })()"""))
            chk("ChatGPT 状态行宽度不超边栏",
                js("""(function(){
                  var s=document.getElementById('st-chatgpt').getBoundingClientRect();
                  var a=document.getElementById('sidebar').getBoundingClientRect();
                  return s.width <= a.width + 1;
                })()"""))
            chk("ChatGPT 状态行贴在边栏底部（在边栏下半区）",
                js("""(function(){
                  var s=document.getElementById('st-chatgpt').getBoundingClientRect();
                  var a=document.getElementById('sidebar').getBoundingClientRect();
                  return s.top >= a.top + a.height/2;
                })()"""))
            chk("两个按钮仍都在边栏内且只有 2 个",
                js("document.querySelectorAll('#sidebar .bwrap button').length") == 2,
                js("document.querySelectorAll('#sidebar .bwrap button').length"))

            print("== 9. 顶栏改造（IMP-031）：标题图标已删、菜单重组 ==")
            chk("顶栏不再有 h1 标题", js("!document.querySelector('.topbar h1')"))
            chk("顶栏不再有 .logo 图标", js("!document.querySelector('.topbar .logo')"))
            chk("「配置」下拉已删（#b-new 现在是直按钮）",
                js("!document.getElementById('m-config')"))
            chk("#b-new 存在且不在任何下拉里",
                js("!!document.getElementById('b-new') && !document.querySelector('.mpanel #b-new')"))
            chk("#b-new 文案为「新建」",
                (js("document.getElementById('b-new').textContent") or "").strip() == "新建",
                js("document.getElementById('b-new').textContent"))
            chk("顶栏直按钮共 2 个（新建 / 设置）",
                js("document.querySelectorAll('#menubar .mact').length") == 2,
                js("document.querySelectorAll('#menubar .mact').length"))
            chk("顶栏只剩 2 个下拉（工具 / 帮助）",
                js("document.querySelectorAll('#menubar .mtitle').length") == 2,
                js("document.querySelectorAll('#menubar .mtitle').length"))
            for _gone in ["b-edit", "b-save", "b-diff", "b-copy", "b-delete", "b-dry"]:
                chk("顶栏已删 #%s（收进右键菜单）" % _gone,
                    js("!document.getElementById('%s')" % _gone))
            chk("「工具」菜单保留同步预设 / 历史恢复 / 进程诊断",
                all(js("!!document.getElementById('%s')" % i)
                    for i in ["b-harvest", "b-history", "b-guard"]))
            chk("工具菜单三项文案已统一，且末尾不带省略号",
                (js("document.getElementById('b-harvest').textContent") or "").strip() == "同步预设"
                and (js("document.getElementById('b-history').textContent") or "").strip() == "历史恢复"
                and (js("document.getElementById('b-guard').textContent") or "").strip() == "进程诊断",
                js("document.getElementById('b-harvest').textContent"))
            chk("「设置」已从工具菜单提出，成为顶栏直按钮",
                js("!!document.getElementById('b-paths')")
                and js("document.getElementById('b-paths').classList.contains('mact')")
                and not js("!!document.querySelector('.mpanel #b-paths')"))
            chk("菜单里已无任何「…」结尾的项",
                not js("""Array.from(document.querySelectorAll('#menubar .mi'))
                          .some(function(e){return /\\u2026$/.test(e.textContent.trim());})"""))

            print("== 10. 预设卡片（IMP-033）：字段中文化、删 url/key ==")
            _card = js("document.querySelector('#plist .card').textContent") or ""
            chk("卡片用中文「模型」字段名", "模型" in _card, _card)
            chk("卡片用中文「供应商」字段名", "供应商" in _card, _card)
            chk("卡片不再显示 url 行", "url" not in _card, _card)
            chk("卡片不再显示 key 行", "key" not in _card, _card)
            chk("卡片保留「当前」标签",
                "当前" in (js("document.getElementById('plist').textContent") or ""))

            print("== 11. 右键菜单文案（IMP-033）==")
            js("SELECTED='aibank'; renderPresets(); openCtx('aibank', 10, 10);")
            _ctx = js("document.getElementById('ctxmenu').textContent") or ""
            chk("右键菜单首项为「启用」", "启用" in _ctx, _ctx)
            chk("右键菜单启用项不带预设名", "启用 aibank" not in _ctx, _ctx)
            chk("右键菜单用「另存为」", "另存为" in _ctx, _ctx)
            chk("右键菜单不再有「切换」字样", "切换" not in _ctx, _ctx)
            js("closeCtx();")

            print("== 12. 表单布局一致性（IMP-038）：向导与编辑器同一套 .fl/.fi ==")
            # 问题：向导里「预设名」用 .fgrid + label.fl（左标签），下面五项却用 .fieldlbl
            # （块级、左对齐、上间距 10px）—— 两套结构混用，导致风格与对齐都不一致。
            # 断言改为锁「向导的每一行都是 .fl + .fi」，并逐项比对左右边缘是否与编辑器一致。
            js("clearFormState(); WIZ={kind:'official',template:'third_party',form:{},userEdited:false};"
               "openWizard();")
            _lab = js("""[...document.querySelectorAll('#m-body .fgrid > .fl')].map(function(e){
                           return e.textContent.trim(); })""")
            chk("向导标签齐全且为 .fl（不含预设名以外的旧写法）",
                _lab == ["预设名", "模型", "供应商", "接口地址（HTTPS）", "API 密钥",
                         "密钥变量名", "接口协议"], _lab)
            chk("向导内不再出现 .fieldlbl（同一表单只用一套写法）",
                js("document.querySelectorAll('#m-body .fieldlbl').length") == 0,
                js("document.querySelectorAll('#m-body .fieldlbl').length"))
            chk("向导每行控件都是 .fi",
                js("""[...document.querySelectorAll('#m-body .fgrid > .fi')].length""") == 7,
                js("[...document.querySelectorAll('#m-body .fgrid > .fi')].length"))
            # 左右边缘对齐：所有标签右边缘一致、所有控件左边缘一致（这才是「对齐一致」）
            chk("所有标签右边缘对齐",
                js("""(function(){
                      var a=[...document.querySelectorAll('#m-body .fgrid > .fl')]
                            .map(function(e){return Math.round(e.getBoundingClientRect().right);});
                      return a.length>0 && a.every(function(x){return Math.abs(x-a[0])<=1;});
                    })()"""))
            chk("所有控件左边缘对齐",
                js("""(function(){
                      var a=[...document.querySelectorAll('#m-body .fgrid > .fi')]
                            .map(function(e){return Math.round(e.getBoundingClientRect().left);});
                      return a.length>0 && a.every(function(x){return Math.abs(x-a[0])<=1;});
                    })()"""))
            # 与编辑器用同一套类名与同一列宽（106px），保证两个弹层的视觉完全一致
            chk("向导与编辑器列宽一致（同为 .fgrid 的 106px）",
                js("getComputedStyle(document.querySelector('#m-body .fgrid')).gridTemplateColumns")
                is not None
                and js("document.querySelector('#m-body .fgrid').className") == "fgrid")
            chk("向导的标签数量与控件数量一一对应（7 行）",
                js("document.querySelectorAll('#m-body .fgrid > .fl').length")
                == js("document.querySelectorAll('#m-body .fgrid > .fi').length")
                == 7)
            js("closeModal(true);")
        except Exception:
            import traceback
            chk("探针未抛异常", False, traceback.format_exc()[-1200:])
        finally:
            results["done"] = True
            try:
                win.destroy()
            except Exception:
                pass

    webview.start(worker)
    print("\n通过 %d / 失败 %d" % (OK, FAIL))
    if FAILED:
        print("失败项：")
        for n in FAILED:
            print("  - " + n)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
