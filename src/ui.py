# -*- coding: utf-8 -*-
"""图形界面资源：HTML / CSS / JS 全部内联，避免打包后资源路径失效。

UI 重做（2026-09-17，IMP-021 ~ IMP-024）：
  * 顶栏新增「配置 / 工具 / 帮助」三个下拉菜单，收纳原右侧「操作」栏的全部低频功能；
  * 预设卡片支持右键菜单（切换 / 编辑 / 差异 / 复制 / 另存 / 删除）；
  * 常驻动作只剩两个按钮：列表标题行右侧的「切换」、状态条右侧的「启动 ChatGPT」；
  * 运行状态不再单独占 pill ——「Codex 正在运行不能切换」并入切换按钮提示，
    ChatGPT「已打开 / 后台驻留 / 未运行」并入启动按钮提示；
  * 状态条只保留必须显眼的横幅（未同步变化 / 状态记录失效 / 状态读取失败）。

功能只实现一份：菜单、右键与按钮共用同一组具名函数（doSwitch / doDiff / doCopy /
doDelete / doSaveNew / doHarvest …），原按钮 id 全部保留，避免逻辑分叉。
宿主进程保护、覆盖配置确认、第三方连接测试的 TLS / 不跟随跳转 / 超时 / 费用确认
等安全逻辑与文案保持不变，未弱化任何安全断言。
"""

APP_TITLE = "Codex 配置管理器"

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codex 配置管理器</title>
<style>
:root{
  --bg:#eef0f4; --panel:#ffffff; --panel-2:#f7f8fa; --line:#e3e6ec; --line-2:#eef0f4;
  --fg:#1b1f24; --fg-2:#5b6472; --fg-3:#8b95a5;
  --accent:#0f9d76; --accent-2:#0b7f5f; --accent-soft:#e6f6f0;
  --ok:#0f9d76; --warn:#b7791f; --warn-soft:#fdf4e3; --danger:#d14343; --danger-soft:#fdecec;
  --shadow:0 1px 2px rgba(16,24,40,.06), 0 6px 18px rgba(16,24,40,.06);
  --mono:"Cascadia Mono","Consolas","SFMono-Regular","Microsoft YaHei UI",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Hiragino Sans GB",sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#17191d; --panel:#212429; --panel-2:#1b1e22; --line:#2e3238; --line-2:#282c31;
    --fg:#e7eaee; --fg-2:#a6aeb9; --fg-3:#767f8c;
    --accent:#2bbd92; --accent-2:#25a67f; --accent-soft:#16302a;
    --ok:#2bbd92; --warn:#d9a04a; --warn-soft:#332c1b; --danger:#e46a6a; --danger-soft:#3a2020;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.32);
    color-scheme:dark;
  }
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{
  font-family:var(--sans); background:var(--bg); color:var(--fg);
  font-size:13px; line-height:1.55; overflow:hidden;
  -webkit-font-smoothing:antialiased;
}
.app{height:100vh;display:grid;grid-template-rows:auto auto minmax(120px,1fr) auto minmax(86px,108px);gap:0}

/* ---------- 顶栏 + 菜单栏 ---------- */
.topbar{
  display:flex;align-items:center;gap:10px;padding:6px 16px;
  background:var(--panel);border-bottom:1px solid var(--line);
  position:relative;z-index:30;
}
.topbar .logo{
  width:26px;height:26px;border-radius:7px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;flex:0 0 auto;
}
.topbar .logo img{width:100%;height:100%;display:block;object-fit:cover}
.topbar h1{font-size:13.5px;font-weight:650;margin:0;letter-spacing:.2px;white-space:nowrap}
.topbar .ver{margin-left:auto;color:var(--fg-3);font-size:11.5px;font-variant-numeric:tabular-nums}

/* 菜单栏：配置 / 工具 / 帮助 三个下拉，收纳原「操作」栏的低频功能 */
.menubar{display:flex;align-items:center;gap:2px;margin-left:8px;min-width:0}
.mgroup{position:relative}
.mtitle{
  font-size:12.5px;font-weight:600;padding:4px 10px;border-radius:7px;
  background:transparent;border:1px solid transparent;color:var(--fg-2);
}
.mtitle:hover:not(:disabled){background:var(--panel-2);border-color:transparent;color:var(--fg)}
.mgroup.open .mtitle{background:var(--accent-soft);border-color:rgba(15,157,118,.22);color:var(--ok)}
.mpanel{
  display:none;position:absolute;left:0;top:calc(100% + 5px);z-index:45;
  min-width:214px;padding:5px;border-radius:10px;
  background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);
}
.mgroup.open .mpanel{display:block}
.mi{
  width:100%;justify-content:flex-start;text-align:left;border-radius:7px;
  background:transparent;border:1px solid transparent;
  padding:6px 10px;font-size:12.5px;font-weight:550;color:var(--fg);
}
.mi:hover:not(:disabled){background:var(--panel-2);border-color:transparent}
.mi.danger{color:var(--danger)}
.mi.danger:hover:not(:disabled){background:var(--danger-soft)}
.msep{height:1px;background:var(--line);margin:4px 6px}

/* ---------- 右键菜单（预设卡片） ---------- */
.ctxmenu{
  position:fixed;left:0;top:0;z-index:70;min-width:198px;padding:5px;border-radius:10px;
  background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);
  display:none;
}
.ctxmenu.on{display:block}
.ctxhead{font-size:11px;color:var(--fg-3);font-family:var(--mono);
  padding:4px 10px 6px;border-bottom:1px solid var(--line);margin-bottom:4px;word-break:break-all}
/* 包住按钮的壳：按钮 disabled 时由外壳承担 title 提示（原生 tooltip 在禁用控件上不可靠） */
.bwrap{display:inline-flex;align-items:center}

/* ---------- 当前配置 hero（首页主区） ---------- */
.hero{
  background:linear-gradient(180deg,var(--panel) 0%,var(--panel-2) 100%);
  border-bottom:1px solid var(--line);
  padding:10px 16px 11px;display:flex;gap:14px;align-items:center;
}
.hero.dirty{background:linear-gradient(180deg,var(--warn-soft),var(--panel-2));
  border-bottom-color:rgba(183,121,31,.3)}
.hero .hcard{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.hero .ht{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.hero .hname{font-size:16px;font-weight:700;letter-spacing:.2px}
.hero .htag{font-size:10.5px;padding:1px 8px;border-radius:999px;font-weight:600;white-space:nowrap;
  background:var(--accent-soft);color:var(--ok)}
.hero .htag.mute{background:var(--panel-2);color:var(--fg-3);border:1px solid var(--line)}
.hero .hmeta{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--mono);
  font-size:11.5px;color:var(--fg-2)}
.hero .hmeta span.k{color:var(--fg-3)}
.hero .hguide{font-size:11.5px;color:var(--fg-3);line-height:1.6}
.hero .hguide b{color:var(--fg-2);font-weight:650}
.hero .hacts{display:flex;flex-direction:column;gap:6px;flex:0 0 auto}
.hero .hacts button{justify-content:center;min-width:132px}
.hero.empty .hname{color:var(--fg-2);font-weight:650;font-size:14px}
.hero.empty .hguide{color:var(--fg-2)}
.hero .mute{background:var(--panel-2);color:var(--fg-3);border:1px solid var(--line)}

/* ---------- 紧凑状态条（只放「必须显眼」的横幅；没有横幅时整条折叠） ----------
   运行状态不再单独占位置：宿主「运行中 / 未运行」并入边栏「切换」按钮提示，
   ChatGPT「已打开 / 后台驻留 / 未运行」并入边栏「启动 ChatGPT」按钮提示
   （见 renderSwitchButton / renderChatGPTButton）。 */
.status{display:none;background:var(--panel);border-bottom:1px solid var(--line);padding:7px 16px 8px}
.status.on{display:block}
.statusbanners{display:flex;flex-direction:column;gap:5px}
.statusbanners:empty{display:none}
.meta{color:var(--fg-2);font-size:12px}
.meta b{color:var(--fg);font-weight:650}
.banner{
  border-radius:8px;padding:8px 11px;font-size:12px;line-height:1.6;
  display:flex;gap:8px;align-items:flex-start;
}
.banner.warn{background:var(--warn-soft);color:var(--warn);border:1px solid rgba(183,121,31,.25)}
.banner.bad{background:var(--danger-soft);color:var(--danger);border:1px solid rgba(209,67,67,.25)}
.banner.info{background:var(--panel-2);color:var(--fg-2);border:1px solid var(--line)}
.banner .ico{flex:0 0 auto;font-weight:700}
.banner .txt{flex:1;min-width:0}
.banner table{border-collapse:collapse;margin-top:6px;font-family:var(--mono);font-size:11px;width:100%}
.banner table td{padding:1px 10px 1px 0;vertical-align:top;color:var(--fg-2);word-break:break-all}
.banner table td:first-child{white-space:nowrap;color:var(--fg)}
.banner details{margin-top:0}
.banner details summary{cursor:pointer;font-size:11.5px;font-weight:600;list-style:none;
  display:inline-block;padding:1px 0;user-select:none;color:var(--fg)}
.banner details summary::-webkit-details-marker{display:none}
.banner details summary:before{content:"▸ ";display:inline-block;transition:transform .15s}
.banner details[open] summary:before{content:"▾ "}
.banner .detbox{margin-top:6px}
.link{color:inherit;text-decoration:underline;cursor:pointer;opacity:.85}

/* ---------- 主体：左侧预设列表 + 右侧操作边栏 ----------
   常驻动作只剩两个按钮，都放在预设列表**右侧的边栏**里 ——「切换」与
   「启动 ChatGPT」。其余功能进顶部菜单栏与卡片右键菜单。 */
.body{display:grid;grid-template-columns:minmax(0,1fr) 164px;gap:12px;padding:10px 16px;min-height:0}
.colhead{display:flex;align-items:center;gap:10px;flex:0 0 auto}
.col-title{font-size:11.5px;color:var(--fg-3);font-weight:650;letter-spacing:.4px;
  margin:0 0 7px 2px;text-transform:uppercase}
.colhead .col-title{margin:0}
/* 右侧操作边栏：两个常驻按钮（切换 / 启动 ChatGPT），固定宽度、不随列表伸缩 */
.sidebar{display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0}
.sidebar .col-title{margin:0 0 0 2px}
.sidebar .bwrap{display:block;width:100%}
.sidebar button{
  width:100%;justify-content:center;text-align:center;white-space:normal;
  padding:8px 10px;line-height:1.35;min-height:36px;
}
#b-chatgpt{background:var(--panel-2)}
.presets{min-height:0;display:flex;flex-direction:column;flex:1}
.plist{overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:2px 4px 4px 2px;min-height:0;flex:1}
.plist::-webkit-scrollbar{width:9px}
.plist::-webkit-scrollbar-thumb{background:var(--line);border-radius:6px;border:2px solid transparent;background-clip:padding-box}
.card{
  background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:8px 12px;cursor:pointer;transition:border-color .12s,box-shadow .12s,transform .06s;
  position:relative;
}
.card:hover{border-color:#c9cfda}
.card:active{transform:scale(.995)}
.card.sel{border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 18%,transparent)}
.card .l1{display:flex;align-items:center;gap:7px}
.card .nm{font-weight:650;font-size:13px}
.card .tag{font-size:10.5px;padding:1px 7px;border-radius:999px;font-weight:600;
  background:var(--accent-soft);color:var(--ok)}
.card .tag.dirty{background:var(--warn-soft);color:var(--warn)}
.card .l2{margin-top:3px;display:flex;gap:14px;flex-wrap:wrap;
  font-family:var(--mono);font-size:11px;color:var(--fg-2)}
.card .l2 span.k{color:var(--fg-3)}
.empty{
  border:1px dashed var(--line);border-radius:10px;padding:22px 16px;text-align:center;
  color:var(--fg-2);background:var(--panel)
}
.empty h3{margin:0 0 6px;font-size:13px;color:var(--fg)}
.empty p{margin:0 0 10px;font-size:12px}
.empty.onboard{text-align:left;padding:18px 18px}
.empty.onboard h3{text-align:left;font-size:14px}
.empty.onboard p{text-align:left}
.empty.onboard ol.steps{margin:8px 0 10px;padding-left:20px;color:var(--fg-2);font-size:12px;line-height:1.9}
.empty.onboard ol.steps b{color:var(--fg)}
.empty.onboard .primary{margin-top:2px}
.card .dotmark{position:absolute;left:-4px;top:50%;width:6px;height:6px;border-radius:50%;
  transform:translateY(-50%);display:none}
.card .dotmark.on{display:block}

/* ---------- 按钮 ---------- */
button{
  font-family:var(--sans);font-size:12px;font-weight:600;color:var(--fg);
  background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:6px 11px;cursor:pointer;text-align:left;transition:background .12s,border-color .12s,opacity .12s;
  display:flex;align-items:center;gap:8px;flex:0 0 auto;
}
button:hover:not(:disabled){background:var(--panel-2);border-color:#c9cfda}
button:disabled{opacity:.45;cursor:not-allowed}
button.primary{
  background:var(--accent);border-color:var(--accent);color:#fff;
  padding:8px 11px;font-size:12.5px;justify-content:center;
}
button.primary:hover:not(:disabled){background:var(--accent-2);border-color:var(--accent-2)}
button.ghost{background:transparent}
button.danger{color:var(--danger);border-color:rgba(209,67,67,.35)}
button.danger:hover:not(:disabled){background:var(--danger-soft)}

/* ---------- 日志区 ---------- */
.console{
  background:var(--panel);border-top:1px solid var(--line);
  display:flex;flex-direction:column;min-height:0;overflow:hidden;
}
.console .head{
  display:flex;align-items:center;gap:10px;padding:7px 16px 6px;
  border-bottom:1px solid var(--line-2);
}
.console .head .t{font-size:11.5px;color:var(--fg-3);font-weight:650;letter-spacing:.4px}
.console .head .s{margin-left:auto;font-size:11px;color:var(--fg-3)}
.spin{width:11px;height:11px;border:2px solid var(--line);border-top-color:var(--accent);
  border-radius:50%;animation:sp .7s linear infinite;display:none}
.spin.on{display:block}
@keyframes sp{to{transform:rotate(360deg)}}
.log{flex:1;overflow-y:auto;padding:7px 16px 12px;font-family:var(--mono);font-size:11.5px;
  line-height:1.75;white-space:pre-wrap;word-break:break-all}
.log::-webkit-scrollbar{width:9px}
.log::-webkit-scrollbar-thumb{background:var(--line);border-radius:6px;border:2px solid transparent;background-clip:padding-box}
.log .l{display:block}
.log .step{color:var(--fg);font-weight:600}
.log .info{color:var(--fg-2)}
.log .ok{color:var(--ok);font-weight:600}
.log .warn{color:var(--warn)}
.log .err{color:var(--danger);font-weight:600}
.log .hintline{color:var(--fg-3)}

/* ---------- 弹层 ---------- */
.backdrop{
  position:fixed;inset:0;background:rgba(15,20,28,.42);display:none;
  align-items:center;justify-content:center;padding:28px;z-index:50;
}
.backdrop.on{display:flex}
.modal{
  background:var(--panel);border-radius:12px;box-shadow:var(--shadow);
  width:min(640px,100%);min-width:0;max-height:100%;display:flex;flex-direction:column;overflow:hidden;
}
.modal.wide{width:min(760px,100%)}
.modal h2{margin:0;font-size:14px;font-weight:650;padding:14px 18px 10px}
.modal .mbody{min-width:0;padding:0 18px 6px;overflow-y:auto;overflow-x:hidden;font-size:12.5px;line-height:1.7;color:var(--fg-2)}
.modal .mbody b{color:var(--fg)}
.modal .mfoot{display:flex;gap:8px;justify-content:flex-end;padding:14px 18px 16px}
.modal .mfoot button{justify-content:center;min-width:84px}
.modal .mfoot button.primary{color:#fff}
input[type=text],input[type=password],.secret-field input{
  width:100%;min-width:0;height:34px;padding:7px 11px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel-2);color:var(--fg);font-family:var(--mono);font-size:12.5px;outline:none;
}
input[type=text]:focus,input[type=password]:focus,.secret-field input:focus{border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 18%,transparent)}
input[type=text]:disabled,input[type=password]:disabled,.secret-field input:disabled{opacity:.5;cursor:not-allowed}
.secret-field{display:flex;align-items:stretch;width:100%;min-width:0;height:34px;gap:0}
.secret-field input{flex:1 1 auto;min-width:0;width:auto;border-top-right-radius:0;border-bottom-right-radius:0;overflow:hidden;text-overflow:clip}
.secret-field button{flex:0 0 52px;width:52px;min-width:52px;height:34px;padding:0 7px;justify-content:center;border-left:0;border-top-left-radius:0;border-bottom-left-radius:0;font-size:11.5px;white-space:nowrap}
.secret-field button:focus-visible{position:relative;z-index:1}
select{
  width:100%;padding:7px 9px;border-radius:8px;border:1px solid var(--line);
  background:var(--panel-2);color:var(--fg);font-family:var(--sans);font-size:12.5px;
  outline:none;cursor:pointer;
}
select:focus{border-color:var(--accent);box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 18%,transparent)}
.fieldlbl{font-size:11.5px;color:var(--fg-3);margin:10px 0 5px}
.errmsg{color:var(--danger);font-size:12px;min-height:18px;margin-top:6px}

