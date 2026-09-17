"""第三方 OpenAI 兼容服务的安全网络操作。

网络操作只接受显式确认后的调用；本模块不写配置、不保存密钥、不返回完整响应。
"""
from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import time
from urllib.parse import urlsplit

from core import CoreError, VERSION, validate_llm_form

TIMEOUT = 12
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_MODELS = 200
MAX_MODEL_ID = 256
MAX_ERROR_TEXT = 240
# 版本号只在 core.VERSION 维护一处，避免发版时漏改这里
USER_AGENT = f"CodexConfigManager/{VERSION} (network test)"


def _is_local_host(hostname: str) -> bool:
    return hostname.lower().rstrip(".") in {"localhost", "127.0.0.1"}


def validate_endpoint(url):
    try:
        raw = str(url or "").strip()
        u = urlsplit(raw)
        local_http = u.scheme == "http" and u.hostname and _is_local_host(u.hostname)
        if ((u.scheme != "https" and not local_http) or not u.hostname
                or u.username is not None or u.password is not None
                or u.query or u.fragment
                or re.search(r"[\s\\\x00-\x1f\x7f]", raw)
                or len(raw) > 2048):
            raise ValueError()
        port = u.port or (80 if u.scheme == "http" else 443)
        if not 1 <= port <= 65535:
            raise ValueError()
        u.hostname.encode("idna")
        return u
    except (ValueError, UnicodeError):
        raise CoreError("Base URL 必须是完整 HTTPS 地址；仅允许 localhost/127.0.0.1 使用 HTTP。不得包含账号、密码、查询参数、片段或空白。请勿在地址中粘贴密钥。") from None


def _join_path(base_path: str, suffix: str) -> str:
    base = "/" + (base_path or "").strip("/") if base_path else ""
    suffix = "/" + suffix.strip("/")
    if base.lower().endswith(suffix.lower()):
        return base or suffix
    return (base + suffix) or "/"


def models_target(form):
    u = validate_endpoint(str(form.get("base_url") or "").strip())
    return u, _join_path(u.path, "models")


def connection_target(form):
    u = validate_endpoint(str(form.get("base_url") or "").strip())
    suffix = "responses" if form.get("wire_api") == "responses" else "chat/completions"
    return u, _join_path(u.path, suffix)


def _target_text(u, path):
    return f"{u.scheme}://{u.netloc}{path}"


def local_check(form, *, require_key=True, require_model=False):
    errors = validate_llm_form(form)
    third = bool(str(form.get("model_provider") or "").strip())
    if not third:
        return {"ok": not errors, "errors": errors, "network_allowed": False,
                "message": "仅完成本地格式检查，未联网。官方配置请在 Codex 中登录后验证；此处不读取官方登录凭据。"}
    for k, label in (("model", "模型 ID"), ("base_url", "Base URL"),
                     ("env_key", "API Key 环境变量名"), ("wire_api", "接口协议")):
        if k == "model" and not require_model:
            continue
        if not str(form.get(k) or "").strip():
            errors[k] = f"请填写{label}。"
    try:
        validate_endpoint(str(form.get("base_url") or "").strip())
    except CoreError as e:
        errors["base_url"] = str(e)
    ek = str(form.get("env_key") or "").strip()
    env_set = bool(ek and os.environ.get(ek))
    if require_key and ek and not env_set:
        errors["env_key"] = "本程序未读取到该环境变量。也可以在本次操作中临时输入 API Key；它不会保存。"
    return {"ok": not errors, "errors": errors, "env_set": env_set,
            "network_allowed": not errors,
            "message": "本地检查通过，未发送任何请求；这不代表账号、额度或模型可用。" if not errors
                       else "本地检查未通过，未联网。请按字段提示修正。"}


def _secret_for(form, secret):
    key = secret if isinstance(secret, str) and secret else os.environ.get(str(form.get("env_key") or "").strip(), "")
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise CoreError("API Key 为空或包含不支持的字符。请检查环境变量，或在本次操作中重新输入。")
    return key


