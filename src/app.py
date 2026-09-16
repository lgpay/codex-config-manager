# -*- coding: utf-8 -*-
"""
Codex 配置管理器 —— 程序入口

同一个可执行文件承担两种形态：
  * 无参数（或 --gui）  → 图形界面
  * 带子命令            → 无界面通道（附加到调用方控制台输出）

两种形态共用 core.py 的同一份实现，行为一致。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
import threading
import secrets
import time
import connection
import userenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core  # noqa: E402
import ui    # noqa: E402

APP_NAME = ui.APP_TITLE
# 用户提供 codex-icon.png，仅格式转换及标准图标尺寸缩放；不重绘。
# exe、窗口与 UI 均使用同一来源。
ICON_NAME = "codex-config-manager.ico"
UI_ICON_NAME = "codex-icon.png"


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, name),
                 os.path.join(here, "assets", name),
                 os.path.join(os.path.dirname(here), "assets", name)):
        if os.path.exists(cand):
            return cand
    return os.path.join(here, name)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# --------------------------------------------------------------------------
# 控制台（仅无界面通道用；图形界面绝不创建控制台）
# --------------------------------------------------------------------------

def _bind_kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetStdHandle.restype = ctypes.c_void_p
    k32.GetStdHandle.argtypes = [ctypes.c_int]
    k32.GetFileType.restype = ctypes.c_uint
    k32.GetFileType.argtypes = [ctypes.c_void_p]
    return k32


def _force_utf8(attr: str) -> bool:
    """把已有文本流改成 UTF-8 且不做换行翻译。"""
    stream = getattr(sys, attr, None)
    if stream is None or getattr(stream, "closed", True):
        return False
    try:
        stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        return True
    except Exception:
        return False


def _reopen(attr: str, std_id: int, k32) -> bool:
    """从继承的句柄重建文本流（用于 stdout/stderr 原本为 None 的情形）。"""
    try:
        import msvcrt
    except ImportError:
        return False
    h = k32.GetStdHandle(std_id)
    if not h or h in (0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return False
    try:
        fd = msvcrt.open_osfhandle(h, os.O_WRONLY)
        setattr(sys, attr, os.fdopen(fd, "w", encoding="utf-8",
                                     errors="replace", buffering=1, newline="\n"))
        return True
    except Exception:
        return False


def init_console() -> None:
    """窗口子系统程序默认没有控制台。

    输出目标分三种：
      * 被重定向到文件 / 管道 → 直接用继承的句柄，写 UTF-8（换行不做翻译）；
      * 是控制台（或本就是 GUI 程序，没有可用句柄）→ 附加到调用方控制台，
        把控制台代码页切成 65001，再以 UTF-8 打开 CONOUT$；
      * 都没有 → 尽可能把现有流改成 UTF-8。

    图形界面路径不会调用本函数，因此绝不产生控制台窗口。
    """
    if not sys.platform.startswith("win"):
        return
    try:
        k32 = _bind_kernel32()
    except Exception:
        return

    try:
        h = k32.GetStdHandle(-11)
        ftype = k32.GetFileType(h) if h else 0
    except Exception:
        h, ftype = None, 0
    # GetFileType: 1=磁盘文件, 2=字符设备(控制台), 3=管道, 0=未知
    redirected = ftype in (1, 3) and bool(h)

    attached = False
    if not redirected:
        try:
            attached = bool(k32.AttachConsole(ctypes.c_uint(-1).value))
        except Exception:
            attached = False
        if attached:
            try:
                k32.SetConsoleOutputCP(65001)
                k32.SetConsoleCP(65001)
            except Exception:
                pass

    for attr, std_id in (("stdout", -11), ("stderr", -12)):
        if attached:
            try:
                setattr(sys, attr, open("CONOUT$", "w", encoding="utf-8",
                                        errors="replace", buffering=1, newline="\n"))
                continue
            except OSError:
                pass
        if _force_utf8(attr):
            continue
        _reopen(attr, std_id, k32)

    if sys.stdin is None or getattr(sys.stdin, "closed", True):
        if attached:
            try:
                sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
            except OSError:
                pass


def _out(text: str = "") -> None:
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


# --------------------------------------------------------------------------
# 图形界面
# --------------------------------------------------------------------------

class Api:
    """暴露给界面 JS 的接口。耗时操作放后台线程，前端轮询取日志。"""

    def __init__(self, paths: core.Paths, initial: str | None = None,
                 path_context: dict | None = None,
                 settings_file: str | os.PathLike | None = None):
        self.p = paths
        self.initial_preset = initial
        self.path_context = dict(path_context or {})
        self.settings_file = (core.settings_path(settings_file) if path_context is not None
                              else None)
        self._lock = threading.Lock()
        self._running = False
        self._result = None
        self._lines: list = []
        self._op = ""
        self._window = None
        self._connection_pending = None
        self._network_pending = {}
        self._key_pending = None
        self._history_tokens = {}
        self._restore_pending = None

    def suggest_env_key(self, provider, name):
        return userenv.suggest_name(provider, name)

    def prepare_key_save(self, name, value):
        """仅由保存按钮调用；确认凭据只保存摘要，不保留或返回密钥。"""
        with self._lock:
            self._key_pending = None
            try:
                userenv.validate(name, value)
                if not value:
                    return {"ok": True, "overwrite": False}
                old = userenv.read_value(name)
                token = secrets.token_urlsafe(24)
                overwrite = old is not None and old[0] != value
                self._key_pending = (token, time.monotonic(), name,
                                     userenv.fingerprint(value), userenv.fingerprint(old), overwrite)
                return {"ok": True, "token": token, "overwrite": overwrite,
                        "message": "同名用户环境变量已有不同值。是否覆盖？原密钥不会显示；用户环境变量不是加密存储。"}
            except Exception:
                return {"ok": False, "error": "无法准备密钥保存，请检查变量名、密钥格式及用户环境变量权限。"}

    # ---- 启动参数（CLI `edit <名>` 直接把界面开到该预设的编辑器） ----
    def initial(self) -> dict:
        out = {"preset": self.initial_preset} if self.initial_preset else {}
        if self.path_context:
            setting = self.path_context.get("settings") or {}
            candidates = core.probe_codex_locations()
            valid = [x for x in candidates if x.get("valid")]
            needs_setup = (not self.path_context.get("env_controlled")
                           and setting.get("status") != "ok")
            auto_saved = False
            if (needs_setup and setting.get("status") == "missing" and len(valid) == 1
                    and valid[0].get("source") == "默认目录"):
                try:
                    core.save_settings(valid[0]["path"],
                                       str(core.normalize_codex_home(valid[0]["path"]) / "configs"),
                                       self.settings_file)
                    loaded = core.load_settings(self.settings_file)
                    self.p = core.Paths(loaded["settings"]["codex_home"],
                                        loaded["settings"]["configs_dir"])
                    self.path_context = {"source": "settings", "configs_source": "settings",
                                         "env_controlled": False, "settings": loaded}
                    setting, needs_setup, auto_saved = loaded, False, True
                except Exception:
                    pass
            if self.initial_preset:
                needs_setup = False
            out.update({
                "path_setup": needs_setup,
                "path_auto_saved": auto_saved,
                "path_status": setting.get("status", "disabled"),
                "path_error": setting.get("error", ""),
                "path_env_controlled": bool(self.path_context.get("env_controlled") or (os.environ.get("CODEX_HOME") or "").strip()),
                "path_candidates": candidates,
                "path_auto_candidate": (valid[0]["path"] if len(valid) == 1 else ""),
            })
        return out

    def path_info(self) -> dict:
        setting = self.path_context.get("settings") or {}
        return {"ok": True, "codex_home": str(self.p.root),
                "configs_dir": str(self.p.lib),
                "codex_exists": self.p.root.is_dir(),
                "config_exists": self.p.live.is_file(),
                "configs_exists": self.p.lib.is_dir(),
                "preset_count": len(core.list_presets(self.p)),
                "settings_path": str(self.settings_file or ""),
                "settings_status": setting.get("status", "disabled"),
                "settings_error": setting.get("error", ""),
                "env_controlled": bool(self.path_context.get("env_controlled") or (os.environ.get("CODEX_HOME") or "").strip()),
                "source": self.path_context.get("source", "explicit"),
                "configs_source": self.path_context.get("configs_source", "explicit")}

    def choose_folder(self) -> dict:
        if not self._window:
            return {"ok": False, "error": "系统目录选择对话框当前不可用，可手动输入绝对路径。"}
        try:
            import webview
            result = self._window.create_file_dialog(webview.FileDialog.FOLDER,
                                                     allow_multiple=False)
            path = result[0] if result else ""
            return {"ok": bool(path), "path": path,
                    "cancelled": not bool(path)}
        except Exception:
            return {"ok": False, "error": "无法打开目录选择对话框，可手动输入绝对路径。"}

    def choose_config_file(self) -> dict:
        if not self._window:
            return {"ok": False, "error": "系统文件选择对话框当前不可用，可手动输入绝对路径。"}
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("Codex config.toml (config.toml)", "TOML files (*.toml)"))
            path = result[0] if result else ""
            if path:
                selected = os.path.abspath(path)
                if os.path.basename(selected).lower() != "config.toml":
                    return {"ok": False, "error": "请选择名为 config.toml 的文件。"}
                path = os.path.dirname(selected)
            return {"ok": bool(path), "path": path,
                    "cancelled": not bool(path)}
        except Exception:
            return {"ok": False, "error": "无法打开文件选择对话框，可手动输入绝对路径。"}

    def validate_paths(self, codex_home, configs_dir, create=False) -> dict:
        try:
            home = core.normalize_codex_home(codex_home)
            configs = core.normalize_configs_dir(configs_dir or (home / "configs"))
            for path, label in ((home, "Codex 配置目录"), (configs, "预设目录")):
                if path.exists() and not path.is_dir():
                    raise core.CoreError(f"{label}指向了文件。")
                if not path.exists() and not create:
                    raise core.CoreError(f"{label}尚不存在；如需创建，请勾选确认创建精确目录。")
                parent = path if path.exists() else path.parent
                if not parent.exists():
                    parent = next((x for x in path.parents if x.exists()), None)
                if parent is None or not parent.is_dir():
                    raise core.CoreError(f"{label}的父目录不存在或不可访问。")
                try:
                    list(parent.iterdir())
                except OSError as e:
                    raise core.CoreError(f"{label}不可访问：{e}")
            if create:
                home.mkdir(parents=True, exist_ok=True)
                configs.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "codex_home": str(home), "configs_dir": str(configs),
                    "codex_exists": home.is_dir(), "config_exists": (home / "config.toml").is_file(),
                    "configs_exists": configs.is_dir(), "preset_count": core._preset_count(configs)}
        except (core.CoreError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def apply_paths(self, codex_home, configs_dir, create=False) -> dict:
        with self._lock:
            if self._running:
                return {"ok": False, "error": "有操作正在执行，请完成后再更改配置位置。"}
        if self.path_context.get("env_controlled") or (os.environ.get("CODEX_HOME") or "").strip():
            return {"ok": False, "env_controlled": True,
                    "error": "当前由 CODEX_HOME 环境变量控制。请在启动本程序前修改或清除该环境变量；本程序不会自动修改环境变量。"}
        checked = self.validate_paths(codex_home, configs_dir, create=create)
        if not checked.get("ok"):
            return checked
        new_paths = core.Paths(checked["codex_home"], checked["configs_dir"])
        try:
            saved = core.save_settings(new_paths.root, new_paths.lib, self.settings_file)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"设置保存失败，当前配置位置未改变：{e}"}
        self.p = new_paths
        loaded = core.load_settings(self.settings_file)
        self.path_context = {"source": "settings", "configs_source": "settings",
                             "env_controlled": False, "settings": loaded}
        return {"ok": True, "settings": saved, **self.path_info(),
                "message": "配置位置已切换；未搬移或删除旧目录中的任何数据。"}

    # ---- 状态 ----
    def get_state(self) -> dict:
        try:
            return core.snapshot(self.p)
        except Exception as e:                                  # noqa: BLE001
            return {"version": core.VERSION, "root": str(self.p.root),
                    "live": str(self.p.live), "lib": str(self.p.lib),
                    "guard_file": str(self.p.guard), "live_exists": False,
                    "current": None, "switched_at": None, "switched_at_human": "",
                    "changed": False, "changed_lines": 0, "no_state": True,
                    "guessed": None, "presets": [], "current_missing": False,
                    "guard": {"patterns": list(core.DEFAULT_GUARD), "source": "default",
                              "source_text": "", "running": False, "hits": [],
                              "total": 0},
                    "error": f"{type(e).__name__}: {e}"}

    def confirm_info(self, name, opts=None) -> dict:
        try:
            s = core.snapshot(self.p)
            current = s["current"]
            will_harvest = bool(current) and s["live_exists"] and s["changed"]
            return {"ok": True, "target": name, "current": current,
                    "changed": s["changed"], "changed_lines": s["changed_lines"],
                    "will_harvest": will_harvest, "no_state": not current}
        except Exception as e:                                  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}

    # ---- 只读操作（同步） ----
    def preset_form(self, name) -> dict:
        """编辑器初始值 + 宿主进程状态。"""
        try:
            f = core.read_preset_form(self.p, name)
        except core.CoreError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:                                  # noqa: BLE001
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            g = core.run_guard(self.p)
            f["guard_running"] = bool(g["running"])
            f["guard_hits"] = [h["name"] + (f" × {h['count']}" if h["count"] > 1 else "")
                               for h in g["hits"]]
        except Exception:                                       # noqa: BLE001
            f["guard_running"] = False
            f["guard_hits"] = []
        return f

    def preview_edit(self, name, form) -> dict:
        """不写盘：校验 + 改动预览。编辑器实时调用。"""
        try:
            return core.preview_edit(self.p, name, form or {})
        except Exception as e:                                  # noqa: BLE001
            return {"ok": False, "errors": {"_": f"{type(e).__name__}: {e}"}}

    def diff(self, name) -> dict:
        try:
            return core.run_diff(self.p, name)
        except core.CoreError as e:
            return {"error": str(e)}
        except Exception as e:                                  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}

    def history_list(self) -> dict:
        """历史路径不返回前端，仅返回短期一次性 opaque id。"""
        import hashlib
        try:
            rows = core.list_history(self.p)
            tokens = {}
            public = []
            now = time.monotonic()
            for row in rows:
                token = secrets.token_urlsafe(24)
                digest = hashlib.sha256(core.read_bytes(row["path"])).hexdigest()
                tokens[token] = (now, row["path"], row["size"], row["mtime_ns"], digest)
                public.append({k: row[k] for k in
                               ("source", "source_name", "preset", "time", "size")})
                public[-1]["id"] = token
            with self._lock:
                self._history_tokens = tokens
                self._restore_pending = None
            return {"ok": True, "items": public}
        except Exception:
            return {"ok": False, "error": "历史版本读取失败，请刷新后重试。"}

    def history_preview(self, token, target_type, target_name="") -> dict:
        import hashlib
        try:
            with self._lock:
                item = self._history_tokens.get(token)
                self._restore_pending = None
            if not item or time.monotonic() - item[0] > 300:
                return {"ok": False, "error": "历史版本选择已过期，请刷新列表。"}
            _created, path, size, mtime_ns, digest = item
            source = core.validate_history_file(self.p, path)
            st = source.stat()
            if st.st_size != size or st.st_mtime_ns != mtime_ns or hashlib.sha256(core.read_bytes(source)).hexdigest() != digest:
                return {"ok": False, "error": "历史版本已变化，请刷新列表。"}
            result = core.preview_history(self.p, source, target_type, target_name)
            confirm_token = secrets.token_urlsafe(24)
            with self._lock:
                self._restore_pending = (confirm_token, time.monotonic(), str(source),
                                         target_type, target_name, size, mtime_ns, digest)
            return dict(result, confirm_token=confirm_token)
        except core.CoreError as e:
            return {"ok": False, "error": str(e)}
        except Exception:
            return {"ok": False, "error": "无法预览该历史版本，请刷新后重试。"}

    def guard_info(self) -> dict:
        try:
            return core.run_guard(self.p)
        except Exception as e:                                  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}", "patterns": [], "hits": [],
                    "total": 0, "scanned": 0, "source_text": "", "running": False}

    def local_check(self, form):
        return connection.local_check(form or {})

    def _prepare_network(self, operation, form, secret=""):
        form = dict(form or {})
        check = connection.local_check(form, require_key=False, require_model=(operation == "model_call"))
        if not check.get("network_allowed"):
            return dict(check, ok=False)
        try:
            u, path = connection.models_target(form) if operation == "models" else connection.connection_target(form)
        except core.CoreError as exc:
            return {"ok": False, "message": str(exc)}
        try:
            bound_secret = connection._secret_for(form, secret)
        except core.CoreError as exc:
            return {"ok": False, "message": str(exc)}
        token = secrets.token_urlsafe(24)
        digest = userenv.fingerprint(bound_secret)
        with self._lock:
            self._network_pending[token] = (time.monotonic(), operation, u.netloc.lower(),
                                             str(form.get("model") or ""), str(form.get("wire_api") or ""),
                                             digest, form, bound_secret)
        target = u.scheme + "://" + u.netloc + path
        return {"ok": True, "token": token, "target": target,
                "host": u.netloc, "model": str(form.get("model") or ""),
                "wire_api": str(form.get("wire_api") or ""), "env_key": str(form.get("env_key") or ""),
                "message": "将向此目标发送一次请求，并使用该环境变量对应的 API Key；通常不会产生模型费用。不会发送配置内容。"
                           if operation == "models" else
                           "将向此第三方发送一次最小模型请求，可能产生少量费用；不会发送配置内容。"}

    def prepare_models(self, form, secret=""):
        return self._prepare_network("models", form, secret)

    def prepare_model_call(self, form, secret=""):
        return self._prepare_network("model_call", form, secret)

    def execute_network(self, token, confirmed=False):
        with self._lock:
            pending = self._network_pending.pop(token, None)
        if confirmed is not True or not pending or time.monotonic() - pending[0] > 120:
            return {"ok": False, "message": "网络确认已取消或过期，本次未联网。请重新操作。"}
        _created, operation, _host, _model, _wire, _digest, form, secret = pending
        try:
            return (connection.fetch_models(form, secret)
                    if operation == "models" else connection.test_model_call(form, secret))
        finally:
            secret = None
            pending = None

    def prepare_connection(self, form):
        with self._lock:
            self._connection_pending = None
            check = connection.local_check(form or {})
            if not check.get("network_allowed"):
                return dict(check, ok=False)
            u, path = connection.connection_target(form)
            token = secrets.token_urlsafe(24)
            self._connection_pending = (token, time.monotonic(), dict(form))
            return {"ok": True, "token": token, "target": u.scheme + "://" + u.netloc + path,
                    "model": form["model"], "env_key": form["env_key"],
                    "message": "将向此第三方发送密钥认证及固定文本 Reply OK.（最多请求 16 个输出 token）。可能产生费用，供应商会接收请求；不会发送配置文件、项目内容或官方登录凭据。请只信任你确认的地址。"}

    def preview_new(self, kind, name, form):
        try:
            name = core.validate_preset_name(name)
            if core.preset_path(self.p, name).exists():
                raise core.CoreError("该预设名已存在，请换一个名称。")
            text = core.new_preset_text(kind, form)
            return {"ok": True, "text": text}
        except core.CoreError as e:
            return {"ok": False, "error": str(e)}
        except Exception:
            return {"ok": False, "error": "字段格式不正确，请检查输入。"}

    # ---- 耗时操作（异步） ----
    def run(self, op, args=None, opts=None) -> dict:
        opts = dict(opts or {})
        if op == "save":
            # 同步前置校验，让「已存在 / 名字非法」直接显示在输入框旁
            try:
                name = core.validate_preset_name(args or "")
                if core.preset_path(self.p, name).exists():
                    return {"error": f"预设「{name}」已存在，未覆盖。"}
                if not self.p.live.exists():
                    return {"error": "正在使用的配置不存在，无法另存。"}
            except core.CoreError as e:
                return {"error": str(e)}
        elif op in ("edit", "save_form"):
            try:
                form = json.loads(opts.get("form_json") or "{}")
            except Exception:                                   # noqa: BLE001
                return {"error": "表单参数格式错误。"}
            if not isinstance(form, dict):
                return {"error": "表单参数格式错误。"}
            opts["form"] = form
        elif op == "copy":
            try:
                source = core.validate_preset_name(args or "")
                target = core.validate_preset_name(opts.get("new_name") or "")
                if not core.preset_path(self.p, source).exists():
                    return {"error": f"找不到预设「{source}」。"}
                if core.preset_path(self.p, target).exists():
                    return {"error": f"预设「{target}」已存在，未覆盖。"}
                opts["new_name"] = target
            except core.CoreError as e:
                return {"error": str(e)}
        elif op == "delete":
            try:
                name = core.validate_preset_name(args or "")
                if (opts.get("confirm_name") or "").strip() != name:
                    return {"error": "请输入完整配置名称以确认删除。"}
                if core.preset_is_current(self.p, name):
                    return {"error": "当前正在使用的配置不能删除。请先切换到其他配置。"}
            except core.CoreError as e:
                return {"error": str(e)}
        elif op == "restore":
            with self._lock:
                pending = self._restore_pending
                self._restore_pending = None
            if (opts.get("confirmed") is not True or not pending
                    or opts.get("token") != pending[0]
                    or time.monotonic() - pending[1] > 120):
                return {"error": "恢复确认已取消或过期，请重新预览。"}
            opts["restore"] = pending
        elif op == "switch" and not (args or "").strip():
            return {"error": "请先选择一个预设。"}
        with self._lock:
            if self._running:
                return {"error": "有操作正在执行，请稍候。"}
            if op == "connection":
                pending = self._connection_pending
                self._connection_pending = None
                if (opts.get("confirmed") is not True or not pending
                        or opts.get("token") != pending[0]
                        or time.monotonic() - pending[1] > 120):
                    return {"error": "确认已取消或过期，本次未联网。请重新点击连接测试并确认。"}
                opts = {"form": pending[2]}
            if op in ("models", "model_call"):
                token = opts.get("token")
                pending = self._network_pending.pop(token, None)
                if (opts.get("confirmed") is not True or not pending
                        or time.monotonic() - pending[0] > 120):
                    return {"error": "网络确认已取消或过期，本次未联网。请重新获取列表或确认模型调用。"}
                if pending[1] != op:
                    return {"error": "网络操作类型不匹配，本次未联网。"}
                opts = {"network": pending}
            if op == "save_form" and opts.get("activate") and opts.get("confirmed") is not True:
                return {"error": "启用前请确认将替换 Codex 正在使用的配置。"}
            value = opts.pop("api_key", "")
            if value and op not in ("edit", "save_form"):
                return {"error": "密钥只能随配置保存。"}
            if value and not opts.get("dry"):
                pending = self._key_pending
                self._key_pending = None
                form = opts.get("form", {})
                if (not pending or opts.get("key_token") != pending[0]
                        or time.monotonic() - pending[1] > 120
                        or form.get("env_key") != pending[2]
                        or userenv.fingerprint(value) != pending[3]
                        or (pending[5] and opts.get("key_confirmed") is not True)):
                    return {"error": "密钥保存确认已失效或未确认覆盖，请重新保存。"}
                if opts.get("create_kind") == "official" or not (form.get("model_provider") or form.get("edit_provider")):
                    return {"error": "官方配置不保存第三方密钥。"}
                opts["_key_value"] = value
                opts["_key_expected"] = pending[4]
            self._running = True
            self._result = None
            self._op = op
            rep = core.Reporter()
            self._lines = rep.lines
        t = threading.Thread(target=self._worker, args=(op, args, opts, rep), daemon=True)
        t.start()
        return {"started": True}

    def _save_with_key(self, op, name, opts, rep):
        value = opts.pop("_key_value")
        expected = opts.pop("_key_expected")
        paths = {self.p.live, self.p.state, *self.p.lib.glob("*.toml")}
        target = core.validate_preset_name(opts["form"].get("new_name") or name)
        paths.add(core.preset_path(self.p, target))
        before = {p: p.read_bytes() if p.exists() else None for p in paths}
        private = core.Reporter()
        def action():
            if op == "save_form":
                return core.run_save_form(self.p, name, opts["form"],
                    create_kind=opts.get("create_kind", ""),
                    activate=bool(opts.get("activate")), rep=private)
            return core.run_edit(self.p, name, opts["form"],
                                 force=bool(opts.get("force")), rep=private)
        try:
            result = userenv.save(opts["form"]["env_key"], value, expected, action)
        except Exception as exc:
            restored = True
            for path, data in before.items():
                try:
                    if data is None:
                        if path.exists():
                            path.unlink()
                    elif not path.exists() or path.read_bytes() != data:
                        core.atomic_write_bytes(path, data)
                except Exception:
                    restored = False
            message = str(exc) if isinstance(exc, userenv.EnvironmentError) else "密钥保存失败，未返回错误细节。"
            rep.err(message)
            if not restored:
                rep.err("部分配置回滚失败，请核对历史备份后再操作。")
            return {"ok": False, "saved": False, "lines": rep.lines}
        finally:
            value = None
        rep.ok("用户环境变量已保存（非加密存储），当前进程已更新并通知环境变化。请重启 Codex；若仍取不到密钥，请重启启动它的终端或宿主。")
        if not result.get("ok"):
            rep.warn("预设和密钥已保存，但尚未启用。请退出 Codex 后再次切换。")
        return {k: v for k, v in dict(result, lines=rep.lines, key_saved=True).items()
                if k in ("ok", "saved", "activated", "blocked", "new_name", "lines", "key_saved")}

    def _worker(self, op, args, opts, rep: core.Reporter) -> None:
        try:
            if opts.get("_key_value"):
                res = self._save_with_key(op, args, opts, rep)
            elif op == "connection":
                res = connection.test_connection(opts["form"], confirmed=True)
                rep("ok" if res["ok"] else "err", res["message"])
            elif op in ("models", "model_call"):
                pending = opts["network"]
                _created, _kind, _host, _model, _wire, _digest, form, secret = pending
                try:
                    res = (connection.fetch_models(form, secret)
                           if op == "models" else connection.test_model_call(form, secret))
                finally:
                    secret = None
                    pending = None
                rep("ok" if res.get("ok") else "err", res.get("message", "网络操作未完成。"))
            elif op == "save_form":
                res = core.run_save_form(self.p, args, opts["form"],
                                         create_kind=opts.get("create_kind", ""),
                                         activate=bool(opts.get("activate")), rep=rep)
            elif op == "switch":
                res = core.run_switch(
                    self.p, args,
                    no_harvest=bool(opts.get("no_harvest")),
                    force=bool(opts.get("force")),
                    dry=bool(opts.get("dry")),
                    rep=rep)
            elif op == "harvest":
                res = core.run_harvest_only(
                    self.p, force=bool(opts.get("force")),
                    dry=bool(opts.get("dry")), rep=rep)
            elif op == "save":
                res = core.run_save_as(
                    self.p, args, set_current=bool(opts.get("set_current")), rep=rep)
            elif op == "edit":
                res = core.run_edit(
                    self.p, args, opts.get("form") or {},
                    force=bool(opts.get("force")), dry=bool(opts.get("dry")), rep=rep)
            elif op == "copy":
                res = core.run_copy_preset(self.p, args, opts["new_name"], rep=rep)
            elif op == "delete":
                res = core.run_delete_preset(self.p, args, rep=rep)
            elif op == "restore":
                pending = opts["restore"]
                res = core.run_restore_history(
                    self.p, pending[2], pending[3], pending[4],
                    expected_size=pending[5], expected_mtime_ns=pending[6],
                    expected_sha256=pending[7], rep=rep)
            else:
                rep.err(f"[×] 未知操作：{op}")
                res = {"ok": False, "lines": rep.lines}
        except Exception as e:                                  # noqa: BLE001
            rep.err(f"[×] 未预期的错误：{type(e).__name__}: {e}")
            res = {"ok": False, "lines": rep.lines}
        with self._lock:
            self._result = res
            self._running = False

    def poll(self) -> dict:
        with self._lock:
            return {"running": self._running, "lines": list(self._lines),
                    "result": self._result, "op": self._op}


def show_error_dialog(title: str, text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:
        pass


def run_gui(paths: core.Paths, initial: str | None = None,
            path_context: dict | None = None,
            settings_file: str | os.PathLike | None = None) -> int:
    try:
        import webview
    except Exception as e:                                      # noqa: BLE001
        show_error_dialog(APP_NAME, f"界面组件加载失败：{type(e).__name__}: {e}")
        return 2

    api = Api(paths, initial=initial, path_context=path_context,
              settings_file=settings_file)
    html = ui.HTML
    try:
        data = base64.b64encode(open(resource_path(UI_ICON_NAME), "rb").read()).decode("ascii")
        html = html.replace('src="codex-icon.png"', f'src="data:image/png;base64,{data}"')
    except Exception:
        pass
    window = webview.create_window(
        APP_NAME,
        html=html,
        js_api=api,
        width=980,
        height=720,
        min_size=(780, 560),
        text_select=True,
        confirm_close=False,
    )
    api._window = window
    kwargs = {}
    icon = resource_path(ICON_NAME)
    if os.path.exists(icon):
        kwargs["icon"] = icon
    try:
        webview.start(**kwargs)
    except Exception as e:                                      # noqa: BLE001
        show_error_dialog(APP_NAME, f"界面启动失败：{type(e).__name__}: {e}")
        return 2
    return 0


# --------------------------------------------------------------------------
# 无界面通道
# --------------------------------------------------------------------------

HELP = f"""{APP_NAME} v{core.VERSION}