/* ---------- 配置编辑表单 ---------- */
.fgrid{display:grid;grid-template-columns:106px minmax(0,1fr);gap:8px 12px;align-items:center;margin:2px 0 0;min-width:0}
.fgrid .fl{font-size:12px;color:var(--fg-2);text-align:right;line-height:1.4;word-break:break-all;min-width:0}
.fgrid .fi,.fgrid>div,.fgrid>input,.fgrid>select,#w-third,#w-third>div{min-width:0}
.fsec{grid-column:1/-1;margin:14px 0 0;padding-top:11px;border-top:1px solid var(--line);
  font-size:11.5px;color:var(--fg-3);font-weight:650;letter-spacing:.3px;
  display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.fsec.off{color:var(--warn)}
.fsec .offnote{display:none;font-weight:400;letter-spacing:0;color:var(--warn);font-size:11px}
.fsec.off .offnote{display:inline}
.fgrid .fi input:disabled,.fgrid .fi select:disabled{opacity:.5;cursor:not-allowed}
.fsec code{font-family:var(--mono);font-size:11px;font-weight:400;color:var(--fg-2);
  background:var(--panel-2);border:1px solid var(--line);padding:0 5px;border-radius:4px}
.fhint{font-size:11px;color:var(--fg-3);margin-top:5px;line-height:1.6}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:5px}
.chip{font-size:11px;font-family:var(--mono);padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);background:var(--panel-2);color:var(--fg-2);cursor:pointer}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip.on{border-color:var(--accent);background:var(--accent-soft);color:var(--ok);font-weight:600}
.fnote{font-size:11.5px;color:var(--fg-2);background:var(--panel-2);border:1px solid var(--line);
  border-radius:8px;padding:8px 11px;line-height:1.6;margin:12px 0 0}
.fnote.warn{background:var(--warn-soft);border-color:rgba(183,121,31,.25);color:var(--warn)}
.fnote.info{background:var(--accent-soft);border-color:rgba(15,157,118,.22);color:var(--ok)}
.fnote code{font-family:var(--mono);font-size:11px;background:rgba(0,0,0,.06);padding:0 4px;border-radius:4px}
@media (prefers-color-scheme: dark){ .fnote code{background:rgba(255,255,255,.08)} }
.tagline{font-size:10.5px;padding:1px 7px;border-radius:999px;font-weight:600;white-space:nowrap}
.tagline.on{background:var(--accent-soft);color:var(--ok)}
.tagline.off{background:var(--panel-2);color:var(--fg-3);border:1px solid var(--line)}
.errbox{display:none;margin-top:11px;font-size:12px;color:var(--danger);line-height:1.7;
  background:var(--danger-soft);border:1px solid rgba(209,67,67,.25);border-radius:8px;padding:8px 11px}
.errbox.on{display:block}
.input-bad{border-color:var(--danger) !important}
.diffwrap{margin-top:12px}
.diffwrap .diff{max-height:24vh}
.diff{font-family:var(--mono);font-size:11.5px;line-height:1.65;background:var(--panel-2);
  border:1px solid var(--line);border-radius:8px;max-height:52vh;overflow:auto;padding:6px 0}
.diff .r{padding:0 12px;white-space:pre-wrap;word-break:break-all}
.diff .add{background:rgba(15,157,118,.10);color:var(--ok)}
.diff .del{background:rgba(209,67,67,.09);color:var(--danger)}
.diff .ctx{color:var(--fg-2)}
.diff .gap{color:var(--fg-3);text-align:center;background:var(--line-2);font-size:10.5px;
  letter-spacing:2px;padding:1px 0}
.diffinfo{font-size:11.5px;color:var(--fg-3);margin:8px 0 6px}
.gtable{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:11px}
.gtable th{text-align:left;color:var(--fg-3);font-weight:600;padding:4px 10px 4px 0;
  border-bottom:1px solid var(--line);font-family:var(--sans);font-size:11px}
.gtable td{padding:3px 10px 3px 0;color:var(--fg-2);vertical-align:top;word-break:break-all;
  border-bottom:1px solid var(--line-2)}
.gtable td.nm{color:var(--fg);white-space:nowrap}
.toast{
  position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(10px);
  background:var(--fg);color:var(--bg);padding:8px 16px;border-radius:999px;font-size:12.5px;
  font-weight:600;opacity:0;pointer-events:none;transition:opacity .18s,transform .18s;z-index:60;
}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
.help-sec{margin:12px 0 0;padding-top:10px;border-top:1px solid var(--line)}
.help-sec h3{font-size:12.5px;color:var(--fg);margin:0 0 6px}
.help-sec ul{margin:4px 0 0;padding-left:18px;color:var(--fg-2);font-size:12px;line-height:1.85}
.help-sec ul b{color:var(--fg)}
.help-sec p{margin:6px 0 0;font-size:12px;color:var(--fg-2)}
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="logo"><img src="codex-icon.png" alt=""></div>
    <h1>Codex 配置管理器</h1>
    <nav class="menubar" id="menubar">
      <div class="mgroup">
        <button class="mtitle" id="m-config" aria-haspopup="menu" aria-expanded="false">配置</button>
        <div class="mpanel" role="menu" aria-labelledby="m-config">
          <button class="mi" id="b-new" role="menuitem">新建配置向导…</button>
          <button class="mi" id="b-edit" role="menuitem" disabled>编辑所选配置…</button>
          <button class="mi" id="b-save" role="menuitem">另存为新预设…</button>
          <div class="msep"></div>
          <button class="mi" id="b-copy" role="menuitem" disabled>复制所选配置…</button>
          <button class="mi danger" id="b-delete" role="menuitem" disabled>删除所选配置…</button>
        </div>
      </div>
      <div class="mgroup">
        <button class="mtitle" id="m-tools" aria-haspopup="menu" aria-expanded="false">工具</button>
        <div class="mpanel" role="menu" aria-labelledby="m-tools">
          <button class="mi" id="b-harvest" role="menuitem">只同步当前预设</button>
          <button class="mi" id="b-diff" role="menuitem" disabled>查看差异</button>
          <button class="mi" id="b-history" role="menuitem">从历史版本恢复…</button>
          <div class="msep"></div>
          <button class="mi" id="b-guard" role="menuitem">诊断宿主进程</button>
          <button class="mi" id="b-dry" role="menuitem" disabled>演练（不写入）</button>
          <button class="mi" id="b-paths" role="menuitem">配置位置…</button>
        </div>
      </div>
      <div class="mgroup">
        <button class="mtitle" id="m-help" aria-haspopup="menu" aria-expanded="false">帮助</button>
        <div class="mpanel" role="menu" aria-labelledby="m-help">
          <button class="mi" id="b-help" role="menuitem">使用帮助</button>
          <button class="mi" id="b-recovery" role="menuitem">手动恢复说明</button>
          <div class="msep"></div>
          <button class="mi" id="b-about" role="menuitem">关于</button>
        </div>
      </div>
    </nav>
    <div class="ver" id="ver"></div>
  </header>

  <section class="hero" id="hero"></section>

  <main class="body">
    <div class="presets">
      <div class="colhead">
        <div class="col-title">预设</div>
      </div>
      <div class="plist" id="plist"></div>
    </div>
    <aside class="sidebar" id="sidebar">
      <div class="col-title">操作</div>
      <span class="bwrap" id="switch-wrap" title="请先在左侧选择一个预设">
        <button class="primary" id="b-switch" disabled>切换到此预设</button>
      </span>
      <span class="bwrap" id="chatgpt-wrap" title="启动本机 ChatGPT 桌面应用">
        <button id="b-chatgpt" title="启动本机 ChatGPT 桌面应用">启动 ChatGPT</button>
      </span>
    </aside>
  </main>

  <section class="status" id="status">
    <div class="statusbanners" id="status-banners"></div>
  </section>

  <section class="console">
    <div class="head">
      <div class="t">执行日志</div>
      <div class="s" id="jobstat"></div>
      <div class="spin" id="spin"></div>
    </div>
    <div class="log" id="log"><span class="l hintline">就绪。先在左侧选中一个预设，再点右侧边栏的「切换」。</span></div>
  </section>
</div>

<div class="backdrop" id="backdrop">
  <div class="modal" id="modal">
    <h2 id="m-title"></h2>
    <div class="mbody" id="m-body"></div>
    <div class="mfoot" id="m-foot"></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="ctxmenu" id="ctxmenu" role="menu"></div>

<script>
"use strict";
const $ = (id) => document.getElementById(id);
let STATE = null;
let SELECTED = null;
let BUSY = false;
let SAVING = false;
let MODAL_BACK = null;   // 关闭确认弹层时恢复到哪里（编辑器中打开确认框时回退到编辑器，而非卡死）
let FORM_KIND = null;
let FORM_INITIAL = "";
let FORM_DIRTY = false;
let LEAVE_CONFIRM = false;