def _scrub(text, secret=""):
    value = str(text or "")
    if secret:
        value = value.replace(secret, "[已隐藏]")
    value = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[已隐藏]", value)
    value = re.sub(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+", r"\1=[已隐藏]", value)
    return value[:MAX_ERROR_TEXT]


def _read_limited(response):
    length = response.getheader("Content-Length")
    try:
        if length is not None and int(length) > MAX_RESPONSE_BYTES:
            raise CoreError("服务端响应过大，已停止读取。")
    except ValueError:
        pass
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise CoreError("服务端响应过大，已停止读取。")
    return data


def _open(u):
    context = ssl.create_default_context()
    cls = http.client.HTTPConnection if u.scheme == "http" else http.client.HTTPSConnection
    return cls(u.hostname, u.port or (80 if u.scheme == "http" else 443),
               timeout=TIMEOUT, context=context) if cls is http.client.HTTPSConnection else cls(
                   u.hostname, u.port or 80, timeout=TIMEOUT)


def _request(form, secret, method, path, body=None):
    u = validate_endpoint(str(form.get("base_url") or "").strip())
    key = _secret_for(form, secret)
    conn = None
    started = time.monotonic()
    try:
        conn = _open(u)
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json",
                   "User-Agent": USER_AGENT}
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        status = response.status
        raw = _read_limited(response)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if 300 <= status < 400:
            return {"status": status, "raw": b"", "elapsed_ms": elapsed_ms,
                    "error": "服务端要求跳转，已停止；不会向跳转地址发送密钥。"}
        return {"status": status, "raw": raw, "elapsed_ms": elapsed_ms}
    except (ssl.SSLError, ssl.CertificateError):
        raise CoreError("TLS 证书验证失败，已停止；不会关闭证书验证。") from None
    except TimeoutError:
        raise CoreError(f"连接或响应等待超时（{TIMEOUT} 秒），未自动重试。服务端可能已计费。") from None
    except CoreError:
        raise
    except Exception as exc:
        raise CoreError("连接失败，详细错误已隐藏以保护 API Key；未自动重试。") from None
    finally:
        key = ""
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _json_body(raw, secret):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise CoreError("服务端返回的不是合法 JSON，未展示正文。") from None


def _error_message(status, raw, secret):
    if status in (401, 403):
        return "认证或权限不足。请检查 API Key 与访问权限。"
    if status == 429:
        return "请求被限流或额度不足，请检查供应商额度后再手动重试。"
    text = ""
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    text = err.get("message", "")
                elif isinstance(err, str):
                    text = err
                if not text:
                    text = data.get("message", "")
        except Exception:
            pass
    text = _scrub(text, secret)
    return f"服务端未接受请求（HTTP {status}）。" + (f"提示：{text}" if text else "请核对地址、模型和协议。")


