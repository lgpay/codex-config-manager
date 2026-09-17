# -*- coding: utf-8 -*-
"""模型功能 GUI 探针：只连接本地 127.0.0.1 mock，不触碰真实配置。"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        OK += 1; print("  ok   " + name)
    else:
        FAIL += 1; print("  FAIL " + name + (" " + extra if extra else ""))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        raw = json.dumps({"data": [{"id": "gui-model-a"}, {"id": "gui-model-b"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
root = tempfile.mkdtemp(prefix="gui_models_")
os.environ["MODEL_GUI_KEY"] = "gui-secret-never-real"
paths = core.Paths(root); core.ensure_layout(paths)
paths.guard.write_text("__test_neutral_guard__.exe\n", encoding="utf-8")
(paths.lib / "mock.toml").write_text(
    'model_provider = "mock"\nmodel = "gui-model-a"\n'
    '[model_providers.mock]\nname = "Mock"\n'
    f'base_url = "http://127.0.0.1:{server.server_port}/v1"\n'
    'env_key = "MODEL_GUI_KEY"\nwire_api = "chat"\n', encoding="utf-8")
paths.live.write_bytes((paths.lib / "mock.toml").read_bytes()); core.write_state(paths, "mock")
api = app.Api(paths)
win = webview.create_window(ui.APP_TITLE, html=ui.HTML, js_api=api, width=980, height=720, min_size=(780, 560))


def js(code):
    try: return win.evaluate_js(code)
    except Exception as exc: return "<js error: %s>" % exc


def wait_ready(timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        if js("(typeof STATE !== 'undefined' && STATE && STATE.presets) ? 1 : 0") == 1: return True
        time.sleep(.2)
    return False


def wait_modal(want, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if js("document.getElementById('backdrop').classList.contains('on')") is want: return True
        time.sleep(.15)
    return False


def worker():
    try:
        chk("界面就绪", wait_ready())
        js("openEditor('mock')")
        chk("编辑器打开", wait_modal(True))
        time.sleep(.5)
        chk("编辑器有获取模型按钮", js("!!document.getElementById('e-models')"))
        chk("编辑器按钮文案正确", js("document.getElementById('e-models').textContent") == "获取模型")
        js("document.getElementById('e-url').value='http://127.0.0.1:%d/v1'; document.getElementById('e-url').dispatchEvent(new Event('input')); document.getElementById('e-apikey').value='gui-secret-never-real'; document.getElementById('e-models').click()" % server.server_port)
        chk("获取模型确认框打开", wait_modal(True))
        body = js("document.getElementById('m-body').textContent") or ""
        chk("确认框显示 localhost 目标", "127.0.0.1" in body)
        chk("确认框说明 GET 请求", "GET" in body)
        js("document.querySelector('#m-foot button:last-child').click()")
        end = time.time() + 8
        while time.time() < end:
            if js("!!document.getElementById('e-model-result')") is True and js("document.getElementById('e-model-list').options.length") == 2:
                break
            time.sleep(.2)
        chk("模型列表结果可见", "获取" in (js("document.getElementById('e-model-result').textContent") or ""))
        chk("模型列表进入可选项", js("document.getElementById('e-model-list').options.length") == 2)
        chk("模型列表含第一项", js("document.getElementById('e-model-list').options[0].value") == "gui-model-a")
        chk("保留手工输入能力", js("document.getElementById('e-model').tagName") == "INPUT")
        js("closeModal(true); clearFormState();")
        time.sleep(.3)
        js("document.getElementById('b-new').click()")
        chk("新建向导打开", wait_modal(True))
        opts = js("Array.from(document.getElementById('w-kind').options).map(x=>x.value).join(',')") or ""
        # IMP-026：模板从五种精简为两种，且官方模板 = 空白预设
        chk("向导只保留两个模板", opts == "official,third_party", opts)
        labels = js("Array.from(document.getElementById('w-kind').options).map(x=>x.textContent)") or []
        chk("两个模板分别是官方服务与自定义模型",
            len(labels) == 2 and "官方服务" in labels[0] and "自定义模型" in labels[1], labels)
        chk("官方模板只问预设名，不给模型 / 地址 / 检查按钮",
            js("!!document.getElementById('w-new_name') && !document.getElementById('w-model')"
               " && !document.getElementById('w-base_url') && !document.getElementById('w-api_key')"
               " && !document.getElementById('w-check') && !document.getElementById('w-connect')"))
        chk("官方模板说明写明「空白预设」并由宿主补齐",
            "空白预设" in (js("document.getElementById('w-guide').textContent") or "")
            and "自动补齐" in (js("document.getElementById('w-guide').textContent") or ""))
        js("document.getElementById('w-kind').value='third_party'; document.getElementById('w-kind').dispatchEvent(new Event('change'))")
        time.sleep(.4)
        chk("切到自定义模型后出现大模型字段",
            js("!!document.getElementById('w-model') && !!document.getElementById('w-base_url')"
               " && !!document.getElementById('w-api_key') && !!document.getElementById('w-check')"))
        chk("自定义模型说明写明只写大模型配置",
            "只写大模型相关设置" in (js("document.getElementById('w-guide').textContent") or ""))
        chk("自定义模型默认协议为 responses",
            js("document.getElementById('w-wire_api').value") == "responses")
        js("document.getElementById('w-base_url').value='http://127.0.0.1:%d/v1'; document.getElementById('w-env_key').value='MODEL_GUI_KEY'; document.getElementById('w-api_key').value='gui-secret-never-real'; document.getElementById('w-models').click()" % server.server_port)
        chk("向导获取模型确认框打开", wait_modal(True))
        js("document.querySelector('#m-foot button:last-child').click()")
        end=time.time()+8
        while time.time()<end:
            if js("!!document.getElementById('w-model-list')") is True and js("document.getElementById('w-model-list').options.length") == 2: break
            time.sleep(.2)
        chk("向导获取后恢复表单", js("!!document.getElementById('w-kind')") is True)
        chk("向导列表进入可选项", js("document.getElementById('w-model-list').options.length") == 2)
    except Exception as exc:
        chk("探针未抛异常", False, repr(exc))
    finally:
        try: win.destroy()
        except Exception: pass


webview.start(worker)
server.shutdown(); server.server_close(); shutil.rmtree(root, ignore_errors=True)
print("\n通过 %d / 失败 %d" % (OK, FAIL))
sys.exit(1 if FAIL else 0)
