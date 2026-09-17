# -*- coding: utf-8 -*-
"""
Codex 配置管理器 —— 核心层

设计约束：
  * 不 import 任何界面库，GUI 与无界面通道共用这一份实现。
  * 不硬编码用户名 / 绝对安装路径，一律运行时解析（需求 §7.9）。
  * 不使用符号链接 / 硬链接，全部为文件复制（需求 §7.4）。
  * 进程检测走系统 API（ctypes），不调用 tasklist（需求 §7.3）。
"""

from __future__ import annotations

import ctypes
import datetime
import difflib
import fnmatch
import json
import os
import re
import sys
from ctypes import wintypes
from pathlib import Path

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

DEFAULT_GUARD = ("ChatGPT.exe", "codex.exe", "codex-*.exe")

# 「启动 ChatGPT」按钮的联动判定：**只看 ChatGPT 自身**。
# 刻意不复用 guard 名单：guard 是宿主合并名单（ChatGPT.exe + codex.exe + codex-*.exe），
# 且可被用户自定义；拿它判断会让「只有 codex.exe 在跑」误判成「ChatGPT 已打开」。
CHATGPT_PROCESS = "ChatGPT.exe"
_CHATGPT_PROCESS_LOWER = CHATGPT_PROCESS.lower()

PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RESERVED_NAMES = {"state", "guard", "history", "live", "presets", "config"}

TS_FMT = "%Y%m%d-%H%M%S"
TS_FMT_HUMAN = "%Y-%m-%d %H:%M:%S"

VERSION = "0.3.0"
SETTINGS_SCHEMA_VERSION = 1
SETTINGS_ENV = "CODEX_CONFIG_MANAGER_SETTINGS"
SETTINGS_APP_DIR = "CodexConfigManager"
SETTINGS_FILE = "settings.json"

# 建议的宿主路径前缀（仅作诊断参考，不参与拦截判定）
HOST_PATH_HINTS = (
    "\\windowsapps\\openai.",
    "\\appdata\\local\\openai\\",
)


class CoreError(Exception):
    """可预期的业务错误（会带中文说明呈现给用户）。"""


# --------------------------------------------------------------------------
# 路径解析
# --------------------------------------------------------------------------

def to_win_path(raw: str) -> str:
    """把可能是 Unix 形式的路径归一化为 Windows 形式。

    支持：C:\\a\\b、C:/a/b、/c/a/b（Git Bash 的盘符形式）、纯 Unix 形式。
    """
    if not raw:
        return raw
    p = os.path.expandvars(raw.strip())
    m = re.match(r"^/([A-Za-z])(/.*)?$", p)
    if m:                                    # /c/Users/...  ->  C:\Users\...
        drive = m.group(1).upper()
        rest = (m.group(2) or "").replace("/", "\\")
        return drive + ":" + (rest or "\\")
    return p.replace("/", "\\")


def home_dir() -> str:
    h = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return to_win_path(h)


def default_root() -> Path:
    return Path(home_dir()) / ".codex"


def _absolute_path(raw: str | os.PathLike, label: str) -> Path:
    text = str(raw).strip()
    if not text:
        raise CoreError(f"{label}不能为空。")
    path = Path(to_win_path(text)).expanduser()
    if not path.is_absolute():
        raise CoreError(f"{label}必须是绝对路径。")
    try:
        return path.resolve(strict=False)
    except OSError as e:
        raise CoreError(f"{label}无法解析：{e}")


def settings_path(explicit: str | os.PathLike | None = None) -> Path:
    raw = explicit or os.environ.get(SETTINGS_ENV)
    if raw and str(raw).strip():
        return _absolute_path(raw, "设置文件路径")
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path(home_dir()) / "AppData" / "Local")
    return _absolute_path(Path(to_win_path(local)) / SETTINGS_APP_DIR / SETTINGS_FILE,
                          "设置文件路径")


def normalize_codex_home(raw: str | os.PathLike) -> Path:
    path = _absolute_path(raw, "Codex 配置目录")
    if path.name.lower() == "config.toml" or path.suffix.lower() == ".toml":
        raise CoreError("请选择包含 config.toml 的目录，不要选择 config.toml 文件本身。")
    if path.exists() and not path.is_dir():
        raise CoreError("Codex 配置目录指向了文件，请选择目录。")
    return path


def normalize_configs_dir(raw: str | os.PathLike) -> Path:
    path = _absolute_path(raw, "预设目录")
    if path.exists() and not path.is_dir():
        raise CoreError("预设目录指向了文件，请选择目录。")
    return path


def load_settings(path: str | os.PathLike | None = None) -> dict:
    target = settings_path(path)
    if not target.exists():
        return {"ok": True, "status": "missing", "path": str(target), "settings": None}
    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise CoreError("设置内容必须是 JSON 对象。")
        if type(data.get("schema_version")) is not int:
            raise CoreError("schema_version 必须是整数。")
        if data["schema_version"] != SETTINGS_SCHEMA_VERSION:
            raise CoreError(f"不支持的设置版本：{data['schema_version']}。")
        if type(data.get("codex_home")) is not str:
            raise CoreError("codex_home 必须是字符串。")
        if type(data.get("configs_dir")) is not str:
            raise CoreError("configs_dir 必须是字符串。")
        home = normalize_codex_home(data["codex_home"])
        configs = normalize_configs_dir(data["configs_dir"])
        clean = {"schema_version": SETTINGS_SCHEMA_VERSION,
                 "codex_home": str(home), "configs_dir": str(configs)}
        return {"ok": True, "status": "ok", "path": str(target), "settings": clean}
    except (OSError, UnicodeError, json.JSONDecodeError, CoreError) as e:
        return {"ok": False, "status": "corrupt", "path": str(target),
                "settings": None, "error": str(e)}


def save_settings(codex_home: str | os.PathLike, configs_dir: str | os.PathLike,
                  path: str | os.PathLike | None = None) -> dict:
    target = settings_path(path)
    home = normalize_codex_home(codex_home)
    configs = normalize_configs_dir(configs_dir)
    data = {"schema_version": SETTINGS_SCHEMA_VERSION,
            "codex_home": str(home), "configs_dir": str(configs)}
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write_bytes(target, payload)
    return data


def resolve_paths(*, explicit_root: str | os.PathLike | None = None,
                  explicit_configs: str | os.PathLike | None = None,
                  settings_file: str | os.PathLike | None = None,
                  use_settings: bool = True) -> dict:
    """解析优先级：显式构造 > CODEX_HOME > GUI settings > 默认目录。"""
    env_raw = os.environ.get("CODEX_HOME")
    env_controlled = bool(env_raw and env_raw.strip()) and explicit_root is None
    loaded = load_settings(settings_file) if use_settings else {
        "ok": True, "status": "disabled", "path": str(settings_path(settings_file)),
        "settings": None}
    if explicit_root is not None:
        home, source = normalize_codex_home(explicit_root), "explicit"
    elif env_controlled:
        home, source = normalize_codex_home(env_raw), "environment"
    elif loaded.get("status") == "ok":
        home, source = normalize_codex_home(loaded["settings"]["codex_home"]), "settings"
    else:
        home, source = default_root().resolve(strict=False), "default"

    if explicit_configs is not None:
        configs, configs_source = normalize_configs_dir(explicit_configs), "explicit"
    elif env_controlled:
        configs, configs_source = home / "configs", "environment"
    elif source == "explicit":
        configs, configs_source = home / "configs", "explicit-root"
    elif loaded.get("status") == "ok":
        configs = normalize_configs_dir(loaded["settings"]["configs_dir"])
        configs_source = "settings"
    else:
        configs, configs_source = home / "configs", "default"

    return {"root": home, "configs_dir": configs.resolve(strict=False),
            "source": source, "configs_source": configs_source,
            "env_controlled": env_controlled, "settings": loaded}


def resolve_root(explicit: str | None = None) -> Path:
    """兼容旧调用：显式参数 > CODEX_HOME > %USERPROFILE%\\.codex。"""
    return resolve_paths(explicit_root=explicit, use_settings=False)["root"]


def _preset_count(directory: Path) -> int:
    try:
        return sum(1 for f in directory.iterdir()
                   if f.is_file() and f.suffix.lower() == ".toml" and not f.name.startswith("."))
    except OSError:
        return 0


def inspect_location(path: str | os.PathLike) -> dict:
    home = normalize_codex_home(path)
    live = home / "config.toml"
    configs = home / "configs"
    accessible = True
    error = ""
    try:
        if home.exists():
            list(home.iterdir())
    except OSError as e:
        accessible, error = False, str(e)
    mtimes = []
    for item in (home, live, configs):
        try:
            if item.exists():
                mtimes.append(item.stat().st_mtime)
        except OSError:
            pass
    modified = (datetime.datetime.fromtimestamp(max(mtimes)).strftime(TS_FMT_HUMAN)
                if mtimes else "")
    count = _preset_count(configs)
    return {"path": str(home), "exists": home.is_dir(), "accessible": accessible,
            "error": error, "config_exists": live.is_file(),
            "configs_exists": configs.is_dir(), "preset_count": count,
            "modified": modified,
            "valid": accessible and (live.is_file() or configs.is_dir())}


