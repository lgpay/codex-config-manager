# -*- coding: utf-8 -*-

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
import sys as _sys_enc
try:
    _sys_enc.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_enc.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

"""历史恢复、未保存提醒、复制删除的无头 GUI 探针；全程临时 CODEX_HOME。"""
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

OK = FAIL = 0


def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


A = ('model = "a-model"\nmodel_provider = "a"\n'
     '[model_providers.a]\nbase_url = "https://a.example/v1"\n'
     'env_key = "A_KEY"\nwire_api = "responses"\n')
B = ('model = "b-model"\nmodel_provider = "b"\n'
     '[model_providers.b]\nbase_url = "https://b.example/v1"\n'
     'env_key = "B_KEY"\nwire_api = "responses"\n')
HIST = b'model = "restored-model"\n'

root = tempfile.mkdtemp(prefix="gui_restore_")
os.environ["CODEX_HOME"] = root
paths = core.Paths(root)
core.ensure_layout(paths)
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "a.toml").write_text(A, encoding="utf-8")
(paths.lib / "b.toml").write_text(B, encoding="utf-8")
paths.live.write_text(A, encoding="utf-8")
core.write_state(paths, "a")
hist = paths.hist_presets / "b" / "20260916-050505.toml"
hist.parent.mkdir(parents=True)
hist.write_bytes(HIST)
live_hist = paths.hist_live / "config.toml.20260916-050506"
live_hist.parent.mkdir(parents=True, exist_ok=True)
live_hist.write_bytes(b'model = "restored-live"\n')

import webview  # noqa: E402


api = app.Api(paths)
win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api,
                            width=980, height=720, min_size=(780, 560))


def js(code):
    try:
        return win.evaluate_js(code)
    except Exception as exc:  # noqa: BLE001
        return f"<js error: {exc}>"