用法：
  带界面：        CodexConfigManager.exe                （双击图标即可）
  无界面通道：    CodexConfigManager.exe <命令> [参数]

命令：
  list              列出全部预设 + 当前标记 + 未同步变化提示
  use <名>          检测 + 同步 + 切换到指定预设
  edit <名>         带界面打开该预设的配置编辑器
  info <名>         打印该预设的大模型相关字段（模型 / URL / 密钥变量…）
  set <名> <字段> <值>
                    改单个字段（直接落盘，走与界面相同的流程）
  harvest           只同步正在使用的配置到当前预设（不切换）
  save <名>         把正在使用的配置另存为新预设
  diff <名>         对比正在使用的配置与指定预设
  show <名>         打印预设内容
  guard             只做进程检测并打印结果（诊断用）
  menu              交互菜单

set 的字段名（中英文均可）：
  model|模型      模型 ID           provider|供应商     供应商 ID
  url|地址        Base URL          env_key|密钥       API Key 环境变量名
  wire_api|协议   接口协议          name|显示名称      供应商显示名称
  reasoning|推理  推理强度          rename|预设名      重命名该预设

选项：
  --no-harvest      切换时跳过同步（仍会保底备份正在使用的配置）
  -n, --dry-run     只演练不写入
  -f, --force       跳过运行中检查
  -h, --help        显示本帮助
  -V, --version     显示版本