def probe_codex_locations() -> list[dict]:
    """只探测有限已知位置，不递归用户目录或磁盘。"""
    raw: list[tuple[Path, str]] = [(default_root(), "默认目录")]
    env = os.environ.get("CODEX_HOME")
    if env and env.strip():
        try:
            raw.append((normalize_codex_home(env), "CODEX_HOME"))
        except CoreError:
            pass
    for env_name, labels in (("APPDATA", ("Codex", "OpenAI\\Codex")),
                             ("LOCALAPPDATA", ("Codex", "OpenAI\\Codex"))):
        base = os.environ.get(env_name)
        if not base:
            continue
        for label in labels:
            cand = Path(to_win_path(base)) / Path(label)
            try:
                info = inspect_location(cand)
            except CoreError:
                continue
            if info["valid"]:
                raw.append((cand, f"%{env_name}%\\{label}"))
    out, seen = [], set()
    for path, source in raw:
        try:
            key = os.path.normcase(str(path.resolve(strict=False)))
        except OSError:
            key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        try:
            info = inspect_location(path)
        except CoreError:
            continue
        info["source"] = source
        out.append(info)
    return out


class Paths:
    """配置根目录与预设库路径；预设库可独立于 Codex 根目录。"""

    def __init__(self, root: str | os.PathLike | None = None,
                 configs_dir: str | os.PathLike | None = None):
        self.root = normalize_codex_home(root) if root is not None else resolve_root()
        self.live = self.root / "config.toml"
        self.lib = (normalize_configs_dir(configs_dir) if configs_dir is not None
                    else self.root / "configs")
        self.state = self.lib / ".state"
        self.guard = self.lib / ".guard"
        self.history = self.lib / ".history"
        self.hist_live = self.history / "live"
        self.hist_presets = self.history / "presets"

    @classmethod
    def for_gui(cls, *, explicit_root: str | os.PathLike | None = None,
                explicit_configs: str | os.PathLike | None = None,
                settings_file: str | os.PathLike | None = None):
        resolved = resolve_paths(explicit_root=explicit_root,
                                 explicit_configs=explicit_configs,
                                 settings_file=settings_file, use_settings=True)
        return cls(resolved["root"], resolved["configs_dir"]), resolved

    # 便于输出：优先相对预设库，其次相对配置根目录
    def short(self, p: Path) -> str:
        for parent in (self.lib, self.root):
            try:
                return str(Path(p).relative_to(parent))
            except Exception:
                pass
        return str(p)

    def __repr__(self) -> str:
        return f"Paths(root={self.root}, configs_dir={self.lib})"


# --------------------------------------------------------------------------
# 基础文件工具
# --------------------------------------------------------------------------