function esc(s){
  return String(s == null ? "" : s)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;");
}
function toast(msg){
  const t = $("toast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove("on"), 1900);
}
function api(){ return window.pywebview && window.pywebview.api; }

/* ---------------- 状态条（紧凑；明细进「使用帮助」） ---------------- */
/* 状态条只承载「必须显眼」的横幅：没有横幅时整条折叠（.status.on 控制），
   把纵向空间让给预设列表。 */
function setBanners(html){
  const text = html || "";
  const box = $("status-banners"); if (box) box.innerHTML = text;
  const st = $("status"); if (st) st.classList.toggle("on", !!text.trim());
}
function renderStatus(){
  const s = STATE;
  const banners = [];
  if (s.error){
    setBanners(`<div class="banner bad"><span class="ico">!</span><span class="txt">读取配置状态出错：${esc(s.error)}。本程序不会修改任何配置；请检查配置目录权限后重新打开。</span></div>`);
    $("ver").textContent = "v" + s.version;
    renderSwitchButton(); renderChatGPTButton();
    return;
  }
  /* 运行状态不再单独占 pill：
       ·「宿主是否在运行」→ 切换按钮提示（renderSwitchButton）
       ·「ChatGPT 已打开 / 后台驻留 / 未运行」→ 启动按钮提示（renderChatGPTButton）
     状态条只保留「必须显眼」的横幅。 */
  if (s.current_missing){
    banners.push(`<div class="banner warn"><span class="ico">!</span><span class="txt">状态记录指向的预设「${esc(s.current)}」已不存在，将按「无状态」处理。</span></div>`);
  } else if (s.current && s.changed){
    banners.push(`<div class="banner warn"><span class="ico">!</span><span class="txt">正在使用的配置有未同步的变化（约 ${s.changed_lines} 行），切换前会自动同步回 <b>${esc(s.current)}</b>。</span></div>`);
  } else if (!s.current && s.live_exists && s.presets.length){
    banners.push(`<div class="banner info"><span class="ico">i</span><span class="txt">${s.guessed ? `正在使用的配置与预设 <b>${esc(s.guessed)}</b> 一致。在左侧选中它后点边栏的「切换」即可把它记为当前预设（内容一致，不会产生改动）。` : `正在使用的配置与预设库中任何预设都不同，可用「配置 › 另存为新预设…」固化当前配置。`}</span></div>`);
  }
  setBanners(banners.join(""));
  $("ver").textContent = "v" + s.version;
  renderSwitchButton();
  renderChatGPTButton();
}

/* 提示统一挂到按钮 + 包裹壳两处：按钮被禁用时，原生 tooltip 在部分引擎下不显示，
   由未禁用的 .bwrap 外壳兜底（见 §CSS .bwrap 注释）。 */
function setTip(btnId, wrapId, tip){
  const b = $(btnId); if (b) b.title = tip;
  const w = $(wrapId); if (w) w.title = tip;
}
function busyTip(){ return "有操作正在执行，请稍候。"; }

/* ---------- 「切换」按钮：把「Codex 运行时不能切换」做成按钮提示 ---------- */
function renderSwitchButton(){
  const el = $("b-switch");
  if (!el) return;
  const g = (STATE && STATE.guard) || {};
  const hasSel = !!SELECTED;
  const running = !!g.running;
  el.disabled = !!BUSY || running || !hasSel;
  el.textContent = hasSel ? `切换到 ${SELECTED}` : "切换到此预设";
  let tip;
  if (BUSY) tip = busyTip();
  else if (!hasSel) tip = "请先在左侧选择一个预设。";
  else if (running) tip = "Codex 正在运行，不能切换。请完全退出 Codex / ChatGPT 桌面应用（含托盘）后再试。";
  else if (SELECTED === STATE.current) tip = `${SELECTED} 正在使用中；切换会重新应用这个预设（内容一致时不会产生变化）。`;
  else tip = `把正在使用的配置切换到 ${SELECTED}。切换前会自动备份到 configs\\.history\\，可随时回退。`;
  setTip("b-switch", "switch-wrap", tip);
}

/* ---------- 「启动 ChatGPT」按钮：把运行状态做成按钮提示 ---------- */
function renderChatGPTButton(){
  const el = $("b-chatgpt");
  if (!el) return;
  const cg = (STATE && STATE.chatgpt) || {};
  // 只有「界面已经打开」才禁用。仅有后台驻留进程时仍允许点击：
  // AUMID 激活会把已有实例带到前台，重复点击没有副作用。
  // 注意用的是 cg.windowed 而不是 cg.running —— 后者含后台驻留，会把按钮永久灰掉。
  const opened = !!cg.windowed;
  el.disabled = !!BUSY || opened;
  el.textContent = opened ? "ChatGPT 已打开" : "启动 ChatGPT";
  let tip;
  if (BUSY) tip = busyTip();
  else if (opened) tip = "运行状态：ChatGPT 已打开。无需重复启动。";
  else if (cg.running) tip = "运行状态：ChatGPT 后台驻留（窗口已关闭）。点此把它唤到前台。";
  else tip = "运行状态：ChatGPT 未运行。点此启动本机 ChatGPT 桌面应用。";
  setTip("b-chatgpt", "chatgpt-wrap", tip);
}

const CG_POLL_MS = 4000;
let CG_POLL = null;
function cgSame(a, b){
  return !!a && !!b && a.windowed === b.windowed && a.running === b.running;
}
/* 轮询「宿主是否在运行」—— 修复「已退出 Codex，切换按钮仍灰着」。
   原先只有 ChatGPT 的状态在轮询，宿主运行状态（guard.running）只在界面渲染那一刻
   算一次，退出后不会更新。这里同时刷新两者，且只在真的变化时才重绘。 */
async function pollRuntime(){
  if (BUSY) return;                    // 忙时不打扰，避免与进行中的操作争状态
  const bd = $("backdrop");
  if (bd && bd.classList.contains("on")) return;   // 弹层打开时不刷新，避免与用户交互竞争
  const a = api();
  if (!a) return;
  let g = null, cg = null;
  const canHost = typeof a.host_state === "function";
  const canCG = typeof a.chatgpt_state === "function";
  if (!canHost && !canCG) return;
  // 至少有一边可查才发请求，避免无谓往返。两边独立 try：一个失败不影响另一个。
  if (canHost) { try { g = await a.host_state(); } catch (e) { g = null; } }
  if (canCG) { try { cg = await a.chatgpt_state(); } catch (e) { cg = null; } }
  let dirty = false;
  // 宿主运行状态：只要拿到就信任，运行 / 未运行都要同步（按钮要能重新变可点）。
  if (g && typeof g.running === "boolean" && STATE){
    const prev = !!(STATE.guard && STATE.guard.running);
    if (prev !== g.running){
      STATE.guard = Object.assign({}, STATE.guard, {running: g.running, total: g.total});
      dirty = true;
    }
  }
  // ChatGPT 状态：沿用旧的「无变化不重绘」策略，避免干扰正在看的内容。
  if (cg && typeof cg.windowed === "boolean" && STATE && !cgSame(STATE.chatgpt, cg)){
    STATE.chatgpt = cg;
    dirty = true;
  }
  if (!dirty) return;
  renderSwitchButton();               // 运行状态已并入按钮提示与置灰判定
  renderChatGPTButton();
  renderButtons();                    // 「只同步」等菜单项同样依赖运行状态
}
// 点击启动后进程与窗口要几秒才起来，这里做一小串追赶式轮询尽快反映到按钮。
function catchUpChatGPT(tries){
  let n = 0;
  const step = async () => {
    n++;
    await pollRuntime();
    if (n < (tries || 4)) setTimeout(step, 1500);
  };
  setTimeout(step, 1200);
}

/* ---------------- 当前配置 hero（首页主区） ---------------- */
function renderHero(){
  const s = STATE;
  const box = $("hero");
  if (!box) return;

  if (s.error){
    box.className = "hero empty";
    box.innerHTML = `<div class="hcard">
      <div class="ht"><span class="hname">配置状态读取失败</span></div>
      <div class="hguide">无法读取配置目录中的状态（${esc(s.error)}）。本程序不会修改任何配置；请检查配置目录权限后重新打开。</div>
    </div>`;
    return;
  }

  if (!s.current){
    box.className = "hero empty";
    const liveTag = s.live_exists
      ? `<span class="htag">有正在使用的配置</span>`
      : `<span class="htag mute">无正在使用的配置</span>`;
    const guide = s.guessed
      ? `正在使用的配置与预设 <b>${esc(s.guessed)}</b> 一致：在左侧选中它后点边栏的「切换」即可记为当前预设。`
      : s.live_exists
        ? `在左侧选择要用的配置后点边栏的「切换」；也可以用「配置 › 另存为新预设…」把当前配置保存成第一个预设。`
        : `还没有任何预设。用「配置 › 新建配置向导…」创建一份，或在「工具 › 配置位置…」里指定 Codex 目录。`;
    box.innerHTML = `<div class="hcard">
      <div class="ht"><span class="hname">尚未记录「当前预设」</span>${liveTag}</div>
      <div class="hguide">${guide}</div>
    </div>`;
    return;
  }

  const cur = s.presets.find(p => p.name === s.current) || null;
  const model = cur ? (cur.model || "<默认>") : "<默认>";
  const prov = cur ? (cur.provider || "官方") : "官方";
  const when = s.switched_at_human ? `上次切换：${esc(s.switched_at_human)}` : "尚未记录切换时间";
  box.className = "hero" + (s.changed ? " dirty" : "");
  box.innerHTML = `<div class="hcard">
    <div class="ht"><span class="hname">${esc(s.current)}</span>
      <span class="htag">正在使用</span>
      ${s.changed ? `<span class="htag mute" style="background:var(--warn-soft);color:var(--warn);border-color:rgba(183,121,31,.25)">有未同步变化</span>` : ""}</div>
    <div class="hmeta"><span><span class="k">model</span> ${esc(model)}</span>
      <span><span class="k">provider</span> ${esc(prov)}</span>
      <span>${esc(when)}</span></div>
    <div class="hguide">在左侧选中目标预设后点右边栏的「切换」；改模型 / 地址 / 密钥变量：右键卡片选「编辑配置…」，或用「配置 › 编辑所选配置…」。</div>
  </div>`;
}

/* ---------------- 预设列表 ---------------- */
function renderPresets(){
  const box = $("plist");
  if (!STATE.presets.length){
    box.innerHTML = `<div class="empty onboard">
      <h3>欢迎使用 Codex 配置管理器</h3>
      <p>这里集中管理你的 Codex 模型配置（模型、供应商、地址、密钥变量），一键切换、随时回退。</p>
      <ol class="steps">
        <li><b>切换</b>：选中一个预设，点右侧边栏的「切换」；</li>
        <li><b>管理</b>：在卡片上<b>右键</b>，或使用顶部「配置」菜单 —— 编辑、复制、删除、另存都在那里；</li>
        <li><b>开始</b>：用「配置 › 新建配置向导…」建第一份；已有配置可用「配置 › 另存为新预设…」保存副本。</li>
      </ol>
      <p>低频与诊断功能（差异、历史恢复、宿主进程诊断、配置位置等）都收在顶部「工具」菜单里。</p>
    </div>`;
    return;
  }
  box.innerHTML = STATE.presets.map(p => {
    const sel = (p.name === SELECTED) ? " sel" : "";
    const cur = p.is_current ? `<span class="tag">当前</span>` : "";
    const dirty = (p.is_current && STATE.changed) ? `<span class="tag dirty">有未同步变化</span>` : "";
    const url = p.base_url ? `<span><span class="k">url</span> ${esc(p.base_url)}</span>` : "";
    const ek = p.env_key ? `<span><span class="k">key</span> ${esc(p.env_key)}</span>` : "";
    return `<div class="card${sel}" data-name="${esc(p.name)}" title="单击选中 · 双击编辑 · 右键更多操作">
      <span class="dotmark${p.is_current?" on":""}"></span>
      <div class="l1"><span class="nm">${esc(p.name)}</span>${cur}${dirty}</div>
      <div class="l2">
        <span><span class="k">model</span> ${esc(p.model || "<默认>")}</span>
        <span><span class="k">provider</span> ${esc(p.provider || "官方")}</span>
        ${url}${ek}
      </div>
    </div>`;
  }).join("");
  for (const el of box.querySelectorAll(".card")){
    el.addEventListener("click", () => { SELECTED = el.dataset.name; renderPresets(); renderButtons(); });
    el.addEventListener("dblclick", () => { SELECTED = el.dataset.name; renderPresets(); renderButtons(); openEditor(el.dataset.name); });
    el.addEventListener("contextmenu", (e) => {
      // 屏蔽 WebView2 默认右键菜单；右键同时把该卡片选中，与左键语义一致。
      e.preventDefault();
      const name = el.dataset.name;
      SELECTED = name; renderPresets(); renderButtons();
      openCtx(name, e.clientX, e.clientY);
    });
  }
}

/* ---------------- 卡片右键菜单 ---------------- */
let CTX_NAME = null;
function ctxButton(cls, label, tip, disabled, fn){
  return {cls:cls, label:label, tip:tip, disabled:!!disabled, fn:fn, sep:false};
}
function closeCtx(){
  const el = $("ctxmenu");
  if (el){ el.classList.remove("on"); el.innerHTML = ""; }
  CTX_NAME = null;
}
function openCtx(name, x, y){
  const el = $("ctxmenu");
  if (!el || !STATE) return;
  const isCur = name === STATE.current;
  const running = !!(STATE.guard && STATE.guard.running);
  const switchTip = running
    ? "Codex 正在运行，不能切换。请完全退出 Codex / ChatGPT 桌面应用（含托盘）后再试。"
    : isCur
      ? `${name} 正在使用中；切换会重新应用这个预设（内容一致时不会产生变化）。`
      : `把正在使用的配置切换到 ${name}（切换前自动备份）。`;
  const items = [
    ctxButton("", "切换到此预设", switchTip, running, doSwitch),
    ctxButton("", "编辑配置…", "修改模型 / 供应商 / 地址 / 密钥变量", false, () => openEditor(name)),
    ctxButton("", "查看差异", "对比正在使用的配置与这个预设", false, doDiff),
    {sep:true},
    ctxButton("", "复制此预设…", "逐字节复制，不会启用新配置", false, doCopy),
    ctxButton("", "另存为新预设…", STATE.live_exists ? "把正在使用的配置存成一个新预设" : "当前没有正在使用的配置",
              !STATE.live_exists, doSaveNew),
    {sep:true},
    ctxButton("danger", "删除此预设…", isCur ? "当前正在使用的配置不能删除" : "删除前自动备份；历史记录与环境变量不删除",
              isCur, doDelete),
  ];
  el.innerHTML = `<div class="ctxhead">${esc(name)}</div>` + items.map((it, i) =>
    it.sep ? `<div class="msep"></div>`
      : `<button class="mi ${it.cls}" data-i="${i}" role="menuitem"${it.disabled ? " disabled" : ""} title="${esc(it.tip)}">${esc(it.label)}</button>`
  ).join("");
  for (const b of el.querySelectorAll("button[data-i]")){
    const it = items[Number(b.dataset.i)];
    b.addEventListener("click", () => { closeCtx(); if (it.disabled) return; it.fn(); });
  }
  // 先显示再量尺寸，贴右/下边缘时翻转，避免溢出窗口（窄窗口同样可用）
  el.classList.add("on");
  const r = el.getBoundingClientRect();
  let left = x, top = y;
  if (left + r.width + 8 > window.innerWidth) left = Math.max(8, x - r.width);
  if (top + r.height + 8 > window.innerHeight) top = Math.max(8, y - r.height);
  el.style.left = left + "px";
  el.style.top = top + "px";
  CTX_NAME = name;
}

/* ---------------- 按钮态 ---------------- */
/* 菜单 / 右键菜单里可能被禁用的项，统一给出「为什么不可用」的提示 */
function menuTip(id, tip){
  const el = $(id);
  if (el) el.title = tip;
}
function renderButtons(){
  if (BUSY){ return; }
  const running = STATE.guard.running;
  const hasSel = !!SELECTED;
  const selTxt = hasSel ? SELECTED : "所选预设";
  $("b-edit").disabled = !hasSel;
  $("b-harvest").disabled = running || !STATE.current;
  $("b-diff").disabled = !hasSel;
  $("b-copy").disabled = !hasSel;
  $("b-delete").disabled = !hasSel || SELECTED === STATE.current;
  $("b-history").disabled = false;
  $("b-save").disabled = !STATE.live_exists;
  $("b-guard").disabled = false;
  $("b-dry").disabled = !hasSel;
  $("b-new").disabled = false;
  $("b-paths").disabled = false;
  $("b-help").disabled = false;
  $("b-recovery").disabled = false;
  $("b-about").disabled = false;
  menuTip("b-edit", hasSel ? `编辑预设 ${selTxt}` : "请先在左侧选择一个预设");
  menuTip("b-diff", hasSel ? `对比正在使用的配置与 ${selTxt}` : "请先在左侧选择一个预设");
  menuTip("b-copy", hasSel ? `逐字节复制 ${selTxt}` : "请先在左侧选择一个预设");
  menuTip("b-dry", hasSel ? `完整跑一遍切换到 ${selTxt} 的流程，但不写入` : "请先在左侧选择一个预设");
  menuTip("b-delete", !hasSel ? "请先在左侧选择一个预设"
    : (SELECTED === STATE.current ? "当前正在使用的配置不能删除，请先切换到其他配置" : `删除 ${selTxt}（删除前自动备份）`));
  menuTip("b-harvest", running ? "Codex 正在运行，暂不能同步。请完全退出后再试。"
    : (!STATE.current ? "还没有「当前预设」记录，无可同步的对象" : `把正在使用的改动同步回 ${STATE.current}`));
  menuTip("b-save", STATE.live_exists ? "把正在使用的配置存成一个新预设" : "当前没有正在使用的配置，无法另存");
  // 「切换」与「启动 ChatGPT」的置灰原因各自写在按钮提示里（见 renderSwitchButton /
  // renderChatGPTButton）。启动 ChatGPT 与配置切换无关：Codex 正在运行不影响启动宿主
  // 应用，故不跟随守卫置灰；是否可用只看 ChatGPT 界面本身有没有打开。
  renderSwitchButton();
  renderChatGPTButton();
}
function setBusy(b){
  BUSY = b;
  $("spin").classList.toggle("on", b);
  document.body.classList.toggle("busy", b);
  for (const id of ["b-new","b-switch","b-edit","b-harvest","b-save","b-diff","b-copy","b-delete","b-history","b-paths","b-guard","b-dry","b-chatgpt"]){
    const el = $(id); if (el) el.disabled = b;
  }
  closeMenu(); closeCtx();
  if (!b) renderButtons();
  else { renderSwitchButton(); renderChatGPTButton(); }
}

/* ---------------- 日志区 ---------------- */
let LOGLEN = 0;
function renderLog(lines){
  const box = $("log");
  if (!lines.length){ box.innerHTML = ""; LOGLEN = 0; return; }
  const near = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
  const html = lines.map(l => {
    const cls = l.kind === "step" ? "step" : l.kind === "ok" ? "ok" : l.kind === "err" ? "err"
              : l.kind === "warn" ? "warn" : "info";
    const text = l.text === "" ? " " : l.text;
    return `<span class="l ${cls}">${esc(text)}</span>`;
  }).join("");
  box.innerHTML = html;
  LOGLEN = lines.length;
  if (near) box.scrollTop = box.scrollHeight;
}

/* ---------------- 弹层 ---------------- */
function modal(title, bodyHtml, buttons, wide, back){
  MODAL_BACK = back || null;
  $("m-title").innerHTML = title;
  $("m-body").innerHTML = bodyHtml;
  $("modal").classList.toggle("wide", !!wide);
  const foot = $("m-foot");
  foot.innerHTML = "";
  for (const b of buttons){
    const el = document.createElement("button");
    el.textContent = b.label;
    if (b.cls) el.className = b.cls;
    el.addEventListener("click", b.onClick);
    foot.appendChild(el);
  }
  $("backdrop").classList.add("on");
  return foot;
}
/* 关闭弹层：若是从编辑器/向导打开的「二次确认」类弹层，则恢复上一层视图；
   否则只是隐藏。这样用户在确认框里按 Esc / 点取消不会卡在空白弹层。 */
function formSnapshot(){
  if (FORM_KIND === "editor" && EDIT && $("e-name")){
    const f = edCollect();
    f.api_key = $("e-apikey") ? $("e-apikey").value : "";
    return JSON.stringify(f);
  }
  if (FORM_KIND === "wizard" && $("w-new_name")){
    const f = wizardFields();
    f.kind = wizardTemplate();
    f.api_key = $("w-api_key") ? $("w-api_key").value : "";
    return JSON.stringify(f);
  }
  return "";
}
function setFormSnapshot(kind){
  FORM_KIND = kind; FORM_INITIAL = formSnapshot(); FORM_DIRTY = false;
}
function updateDirty(){
  if (!FORM_KIND || SAVING) return false;
  FORM_DIRTY = formSnapshot() !== FORM_INITIAL;
  return FORM_DIRTY;
}
function clearFormState(){
  FORM_KIND = null; FORM_INITIAL = ""; FORM_DIRTY = false; SAVING = false;
}
function closeModalNow(){
  const b = MODAL_BACK; MODAL_BACK = null;
  if (b){ b(); } else { $("backdrop").classList.remove("on"); clearFormState(); }
}
function askLeave(leave){
  if (LEAVE_CONFIRM) return;
  LEAVE_CONFIRM = true;
  const back = FORM_KIND === "editor" ? preserveEditor() : (FORM_KIND === "wizard" ? preserveWizard() : null);
  const resume=()=>{LEAVE_CONFIRM=false;MODAL_BACK=null;if(back)back();else closeModalNow();};
  modal("更改尚未保存", `<p>更改尚未保存。确定要离开吗？</p>`, [
    {label:"继续编辑",onClick:resume},
    {label:"放弃更改",cls:"danger",onClick:()=>{LEAVE_CONFIRM=false;MODAL_BACK=null;clearFormState();$("backdrop").classList.remove("on");if(leave)leave();}}
  ], false, back);
}
/* 关闭弹层：有实际未保存修改时先确认；二次确认取消则回到原表单并保留修改。 */
function closeModal(force=false){
  if (!force && !LEAVE_CONFIRM && !MODAL_BACK && updateDirty()) { askLeave(); return; }
  closeModalNow();
}

/* ---------------- 数据刷新 ---------------- */
async function refresh(keepSelection){
  const s = await api().get_state();
  STATE = s;
  const names = s.presets.map(p => p.name);
  if (keepSelection === false || !SELECTED || !names.includes(SELECTED)){
    SELECTED = s.current && names.includes(s.current) ? s.current : (names[0] || null);
  }
  renderStatus(); renderHero(); renderPresets(); renderButtons();
}

/* ---------------- 配置位置 / 首次设置 ---------------- */
let PATH_INIT = null;
function pathSummary(info){
  return `<div class="fnote">
    <b>Codex 配置目录</b><br><code>${esc(info.codex_home)}</code><br>
    状态：${info.codex_exists?'目录存在':'目录尚不存在'}；${info.config_exists?'已有 config.toml':'暂无 config.toml（首次启用配置时创建）'}
  </div><div class="fnote">
    <b>预设目录</b><br><code>${esc(info.configs_dir)}</code><br>
    状态：${info.configs_exists?'目录存在':'目录尚不存在'}；预设 ${info.preset_count||0} 个
  </div>`;
}
async function choosePathInto(id, file=false){
  const r = file ? await api().choose_config_file() : await api().choose_folder();
  if(r&&r.ok){$(id).value=r.path;if(id==='path-home'&&$('path-follow').checked)$('path-configs').value=r.path.replace(/[\\\/]$/,'')+'\\configs';updatePathPreview();}
  else if(r&&!r.cancelled)toast(r.error||'无法打开系统选择对话框，可手动输入绝对路径');
}
async function updatePathPreview(){
  if(!$('path-preview'))return;
  const r=await api().validate_paths($('path-home').value,$('path-configs').value,false);
  $('path-preview').innerHTML=r.ok?pathSummary(r):`<div class="errbox on">${esc(r.error||'路径无效')}</div>`;
}
async function openPathSettings(first=false, initial=null){
  if(BUSY){toast('有操作正在执行，请稍候');return;}
  if(!first&&FORM_KIND&&updateDirty()){askLeave(()=>openPathSettings(false));return;}
  const info=await api().path_info();
  const init=initial||info;
  const followed=String(init.configs_dir||'').toLowerCase()===String((init.codex_home||'').replace(/[\\\/]$/,'')+'\\configs').toLowerCase();
  const envNote=info.env_controlled?`<div class="fnote warn">当前由 <code>CODEX_HOME</code> 环境变量控制。这里不能保存另一套位置；请在启动本程序前修改或清除环境变量，本程序不会自动修改环境变量。</div>`:'';
  const corrupt=info.settings_status==='corrupt'?`<div class="fnote warn">设置文件损坏：${esc(info.settings_error||'格式无效')}。可重新选择并保存来恢复默认。</div>`:'';
  const candidates=first&&PATH_INIT&&PATH_INIT.path_candidates&&PATH_INIT.path_candidates.length
    ? `<div class="fieldlbl">检测到的位置</div><select id="path-candidate"><option value="">手动选择</option>${PATH_INIT.path_candidates.map(x=>`<option value="${esc(x.path)}">${esc(x.source)} · ${esc(x.path)} · ${x.config_exists?'有 config.toml':'无 config.toml'} · ${x.preset_count} 个预设${x.modified?' · '+esc(x.modified):''}</option>`).join('')}</select>`:'';
  modal(first?'首次设置配置位置':'配置位置',`${corrupt}${envNote}${candidates}
    <div class="fieldlbl">Codex 配置目录（包含 config.toml）</div>
    <div style="display:flex;gap:7px"><input id="path-home" type="text" value="${esc(init.codex_home||'')}" spellcheck="false"><button id="path-home-dir">选择目录…</button><button id="path-home-file">选择 config.toml…</button></div>
    <div class="fieldlbl">预设目录</div>
    <div style="display:flex;gap:7px"><input id="path-configs" type="text" value="${esc(init.configs_dir||'')}" spellcheck="false"><button id="path-configs-dir">选择目录…</button></div>
    <label style="display:flex;gap:7px;align-items:center;margin-top:9px"><input id="path-follow" type="checkbox" ${followed?'checked':''}> 预设目录跟随 Codex 目录（&lt;Codex目录&gt;\\configs）</label>
    <label style="display:flex;gap:7px;align-items:center;margin-top:9px"><input id="path-create" type="checkbox"> 若目录不存在，确认创建上面显示的精确目录</label>
    <div class="fhint">切换只改变本管理器以后读写的位置，不搬移、不删除旧目录数据。预设历史始终保存在所选预设目录的 <code>.history</code> 下。</div>
    <div id="path-preview"></div>`,[
      {label:first?'稍后设置':'取消',onClick:closeModal},
      {label:'恢复默认',onClick:()=>{const h=(PATH_INIT&&PATH_INIT.path_candidates||[]).find(x=>x.source==='默认目录');const v=h?h.path:'';$('path-home').value=v;$('path-follow').checked=true;$('path-configs').value=v.replace(/[\\\/]$/,'')+'\\configs';updatePathPreview();}},
      {label:first?'确认并进入':'应用位置',cls:'primary',onClick:applyPathSettings}
    ],true);
  const sync=()=>{if($('path-follow').checked)$('path-configs').value=$('path-home').value.replace(/[\\\/]$/,'')+'\\configs';updatePathPreview();};
  $('path-home').oninput=sync;$('path-configs').oninput=()=>{$('path-follow').checked=false;updatePathPreview();};
  $('path-follow').onchange=sync;$('path-home-dir').onclick=()=>choosePathInto('path-home');$('path-home-file').onclick=()=>choosePathInto('path-home',true);$('path-configs-dir').onclick=()=>choosePathInto('path-configs');
  if($('path-candidate'))$('path-candidate').onchange=()=>{const v=$('path-candidate').value;if(v){$('path-home').value=v;$('path-follow').checked=true;sync();}};
  if(info.env_controlled)document.querySelector('#m-foot button:last-child').disabled=true;
  updatePathPreview();
}
async function applyPathSettings(){
  const create=$('path-create').checked;
  const r=await api().apply_paths($('path-home').value,$('path-configs').value,create);
  if(!r||!r.ok){toast((r&&r.error)||'配置位置切换失败');updatePathPreview();return;}
  closeModal(true);SELECTED=null;await refresh(false);toast(r.message||'配置位置已切换');
}

/* ---------------- 任务执行 ---------------- */
async function runJob(op, args, opts){
  setBusy(true);
  renderLog([]);
  $("jobstat").textContent = "执行中…";
  const r = await api().run(op, args, opts || {});
  if (r && r.error){ setBusy(false); $("jobstat").textContent = ""; toast(r.error); return; }
  pollLoop();
}
function pollLoop(){
  const tick = async () => {
    const j = await api().poll();
    renderLog(j.lines);
    if (j.running){ setTimeout(tick, 160); return; }
    setBusy(false);
    $("jobstat").textContent = j.result ? (j.result.ok ? "完成" : "未完成") : "";
    if (j.result && j.result.ok) toast("操作完成");
    await refresh(true);
  };
  setTimeout(tick, 120);
}

/* ---------------- 配置编辑 ---------------- */
let EDIT = null;
let EDIT_T = null;
const REASON_OPTS = ["", "minimal", "low", "medium", "high"];
const WIRE_OPTS = ["responses", "chat"];
const ERR_FIELD = {
  new_name:"e-name", model:"e-model", model_provider:"e-provider",
  reasoning:"e-reason", prov_name:"e-pname", base_url:"e-url",
  env_key:"e-envkey", wire_api:"e-wire", "_":"e-provider"
};

function opt(list, cur, labels){
  const vals = list.slice();
  if (cur && vals.indexOf(cur) < 0) vals.push(cur);
  return vals.map(v => {
    const lb = (labels && labels[v] !== undefined) ? labels[v] : (v === "" ? "（不设置）" : v);
    return `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(lb)}</option>`;
  }).join("");
}

function edFields(){
  return {
    preset: EDIT.preset,
    new_name: $("e-name").value.trim(),
    model: $("e-model").value.trim(),
    model_provider: $("e-provider").value.trim(),
    reasoning: $("e-reason").value,
    prov_name: $("e-pname").value.trim(),
    base_url: $("e-url").value.trim(),
    env_key: $("e-envkey").value.trim(),
    wire_api: $("e-wire").value,
    edit_provider: EDIT.loaded || "",     // 实际写哪个供应商块（与 model_provider 解耦）
    drop_provider: ""
  };
}
function edCollect(){
  const f = edFields();
  const pid = f.model_provider;
  const orig = (EDIT.model_provider || "").trim();
  /* 只有「原文引用着某个块、现在改成一个全新的名字」才算重命名，才删旧块。
     原文没引用任何块时（官方预设就是这样）绝不能删 —— 否则一保存就静默丢块。 */
  f.drop_provider = (orig && pid && orig !== pid && !(EDIT.blocks || {})[pid]) ? orig : "";
  return f;
}

function showErrs(errs){
  const box = $("e-err");
  box.innerHTML = Object.keys(errs).map(k => esc(errs[k])).join("<br>");
  box.classList.add("on");
  for (const el of document.querySelectorAll(".input-bad")) el.classList.remove("input-bad");
  for (const k of Object.keys(errs)){
    const id = ERR_FIELD[k];
    if (id && $(id)) $(id).classList.add("input-bad");
  }
}
function clearErrs(){
  const box = $("e-err");
  if (box){ box.classList.remove("on"); box.innerHTML = ""; }
  for (const el of document.querySelectorAll(".input-bad")) el.classList.remove("input-bad");
}

function edPreview(){
  clearTimeout(EDIT_T);
  EDIT_T = setTimeout(async () => {
    if (!EDIT || !$("e-diffinfo") || !$("e-diff")) return;
    const pv = await api().preview_edit(EDIT.preset, edCollect());
    const info = $("e-diffinfo"), box = $("e-diff");
    if (!info || !box) return;
    const errs = (pv && pv.errors) || {};
    if (Object.keys(errs).length){
      info.innerHTML = `<span style="color:var(--danger)">有 ${Object.keys(errs).length} 处需要修正</span>`;
      box.innerHTML = `<div class="r ctx">${Object.keys(errs).map(k => esc(errs[k])).join("\n")}</div>`;
      showErrs(errs);
      return;
    }
    clearErrs();
    if (pv.same && !pv.rename){
      info.textContent = "与当前文件完全一致，保存不会产生任何改动";
      box.innerHTML = `<div class="r ctx">（无差异）</div>`;
      return;
    }
    const rows = pv.rows.map(r =>
      `<div class="r ${r.kind}">${r.kind==="add"?"+ ":r.kind==="del"?"- ":r.kind==="gap"?"⋯ ":"  "}${esc(r.text)}</div>`).join("");
    info.innerHTML = `改动 <b>${pv.changed}</b> 处 · ${pv.size_before} → ${pv.size_after} 字节`
      + (pv.rename ? ` · 将重命名为 <b>${esc(pv.new_name)}.toml</b>` : "");
    box.innerHTML = rows;
  }, 220);
}

function loadBlock(pid){
  const b = (EDIT.blocks || {})[pid] || {};
  $("e-provider").value = pid;
  $("e-pname").value = b.name || "";
  $("e-url").value = b.base_url || "";
  $("e-envkey").value = b.env_key || "";
  $("e-wire").value = b.wire_api || "responses";
  EDIT.loaded = pid;
  for (const x of document.querySelectorAll("#m-body .chip")) x.classList.toggle("on", x.dataset.pid === pid);
}

/* 供应商 ID 为空 = 走宿主官方默认，此时供应商块不会被写入，把字段置灰并说清楚 */
function syncPidState(){
  const pid = $("e-provider").value.trim();
  const off = !pid;
  $("e-sectag").textContent = "[model_providers." + (pid || "…") + "]";
  for (const id of ["e-pname","e-url","e-envkey","e-wire"]){
    const el = $(id);
    if (el) el.disabled = off;
  }
  const sec = document.querySelector("#m-body .fsec");
  if (sec) sec.classList.toggle("off", off);
  return pid;
}

async function openEditor(name){
  if (!name){ toast("请先选择一个预设"); return; }
  if (FORM_KIND && EDIT && EDIT.preset !== name && updateDirty()){
    askLeave(()=>openEditor(name)); return;
  }
  const f = await api().preset_form(name);
  if (!f || f.error || f.ok === false){ toast((f && f.error) || "读取预设失败"); return; }
  EDIT = f;
  EDIT.loaded = f.orig_provider_id || "";
  renderEditor();
  setFormSnapshot("editor");
}

function renderEditor(){
  const f = EDIT;
  const others = (f.providers || []).filter(x => x !== EDIT.loaded);
  const chips = others.length
    ? `<div class="fhint">该预设还有其他供应商块，点名字切去编辑（不会删掉当前块）：</div>
       <div class="chips">${others.map(x => `<span class="chip" data-pid="${esc(x)}">${esc(x)}</span>`).join("")}</div>`
    : "";
  const curTag = f.is_current
    ? `<span class="tagline on">正在使用</span>` : `<span class="tagline off">未在使用</span>`;
  const envState = !f.env_key
    ? "—"
    : (f.env_set ? `<span style="color:var(--ok)">已设置</span>`
                 : `<span style="color:var(--warn)">未设置</span>`);

  const body = `
    <div class="fgrid">
      <div class="fl">预设名</div>
      <div class="fi"><input type="text" id="e-name" value="${esc(f.preset)}" spellcheck="false"></div>

      <div class="fl">模型 ID</div>
      <div class="fi"><div style="display:flex;gap:7px"><input type="text" id="e-model" list="e-model-list" value="${esc(f.model)}" spellcheck="false"
        placeholder="留空则用官方默认模型"><button type="button" id="e-models">获取模型</button></div><datalist id="e-model-list"></datalist>
        <div class="fhint" id="e-model-result">保留手工输入；获取列表不等于模型可调用。</div></div>

      <div class="fl">供应商 ID</div>
      <div class="fi">
        <input type="text" id="e-provider" value="${esc(f.model_provider)}" spellcheck="false" placeholder="例如 aibank">
        ${chips}
      </div>

      <div class="fl">推理强度</div>
      <div class="fi"><select id="e-reason">${opt(REASON_OPTS, f.reasoning)}</select></div>

      <div class="fsec">供应商块 <code id="e-sectag">[model_providers.${esc(f.model_provider || "…")}]</code>
        <span class="offnote">未填供应商 ID —— 以下字段本次不会被写入</span></div>

      <div class="fl">显示名称</div>
      <div class="fi"><input type="text" id="e-pname" value="${esc(f.prov_name)}" spellcheck="false"></div>

      <div class="fl">Base URL</div>
      <div class="fi"><input type="text" id="e-url" value="${esc(f.base_url)}" spellcheck="false"
        placeholder="https://example.com/v1"></div>

      <div class="fl">API Key</div>
      <div class="fi">
        <div class="secret-field"><input type="password" id="e-apikey" autocomplete="new-password" placeholder="留空表示不修改已保存的密钥"><button type="button" id="e-keyshow" aria-label="显示 API Key" aria-pressed="false">显示</button></div>
        <div class="fhint">保存后写入当前 Windows 用户环境变量，不写进配置文件。环境变量不是加密存储。</div>
      </div>

      <div class="fl">密钥变量名</div>
      <div class="fi">
        <div style="display:flex;gap:7px"><input type="text" id="e-envkey" value="${esc(f.env_key)}" spellcheck="false" placeholder="自动生成"><button type="button" id="e-keyauto">自动</button></div>
        <div class="fhint">一般无需修改。当前状态：${envState}</div>
      </div>

      <div class="fl">接口协议</div>
      <div class="fi"><select id="e-wire">${opt(WIRE_OPTS, f.wire_api || "responses")}</select></div>
    </div>

    ${f.is_current
      ? `<div class="fnote warn">该预设<b>正在使用中</b>。保存会先把正在使用的 <code>config.toml</code> 的改动同步进本预设，
          再写入并同步回正在使用的配置 —— 否则下一次切换会把这次编辑冲掉。</div>`
      : `<div class="fnote">该预设<b>未在使用中</b>，保存只改动这个预设文件；正在使用的配置与状态记录都不受影响。</div>`}

    <div class="fnote">本地检查不联网；获取列表不等于模型可调用。“测试模型调用”会发送固定短文本并可能产生少量费用。未保存的 API Key 只用于本次请求。</div>
    <div style="display:flex;gap:8px;margin-top:10px"><button id="e-check" onclick="checkEditor()">本地检查（不联网）</button><button id="e-connect" onclick="testEditorConnection()">测试模型调用…</button></div>
    <div id="e-check-result" class="fhint" aria-live="polite"></div>
    <div class="errbox" id="e-err"></div>

    <div class="diffwrap">
      <div class="diffinfo" id="e-diffinfo">改动预览</div>
      <div class="diff" id="e-diff"></div>
    </div>`;

  modal(`编辑配置 · ${esc(f.preset)} ${curTag}`, body, [
    { label: "取消", onClick: closeModal },
    { label: "保存并启用…", onClick: () => doSave(true) },
    { label: "保存", cls: "primary", onClick: () => doSave(false) },
  ], true);

  EDIT.envManual = !!f.env_key;
  const markEditorDirty = () => { updateDirty(); };
  const suggestEditorKey = async (force=false) => {
    if (!force && EDIT.envManual) return;
    const v = await api().suggest_env_key($("e-provider").value.trim(), $("e-name").value.trim());
    $("e-envkey").value = v; edPreview();
  };
  $("e-keyshow").onclick=()=>toggleSecret("e-apikey","e-keyshow");
  $("e-models").onclick=fetchEditorModels;
  $("e-apikey").addEventListener("input",markEditorDirty);
  $("e-keyauto").onclick=()=>{EDIT.envManual=false;suggestEditorKey(true);setTimeout(markEditorDirty,0);};
  $("e-envkey").addEventListener("input",()=>{EDIT.envManual=true;clearErrs();edPreview();markEditorDirty();});
  for (const id of ["e-model","e-pname","e-url"]){
    $(id).addEventListener("input", () => { clearErrs(); syncPidState(); edPreview(); markEditorDirty(); });
  }
  $("e-name").addEventListener("input",()=>{clearErrs();suggestEditorKey();edPreview();markEditorDirty();});
  $("e-provider").addEventListener("input", () => {
    clearErrs();
    const pid = syncPidState();
    if (pid && pid !== EDIT.loaded && (EDIT.blocks || {})[pid]){
      loadBlock(pid);                     // 写的是既有块的名字 → 直接切去编辑那个块
      EDIT.envManual = true;
      syncPidState();
    } else { suggestEditorKey(); }
    edPreview(); markEditorDirty();
  });
  for (const id of ["e-reason","e-wire"]){
    $(id).addEventListener("change", () => { clearErrs(); edPreview(); markEditorDirty(); });
  }
  for (const c of document.querySelectorAll("#m-body .chip")){
    c.classList.toggle("on", c.dataset.pid === EDIT.loaded);
    c.addEventListener("click", () => {
      loadBlock(c.dataset.pid);
      syncPidState(); clearErrs(); edPreview(); markEditorDirty();
    });
  }
  syncPidState();
  edPreview();
}

async function prepareKeyOptions(form, value, back){
  if (!value) return {};
  const k = await api().prepare_key_save(form.env_key, value);
  if (!k.ok){ toast(k.error || "密钥无法保存"); return null; }
  if (!k.overwrite) return {api_key:value,key_token:k.token};
  return await new Promise(resolve=>modal("确认覆盖密钥",
    `<p>这个密钥变量已经有值。继续后将用新 API Key 覆盖；原密钥不会显示。</p><p>变量名：<code>${esc(form.env_key)}</code></p>`,[
      {label:"取消",onClick:()=>{closeModal();resolve(null);}},
      {label:"确认覆盖",cls:"primary",onClick:()=>{MODAL_BACK=null;closeModal(true);resolve({api_key:value,key_token:k.token,key_confirmed:true});}}
    ],false,back||preserveEditor()));
}

async function doSave(activate=false){
  if (SAVING) return;
  SAVING = true;
  const form = edCollect();
  const pv = await api().preview_edit(EDIT.preset, form);
  const errs = (pv && pv.errors) || {};
  if (Object.keys(errs).length){ SAVING=false; showErrs(errs); return; }
  if (pv.rename_conflict){
    SAVING=false; showErrs({ new_name: `预设「${pv.new_name}」已存在，换个名字。` });
    return;
  }
  const keyOpts=await prepareKeyOptions(form,$("e-apikey").value);
  if(keyOpts===null){SAVING=false;return;}
  if (activate){
    SAVING=false; confirmActivation(EDIT.preset, form, "", preserveEditor(),keyOpts);
    return;
  }
  if (pv.same && !pv.rename && !keyOpts.api_key){ SAVING=false; toast("没有任何改动"); return; }

  if (EDIT.is_current && EDIT.guard_running){
    SAVING=false;
    toast("Codex 正在运行。请完全退出 Codex（包括托盘）后再保存当前配置。");
    return;
  }
  FORM_DIRTY=false; FORM_INITIAL=formSnapshot();
  closeModal(true);
  runJob("edit", EDIT.preset, Object.assign({ form_json: JSON.stringify(form) },keyOpts));
}

/* ---------------- 新建向导与显式联网确认 ---------------- */
function toggleSecret(inputId,buttonId){
  const input=$(inputId), button=$(buttonId);
  if(!input||!button)return;
  const shown=input.type==='password';
  input.type=shown?'text':'password';
  button.textContent=shown?'隐藏':'显示';
  button.setAttribute('aria-label',(shown?'隐藏':'显示')+' API Key');
  button.setAttribute('aria-pressed',shown?'true':'false');
}
/* 新建向导只保留两个模板：
     · 官方服务   → 建一个**空白预设**（不含任何设置），首次打开 Codex / ChatGPT 时宿主自动补齐；
     · 自定义模型 → 预设文件**只写大模型相关设置**，其余内容同样由宿主在打开时补齐。
   「本地服务 / Responses API / Chat Completions」三个模板已按用户要求取消：
   它们只是自定义模型的预填组合，字段本来就能全改，留着反而增加选择负担。 */
const WIZ_TEMPLATE_LABELS = {
  official: "官方服务（在 Codex / ChatGPT 中登录）",
  third_party: "自定义模型（OpenAI 兼容接口）",
};
let WIZ = {kind:'official', template:'official', form:{}};
function wizardTemplate(){ return WIZ.template || WIZ.kind || 'official'; }
/* 官方模板界面上根本没有这些字段，取值一律回落到空串（不再依赖元素一定存在）。 */
function wval(id){ const e = $(id); return e ? e.value.trim() : ""; }
function wizardFields(){
  const f = {new_name:wval('w-new_name'), model:wval('w-model'),
             model_provider:wval('w-model_provider'), base_url:wval('w-base_url'),
             env_key:wval('w-env_key'), wire_api:wval('w-wire_api')};
  if (wizardTemplate() === 'official'){
    Object.assign(f,{model:'',model_provider:'',base_url:'',env_key:'',wire_api:''});
  }
  WIZ.form = f;
  return f;
}
function wizardHasInput(){ return !!WIZ.userEdited; }
function applyWizardTemplate(value){
  const official = (value === 'official');
  const f={new_name:wval('w-new_name'),model:'',model_provider:'',base_url:'',env_key:'',wire_api:''};
  WIZ.template = official ? 'official' : 'third_party';
  WIZ.kind = WIZ.template;
  WIZ.userEdited=false;
  if(!official){f.model_provider='custom';f.env_key='CUSTOM_API_KEY';f.wire_api='responses';}
  WIZ.form=f; openWizard(); FORM_KIND='wizard'; updateDirty();
}
function openWizard(){
  const carryDirty=FORM_KIND==='wizard'&&FORM_DIRTY, carryInitial=FORM_INITIAL;
  const f=WIZ.form||{}, official=wizardTemplate()==='official';
  const tplOpts=Object.entries(WIZ_TEMPLATE_LABELS).map(([v,label])=>
    `<option value="${v}"${official===(v==='official')?' selected':''}>${esc(label)}</option>`).join('');
  /* 官方服务：只问一个名字。建出来的是空白预设 —— 不写 model / provider / 地址 / 密钥。 */
  const nameRow=`<div class="fgrid"><label class="fl" for="w-new_name">预设名</label><input id="w-new_name" type="text" value="${esc(f.new_name||'')}" placeholder="字母、数字、连字符、下划线"></div>`;
  /* 自定义模型：这五个字段就是会写进预设文件的**全部内容**。 */
  const modelRows=`<div class="fgrid"><label class="fl" for="w-model">模型 ID</label><div style="display:flex;gap:7px"><input id="w-model" list="w-model-list" type="text" value="${esc(f.model||'')}" placeholder="填写供应商提供的准确模型 ID"><button type="button" id="w-models">获取模型</button></div><datalist id="w-model-list"></datalist></div>
    <div id="w-third"><div class="fieldlbl">供应商 ID</div><input type="text" id="w-model_provider" value="${esc(f.model_provider||'')}" placeholder="例如 my_provider">
    <div class="fieldlbl">Base URL（HTTPS）</div><input type="text" id="w-base_url" value="${esc(f.base_url||'')}">
    <div class="fieldlbl">API Key</div><div class="secret-field"><input type="password" id="w-api_key" autocomplete="new-password" placeholder="粘贴供应商提供的 API Key"><button type="button" id="w-keyshow" aria-label="显示 API Key" aria-pressed="false">显示</button></div>
    <div class="fieldlbl">密钥变量名</div><div style="display:flex;gap:7px"><input type="text" id="w-env_key" value="${esc(f.env_key||'')}" placeholder="自动生成"><button type="button" id="w-keyauto">自动</button></div>
    <div class="fhint">一般无需修改。保存后密钥写入当前用户环境变量，不写进配置文件。</div>
    <div class="fieldlbl">接口协议</div><select id="w-wire_api">${opt(WIRE_OPTS,f.wire_api||'responses')}</select></div>
    <div style="display:flex;gap:8px"><button id="w-check">本地检查（不联网）</button><button id="w-connect">测试模型调用…</button></div>`;
  const guide=official
    ? '官方服务：不需要地址或密钥，用你的官方账号登录即可。会创建一个<b>空白预设</b>（不含任何设置）；切换到它之后，首次打开 Codex / ChatGPT 时会自动补齐官方默认配置。'
    : '自定义模型：预设文件<b>只写大模型相关设置</b>（模型 ID、供应商、Base URL、密钥变量名、接口协议）；项目、插件等其余内容由 Codex / ChatGPT 在打开时自动补齐。只填写环境变量名称，不要粘贴密钥。地址应包含供应商要求的 API 前缀（例如 /v1），不包含 /responses 或 /chat/completions。';
  modal('新建配置向导', `<p>1. 选择模板　2. 填写配置　3. 检查并保存</p>
    <select id="w-kind">${tplOpts}</select>
    <p id="w-guide">${guide}</p>
    ${nameRow}
    ${official?'':modelRows}
    <p>保存只创建预设，不改变正在使用的配置；保存并启用会在确认后替换配置。新建不继承旧配置中的项目、插件或其他设置。</p>
    <p id="w-result" aria-live="polite"></p>`, [
      {label:'取消',onClick:closeModal},
      {label:'保存并启用…',onClick:()=>saveWizard(true)},
      {label:'保存',cls:'primary',onClick:()=>saveWizard(false)}],true);
  WIZ.envManual=!!(f.env_key);
  const suggestWizardKey=async(force=false)=>{if(official||(!force&&WIZ.envManual))return;const v=await api().suggest_env_key($('w-model_provider').value.trim(),$('w-new_name').value.trim());if(!force&&WIZ.envManual)return;$('w-env_key').value=v;WIZ.form.env_key=v;};
  if(!official){
    $('w-models').onclick=async()=>{const f=wizardFields(),secret=$('w-api_key').value,back=preserveWizard(),r=await api().prepare_models(f,secret);if(!r.ok){$('w-result').textContent=[r.message,...Object.values(r.errors||{})].join(' ');return;}modal('获取模型前确认',`<p>目标：<code>${esc(r.host)}</code></p><p>发送一次 GET 请求获取模型列表，并使用 API Key；通常不会产生模型费用。</p><p>启用 TLS 证书校验；不跟随跳转；12 秒超时；不自动重试。</p>`,[{label:'取消',onClick:closeModal},{label:'确认获取',cls:'primary',onClick:async()=>{MODAL_BACK=null;closeModal(true);setBusy(true);const x=await api().execute_network(r.token,true);setBusy(false);if(back)back();if(x.ok){$('w-model-list').innerHTML=(x.models||[]).map(m=>`<option value="${esc(m)}"></option>`).join('');$('w-result').textContent=x.message||'已获取模型列表';}else $('w-result').textContent=x.message||'获取失败';}}],false,back);};
    $('w-keyshow').onclick=()=>toggleSecret('w-api_key','w-keyshow');
    $('w-keyauto').onclick=()=>{WIZ.envManual=false;suggestWizardKey(true);};
    $('w-env_key').oninput=()=>{WIZ.envManual=true;};
    $('w-model_provider').oninput=()=>suggestWizardKey();$('w-new_name').oninput=()=>suggestWizardKey();
    $('w-check').onclick=async()=>{const r=await api().local_check(wizardFields());$('w-result').textContent=[r.message,...Object.values(r.errors||{})].join(' ');};
    $('w-connect').onclick=()=>confirmModelCall(wizardFields(),preserveWizard());
  }
  const markWizardDirty=()=>{WIZ.userEdited=true;updateDirty();};
  for(const id of ['w-new_name','w-model','w-model_provider','w-base_url','w-env_key','w-wire_api','w-api_key']){const e=$(id);if(e)e.addEventListener(e.tagName==='SELECT'?'change':'input',markWizardDirty);}
  $('w-kind').onchange=()=>{if(wizardHasInput()&&!confirm('切换模板会替换已填写的模板字段，是否继续？')){$('w-kind').value=wizardTemplate();return;} applyWizardTemplate($('w-kind').value);};
  if(!FORM_KIND)setFormSnapshot('wizard');
  else if(carryDirty){FORM_KIND='wizard';FORM_INITIAL=carryInitial;FORM_DIRTY=true;}
}
async function saveWizard(activate){
  if(SAVING)return;SAVING=true;
  const f=wizardFields(), kind=wizardTemplate();
  const r=await api().preview_new(kind,f.new_name,f);
  if (!r.ok){SAVING=false;$('w-result').textContent=r.error;return;}
  /* 官方模板没有 API Key 输入框（空白预设不涉及密钥），取值要能容忍元素不存在。 */
  const keyEl=$('w-api_key');
  const value=(kind!=='official'&&keyEl)?keyEl.value:'';
  const keyOpts=await prepareKeyOptions(f,value,preserveWizard());if(keyOpts===null){SAVING=false;return;}
  if (activate){SAVING=false;confirmActivation(f.new_name,f,kind,preserveWizard(),keyOpts);return;}
  FORM_DIRTY=false;FORM_INITIAL=formSnapshot();closeModal(true);runJob('save_form',f.new_name,Object.assign({form_json:JSON.stringify(f),create_kind:kind},keyOpts));
}
function confirmActivation(name,form,kind,back,keyOpts={}){
  modal('确认保存并启用',`<p>将保存 <b>${esc(form.new_name||name)}</b>，并替换 Codex 正在使用的 <code>config.toml</code>。请先完全退出 Codex（含托盘）。</p>
    <p>当前配置中的外部更改会先保存到原预设，再切换到新配置；没有当前预设记录时只做历史备份，不猜测归属。</p>
    <p>切换前自动备份。启用失败时，已保存的预设仍保留，可退出 Codex 后选中它再次切换。完成后重新打开 Codex；官方配置可能需要登录。</p>
    <p>恢复方法：退出 Codex，将历史文件复制到预设库并命名为 recovery.toml，再重新打开管理器选择 recovery 并切换。</p>`,[
    {label:'返回编辑',onClick:()=>closeModal()},
    {label:'确认保存并启用',cls:'primary',onClick:()=>{MODAL_BACK=null;FORM_DIRTY=false;FORM_INITIAL=formSnapshot();closeModal(true);runJob('save_form',name,Object.assign({form_json:JSON.stringify(form),create_kind:kind,activate:true,confirmed:true},keyOpts));}}
  ], false, back);
}
function preserveEditor(){
  const f=edCollect();
  const key=$("e-apikey")?$("e-apikey").value:"";
  const initial=FORM_INITIAL,dirty=FORM_DIRTY;
  return ()=>{renderEditor();for(const [k,id] of Object.entries(ERR_FIELD)){if(k!=='_' && $(id) && f[k]!==undefined) $(id).value=f[k];}if($("e-apikey"))$("e-apikey").value=key;syncPidState();edPreview();FORM_KIND="editor";FORM_INITIAL=initial;FORM_DIRTY=dirty;SAVING=false;};
}
function preserveWizard(){
  const f=wizardFields(); const kind=WIZ.kind, tpl=WIZ.template;
  const key=$("w-api_key")?$("w-api_key").value:"";
  const initial=FORM_INITIAL,dirty=FORM_DIRTY;
  return ()=>{WIZ={kind:kind,template:tpl,form:f};openWizard();if($("w-api_key"))$("w-api_key").value=key;FORM_KIND="wizard";FORM_INITIAL=initial;FORM_DIRTY=dirty;SAVING=false;};
}
function testEditorConnection(){const back=preserveEditor();confirmModelCall(edCollect(),back);}
async function fetchEditorModels(){
  const back=preserveEditor(), form=edCollect(), secret=$("e-apikey")?$("e-apikey").value:"";
  const r=await api().prepare_models(form,secret);
  if(!r.ok){$("e-model-result").textContent=[r.message,...Object.values(r.errors||{})].join(" ");return;}
  modal("获取模型前确认",`<p>目标：<code>${esc(r.host)}</code></p><p>将发送一次 GET 请求获取模型列表，并使用环境变量 ${esc(r.env_key)} 对应的 API Key。通常不会产生模型费用。</p><p>不会发送配置内容；只连接你确认的目标。</p>`,[
    {label:"取消",onClick:()=>closeModal()},
    {label:"确认获取",cls:"primary",onClick:async()=>{MODAL_BACK=null;const restore=back;closeModal(true);setBusy(true);$("jobstat").textContent="获取模型中…";const x=await api().execute_network(r.token,true);setBusy(false);$("jobstat").textContent="";if(restore)restore();if(x.ok){$("e-model-list").innerHTML=(x.models||[]).map(m=>`<option value="${esc(m)}"></option>`).join("");$("e-model-result").textContent=x.message||"已获取模型列表";}else $("e-model-result").textContent=x.message||"获取失败";}}
  ],false,preserveEditor());
}
function confirmModelCall(form,back){
  api().prepare_model_call(form,$("e-apikey")?$("e-apikey").value:"").then(r=>{
    if(!r.ok){toast([r.message,...Object.values(r.errors||{})].join(" "));return;}
    modal("测试模型调用前确认",`<p>目标：<code>${esc(r.host)}</code><br>模型：${esc(r.model)}<br>协议：${esc(r.wire_api)}</p><p>将发送固定测试文本，可能产生少量费用。只发送一次，不发送配置内容。</p><p>启用 TLS 证书校验；不跟随跳转；12 秒超时；不自动重试。</p>`,[
      {label:"取消",onClick:()=>closeModal()},
      {label:"确认测试",cls:"primary",onClick:async()=>{MODAL_BACK=null;closeModal(true);setBusy(true);$("jobstat").textContent="测试模型调用中…";const x=await api().execute_network(r.token,true);setBusy(false);$("jobstat").textContent="";if(back)back();const el=$("e-check-result")||$("w-result");if(el)el.textContent=[x.message,x.status?`HTTP ${x.status}`:'',x.elapsed_ms!=null?`${x.elapsed_ms} ms`:'',x.protocol||''].filter(Boolean).join(' · ');else toast(x.message||"测试完成");}}
    ],false,back);
  });
}
async function checkEditor(){
  const r=await api().local_check(edCollect());
  $('e-check-result').textContent=[r.message,...Object.values(r.errors||{})].join(' ');
}
async function confirmConnection(form,back){
  const r=await api().prepare_connection(form);
  if (!r.ok){toast([r.message,...Object.values(r.errors||{})].join(' '));return;}
  modal('发送前确认 · 第三方连接测试',`<p>${esc(r.message)}</p>
    <p>目标：<code style="word-break:break-all">${esc(r.target)}</code><br>模型：${esc(r.model)}<br>密钥来源：环境变量 ${esc(r.env_key)}</p>
    <p>启用 TLS 证书校验；不跟随任何跳转；连接及响应等待超时 12 秒；不自动重试。即使超时，服务端也可能已计费。此次确认只使用一次，2 分钟后过期。</p>`,[
    {label:'取消发送，返回',onClick:()=>closeModal()},
    {label:'我同意费用并发送一次',cls:'primary',onClick:()=>{MODAL_BACK=null;closeModal();runJob('connection',null,{token:r.token,confirmed:true});}}
  ],true,back);
}
$('b-new').onclick=()=>{if(BUSY)return;if(FORM_KIND&&updateDirty()){askLeave(()=>$('b-new').click());return;}clearFormState();WIZ={kind:'official',template:'official',form:{},userEdited:false};openWizard();setFormSnapshot('wizard');};
$('b-recovery').onclick=()=>modal('恢复之前的配置',`<ol><li>完全退出 Codex（包括托盘），避免配置再次被覆盖。</li><li>打开 <code>${esc(STATE.lib)}</code> 下的 <code>.history</code>：live 保存切换前的配置，presets 保存各预设修改前的版本。</li><li>按时间选中需要的历史文件，<b>复制，不要移动</b>到预设库；改名为未使用的 <code>recovery.toml</code>（不要覆盖已有同名文件）。</li><li>重新打开管理器，选中 recovery，查看差异后切换到它。这样会先备份当前配置，恢复错误也可再选其他历史版本。</li><li>重新打开 Codex。登录凭据及环境变量不在这些备份中，必要时自行重新登录或设置。</li></ol>`,[{label:'我知道了',cls:'primary',onClick:closeModal}],true);
$('b-help').onclick=()=>openHelp();

/* ---------------- 使用帮助（按需打开，收纳原内联说明） ---------------- */
function openHelp(){
  const g = STATE && STATE.guard;
  const guardTxt = g ? (g.running ? "宿主应用<b>正在运行</b>，「切换」「只同步」被禁用"
                                : (g.source === "file" ? "宿主进程名单来自 <code>.guard</code> 文件"
                                                         : "宿主进程名单为内置默认")) : "";
  modal('使用帮助', `<div class="help-sec">
      <h3>日常操作</h3>
      <ul>
        <li><b>切换</b>：在左侧选中一个预设，点右侧边栏的「切换」；有未同步变化时会先自动同步回当前预设。</li>
        <li><b>编辑</b>：在卡片上<b>右键</b>选「编辑配置…」，或双击卡片；改模型 / 供应商 / 地址 / 密钥变量。</li>
        <li><b>新建</b>：「配置 › 新建配置向导…」只两个模板 —— <b>官方服务</b>（建空白预设，登录即可）与<b>自定义模型</b>（只写大模型相关设置）。其余内容由 Codex / ChatGPT 打开时自动补齐。</li>
        <li><b>另存</b>：「配置 › 另存为新预设…」把正在使用的配置存成新预设。</li>
        <li><b>只同步</b>：「工具 › 只同步当前预设」把正在使用的改动写回当前预设，不改正在使用的配置。</li>
      </ul>
    </div>
    <div class="help-sec">
      <h3>安全与保护</h3>
      <ul>
        <li>切换 / 启用前会<b>自动备份</b>到 <code>configs/.history</code>，可随时回退。</li>
        <li>${guardTxt}。完全退出 Codex（含托盘）后再切换，否则改动会被覆盖回去。</li>
        <li>运行状态不单独占位置：<b>鼠标停在「切换」按钮上</b>可看到为什么不能切换，停在<b>「启动 ChatGPT」按钮上</b>可看到 ChatGPT 的运行状态。详细进程诊断在「工具 › 诊断宿主进程」。</li>
        <li>第三方连接测试只在你<b>显式确认</b>后发送一次：启用 TLS 校验、不跟随跳转、超时 12 秒、不保存密钥明文，可能产生费用。</li>
        <li>本程序只改预设与配置，不会替你登录官方账号、不读取官方登录凭据。</li>
      </ul>
    </div>
    <div class="help-sec">
      <h3>低频 / 诊断（顶部「工具」菜单）</h3>
      <ul>
        <li><b>查看差异</b>：对比正在使用的配置与所选预设（卡片右键里也有）。</li>
        <li><b>诊断宿主进程</b>：扫描宿主进程，确认保护是否生效。</li>
        <li><b>演练</b>：完整跑一遍切换流程但不写入。</li>
        <li><b>历史恢复</b>：列出备份、查看差异并安全恢复；恢复前会再次备份当前目标。</li>
        <li><b>配置位置</b>：切换 Codex 配置目录与预设目录。</li>
        <li><b>复制 / 删除</b>：复制不会启用；删除仅允许非当前配置，删除前自动备份。</li>
      </ul>
    </div>`, [{label:'关闭',cls:'primary',onClick:closeModal}], true);
}

/* ---------------- 事件绑定 ----------------
   每个动作都做成具名函数：顶部菜单栏、卡片右键菜单与按钮共用同一套实现，
   功能只有一份，不会因为入口变多而分叉。 */
async function doSwitch(){
  const info = await api().confirm_info(SELECTED, {});
  let html = "";
  if (info.no_state){
    html = `<p>未找到「当前预设」记录，正在使用的配置中的改动<b>不会并入任何预设</b>。</p>
            <p>将先保底备份正在使用的配置，然后切换到 <b>${esc(SELECTED)}</b>。</p>`;
  } else if (info.will_harvest){
    html = `<p>将<b>同步</b>正在使用的配置 → 预设 <b>${esc(info.current)}</b>（改动约 <b>${info.changed_lines}</b> 行），然后切换到 <b>${esc(SELECTED)}</b>。</p>`;
  } else {
    html = `<p>正在使用的配置与 <b>${esc(info.current)}</b> 一致，无需同步。</p><p>将直接切换到 <b>${esc(SELECTED)}</b>。</p>`;
  }
  html += `<p style="color:var(--fg-3)">每一步都会自动留底到 <code>configs\\.history\\</code>，可随时回退。</p>`;
  modal("确认切换", html, [
    { label: "取消", onClick: closeModal },
    { label: "开始切换", cls: "primary", onClick: () => { closeModal(); runJob("switch", SELECTED, {}); } },
  ]);
}
$("b-switch").addEventListener("click", doSwitch);
$("status").addEventListener("click", async (e) => {
  const btn = e.target && e.target.closest ? e.target.closest("#b-force") : null;
  if (!btn || btn.disabled || BUSY) return;
  const info = await api().confirm_info(SELECTED, {});
  const html = `<p style="color:var(--danger)"><b>宿主应用可能仍在运行。</b>强制切换后，新配置<b>可能立刻被覆盖回去</b>，同步到的也可能是半成品。</p>
    <p>将强制切换到 <b>${esc(SELECTED)}</b>。</p>
    <p style="color:var(--fg-3)">确认进程确实已退出后再继续。</p>`;
  modal("强制切换 — 二次确认", html, [
    { label: "取消", onClick: closeModal },
    { label: "我已确认，强制切换", cls: "danger", onClick: () => { closeModal(); runJob("switch", SELECTED, { force: true }); } },
  ]);
});
async function doHarvest(){
  const html = `<p>将把正在使用的配置的改动同步回预设 <b>${esc(STATE.current || "")}</b>。</p>
    <p style="color:var(--fg-3)">正在使用的配置与状态记录都<b>不会</b>改变；同步前的预设旧版本会备份到历史目录。</p>`;
  modal("确认同步", html, [
    { label: "取消", onClick: closeModal },
    { label: "开始同步", cls: "primary", onClick: () => { closeModal(); runJob("harvest", null, {}); } },
  ]);
}
$("b-harvest").addEventListener("click", doHarvest);
function doSaveNew(){
  const body = `<p>把当前正在使用的配置另存为一个新预设。</p>
    <div class="fieldlbl">预设名（字母、数字、连字符、下划线）</div>
    <input type="text" id="newname" placeholder="例如 kimi" spellcheck="false">
    <div class="errmsg" id="nameerr"></div>
    <label style="display:flex;gap:7px;align-items:center;color:var(--fg-2);font-size:12px;margin-top:2px">
      <input type="checkbox" id="setcur" checked> 同时设为当前预设</label>`;
  const foot = modal("另存为新预设", body, [
    { label: "取消", onClick: closeModal },
    { label: "保存", cls: "primary", onClick: async () => {
        const name = $("newname").value.trim();
        const setcur = $("setcur").checked;
        const r = await api().run("save", name, { set_current: setcur });
        if (r && r.error){ $("nameerr").textContent = r.error; return; }
        closeModal(); pollLoop();
    } },
  ]);
  setTimeout(() => { const el = $("newname"); if (el) el.focus(); }, 30);
  const inp = $("newname");
  if (inp) inp.addEventListener("keydown", e => { if (e.key === "Enter") foot.querySelectorAll("button")[1].click(); });
}
$("b-save").addEventListener("click", doSaveNew);
$("b-edit").addEventListener("click", () => { openEditor(SELECTED); });
async function doDiff(){
  const d = await api().diff(SELECTED);
  if (d.error){ toast(d.error); return; }
  let body;
  if (d.same){
    body = `<p>正在使用的配置与预设 <b>${esc(SELECTED)}</b> <b>完全一致</b>，没有差异。</p>`;
  } else {
    const rows = d.rows.map(r => `<div class="r ${r.kind}">${r.kind==="add"?"+ ":r.kind==="del"?"- ":r.kind==="gap"?"⋯ ":"  "}${esc(r.text)}</div>`).join("");
    body = `<div class="diffinfo">正在使用的配置（+ 仅正在使用的有） 对比 预设 ${esc(SELECTED)}（- 仅预设里有）·  改动 ${d.changed} 行</div>
            <div class="diff">${rows}</div>`;
  }
  modal(`差异：正在使用的 ↔ ${esc(SELECTED)}`, body, [{ label: "关闭", cls: "primary", onClick: closeModal }], true);
}
$("b-diff").addEventListener("click", doDiff);
function doCopy(){
  if (!SELECTED) return;
  const suggested = SELECTED + "-copy";
  modal("复制配置", `<p>逐字节复制预设 <b>${esc(SELECTED)}</b>，不会启用新配置。</p>
    <div class="fieldlbl">新配置名称</div><input type="text" id="copy-name" value="${esc(suggested)}" spellcheck="false">
    <div class="errmsg" id="copy-err"></div>`, [
    {label:"取消",onClick:closeModal},
    {label:"复制",cls:"primary",onClick:async()=>{
      const name=$("copy-name").value.trim();
      const r=await api().run("copy",SELECTED,{new_name:name});
      if(r&&r.error){$("copy-err").textContent=r.error;return;}
      closeModal(true);pollLoop();
    }}
  ]);
  setTimeout(()=>$("copy-name")&&$("copy-name").focus(),30);
}
$("b-copy").addEventListener("click", doCopy);

function doDelete(){
  if (!SELECTED) return;
  if (SELECTED === STATE.current){toast("当前正在使用的配置不能删除。请先切换到其他配置。");return;}
  const name=SELECTED;
  modal("删除配置", `<p>删除前会自动备份预设文件。历史记录和环境变量不会删除。</p>
    <p>请输入完整名称 <b>${esc(name)}</b> 以确认：</p>
    <input type="text" id="delete-name" autocomplete="off" spellcheck="false">
    <div class="errmsg" id="delete-err"></div>`, [
    {label:"取消",onClick:closeModal},
    {label:"删除",cls:"danger",onClick:async()=>{
      const confirmName=$("delete-name").value.trim();
      const r=await api().run("delete",name,{confirm_name:confirmName});
      if(r&&r.error){$("delete-err").textContent=r.error;return;}
      closeModal(true);pollLoop();
    }}
  ]);
}
$("b-delete").addEventListener("click", doDelete);

async function openHistory(){
  const r=await api().history_list();
  if(!r||!r.ok){toast((r&&r.error)||"历史版本读取失败");return;}
  if(!r.items.length){modal("从历史版本恢复","<p>暂无可恢复的历史版本。</p>",[{label:"关闭",cls:"primary",onClick:closeModal}],false);return;}
  const targets=[`<option value="live">当前配置</option>`,...STATE.presets.map(p=>`<option value="preset:${esc(p.name)}">预设 ${esc(p.name)}</option>`)].join("");
  const items=r.items.map((x,i)=>`<option value="${esc(x.id)}">${esc(x.source_name)} · ${esc(x.time||"时间未知")} · ${x.size} 字节</option>`).join("");
  modal("从历史版本恢复", `<p>选择历史版本与恢复目标。恢复前会先备份目标，历史文件不会删除。</p>
    <div class="fieldlbl">历史版本</div><select id="hist-id">${items}</select>
    <div class="fieldlbl">恢复到</div><select id="hist-target">${targets}</select>
    <div class="diffinfo" id="hist-info">请选择后预览差异</div><div class="diff" id="hist-diff"><div class="r ctx">（等待预览）</div></div>
    <div class="errmsg" id="hist-err"></div>`, [
      {label:"取消",onClick:closeModal},
      {label:"恢复所选版本",cls:"primary",onClick:()=>restoreHistory()}
    ],true);
  $("hist-id").onchange=previewHistory;$("hist-target").onchange=previewHistory;
  await previewHistory();
}
async function previewHistory(){
  const id=$("hist-id")&&$("hist-id").value, raw=$("hist-target")&&$("hist-target").value;
  if(!id||!raw)return;
  const parts=raw.split(":",2),type=parts[0],name=parts[1]||"";
  const r=await api().history_preview(id,type,name);
  if(!r||!r.ok){$("hist-err").textContent=(r&&r.error)||"预览失败";$("hist-info").textContent="无法预览";return;}
  $("hist-err").textContent=""; window.__restorePreview={token:r.confirm_token,type:type,name:name};
  $("hist-info").textContent=r.same?`与${r.target}完全一致`:`将改动 ${r.changed} 行 · ${r.size_before} → ${r.size_after} 字节`;
  $("hist-diff").innerHTML=r.same?'<div class="r ctx">（无差异）</div>':r.rows.map(x=>`<div class="r ${x.kind}">${x.kind==='add'?'+ ':x.kind==='del'?'- ':x.kind==='gap'?'⋯ ':'  '}${esc(x.text)}</div>`).join('');
}
function restoreHistory(){
  const p=window.__restorePreview;if(!p){toast("请先完成差异预览");return;}
  const back=()=>openHistory();
  modal("确认恢复",`<p>将用所选历史版本替换目标。恢复前会再次备份当前目标。</p><p>若目标是当前配置或正在使用的预设，必须先完全退出 Codex。</p>`,[
    {label:"返回预览",onClick:closeModal},
    {label:"确认恢复",cls:"primary",onClick:()=>{MODAL_BACK=null;closeModal(true);runJob("restore",null,{token:p.token,confirmed:true});}}
  ],false,back);
}
$("b-history").addEventListener("click",openHistory);
$("b-paths").addEventListener("click",()=>openPathSettings(false));

$("b-guard").addEventListener("click", async () => {
  const g = await api().guard_info();
  let body;
  if (!g.hits.length){
    body = `<p><b>Codex 未运行</b>，可以安全切换或同步配置。</p>`;
  } else {
    body = `<p style="color:var(--danger)"><b>Codex 正在运行</b>。</p>
      <p>为避免配置被 Codex 覆盖，切换和同步暂不可用。请完全退出 Codex（包括托盘）后重试。</p>`;
  }
  modal("运行状态", body, [{ label: "关闭", cls: "primary", onClick: closeModal }], false);
});
$("b-dry").addEventListener("click", () => {
  runJob("switch", SELECTED, { dry: true });
});
$("b-chatgpt").addEventListener("click", async () => {
  // 只请求系统启动 ChatGPT：不改任何配置、不切换预设、不读取登录凭据。
  // 界面已打开时不重复请求（按钮此时本就是禁用态，这里再兜一层）。
  if (STATE && STATE.chatgpt && STATE.chatgpt.windowed) return;
  setBusy(true);
  try {
    const r = await api().launch_chatgpt();
    if (r && r.ok){
      toast(r.message || "已请求启动 ChatGPT。");
      catchUpChatGPT();
    } else {
      toast((r && r.error) || "启动 ChatGPT 失败。");
    }
  } catch (e) {
    toast("启动 ChatGPT 失败，请稍后重试。");
  } finally {
    setBusy(false);
  }
});
$("backdrop").addEventListener("click", e => { if (e.target === $("backdrop") && !BUSY) closeModal(); });
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  // 关闭优先级：右键菜单 → 顶部下拉 → 弹层
  if ($("ctxmenu").classList.contains("on")){ closeCtx(); return; }
  if (document.querySelector("#menubar .mgroup.open")){ closeMenu(); return; }
  if (!BUSY) closeModal();
});
window.addEventListener("beforeunload", e => {
  if (updateDirty() && !SAVING){e.preventDefault();e.returnValue="更改尚未保存";return e.returnValue;}
});

