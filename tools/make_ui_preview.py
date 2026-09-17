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
  current: "aibank",
  current_missing: false,
  /* IMP-032：hero 要显示当前预设的模型 / 供应商，这里给那条预设的摘要。
     用 aibank 当当前预设，这样第二行能看到真实的「模型 / 供应商 / 应用时间」。 */
  current_preset: {name: "aibank", model: "gpt-5.6-luna", provider: "aibank"},
  switched_at: null,
  switched_at_human: "2026-09-17 08:20:11",
  changed: false,
  changed_lines: 0,
  no_state: false,
  guessed: null,
  presets: [
    {name: "official", model: "", provider: "", base_url: "", env_key: "", is_current: false},
    {name: "aibank", model: "gpt-5.6-luna", provider: "aibank",
     base_url: "https://aibank.eu.org/v1", env_key: "AIBANK_API_KEY", is_current: true},
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
    current: "aibank", changed_lines: 0}),
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

# 场景切换条：真实界面靠 4 秒轮询更新 guard.running / chatgpt，预览里给个手动开关，
# 方便一眼看全「Codex 运行中 / 未运行」「ChatGPT 未启动 / 后台驻留 / 运行中」各态下
# 按钮文字与边栏底部状态行的样子。**只调用产品自己的 render* 函数**。
SCENE_BAR = r"""
<script>
(function(){
  var SCENES = [
    {label:"通常（均未运行）", guard:false, cg:false, win:false, banner:""},
    {label:"当前配置有更新",   guard:false, cg:false, win:false, banner:"dirty"},
    {label:"Codex 运行中",     guard:true,  cg:false, win:false, banner:""},
    {label:"ChatGPT 后台驻留", guard:false, cg:true,  win:false, banner:""},
    {label:"ChatGPT 已打开",   guard:false, cg:true,  win:true,  banner:""},
    {label:"预设已不存在",     guard:false, cg:false, win:false, banner:"missing"}
  ];
  var bar = document.createElement("div");
  bar.style.cssText = "position:fixed;right:10px;bottom:10px;z-index:9999;display:flex;"
    + "gap:6px;align-items:center;flex-wrap:wrap;max-width:70vw;background:#fff;"
    + "border:1px solid #ccd2dc;border-radius:8px;padding:6px 9px;"
    + "box-shadow:0 4px 14px rgba(0,0,0,.13);font:12px/1.4 system-ui,'Segoe UI',sans-serif";
  var tag = document.createElement("span");
  tag.textContent = "状态场景：";
  tag.style.cssText = "color:#6b7280;font-weight:650";
  bar.appendChild(tag);
  SCENES.forEach(function(sc){
    var b = document.createElement("button");
    b.textContent = sc.label;
    b.style.cssText = "padding:4px 9px;border-radius:6px;border:1px solid #ccd2dc;"
      + "background:#f6f8fb;cursor:pointer;font:inherit";
    b.onclick = function(){
      MOCK_STATE.guard = Object.assign({}, MOCK_STATE.guard,
        {running: sc.guard, total: sc.guard ? 2 : 0});
      MOCK_STATE.chatgpt = {running: sc.cg, windowed: sc.win, count: sc.cg ? 9 : 0};
      MOCK_STATE.changed = (sc.banner === "dirty");
      MOCK_STATE.changed_lines = (sc.banner === "dirty") ? 4 : 0;
      MOCK_STATE.current_missing = (sc.banner === "missing");
      // 走产品自己的重绘路径 —— 看到的就是真实界面会呈现的效果
      STATE = JSON.parse(JSON.stringify(MOCK_STATE));
      renderHero(); renderStatus();
      renderSwitchButton(); renderChatGPTButton();
      b.blur();
    };
    bar.appendChild(b);
  });
  document.body.appendChild(bar);
  bar.querySelector("button").click();   // 初始落到第一个场景
})();
</script>
"""


def main():
    html = ui.HTML
    if "pywebviewready" not in html:
        raise SystemExit("ui.HTML 里没找到 pywebviewready，预览注入点已失效")
    # 版本号跟着 core.VERSION 走，发版后预览不会显示旧版本
    mock = MOCK.replace("__VERSION__", core.VERSION)
    # 顺序很重要：mock（含 MOCK_STATE + 派发 ready）在前，场景条在后 ——
    # 场景条要操作 MOCK_STATE、调 render*，必须等界面已经渲染过一次。
    out = html.replace("</body>", mock + SCENE_BAR + "</body>")
    if out == html:
        raise SystemExit("注入失败：ui.HTML 里没有 </body>")
    # 预览是给人看的，不打包；不进 git 白名单也无所谓
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    print("已生成预览：%s（%d 字符）" % (OUT, len(out)))


if __name__ == "__main__":
    main()
