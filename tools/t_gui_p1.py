# -*- coding: utf-8 -*-
"""IMP-003/004/005/006 的新 GUI 无头探针。

覆盖「官方 / 第三方新建向导」「保存 vs 保存并启用」「本地检查（不联网）」
「第三方连接测试（逐次确认、一次性 token、禁用项显式列出 TLS/不跟随跳转/超时/费用）」
「恢复之前的配置」等用户可见链路。

全程在临时 CODEX_HOME 中运行；连接测试只验证「确认门槛 + 一次性 token」，
绝不真正联网（避免 12s 超时与真实计费）。核心层网络安全断言由 test_priority1 锁定。
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
OFFICIAL = ('model_reasoning_effort = "medium"\n'
            '[model_providers.example]\n'
            'name = "Example Provider"\n'
            'base_url = "https://example.eu.org/v1"\n'
            'env_key = "EXAMPLE_API_KEY"\n'
            'wire_api = "responses"\n')

root = tempfile.mkdtemp(prefix="codegui_p1_")
os.environ["CODEX_HOME"] = root
os.environ["P_KEY"] = "synthetic-probe-key-not-real"  # 让本地检查通过（不真正联网）
paths = core.Paths(root)
core.ensure_layout(paths)
# 测试隔离：给临时目录一个不会命中的守卫名单，避免被本机正在运行的宿主进程拦截
# （仅影响本测试目录；真实 DEFAULT_GUARD 与连接安全断言不受影响）。
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "example.toml").write_text(PRESET, encoding="utf-8")
(paths.lib / "official.toml").write_text(OFFICIAL, encoding="utf-8")
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


def api_call(expr, wait=0.6):
    """执行返回 Promise 的 api() 调用，结果暂存到 window.__api 再读回。"""
    code = "(async()=>{try{window.__api=await (" + expr + ");}catch(e){window.__api={'_err':String(e)};}})()"
    js(code)
    time.sleep(wait)
    return js("window.__api")


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

        print("== IMP-003：新建配置向导 == ")
        js("document.getElementById('b-new').click();")
        chk("向导弹层打开", wait_modal(True))
        time.sleep(0.4)
        chk("标题为「新建配置向导」",
            "新建配置向导" in (js("document.getElementById('m-title').textContent") or ""),
            js("document.getElementById('m-title').textContent"))
        chk("默认官方：第三方字段隐藏",
            js("document.getElementById('w-third').style.display") == "none",
            js("document.getElementById('w-third').style.display"))

        # 切到第三方
        js("""(() => { const s = document.getElementById('w-kind');
              s.value = 'third_party';
              s.dispatchEvent(new Event('change')); return 1; })()""")
        time.sleep(0.5)
        chk("切第三方：第三方字段显示",
            js("document.getElementById('w-third').style.display") == "block",
            js("document.getElementById('w-third').style.display"))
        chk("切第三方：连接测试按钮可用",
            js("document.getElementById('w-connect').disabled") is False)
        # 切回官方
        js("""(() => { const s = document.getElementById('w-kind');
              s.value = 'official';
              s.dispatchEvent(new Event('change')); return 1; })()""")
        time.sleep(0.5)
        chk("切回官方：第三方字段隐藏",
            js("document.getElementById('w-third').style.display") == "none")

        print("== IMP-005：连接确认弹层显式列出安全项（向导内）== ")
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
        chk("确认文案含 TLS 校验", "TLS" in cbody, cbody[:80])
        chk("确认文案含 不跟随跳转", "不跟随" in cbody, cbody[:80])
        chk("确认文案含 超时", "超时" in cbody, cbody[:80])
        chk("确认文案含 费用提醒", "费用" in cbody, cbody[:80])
        close_modal()
        time.sleep(0.5)

        print("== IMP-003：官方模板从空创建、不继承第三方设置 ==")
        r = api_call("api().preview_new('official', 'wiz_off', {})")
        chk("官方预览 ok", bool(r and r.get("ok")), r)
        txt = (r or {}).get("text", "")
        chk("官方模板不含 model_provider", "model_provider" not in txt, txt[:160])
        chk("官方模板不含 base_url", "base_url" not in txt, txt[:160])
        chk("官方模板不含 env_key", "env_key" not in txt, txt[:160])
        try:
            import tomllib
            tomllib.loads(txt)
            chk("官方模板是合法 TOML", True)
        except Exception as e:  # noqa: BLE001
            chk("官方模板是合法 TOML", False, str(e))

        print("== IMP-003：第三方缺字段被拒 ==")
        r = api_call("api().preview_new('third_party', 'wiz_tp', {model:'x'})")
        chk("第三方缺字段预览失败", bool(r and r.get("ok") is False), r)

        print("== IMP-005：本地检查不联网 ==")
        tp_form = dict(model='m', model_provider='p', base_url='https://p.example/v1',
                       env_key='P_KEY', wire_api='responses')
        r = api_call(f"api().local_check({tp_form!r})")
        chk("第三方本地检查 ok", bool(r and r.get("ok")), r)
        chk("network_allowed=True", bool(r and r.get("network_allowed") is True), r)
        chk("文案声明未联网", bool(r and ("未联网" in (r.get("message") or "")
                                          or "未发送" in (r.get("message") or ""))), r)
        r2 = api_call("api().local_check({})")
        chk("官方本地检查 network_allowed=False",
            bool(r2 and r2.get("network_allowed") is False), r2)
        chk("官方文案声明不读取官方登录",
            bool(r2 and ("官方" in (r2.get("message") or ""))), r2)

        print("== IMP-005：连接测试确认门槛 + 一次性 token（不联网） ==")
        r = api_call(f"api().prepare_connection({tp_form!r})")
        chk("prepare_connection ok", bool(r and r.get("ok")), r)
        token = (r or {}).get("token")
        chk("返回一次性 token", bool(token))
        msg = (r or {}).get("message", "")
        chk("确认文案含 费用提醒", "费用" in msg, msg[:80])
        # 错误 token → 不联网、被拒
        r = api_call("api().run('connection', null, {token:'bad', confirmed:true})")
        chk("错误 token 被拒（未联网）", bool(r and r.get("error")), r)
        # 未确认 → 被拒
        r = api_call("api().run('connection', null, {token:undefined, confirmed:false})")
        chk("未确认被拒", bool(r and r.get("error")), r)
        # 一次性 token 复用失效（用真 token 再查 prepare 前先试第二次应失败）
        # 先拿到已用 token 的“再次使用”应失败：用同一 token 但 prepare 已清空前不可复现，
        # 故此处仅验证 token 字段存在（一次性语义由 test_priority1 锁定）。

        print("== IMP-006：恢复之前的配置 指引 == ")
        js("document.getElementById('b-recovery').click();")
        chk("恢复弹层打开", wait_modal(True))
        time.sleep(0.3)
        rbody = js("document.getElementById('m-body').textContent") or ""
        chk("恢复步骤含 复制（不要移动）", "复制" in rbody, rbody[:60])
        chk("恢复步骤含 recovery.toml 命名", "recovery.toml" in rbody, rbody[:60])
        chk("恢复步骤含 退出 Codex", "退出 Codex" in rbody or "完全退出" in rbody, rbody[:60])
        close_modal()

        print("== IMP-004：保存并启用需二次确认（当前预设）== ")
        # 打开「正在使用」的 example 编辑器
        js("openEditor('example');")
        chk("编辑器打开", wait_modal(True))
        time.sleep(0.8)
        # 点「保存并启用…」应弹「确认保存并启用」，而不是直接写盘
        js("document.querySelectorAll('#m-foot button')[1].click();")  # 中间按钮
        chk("保存并启用弹确认框", wait_modal(True))
        time.sleep(0.3)
        ctitle = js("document.getElementById('m-title').textContent") or ""
        chk("确认框为「确认保存并启用」", "确认保存并启用" in ctitle, ctitle)
        cbody = js("document.getElementById('m-body').textContent") or ""
        chk("确认框含 恢复方法", "恢复方法" in cbody or "历史" in cbody, cbody[:60])
        close_modal()
        time.sleep(0.8)   # 关闭确认框后编辑器应被还原（回退到上一层视图）
        chk("取消确认后编辑器已还原", js("!!document.getElementById('e-model')"))
        close_modal()      # 关闭编辑器本身
        time.sleep(0.5)

        print("== IMP-004：非当前预设「保存」不启用（live/state 不变）== ")
        js("openEditor('official');")
        chk("官方编辑器打开", wait_modal(True))
        time.sleep(0.8)
        before_live = paths.live.read_bytes()
        before_state = paths.state.read_bytes()
        js("""(() => { const e = document.getElementById('e-model');
              e.value = 'gpt-p1-saved'; e.dispatchEvent(new Event('input')); return 1; })()""")
        time.sleep(0.6)
        js("document.querySelector('#m-foot button:last-child').click();")  # 保存
        t0 = time.time()
        while time.time() - t0 < 15:
            if js("(typeof BUSY !== 'undefined' && BUSY) ? 0 : 1") == 1:
                break
            time.sleep(0.25)
        time.sleep(0.6)
        chk("保存后弹层关闭", js("document.getElementById('backdrop').classList.contains('on')") is False)
        off = (paths.lib / "official.toml").read_text(encoding="utf-8")
        chk("预设文件已改（保存生效）", 'gpt-p1-saved' in off, off[:200])
        chk("保存未启用：正在使用的配置不变", paths.live.read_bytes() == before_live)
        chk("保存未启用：状态记录不变", paths.state.read_bytes() == before_state)

        print("== IMP-004（非当前预设）：保存并启用需确认、启用才会替换 ==")
        js("openEditor('official');")
        chk("官方编辑器打开", wait_modal(True))
        time.sleep(0.8)
        # 官方预设当前非「正在使用」：点「保存并启用…」
        js("document.querySelectorAll('#m-foot button')[1].click();")
        chk("非当前预设保存并启用也弹确认", wait_modal(True))
        time.sleep(0.3)
        chk("确认框为「确认保存并启用」",
            "确认保存并启用" in (js("document.getElementById('m-title').textContent") or ""))
        close_modal()
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