def read_bytes(path: str | os.PathLike) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str | os.PathLike) -> str:
    return read_bytes(path).decode("utf-8-sig", errors="replace")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """写临时文件 + os.replace，避免宿主或外部读到半成品。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (f".__tmp_{os.getpid()}_{path.name}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    except OSError:
        # 目标只读时先去掉只读属性再重试
        try:
            os.chmod(path, 0o666)
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise


def copy_file(src: Path, dst: Path) -> None:
    """文件复制（禁止硬/符号链接）。目标是原子替换。"""
    atomic_write_bytes(dst, read_bytes(src))


def unique_path(directory: Path, base: str, ext: str = "") -> Path:
    """同一秒内重复操作不互相覆盖：撞名时在末尾追加 -1、-2 …

    调用方把「名字」与「后缀」分开传，避免 config.toml.20260913-182024
    这种带多个点的文件名被切错位置。
    """
    directory.mkdir(parents=True, exist_ok=True)
    cand = directory / f"{base}{ext}"
    i = 1
    while cand.exists():
        cand = directory / f"{base}-{i}{ext}"
        i += 1
    return cand


def now_ts() -> str:
    return datetime.datetime.now().strftime(TS_FMT)


def human_time(ts: str | None) -> str:
    if not ts:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", TS_FMT):
        try:
            dt = datetime.datetime.strptime(ts, fmt)
            return dt.strftime(TS_FMT_HUMAN)
        except ValueError:
            continue
    return ts


# --------------------------------------------------------------------------
# 预设库
# --------------------------------------------------------------------------

def ensure_layout(p: Paths) -> None:
    p.lib.mkdir(parents=True, exist_ok=True)


def list_presets(p: Paths) -> list[dict]:
    """列出全部预设（数量不限，不做「只有两个」的假设）。"""
    out: list[dict] = []
    if not p.lib.is_dir():
        return out
    for f in sorted(p.lib.iterdir(), key=lambda x: x.name.lower()):
        if not f.is_file() or f.suffix.lower() != ".toml":
            continue
        if f.name.startswith("."):
            continue
        model, provider = peek_model(f)
        pinfo = peek_provider(read_text(f), provider) if provider else {}
        try:
            st = f.stat()
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime(TS_FMT_HUMAN)
            size = st.st_size
        except OSError:
            mtime, size = "", 0
        out.append({
            "name": f.stem,
            "file": f.name,
            "path": str(f),
            "model": model,
            "provider": provider,
            "prov_name": pinfo.get("name", ""),
            "base_url": pinfo.get("base_url", ""),
            "env_key": pinfo.get("env_key", ""),
            "wire_api": pinfo.get("wire_api", ""),
            "mtime": mtime,
            "size": size,
        })
    return out


def preset_path(p: Paths, name: str) -> Path:
    return p.lib / f"{name}.toml"


def validate_preset_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise CoreError("预设名不能为空。")
    if not PRESET_NAME_RE.match(name):
        raise CoreError("预设名只能包含字母、数字、连字符、下划线（最长 64 字符）。")
    if name.lower() in RESERVED_NAMES:
        raise CoreError(f"「{name}」是保留名称，请换一个。")
    return name


def peek_model(path: Path) -> tuple[str | None, str | None]:
    """读取 model / model_provider。优先用 tomllib，失败则正则兜底。"""
    try:
        text = read_text(path)
    except OSError:
        return None, None
    return peek_model_text(text)


def model_label(model: str | None) -> str:
    return model if model else "<默认>"


def provider_label(provider: str | None) -> str:
    if not provider:
        return "官方"
    return provider


# --------------------------------------------------------------------------
# TOML 文本级编辑
#
#   只改「目标键所在的那一行」，其余字节原样保留 —— 注释、键顺序、多行数组
#   统统不动。刻意不做「解析成字典再整体重写」，因为那会打乱宿主的文件结构，
#   也会把同步机制积累下来的差异搅乱。
# --------------------------------------------------------------------------

PROVIDER_SECTION_PREFIX = "model_providers."
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
WIRE_API_VALUES = ("responses", "chat")

TOP_KEYS = ("model", "model_provider", "model_reasoning_effort")
PROVIDER_KEYS = ("name", "base_url", "env_key", "wire_api")

_HDR_RE = re.compile(r"^\s*\[\s*(.+?)\s*\]\s*$")
_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*=")


def _cut_comment(line: str) -> str:
    """截掉引号外的行尾注释。"""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c in "\"'":
            q = c
            i += 1
            while i < n:
                if q == '"' and line[i] == "\\":
                    i += 2
                    continue
                if line[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == "#":
            return line[:i]
        i += 1
    return line


def _scrub(line: str) -> str:
    """去掉字符串字面量与注释，只留下结构性字符（用于数括号）。"""
    s = _cut_comment(line)
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            q = c
            i += 1
            while i < n:
                if q == '"' and s[i] == "\\":
                    i += 2
                    continue
                if s[i] == q:
                    i += 1
                    break
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _canon(section) -> str:
    """段名归一化：去空白、去引号（model_providers."a b" → model_providers.a b）。"""
    if section is None:
        return ""
    return str(section).strip().strip("[]").replace('"', "").replace("'", "").strip()


def parse_blocks(text: str) -> list[dict]:
    """切成若干块：{'section': None|str, 'hdr': int|None, 'body': (a, b)}

    * section=None 表示顶层（第一个 [ 之前），hdr 为 None；
    * body 是该块的键行区间（左闭右开，不含段头行）；
    * 多行数组内部的续行不会被误判为键行（见 block_key_lines）。
    """
    lines = text.split("\n")
    heads: list[tuple[int, str]] = []
    depth = 0
    for i, raw in enumerate(lines):
        clean = _cut_comment(raw)
        if depth == 0:
            m = _HDR_RE.match(clean)
            if m:
                heads.append((i, m.group(1).strip()))
                continue
        s = _scrub(raw)
        depth += s.count("[") + s.count("{") - s.count("]") - s.count("}")

    blocks: list[dict] = []
    first = heads[0][0] if heads else len(lines)
    if first > 0:
        blocks.append({"section": None, "hdr": None, "body": (0, first)})
    for idx, (hi, nm) in enumerate(heads):
        nxt = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        blocks.append({"section": nm, "hdr": hi, "body": (hi + 1, nxt)})
    return blocks


def find_block(blocks: list[dict], section) -> dict | None:
    want = _canon(section)
    for b in blocks:
        if _canon(b["section"]) == want:
            return b
    if want:                                    # 大小写不同也认
        low = want.lower()
        for b in blocks:
            if _canon(b["section"]).lower() == low:
                return b
    return None


def block_key_lines(lines: list[str], blk: dict) -> list[int]:
    """块内可视为「赋值行」的行号；多行结构内部的续行会被跳过。"""
    a, b = blk["body"]
    out: list[int] = []
    depth = 0
    for i in range(a, b):
        raw = lines[i]
        if depth == 0 and _KEY_RE.match(_cut_comment(raw)):
            out.append(i)
        s = _scrub(raw)
        depth += s.count("[") + s.count("{") - s.count("]") - s.count("}")
    return out


def _parse_str(raw: str) -> str:
    s = _cut_comment(raw).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
        return s.replace('\\"', '"').replace("\\\\", "\\") if raw.strip()[0] == '"' else s
    return s


def toml_value_str(v: str) -> str:
    """把值写成 TOML 双引号字符串。"""
    s = (str(v).replace("\\", "\\\\").replace('"', '\\"')
         .replace("\r", "").replace("\n", "\\n").replace("\t", "\\t"))
    return '"' + s + '"'


def read_key(text: str, section, key: str) -> str | None:
    """读 section 下 key 的值（已去引号）。找不到返回 None。"""
    lines = text.split("\n")
    blk = find_block(parse_blocks(text), section)
    if not blk:
        return None
    for i in block_key_lines(lines, blk):
        m = _KEY_RE.match(_cut_comment(lines[i]))
        if m and m.group(1) == key:
            _, _, rest = lines[i].partition("=")
            return _parse_str(rest)
    return None


def key_exists(text: str, section, key: str) -> bool:
    return read_key(text, section, key) is not None


def _is_crlf(text: str) -> bool:
    """文件是否用 CRLF 换行（记事本改过就会变）。改写时必须跟着走，否则混合换行。"""
    return "\r\n" in text


def set_key(text: str, section, key: str, value: str | None) -> str:
    """设置 / 删除 section 下的 key（value=None 表示删除）。段不存在则新建。"""
    eol = "\r" if _is_crlf(text) else ""
    lines = text.split("\n")
    blk = find_block(parse_blocks(text), section)
    if blk is None:
        if value is None:
            return text
        sec = _canon(section)
        if not sec:
            return f"{key} = {toml_value_str(value)}{eol}\n" + text
        body = f"[{sec}]{eol}\n{key} = {toml_value_str(value)}{eol}\n"
        base = text.rstrip("\r\n")
        return (base + eol + "\n" + eol + "\n" + body) if base else body

    hit = None
    for i in block_key_lines(lines, blk):
        m = _KEY_RE.match(_cut_comment(lines[i]))
        if m and m.group(1) == key:
            hit = i
            break

    if hit is not None:
        if value is None:
            del lines[hit]
        else:
            lines[hit] = f"{key} = {toml_value_str(value)}{eol}"
    elif value is not None:
        a, b = blk["body"]
        i = b
        while i > a and lines[i - 1].strip() == "":
            i -= 1
        lines.insert(i, f"{key} = {toml_value_str(value)}{eol}")
    return "\n".join(lines)


def remove_block(text: str, section) -> str:
    """整段删除（含段头）。段不存在时原样返回。"""
    eol = "\r" if _is_crlf(text) else ""
    lines = text.split("\n")
    blk = find_block(parse_blocks(text), section)
    if not blk or blk["hdr"] is None:
        return text
    a = blk["hdr"]
    b = blk["body"][1]
    while b < len(lines) and lines[b].strip() == "":
        b += 1
    del lines[a:b]
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines:
        lines.append(eol)
    return "\n".join(lines)


def change_count(rows: list[dict]) -> int:
    """面向人的改动量：配对的一删一加算作「一处」。"""
    return max(sum(1 for r in rows if r["kind"] == "del"),
               sum(1 for r in rows if r["kind"] == "add"))


def provider_ids(text: str) -> list[str]:
    out: list[str] = []
    for b in parse_blocks(text):
        c = _canon(b["section"])
        if c.lower().startswith(PROVIDER_SECTION_PREFIX):
            pid = c[len(PROVIDER_SECTION_PREFIX):]
            if pid and pid not in out:
                out.append(pid)
    return out


def provider_section(pid: str) -> str:
    return PROVIDER_SECTION_PREFIX + (pid or "").strip()


# ---- 表单 <-> 文本 ----

def peek_model_text(text: str) -> tuple[str | None, str | None]:
    """读取 model / model_provider。优先 tomllib，失败则回退文本扫描。"""
    try:
        import tomllib
        data = tomllib.loads(text)
        m = data.get("model")
        pv = data.get("model_provider")
        return (str(m) if m is not None else None,
                str(pv) if pv is not None else None)
    except Exception:
        pass
    return read_key(text, None, "model"), read_key(text, None, "model_provider")


def peek_provider(text: str, pid: str | None) -> dict:
    """读取某个供应商块的四个字段（值已去引号）。"""
    if not pid:
        return {}
    sec = provider_section(pid)
    return {k: (read_key(text, sec, k) or "") for k in PROVIDER_KEYS}


def validate_llm_form(form: dict) -> dict:
    """返回 {字段: 错误信息}；空字典表示通过。

    注意：`model_provider` 与 `model` 都允许为空 —— 那是「走宿主官方默认」的合法状态
    （官方预设就是这个样子）。provider_id 为空时不写供应商块，由界面负责提示。
    """
    errs: dict[str, str] = {}
    pid = (form.get("model_provider") or "").strip()
    if pid and not PROVIDER_ID_RE.match(pid):
        errs["model_provider"] = "供应商 ID 只能包含字母、数字、连字符、下划线（最长 64 字符）。"

    model = (form.get("model") or "").strip()
    if model and re.search(r'[\s"\']', model):
        errs["model"] = "模型 ID 不应包含空格或引号。"

    url = (form.get("base_url") or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        errs["base_url"] = "Base URL 需以 http:// 或 https:// 开头。"

    ek = (form.get("env_key") or "").strip()
    if ek and not ENV_KEY_RE.match(ek):
        errs["env_key"] = "环境变量名只能由字母、数字、下划线组成，且不能以数字开头。"

    wa = (form.get("wire_api") or "").strip()
    if wa and wa not in WIRE_API_VALUES:
        errs["wire_api"] = "接口协议只能是 responses 或 chat。"

    rz = (form.get("reasoning") or "").strip()
    if rz and not re.match(r"^[A-Za-z0-9_-]{1,32}$", rz):
        errs["reasoning"] = "推理强度只能使用字母、数字、连字符。"

    pn = (form.get("prov_name") or "").strip()
    if re.search(r'["\']', pn):
        errs["prov_name"] = "显示名称不能包含引号。"

    nn = (form.get("new_name") or "").strip()
    if nn and nn != (form.get("preset") or "").strip():
        try:
            validate_preset_name(nn)
        except CoreError as e:
            errs["new_name"] = str(e)
    return errs


def _form_val(form: dict, key: str) -> str | None:
    v = form.get(key)
    v = "" if v is None else str(v).strip()
    return v or None


def apply_form_to_text(text: str, form: dict) -> str:
    """按表单生成新文本（纯函数，便于预览与测试）。"""
    pid = _form_val(form, "model_provider") or ""

    text = set_key(text, None, "model", _form_val(form, "model"))
    text = set_key(text, None, "model_provider", pid or None)
    text = set_key(text, None, "model_reasoning_effort", _form_val(form, "reasoning"))

    # 要写哪个供应商块：显式指定的 edit_provider 优先。
    # 预设没有 model_provider 时（官方预设就是这样）也得能改供应商块，
    # 但不能顺手把 model_provider 加上 —— 那会悄悄改变预设实际用的供应商。
    blk = (form.get("edit_provider") or "").strip() or pid
    drop = (form.get("drop_provider") or "").strip()
    if drop and pid and drop == blk:
        # 块改名：字段必须跟着新名字落到新块，否则先写旧块再删旧块，字段全丢
        blk = pid

    if blk:
        sec = provider_section(blk)
        text = set_key(text, sec, "name", _form_val(form, "prov_name"))
        text = set_key(text, sec, "base_url", _form_val(form, "base_url"))
        text = set_key(text, sec, "env_key", _form_val(form, "env_key"))
        text = set_key(text, sec, "wire_api", _form_val(form, "wire_api"))

    # 供应商 ID 改名：把不再被引用的旧块一并删掉
    if drop and drop != pid and drop != blk:
        text = remove_block(text, provider_section(drop))
    return text


def read_preset_form(p: Paths, name: str) -> dict:
    """收集编辑表单所需的全部字段（只读，不写盘）。"""
    name = validate_preset_name(name)
    f = preset_path(p, name)
    if not f.exists():
        raise CoreError(f"找不到预设「{name}」：{f}")
    text = read_text(f)

    ids = provider_ids(text)
    current, _ = read_state(p)
    is_current = (current == name)
    if not current and p.live.exists():
        try:
            if read_text(p.live) == text:
                is_current = True            # 当前配置未记录，但正在使用的就是它
        except OSError:
            pass

    mp = read_key(text, None, "model_provider") or ""
    sel = mp if mp in ids else (ids[0] if ids else mp)
    pinfo = peek_provider(text, sel) if sel else {}
    ek = pinfo.get("env_key") or ""

    return {
        "ok": True,
        "preset": name,
        "path": str(f),
        "is_current": is_current,
        "live": str(p.live),
        "model": read_key(text, None, "model") or "",
        "model_provider": mp,
        "reasoning": read_key(text, None, "model_reasoning_effort") or "",
        "providers": ids,
        "blocks": {pid: peek_provider(text, pid) for pid in ids},
        "orig_provider_id": sel,
        "prov_name": pinfo.get("name", ""),
        "base_url": pinfo.get("base_url", ""),
        "env_key": ek,
        "env_set": bool(ek) and bool(os.environ.get(ek)),
        "wire_api": pinfo.get("wire_api", ""),
    }


def preview_edit(p: Paths, name: str, form: dict) -> dict:
    """不写盘的预览：校验 + 差异行。供界面实时显示。"""
    try:
        name = validate_preset_name(name)
        f = preset_path(p, name)
        if not f.exists():
            raise CoreError(f"找不到预设「{name}」：{f}")
        errs = validate_llm_form(form)
        if errs:
            return {"ok": False, "errors": errs}
        old = read_text(f)
        new = apply_form_to_text(old, form)
        new_name = (form.get("new_name") or "").strip() or name
        raw_changed, rows = diff_rows(old, new)
        rename = new_name != name
        return {
            "ok": True, "errors": {}, "changed": change_count(rows), "rows": rows,
            "same": raw_changed == 0, "new_name": new_name, "rename": rename,
            "rename_conflict": bool(rename and preset_path(p, new_name).exists()),
            "size_before": len(old.encode("utf-8")),
            "size_after": len(new.encode("utf-8")),
        }
    except CoreError as e:
        return {"ok": False, "errors": {"_": str(e)}}
    except Exception as e:                                  # noqa: BLE001
        return {"ok": False, "errors": {"_": f"{type(e).__name__}: {e}"}}


def run_edit(p: Paths, name: str, form: dict, *, force: bool = False,
             dry: bool = False, rep: Reporter | None = None) -> dict:
    """编辑预设的大模型相关配置。

    与启用流程一致的取舍：若改的是「当前正在使用」的预设，会先同步正在使用的改动，
    改完再同步写回 config.toml —— 否则下一次启用会把这次编辑冲掉。
    """
    rep = rep or Reporter()
    warn_codes: list[str] = []
    try:
        name = validate_preset_name(name)
        src = preset_path(p, name)
        if not src.exists():
            raise CoreError(f"找不到预设「{name}」：{src}")

        errs = validate_llm_form(form)
        if errs:
            raise CoreError("；".join(errs.values()))

        new_name = (form.get("new_name") or "").strip() or name
        new_name = validate_preset_name(new_name)
        dst = preset_path(p, new_name)
        if new_name != name and dst.exists():
            raise CoreError(f"预设「{new_name}」已存在，未覆盖。")

        current, _ = read_state(p)
        is_current = (current == name)
        if not current and p.live.exists():
            try:
                if read_text(p.live) == read_text(src):
                    is_current = True
            except OSError:
                pass

        # ---- 1 进程检测（只有会影响正在使用的配置时才需要拦） ----
        if is_current:
            pats, gsrc = guard_list(p)
            hits = match_processes(pats)
            head = "[1/4] 检查宿主应用进程 ...... "
            if hits:
                if dry:
                    rep.step(head + f"检测到 {len(hits)} 个进程（演练模式不拦截）")
                elif force:
                    rep.step(head + f"检测到 {len(hits)} 个进程（已强制跳过）")
                    rep.warn("    宿主应用正在运行，这次写入可能马上被覆盖回去。")
                else:
                    rep.step(head + f"检测到 {len(hits)} 个进程  ×")
                    rep.err("[!] 该预设正在使用中，编辑会同时改写正在使用的 config.toml。")
                    rep.err("[!] 检测到宿主应用正在运行，已中止：")
                    rep.info("")
                    for line in format_hits(hits):
                        rep.info(line)
                    rep.info("")
                    rep.info("    请先完全退出（含托盘图标）再操作；")
                    rep.info("    或先启用别的预设，就能只改这个预设文件而不碰正在使用的。")
                    rep.info(f"    若确认无碍可强制；认为误伤可编辑：{p.guard}")
                    return {"ok": False, "blocked": True, "lines": rep.lines,
                            "warns": warn_codes}
            else:
                rep.step(head + "未运行  OK")
                if gsrc != "file":
                    rep.info("      （" + guard_source_text(p, gsrc) + "："
                             + ", ".join(pats) + "）")
        else:
            rep.step("[1/4] 该预设未在使用中 —— 只改动预设文件，不影响正在使用的配置")

        if not dry:
            _probe_writable(p)

        # ---- 2 正在使用的预设：先同步，保住宿主运行期累积的改动 ----
        if is_current and p.live.exists():
            if read_text(src) != read_text(p.live):
                n0, _ = diff_rows(read_text(src), read_text(p.live))
                if dry:
                    rep.info(f"[2/4] （演练）将先把正在使用的改动 {n0} 行同步进 {name}")
                else:
                    b = backup_preset(p, name)
                    copy_file(p.live, src)
                    rep.info(f"[2/4] 先同步正在使用的改动 -> {name}（{n0} 行；"
                             f"同步前版本 {p.short(b)}）")
            else:
                rep.step("[2/4] 正在使用的配置与预设一致，无需同步")
        else:
            rep.step("[2/4] 跳过同步（该预设不是当前预设）")

        # ---- 3 应用编辑 ----
        old_text = read_text(src)
        new_text = apply_form_to_text(old_text, form)
        raw_changed, rows = diff_rows(old_text, new_text)
        changed = change_count(rows)

        if raw_changed == 0 and new_name == name:
            rep.ok("[OK] 没有任何改动，未写入任何文件。")
            return {"ok": True, "noop": True, "lines": rep.lines, "warns": warn_codes}

        if changed:
            rep.step(f"[3/4] 写入预设 {name}.toml ...... 改动 {changed} 处")
        else:
            rep.step(f"[3/4] 预设 {name}.toml 内容无变化，跳过写入")
        if changed:
            if dry:
                rep.info(f"      （演练）将写入 {new_name}.toml，改动 {changed} 处")
            else:
                b = backup_preset(p, name)
                atomic_write_bytes(src, new_text.encode("utf-8"))
                rep.info(f"      改动 {changed} 处；旧版本 -> {p.short(b)}")
                if form.get("drop_provider"):
                    rep.info(f"      已移除不再引用的供应商块 "
                             f"[{provider_section(form['drop_provider'])}]")

        if new_name != name:
            if not dry:
                os.replace(src, dst)
            rep.info(f"      重命名 {name}.toml -> {new_name}.toml")

        # ---- 4 同步到正在使用的 ----
        rep.step("[4/4] 同步到正在使用的配置")
        if is_current:
            if dry:
                rep.info("      （演练）将覆盖正在使用的 config.toml")
            else:
                bl = backup_live(p)
                copy_file(dst, p.live)
                rep.info(f"      正在使用的 config.toml 已更新；启用前快照 -> {p.short(bl)}")
            if new_name != name and not dry:
                write_state(p, new_name)
                rep.info(f"      状态记录更新为 {new_name}")
        else:
            rep.info("      该预设未在使用中，正在使用的配置与状态记录均未改动")
        rep.ok("[OK] 保存完成。请重启宿主应用使新配置生效"
               if not dry else "[OK] 演练完成，磁盘未发生任何变化")
        return {"ok": True, "blocked": False, "lines": rep.lines, "warns": warn_codes,
                "changed": changed, "new_name": new_name, "is_current": is_current,
                "dry": dry}
    except CoreError as e:
        rep.err(f"[×] {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines, "warns": warn_codes}
    except Exception as e:                                  # noqa: BLE001
        rep.err(f"[×] 未预期的错误，已中止：{type(e).__name__}: {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines, "warns": warn_codes}


# 官方模板 = **完全空白**的预设：不写 model / model_provider，也不写任何
# [model_providers.*] 块。首次用 Codex / ChatGPT 打开时会由宿主自动补齐官方
# 默认配置，工具不替用户猜一个模型名。
OFFICIAL_BLANK_TEXT = (
    "# Codex 官方配置（空白预设）\n"
    "# 未写入任何设置；启用它之后，首次打开 Codex / ChatGPT 时会自动补齐官方默认配置。\n"
)


def new_preset_text(kind: str, form: dict) -> str:
    """从空模板创建；官方配置不继承第三方设置或登录文件。

    · 官方模板 = **完全空白**（只有说明注释，不含任何键）；
    · 自定义模型模板 = **只写大模型相关设置**（model / model_provider /
      [model_providers.*] 块）；项目、插件等其余内容都不写，
      与官方模板一样交给宿主在打开时补齐。
    """
    if kind not in ("official", "third_party", "local", "responses", "chat"):
        raise CoreError("请选择有效配置模板。")
    import tomllib
    if kind == "official":
        tomllib.loads(OFFICIAL_BLANK_TEXT)      # 空白模板本身也必须是合法 TOML
        return OFFICIAL_BLANK_TEXT
    fields = {k: form.get(k, "") for k in
              ("model", "model_provider", "reasoning", "prov_name", "base_url", "env_key", "wire_api")}
    if kind == "local":
        fields["base_url"] = fields["base_url"] or "http://127.0.0.1:11434/v1"
        fields["wire_api"] = fields["wire_api"] or "chat"
        fields["model_provider"] = fields["model_provider"] or "local"
        fields["env_key"] = fields["env_key"] or "LOCAL_API_KEY"
    elif kind == "responses":
        fields["wire_api"] = "responses"
    elif kind == "chat":
        fields["wire_api"] = "chat"
    for key, label in (("model", "模型 ID"), ("model_provider", "供应商 ID"),
                       ("base_url", "Base URL"), ("env_key", "API Key 环境变量名"),
                       ("wire_api", "接口协议")):
        if not str(fields.get(key) or "").strip():
            raise CoreError(f"请填写{label}。")
    from connection import validate_endpoint
    validate_endpoint(str(fields["base_url"]).strip())
    errs = validate_llm_form(fields)
    if errs:
        raise CoreError("；".join(errs.values()))
    text = apply_form_to_text("# Codex 配置预设\n", fields)
    tomllib.loads(text)
    return text


def run_save_form(p: Paths, name: str, form: dict, *, create_kind: str = "",
                  activate: bool = False, rep: Reporter | None = None) -> dict:
    """保存与启用分开汇报；启用失败不能误报为完全成功。"""
    rep = rep or Reporter()
    try:
        name = validate_preset_name(name)
        if create_kind:
            text = new_preset_text(create_kind, form)
            dest = preset_path(p, name)
            if dest.exists():
                raise CoreError(f"预设「{name}」已存在，未覆盖。请换一个名称。")
            ensure_layout(p)
            # 排他创建，防止检查之后同名文件被其他操作创建。
            with dest.open("xb") as f:
                f.write(text.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            rep.ok("[OK] 新预设已保存；尚未改变 Codex 正在使用的配置。")
            res = {"ok": True, "new_name": name, "lines": rep.lines}
        else:
            res = run_edit(p, name, form, rep=rep)
            if not res["ok"]:
                return dict(res, saved=False, activated=False)
        target = res.get("new_name", name)
        if activate:
            switched = run_switch(p, target, rep=rep)
            if not switched["ok"]:
                rep.warn("预设已保存，但尚未启用。请完全退出 Codex 后，选中该预设再点右侧边栏的「启用配置」；无需重复新建。")
            return dict(switched, saved=True, activated=bool(switched["ok"]), new_name=target)
        return dict(res, saved=True, activated=False)
    except (CoreError, OSError, ValueError):
        rep.err("保存未完成。请检查名称是否重复、字段格式和目录写入权限；现有同名预设不会被覆盖。")
        return {"ok": False, "saved": False, "activated": False, "lines": rep.lines}


# --------------------------------------------------------------------------
# 状态记录
# --------------------------------------------------------------------------

def read_state(p: Paths) -> tuple[str | None, str | None]:
    """返回 (当前预设名, 上次启用时间)。缺失或损坏 → (None, None)，不抛异常。"""
    try:
        text = read_text(p.state)
    except OSError:
        return None, None
    preset = None
    switched = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().lower(), v.strip()
        if k == "preset":
            preset = v or None
        elif k in ("switched_at", "switched", "time"):
            switched = v or None
    if preset and not PRESET_NAME_RE.match(preset):
        return None, switched          # 损坏 → 按「当前配置未记录」处理
    return preset, switched


def write_state(p: Paths, preset: str) -> None:
    text = (f"preset={preset}\n"
            f"switched_at={datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
    atomic_write_bytes(p.state, text.encode("utf-8"))


# --------------------------------------------------------------------------
# 进程名单与检测
# --------------------------------------------------------------------------

def guard_list(p: Paths) -> tuple[list[str], str]:
    """返回 (模式列表, 来源)。来源：file / default / default(空文件)"""
    try:
        raw = read_text(p.guard)
    except OSError:
        return list(DEFAULT_GUARD), "default"
    pats: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pats.append(line)
    if not pats:
        # 名单文件存在但没有任何有效行 —— 仍回退默认，避免保护被静默关闭
        return list(DEFAULT_GUARD), "default-empty"
    return pats, "file"


def guard_source_text(p: Paths, source: str) -> str:
    if source == "file":
        return f"来自 {p.guard}"
    if source == "default-empty":
        return f"未找到 {p.guard}，已使用内置默认名单"
    return f"未找到 {p.guard}，已使用内置默认名单"


# ---- Windows 进程枚举（ctypes，无外部依赖） ----

_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

# 顶层窗口枚举（用于区分「ChatGPT 界面已打开」与「仅有后台驻留进程」）。
# WINFUNCTYPE / WinDLL 只在 Windows 存在，非 Windows 下置 None 由调用方短路。
if sys.platform.startswith("win"):
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
else:
    _WNDENUMPROC = None

_MIN_WINDOW_SIDE = 80   # 边长小于此值视为隐藏辅助窗口，不计入「界面已打开」


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _bind_kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


def _process_path(k32, pid: int) -> str:
    h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(2048)
        size = wintypes.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    except Exception:
        pass
    finally:
        k32.CloseHandle(h)
    return ""


def list_processes(with_path: bool = True) -> list[tuple[int, str, str]]:
    """返回 [(pid, 进程名, 完整路径)]。失败时返回空列表，不抛异常。"""
    if not sys.platform.startswith("win"):
        return []
    try:
        k32 = _bind_kernel32()
    except Exception:
        return []
    snap = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE_VALUE:
        return []
    out: list[tuple[int, str, str]] = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            pid = int(entry.th32ProcessID)
            out.append((pid, name, ""))
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    except Exception:
        pass
    finally:
        k32.CloseHandle(snap)
    if with_path:
        out = [(pid, nm, _process_path(k32, pid)) for pid, nm, _ in out]
    return out


def match_processes(patterns: list[str], procs=None) -> list[dict]:
    """按名单匹配进程，返回明细（含完整路径，用于识别误伤）。"""
    if procs is None:
        procs = list_processes(with_path=True)
    lower = [x.lower() for x in patterns]
    hits: list[dict] = []
    for pid, name, path in procs:
        n = (name or "").lower()
        for pat in lower:
            if fnmatch.fnmatch(n, pat):
                hits.append({"name": name, "pid": pid, "path": path})
                break
    return hits


def chatgpt_processes(procs=None) -> list[dict]:
    """只匹配 ChatGPT 应用自身的进程（**不含** `codex.exe`）。

    见 `CHATGPT_PROCESS` 注释：不要把 `guard.running` 的结果拿来做这个判断，
    两者语义不同（guard 是宿主合并名单，且可被用户自定义）。
    """
    if procs is None:
        procs = list_processes(with_path=False)
    out: list[dict] = []
    for pid, name, path in procs:
        if (name or "").strip().lower() == _CHATGPT_PROCESS_LOWER:
            out.append({"name": name, "pid": pid, "path": path})
    return out


def visible_window_pids(pids) -> set[int]:
    """返回给定进程集合中**拥有可见顶层窗口**的 pid 集合。

    用途：MSIX 桌面应用关闭窗口后常驻后台，只看进程会把「界面其实没打开」
    误判成「已经在运行」，按钮就永远灰着。这里以「存在可见且非微型的顶层窗口」
    作为「界面已打开」的判据。

    任何异常或非 Windows 平台一律返回空集合 —— 调用方据此按「未打开」处理，
    宁可多让用户点一下，也不要让按钮无理由不可用。
    """
    if _WNDENUMPROC is None or not pids:
        return set()
    want = {int(x) for x in pids}
    try:
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u32.GetWindowThreadProcessId.restype = wintypes.DWORD
        u32.IsWindowVisible.argtypes = [wintypes.HWND]
        u32.IsWindowVisible.restype = wintypes.BOOL
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect.restype = wintypes.BOOL
        u32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
        u32.EnumWindows.restype = wintypes.BOOL
    except Exception:                                          # noqa: BLE001
        return set()

    found: set[int] = set()

    def _cb(hwnd, _lparam):
        if hwnd is None:
            return True
        pid = wintypes.DWORD(0)
        try:
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        except Exception:                                      # noqa: BLE001
            return True
        if pid.value not in want:
            return True
        try:
            if not u32.IsWindowVisible(hwnd):
                return True
            rect = wintypes.RECT()
            if not u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if ((rect.right - rect.left) < _MIN_WINDOW_SIDE
                    or (rect.bottom - rect.top) < _MIN_WINDOW_SIDE):
                return True
        except Exception:                                      # noqa: BLE001
            return True
        found.add(pid.value)
        # 所有目标进程都找到可见窗口后即可停止枚举
        return len(found) < len(want)

    try:
        u32.EnumWindows(_WNDENUMPROC(_cb), 0)
    except Exception:                                          # noqa: BLE001
        return set()
    return found


def chatgpt_state(procs=None) -> dict:
    """「启动 ChatGPT」按钮所需的联动状态。

    * `running`  —— 存在 `ChatGPT.exe` 进程（含仅有后台驻留的情况）
    * `windowed` —— 存在可见的 ChatGPT 顶层窗口，即**界面已经打开**
    * `count`    —— 进程数量（该应用运行时有多个同名实例，仅供参考）

    按钮可用性应由 `windowed` 决定：界面已打开时重复启动没有意义；
    而只有后台驻留进程时仍应允许点击（AUMID 激活会把已有实例带到前台）。
    """
    procs = list_processes(with_path=False) if procs is None else list(procs)
    hits = chatgpt_processes(procs)
    windowed = bool(visible_window_pids([h["pid"] for h in hits]))
    return {"running": bool(hits), "windowed": windowed, "count": len(hits)}


def aggregate_hits(hits: list[dict]) -> list[dict]:
    """按进程名聚合计数（宿主会有十余个同名实例）。"""
    agg: dict[str, dict] = {}
    for h in hits:
        key = h["name"].lower()
        a = agg.setdefault(key, {"name": h["name"], "count": 0,
                                 "pids": [], "paths": []})
        a["count"] += 1
        a["pids"].append(h["pid"])
        if h["path"] and h["path"] not in a["paths"]:
            a["paths"].append(h["path"])
    return sorted(agg.values(), key=lambda x: (-x["count"], x["name"].lower()))


def host_hint(path: str) -> bool:
    """路径是否位于 OpenAI 相关目录（仅诊断参考，不参与拦截）。"""
    if not path:
        return False
    lp = path.lower().replace("/", "\\")
    return any(hint in lp for hint in HOST_PATH_HINTS)


# --------------------------------------------------------------------------
# 差异对比
# --------------------------------------------------------------------------

def diff_rows(old_text: str, new_text: str, context: int = 3) -> tuple[int, list[dict]]:
    """返回 (改动行数, 行列表)。行 = {kind: ctx|add|del, text, gap?:bool}"""
    old = old_text.splitlines()
    new = new_text.splitlines()
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    rows: list[dict] = []
    changed = 0
    pending_gap = False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            block = old[i1:i2]
            if len(block) <= context * 2:
                if pending_gap and rows:
                    rows.append({"kind": "gap", "text": ""})
                    pending_gap = False
                rows.extend({"kind": "ctx", "text": ln} for ln in block)
            else:
                head, tail = block[:context], block[-context:]
                if pending_gap and rows:
                    rows.append({"kind": "gap", "text": ""})
                rows.extend({"kind": "ctx", "text": ln} for ln in head)
                rows.append({"kind": "gap", "text": ""})
                rows.extend({"kind": "ctx", "text": ln} for ln in tail)
                pending_gap = False
                continue
            pending_gap = False
        else:
            if pending_gap and rows:
                rows.append({"kind": "gap", "text": ""})
                pending_gap = False
            for ln in old[i1:i2]:
                rows.append({"kind": "del", "text": ln})
                changed += 1
            for ln in new[j1:j2]:
                rows.append({"kind": "add", "text": ln})
                changed += 1
    return changed, rows


# --------------------------------------------------------------------------
# 备份 / 同步 / 启用
# --------------------------------------------------------------------------

def _probe_writable(p: Paths) -> None:
    """历史目录不可写 → 中止整个流程（FR-3.2 / FR-5）。"""
    for d in (p.lib, p.history, p.hist_live, p.hist_presets):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise CoreError(f"无法创建目录 {d}：{e}")
    probe = p.hist_live / f".__wtest_{os.getpid()}"
    try:
        with open(probe, "wb") as f:
            f.write(b"x")
        probe.unlink()
    except OSError as e:
        raise CoreError(f"历史目录不可写，已中止（不执行任何写入）：{p.hist_live}（{e}）")


def backup_live(p: Paths) -> Path:
    dest = unique_path(p.hist_live, f"config.toml.{now_ts()}")
    copy_file(p.live, dest)
    return dest


def backup_preset(p: Paths, name: str) -> Path:
    dest = unique_path(p.hist_presets / name, now_ts(), ".toml")
    copy_file(preset_path(p, name), dest)
    return dest


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(parent.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _history_time(path: Path) -> str:
    """优先从备份文件名读取时间；无法识别时使用文件修改时间。"""
    names = [path.stem]
    if path.name.startswith("config.toml."):
        names.insert(0, path.name[len("config.toml."):])
    for raw in names:
        m = re.match(r"^(\d{8}-\d{6})(?:-\d+)?$", raw)
        if m:
            return human_time(m.group(1))
    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime(TS_FMT_HUMAN)
    except OSError:
        return ""


def list_history(p: Paths) -> list[dict]:
    """只读列出受管历史文件；不跟随目录外路径。"""
    rows: list[dict] = []
    history_root = p.history.resolve(strict=False)

    if p.hist_live.is_dir():
        for f in p.hist_live.iterdir():
            if not f.is_file() or not f.name.startswith("config.toml."):
                continue
            try:
                resolved = f.resolve(strict=True)
                resolved.relative_to(history_root)
                st = resolved.stat()
            except (OSError, ValueError):
                continue
            rows.append({"source": "live", "source_name": "当前配置", "preset": "",
                         "path": str(resolved), "time": _history_time(resolved),
                         "size": st.st_size, "mtime_ns": st.st_mtime_ns})

    if p.hist_presets.is_dir():
        for directory in p.hist_presets.iterdir():
            if not directory.is_dir():
                continue
            try:
                name = validate_preset_name(directory.name)
            except CoreError:
                continue
            for f in directory.iterdir():
                if not f.is_file() or f.suffix.lower() != ".toml":
                    continue
                try:
                    resolved = f.resolve(strict=True)
                    resolved.relative_to(history_root)
                    st = resolved.stat()
                except (OSError, ValueError):
                    continue
                rows.append({"source": "preset", "source_name": f"预设 {name}",
                             "preset": name, "path": str(resolved),
                             "time": _history_time(resolved), "size": st.st_size,
                             "mtime_ns": st.st_mtime_ns})

    rows.sort(key=lambda x: (x["time"], x["mtime_ns"], x["path"]), reverse=True)
    return rows


def preset_is_current(p: Paths, name: str) -> bool:
    current, _ = read_state(p)
    if current:
        return current == name
    target = preset_path(p, name)
    if not target.exists() or not p.live.exists():
        return False
    try:
        return read_bytes(target) == read_bytes(p.live)
    except OSError:
        return False


def history_target(p: Paths, target_type: str, target_name: str = "") -> tuple[Path, str, bool]:
    """返回（目标文件、显示名、是否会影响正在使用的配置）。"""
    if target_type == "live":
        return p.live, "当前配置", True
    if target_type != "preset":
        raise CoreError("恢复目标无效。")
    name = validate_preset_name(target_name)
    target = preset_path(p, name)
    return target, f"预设「{name}」", preset_is_current(p, name)


def validate_history_file(p: Paths, source: str | os.PathLike) -> Path:
    """历史文件必须仍存在、是普通文件并位于受管 .history 目录内。"""
    path = Path(source)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(p.history.resolve(strict=True))
    except (OSError, ValueError):
        raise CoreError("所选历史版本已不存在或不属于本程序的历史目录。")
    if not resolved.is_file():
        raise CoreError("所选历史版本不是可读取的文件。")
    listed = {Path(x["path"]).resolve(strict=True) for x in list_history(p)}
    if resolved not in listed:
        raise CoreError("所选历史版本已变化，请刷新列表后重试。")
    return resolved


def preview_history(p: Paths, source: str | os.PathLike,
                    target_type: str, target_name: str = "") -> dict:
    source_path = validate_history_file(p, source)
    target, label, affects_live = history_target(p, target_type, target_name)
    if not target.exists():
        raise CoreError(f"恢复目标不存在：{label}。")
    old = read_text(target)
    new = read_text(source_path)
    changed, rows = diff_rows(old, new)
    return {"ok": True, "target": label, "affects_live": affects_live,
            "changed": changed, "same": old == new, "rows": rows,
            "size_before": len(read_bytes(target)), "size_after": len(read_bytes(source_path))}


def _host_hits(p: Paths) -> list[dict]:
    pats, _ = guard_list(p)
    return match_processes(pats)


def run_restore_history(p: Paths, source: str | os.PathLike,
                        target_type: str, target_name: str = "",
                        *, expected_size: int | None = None,
                        expected_mtime_ns: int | None = None,
                        expected_sha256: str | None = None,
                        rep: Reporter | None = None) -> dict:
    """从历史版本恢复；普通入口没有 force，影响 live 时宿主运行即拒绝。"""
    import hashlib
    rep = rep or Reporter()
    try:
        source_path = validate_history_file(p, source)
        st = source_path.stat()
        digest = hashlib.sha256(read_bytes(source_path)).hexdigest()
        if ((expected_size is not None and st.st_size != expected_size)
                or (expected_mtime_ns is not None and st.st_mtime_ns != expected_mtime_ns)
                or (expected_sha256 is not None and digest != expected_sha256)):
            raise CoreError("所选历史版本在预览后发生了变化，请刷新列表后重试。")

        target, label, affects_live = history_target(p, target_type, target_name)
        if not target.exists():
            raise CoreError(f"恢复目标不存在：{label}。")
        if affects_live:
            hits = _host_hits(p)
            if hits:
                rep.err("Codex 正在运行，已停止恢复。请完全退出 Codex（包括托盘）后重试。")
                return {"ok": False, "blocked": True, "lines": rep.lines}
        if read_bytes(target) == read_bytes(source_path):
            rep.ok("所选历史版本与恢复目标完全一致，无需写入。")
            return {"ok": True, "noop": True, "lines": rep.lines}

        _probe_writable(p)
        if target_type == "live":
            backup = backup_live(p)
            try:
                copy_file(source_path, p.live)
            except Exception:
                copy_file(backup, p.live)
                raise
            rep.info(f"恢复前已备份当前配置 -> {p.short(backup)}")
        else:
            name = validate_preset_name(target_name)
            preset_backup = backup_preset(p, name)
            live_backup = None
            if affects_live:
                live_backup = backup_live(p)
            try:
                copy_file(source_path, target)
                if affects_live:
                    copy_file(target, p.live)
            except Exception:
                copy_file(preset_backup, target)
                if affects_live and live_backup:
                    copy_file(live_backup, p.live)
                raise
            rep.info(f"恢复前已备份预设 -> {p.short(preset_backup)}")
            if live_backup:
                rep.info(f"恢复前已备份当前配置 -> {p.short(live_backup)}")
        rep.ok(f"已恢复到{label}。历史文件仍保留。")
        return {"ok": True, "blocked": False, "lines": rep.lines,
                "target": label, "affects_live": affects_live}
    except CoreError as e:
        rep.err(str(e))
        return {"ok": False, "blocked": False, "lines": rep.lines}
    except Exception as e:  # noqa: BLE001
        rep.err(f"恢复失败，已停止：{type(e).__name__}: {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines}


def run_copy_preset(p: Paths, source_name: str, new_name: str,
                    rep: Reporter | None = None) -> dict:
    rep = rep or Reporter()
    try:
        source_name = validate_preset_name(source_name)
        new_name = validate_preset_name(new_name)
        source = preset_path(p, source_name)
        target = preset_path(p, new_name)
        if not source.exists():
            raise CoreError(f"找不到预设「{source_name}」。")
        if target.exists():
            raise CoreError(f"预设「{new_name}」已存在，未覆盖。")
        ensure_layout(p)
        data = read_bytes(source)
        with target.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        rep.ok(f"已复制为预设「{new_name}」，未启用。")
        return {"ok": True, "lines": rep.lines, "name": new_name}
    except CoreError as e:
        rep.err(str(e))
        return {"ok": False, "lines": rep.lines}
    except Exception as e:  # noqa: BLE001
        rep.err(f"复制失败：{type(e).__name__}: {e}")
        return {"ok": False, "lines": rep.lines}


def run_delete_preset(p: Paths, name: str, rep: Reporter | None = None) -> dict:
    rep = rep or Reporter()
    try:
        name = validate_preset_name(name)
        if preset_is_current(p, name):
            raise CoreError("当前正在使用的配置不能删除。请先启用其他配置。")
        target = preset_path(p, name)
        if not target.exists():
            raise CoreError(f"找不到预设「{name}」。")
        _probe_writable(p)
        backup = backup_preset(p, name)
        target.unlink()
        rep.info(f"删除前已备份 -> {p.short(backup)}")
        rep.ok(f"已删除预设「{name}」。历史记录和环境变量未删除。")
        return {"ok": True, "lines": rep.lines, "name": name,
                "backup": str(backup)}
    except CoreError as e:
        rep.err(str(e))
        return {"ok": False, "lines": rep.lines}
    except Exception as e:  # noqa: BLE001
        rep.err(f"删除失败：{type(e).__name__}: {e}")
        return {"ok": False, "lines": rep.lines}


class Reporter:
    """收集操作过程中的日志行。kind: step|info|ok|warn|err"""

    def __init__(self):
        self.lines: list[dict] = []

    def __call__(self, kind: str, text: str) -> None:
        self.lines.append({"kind": kind, "text": text})

    def step(self, text: str) -> None:
        self("step", text)

    def info(self, text: str) -> None:
        self("info", text)

    def ok(self, text: str) -> None:
        self("ok", text)

    def warn(self, text: str) -> None:
        self("warn", text)

    def err(self, text: str) -> None:
        self("err", text)


def live_vs_preset(p: Paths, name: str | None) -> tuple[bool, int]:
    """返回 (是否存在差异, 差异行数)。name 为空或文件缺失时视为有差异。"""
    if not name:
        return True, 0
    f = preset_path(p, name)
    if not p.live.exists() or not f.exists():
        return True, 0
    old = read_text(f)
    new = read_text(p.live)
    if old == new:
        return False, 0
    n, _ = diff_rows(old, new)
    return True, n


def host_running_now(p: Paths) -> dict:
    """轻量查询「宿主是否在运行」（供界面按秒轮询）。

    与 `run_guard(p)` 的区别：这里**只**枚举进程并匹配名单，
    不读任何配置文件、不聚合命中明细 —— 实测单次约 9 ms（277 进程），
    因此可以安全地按秒级频率轮询。

    为什么需要它：`snapshot()` 里的 `guard.running` 只在界面渲染那一刻算一次，
    用户退出 Codex / ChatGPT 之后不会自动更新，「启用配置」按钮就会一直灰着。
    界面改为轮询本函数来实时反映「宿主已退出」。

    任何异常都退化为「未在运行」：宁可让用户点一下再被真正拦截，
    也不要让按钮无理由地灰掉（这是用户实际反馈过的坏体验）。
    """
    try:
        pats, src = guard_list(p)
        hits = match_processes(pats, list_processes(with_path=False))
        return {"running": bool(hits), "total": len(hits),
                "names": sorted({h["name"] for h in hits}), "source": src}
    except Exception:                                          # noqa: BLE001
        return {"running": False, "total": 0, "names": [], "source": "error"}


def host_running(p: Paths) -> bool:
    """只回答「宿主是否在运行」这一个问题。"""
    return bool(host_running_now(p).get("running"))


def snapshot(p: Paths) -> dict:
    """界面与 CLI 共用的当前状态快照。"""
    current, switched_at = read_state(p)
    presets = list_presets(p)
    names = {x["name"] for x in presets}
    current_missing = bool(current) and current not in names

    changed = False
    changed_lines = 0
    if p.live.exists():
        changed, changed_lines = live_vs_preset(p, current)
    if not current:
        changed = False
        changed_lines = 0

    # 当前配置未记录时：正在使用的是否等于某个预设
    guessed = None
    if not current and p.live.exists():
        lt = read_text(p.live)
        for x in presets:
            try:
                if read_text(Path(x["path"])) == lt:
                    guessed = x["name"]
                    break
            except OSError:
                continue

    pats, src = guard_list(p)
    procs = list_processes(with_path=True)
    hits = match_processes(pats, procs)
    # 「启动 ChatGPT」联动状态：复用同一份进程快照，零额外枚举成本。
    # 注意只看 ChatGPT 自身，不等同于上面的 guard（宿主合并名单）。
    _cg_procs = chatgpt_processes(procs)
    chatgpt = {
        "running": bool(_cg_procs),
        "windowed": bool(visible_window_pids([x["pid"] for x in _cg_procs])),
        "count": len(_cg_procs),
    }

    # hero 要显示「当前预设的模型 / 供应商」，这里直接给出那条预设记录的摘要。
    # current_missing 时不给 —— 预设已经不存在了，再显示它的模型是误导。
    current_preset = None
    if current and not current_missing:
        for x in presets:
            if x["name"] == current:
                current_preset = {"name": x["name"], "model": x.get("model"),
                                  "provider": x.get("provider")}
                break

    return {
        "version": VERSION,
        "root": str(p.root),
        "live": str(p.live),
        "lib": str(p.lib),
        "guard_file": str(p.guard),
        "live_exists": p.live.exists(),
        "current": current,
        "current_missing": current_missing,
        "current_preset": current_preset,
        "switched_at": switched_at,
        "switched_at_human": human_time(switched_at),
        "changed": changed,
        "changed_lines": changed_lines,
        "no_state": current is None,
        "guessed": guessed,
        "presets": [dict(x, is_current=(x["name"] == current)) for x in presets],
        "guard": {
            "patterns": pats,
            "source": src,
            "source_text": guard_source_text(p, src),
            "running": bool(hits),
            "hits": aggregate_hits(hits),
            "total": len(hits),
        },
        "chatgpt": chatgpt,
    }


def format_hits(hits: list[dict]) -> list[str]:
    """被拦截时的进程明细（§6.4）。"""
    width = 30
    out = [f"    {'进程名':<{width}} {'PID':<8} 可执行文件"]
    for h in hits:
        out.append(f"    {h['name']:<{width}} {h['pid']:<8} {h['path'] or '(路径不可读)'}")
    return out


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run_switch(p: Paths, target: str, *, no_harvest: bool = False,
               force: bool = False, dry: bool = False,
               rep: Reporter | None = None) -> dict:
    """固定五步流程（§6.7）：检测 → 读状态 → 同步 → 启用 → 写状态。"""
    rep = rep or Reporter()
    warn_codes: list[str] = []

    try:
        validate_preset_name(target)
        tfile = preset_path(p, target)
        if not tfile.exists():
            raise CoreError(f"找不到预设「{target}」：{tfile}")

        # ---- 1 进程检测 ----
        pats, src = guard_list(p)
        hits = match_processes(pats)
        head = "[1/5] 检查宿主应用进程 ...... "
        if hits:
            if dry:
                rep.step(head + f"检测到 {len(hits)} 个进程（演练模式不拦截）")
            elif force:
                rep.step(head + f"检测到 {len(hits)} 个进程（已强制跳过）")
                rep.warn("    宿主应用正在运行，此刻同步可能拿到半成品，启用也可能被覆盖回去。")
            else:
                rep.step(head + f"检测到 {len(hits)} 个进程  ×")
                rep.err("[!] 检测到宿主应用正在运行，已中止：")
                rep.info("")
                for line in format_hits(hits):
                    rep.info(line)
                rep.info("")
                rep.info("    运行中的宿主应用会持续改写 config.toml：")
                rep.info("      · 此刻同步会拿到半成品")
                rep.info("      · 启用也会马上被覆盖回去")
                rep.info("")
                rep.info("    请先完全退出（含托盘图标）再操作。")
                rep.info("    确认无碍可强制；若认为误伤，可编辑：")
                rep.info(f"      {p.guard}")
                return {"ok": False, "blocked": True, "lines": rep.lines,
                        "warns": warn_codes, "target": target}
        else:
            rep.step(head + "未运行  OK")
            if src != "file":
                rep.info("      （" + guard_source_text(p, src) + "："
                         + ", ".join(pats) + "）")

        # ---- 2 读取状态 ----
        current, _ = read_state(p)
        if current and not preset_path(p, current).exists():
            rep.warn(f"[!] 状态记录指向的预设「{current}」已被删除，将按「未记录当前配置」继续。")
            rep.info("    正在使用的配置仍会照常备份；同步与启用不再往回写这个已消失的预设。")
            warn_codes.append("state-preset-missing")
            current = None
        rep.step("[2/5] 读取状态 ...... "
                 + (f"当前配置 = {current}" if current else "当前配置未记录"))

        # ---- 写前预备：历史目录必须可写 ----
        if not dry:
            _probe_writable(p)

        # ---- 3 同步 ----
        rep.step(f"[3/5] 同步正在使用的配置 -> 预设 {current or '(无)'}")
        harvest_done = False
        if no_harvest:
            rep.info("      已按 --no-harvest 跳过同步（仍会保底备份正在使用的配置）")
        elif not p.live.exists():
            rep.info("      正在使用的配置不存在，无需同步")
        elif not current:
            rep.warn("[!] 没有「当前配置」记录，正在使用的配置中的改动不会并入任何预设。")
            rep.info("    可执行「另存为新预设」把它固化为一个新预设。")
            warn_codes.append("no-state")
            if not dry:
                b = backup_live(p)
                rep.info(f"    已保底备份 -> {p.short(b)}")
        else:
            same = read_text(preset_path(p, current)) == read_text(p.live)
            if same:
                rep.step(f"[3/5] 同步正在使用的配置 -> 预设 {current} ...... 无变化，跳过")
            else:
                n, _ = diff_rows(read_text(preset_path(p, current)), read_text(p.live))
                if dry:
                    rep.info(f"      （演练）将把改动 {n} 行并入 {current}")
                    ts = now_ts()
                    rep.info(f"      （演练）同步前版本 -> "
                             f"{p.short(p.hist_presets / current / (ts + '.toml'))}")
                else:
                    b = backup_preset(p, current)
                    copy_file(p.live, preset_path(p, current))
                    rep.info(f"      改动 {n} 行已并入 {current}")
                    rep.info(f"      同步前版本 -> {p.short(b)}")
                harvest_done = True

        # ---- 4 启用 ----
        rep.step(f"[4/5] 启用 {current or '(无)'} -> {target}")
        if dry:
            ts = now_ts()
            rep.info(f"      （演练）正在使用的配置将被 {target}.toml 覆盖")
            rep.info(f"      （演练）启用前快照 -> "
                     f"{p.short(p.hist_live / ('config.toml.' + ts))}")
        else:
            if p.live.exists():
                b = backup_live(p)
            else:
                b = None
            copy_file(tfile, p.live)
            if b:
                rep.info(f"      正在使用的配置已替换；启用前快照 -> {p.short(b)}")
            else:
                rep.info("      正在使用的配置已创建（原先不存在）")

        # ---- 5 写状态 ----
        rep.step(f"[5/5] 更新状态 ...... 当前预设 = {target}")
        if not dry:
            write_state(p, target)

        rep.ok("[OK] 完成。请重启宿主应用使新配置生效"
               if not dry else "[OK] 演练完成，磁盘未发生任何变化")
        return {"ok": True, "blocked": False, "lines": rep.lines,
                "warns": warn_codes, "target": target,
                "harvested": harvest_done, "dry": dry}

    except CoreError as e:
        rep.err(f"[×] {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines,
                "warns": warn_codes, "target": target}
    except Exception as e:                                  # noqa: BLE001
        rep.err(f"[×] 未预期的错误，已中止：{type(e).__name__}: {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines,
                "warns": warn_codes, "target": target}


def run_harvest_only(p: Paths, *, force: bool = False, dry: bool = False,
                     rep: Reporter | None = None) -> dict:
    """只同步、不启用（FR-3.5）。正在使用的配置与状态均不变。"""
    rep = rep or Reporter()
    try:
        pats, src = guard_list(p)
        hits = match_processes(pats)
        if hits and not force and not dry:
            rep.err("[!] 检测到宿主应用正在运行，已中止：")
            for line in format_hits(hits):
                rep.info(line)
            rep.info("")
            rep.info("    请先完全退出（含托盘图标）再操作；确认无碍可强制。")
            return {"ok": False, "blocked": True, "lines": rep.lines}

        current, _ = read_state(p)
        if not current or not preset_path(p, current).exists():
            rep.warn("[!] 没有可同步的目标预设（状态记录缺失或指向的预设不存在）。")
            if p.live.exists() and not dry:
                b = backup_live(p)
                rep.info(f"    已保底备份正在使用的配置 -> {p.short(b)}")
                rep.info("    可执行「另存为新预设」把它固化为一个新预设。")
            return {"ok": False, "blocked": False, "lines": rep.lines,
                    "reason": "no-state"}

        if not p.live.exists():
            rep.err("[×] 正在使用的配置不存在，无法同步。")
            return {"ok": False, "blocked": False, "lines": rep.lines}

        same = read_text(preset_path(p, current)) == read_text(p.live)
        if same:
            rep.ok(f"[OK] 无需同步：正在使用的配置与预设「{current}」完全一致。")
            return {"ok": True, "blocked": False, "lines": rep.lines,
                    "harvested": False, "target": current}

        n, _ = diff_rows(read_text(preset_path(p, current)), read_text(p.live))
        if dry:
            rep.info(f"（演练）将把改动 {n} 行并入预设「{current}」。")
        else:
            _probe_writable(p)
            b = backup_preset(p, current)
            copy_file(p.live, preset_path(p, current))
            rep.info(f"改动 {n} 行已并入预设「{current}」。")
            rep.info(f"同步前版本 -> {p.short(b)}")
        rep.ok("[OK] 同步完成（正在使用的配置与状态记录均未改动）"
               if not dry else "[OK] 演练完成，磁盘未发生任何变化")
        return {"ok": True, "blocked": False, "lines": rep.lines,
                "harvested": True, "target": current, "changed_lines": n}

    except CoreError as e:
        rep.err(f"[×] {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines}
    except Exception as e:                                  # noqa: BLE001
        rep.err(f"[×] 未预期的错误，已中止：{type(e).__name__}: {e}")
        return {"ok": False, "blocked": False, "lines": rep.lines}


def run_save_as(p: Paths, name: str, *, set_current: bool = False,
                force: bool = False, rep: Reporter | None = None) -> dict:
    """把正在使用的配置另存为新预设（FR-8）。已存在则拒绝，不静默覆盖。"""
    rep = rep or Reporter()
    try:
        name = validate_preset_name(name)
        if not p.live.exists():
            raise CoreError(f"正在使用的配置不存在，无法另存：{p.live}")
        dest = preset_path(p, name)
        if dest.exists():
            raise CoreError(f"预设「{name}」已存在，未覆盖（如需替换请手动处理该文件）。")
        _probe_writable(p)
        copy_file(p.live, dest)
        rep.info(f"已从正在使用的配置创建预设：{name}.toml")
        rep.info(f"  路径 -> {p.short(dest)}")
        if set_current:
            write_state(p, name)
            rep.info(f"  已设为当前预设：{name}")
        rep.ok("[OK] 另存完成")
        return {"ok": True, "lines": rep.lines, "name": name}
    except CoreError as e:
        rep.err(f"[×] {e}")
        return {"ok": False, "lines": rep.lines}
    except Exception as e:                                  # noqa: BLE001
        rep.err(f"[×] 未预期的错误：{type(e).__name__}: {e}")
        return {"ok": False, "lines": rep.lines}


def run_diff(p: Paths, name: str) -> dict:
    """正在使用的配置 vs 指定预设（FR-9）。"""
    validate_preset_name(name)
    f = preset_path(p, name)
    if not f.exists():
        raise CoreError(f"找不到预设「{name}」。")
    if not p.live.exists():
        raise CoreError(f"正在使用的配置不存在：{p.live}")
    old = read_text(f)
    new = read_text(p.live)
    changed, rows = diff_rows(old, new)
    return {"ok": True, "name": name, "changed": changed, "rows": rows,
            "same": changed == 0}


def run_guard(p: Paths) -> dict:
    """只做进程检测并打印结果（诊断用，不写任何文件）。"""
    pats, src = guard_list(p)
    procs = list_processes(with_path=True)
    hits = match_processes(pats, procs)
    return {
        "patterns": pats,
        "source": src,
        "source_text": guard_source_text(p, src),
        "running": bool(hits),
        "hits": aggregate_hits(hits),
        "total": len(hits),
        "scanned": len(procs),
    }
