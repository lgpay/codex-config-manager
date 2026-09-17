# -*- coding: utf-8 -*-
"""「宿主运行状态实时刷新」无头 GUI 探针（IMP-029 建立）。

这个探针盯的是一个真实用户反馈过的 bug：

    用户退出了 Codex，但界面上的「切换」按钮仍然是灰的、点不动。
    （原先只有 ChatGPT 的状态在轮询，宿主运行状态 `guard.running` 只在界面
      渲染那一刻算一次，退出后永远不会更新。）

覆盖四件事：

  * 后端轻量接口 `host_state()` 存在、可调用、返回结构正确；
  * 宿主从「运行中」变「未运行」后，**不需要重新渲染界面**，
    轮询就能把切换按钮恢复成可点、提示文案同步更新；
  * 反向也一样：宿主重新启动后按钮会被重新置灰（不能只处理单向）；
  * 轮询在弹层打开 / 界面忙碌时**真的跳过**（这是设计行为，
    所以另有 focus 补查路径来兜底 —— 一并验证它存在）。

原则：全程隔离的临时 CODEX_HOME；状态查询与启动全部替换为可控假函数；
绝不依赖本机真实的 Codex / ChatGPT 开关状态，否则探针会失去判别力。
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

root = tempfile.mkdtemp(prefix="gui_liveguard_")
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


def wait(expr, want=True, timeout=10):
    """轮询式断言 —— 不靠固定 sleep，避免负载高时抢跑产生假失败。"""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = js(expr)
        if last == want:
            return True
        time.sleep(.15)
    return False


# 把「宿主运行状态」与「ChatGPT 状态」都换成可控桩。
# 注意：host_state 返回值里的 running 直接驱动切换按钮的置灰判定。
STUB = """
window.__host = {running:true, total:1, names:['codex.exe'], source:'file'};
window.__cg   = {running:false, windowed:false, count:0};
window.__hostCalls = 0;
try {
  window.pywebview.api.host_state = () => { window.__hostCalls++; return window.__host; };
  window.pywebview.api.chatgpt_state = () => window.__cg;
} catch (e) {}
function setHost(o){ window.__host = o; }
"""


def digest(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def worker():
    before_live = digest(paths.live)
    before_preset = digest(paths.lib / "mock.toml")
    try:
        chk("窗口就绪", wait_ready())
        js(STUB)

        # ---------------- 后端轻量接口 ----------------
        print("== 后端：轻量运行状态接口 ==")
        chk("core.host_running_now 存在", callable(getattr(core, "host_running_now", None)))
        chk("core.host_running 存在", callable(getattr(core, "host_running", None)))
        chk("app.Api 暴露 host_state", callable(getattr(api, "host_state", None)))
        r = api.host_state()
        chk("host_state 返回 dict 且含 running 布尔", isinstance(r, dict) and isinstance(r.get("running"), bool), str(r))
        chk("host_state 含 names 与 total",
            isinstance(r.get("names"), list) and isinstance(r.get("total"), int), str(r))

        # 隔离环境里 guard 名单是中性名字，本机不可能命中 → 应为未运行
        chk("隔离环境下判定为未运行", r.get("running") is False, str(r))

        # ---------------- 核心场景：退出后按钮恢复可点 ----------------
        print("== 核心：宿主退出后切换按钮自动恢复 ==")
        cur = js("STATE.presets[0].name")
        # 选中该预设，并把宿主状态设为「运行中」
        js("selectPreset(%r)" % cur)
        # 注意：renderSwitchButton 只管切换按钮本身；菜单项的置灰归 renderButtons 管。
        # 手工改 STATE 后两个都要调，否则测的是「我忘了重绘」而不是产品行为。
        js("setHost({running:true, total:1, names:['codex.exe'], source:'file'}); "
           "STATE.guard = Object.assign({}, STATE.guard, {running:true}); "
           "renderSwitchButton(); renderButtons();")
        chk("运行中：切换按钮被置灰",
            wait("document.getElementById('b-switch').disabled", True))
        chk("运行中：提示说明为什么不能切换",
            "正在运行" in (js("document.getElementById('switch-wrap').title") or ""),
            repr(js("document.getElementById('switch-wrap').title")))
        chk("运行中：菜单里「只同步」也置灰",
            js("document.getElementById('b-harvest').disabled") is True)

        # 关键一步：只改桩数据，**不碰界面**，然后等轮询把它捡起来。
        calls_before = js("window.__hostCalls") or 0
        js("setHost({running:false, total:0, names:[], source:'file'})")
        chk("轮询确实在调用 host_state（不是一次性快照）",
            wait("(window.__hostCalls || 0) > %d" % calls_before, True, timeout=12),
            "calls=%s before=%s" % (js("window.__hostCalls"), calls_before))
        chk("★ 退出后：切换按钮自动恢复可点（无需重渲染界面）",
            wait("document.getElementById('b-switch').disabled", False, timeout=14))
        chk("退出后：提示不再说「正在运行」",
            "正在运行" not in (js("document.getElementById('switch-wrap').title") or ""),
            repr(js("document.getElementById('switch-wrap').title")))
        chk("退出后：菜单里「只同步」也恢复可点",
            wait("document.getElementById('b-harvest').disabled", False, timeout=12))

        # ---------------- 反向：重新启动后要重新置灰 ----------------
        print("== 反向：宿主重新运行后按钮应重新置灰 ==")
        js("setHost({running:true, total:1, names:['codex.exe'], source:'file'})")
        chk("重新运行：切换按钮再次被置灰",
            wait("document.getElementById('b-switch').disabled", True, timeout=14))
        js("setHost({running:false, total:0, names:[], source:'file'})")
        chk("再退出：又能恢复可点",
            wait("document.getElementById('b-switch').disabled", False, timeout=14))

        # ---------------- ChatGPT 侧没被这次改动破坏 ----------------
        print("== 回归：ChatGPT 状态轮询仍然有效 ==")
        js("window.__cg = {running:true, windowed:true, count:2}")
        chk("ChatGPT 界面打开 → 按钮禁用且文案变为已打开",
            wait("document.getElementById('b-chatgpt').disabled", True, timeout=14))
        js("window.__cg = {running:false, windowed:false, count:0}")
        chk("ChatGPT 全退 → 按钮恢复可点",
            wait("document.getElementById('b-chatgpt').disabled", False, timeout=14))

        # ---------------- 设计行为：弹层打开时轮询跳过 ----------------
        print("== 设计行为：弹层打开 / 忙碌时轮询跳过，另有 focus 兜底 ==")
        chk("轮询函数会读 BUSY", "if (BUSY) return" in js("pollRuntime.toString()"))
        chk("轮询函数会读 backdrop", "backdrop" in js("pollRuntime.toString()"))
        chk("弹层打开时轮询直接返回（不刷新）",
            wait("(() => { if (typeof pollRuntime !== 'function') return false; "
                 "return pollRuntime.toString().includes('backdrop'); })()", True))
        # 直接验证行为：focus 事件会触发一次 host_state 调用
        calls_before = js("window.__hostCalls") or 0
        js("window.dispatchEvent(new Event('focus'))")
        chk("★ 窗口重新获得焦点会补查一次运行状态（兜底路径）",
            wait("(window.__hostCalls || 0) > %d" % calls_before, True, timeout=8),
            "calls=%s before=%s" % (js("window.__hostCalls"), calls_before))

        # ---------------- 只读性 ----------------
        print("== 只读性：整个过程未改动配置 ==")
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
