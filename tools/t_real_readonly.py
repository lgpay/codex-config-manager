# -*- coding: utf-8 -*-
"""真实数据「只读」复核：用**本机真实配置目录**渲染界面，确认改版后的界面在真实数据下
依然正确，并证明本次运行没有改动任何文件。

★ 只读承诺（本文件的设计约束，勿改）：
  * 不设 `CODEX_HOME`，路径指向真实的 `~/.codex`；设置文件用临时文件隔离，
    绝不读写用户真实的 settings.json；
  * 全程只调用读取类接口（`snapshot` / `history_*` / `chatgpt_state` 等经 `refresh`），
    不点任何「切换 / 保存 / 删除 / 同步」入口；
  * 运行前后对 **在用 config.toml / 每个预设 / .state / .guard** 做 SHA-256 指纹比对，
    一旦有任何字节变化即判失败 —— 因此这个探针本身就是「没有写盘」的证据。

用法：
    python tools/t_real_readonly.py            # 默认只读复核
    CODEX_REAL_HOME=<别的目录> python tools/t_real_readonly.py
"""
import hashlib
import os
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


os.environ.pop("CODEX_HOME", None)          # 强制走真实目录
REAL_HOME = os.environ.get("CODEX_REAL_HOME") or str(core.default_root())
paths = core.Paths(REAL_HOME)


def fingerprint():
    """真实目录下的所有关键文件指纹；只读，不存在则记 None。"""
    out = {"live": None, "state": None, "guard": None}
    for key, p in (("live", paths.live), ("state", paths.state), ("guard", paths.guard)):
        try:
            out[key] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        except OSError as e:                     # noqa: PERF203
            out[key] = f"<unreadable: {e}>"
    presets = {}
    try:
        for f in sorted(paths.lib.glob("*.toml")):
            presets[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        pass
    out["presets"] = presets
    return out


BEFORE = fingerprint()
print(f"真实配置目录：{paths.root}")
print(f"  在用配置：{paths.live}  ({'存在' if BEFORE['live'] else '不存在'})")
print(f"  预设目录：{paths.lib}  （{len(BEFORE['presets'])} 个：{', '.join(BEFORE['presets']) or '无'}）")

tmp_settings_dir = tempfile.mkdtemp(prefix="codegui_real_")
# path_context 非空 → 设置文件走临时文件，真实 settings.json 不被读写
api = app.Api(paths, path_context={}, settings_file=os.path.join(tmp_settings_dir, "settings.json"))

import webview  # noqa: E402

win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api,
                            width=980, height=720, min_size=(780, 560))


def js(code, default=None):
    try:
        return win.evaluate_js(code)
    except Exception as e:  # noqa: BLE001
        return f"<js error: {e}>"


