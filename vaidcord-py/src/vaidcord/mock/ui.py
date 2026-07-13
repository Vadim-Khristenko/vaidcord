"""Static UI for the local Discord mock server.

The HTML below is a self-contained single-page ops console served by
:mod:`vaidcord.mock.server`. It deliberately does *not* imitate the Discord
client; instead it is styled as a premium developer operations console:
layered translucent (glass) panels over a deep space background, one strong
indigo-to-cyan accent gradient, monospace accents for ids and routes, and a
right-hand console with live panels for the request inspector, gateway
sessions, chaos injection, rate limits, the scenario runner and profiles.

Everything is inline (CSS + JS, no external assets). The scripting API
surface (element ids, ``apiFetch`` calls and :func:`validate_mock_ui`) is
kept stable so existing tests and tooling continue to work.
"""

MOCK_UI_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VaidCord Mock Server</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #05060a;
      --panel: rgba(255, 255, 255, 0.032);
      --panel-strong: rgba(255, 255, 255, 0.055);
      --panel-border: rgba(255, 255, 255, 0.08);
      --panel-border-soft: rgba(255, 255, 255, 0.05);
      --text: #e7eaf3;
      --text-dim: #9aa1b5;
      --text-faint: #5d647a;
      --accent-a: #6366f1;
      --accent-b: #22d3ee;
      --accent-grad: linear-gradient(135deg, #6366f1 0%, #22d3ee 100%);
      --accent-soft: rgba(99, 102, 241, 0.16);
      --accent-glow: 0 0 24px rgba(99, 102, 241, 0.35);
      --ok: #34d399;
      --ok-soft: rgba(52, 211, 153, 0.14);
      --warn: #fbbf24;
      --warn-soft: rgba(251, 191, 36, 0.14);
      --err: #f87171;
      --err-soft: rgba(248, 113, 113, 0.14);
      --info: #60a5fa;
      --info-soft: rgba(96, 165, 250, 0.14);
      --purple: #c084fc;
      --font: "Inter", "SF Pro Text", "Segoe UI", system-ui, sans-serif;
      --mono: ui-monospace, "SFMono-Regular", "JetBrains Mono", "Cascadia Code", Menlo, Consolas, monospace;
      --radius: 14px;
      --header-h: 58px;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      color: var(--text);
      font: 13.5px/1.45 var(--font);
      background:
        radial-gradient(1100px 700px at -10% -20%, rgba(99, 102, 241, 0.16), transparent 60%),
        radial-gradient(900px 620px at 110% 115%, rgba(34, 211, 238, 0.10), transparent 60%),
        radial-gradient(700px 480px at 60% -30%, rgba(192, 132, 252, 0.07), transparent 60%),
        var(--bg);
      background-attachment: fixed;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }
    button { font: inherit; cursor: pointer; }
    input, textarea, select { font: inherit; color: var(--text); }
    ::selection { background: rgba(99, 102, 241, 0.4); }

    /* ---------- scrollbars ---------- */
    * { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.14) transparent; }
    *::-webkit-scrollbar { width: 8px; height: 8px; }
    *::-webkit-scrollbar-track { background: transparent; }
    *::-webkit-scrollbar-thumb {
      background: rgba(255,255,255,0.12);
      border-radius: 8px;
      border: 2px solid transparent;
      background-clip: padding-box;
    }
    *::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.22); background-clip: padding-box; }

    /* ---------- shell ---------- */
    .shell {
      display: grid;
      grid-template-rows: var(--header-h) minmax(0, 1fr);
      height: 100vh;
      width: 100vw;
      gap: 12px;
      padding: 12px;
    }
    .main {
      display: grid;
      grid-template-columns: 264px minmax(0, 1fr) 400px;
      gap: 12px;
      min-height: 0;
    }
    @media (max-width: 1280px) {
      .main { grid-template-columns: 220px minmax(0, 1fr) 340px; }
    }
    .glass {
      background: var(--panel);
      border: 1px solid var(--panel-border-soft);
      border-radius: var(--radius);
      backdrop-filter: blur(18px) saturate(1.3);
      -webkit-backdrop-filter: blur(18px) saturate(1.3);
      box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 40px rgba(0,0,0,0.45);
    }

    /* ---------- header ---------- */
    .topbar {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 16px;
    }
    .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .brand-mark {
      width: 30px; height: 30px; border-radius: 9px;
      background: var(--accent-grad);
      box-shadow: var(--accent-glow);
      display: grid; place-items: center;
      font-weight: 800; font-size: 14px; color: #fff;
    }
    .brand-title { font-weight: 700; letter-spacing: 0.02em; white-space: nowrap; }
    .brand-title .thin { color: var(--text-dim); font-weight: 500; }
    .brand-sub {
      font-family: var(--mono); font-size: 10.5px; color: var(--text-faint);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .stats { display: flex; gap: 8px; margin-left: 8px; }
    .stat {
      display: flex; flex-direction: column; justify-content: center;
      padding: 4px 14px; min-width: 84px;
      border: 1px solid var(--panel-border-soft);
      border-radius: 10px;
      background: var(--panel);
      transition: border-color 160ms ease, transform 160ms ease;
    }
    .stat:hover { border-color: var(--panel-border); transform: translateY(-1px); }
    .stat b { font-size: 16px; font-variant-numeric: tabular-nums; line-height: 1.15; }
    .stat span { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--text-faint); }
    .stat.pulse b { color: var(--accent-b); }
    .topbar .spacer { flex: 1; }
    .btn {
      border: 1px solid var(--panel-border);
      background: var(--panel-strong);
      color: var(--text);
      border-radius: 9px;
      padding: 7px 13px;
      font-size: 12.5px;
      font-weight: 600;
      transition: background 140ms ease, border-color 140ms ease, transform 120ms ease, box-shadow 140ms ease;
      white-space: nowrap;
    }
    .btn:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.16); }
    .btn:active { transform: translateY(1px); }
    .btn.primary {
      background: var(--accent-grad);
      border-color: transparent;
      color: #fff;
      box-shadow: 0 4px 18px rgba(99,102,241,0.35);
    }
    .btn.primary:hover { filter: brightness(1.08); box-shadow: 0 4px 24px rgba(99,102,241,0.5); }
    .btn.danger { color: var(--err); border-color: rgba(248,113,113,0.3); }
    .btn.danger:hover { background: var(--err-soft); }
    .btn.ghost { background: transparent; border-color: transparent; color: var(--text-dim); }
    .btn.ghost:hover { color: var(--text); background: var(--panel-strong); }
    .btn.sm { padding: 4px 9px; font-size: 11px; border-radius: 7px; }

    /* ---------- left rail ---------- */
    .rail { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
    .rail-scroll { overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 18px; min-height: 0; }
    .rail h3, .console h3 {
      margin: 0 0 8px;
      font-size: 10px; font-weight: 700;
      letter-spacing: 0.16em; text-transform: uppercase;
      color: var(--text-faint);
      display: flex; align-items: center; gap: 8px;
    }
    .rail h3::after, .console h3::after {
      content: ""; flex: 1; height: 1px;
      background: linear-gradient(90deg, var(--panel-border), transparent);
    }
    .list { display: flex; flex-direction: column; gap: 3px; }
    .row-item {
      display: flex; align-items: center; gap: 9px;
      padding: 7px 9px;
      border-radius: 9px;
      border: 1px solid transparent;
      color: var(--text-dim);
      cursor: pointer;
      transition: background 130ms ease, color 130ms ease, border-color 130ms ease;
      overflow: hidden;
    }
    .row-item:hover { background: var(--panel-strong); color: var(--text); }
    .row-item.active {
      background: var(--accent-soft);
      border-color: rgba(99,102,241,0.35);
      color: var(--text);
    }
    .row-item .glyph {
      font-family: var(--mono);
      color: var(--text-faint);
      width: 14px; text-align: center; flex: none;
    }
    .row-item.active .glyph { color: var(--accent-b); }
    .row-item .label { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .row-item .meta { font-family: var(--mono); font-size: 10px; color: var(--text-faint); flex: none; }
    .guild-card {
      display: flex; align-items: center; gap: 10px;
      padding: 9px;
      border-radius: 11px;
      border: 1px solid var(--panel-border-soft);
      background: var(--panel);
      margin-bottom: 4px;
    }
    .guild-badge {
      width: 34px; height: 34px; flex: none;
      border-radius: 10px;
      background: linear-gradient(135deg, rgba(99,102,241,0.7), rgba(34,211,238,0.55));
      display: grid; place-items: center;
      font-weight: 800; font-size: 13px; color: #fff;
    }
    .guild-name { font-weight: 650; font-size: 13px; line-height: 1.2; }
    .guild-meta { font-family: var(--mono); font-size: 10px; color: var(--text-faint); }

    /* ---------- center: chat ---------- */
    .chat { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
    .chat-head {
      display: flex; align-items: baseline; gap: 12px;
      padding: 13px 18px;
      border-bottom: 1px solid var(--panel-border-soft);
      flex: none;
    }
    .chat-head .hash { font-family: var(--mono); color: var(--accent-b); font-size: 16px; }
    .chat-head .name { font-weight: 700; font-size: 15px; }
    .chat-head .topic {
      color: var(--text-faint); font-size: 12px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .msgs { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 12px; }
    .msg { display: flex; gap: 11px; animation: rise 220ms ease both; }
    @keyframes rise { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
    .avatar {
      width: 34px; height: 34px; flex: none;
      border-radius: 50%;
      display: grid; place-items: center;
      font-weight: 700; font-size: 12px; color: #fff;
      background: linear-gradient(135deg, #6366f1, #a855f7);
    }
    .avatar.bot { background: linear-gradient(135deg, #0ea5e9, #22d3ee); }
    .msg-body { min-width: 0; flex: 1; }
    .msg-top { display: flex; align-items: baseline; gap: 8px; }
    .msg-author { font-weight: 650; font-size: 13.5px; }
    .chip {
      font-size: 9px; font-weight: 700; letter-spacing: 0.08em;
      padding: 1.5px 6px; border-radius: 5px;
      text-transform: uppercase;
    }
    .chip.bot { background: var(--accent-soft); color: #a5b4fc; }
    .msg-time { font-family: var(--mono); font-size: 10px; color: var(--text-faint); }
    .msg-id { font-family: var(--mono); font-size: 9.5px; color: var(--text-faint); opacity: 0; transition: opacity 140ms ease; }
    .msg:hover .msg-id { opacity: 1; }
    .msg-content { color: var(--text); word-wrap: break-word; white-space: pre-wrap; margin-top: 1px; }
    .msg-content .edited { font-size: 10px; color: var(--text-faint); }
    .typing-strip {
      flex: none; min-height: 20px; padding: 0 20px 4px;
      font-size: 11.5px; color: var(--text-dim); font-style: italic;
    }
    .typing-strip .dots::after { content: "…"; animation: blink 1.2s infinite; }
    @keyframes blink { 50% { opacity: 0.3; } }
    .composer {
      flex: none;
      margin: 0 14px 14px;
      border: 1px solid var(--panel-border);
      border-radius: 13px;
      background: var(--panel-strong);
      transition: border-color 160ms ease, box-shadow 160ms ease;
    }
    .composer:focus-within { border-color: rgba(99,102,241,0.55); box-shadow: 0 0 0 3px rgba(99,102,241,0.14); }
    .composer textarea {
      display: block; width: 100%;
      background: transparent; border: 0; outline: 0; resize: none;
      padding: 12px 14px 6px;
      min-height: 44px; max-height: 160px;
      color: var(--text);
    }
    .composer-bar {
      display: flex; align-items: center; gap: 8px;
      padding: 6px 10px 9px;
    }
    .composer-bar select {
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--panel-border-soft);
      border-radius: 8px;
      padding: 5px 8px;
      font-size: 12px;
      max-width: 180px;
    }
    .composer-bar .hint { flex: 1; text-align: right; font-family: var(--mono); font-size: 10px; color: var(--text-faint); }

    /* ---------- right console ---------- */
    .console { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
    .tabs {
      display: flex; gap: 2px; padding: 8px 8px 0;
      border-bottom: 1px solid var(--panel-border-soft);
      flex: none;
      overflow-x: auto;
    }
    .tab-btn {
      border: 0; background: transparent;
      color: var(--text-dim);
      padding: 8px 11px 10px;
      font-size: 12px; font-weight: 600;
      border-radius: 8px 8px 0 0;
      position: relative;
      white-space: nowrap;
      transition: color 140ms ease;
    }
    .tab-btn:hover { color: var(--text); }
    .tab-btn[data-active="1"] { color: var(--text); }
    .tab-btn[data-active="1"]::after {
      content: "";
      position: absolute; left: 8px; right: 8px; bottom: -1px; height: 2px;
      border-radius: 2px;
      background: var(--accent-grad);
      box-shadow: 0 0 10px rgba(99,102,241,0.7);
    }
    .pane { flex: 1; overflow-y: auto; padding: 13px; display: none; flex-direction: column; gap: 14px; min-height: 0; }
    .pane[data-active="1"] { display: flex; }
    .empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 6px; padding: 34px 12px;
      color: var(--text-faint); text-align: center;
    }
    .empty .glyph { font-size: 24px; opacity: 0.6; }
    .empty .hint { font-size: 11.5px; max-width: 220px; }

    /* inspector */
    .req { border: 1px solid var(--panel-border-soft); border-radius: 10px; overflow: hidden; background: var(--panel); }
    .req-row {
      display: flex; align-items: center; gap: 8px;
      padding: 7px 9px; cursor: pointer;
      transition: background 130ms ease;
    }
    .req-row:hover { background: var(--panel-strong); }
    .method {
      font-family: var(--mono); font-size: 10px; font-weight: 700;
      padding: 2px 6px; border-radius: 5px; flex: none;
      min-width: 44px; text-align: center; letter-spacing: 0.04em;
    }
    .method.GET { color: var(--ok); background: var(--ok-soft); }
    .method.POST { color: var(--info); background: var(--info-soft); }
    .method.PATCH { color: var(--warn); background: var(--warn-soft); }
    .method.PUT { color: var(--purple); background: rgba(192,132,252,0.14); }
    .method.DELETE { color: var(--err); background: var(--err-soft); }
    .req-path {
      flex: 1; min-width: 0;
      font-family: var(--mono); font-size: 11px;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      color: var(--text);
    }
    .status-pill {
      font-family: var(--mono); font-size: 10px; font-weight: 700;
      padding: 2px 7px; border-radius: 999px; flex: none;
    }
    .status-2xx { color: var(--ok); background: var(--ok-soft); }
    .status-3xx { color: var(--info); background: var(--info-soft); }
    .status-4xx { color: var(--warn); background: var(--warn-soft); }
    .status-429 { color: #fb923c; background: rgba(251,146,60,0.16); }
    .status-5xx { color: var(--err); background: var(--err-soft); }
    .status-na { color: var(--text-faint); background: rgba(255,255,255,0.05); }
    .req-ms { font-family: var(--mono); font-size: 9.5px; color: var(--text-faint); flex: none; }
    .req-json {
      display: none;
      margin: 0;
      padding: 9px 11px;
      border-top: 1px solid var(--panel-border-soft);
      background: rgba(0,0,0,0.32);
      font-family: var(--mono); font-size: 10.5px; line-height: 1.55;
      color: #a5f3fc;
      overflow-x: auto;
      white-space: pre;
    }
    .req.open .req-json { display: block; }

    /* gateway */
    .kv { display: flex; align-items: center; gap: 8px; font-size: 12px; }
    .kv .k { color: var(--text-faint); min-width: 84px; font-size: 11px; }
    .kv .v { font-family: var(--mono); font-size: 11px; word-break: break-all; }
    .session-card {
      border: 1px solid var(--panel-border-soft);
      border-radius: 10px; padding: 9px 11px;
      background: var(--panel);
      display: flex; flex-direction: column; gap: 4px;
    }
    .session-top { display: flex; align-items: center; gap: 8px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
    .dot.on { background: var(--ok); box-shadow: 0 0 8px rgba(52,211,153,0.8); }
    .dot.off { background: var(--text-faint); }
    .session-id { font-family: var(--mono); font-size: 11px; flex: 1; overflow: hidden; text-overflow: ellipsis; }
    .session-meta { font-family: var(--mono); font-size: 10px; color: var(--text-faint); display: flex; gap: 12px; flex-wrap: wrap; }
    .feed { display: flex; flex-direction: column; gap: 3px; }
    .feed-item {
      display: flex; align-items: center; gap: 8px;
      font-family: var(--mono); font-size: 10.5px;
      padding: 4px 8px; border-radius: 7px;
      background: var(--panel);
      color: var(--text-dim);
      animation: rise 200ms ease both;
    }
    .feed-item .t { color: var(--accent-b); font-weight: 700; }
    .feed-item .when { margin-left: auto; color: var(--text-faint); font-size: 9.5px; flex: none; }
    .live-dot {
      display: inline-block; width: 7px; height: 7px; border-radius: 50%;
      background: var(--err); margin-right: 5px;
    }
    .live-dot.on { background: var(--ok); box-shadow: 0 0 8px rgba(52,211,153,0.9); animation: blink 2s infinite; }

    /* forms */
    .field { display: flex; flex-direction: column; gap: 4px; }
    .field label { font-size: 10.5px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; }
    .field input[type="text"], .field input[type="number"], .field textarea, .field select {
      background: rgba(255,255,255,0.045);
      border: 1px solid var(--panel-border-soft);
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 12.5px;
      outline: none;
      transition: border-color 140ms ease, box-shadow 140ms ease;
    }
    .field input:focus, .field textarea:focus, .field select:focus {
      border-color: rgba(99,102,241,0.55);
      box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
    }
    .field textarea { font-family: var(--mono); font-size: 11px; min-height: 110px; resize: vertical; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .form-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .switch { display: flex; align-items: center; gap: 9px; cursor: pointer; user-select: none; }
    .switch input { position: absolute; opacity: 0; }
    .switch .track {
      width: 34px; height: 19px; border-radius: 999px;
      background: rgba(255,255,255,0.12);
      position: relative; flex: none;
      transition: background 160ms ease;
    }
    .switch .track::after {
      content: ""; position: absolute; top: 2px; left: 2px;
      width: 15px; height: 15px; border-radius: 50%;
      background: #fff;
      transition: transform 160ms ease;
    }
    .switch input:checked + .track { background: var(--accent-a); }
    .switch input:checked + .track::after { transform: translateX(15px); }
    .switch .lbl { font-size: 12.5px; }

    /* profiles */
    .user-row {
      display: flex; align-items: center; gap: 9px;
      padding: 7px 9px;
      border: 1px solid var(--panel-border-soft);
      border-radius: 10px;
      background: var(--panel);
    }
    .user-row .avatar { width: 28px; height: 28px; font-size: 10px; }
    .user-row .uname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; font-size: 12.5px; }
    .user-row .uid { font-family: var(--mono); font-size: 9.5px; color: var(--text-faint); }
    .user-row.current { border-color: rgba(34,211,238,0.4); }
    .chip.current { background: rgba(34,211,238,0.15); color: var(--accent-b); }

    /* scenario */
    .scenario-row {
      border: 1px solid var(--panel-border-soft);
      border-radius: 10px; padding: 8px 10px;
      background: var(--panel);
      display: flex; align-items: center; gap: 9px;
    }
    .scenario-row .sname { flex: 1; min-width: 0; font-weight: 600; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .scenario-row .sprog { font-family: var(--mono); font-size: 10px; color: var(--text-faint); }
    .chip.running { background: var(--info-soft); color: var(--info); }
    .chip.completed { background: var(--ok-soft); color: var(--ok); }
    .chip.cancelled { background: rgba(255,255,255,0.07); color: var(--text-dim); }
    .chip.error { background: var(--err-soft); color: var(--err); }

    /* toasts */
    #ui-notice {
      position: fixed; right: 18px; bottom: 18px;
      display: flex; flex-direction: column; gap: 8px;
      z-index: 60; max-width: 360px;
    }
    .toast {
      padding: 10px 14px;
      border-radius: 11px;
      border: 1px solid var(--panel-border);
      background: rgba(12, 14, 22, 0.92);
      backdrop-filter: blur(14px);
      box-shadow: 0 14px 40px rgba(0,0,0,0.5);
      font-size: 12.5px;
      display: flex; gap: 9px; align-items: flex-start;
      animation: rise 200ms ease both;
    }
    .toast .bar { width: 3px; border-radius: 3px; align-self: stretch; flex: none; background: var(--accent-grad); }
    .toast.ok .bar { background: var(--ok); }
    .toast.err .bar { background: var(--err); }

    .hidden-bucket { display: none !important; }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar glass">
      <div class="brand">
        <div class="brand-mark">V</div>
        <div>
          <div class="brand-title">VaidCord Mock Server <span class="thin">/ ops console</span></div>
          <div class="brand-sub" id="base-url">connecting…</div>
        </div>
      </div>
      <div class="stats">
        <div class="stat"><b id="stat-requests">0</b><span>requests</span></div>
        <div class="stat"><b id="stat-messages">0</b><span>messages</span></div>
        <div class="stat pulse"><b id="stat-sessions">0</b><span>gw sessions</span></div>
        <div class="stat pulse"><b id="stat-events">0</b><span>dispatches</span></div>
      </div>
      <div class="spacer"></div>
      <button class="btn ghost" id="btn-refresh">Refresh</button>
      <button class="btn" id="btn-export">Export state</button>
      <button class="btn" id="btn-import">Import</button>
      <input type="file" id="import-file" accept="application/json" class="hidden-bucket">
      <button class="btn danger" id="btn-reset">Reset</button>
    </header>

    <div class="main">
      <!-- left rail -->
      <aside class="rail glass">
        <div class="rail-scroll">
          <section>
            <h3>Guilds</h3>
            <div class="list" id="guilds"></div>
          </section>
          <section>
            <h3>Channels</h3>
            <div class="list" id="channels"></div>
          </section>
        </div>
      </aside>

      <!-- center chat -->
      <section class="chat glass">
        <div class="chat-head">
          <span class="hash">#</span>
          <span class="name" id="channel-title">–</span>
          <span class="topic" id="channel-topic"></span>
        </div>
        <div class="msgs" id="messages"></div>
        <div class="typing-strip" id="typing"></div>
        <div class="composer">
          <textarea id="composer-input" rows="1" placeholder="Inject a message into the simulation…  (Enter = as user · Ctrl+Enter = as bot)"></textarea>
          <div class="composer-bar">
            <select id="composer-author" title="Author profile for injected messages"></select>
            <button class="btn sm primary" id="composer-inject">Inject as user</button>
            <button class="btn sm" id="composer-bot">Send as bot</button>
            <button class="btn sm ghost" id="composer-typing">Typing</button>
            <span class="hint" id="composer-hint"></span>
          </div>
        </div>
      </section>

      <!-- right console -->
      <aside class="console glass">
        <div class="tabs">
          <button class="tab-btn" data-tab="inspector" data-active="1">Inspector</button>
          <button class="tab-btn" data-tab="gateway" data-active="0">Gateway</button>
          <button class="tab-btn" data-tab="chaos" data-active="0">Chaos</button>
          <button class="tab-btn" data-tab="limits" data-active="0">Limits</button>
          <button class="tab-btn" data-tab="scenario" data-active="0">Scenario</button>
          <button class="tab-btn" data-tab="profiles" data-active="0">Profiles</button>
        </div>

        <div class="pane" data-pane="inspector" data-active="1">
          <section>
            <h3>Request inspector</h3>
            <div class="list" id="requests"></div>
          </section>
        </div>

        <div class="pane" data-pane="gateway" data-active="0">
          <section>
            <h3>Endpoint</h3>
            <div class="kv"><span class="k">WS URL</span><span class="v" id="gw-url">–</span></div>
          </section>
          <section>
            <h3>Sessions</h3>
            <div class="list" id="gw-sessions"></div>
            <div class="form-actions" style="margin-top:9px">
              <button class="btn sm" id="gw-op7">Send op 7 · reconnect</button>
              <button class="btn sm danger" id="gw-op9">Send op 9 · invalidate</button>
            </div>
          </section>
          <section>
            <h3><span class="live-dot" id="sse-dot"></span>Event feed</h3>
            <div class="feed" id="gw-events"></div>
          </section>
        </div>

        <div class="pane" data-pane="chaos" data-active="0">
          <section>
            <h3>Latency injection</h3>
            <div class="grid2">
              <div class="field"><label for="chaos-latency">latency ms</label><input type="number" id="chaos-latency" min="0" step="10" value="0"></div>
              <div class="field"><label for="chaos-jitter">jitter ms</label><input type="number" id="chaos-jitter" min="0" step="10" value="0"></div>
            </div>
          </section>
          <section>
            <h3>Error injection</h3>
            <div class="grid2">
              <div class="field"><label for="chaos-error-rate">error rate %</label><input type="number" id="chaos-error-rate" min="0" max="100" step="5" value="0"></div>
              <div class="field"><label for="chaos-error-status">status</label><input type="number" id="chaos-error-status" min="400" max="599" value="500"></div>
            </div>
          </section>
          <div class="form-actions">
            <button class="btn primary" id="chaos-apply">Apply chaos</button>
            <button class="btn ghost" id="chaos-clear">Clear</button>
          </div>
        </div>

        <div class="pane" data-pane="limits" data-active="0">
          <section>
            <h3>Rate limit simulation</h3>
            <label class="switch"><input type="checkbox" id="rl-enabled"><span class="track"></span><span class="lbl">Enabled</span></label>
          </section>
          <section>
            <h3>Per-route bucket</h3>
            <div class="grid2">
              <div class="field"><label for="rl-route-limit">limit</label><input type="number" id="rl-route-limit" min="1" value="5"></div>
              <div class="field"><label for="rl-route-window">window s</label><input type="number" id="rl-route-window" min="0.1" step="0.5" value="5"></div>
            </div>
          </section>
          <section>
            <h3>Global bucket</h3>
            <div class="grid2">
              <div class="field"><label for="rl-global-limit">limit</label><input type="number" id="rl-global-limit" min="1" value="50"></div>
              <div class="field"><label for="rl-global-window">window s</label><input type="number" id="rl-global-window" min="0.1" step="0.5" value="1"></div>
            </div>
          </section>
          <div class="form-actions">
            <button class="btn primary" id="rl-apply">Apply limits</button>
          </div>
        </div>

        <div class="pane" data-pane="scenario" data-active="0">
          <section>
            <h3>Scripted scenario</h3>
            <div class="field">
              <label for="scenario-json">steps json</label>
              <textarea id="scenario-json" spellcheck="false"></textarea>
            </div>
            <div class="form-actions" style="margin-top:9px">
              <button class="btn primary" id="scenario-run">Run scenario</button>
              <button class="btn ghost" id="scenario-sample">Load sample</button>
            </div>
          </section>
          <section>
            <h3>Runs</h3>
            <div class="list" id="scenario-list"></div>
          </section>
        </div>

        <div class="pane" data-pane="profiles" data-active="0">
          <section>
            <h3>Profiles</h3>
            <div class="list" id="users"></div>
          </section>
          <section>
            <h3>Create profile</h3>
            <div class="grid2">
              <div class="field"><label for="profile-id">id (optional)</label><input type="text" id="profile-id" placeholder="auto"></div>
              <div class="field"><label for="profile-name">username</label><input type="text" id="profile-name" placeholder="Support"></div>
            </div>
            <div class="grid2" style="margin-top:9px">
              <div class="field"><label for="profile-global">display name</label><input type="text" id="profile-global" placeholder="optional"></div>
              <div class="field" style="justify-content:flex-end">
                <label class="switch" style="margin-top:16px"><input type="checkbox" id="profile-bot"><span class="track"></span><span class="lbl">Bot</span></label>
              </div>
            </div>
            <div class="form-actions" style="margin-top:10px">
              <button class="btn primary" id="profile-create">Create profile</button>
            </div>
          </section>
        </div>
      </aside>
    </div>
  </div>

  <div id="ui-notice"></div>

  <script>
    "use strict";
    const d = (id) => document.getElementById(id);

    // ---------------- client state ----------------
    let state = null;
    let activeChannel = null;
    let sseCount = 0;
    const expandedRequests = new Set();
    const feedItems = [];

    // ---------------- helpers ----------------
    function escapeHtml(value) {
      return String(value == null ? "" : value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
    function initials(name) {
      const parts = String(name || "?").trim().split(/\s+/);
      const chars = parts.slice(0, 2).map((p) => p.charAt(0).toUpperCase());
      return chars.join("") || "?";
    }
    function timeOf(iso) {
      if (!iso) return "";
      const t = new Date(iso);
      if (Number.isNaN(t.getTime())) return "";
      return t.toTimeString().slice(0, 8);
    }
    function toast(message, kind) {
      const box = d("ui-notice");
      const node = document.createElement("div");
      node.className = "toast" + (kind ? " " + kind : "");
      node.innerHTML = '<span class="bar"></span><span>' + escapeHtml(message) + "</span>";
      box.appendChild(node);
      setTimeout(() => {
        node.style.transition = "opacity 300ms ease, transform 300ms ease";
        node.style.opacity = "0";
        node.style.transform = "translateY(6px)";
        setTimeout(() => node.remove(), 320);
      }, 3600);
      while (box.children.length > 5) box.firstChild.remove();
    }
    async function apiFetch(path, options) {
      const response = await fetch(path, options);
      if (!response.ok) {
        let detail = response.status + " " + response.statusText;
        try {
          const body = await response.json();
          if (body && body.message) detail = body.message + " (" + response.status + ")";
        } catch (err) { /* not json */ }
        throw new Error(detail);
      }
      return response;
    }
    function guard(fn) {
      return async () => {
        try { await fn(); }
        catch (err) { toast(err.message || String(err), "err"); console.error(err); }
      };
    }
    function bind(id, fn) {
      const el = d(id);
      if (el) el.addEventListener("click", guard(fn));
    }

    // ---------------- rendering ----------------
    function emptyState(glyph, title, hint) {
      return '<div class="empty"><div class="glyph">' + glyph + '</div><div>' + escapeHtml(title) +
             '</div><div class="hint">' + escapeHtml(hint) + "</div></div>";
    }

    function renderGuilds() {
      const box = d("guilds");
      if (!state.guilds.length) {
        box.innerHTML = emptyState("◇", "No guilds yet", "Inject a message with a guild_id to create one.");
        return;
      }
      box.innerHTML = state.guilds.map((g) =>
        '<div class="guild-card">' +
          '<div class="guild-badge">' + escapeHtml(initials(g.name)) + "</div>" +
          '<div><div class="guild-name">' + escapeHtml(g.name) + "</div>" +
          '<div class="guild-meta">id ' + escapeHtml(g.id) + " · " + escapeHtml(String(g.member_count)) + " members</div></div>" +
        "</div>"
      ).join("");
    }

    function renderChannels() {
      const box = d("channels");
      if (!state.channels.length) {
        box.innerHTML = emptyState("⌗", "No channels", "Channels appear when created via REST or injection.");
        return;
      }
      if (!activeChannel || !state.channels.some((c) => c.id === activeChannel)) {
        activeChannel = state.channels[0].id;
      }
      box.innerHTML = state.channels.map((c) => {
        const count = state.messages.filter((m) => m.channel_id === c.id).length;
        const glyph = c.type === 1 ? "@" : "#";
        const active = c.id === activeChannel ? " active" : "";
        return '<div class="row-item' + active + '" data-channel="' + escapeHtml(c.id) + '">' +
          '<span class="glyph">' + glyph + "</span>" +
          '<span class="label">' + escapeHtml(c.name) + "</span>" +
          '<span class="meta">' + count + "</span></div>";
      }).join("");
      box.querySelectorAll("[data-channel]").forEach((el) => {
        el.addEventListener("click", () => {
          activeChannel = el.dataset.channel;
          renderChannels();
          renderMessages();
          renderChannelHead();
        });
      });
    }

    function renderChannelHead() {
      const channel = state.channels.find((c) => c.id === activeChannel);
      d("channel-title").textContent = channel ? channel.name : "–";
      d("channel-topic").textContent = channel && channel.topic ? channel.topic : "";
      d("composer-hint").textContent = channel ? "channel " + channel.id : "";
    }

    function renderMessages() {
      const box = d("messages");
      const wasPinned = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
      const messages = state.messages.filter((m) => m.channel_id === activeChannel);
      if (!messages.length) {
        box.innerHTML = emptyState("⌁", "Silence on the wire", "Send a message with the composer below, or hit the REST API.");
        return;
      }
      box.innerHTML = messages.map((m) => {
        const bot = m.author && m.author.bot;
        const edited = m.edited_timestamp ? ' <span class="edited">(edited)</span>' : "";
        return '<div class="msg">' +
          '<div class="avatar' + (bot ? " bot" : "") + '">' + escapeHtml(initials(m.author && m.author.username)) + "</div>" +
          '<div class="msg-body"><div class="msg-top">' +
            '<span class="msg-author">' + escapeHtml(m.author ? m.author.username : "?") + "</span>" +
            (bot ? '<span class="chip bot">bot</span>' : "") +
            '<span class="msg-time">' + timeOf(m.timestamp) + "</span>" +
            '<span class="msg-id">' + escapeHtml(m.id) + "</span>" +
          "</div>" +
          '<div class="msg-content">' + escapeHtml(m.content) + edited + "</div></div></div>";
      }).join("");
      if (wasPinned) box.scrollTop = box.scrollHeight;
    }

    function renderTyping() {
      const box = d("typing");
      const cutoff = Date.now() - 8000;
      const active = state.typing_events.filter((t) =>
        t.channel_id === activeChannel && new Date(t.timestamp).getTime() > cutoff);
      if (!active.length) { box.innerHTML = ""; return; }
      const names = Array.from(new Set(active.map((t) => t.username)));
      box.innerHTML = escapeHtml(names.join(", ")) + ' is typing<span class="dots"></span>';
    }

    function statusClass(status) {
      if (status == null) return "status-na";
      if (status === 429) return "status-429";
      if (status >= 500) return "status-5xx";
      if (status >= 400) return "status-4xx";
      if (status >= 300) return "status-3xx";
      return "status-2xx";
    }

    function renderRequests() {
      const box = d("requests");
      if (!state.requests.length) {
        box.innerHTML = emptyState("⇄", "No traffic yet", "Every REST and control-plane call lands here with status and latency.");
        return;
      }
      const rows = state.requests.slice(-120).reverse();
      box.innerHTML = rows.map((r) => {
        const key = r.request_id || (r.method + " " + r.path);
        const open = expandedRequests.has(key) ? " open" : "";
        const status = r.status == null ? "…" : r.status;
        const ms = r.duration_ms == null ? "" : r.duration_ms + " ms";
        const body = r.json ? JSON.stringify(r.json, null, 2) : "";
        return '<div class="req' + open + '" data-req="' + escapeHtml(key) + '">' +
          '<div class="req-row">' +
            '<span class="method ' + escapeHtml(r.method) + '">' + escapeHtml(r.method) + "</span>" +
            '<span class="req-path" title="' + escapeHtml(r.path) + '">' + escapeHtml(r.path) + "</span>" +
            '<span class="status-pill ' + statusClass(r.status) + '">' + escapeHtml(String(status)) + "</span>" +
            '<span class="req-ms">' + escapeHtml(ms) + "</span>" +
          "</div>" +
          (body ? '<pre class="req-json">' + escapeHtml(body) + "</pre>" : "") +
        "</div>";
      }).join("");
      box.querySelectorAll(".req").forEach((el) => {
        el.querySelector(".req-row").addEventListener("click", () => {
          const key = el.dataset.req;
          if (expandedRequests.has(key)) expandedRequests.delete(key); else expandedRequests.add(key);
          el.classList.toggle("open");
        });
      });
    }

    function renderGateway() {
      d("gw-url").textContent = state.ws_url || "–";
      const box = d("gw-sessions");
      const sessions = (state.gateway && state.gateway.sessions) || [];
      if (!sessions.length) {
        box.innerHTML = emptyState("⛓", "No gateway sessions", "Point a bot at GET /api/v10/gateway/bot and IDENTIFY over the socket.");
      } else {
        box.innerHTML = sessions.map((s) =>
          '<div class="session-card">' +
            '<div class="session-top"><span class="dot ' + (s.connected ? "on" : "off") + '"></span>' +
            '<span class="session-id">' + escapeHtml(s.session_id) + "</span>" +
            (s.connected ? '<span class="chip current">live</span>' : '<span class="chip cancelled">idle</span>') +
            "</div>" +
            '<div class="session-meta"><span>seq ' + s.seq + "</span><span>♥ " + s.heartbeats +
            "</span><span>resumes " + s.resume_count + "</span><span>buffer " + s.buffered_events + "</span></div>" +
          "</div>"
        ).join("");
      }
      renderFeed();
    }

    function renderFeed() {
      const box = d("gw-events");
      if (!feedItems.length) {
        box.innerHTML = emptyState("⚡", "Waiting for dispatches", "Gateway events stream here live over SSE.");
        return;
      }
      box.innerHTML = feedItems.slice(-60).reverse().map((e) => {
        if (e.kind === "dispatch") {
          return '<div class="feed-item"><span class="t">' + escapeHtml(e.t) + "</span>" +
                 "<span>→ " + e.delivered + " ws</span>" +
                 '<span class="when">' + timeOf(e.at) + "</span></div>";
        }
        if (e.kind === "request") {
          return '<div class="feed-item"><span class="method ' + escapeHtml(e.method) + '">' + escapeHtml(e.method) + "</span>" +
                 "<span>" + escapeHtml(e.path) + "</span>" +
                 '<span class="status-pill ' + statusClass(e.status) + '">' + e.status + "</span>" +
                 '<span class="when">' + timeOf(e.at) + "</span></div>";
        }
        return '<div class="feed-item"><span class="t">' + escapeHtml(e.kind) + "</span>" +
               '<span class="when">' + timeOf(e.at) + "</span></div>";
      }).join("");
    }

    function renderUsers() {
      const box = d("users");
      const currentId = state.current_user ? state.current_user.id : null;
      box.innerHTML = state.users.map((u) => {
        const isCurrent = u.id === currentId;
        return '<div class="user-row' + (isCurrent ? " current" : "") + '">' +
          '<div class="avatar' + (u.bot ? " bot" : "") + '">' + escapeHtml(initials(u.username)) + "</div>" +
          '<div style="flex:1;min-width:0"><div class="uname">' + escapeHtml(u.username) +
          (u.bot ? ' <span class="chip bot">bot</span>' : "") +
          (isCurrent ? ' <span class="chip current">current</span>' : "") +
          '</div><div class="uid">id ' + escapeHtml(u.id) + "</div></div>" +
          (isCurrent ? "" : '<button class="btn sm" data-use="' + escapeHtml(u.id) + '">Use</button>') +
        "</div>";
      }).join("");
      box.querySelectorAll("[data-use]").forEach((el) => {
        el.addEventListener("click", guard(async () => {
          await apiFetch("/api/mock/current-user", {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({user_id: el.dataset.use})
          });
          toast("Current user switched", "ok");
          await refresh();
        }));
      });
      // composer author select
      const select = d("composer-author");
      const previous = select.value;
      select.innerHTML = state.users.map((u) =>
        '<option value="' + escapeHtml(u.id) + '">' + escapeHtml(u.username) + (u.bot ? " [bot]" : "") + "</option>"
      ).join("");
      const fallback = state.users.find((u) => !u.bot);
      select.value = previous && state.users.some((u) => u.id === previous)
        ? previous
        : (fallback ? fallback.id : (state.users[0] ? state.users[0].id : ""));
    }

    function renderScenarios() {
      const box = d("scenario-list");
      const scenarios = state.scenarios || [];
      if (!scenarios.length) {
        box.innerHTML = emptyState("▶", "No scenario runs", "Script timed events as JSON and press Run.");
        return;
      }
      box.innerHTML = scenarios.slice().reverse().map((s) =>
        '<div class="scenario-row">' +
          '<span class="chip ' + escapeHtml(s.status) + '">' + escapeHtml(s.status) + "</span>" +
          '<span class="sname">' + escapeHtml(s.name) + "</span>" +
          '<span class="sprog">' + s.steps_done + "/" + s.steps_total + "</span>" +
          (s.status === "running" ? '<button class="btn sm danger" data-cancel="' + escapeHtml(s.id) + '">Stop</button>' : "") +
        "</div>"
      ).join("");
      box.querySelectorAll("[data-cancel]").forEach((el) => {
        el.addEventListener("click", guard(async () => {
          await apiFetch("/api/mock/scenario/" + el.dataset.cancel, {method: "DELETE"});
          toast("Scenario cancelled");
          await refresh();
        }));
      });
    }

    function renderControls() {
      if (document.activeElement && document.activeElement.closest(".pane[data-pane='chaos'], .pane[data-pane='limits']")) {
        return; // don't clobber values while the operator is editing
      }
      const chaos = state.chaos || {};
      d("chaos-latency").value = chaos.latency_ms != null ? chaos.latency_ms : 0;
      d("chaos-jitter").value = chaos.jitter_ms != null ? chaos.jitter_ms : 0;
      d("chaos-error-rate").value = chaos.error_rate != null ? Math.round(chaos.error_rate * 100) : 0;
      d("chaos-error-status").value = chaos.error_status != null ? chaos.error_status : 500;
      const rl = state.rate_limit || {};
      d("rl-enabled").checked = !!rl.enabled;
      d("rl-route-limit").value = rl.per_route_limit != null ? rl.per_route_limit : 5;
      d("rl-route-window").value = rl.per_route_window != null ? rl.per_route_window : 5;
      d("rl-global-limit").value = rl.global_limit != null ? rl.global_limit : 50;
      d("rl-global-window").value = rl.global_window != null ? rl.global_window : 1;
    }

    function renderStats() {
      d("stat-requests").textContent = state.requests.length;
      d("stat-messages").textContent = state.messages.length;
      const sessions = (state.gateway && state.gateway.sessions) || [];
      d("stat-sessions").textContent = sessions.filter((s) => s.connected).length;
      d("stat-events").textContent = (state.gateway && state.gateway.events_dispatched) || 0;
      d("base-url").textContent = state.base_url + "  ·  " + state.ws_url;
    }

    async function refresh() {
      const response = await apiFetch("/api/mock/state");
      state = await response.json();
      renderStats();
      renderGuilds();
      renderChannels();
      renderChannelHead();
      renderMessages();
      renderTyping();
      renderRequests();
      renderGateway();
      renderUsers();
      renderScenarios();
      renderControls();
    }

    // ---------------- composer actions ----------------
    async function injectMessage() {
      const input = d("composer-input");
      const content = input.value.trim();
      if (!content || !activeChannel) return;
      const authorId = d("composer-author").value;
      const author = (state.users || []).find((u) => u.id === authorId);
      await apiFetch("/api/mock/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          channel_id: activeChannel,
          content: content,
          author_id: authorId || "2",
          author_username: author ? author.username : "MockUser",
          author_bot: author ? !!author.bot : false
        })
      });
      input.value = "";
      autosize();
      await refresh();
    }
    async function sendAsBot() {
      const input = d("composer-input");
      const content = input.value.trim();
      if (!content || !activeChannel) return;
      await apiFetch("/api/v10/channels/" + activeChannel + "/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({content: content})
      });
      input.value = "";
      autosize();
      await refresh();
    }
    async function triggerTyping() {
      if (!activeChannel) return;
      await apiFetch("/api/v10/channels/" + activeChannel + "/typing", {method: "POST"});
      await refresh();
    }
    function autosize() {
      const input = d("composer-input");
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 160) + "px";
    }

    // ---------------- header actions ----------------
    async function exportState() {
      const response = await apiFetch("/api/mock/state/export");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vaidcord-mock-state.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast("State exported", "ok");
    }
    async function importState(file) {
      const text = await file.text();
      const payload = JSON.parse(text);
      await apiFetch("/api/mock/state/import", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      toast("State imported", "ok");
      await refresh();
    }
    async function resetState() {
      await apiFetch("/api/mock/reset", {method: "POST"});
      expandedRequests.clear();
      feedItems.length = 0;
      toast("Simulation reset");
      await refresh();
    }

    // ---------------- console actions ----------------
    async function applyChaos() {
      await apiFetch("/api/mock/chaos", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          latency_ms: Number(d("chaos-latency").value) || 0,
          jitter_ms: Number(d("chaos-jitter").value) || 0,
          error_rate: (Number(d("chaos-error-rate").value) || 0) / 100,
          error_status: Number(d("chaos-error-status").value) || 500
        })
      });
      toast("Chaos settings applied", "ok");
      await refresh();
    }
    async function clearChaos() {
      await apiFetch("/api/mock/chaos", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({latency_ms: 0, jitter_ms: 0, error_rate: 0, error_status: 500})
      });
      toast("Chaos cleared");
      await refresh();
    }
    async function applyLimits() {
      await apiFetch("/api/mock/ratelimit", {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          enabled: d("rl-enabled").checked,
          per_route_limit: Number(d("rl-route-limit").value) || 5,
          per_route_window: Number(d("rl-route-window").value) || 5,
          global_limit: Number(d("rl-global-limit").value) || 50,
          global_window: Number(d("rl-global-window").value) || 1
        })
      });
      toast("Rate limits updated", "ok");
      await refresh();
    }
    async function runScenario() {
      const raw = d("scenario-json").value.trim();
      if (!raw) { toast("Scenario JSON is empty", "err"); return; }
      const steps = JSON.parse(raw);
      const payload = Array.isArray(steps) ? {steps: steps} : steps;
      await apiFetch("/api/mock/scenario", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      toast("Scenario started", "ok");
      await refresh();
    }
    function loadScenarioSample() {
      const sample = {
        name: "greeting-burst",
        steps: [
          {at: 0.0, action: "typing", data: {channel_id: "123", user_id: "2"}},
          {at: 0.8, action: "message", data: {channel_id: "123", content: "hey! anyone around?", author_id: "2", author_username: "MockUser"}},
          {at: 1.6, action: "message", data: {channel_id: "123", content: "test message burst", author_id: "2", author_username: "MockUser"}},
          {at: 2.2, action: "dispatch", data: {t: "GUILD_MEMBER_ADD", d: {guild_id: "999", user: {id: "42", username: "Newcomer"}}}}
        ]
      };
      d("scenario-json").value = JSON.stringify(sample, null, 2);
    }
    async function sendOp7() {
      const response = await apiFetch("/api/mock/gateway/reconnect", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}"
      });
      const body = await response.json();
      toast("op 7 sent to " + body.sent + " session(s)", "ok");
    }
    async function sendOp9() {
      const response = await apiFetch("/api/mock/gateway/invalidate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({resumable: false})
      });
      const body = await response.json();
      toast("op 9 sent to " + body.sent + " session(s)", "ok");
      await refresh();
    }
    async function createProfile() {
      const payload = {
        username: d("profile-name").value || "Profile",
        global_name: d("profile-global").value || null,
        bot: d("profile-bot").checked
      };
      const id = d("profile-id").value.trim();
      if (id) payload.id = id;
      await apiFetch("/api/mock/profiles", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      d("profile-id").value = "";
      d("profile-name").value = "";
      d("profile-global").value = "";
      d("profile-bot").checked = false;
      toast("Profile created", "ok");
      await refresh();
    }

    // ---------------- tabs ----------------
    function activateTab(name) {
      document.querySelectorAll(".tab-btn").forEach((b) => {
        b.dataset.active = b.dataset.tab === name ? "1" : "0";
      });
      document.querySelectorAll(".pane").forEach((p) => {
        p.dataset.active = p.dataset.pane === name ? "1" : "0";
      });
    }
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.addEventListener("click", () => activateTab(b.dataset.tab));
    });

    // ---------------- SSE live feed ----------------
    function connectSse() {
      let source;
      try { source = new EventSource("/api/mock/events"); }
      catch (err) { return; }
      source.onopen = () => { d("sse-dot").classList.add("on"); };
      source.onerror = () => {
        d("sse-dot").classList.remove("on");
        source.close();
        setTimeout(connectSse, 3000);
      };
      source.onmessage = (event) => {
        let payload;
        try { payload = JSON.parse(event.data); } catch (err) { return; }
        feedItems.push(payload);
        if (feedItems.length > 200) feedItems.splice(0, feedItems.length - 200);
        sseCount += 1;
        renderFeed();
        if (payload.kind === "dispatch") {
          d("stat-events").textContent = String(Number(d("stat-events").textContent || "0") + 1);
        }
      };
    }

    // ---------------- wiring ----------------
    const composerInput = d("composer-input");
    composerInput.addEventListener("input", autosize);
    composerInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        const asBot = event.ctrlKey || event.metaKey;
        guard(asBot ? sendAsBot : injectMessage)();
      }
    });

    bind("composer-inject", injectMessage);
    bind("composer-bot", sendAsBot);
    bind("composer-typing", triggerTyping);
    bind("btn-refresh", refresh);
    bind("btn-export", exportState);
    bind("btn-reset", resetState);
    bind("chaos-apply", applyChaos);
    bind("chaos-clear", clearChaos);
    bind("rl-apply", applyLimits);
    bind("scenario-run", runScenario);
    bind("gw-op7", sendOp7);
    bind("gw-op9", sendOp9);
    bind("profile-create", createProfile);
    d("scenario-sample").addEventListener("click", loadScenarioSample);
    d("btn-import").addEventListener("click", () => d("import-file").click());
    d("import-file").addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (file) guard(() => importState(file))();
      event.target.value = "";
    });

    // initial paint + polling + live feed
    loadScenarioSample();
    connectSse();
    refresh().catch((err) => toast(err.message || String(err), "err"));
    setInterval(() => refresh().catch(() => {}), 2000);
  </script>
</body>
</html>
"""


def validate_mock_ui() -> None:
    """Cheap validation for generated mock UI HTML and embedded JavaScript."""
    if "<script>" not in MOCK_UI_HTML or "</script>" not in MOCK_UI_HTML:
        raise ValueError("Mock UI HTML must contain one inline script block")
    script = MOCK_UI_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
    if '""":' in script:
        raise ValueError("Mock UI JavaScript contains an unescaped Python triple-quote artifact")
    required_ids = (
        "messages",
        "requests",
        "users",
        "channels",
        "guilds",
        "typing",
        "ui-notice",
        "gw-sessions",
        "gw-events",
        "scenario-list",
        "composer-input",
    )
    for element_id in required_ids:
        if f'id="{element_id}"' not in MOCK_UI_HTML:
            raise ValueError(f"Mock UI is missing required element id={element_id!r}")