环境变量：
  CODEX_HOME        覆盖配置根目录（默认 %USERPROFILE%\\.codex）
"""


def _print_lines(lines) -> None:
    for l in lines:
        _out(l["text"])


def cmd_header(p: core.Paths) -> None:
    current, switched = core.read_state(p)
    changed, n = core.live_vs_preset(p, current) if current else (False, 0)
    pats, src = core.guard_list(p)
    hits = core.match_processes(pats)
    _out(APP_NAME)
    _out(f"  预设库  {p.lib}")
    _out(f"  正在使用的    {p.live}")
    _out("  当前预设 " + (current or "(未记录)")
         + (f"        (上次切换 {core.human_time(switched)})" if switched else ""))
    _out("  进程检查 " + ("拦截（宿主应用运行中，共 %d 个进程）" % len(hits) if hits
                        else "通过（宿主应用未运行）"))
    if src != "file":
        _out(f"  [i] {core.guard_source_text(p, src)}")
    if current and changed:
        _out(f"  [!] 正在使用的配置有未同步的变化（约 {n} 行），切换前会自动同步回 {current}")
    elif current_missing_note(p, current):
        _out(f"  [!] 状态记录指向的预设「{current}」已不存在，将按无状态处理。")
    elif not current:
        _out("  [!] 未找到「当前预设」记录")


def current_missing_note(p: core.Paths, current) -> bool:
    return bool(current) and not core.preset_path(p, current).exists()


def cmd_list(p: core.Paths) -> int:
    cmd_header(p)
    presets = core.list_presets(p)
    current, _ = core.read_state(p)
    _out("")
    if not presets:
        _out("  （预设库为空，可用 save <名> 把正在使用的配置存为第一个预设）")
        return 0
    w = max(len(x["name"]) for x in presets) + 1
    for i, x in enumerate(presets, 1):
        mark = "  <- 当前" if x["name"] == current else ""
        _out(f"  {i:>2}) {x['name']:<{w}} model={core.model_label(x['model']):<18}"
             f" provider={core.provider_label(x['provider'])}{mark}")
    return 0


def cmd_use(p: core.Paths, name: str, opts: dict) -> int:
    rep = core.Reporter()
    res = core.run_switch(p, name, no_harvest=opts["no_harvest"],
                          force=opts["force"], dry=opts["dry"], rep=rep)
    _print_lines(rep.lines)
    return 0 if res["ok"] else 1


def cmd_harvest(p: core.Paths, opts: dict) -> int:
    rep = core.Reporter()
    res = core.run_harvest_only(p, force=opts["force"], dry=opts["dry"], rep=rep)
    _print_lines(rep.lines)
    return 0 if res["ok"] else 1


def cmd_save(p: core.Paths, name: str, opts: dict) -> int:
    rep = core.Reporter()
    res = core.run_save_as(p, name, set_current=opts.get("set_current", False), rep=rep)
    _print_lines(rep.lines)
    return 0 if res["ok"] else 1


def cmd_diff(p: core.Paths, name: str) -> int:
    try:
        d = core.run_diff(p, name)
    except core.CoreError as e:
        _out(f"[×] {e}")
        return 1
    if d["same"]:
        _out(f"正在使用的配置与预设「{name}」完全一致，无差异。")
        return 0
    _out(f"差异：正在使用的配置（+） vs 预设 {name}（-）   改动 {d['changed']} 行")
    _out("-" * 68)
    for r in d["rows"]:
        mark = "+ " if r["kind"] == "add" else ("- " if r["kind"] == "del" else "  ")
        if r["kind"] == "gap":
            _out("  ...")
        else:
            _out(mark + r["text"])
    return 0


def cmd_show(p: core.Paths, name: str) -> int:
    f = core.preset_path(p, name)
    if not f.exists():
        _out(f"[×] 找不到预设「{name}」：{f}")
        return 1
    _out(core.read_text(f).rstrip("\n"))
    return 0


def cmd_info(p: core.Paths, name: str) -> int:
    """打印预设的大模型相关字段（只读）。"""
    try:
        f = core.read_preset_form(p, name)
    except core.CoreError as e:
        _out(f"[×] {e}")
        return 1
    except Exception as e:                                      # noqa: BLE001
        _out(f"[×] 读取失败：{type(e).__name__}: {e}")
        return 1
    _out(f"预设 {f['preset']}"
         + ("   [正在使用中]" if f["is_current"] else "   [未在使用]"))
    _out(f"  文件        {f['path']}")
    _out(f"  模型 ID     {f['model'] or '(默认)'}")
    _out(f"  供应商 ID   {f['model_provider'] or '(未设置)'}")
    _out(f"  推理强度    {f['reasoning'] or '(未设置)'}")
    _out(f"  供应商块    {', '.join(f['providers']) or '(无)'}")
    _out(f"  显示名称    {f['prov_name'] or '(未设置)'}")
    _out(f"  Base URL    {f['base_url'] or '(未设置)'}")
    ek = f["env_key"] or "(未设置)"
    if f["env_key"]:
        ek += "   " + ("已设置" if f["env_set"] else "未设置（宿主可能拿不到密钥）")
    _out(f"  密钥变量    {ek}")
    _out(f"  接口协议    {f['wire_api'] or '(未设置)'}")
    return 0


# 字段别名：命令行里写哪个都认
KEY_ALIASES = {
    "model": "model", "模型": "model", "模型id": "model",
    "provider": "model_provider", "model_provider": "model_provider", "供应商": "model_provider",
    "reasoning": "reasoning", "effort": "reasoning", "推理": "reasoning", "推理强度": "reasoning",
    "name": "prov_name", "prov_name": "prov_name", "显示名称": "prov_name",
    "url": "base_url", "base_url": "base_url", "地址": "base_url",
    "env_key": "env_key", "key": "env_key", "密钥": "env_key", "密钥变量": "env_key",
    "wire_api": "wire_api", "协议": "wire_api", "接口协议": "wire_api",
    "rename": "new_name", "预设名": "new_name",
}
SET_FIELDS = ("model", "model_provider", "reasoning",
              "prov_name", "base_url", "env_key", "wire_api")


def cmd_set(p: core.Paths, name: str, key: str, value: str, opts: dict) -> int:
    """改单个字段（脚本友好）。走的是与界面完全相同的 run_edit。"""
    k = KEY_ALIASES.get((key or "").strip().lower())
    if not k:
        _out(f"[×] 不认识的字段：{key}")
        _out("    可用字段：" + " / ".join(sorted(set(KEY_ALIASES))))
        return 2
    try:
        cur = core.read_preset_form(p, name)
    except core.CoreError as e:
        _out(f"[×] {e}")
        return 1

    form = {f: (cur.get(f) or "") for f in SET_FIELDS}
    form["preset"] = name
    form["new_name"] = value if k == "new_name" else name
    # 供应商块字段写到「文件里已有的那个块」——官方预设没有 model_provider，
    # 若按 model_provider 走，url/env_key 这类改动会被静默丢掉。
    form["edit_provider"] = cur.get("orig_provider_id") or ""
    if k != "new_name":
        form[k] = value

    rep = core.Reporter()
    res = core.run_edit(p, name, form, force=opts["force"], dry=opts["dry"], rep=rep)
    _print_lines(rep.lines)
    return 0 if res["ok"] else 1


def cmd_edit_gui(p: core.Paths, name: str) -> int:
    """带界面打开指定预设的编辑器。"""
    try:
        name = core.validate_preset_name(name)
    except core.CoreError as e:
        init_console()
        _out(f"[×] {e}")
        return 2
    if not core.preset_path(p, name).exists():
        init_console()
        _out(f"[×] 找不到预设「{name}」：{core.preset_path(p, name)}")
        return 1
    env_controlled = bool((os.environ.get("CODEX_HOME") or "").strip())
    source = "environment" if env_controlled else "default"
    context = {"source": source, "configs_source": source,
               "env_controlled": env_controlled,
               "settings": {"status": "disabled", "settings": None}}
    return run_gui(p, initial=name, path_context=context)


def cmd_guard(p: core.Paths) -> int:
    g = core.run_guard(p)
    _out(f"名单来源：{g['source_text']}")
    _out(f"名单模式：{', '.join(g['patterns'])}")
    _out(f"已扫描进程：{g['scanned']} 个")
    _out("")
    if not g["running"]:
        _out("[OK] 未检测到宿主应用进程。")
        return 0
    _out(f"[!] 检测到 {g['total']} 个宿主相关进程：")
    _out("")
    lines = ["    %-30s %-8s %s" % ("进程名", "PID", "可执行文件")]
    for h in g["hits"]:
        label = h["name"] + (f" × {h['count']}" if h["count"] > 1 else "")
        pidtxt = ", ".join(str(x) for x in h["pids"][:4]) + (" …" if len(h["pids"]) > 4 else "")
        paths = h["paths"] or ["(路径不可读)"]
        lines.append("    %-30s %-8s %s" % (label, pidtxt, paths[0]))
        for extra in paths[1:]:
            lines.append("    %-30s %-8s %s" % ("", "", extra))
    _out("\n".join(lines))
    _out("")
    _out(f"    若认为误伤，可编辑名单文件：{p.guard}")
    return 1


def cmd_menu(p: core.Paths) -> int:
    while True:
        _out("=" * 68)
        cmd_list(p)
        presets = core.list_presets(p)
        current, _ = core.read_state(p)
        _out("")
        try:
            raw = input("输入编号切换，s <名字> 另存为新预设，h 只同步不切换，"
                        "d <名字> 看差异，i <名字> 看字段，"
                        "k <名字> <字段> <值> 改字段，回车取消: ").strip()
        except (EOFError, KeyboardInterrupt):
            _out("")
            return 0
        if not raw:
            return 0
        low = raw.lower()
        if low in ("h", "harvest"):
            cmd_harvest(p, {"force": False, "dry": False})
            continue
        if low.startswith("s ") or low.startswith("save "):
            name = raw.split(None, 1)[1].strip()
            cmd_save(p, name, {"set_current": True})
            continue
        if low.startswith("d ") or low.startswith("diff "):
            name = raw.split(None, 1)[1].strip()
            cmd_diff(p, name)
            continue
        if low.startswith("i ") or low.startswith("info "):
            name = raw.split(None, 1)[1].strip()
            cmd_info(p, name)
            continue
        if low.startswith("k ") or low.startswith("set "):
            parts = raw.split(None, 3)
            if len(parts) < 4:
                _out("[×] 用法：k <预设名> <字段> <值>")
                continue
            cmd_set(p, parts[1], parts[2], parts[3],
                    {"force": False, "dry": False})
            continue
        if raw.isdigit():
            i = int(raw)
            if 1 <= i <= len(presets):
                cmd_use(p, presets[i - 1]["name"],
                        {"no_harvest": False, "force": False, "dry": False})
                return 0
            _out(f"[×] 编号超出范围（1~{len(presets)}）")
            continue
        _out("[×] 无法识别的输入。")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

FLAG_ALIASES = {
    "--dry-run": "dry", "-n": "dry",
    "--force": "force", "-f": "force",
    "--no-harvest": "no_harvest",
    "--gui": "gui",
    "--json": "json",
    "--set-current": "set_current",
}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    opts = {"dry": False, "force": False, "no_harvest": False,
            "gui": False, "json": False, "set_current": False}
    positional: list[str] = []
    for a in args:
        key = FLAG_ALIASES.get(a)
        if key:
            opts[key] = True
        elif a in ("-h", "--help"):
            init_console()
            _out(HELP)
            return 0
        elif a in ("-V", "--version"):
            init_console()
            _out(f"{APP_NAME} v{core.VERSION}")
            return 0
        elif a.startswith("-") and a != "-":
            init_console()
            _out(f"[×] 未知选项：{a}\n")
            _out(HELP)
            return 2
        else:
            positional.append(a)

    gui_mode = opts["gui"] or not positional
    if gui_mode:
        paths, path_context = core.Paths.for_gui()
        return run_gui(paths, path_context=path_context)

    paths = core.Paths()
    init_console()
    cmd = positional[0].lower()
    rest = positional[1:]

    try:
        core.ensure_layout(paths)
    except OSError as e:
        _out(f"[×] 无法创建预设库目录：{paths.lib}（{e}）")
        return 2

    if cmd in ("list", "ls"):
        return cmd_list(paths)
    if cmd in ("menu", "m"):
        return cmd_menu(paths)
    if cmd in ("use", "switch"):
        if not rest:
            _out("[×] 用法：use <预设名>")
            return 2
        return cmd_use(paths, rest[0], opts)
    if cmd == "harvest":
        return cmd_harvest(paths, opts)
    if cmd == "save":
        if not rest:
            _out("[×] 用法：save <预设名>")
            return 2
        return cmd_save(paths, rest[0], opts)
    if cmd == "diff":
        if not rest:
            _out("[×] 用法：diff <预设名>")
            return 2
        return cmd_diff(paths, rest[0])
    if cmd == "show":
        if not rest:
            _out("[×] 用法：show <预设名>")
            return 2
        return cmd_show(paths, rest[0])
    if cmd == "info":
        if not rest:
            _out("[×] 用法：info <预设名>")
            return 2
        return cmd_info(paths, rest[0])
    if cmd == "edit":
        if not rest:
            _out("[×] 用法：edit <预设名>")
            return 2
        return cmd_edit_gui(paths, rest[0])
    if cmd == "set":
        if len(rest) < 3:
            _out("[×] 用法：set <预设名> <字段> <值>")
            _out("    例：set aibank url https://new.example/v1")
            _out("    例：set aibank model gpt-5.6-luna")
            _out("    例：set aibank rename aibank-pro")
            return 2
        return cmd_set(paths, rest[0], rest[1], " ".join(rest[2:]), opts)
    if cmd == "guard":
        return cmd_guard(paths)

    _out(f"[×] 未知命令：{cmd}\n")
    _out(HELP)
    return 2


if __name__ == "__main__":
    sys.exit(main())