/* ---------------- 顶部菜单栏（配置 / 工具 / 帮助） ---------------- */
function closeMenu(){
  for (const g of document.querySelectorAll("#menubar .mgroup")){
    g.classList.remove("open");
    const t = g.querySelector(".mtitle");
    if (t) t.setAttribute("aria-expanded", "false");
  }
}
function toggleMenu(titleEl){
  const g = titleEl.closest(".mgroup");
  if (!g) return;
  const was = g.classList.contains("open");
  closeMenu(); closeCtx();
  if (!was){ g.classList.add("open"); titleEl.setAttribute("aria-expanded", "true"); }
}
for (const t of document.querySelectorAll("#menubar .mtitle")){
  t.addEventListener("click", (e) => { e.stopPropagation(); if (BUSY) return; toggleMenu(t); });
}
// 面板内点中任何一项后收起菜单（面板的冒泡监听晚于按钮自身的处理，所以动作会先执行）
for (const p of document.querySelectorAll("#menubar .mpanel")){
  p.addEventListener("click", (e) => { if (e.target && e.target.closest("button")) closeMenu(); });
}
// 点菜单栏 / 右键菜单以外任意处收起；mousedown 先于 click，观感更利落
document.addEventListener("mousedown", (e) => {
  const t = e.target;
  if (t && t.closest && (t.closest("#menubar") || t.closest("#ctxmenu"))) return;
  closeMenu(); closeCtx();
}, true);
window.addEventListener("resize", () => { closeMenu(); closeCtx(); });
document.addEventListener("scroll", closeCtx, true);
$("plist").addEventListener("scroll", closeCtx);

