# -*- coding: utf-8 -*-
"""用户密钥仅写 HKCU\\Environment；不向调用方返回值或原始异常。"""
import ctypes
import hashlib
import os
import re
import winreg


class EnvironmentError(Exception):
    pass


def suggest_name(provider, name):
    source = (provider or name or "codex").strip()
    stem = re.sub(r"[^A-Z0-9_]+", "_", source.upper()).strip("_")
    if not stem:
        stem = "CODEX_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12].upper()
    if stem[0].isdigit():
        stem = "CODEX_" + stem
    return stem[:100] + ("" if stem.endswith("_API_KEY") else "_API_KEY")


def read_value(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            try:
                return winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return None
    except FileNotFoundError:
        return None
    except Exception:
        raise EnvironmentError("无法读取用户环境变量；未保存任何密钥。") from None


def fingerprint(value):
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def validate(name, value):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise EnvironmentError("API Key 环境变量名不合法。")
    if not isinstance(value, str) or any(c in value for c in "\0\r\n") or len(value) > 32760:
        raise EnvironmentError("API Key 格式不正确；不允许换行或空字符。")


def write_value(name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_SET_VALUE) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, name, 0, value[1], value[0])


def broadcast():
    from ctypes import wintypes
    send = ctypes.windll.user32.SendMessageTimeoutW
    send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                     wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT,
                     ctypes.POINTER(ctypes.c_size_t)]
    send.restype = wintypes.LPARAM
    result = ctypes.c_size_t()
    if not send(0xffff, 0x001A, 0, "Environment", 0x0002, 2000, ctypes.byref(result)):
        raise EnvironmentError("环境变化通知未完成。")


def save(name, value, expected, action):
    """注册表失败不执行配置写入；配置失败还原注册表及当前进程环境。"""
    validate(name, value)
    old = read_value(name)
    if fingerprint(old) != expected:
        raise EnvironmentError("用户环境变量已被其他操作修改，请重新保存并确认。")
    previous = os.environ.get(name)
    changed = old != (value, winreg.REG_SZ)
    touched = False
    try:
        if changed:
            touched = True
            write_value(name, (value, winreg.REG_SZ))
        os.environ[name] = value
        broadcast()
        result = action()
        if not result.get("ok") and not result.get("saved"):
            raise EnvironmentError("配置保存失败。")
    except Exception:
        rollback_ok = True
        try:
            if touched:
                write_value(name, old)
        except Exception:
            rollback_ok = False
        try:
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        except Exception:
            rollback_ok = False
        try:
            broadcast()
        except Exception:
            pass
        message = ("保存未完成，密钥和当前进程环境已回滚；请检查权限后重试。" if rollback_ok else
                   "保存未完成，密钥回滚失败；请在 Windows 用户环境变量中核对，勿直接重试。")
        raise EnvironmentError(message) from None
    return result
