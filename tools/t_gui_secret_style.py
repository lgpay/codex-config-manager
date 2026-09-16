# -*- coding: utf-8 -*-
"""IMP-014 API Key 组件无头 GUI 探针；只使用隔离目录与假值。"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import app  # noqa: E402
import core  # noqa: E402
import ui  # noqa: E402
import webview  # noqa: E402

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

root = tempfile.mkdtemp(prefix="gui_secret_style_")
os.environ["CODEX_HOME"] = root
os.environ["CODEX_CONFIG_MANAGER_SETTINGS"] = os.path.join(root, "settings.json")
paths = core.Paths(root)
core.ensure_layout(paths)
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "mock.toml").write_text(PRESET, encoding="utf-8")
paths.live.write_text(PRESET, encoding="utf-8")
core.write_state(paths, "mock")
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

def wait_modal(want, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if js("document.getElementById('backdrop').classList.contains('on')") is want:
            return True
        time.sleep(.15)
    return False

def rect(selector):
    return js("(() => { const e=document.querySelector(%r); if(!e)return null; const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom}; })()" % selector)

def check_form(kind, label):
    secret = "fake-secret-" + ("x" * 320)
    input_id = "e-apikey" if kind == "editor" else "w-api_key"
    button_id = "e-keyshow" if kind == "editor" else "w-keyshow"
    shell = rect(".secret-field")
    inp = rect("#" + input_id)
    btn = rect("#" + button_id)
    normal = rect("#e-url" if kind == "editor" else "#w-base_url")
    body = rect("#m-body")
    modal = rect("#modal")
    geo = js("({vw:innerWidth,vh:innerHeight,bodyScroll:document.getElementById('m-body').scrollWidth,bodyClient:document.getElementById('m-body').clientWidth,docScroll:document.documentElement.scrollWidth,bodyOverflow:getComputedStyle(document.body).overflowX})")
    chk(label + " 使用统一 secret-field", js("document.querySelector('.secret-field').classList.contains('secret-field')"))
    chk(label + " 外壳宽度等于普通字段", abs(shell["w"] - normal["w"]) <= 1, str((shell, normal)))
    chk(label + " 输入与普通字段高度一致", abs(inp["h"] - normal["h"]) <= 2, str((inp, normal)))
    chk(label + " 外壳与输入按钮等高", abs(inp["h"] - btn["h"]) <= 1, str((inp, btn)))
    chk(label + " 输入占据剩余宽度", inp["w"] > 180 and inp["w"] + btn["w"] <= shell["w"] + 1, str((inp, btn, shell)))
    chk(label + " 按钮为紧凑固定宽", 48 <= btn["w"] <= 56, str(btn))
    chk(label + " 不超父容器", shell["right"] <= body["right"] + 1 and shell["right"] <= modal["right"] + 1, str((shell, body, modal)))
    chk(label + " 初始为 password", js("document.getElementById('%s').type" % input_id) == "password")
    chk(label + " 初始 aria 状态正确", js("document.getElementById('%s').getAttribute('aria-pressed')" % button_id) == "false")
    chk(label + " 按钮有可访问名称", js("document.getElementById('%s').getAttribute('aria-label')" % button_id) == "显示 API Key")
    chk(label + " 按钮可由 Tab 聚焦", js("document.getElementById('%s').tabIndex" % button_id) == 0)
    js("document.getElementById('%s').value=%r; document.getElementById('%s').dispatchEvent(new Event('input',{bubbles:true}))" % (input_id, secret, input_id))
    chk(label + " 长密钥值保留", js("document.getElementById('%s').value.length" % input_id) == len(secret))
    chk(label + " 长密钥不撑宽", js("document.getElementById('%s').getBoundingClientRect().width" % input_id) <= shell["w"] + 1)
    dirty_before = js("FORM_DIRTY")
    js("document.getElementById('%s').click()" % button_id)
    chk(label + " 显示切换为 text", js("document.getElementById('%s').type" % input_id) == "text")
    chk(label + " 显示 aria 状态更新", js("document.getElementById('%s').getAttribute('aria-pressed')" % button_id) == "true")
    chk(label + " 显示后值不变", js("document.getElementById('%s').value.length" % input_id) == len(secret))
    js("document.getElementById('%s').click()" % button_id)
    chk(label + " 隐藏切回 password", js("document.getElementById('%s').type" % input_id) == "password")
    chk(label + " 隐藏 aria 状态复原", js("document.getElementById('%s').getAttribute('aria-pressed')" % button_id) == "false")
    chk(label + " 按钮不改变 dirty 状态", js("FORM_DIRTY") is dirty_before, str((dirty_before, js("FORM_DIRTY"))))
    chk(label + " 当前视口无横向溢出", geo["bodyScroll"] <= geo["bodyClient"] + 1 and geo["docScroll"] <= geo["vw"] + 1 and geo["bodyOverflow"] == "hidden", str(geo))
    return {"shell": shell, "input": inp, "button": btn, "normal": normal, "geo": geo}

def worker():
    try:
        chk("界面就绪", wait_ready())
        js("openEditor('mock')")
        chk("编辑器打开", wait_modal(True))
        time.sleep(.5)
        editor = check_form("editor", "编辑器")
        js("closeModal(true); clearFormState();")
        time.sleep(.3)
        js("document.getElementById('b-new').click();")
        chk("新建向导打开", wait_modal(True))
        js("document.getElementById('w-kind').value='third_party'; document.getElementById('w-kind').dispatchEvent(new Event('change'))")
        time.sleep(.5)
        wizard = check_form("wizard", "新建向导")
        same_style = js("(() => { const i=document.getElementById('w-api_key'),b=document.getElementById('w-keyshow'),s=document.querySelector('.secret-field'); const ci=getComputedStyle(i),cb=getComputedStyle(b),cs=getComputedStyle(s); return {shellWidth:cs.width,shellHeight:cs.height,inputHeight:ci.height,inputFont:ci.fontFamily,inputSize:ci.fontSize,inputBg:ci.backgroundColor,inputRadius:ci.borderRadius,buttonWidth:cb.width,buttonHeight:cb.height}; })()")
        chk("编辑器与向导使用同一组件样式", same_style["inputHeight"] == "34px" and same_style["buttonWidth"] == "52px" and same_style["buttonHeight"] == "34px", str(same_style))
        chk("编辑器与向导输入高度一致", abs(editor["input"]["h"] - wizard["input"]["h"]) <= 1, str((editor, wizard)))
        chk("编辑器与向导按钮宽度一致", abs(editor["button"]["w"] - wizard["button"]["w"]) <= 1, str((editor, wizard)))
        win.resize(650, 560)
        time.sleep(.6)
        narrow = js("({vw:innerWidth,vh:innerHeight,docScroll:document.documentElement.scrollWidth,bodyScroll:document.getElementById('m-body').scrollWidth,bodyClient:document.getElementById('m-body').clientWidth,modal:document.getElementById('modal').getBoundingClientRect().toJSON(),shell:document.querySelector('.secret-field').getBoundingClientRect().toJSON()})")
        chk("窄窗口无横向滚动", narrow["docScroll"] <= narrow["vw"] + 1 and narrow["bodyScroll"] <= narrow["bodyClient"] + 1, str(narrow))
        chk("窄窗口组件仍在弹层内", narrow["shell"]["right"] <= narrow["modal"]["right"] + 1, str(narrow))
    except Exception as exc:
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