def wait_ready(timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if js("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0") == 1:
            return True
        time.sleep(0.2)
    return False


def worker():
    try:
        chk("界面就绪（真实 STATE 已加载）", wait_ready(), "STATE 未就绪")
        # 窗口显示时 WebView2 会补一次 resize，而 resize 监听会 closeCtx()。
        # 这一步要等它过去，否则右键测试会撞上启动期的 resize（探针假失败）。
        time.sleep(2.4)
        n = js("STATE.presets.length")
        print(f"  · 真实预设数：{n}")

        print("== 真实数据下的新版结构（IMP-021 ~ IMP-026）==")
        chk("顶栏三下拉就位", js("document.querySelectorAll('#menubar .mgroup').length") == 3)
        chk("右侧操作边栏存在", js("!!document.getElementById('sidebar')"))
        chk("主区只有两个按钮，且都在边栏内",
            js("[...document.querySelectorAll('.body button')].map(b=>b.id)") == ["b-switch", "b-chatgpt"]
            and js("[...document.querySelectorAll('.body button')].every(b=>!!b.closest('#sidebar'))") is True,
            js("[...document.querySelectorAll('.body button')].map(b=>b.id)"))
        chk("状态条里没有按钮", js("document.querySelectorAll('.status button').length") == 0)
        chk("边栏在预设列表右侧",
            js("Math.round(document.getElementById('sidebar').getBoundingClientRect().left) >= "
               "Math.round(document.querySelector('.presets').getBoundingClientRect().right)"))
        chk("切换按钮提示为可读文案（非空）",
            len(js("document.getElementById('switch-wrap').getAttribute('title')") or "") > 6)
        chk("启动按钮提示说明运行状态",
            (js("document.getElementById('chatgpt-wrap').getAttribute('title')") or "").startswith("运行状态："),
            js("document.getElementById('chatgpt-wrap').getAttribute('title')"))

        print("== 真实数据下：卡片右键菜单可用 ==")
        cur = js("STATE.presets[0].name")
        # 注意：必须 cancelable:true。WebView2 真实右键永远是 cancelable 的；
        # 若派发不可取消的事件，preventDefault 失效、WebView2 默认菜单照常弹出，
        # 会连带触发 scroll → 被 closeCtx 收起，看起来像「菜单打不开」（探针假失败）。
        js("""(() => { const c=document.querySelector('.card');
              c.dispatchEvent(new MouseEvent('contextmenu',
                {bubbles:true, cancelable:true, clientX:80, clientY:260})); })()""")
        time.sleep(0.4)
        chk("右键菜单打开", js("document.getElementById('ctxmenu').classList.contains('on')") is True)
        chk("右键同时选中该卡片", js("!!document.querySelector('.card.sel')") is True)
        chk("头部为真实预设名",
            (js("document.querySelector('#ctxmenu .ctxhead').textContent") or "").strip() == cur, cur)
        chk("六个条目齐全", js("document.querySelectorAll('#ctxmenu button.mi').length") == 6)
        js("closeCtx();")
        time.sleep(0.2)

        print("== 真实数据下：状态条按需出现（无横幅就不占位置）==")
        chk("状态条状态与横幅数量一致",
            (js("document.querySelectorAll('#status-banners .banner').length") == 0)
            is (js("document.getElementById('status').classList.contains('on')") is False),
            js("document.getElementById('status-banners').textContent"))

        print("== 真实数据下：新建向导只有两个模板、官方模板只问预设名 ==")
        js("document.getElementById('b-new').click();")
        t0 = time.time()
        while time.time() - t0 < 6 and js("document.getElementById('backdrop').classList.contains('on')") is not True:
            time.sleep(0.2)
        chk("向导打开", js("document.getElementById('backdrop').classList.contains('on')") is True)
        chk("模板只有两个",
            js("Array.from(document.getElementById('w-kind').options).map(x=>x.value)") == ["official", "third_party"],
            js("Array.from(document.getElementById('w-kind').options).map(x=>x.value)"))
        chk("官方模板只有预设名一个输入框",
            js("document.querySelectorAll('#m-body input').length") == 1
            and js("!!document.getElementById('w-new_name')"))
        chk("官方模板不给「获取模型 / 测试模型调用」",
            js("!document.getElementById('w-models') && !document.getElementById('w-check')"
               " && !document.getElementById('w-connect')"))
        chk("官方模板说明写明空白预设由宿主补齐",
            "空白预设" in (js("document.getElementById('w-guide').textContent") or ""))
        js("document.querySelector('#m-foot button').click();")   # 取消
        time.sleep(0.3)

        print("== 只读性：真实配置 / 预设 / 状态 / 守卫指纹未变 ==")
        after = fingerprint()
        chk("在用 config.toml 未变", after["live"] == BEFORE["live"])
        chk("预设文件集合与内容未变", after["presets"] == BEFORE["presets"],
            f"{BEFORE['presets']} -> {after['presets']}")
        chk(".state 未变", after["state"] == BEFORE["state"])
        chk(".guard 未变", after["guard"] == BEFORE["guard"])
    except Exception as e:  # noqa: BLE001
        import traceback
        chk("探针未抛异常", False, traceback.format_exc()[-900:])
    finally:
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass


webview.start(worker)

import shutil  # noqa: E402

shutil.rmtree(tmp_settings_dir, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
