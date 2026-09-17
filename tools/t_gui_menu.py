# -*- coding: utf-8 -*-
"""UI 重做（IMP-021 ~ IMP-025、IMP-031、IMP-033）无头 GUI 探针。

覆盖五件事，且逐条对应改动条目：
  * IMP-021 顶部菜单栏：原「操作」栏功能迁入菜单、单选展开、点外部 / Esc 收起、
            面板不溢出视口；IMP-031/037 起顶栏为「新建」「设置」两个直按钮 + 工具 / 帮助两个下拉；
  * IMP-022 卡片右键菜单：屏蔽默认右键菜单、右键即选中、条目与禁用原因、
            贴边翻转、点外部 / Esc 收起、条目接通真实动作；
            文案改短（启用 / 编辑 / 对比 / 复制 / 另存为 / 删除）；
  * IMP-023 常驻按钮只剩两个（启用配置 / 启动 ChatGPT）；「Codex 运行时不能启用」进
            启用按钮提示，「运行状态」进启动按钮提示；状态条不再有 pill；
  * IMP-024 布局：窄窗口不裁切、不横向滚动，菜单打开时仍在视口内；
  * IMP-025 两个常驻按钮移入**预设列表右侧的操作边栏**（固定宽、纵向堆叠、撑满边栏），
            状态条只承载横幅、没有横幅时整条折叠；
  * IMP-033 ChatGPT 三态改到边栏底部单独一行（`#st-chatgpt`，带状态色），
            启用按钮不再有自己的状态行（`#st-switch` 已删）。

全程在临时 CODEX_HOME 中运行；用中性 .guard 隔离本机正在运行的宿主，
不触碰真实配置、不联网、不弱化任何安全断言。
"""

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import hashlib

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
'''
OTHER = PRESET.replace("example", "other").replace("Example", "Other").replace("gpt-5.6-luna", "gpt-5.6-sol")

root = tempfile.mkdtemp(prefix="codegui_menu_")
os.environ["CODEX_HOME"] = root
os.environ["EXAMPLE_API_KEY"] = "synthetic-probe-key-not-real"
paths = core.Paths(root)
core.ensure_layout(paths)
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "example.toml").write_text(PRESET, encoding="utf-8")
(paths.lib / "other.toml").write_text(OTHER, encoding="utf-8")
core.write_state(paths, "example")
paths.live.write_text(PRESET, encoding="utf-8")


def fingerprint():
    h = {}
    for p in [paths.live, paths.lib / "example.toml", paths.lib / "other.toml", paths.state]:
        h[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return h


BEFORE = fingerprint()

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


def wait_eq(expr, expect, timeout=6):
    """轮询直到表达式的值等于期望值。

    pywebview 的 evaluate_js 是跨进程往返，紧挨着连发「点击 → 读状态」偶发读早一帧
    （IMP-017 记过一次同类竞态）。这里统一用轮询断言，避免偶发假失败。
    """
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = js(expr)
        if last == expect:
            return True
        time.sleep(0.12)
    print(f"       （等待超时：{expr} 期望 {expect!r} 实际 {last!r}）")
    return False


def menu_open_count():
    return "document.querySelectorAll('#menubar .mgroup.open').length"


def ctx_fire(name, x=60, y=300):
    """在指定卡片上派发真正的 contextmenu 事件，返回 (菜单是否打开, 是否被 preventDefault)。"""
    return js("""(() => {
      const el = [...document.querySelectorAll('.card')].find(c => c.dataset.name === %r);
      if (!el) return {found:false};
      const ev = new MouseEvent('contextmenu', {bubbles:true, cancelable:true,
                                               clientX:%d, clientY:%d});
      const notCancelled = el.dispatchEvent(ev);   // preventDefault 后返回 false
      return {found:true, prevented: !notCancelled,
              open: document.getElementById('ctxmenu').classList.contains('on'),
              selected: SELECTED};
    })()""" % (name, x, y))


def rect(sel):
    return js("(() => { const e=document.querySelector(%r); if(!e) return null;"
              " const r=e.getBoundingClientRect();"
              " return {l:Math.round(r.left),t:Math.round(r.top),"
              " r:Math.round(r.right),b:Math.round(r.bottom)}; })()" % sel)


def worker():
    try:
        chk("界面就绪（STATE 已加载）", wait_ready(), "STATE 未就绪")
        time.sleep(0.5)

        # ---------------- IMP-021 / IMP-031 顶部菜单栏 ----------------
        print("== IMP-021/031 顶部菜单栏：一个直按钮 + 两个下拉 ==")
        chk("菜单栏存在", js("!!document.getElementById('menubar')"))
        # IMP-031：原「配置」下拉拆掉 —— 新建提成直按钮 #b-new，
        # 编辑/另存/复制/删除进卡片右键菜单。所以下拉只剩 工具 / 帮助 两个。
        chk("恰好两个下拉组（工具 / 帮助）", js("document.querySelectorAll('#menubar .mgroup').length") == 2,
            js("document.querySelectorAll('#menubar .mgroup').length"))
        titles = js("[...document.querySelectorAll('#menubar .mtitle')].map(x=>x.textContent.trim())")
        chk("下拉标题为 工具/帮助", titles == ["工具", "帮助"], titles)
        # IMP-037：直按钮从 1 个（新建）增到 2 个（新建 / 设置）。
        macts = js("[...document.querySelectorAll('#menubar .mact')].map(x=>x.textContent.trim())")
        chk("直按钮为 新建/设置，都不在下拉里",
            macts == ["新建", "设置"] and not js("!!document.querySelector('.mpanel .mact')"), macts)
        chk("「新建」排在两个下拉之前",
            js("""(function(){
                  var n=document.getElementById('b-new').getBoundingClientRect();
                  var t=document.getElementById('m-tools').getBoundingClientRect();
                  return n.left < t.left;
                })()"""))
        chk("「设置」排在工具下拉之后、帮助下拉之前",
            js("""(function(){
                  var s=document.getElementById('b-paths').getBoundingClientRect();
                  var a=document.getElementById('m-tools').getBoundingClientRect();
                  var b=document.getElementById('m-help').getBoundingClientRect();
                  return s.left > a.left && s.left < b.left;
                })()"""))
        chk("默认全部收起", js("document.querySelectorAll('#menubar .mgroup.open').length") == 0)
        chk("默认面板不可见（display 为 none）",
            js("getComputedStyle(document.querySelector('#menubar .mpanel')).display") == "none")

        print("== IMP-021/031/037 功能区分布：菜单 3+3 项 + 直按钮 2 个 + 右键 6 项 ==")
        mapping = {
            "工具": ["b-harvest", "b-history", "b-guard"],
            "帮助": ["b-help", "b-recovery", "b-about"],
        }
        for title, ids in mapping.items():
            got = js("""(() => {
              const t=[...document.querySelectorAll('#menubar .mtitle')].find(x=>x.textContent.trim()===%r);
              if(!t) return null;
              return [...t.parentElement.querySelectorAll('.mpanel .mi')].map(x=>x.id); })()""" % title)
            chk(f"「{title}」菜单项齐全", got == ids, got)
        # IMP-031：这些原属顶栏的单条预设动作已收进右键菜单，顶栏不再重复一份。
        # 断言迁移（不是删除）：锁「顶栏确实没有它们」，能力由右键菜单那组断言兜住。
        for gone in ["b-edit", "b-save", "b-copy", "b-delete", "b-diff", "b-dry", "m-config"]:
            chk(f"顶栏已移除 #{gone}", not js("!!document.getElementById('%s')" % gone))
        # IMP-037：菜单项文字末尾不写省略号 —— 带省略号的项没几个真会再弹一层，只是噪音。
        chk("菜单里没有任何「…」结尾的项",
            not js("""Array.from(document.querySelectorAll('#menubar .mi'))
                      .some(function(e){return /…$/.test(e.textContent.trim());})"""),
            js("[...document.querySelectorAll('#menubar .mi')].map(x=>x.textContent.trim())"))
        chk("菜单项文案为 同步预设/历史恢复/进程诊断/使用帮助/手动恢复说明/关于",
            js("[...document.querySelectorAll('#menubar .mi')].map(x=>x.textContent.trim())")
            == ["同步预设", "历史恢复", "进程诊断", "使用帮助", "手动恢复说明", "关于"],
            js("[...document.querySelectorAll('#menubar .mi')].map(x=>x.textContent.trim())"))
        chk("原 #actions 操作栏已移除", js("!document.getElementById('actions')"))
        chk("原 details.adv 折叠已移除", js("!document.querySelector('details.adv')"))
        chk("顶栏不再有 h1 标题（窗口标题已够）", js("!document.querySelector('.topbar h1')"))
        chk("顶栏不再有 logo 图标", js("!document.querySelector('.topbar .logo')"))

        print("== IMP-021 菜单交互：单选展开 / 点外部 / Esc ==")
        js("document.getElementById('m-tools').click();")
        chk("点「工具」展开", wait_eq(menu_open_count(), 1))
        chk("aria-expanded 同步为 true",
            js("document.getElementById('m-tools').getAttribute('aria-expanded')") == "true")
        js("document.getElementById('m-help').click();")
        chk("切到「帮助」后只剩一个展开", wait_eq(menu_open_count(), 1))
        chk("展开的是「帮助」",
            js("!!document.getElementById('m-help').closest('.mgroup').classList.contains('open')"))
        js("document.getElementById('m-help').click();")
        chk("再点同一项则收起", wait_eq(menu_open_count(), 0))

        js("document.getElementById('m-tools').click();")
        wait_eq(menu_open_count(), 1)
        js("document.querySelector('.card').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
        chk("点菜单外收起", wait_eq(menu_open_count(), 0))

        js("document.getElementById('m-help').click();")
        chk("Esc 前菜单是展开的", wait_eq(menu_open_count(), 1))
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        chk("Esc 收起菜单", wait_eq(menu_open_count(), 0))

        print("== IMP-021 菜单面板不溢出视口 ==")
        for mid in ("m-tools", "m-help"):
            geo = js("""(() => { document.getElementById(%r).click();
              const p=document.querySelector('#menubar .mgroup.open .mpanel');
              if(!p) return null; const r=p.getBoundingClientRect();
              const out={l:Math.round(r.left),r:Math.round(r.right),b:Math.round(r.bottom),
                         vw:innerWidth,vh:innerHeight};
              document.getElementById('menubar').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
              return out; })()""" % mid)
            chk(f"{mid} 面板在视口内",
                geo and geo["l"] >= 0 and geo["r"] <= geo["vw"] + 1 and geo["b"] <= geo["vh"] + 1, geo)

        # ---------------- IMP-025 两个常驻按钮进右侧边栏 ----------------
        print("== IMP-025/033 常驻按钮只剩两个，且都放进预设右侧的边栏 ==")
        chk("主区只有 2 个按钮（启用配置 + 启动 ChatGPT）",
            js("document.querySelectorAll('.body button').length") == 2,
            js("document.querySelectorAll('.body button').length"))
        chk("两个按钮都在右侧边栏内",
            js("[...document.querySelectorAll('.body button')].every(b=>!!b.closest('#sidebar'))") is True)
        chk("边栏内按钮 id 齐全（b-switch / b-chatgpt）",
            js("[...document.querySelectorAll('.body button')].map(b=>b.id)") == ["b-switch", "b-chatgpt"],
            js("[...document.querySelectorAll('.body button')].map(b=>b.id)"))
        chk("状态条里不再有按钮",
            js("document.querySelectorAll('.status button').length") == 0)
        chk("启动按钮在 .bwrap 外壳内（禁用时仍能显示提示）",
            js("!!document.getElementById('b-chatgpt').closest('#chatgpt-wrap')"))
        chk("启用按钮在 .bwrap 外壳内", js("!!document.getElementById('b-switch').closest('#switch-wrap')"))
        chk("边栏位于预设列表右侧",
            js("Math.round(document.getElementById('sidebar').getBoundingClientRect().left) >= "
               "Math.round(document.querySelector('.presets').getBoundingClientRect().right)"))
        chk("边栏宽度固定（164px，不随列表伸缩）",
            abs((js("document.getElementById('sidebar').getBoundingClientRect().width") or 0) - 164) <= 2,
            js("document.getElementById('sidebar').getBoundingClientRect().width"))
        chk("两个按钮都撑满边栏宽度（纵向堆叠，不挤成半宽）",
            js("""(() => { const w=document.getElementById('sidebar').getBoundingClientRect().width;
                   return [...document.querySelectorAll('.body button')]
                     .every(b=>Math.abs(b.getBoundingClientRect().width-w) < 2); })()""") is True)
        chk("两个按钮纵向排列（启动在启用下方）",
            js("Math.round(document.getElementById('b-chatgpt').getBoundingClientRect().top) > "
               "Math.round(document.getElementById('b-switch').getBoundingClientRect().bottom) - 1"))
        # IMP-033：ChatGPT 运行状态单独占边栏底部一行，带状态色。
        chk("ChatGPT 状态行在边栏内且在两个按钮之下",
            js("!!document.querySelector('#sidebar #st-chatgpt')") and
            js("Math.round(document.getElementById('st-chatgpt').getBoundingClientRect().top) > "
               "Math.round(document.getElementById('b-chatgpt').getBoundingClientRect().bottom) - 1"))
        chk("启用按钮不再有自己的状态行（#st-switch 已删）",
            not js("!!document.getElementById('st-switch')"))
        chk("启用按钮文案固定为「启用配置」",
            js("document.getElementById('b-switch').textContent.trim()") == "启用配置",
            js("document.getElementById('b-switch').textContent"))
        chk("hero 不再有常驻动作按钮（b-edit-cur 已移除）",
            js("!document.getElementById('b-edit-cur') && !document.getElementById('b-switch-cur')"))
        chk("空态引导按钮 b-save-empty 已移除", js("!document.getElementById('b-save-empty')"))

        print("== IMP-025 状态条只放横幅：没有横幅就整条折叠 ==")
        chk("无横幅时状态条折叠",
            js("document.getElementById('status').classList.contains('on')") is False)
        chk("折叠时不占高度",
            js("Math.round(document.getElementById('status').getBoundingClientRect().height)") == 0)
        js("""setBanners('<div class="banner warn"><span class="ico">!</span>'
             + '<span class="txt">probe banner</span></div>');""")
        time.sleep(0.3)
        chk("有横幅时展开且占高度",
            js("document.getElementById('status').classList.contains('on')") is True and
            js("document.getElementById('status').getBoundingClientRect().height") > 5,
            js("document.getElementById('status').getBoundingClientRect().height"))
        js("setBanners('');")
        time.sleep(0.3)
        chk("横幅清空后重新折叠",
            js("document.getElementById('status').classList.contains('on')") is False)
        js("renderStatus();")
        time.sleep(0.3)

        print("== IMP-023/033 运行状态不再占 pill：说明并入按钮提示 + 边栏状态行 ==")
        chk("状态条 pill 已移除", js("document.querySelectorAll('#status .pill').length") == 0)
        chk("#status-pills 已移除", js("!document.getElementById('status-pills')"))
        chk("未运行时启用按钮可用", js("document.getElementById('b-switch').disabled") is False)
        tip = js("document.getElementById('switch-wrap').getAttribute('title')") or ""
        chk("启用提示说明将启用哪个预设", "example" in tip, tip)
        ct = js("document.getElementById('chatgpt-wrap').getAttribute('title')") or ""
        chk("启动按钮提示含运行状态", ct.startswith("运行状态："), ct)
        chk("按钮自身也带同一提示",
            js("document.getElementById('b-switch').getAttribute('title')") == tip)
        # IMP-033：ChatGPT 的三态现在也写在边栏底部那一行里，与 tooltip 同一套判据。
        chk("边栏状态行报「ChatGPT 未启动」",
            "未启动" in (js("document.getElementById('st-chatgpt').textContent") or ""),
            js("document.getElementById('st-chatgpt').textContent"))

        print("== IMP-023/033 宿主运行中：启用置灰且写明原因 ==")
        js("STATE.guard.running = true; renderButtons();")
        time.sleep(0.3)
        chk("运行中启用按钮禁用", js("document.getElementById('b-switch').disabled") is True)
        tip = js("document.getElementById('switch-wrap').getAttribute('title')") or ""
        chk("提示含「Codex 正在运行，不能启用」", "Codex 正在运行，不能启用" in tip, tip)
        chk("提示给出退出指引", "退出" in tip, tip)
        chk("运行中不再有常驻警告横幅", js("document.querySelectorAll('#status-banners .banner').length") == 0,
            js("document.getElementById('status-banners').textContent"))
        js("STATE.guard.running = false; renderButtons();")
        time.sleep(0.3)

        print("== IMP-023/033 启动按钮提示与边栏状态行随 ChatGPT 状态变化 ==")
        js("STATE.chatgpt = {running:false, windowed:false, count:0}; renderChatGPTButton();")
        time.sleep(0.2)
        chk("未运行时可用", js("document.getElementById('b-chatgpt').disabled") is False)
        chk("提示为「未运行」",
            "未运行" in (js("document.getElementById('chatgpt-wrap').title") or ""))
        chk("状态行为「未启动」",
            "未启动" in (js("document.getElementById('st-chatgpt').textContent") or ""))
        js("STATE.chatgpt = {running:true, windowed:false, count:3}; renderChatGPTButton();")
        time.sleep(0.2)
        chk("仅后台驻留时仍可点击", js("document.getElementById('b-chatgpt').disabled") is False)
        chk("提示为「后台驻留」",
            "后台驻留" in (js("document.getElementById('chatgpt-wrap').title") or ""))
        chk("状态行为「后台驻留」带 warn 配色",
            "后台驻留" in (js("document.getElementById('st-chatgpt').textContent") or "") and
            "warn" in (js("document.getElementById('st-chatgpt').className") or ""))
        js("STATE.chatgpt = {running:true, windowed:true, count:3}; renderChatGPTButton();")
        time.sleep(0.2)
        chk("界面已打开则禁用", js("document.getElementById('b-chatgpt').disabled") is True)
        chk("提示为「已打开」",
            "已打开" in (js("document.getElementById('chatgpt-wrap').title") or ""))
        chk("按钮文案变为「ChatGPT 已打开」",
            js("document.getElementById('b-chatgpt').textContent.trim()") == "ChatGPT 已打开")
        chk("状态行为「运行中」带 ok 配色",
            "运行中" in (js("document.getElementById('st-chatgpt').textContent") or "") and
            "ok" in (js("document.getElementById('st-chatgpt').className") or ""))
        js("refresh(true);")
        time.sleep(0.8)

        # ---------------- IMP-022 卡片右键菜单 ----------------
        print("== IMP-022 右键菜单：屏蔽默认菜单 + 右键即选中 ==")
        r = ctx_fire("other", 60, 300)
        chk("找到目标卡片", isinstance(r, dict) and r.get("found"), r)
        chk("默认右键菜单被屏蔽", isinstance(r, dict) and r.get("prevented"), r)
        chk("右键后菜单打开", isinstance(r, dict) and r.get("open"), r)
        chk("右键即选中该卡片", isinstance(r, dict) and r.get("selected") == "other", r)
        chk("卡片呈选中态", js("[...document.querySelectorAll('.card.sel')].map(c=>c.dataset.name)") == ["other"])

        print("== IMP-022/033 条目齐全 + 头部显示预设名 ==")
        chk("头部显示预设名",
            (js("document.querySelector('#ctxmenu .ctxhead').textContent") or "").strip() == "other")
        labels = js("[...document.querySelectorAll('#ctxmenu button.mi')].map(x=>x.textContent.trim())")
        # IMP-033：文案全部改成两字短词，「启用」不再跟预设名。
        chk("六个条目齐全且文案统一",
            labels == ["启用", "编辑", "对比", "复制", "另存为", "删除"], labels)
        chk("「启用」不带预设名", labels and labels[0] == "启用", labels)
        chk("含两处分隔", js("document.querySelectorAll('#ctxmenu .msep').length") == 2)
        chk("非当前预设的「删除」可用",
            js("[...document.querySelectorAll('#ctxmenu button.mi')].find(x=>x.textContent.indexOf('删除')>=0).disabled") is False)
        chk("每条都带原因提示",
            js("document.querySelectorAll('#ctxmenu button.mi[title]').length") == 6)

        print("== IMP-022/033 当前预设：启用写明「正在使用」、删除禁用 ==")
        js("closeCtx();")
        r = ctx_fire("example", 60, 220)
        chk("当前预设右键菜单打开", isinstance(r, dict) and r.get("open"), r)
        cur_tip = js("[...document.querySelectorAll('#ctxmenu button.mi')].find(x=>x.textContent.indexOf('启用')>=0).title") or ""
        chk("当前预设的启用提示写明正在使用", "正在使用中" in cur_tip, cur_tip)
        chk("当前预设的删除被禁用",
            js("[...document.querySelectorAll('#ctxmenu button.mi')].find(x=>x.textContent.indexOf('删除')>=0).disabled") is True)
        del_tip = js("[...document.querySelectorAll('#ctxmenu button.mi')].find(x=>x.textContent.indexOf('删除')>=0).title") or ""
        chk("删除禁用给出原因", "不能删除" in del_tip, del_tip)

        print("== IMP-022 宿主运行中：右键里的启用被禁用并写明原因 ==")
        js("closeCtx(); STATE.guard.running = true; renderButtons();")
        r = ctx_fire("other", 60, 300)
        chk("运行中右键菜单仍可打开", isinstance(r, dict) and r.get("open"), r)
        sw = js("""(() => { const b=[...document.querySelectorAll('#ctxmenu button.mi')]
                     .find(x=>x.textContent.indexOf('启用')>=0);
                   return {d:b.disabled, t:b.title}; })()""")
        chk("运行中启用条目禁用", isinstance(sw, dict) and sw.get("d") is True, sw)
        chk("运行中启用条目写明「不能启用」",
            isinstance(sw, dict) and "不能启用" in (sw.get("t") or ""), sw)
        js("closeCtx(); STATE.guard.running = false; renderButtons();")
        time.sleep(0.3)

        print("== IMP-022/033 条目接通真实动作 ==")
        r = ctx_fire("other", 60, 300)
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='编辑').click();""")
        chk("「编辑」打开编辑器", wait_modal(True))
        time.sleep(0.8)
        chk("编辑器标题为 other", "other" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)
        chk("动作执行后右键菜单已关闭",
            wait_eq("document.getElementById('ctxmenu').classList.contains('on')", False))

        r = ctx_fire("other", 60, 300)
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='对比').click();""")
        chk("「对比」打开差异弹层", wait_modal(True))
        time.sleep(0.4)
        chk("差异弹层标题含「差异」", "差异" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)

        r = ctx_fire("other", 60, 300)
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='启用').click();""")
        chk("「启用」打开启用确认", wait_modal(True))
        time.sleep(0.4)
        chk("确认弹层为「确认启用」", "确认启用" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
        time.sleep(0.4)

        r = ctx_fire("other", 60, 300)
        js("""[...document.querySelectorAll('#ctxmenu button.mi')]
                .find(x=>x.textContent.trim()==='复制').click();""")
        chk("「复制」打开复制弹层", wait_modal(True))
        time.sleep(0.4)
        chk("复制弹层标题为「复制配置」", "复制配置" in (js("document.getElementById('m-title').textContent") or ""))
        chk("复制默认建议名 other-copy",
            js("document.getElementById('copy-name').value") == "other-copy")
        close_modal()
        time.sleep(0.4)

        print("== IMP-022 点外部 / Esc 收起 ==")
        ctx_fire("other", 60, 300)
        js("document.getElementById('hero').dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))")
        chk("点菜单外收起", wait_eq("document.getElementById('ctxmenu').classList.contains('on')", False))
        ctx_fire("other", 60, 300)
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));")
        chk("Esc 收起", wait_eq("document.getElementById('ctxmenu').classList.contains('on')", False))
        chk("Esc 不会顺带关掉不存在的弹层",
            js("document.getElementById('backdrop').classList.contains('on')") is False)

        print("== IMP-022 贴边翻转：右下角触发仍在视口内 ==")
        geo = js("""(() => {
          const vw=innerWidth, vh=innerHeight;
          const el=[...document.querySelectorAll('.card')].find(c=>c.dataset.name==='other');
          const ev=new MouseEvent('contextmenu',{bubbles:true,cancelable:true,
                    clientX:vw-4, clientY:vh-4});
          el.dispatchEvent(ev);
          const r=document.getElementById('ctxmenu').getBoundingClientRect();
          const out={l:Math.round(r.left),t:Math.round(r.top),
                     r:Math.round(r.right),b:Math.round(r.bottom),vw:vw,vh:vh};
          closeCtx();
          return out; })()""")
        chk("右下角触发时菜单翻转到视口内",
            geo and geo["l"] >= 0 and geo["t"] >= 0 and geo["r"] <= geo["vw"] + 1 and geo["b"] <= geo["vh"] + 1,
            geo)

        # ---------------- IMP-024 布局 ----------------
        print("== IMP-024 布局：980x720 不裁切、不横向滚动 ==")
        for w, h in ((980, 720), (780, 560)):
            win.resize(w, h)
            time.sleep(1.0)
            g = js("""(() => {
              const r=(s)=>{const e=document.querySelector(s); if(!e) return null;
                            const b=e.getBoundingClientRect();
                            return {t:Math.round(b.top),b:Math.round(b.bottom),h:Math.round(b.height)};};
              return {vw:innerWidth, vh:innerHeight,
                      docScroll:document.documentElement.scrollWidth,
                      bodyScroll:document.body.scrollWidth,
                      status:r('.status'), console_:r('.console'), sw:r('#b-switch'), cg:r('#b-chatgpt'),
                      sidebar:r('#sidebar'), presets:r('.presets')}; })()""")
            chk(f"{w}x{h} 无横向滚动",
                g and g["docScroll"] <= g["vw"] + 1 and g["bodyScroll"] <= g["vw"] + 1, g)
            chk(f"{w}x{h} 状态条在视口内", g and g["status"] and g["status"]["b"] <= g["vh"] + 1, g)
            chk(f"{w}x{h} 日志区在视口内", g and g["console_"] and g["console_"]["b"] <= g["vh"] + 1, g)
            chk(f"{w}x{h} 启用按钮可见", g and g["sw"] and g["sw"]["h"] > 10, g)
            chk(f"{w}x{h} 启动按钮可见", g and g["cg"] and g["cg"]["h"] > 10, g)
            chk(f"{w}x{h} 边栏可见且未越出视口",
                g and g["sidebar"] and g["sidebar"]["h"] > 10 and g["sidebar"]["b"] <= g["vh"] + 1, g)
            geo = js("""(() => { document.getElementById('m-tools').click();
              const p=document.querySelector('#menubar .mgroup.open .mpanel');
              if(!p) return null; const r=p.getBoundingClientRect();
              const out={l:Math.round(r.left),r:Math.round(r.right),b:Math.round(r.bottom),
                         vw:innerWidth,vh:innerHeight};
              closeMenu(); return out; })()""")
            chk(f"{w}x{h} 菜单面板不溢出", geo and geo["r"] <= geo["vw"] + 1 and geo["b"] <= geo["vh"] + 1, geo)
        win.resize(980, 720)
        time.sleep(0.8)

        print("== 只读性：预设 / 正在使用的配置 / 状态记录未被改动 ==")
        chk("指纹一致", fingerprint() == BEFORE, "文件被改动")
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
