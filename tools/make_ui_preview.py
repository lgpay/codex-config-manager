# -*- coding: utf-8 -*-
"""把 src/ui.py 的界面导成一个**可交互的静态 HTML 预览**，用于人工核对布局。

做法：取 ui.HTML 原文，在末尾追加一层 mock 的 `window.pywebview.api`，再手动派发
`pywebviewready` 事件。这样界面会用假数据完整渲染，菜单、卡片右键、按钮提示都能点，
但**不会读写任何真实配置、不发任何网络请求**。

注意：这里只做「注入 mock」，**不改动 ui.HTML 的任何字节**，所以预览与真实界面同源。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import core  # noqa: E402
import ui  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "ui-preview.html")

MOCK = r"""
<script>
/* ===== 仅供预览：mock 掉 pywebview 桥 =====
   不读写任何真实配置、不发任何网络请求；所有动作都在浏览器里就地返回。 */
const NOW = new Date();
const MOCK_STATE = {
  version: "__VERSION__",
  root: "C:\\Users\\you\\.codex",
  live: "C:\\Users\\you\\.codex\\config.toml",
  lib: "C:\\Users\\you\\.codex\\configs",
  guard_file: "C:\\Users\\you\\.codex\\configs\\.guard",
  live_exists: true,
  current: "official",
  current_missing: false,
  switched_at: null,
  switched_at_human: "2026-09-17 08:20:11",
  changed: false,
  changed_lines: 0,
  no_state: false,
  guessed: null,
  presets: [
    {name: "official", model: "", provider: "", base_url: "", env_key: "", is_current: true},
    {name: "aibank", model: "gpt-5.6-luna", provider: "aibank",
     base_url: "https://aibank.eu.org/v1", env_key: "AIBANK_API_KEY", is_current: false},
    {name: "local-ollama", model: "qwen3:14b", provider: "local",
     base_url: "http://127.0.0.1:11434/v1", env_key: "LOCAL_API_KEY", is_current: false}
  ],
  guard: {patterns: ["ChatGPT.exe", "codex.exe", "codex-*.exe"], source: "default",
          source_text: "宿主进程名单为内置默认", running: false, hits: [], total: 0},
  chatgpt: {running: false, windowed: false, count: 0}
};
const PREVIEW_PRESET = 'model_reasoning_effort = "medium"\nmodel = "gpt-5.6-luna"\n'
  + 'model_provider = "aibank"\n\n[model_providers.aibank]\nname = "AIBank"\n'
  + 'base_url = "https://aibank.eu.org/v1"\nenv_key = "AIBANK_API_KEY"\nwire_api = "responses"\n';

function _lines(kind, arr){ return arr.map(t => ({kind: kind, text: t})); }

window.pywebview = { api: {
  get_state: async () => JSON.parse(JSON.stringify(MOCK_STATE)),
  chatgpt_state: async () => ({running:false, windowed:false, count:0}),
  initial: async () => ({path_setup: false, preset: null}),
  path_info: async () => ({codex_home: MOCK_STATE.root, configs_dir: MOCK_STATE.lib,
    codex_exists: true, config_exists: true, configs_exists: true, preset_count: 3,
    env_controlled: false, settings_status: "ok"}),
  validate_paths: async () => ({ok: true, codex_home: MOCK_STATE.root,
    configs_dir: MOCK_STATE.lib, codex_exists: true, config_exists: true,
    configs_exists: true, preset_count: 3}),
  choose_folder: async () => ({ok: false, cancelled: true}),
  choose_config_file: async () => ({ok: false, cancelled: true}),
  apply_paths: async () => ({ok: true, message: "（预览）配置位置未真的切换"}),
  guard_info: async () => ({hits: [], patterns: MOCK_STATE.guard.patterns,
    source: "default", source_text: MOCK_STATE.guard.source_text}),
  confirm_info: async () => ({no_state: false, will_harvest: false,
    current: "official", changed_lines: 0}),
  diff: async () => ({same: false, changed: 3, rows: [
    {kind: "ctx", text: 'model_reasoning_effort = "medium"'},
    {kind: "del", text: ''}, {kind: "add", text: 'model = "gpt-5.6-luna"'},
    {kind: "add", text: 'model_provider = "aibank"'}]}),
  history_list: async () => ({ok: true, items: [
    {id: "h1", source_name: "预设 official", time: "2026-09-17 03:32:52", size: 3161},
    {id: "h2", source_name: "当前配置", time: "2026-09-17 02:39:43", size: 1915}]}),
  history_preview: async () => ({ok: true, same: false, changed: 2, size_before: 1915,
    size_after: 1990, target: "预设 official", confirm_token: "preview-token",
    rows: [{kind: "add", text: 'model = "gpt-5.6-luna"'}]}),
  launch_chatgpt: async () => ({ok: true, message: "（预览）已请求启动 ChatGPT。"}),
  preset_form: async (name) => ({
    ok: true, preset: name, is_current: name === MOCK_STATE.current,
    model: 'gpt-5.6-luna', model_provider: 'aibank', reasoning: 'medium',
    prov_name: 'AIBank', base_url: 'https://aibank.eu.org/v1',
    env_key: 'AIBANK_API_KEY', env_set: true, wire_api: 'responses',
    providers: ['aibank'], blocks: {aibank: {name: 'AIBank',
      base_url: 'https://aibank.eu.org/v1', env_key: 'AIBANK_API_KEY',
      wire_api: 'responses'}},
    orig_provider_id: 'aibank', guard_running: false}),
  preview_edit: async () => ({same: true, rename: false, changed: 0,
    size_before: 215, size_after: 215, errors: {}, rows: []}),
  preview_new: async () => ({ok: true}),
  suggest_env_key: async () => 'MOCK_API_KEY',
  prepare_key_save: async () => ({ok: true, overwrite: false, token: "preview"}),
  prepare_models: async () => ({ok: false, message: "（预览不联网）", errors: {}}),
  prepare_model_call: async () => ({ok: false, message: "（预览不联网）", errors: {}}),
  prepare_connection: async () => ({ok: false, message: "（预览不联网）", errors: {}}),
  execute_network: async () => ({ok: false, message: "（预览不联网）"}),
  local_check: async () => ({message: "（预览）本地检查通过。", errors: {}}),
  run: async () => ({ok: true}),
  poll: async () => ({running: false, result: {ok: true},
    lines: _lines("ok", ["（预览）这里不会真的执行任何操作。"])})
}};
window.dispatchEvent(new Event("pywebviewready"));
</script>
"""


def main():
    html = ui.HTML
    if "pywebviewready" not in html:
        raise SystemExit("ui.HTML 里没找到 pywebviewready，预览注入点已失效")
    # 版本号跟着 core.VERSION 走，发版后预览不会显示旧版本
    mock = MOCK.replace("__VERSION__", core.VERSION)
    out = html.replace("</body>", mock + "</body>")
    if out == html:
        raise SystemExit("注入失败：ui.HTML 里没有 </body>")
    # 预览是给人看的，不打包；不进 git 白名单也无所谓
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    print("已生成预览：%s（%d 字符）" % (OUT, len(out)))


if __name__ == "__main__":
    main()