def _valid_model_id(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= MAX_MODEL_ID \
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _extract_models(data):
    if not isinstance(data, dict):
        raise CoreError("模型列表格式不受支持，未展示服务端正文。")
    values = data.get("data") if "data" in data else data.get("models")
    if not isinstance(values, list) or len(values) > MAX_MODELS:
        raise CoreError("模型列表格式不受支持或数量过多。")
    out = []
    seen = set()
    for item in values:
        if isinstance(item, dict):
            if any(isinstance(v, (dict, list)) for k, v in item.items() if k != "id"):
                raise CoreError("模型列表包含不安全的嵌套数据，已停止。")
            value = item.get("id")
        elif "models" in data and isinstance(item, str):
            value = item
        else:
            raise CoreError("模型列表条目缺少合法 id，已停止。")
        if not _valid_model_id(value):
            raise CoreError("模型列表包含过长或非法的模型 ID，已停止。")
        value = value.strip()
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def fetch_models(form, secret=""):
    check = local_check(form, require_key=False, require_model=False)
    if not check["network_allowed"]:
        return {"ok": False, "message": check["message"], "errors": check["errors"]}
    try:
        u, path = models_target(form)
        result = _request(form, secret, "GET", path)
        status, elapsed = result["status"], result["elapsed_ms"]
        if result.get("error"):
            return {"ok": False, "status": status, "elapsed_ms": elapsed, "message": result["error"]}
        if not 200 <= status < 300:
            return {"ok": False, "status": status, "elapsed_ms": elapsed,
                    "message": _error_message(status, result["raw"], secret)}
        models = _extract_models(_json_body(result["raw"], secret))
        return {"ok": True, "status": status, "elapsed_ms": elapsed, "models": models,
                "message": (f"已获取 {len(models)} 个模型；这不等于模型调用一定成功。" if models
                            else "服务端返回了空模型列表。请确认供应商地址和权限。")}
    except CoreError as exc:
        return {"ok": False, "message": _scrub(exc, secret)}
    except Exception:
        return {"ok": False, "message": "获取模型列表失败，详细错误已隐藏。"}


def _reasonable_output(data):
    if not isinstance(data, dict):
        return False
    if _valid_model_id(data.get("id")):
        return True
    output = data.get("output")
    if isinstance(output, list) and output and all(isinstance(x, dict) for x in output[:20]):
        return True
    choices = data.get("choices")
    if isinstance(choices, list) and choices and all(isinstance(x, dict) for x in choices[:20]):
        return True
    return False


def test_model_call(form, secret=""):
    check = local_check(form, require_key=False, require_model=True)
    if not check["network_allowed"]:
        return {"ok": False, "message": check["message"], "errors": check["errors"]}
    model = str(form.get("model") or "").strip()
    try:
        u, path = connection_target(form)
        if form.get("wire_api") == "responses":
            body = {"model": model, "input": "Reply OK.", "max_output_tokens": 16, "store": False}
        else:
            body = {"model": model, "messages": [{"role": "user", "content": "Reply OK."}],
                    "max_tokens": 16, "stream": False}
        result = _request(form, secret, "POST", path, body)
        status, elapsed = result["status"], result["elapsed_ms"]
        if result.get("error"):
            return {"ok": False, "status": status, "elapsed_ms": elapsed, "protocol": form["wire_api"],
                    "message": result["error"]}
        if not 200 <= status < 300:
            return {"ok": False, "status": status, "elapsed_ms": elapsed, "protocol": form["wire_api"],
                    "message": _error_message(status, result["raw"], secret)}
        data = _json_body(result["raw"], secret)
        if not _reasonable_output(data):
            return {"ok": False, "status": status, "elapsed_ms": elapsed, "protocol": form["wire_api"],
                    "message": "服务端返回成功状态，但响应结构不像有效模型结果；不能确认调用成功。"}
        return {"ok": True, "status": status, "elapsed_ms": elapsed, "protocol": form["wire_api"],
                "message": "本次测试成功：服务端返回了合理的模型响应；这不代表之后每次调用都可用。"}
    except CoreError as exc:
        return {"ok": False, "protocol": form.get("wire_api", ""), "message": _scrub(exc, secret)}
    except Exception:
        return {"ok": False, "protocol": form.get("wire_api", ""), "message": "模型调用测试失败，详细错误已隐藏。"}


def test_connection(form, *, confirmed=False):
    """兼容旧 API：只确认第三方连接并发送最小请求，不读取完整响应。"""
    if confirmed is not True:
        return {"ok": False, "message": "未确认发送，本次未联网。"}
    check = local_check(form)
    if not check["network_allowed"]:
        return {"ok": False, "message": check["message"]}
    try:
        key = _secret_for(form, "")
        u, path = connection_target(form)
        body = {"model": form["model"].strip(), "stream": False}
        if form["wire_api"] == "responses":
            body.update(input="Reply OK.", max_output_tokens=16, store=False)
        else:
            body.update(messages=[{"role": "user", "content": "Reply OK."}], max_tokens=16)
        conn = _open(u)
        conn.request("POST", path, body=json.dumps(body).encode("utf-8"), headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": USER_AGENT})
        response = conn.getresponse()
        status = response.status
        if 200 <= status < 300:
            msg = "服务端已接受测试请求（HTTP 成功），可能产生费用；未检查生成内容，不保证 Codex 全部功能兼容。"
        elif 300 <= status < 400:
            msg = "服务端要求跳转，已停止，不会向跳转地址发送密钥。请核对最终 HTTPS 地址后重新确认测试。"
        else:
            msg = _error_message(status, b"", key)
        return {"ok": 200 <= status < 300, "status": status, "message": msg}
    except CoreError as e:
        return {"ok": False, "message": _scrub(e)}
    except TimeoutError:
        return {"ok": False, "message": "连接或响应等待超时（12 秒），未自动重试。服务端可能已计费。"}
    except (ssl.SSLError, ssl.CertificateError):
        return {"ok": False, "message": "TLS 证书验证失败，已停止；不会关闭证书验证。"}
    except Exception:
        return {"ok": False, "message": "连接失败，详细错误已隐藏以保护 API Key。"}
    finally:
        key = ""
        try:
            conn.close()
        except Exception:
            pass