def wait(expr, want=True, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if js(expr) == want:
            return True
        time.sleep(.2)
    return False


def wait_ready():
    return wait("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0", 1, 12)


def close_force():
    js("clearFormState(); MODAL_BACK=null; document.getElementById('backdrop').classList.remove('on');")
    time.sleep(.3)


def worker():
    try:
        chk("界面就绪", wait_ready())
        time.sleep(.6)
        print("== 新入口 ==")
        for bid in ("b-copy", "b-delete", "b-history"):
            chk(f"{bid} 存在", js(f"!!document.getElementById('{bid}')"))
        chk("复制/删除已收进「配置」菜单",
            js("!!document.querySelector('#menubar .mpanel #b-copy')")
            and js("!!document.querySelector('#menubar .mpanel #b-delete')"))
        chk("历史恢复已收进「工具」菜单",
            js("!!document.querySelector('#menubar .mpanel #b-history')"))
        chk("复制/删除同时可经卡片右键到达", js("!!document.getElementById('ctxmenu')"))
        chk("当前配置删除按钮禁用", js("document.getElementById('b-delete').disabled") is True)

        print("== 编辑器 dirty：无变化不打扰 ==")
        js("openEditor('a')")
        chk("编辑器打开", wait("!!document.getElementById('e-model')", True))
        time.sleep(.5)
        chk("初始不脏", js("FORM_DIRTY") is False)
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        chk("无变化 Esc 直接关闭", wait("document.getElementById('backdrop').classList.contains('on')", False))

        print("== 编辑器 dirty：Esc/取消/遮罩/切换对象 ==")
        js("openEditor('a')"); wait("document.getElementById('backdrop').classList.contains('on')", True); time.sleep(.7)
        js("(()=>{const e=document.getElementById('e-model');e.value='dirty-model';e.dispatchEvent(new Event('input'));})()")
        time.sleep(.4)
        chk("字段变化才 dirty", js("FORM_DIRTY") is True)
        chk("dirty 时 beforeunload 被取消", js("window.dispatchEvent(new Event('beforeunload',{cancelable:true}))") is False)
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        chk("Esc 弹未保存确认", wait("document.getElementById('m-title').textContent", "更改尚未保存"), js("document.getElementById('m-title').textContent"))
        js("document.querySelector('#m-foot button:first-child').click()")
        time.sleep(.5)
        chk("取消离开恢复编辑器", js("!!document.getElementById('e-model')"))
        chk("取消后保留字段", js("document.getElementById('e-model').value") == "dirty-model")
        chk("取消后仍 dirty", js("FORM_DIRTY") is True)
        js("document.getElementById('backdrop').dispatchEvent(new MouseEvent('click',{bubbles:true}))")
        chk("点击遮罩也提示", wait("document.getElementById('m-title').textContent", "更改尚未保存"))
        js("document.querySelector('#m-foot button:first-child').click()")
        time.sleep(.4)
        js("openEditor('b')")
        chk("切换编辑对象也提示", wait("document.getElementById('m-title').textContent", "更改尚未保存"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("放弃后打开目标编辑器", wait("document.getElementById('e-name').value", "b"))
        close_force()

        print("== 向导 dirty ==")
        js("document.getElementById('b-new').click()")
        chk("向导打开", wait("!!document.getElementById('w-new_name')", True))
        chk("向导初始不脏", js("FORM_DIRTY") is False)
        js("(()=>{const e=document.getElementById('w-new_name');e.value='new-one';e.dispatchEvent(new Event('input'));})()")
        time.sleep(.3)
        chk("向导输入后 dirty", js("FORM_DIRTY") is True)
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
        chk("向导 Esc 提示未保存", wait("document.getElementById('m-title').textContent", "更改尚未保存"))
        js("document.querySelector('#m-foot button:first-child').click()")
        time.sleep(.4)
        chk("向导取消离开保留值", js("document.getElementById('w-new_name').value") == "new-one")
        chk("向导恢复后仍 dirty", js("FORM_DIRTY") is True, js("JSON.stringify({kind:FORM_KIND,dirty:FORM_DIRTY,initial:FORM_INITIAL,snap:formSnapshot()})"))
        js("closeModal()")
        time.sleep(.4)
        chk("向导取消再次提示", js("document.getElementById('m-title').textContent") == "更改尚未保存", js("JSON.stringify({title:document.getElementById('m-title').textContent,kind:FORM_KIND,dirty:FORM_DIRTY,back:!!MODAL_BACK,leave:LEAVE_CONFIRM})"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("放弃向导后关闭", wait("document.getElementById('backdrop').classList.contains('on')", False))

        print("== 复制 ==")
        js("SELECTED='b';renderPresets();renderButtons();document.getElementById('b-copy').click()")
        chk("复制建议名称", wait("document.getElementById('copy-name') && document.getElementById('copy-name').value", "b-copy"), js("document.getElementById('m-title').textContent"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("复制任务完成", wait("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1", 1, 12))
        time.sleep(.6)
        chk("副本逐字节一致", (paths.lib / "b-copy.toml").read_bytes() == (paths.lib / "b.toml").read_bytes())
        chk("复制未启用", core.read_state(paths)[0] == "a")

        print("== 删除 ==")
        js("SELECTED='b-copy';renderPresets();renderButtons();document.getElementById('b-delete').click()")
        chk("删除要求输入名称", wait("!!document.getElementById('delete-name')", True))
        js("document.getElementById('delete-name').value='wrong';document.querySelector('#m-foot button:last-child').click()")
        time.sleep(.4)
        chk("名称不符拒绝", "完整配置名称" in (js("document.getElementById('delete-err').textContent") or ""))
        js("document.getElementById('delete-name').value='b-copy';document.querySelector('#m-foot button:last-child').click()")
        chk("删除任务完成", wait("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1", 1, 12))
        time.sleep(.6)
        chk("仅预设文件删除", not (paths.lib / "b-copy.toml").exists())
        chk("删除前历史备份存在", bool(list((paths.hist_presets / "b-copy").glob("*.toml"))))
        chk("当前配置仍在", core.read_state(paths)[0] == "a" and paths.live.read_text(encoding="utf-8") == A)

        print("== 历史列表 / 差异 / 恢复 ==")
        js("document.getElementById('b-history').click()")
        chk("历史弹层打开", wait("!!document.getElementById('hist-id')", True))
        time.sleep(.8)
        labels = js("[...document.getElementById('hist-id').options].map(x=>x.textContent)") or []
        chk("结构化显示来源时间大小", any("预设 b" in x and "字节" in x for x in labels), labels)
        # 两次 change 必须分开触发并各自等预览跑完：连发时两个异步预览响应到达顺序不定，
        # 后到的响应会重渲染弹层并把恢复目标重置回默认项，导致恢复「打错目标」
        # （表现为 b.toml 未变、live 被改，偶发且难查）。
        js("(()=>{const h=document.getElementById('hist-id');"
           "const o=[...h.options].find(x=>x.textContent.includes('预设 b')"
           "&&x.textContent.includes('2026-09-16 05:05:05'));"
           "if(!o)return 0;h.value=o.value;h.dispatchEvent(new Event('change'));return 1;})()")
        time.sleep(1.0)
        chk("已选中带时间戳的历史条目",
            "2026-09-16 05:05:05" in (js(
                "(document.getElementById('hist-id').selectedOptions[0]||{}).textContent") or ""),
            js("(document.getElementById('hist-id').selectedOptions[0]||{}).textContent"))
        js("(()=>{const t=document.getElementById('hist-target');t.value='preset:b';"
           "t.dispatchEvent(new Event('change'));})()")
        time.sleep(1.0)
        chk("恢复目标已选为「预设 b」",
            js("document.getElementById('hist-target').value") == "preset:b",
            js("document.getElementById('hist-target').value"))
        chk("差异预览已渲染", (js("document.getElementById('hist-diff').getBoundingClientRect().height") or 0) > 16)
        chk("差异包含历史内容", "restored-model" in (js("document.getElementById('hist-diff').textContent") or ""))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("恢复确认出现", wait("document.getElementById('m-title').textContent", "确认恢复"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("恢复任务完成", wait("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1", 1, 12))
        time.sleep(.7)
        _bt = paths.lib / "b.toml"
        _bnow = _bt.read_bytes() if _bt.exists() else b"<missing b.toml>"
        chk("非当前预设已恢复", _bnow == HIST, "实际=%r 期望=%r" % (_bnow, HIST))
        _lnow = paths.live.read_text(encoding="utf-8")
        chk("非当前恢复不碰 live", _lnow == A, "实际=%r" % (_lnow[:160],))
        chk("历史文件未删除", hist.exists())
    except Exception as exc:  # noqa: BLE001
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-1200:])
    finally:
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass


webview.start(worker)
shutil.rmtree(root, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
