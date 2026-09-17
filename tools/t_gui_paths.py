# -*- coding: utf-8 -*-
"""首次路径向导与设置热切换无头探针；全部使用临时 settings/CODEX 目录。"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
import app  # noqa: E402
import core  # noqa: E402
import ui  # noqa: E402

OK = FAIL = 0

def chk(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1; print("  ok  ", name)
    else:
        FAIL += 1; print("  FAIL", name, extra)

base = Path(tempfile.mkdtemp(prefix="gui_paths_"))
profile = base / "profile"
local = base / "local"
roaming = base / "roaming"
profile.mkdir(); local.mkdir(); roaming.mkdir()
settings = base / "manager" / "settings.json"
os.environ["USERPROFILE"] = str(profile)
os.environ["LOCALAPPDATA"] = str(local)
os.environ["APPDATA"] = str(roaming)
os.environ[core.SETTINGS_ENV] = str(settings)
os.environ.pop("CODEX_HOME", None)
settings.parent.mkdir(parents=True)
settings.write_text("{broken", encoding="utf-8")
old_home = base / "old-codex"
old_lib = old_home / "configs"
old_lib.mkdir(parents=True)
(old_home / "config.toml").write_text('model="old"\n', encoding="utf-8")
(old_lib / "old.toml").write_text('model="old"\n', encoding="utf-8")
new_home = base / "new-codex"
new_lib = base / "custom-presets"
new_home.mkdir()
new_lib.mkdir()
(new_lib / "new.toml").write_text('model="new"\n', encoding="utf-8")

paths, context = core.Paths.for_gui()
import webview  # noqa: E402

# --- 输出编码：CI（windows-latest）控制台默认 cp1252，中文断言名会 UnicodeEncodeError ---
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

api = app.Api(paths, path_context=context, settings_file=settings)
win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api,
                            width=980, height=720, min_size=(780, 560))
api._window = win

def js(code):
    try: return win.evaluate_js(code)
    except Exception as exc: return f"<js error: {exc}>"

def wait(expr, want=True, timeout=12):
    start=time.time()
    while time.time()-start<timeout:
        if js(expr)==want:return True
        time.sleep(.2)
    return False

def open_paths():
    """打开「设置」弹层。

    产品在 BUSY（有操作执行中）时会忽略这次点击并提示「请稍候」——这是设计行为。
    探针若不等界面空闲就点，负载高时会抢跑（表现为弹层打不开、后续断言连锁失败），
    所以这里先等 BUSY 落下再点，并确认弹层真的开了。
    """
    wait("!BUSY", True, timeout=10)
    js("document.getElementById('b-paths').click()")
    return wait("document.getElementById('m-title').textContent", "设置")

def worker():
    try:
        chk("界面状态已加载", wait("(typeof STATE!=='undefined'&&STATE)?1:0",1))
        # IMP-031：弹层标题与菜单项都从「配置位置」统一为「设置」。
        chk("无有效设置时首次向导自动打开", wait("document.getElementById('m-title').textContent", "首次设置"), js("document.getElementById('m-title').textContent"))
        chk("损坏设置显示明确恢复状态", "设置文件损坏" in (js("document.getElementById('m-body').textContent") or ""))
        chk("向导有 Codex 路径输入", js("!!document.getElementById('path-home')"))
        chk("向导有预设路径输入", js("!!document.getElementById('path-configs')"))
        chk("向导有目录与文件选择", js("!!document.getElementById('path-home-dir')&&!!document.getElementById('path-home-file')&&!!document.getElementById('path-configs-dir')"))
        chk("向导说明不搬移删除", "不搬移、不删除" in (js("document.getElementById('m-body').textContent") or ""))
        js(f"document.getElementById('path-home').value={json.dumps(str(old_home))};document.getElementById('path-home').dispatchEvent(new Event('input'));document.getElementById('path-follow').checked=true;document.getElementById('path-follow').dispatchEvent(new Event('change'))")
        # updatePathPreview 是异步的（await validate_paths），固定 sleep 在机器忙时会抢跑 —— 改成轮询断言
        chk("确认页显示 config.toml 与预设数",
            wait("(() => { const t=document.getElementById('path-preview'); if(!t) return false;"
                 " const s=t.textContent||'';"
                 " return s.indexOf('config.toml')>=0 && s.indexOf('预设 1 个')>=0; })()", True),
            js("document.getElementById('path-preview').textContent"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("首次设置保存并关闭", wait("document.getElementById('backdrop').classList.contains('on')",False))
        chk("settings 已写入临时位置", settings.exists(), settings)
        chk("首页已切到首次选择目录", wait("(typeof STATE!=='undefined'&&STATE.root)||''",str(old_home.resolve())))
        chk("自定义 settings 未写真实 LOCALAPPDATA", not (local / core.SETTINGS_APP_DIR / core.SETTINGS_FILE).exists())
        chk("设置页入口可达", open_paths())
        js(f"document.getElementById('path-home').value={json.dumps(str(new_home))};document.getElementById('path-home').dispatchEvent(new Event('input'));document.getElementById('path-follow').checked=false;document.getElementById('path-configs').value={json.dumps(str(new_lib))};document.getElementById('path-configs').dispatchEvent(new Event('input'))")
        # 等到预览真的换成了新预设目录再点「应用位置」，避免异步预览还没落笔就提交
        chk("预览更新为新的预设目录",
            wait("(document.getElementById('path-preview').textContent||'').indexOf('custom-presets')>=0", True),
            js("document.getElementById('path-preview').textContent"))
        js("document.querySelector('#m-foot button:last-child').click()")
        chk("热切换设置页后关闭", wait("document.getElementById('backdrop').classList.contains('on')",False))
        chk("无需重启即读取自定义预设目录", wait("(typeof STATE!=='undefined'&&STATE.lib)||''",str(new_lib.resolve())))
        # 卡片列表由 refresh → renderPresets 落笔，比 STATE.lib 晚一拍；固定时序会在忙时抢跑
        chk("切换后新预设可见",
            wait("[...document.querySelectorAll('.card')].map(x=>x.dataset.name).indexOf('new')>=0", True),
            js("[...document.querySelectorAll('.card')].map(x=>x.dataset.name)"))
        chk("旧目录数据未搬移删除", (old_lib / "old.toml").exists())
        data=json.loads(settings.read_text(encoding="utf-8"))
        chk("settings 保存 schema/root/configs", data["schema_version"]==1 and Path(data["codex_home"])==new_home.resolve() and Path(data["configs_dir"])==new_lib.resolve(), data)
        close_force = "clearFormState();MODAL_BACK=null;document.getElementById('backdrop').classList.remove('on')"
        chk("设置页可重复打开", open_paths())
        api.path_context['env_controlled']=True
        js("closeModal(true)")
        time.sleep(.2)
        chk("环境控制时设置页可打开", open_paths())
        chk("CODEX_HOME 控制提示可见",
            wait("(document.getElementById('m-body').textContent||'').indexOf('CODEX_HOME')>=0", True),
            js("document.getElementById('m-body').textContent"))
        # 按钮的 disabled 由 path_info 返回后设置，同样是异步的 —— 轮询而非单次读取
        chk("环境控制时应用按钮禁用",
            wait("document.querySelector('#m-foot button:last-child').disabled", True))
        js(close_force)
        time.sleep(.3)
    except Exception as exc:
        import traceback
        chk("探针无异常",False,traceback.format_exc()[-1200:])
    finally:
        try:win.destroy()
        except Exception:pass

webview.start(worker)
shutil.rmtree(base, ignore_errors=True)
print(f"\n通过 {OK} / 失败 {FAIL}")
sys.exit(1 if FAIL else 0)