$("b-about").addEventListener("click", () => {
  const s = STATE || {};
  modal("关于", `<p><b>Codex 配置管理器</b> v${esc(s.version || "")}</p>
    <p>集中管理 Codex 的模型配置：一键切换、编辑、备份与恢复。</p>
    <p style="color:var(--fg-3);word-break:break-all">Codex 配置目录：<code>${esc(s.root || "")}</code><br>
       预设目录：<code>${esc(s.lib || "")}</code></p>
    <p style="color:var(--fg-3)">切换前自动备份到 <code>configs\\.history\\</code>；本程序不读取官方登录凭据，也不会自动登录。</p>
    <p style="color:var(--fg-3)">操作入口：顶部「配置 / 工具 / 帮助」菜单，或在预设卡片上右键。</p>`,
    [{label:"关闭",cls:"primary",onClick:closeModal}], false);
});

/* ---------------- 启动 ---------------- */
window.addEventListener("pywebviewready", async () => {
  await refresh(false);
  // 运行状态（宿主 + ChatGPT）低频轮询：只在状态真的变化时才重绘。
  if (!CG_POLL) CG_POLL = setInterval(pollRuntime, CG_POLL_MS);
  // 轮询会在「弹层打开」或「界面忙碌」时主动跳过，那种情况下正好退出 Codex
  // 就会留下一个过期的灰按钮。所以界面重新获得焦点时补查一次 ——
  // 用户从 Codex 切回来点这个窗口，正是最需要它已经变可点的时刻。
  window.addEventListener("focus", () => { pollRuntime(); });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollRuntime();
  });
  const box = $("log");
  box.innerHTML = `<span class="l hintline">就绪。共 ${STATE.presets.length} 个预设` +
    (STATE.current ? `，当前预设「${STATE.current}」` : "，尚无当前预设记录") +
    `。选中预设后点右侧边栏的「切换」；在卡片上右键可用编辑 / 复制 / 删除 / 另存。</span>`;
  let ini = null;
  try { ini = await api().initial(); } catch (e) { ini = null; }
  PATH_INIT = ini || {};
  if (ini && ini.path_setup){
    const pi=await api().path_info();
    let start=pi;
    if(ini.path_auto_candidate){start=await api().validate_paths(ini.path_auto_candidate,ini.path_auto_candidate.replace(/[\\\/]$/,'')+'\\configs',false);}
    await openPathSettings(true,start);
    return;
  }
  if (ini && ini.preset){
    if (STATE.presets.some(p => p.name === ini.preset)){
      SELECTED = ini.preset;
    } else {
      toast(`预设「${ini.preset}」不存在`);
      return;
    }
    renderPresets(); renderButtons();
    openEditor(ini.preset);
  }
});
</script>
</body>
</html>
"""
