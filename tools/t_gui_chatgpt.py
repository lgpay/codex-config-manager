# -*- coding: utf-8 -*-
"""「启动 ChatGPT」按钮无头 GUI 探针（IMP-016 建立，IMP-018 扩展联动，IMP-023 迁移）。

原则：
  * 全程使用隔离的临时 CODEX_HOME，不触碰真实配置；
  * **绝不真的启动 ChatGPT**——启动调用被替换为记录用的假函数；
  * **绝不依赖本机 ChatGPT 的真实开关状态**——状态查询被替换为可控假函数，
    否则本机 ChatGPT 开着时按钮本来就该禁用，探针会失去判别力；
  * 真实系统应用列表查询也被替换，避免依赖具体机器安装情况。

IMP-023 迁移：运行状态 pill 已取消，状态信息并入「启动 ChatGPT」按钮的提示
（`#chatgpt-wrap` 外壳 + 按钮自身的 title）。原来断言 `#status-pills` 文案的用例
改为断言外壳提示，覆盖没有减弱。
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import app      # noqa: E402
import core     # noqa: E402
import launcher  # noqa: E402
import ui       # noqa: E402
import webview  # noqa: E402

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
        print("  ok   " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + (" " + extra if extra else ""))


PRESET = '''model_provider = "mock"
model = "gui-model"
[model_providers.mock]
name = "Mock"
base_url = "https://example.invalid/v1"
env_key = "FAKE_API_KEY"
wire_api = "responses"
'''

root = tempfile.mkdtemp(prefix="gui_chatgpt_")
os.environ["CODEX_HOME"] = root
os.environ["CODEX_CONFIG_MANAGER_SETTINGS"] = os.path.join(root, "settings.json")
paths = core.Paths(root)
core.ensure_layout(paths)
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "mock.toml").write_text(PRESET, encoding="utf-8")
paths.live.write_text(PRESET, encoding="utf-8")
core.write_state(paths, "mock")

# 记录启动调用；不真的启动任何应用。
CALLS = []


def fake_launch(entries=None):
    CALLS.append(entries)
    return {"ok": True, "name": "ChatGPT", "app_id": "OpenAI.Test_abc!App",
            "method": "shell:AppsFolder", "message": "已请求启动 ChatGPT，请查看任务栏。"}


app.launcher.launch_chatgpt = fake_launch
api = app.Api(paths)
win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api, width=980, height=720,
                            min_size=(640, 520))


def js(code):
    try:
        return win.evaluate_js(code)
    except Exception as exc:
        return "<js error: %s>" % exc


def wait_ready(timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        if js("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0") == 1:
            return True
        time.sleep(.2)
    return False


def rect(selector):
    return js("(() => { const e=document.querySelector(%r); if(!e)return null;"
              " const r=e.getBoundingClientRect();"
              " return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom,"
              " midY: r.y + r.height/2}; })()" % selector)


# 把状态查询替换为可控假函数，并在需要时直接改写 STATE.chatgpt 后重绘。
STUB = ("window.__cg = {running:false, windowed:false, count:0};"
        "try { window.pywebview.api.chatgpt_state = () => window.__cg; } catch (e) {}\n"
        "function setCG(o){ window.__cg = o; STATE.chatgpt = o; renderStatus(); }\n")


def digest(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def worker():
    before_live = digest(paths.live)
    before_preset = digest(paths.lib / "mock.toml")
    try:
        chk("窗口就绪", wait_ready())
        js(STUB)
        chk("状态查询已替换为可控桩",
            js("JSON.stringify(window.__cg)") == '{"running":false,"windowed":false,"count":0}',
            repr(js("typeof window.__cg")))

        # --- 位置：IMP-025 后移入「预设列表右侧的操作边栏」，与切换按钮同栏 ---
        chk("启动按钮存在", js("!!document.getElementById('b-chatgpt')"))
        chk("按钮位于右侧边栏内",
            js("(document.getElementById('b-chatgpt').closest('aside')||{}).id") == "sidebar")
        chk("按钮与切换按钮同栏（边栏里只有这两个按钮）",
            js("[...document.querySelectorAll('.body button')].map(b=>b.id)") == ["b-switch", "b-chatgpt"])
        chk("按钮不再位于状态条内",
            js("!document.getElementById('b-chatgpt').closest('.status')"))
        chk("按钮在专用外壳内（禁用时由外壳承担提示）",
            js("!!document.getElementById('b-chatgpt').closest('#chatgpt-wrap')"))
        chk("状态条内不再有运行状态 pill",
            js("document.querySelectorAll('#status .pill').length") == 0)
        sb = rect("#sidebar")
        btn = rect("#b-chatgpt")
        chk("启动按钮在边栏内且撑满边栏宽度（位于切换按钮下方）",
            sb and btn and abs(btn["w"] - sb["w"]) <= 2
            and btn["x"] >= sb["x"] - 1 and btn["right"] <= sb["right"] + 1
            and btn["y"] >= sb["y"] - 1 and btn["bottom"] <= sb["bottom"] + 1
            and btn["y"] > rect("#b-switch")["y"],
            str((sb, btn)))

        # --- 联动：界面未打开 → 可点击 ---
        js("setCG({running:false, windowed:false, count:0});")
        time.sleep(.25)
        chk("未启动时按钮可点击", js("document.getElementById('b-chatgpt').disabled") is False)
        chk("未启动时文案为「启动 ChatGPT」",
            js("document.getElementById('b-chatgpt').textContent.trim()") == "启动 ChatGPT")
        chk("未启动时提示为「未运行」",
            "未运行" in (js("document.getElementById('chatgpt-wrap').getAttribute('title')") or ""))
        chk("未启动时状态条没有多余的 ChatGPT 文案",
            "ChatGPT" not in (js("document.getElementById('status-banners').textContent") or ""))

        # --- 联动：界面已打开 → 不可点击 ---
        js("setCG({running:true, windowed:true, count:9});")
        time.sleep(.25)
        chk("已打开时按钮被禁用", js("document.getElementById('b-chatgpt').disabled") is True)
        chk("已打开时文案变为「ChatGPT 已打开」",
            js("document.getElementById('b-chatgpt').textContent.trim()") == "ChatGPT 已打开")
        chk("已打开时提示给出原因",
            "已打开" in (js("document.getElementById('chatgpt-wrap').getAttribute('title')") or ""))
        chk("按钮自身也带同一提示",
            js("document.getElementById('b-chatgpt').getAttribute('title')")
            == js("document.getElementById('chatgpt-wrap').getAttribute('title')"))
        CALLS.clear()
        js("(() => { const b=document.getElementById('b-chatgpt');"
           " b.disabled = false; b.click(); })()")
        time.sleep(.6)
        chk("已打开时点击不会重复发起启动", len(CALLS) == 0, "calls=%d" % len(CALLS))

        # --- 仅后台驻留（有进程无窗口）→ 仍可点击，但标签说明情况 ---
        js("setCG({running:true, windowed:false, count:3});")
        time.sleep(.25)
        chk("仅后台驻留时按钮仍可点击",
            js("document.getElementById('b-chatgpt').disabled") is False)
        chk("仅后台驻留时提示说明「后台驻留」",
            "后台驻留" in (js("document.getElementById('chatgpt-wrap').getAttribute('title')") or ""))

        # --- 不跟随 Codex 守卫：守卫运行不应禁用启动按钮 ---
        js("setCG({running:false, windowed:false, count:0});")
        js("STATE.guard.running = true; renderButtons();")
        time.sleep(.2)
        chk("守卫运行时切换按钮被禁用",
            js("document.getElementById('b-switch').disabled") is True)
        chk("守卫运行时启动按钮仍可用",
            js("document.getElementById('b-chatgpt').disabled") is False)
        js("STATE.guard.running = false; renderButtons();")
        time.sleep(.2)

        # --- 轮询：状态变化后自动反映到按钮 ---
        js("window.__cg = {running:false, windowed:false, count:0};")
        chk("轮询前按钮可用", js("document.getElementById('b-chatgpt').disabled") is False)
        js("window.__cg = {running:true, windowed:true, count:5}; pollChatGPT();")
        end = time.time() + 5
        while time.time() < end:
            if js("document.getElementById('b-chatgpt').disabled") is True:
                break
            time.sleep(.2)
        chk("轮询发现已打开后按钮自动禁用",
            js("document.getElementById('b-chatgpt').disabled") is True)
        chk("轮询把状态写回 STATE", js("STATE.chatgpt.windowed") is True)

        # 状态没变时轮询不应重绘（避免干扰正在看的内容）。
        # IMP-023 后运行状态已并入按钮提示，轮询只需刷按钮，故这里盯 renderChatGPTButton。
        js("window.__RECOMPUTED = 0; window.__rc = renderChatGPTButton;"
           " renderChatGPTButton = function(){ window.__RECOMPUTED++; return window.__rc(); };")
        js("pollChatGPT();")
        time.sleep(1.2)
        chk("状态无变化时轮询不重绘", js("window.__RECOMPUTED") == 0,
            "recomputed=%s" % js("window.__RECOMPUTED"))
        js("renderChatGPTButton = window.__rc;")

        js("setCG({running:false, windowed:false, count:0});")

        # --- 成功路径 ---
        CALLS.clear()
        js("document.getElementById('b-chatgpt').click();")
        end = time.time() + 8
        while time.time() < end and not CALLS:
            time.sleep(.15)
        chk("点击后调用了一次启动接口", len(CALLS) == 1, "calls=%d" % len(CALLS))
        time.sleep(.5)
        toast = js("document.getElementById('toast').textContent")
        chk("显示成功提示", "已请求启动" in (toast or ""), repr(toast))

        # --- 失败路径 ---
        app.launcher.launch_chatgpt = lambda entries=None: {
            "ok": False, "error": "未检测到 ChatGPT 应用入口，请先在系统中安装 ChatGPT 桌面应用。"}
        js("document.getElementById('b-chatgpt').click();")
        time.sleep(.9)
        toast2 = js("document.getElementById('toast').textContent")
        chk("失败时给出可读提示", "未检测到" in (toast2 or ""), repr(toast2))
        chk("失败后按钮恢复可用",
            js("document.getElementById('b-chatgpt').disabled") is False)

        # --- 抛异常也不能卡死按钮 ---
        def boom(entries=None):
            raise RuntimeError("boom")
        app.launcher.launch_chatgpt = boom
        js("document.getElementById('b-chatgpt').click();")
        time.sleep(.9)
        chk("异常后按钮恢复可用",
            js("document.getElementById('b-chatgpt').disabled") is False)
        app.launcher.launch_chatgpt = fake_launch

        # --- 忙碌态 ---
        js("setBusy(true);")
        time.sleep(.2)
        chk("忙碌时按钮禁用", js("document.getElementById('b-chatgpt').disabled") is True)
        js("setBusy(false);")
        time.sleep(.3)
        chk("解除忙碌后恢复", js("document.getElementById('b-chatgpt').disabled") is False)

        # --- 状态条错误态下按钮仍按 ChatGPT 状态工作 ---
        js("setCG({running:false, windowed:false, count:0});")
        js("const _s = STATE; STATE = Object.assign({}, _s, {error:'probe'}); renderStatus();")
        time.sleep(.25)
        chk("状态读取出错时按钮仍可用（启动不依赖配置状态）",
            js("document.getElementById('b-chatgpt').disabled") is False)
        chk("状态读取出错时错误条仍在",
            "读取配置" in (js("document.getElementById('status-banners').textContent") or ""),
            js("document.getElementById('status-banners').textContent"))
        js("STATE = _s; renderStatus();")

        # --- 布局不裁切 ---
        for w, h in ((980, 720), (780, 560)):
            win.resize(w, h)
            time.sleep(.7)
            geo = rect("#b-chatgpt")
            vp = js("({vw:innerWidth,vh:innerHeight,docScroll:document.documentElement.scrollWidth})")
            chk("%dx%d 按钮在视口内" % (w, h),
                geo and geo["bottom"] <= vp["vh"] + 1 and geo["right"] <= vp["vw"] + 1,
                str((geo, vp)))
            chk("%dx%d 无横向滚动" % (w, h), vp["docScroll"] <= vp["vw"] + 1, str(vp))

        # --- 只读性：点按钮不动配置 ---
        chk("当前配置未被改动", digest(paths.live) == before_live)
        chk("预设文件未被改动", digest(paths.lib / "mock.toml") == before_preset)
    except Exception:
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-1200:])
    finally:
        try:
            win.destroy()
        except Exception:
            pass


webview.start(worker)
shutil.rmtree(root, ignore_errors=True)
print("\n通过 %d / 失败 %d" % (OK, FAIL))
sys.exit(1 if FAIL else 0)
