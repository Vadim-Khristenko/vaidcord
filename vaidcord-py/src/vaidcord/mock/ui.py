"""Static UI for the local Discord mock server.

The HTML below is a self-contained single-page app served by
:mod:`vaidcord.mock.server`. The visual language deliberately mirrors the
real Discord client: a left server bar, a channel sidebar, a chat column with
an inline composer, and a right-hand member list. The scripting API surface
(element ids and ``apiFetch`` calls) is intentionally preserved so existing
tests and tooling continue to work.
"""


MOCK_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VaidCord Mock Server</title>
  <style>
    :root {
      color-scheme: dark;
      --bg-tertiary: #1e1f22;
      --bg-secondary: #2b2d31;
      --bg-secondary-alt: #232428;
      --bg-primary: #313338;
      --bg-accent: #404249;
      --bg-modifier-hover: rgba(78, 80, 88, 0.32);
      --bg-modifier-active: rgba(79, 84, 92, 0.48);
      --bg-modifier-selected: rgba(79, 84, 92, 0.6);
      --bg-floating: #111214;
      --channeltextarea: #383a40;
      --interactive-normal: #b5bac1;
      --interactive-hover: #dbdee1;
      --interactive-active: #ffffff;
      --interactive-muted: #4e5058;
      --header-primary: #f2f3f5;
      --header-secondary: #b5bac1;
      --text-normal: #dbdee1;
      --text-muted: #949ba4;
      --text-link: #00a8fc;
      --brand: #5865f2;
      --brand-hover: #4752c4;
      --brand-soft: rgba(88, 101, 242, 0.16);
      --status-online: #23a55a;
      --status-idle: #f0b232;
      --status-dnd: #f23f43;
      --status-offline: #80848e;
      --status-streaming: #593695;
      --danger: #f23f43;
      --danger-soft: rgba(242, 63, 67, 0.18);
      --success: #23a55a;
      --success-soft: rgba(35, 165, 90, 0.16);
      --warning: #f0b232;
      --border: rgba(0, 0, 0, 0.32);
      --elevation-low: 0 1px 0 rgba(4, 4, 5, 0.2), 0 1.5px 0 rgba(6, 6, 7, 0.05), 0 2px 0 rgba(4, 4, 5, 0.05);
      --elevation-stroke: 0 0 0 1px rgba(0, 0, 0, 0.18);
      --elevation-medium: 0 4px 4px rgba(0, 0, 0, 0.16);
      --font-display: "gg sans", "Whitney", "Helvetica Neue", Helvetica, Arial, sans-serif;
      --font-mono: "Source Code Pro", "Consolas", "Andale Mono", "Lucida Console", monospace;
      --servers-width: 72px;
      --sidebar-width: 240px;
      --members-width: 240px;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--bg-tertiary);
      color: var(--text-normal);
      font: 14px/1.375 var(--font-display);
      -webkit-font-smoothing: antialiased;
      overflow: hidden;
    }
    button { font: inherit; }
    input, textarea {
      font: inherit;
      color: var(--text-normal);
    }
    /* ============= shell ============= */
    .app {
      display: grid;
      grid-template-columns: var(--servers-width) var(--sidebar-width) minmax(0, 1fr) var(--members-width);
      height: 100vh;
      width: 100vw;
    }
    /* ============= server bar ============= */
    .servers {
      background: var(--bg-tertiary);
      padding: 12px 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      overflow-y: auto;
      scrollbar-width: none;
    }
    .servers::-webkit-scrollbar { display: none; }
    .server-pill {
      position: relative;
      width: 48px;
      height: 48px;
    }
    .server-pill::before {
      content: "";
      position: absolute;
      left: -16px;
      top: 50%;
      transform: translateY(-50%) scale(0);
      width: 8px;
      height: 8px;
      border-radius: 4px;
      background: var(--interactive-active);
      transition: transform 160ms ease, height 160ms ease;
    }
    .server-pill[data-active="1"]::before { transform: translateY(-50%) scale(1); height: 40px; }
    .server-pill:hover::before { transform: translateY(-50%) scale(1); height: 20px; }
    .server-pill button {
      width: 48px;
      height: 48px;
      border: 0;
      border-radius: 24px;
      background: var(--bg-primary);
      color: var(--header-primary);
      font-weight: 700;
      letter-spacing: 0.02em;
      cursor: pointer;
      transition: background-color 120ms ease, border-radius 160ms ease, color 120ms ease;
      display: grid;
      place-items: center;
      font-size: 16px;
      line-height: 1;
      padding: 0;
    }
    .server-pill button:hover, .server-pill[data-active="1"] button {
      border-radius: 16px;
      background: var(--brand);
      color: white;
    }
    .server-pill.home button {
      background: var(--bg-primary);
      color: var(--brand);
    }
    .server-pill.home[data-active="1"] button, .server-pill.home button:hover {
      background: var(--brand);
      color: white;
    }
    .server-divider {
      width: 32px;
      height: 2px;
      background: rgba(255, 255, 255, 0.06);
      margin: 4px 0;
      border-radius: 1px;
    }
    /* ============= channel sidebar ============= */
    .sidebar {
      background: var(--bg-secondary);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .sidebar-header {
      height: 48px;
      flex: 0 0 48px;
      padding: 0 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: var(--elevation-low);
      font-weight: 600;
      color: var(--header-primary);
      cursor: default;
      gap: 8px;
    }
    .sidebar-header .guild-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .sidebar-header .chev {
      color: var(--interactive-normal);
      font-size: 18px;
    }
    .channel-scroller {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 16px 0 80px;
    }
    .channel-scroller::-webkit-scrollbar { width: 8px; }
    .channel-scroller::-webkit-scrollbar-thumb { background: rgba(0, 0, 0, 0.32); border-radius: 4px; }
    .channel-scroller::-webkit-scrollbar-track { background: transparent; }
    .channel-category {
      padding: 16px 8px 4px 18px;
      display: flex;
      align-items: center;
      gap: 4px;
      color: var(--interactive-normal);
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      cursor: pointer;
    }
    .channel-category:hover { color: var(--interactive-hover); }
    .channel-category .arrow {
      font-size: 10px;
      transition: transform 120ms ease;
    }
    .channel {
      margin: 1px 8px;
      padding: 6px 8px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      color: var(--interactive-normal);
      font-size: 14px;
      font-weight: 500;
      min-width: 0;
    }
    .channel:hover { background: var(--bg-modifier-hover); color: var(--interactive-hover); }
    .channel[data-active="1"] {
      background: var(--bg-modifier-selected);
      color: var(--interactive-active);
    }
    .channel .hash {
      color: var(--interactive-muted);
      font-size: 20px;
      line-height: 1;
      flex: 0 0 20px;
      text-align: center;
    }
    .channel[data-active="1"] .hash, .channel:hover .hash { color: var(--interactive-normal); }
    .channel .channel-name {
      flex: 1 1 auto;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .channel .channel-badge {
      flex: 0 0 auto;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 8px;
      background: var(--bg-tertiary);
      color: var(--interactive-normal);
    }
    .panel-user {
      flex: 0 0 52px;
      background: var(--bg-secondary-alt);
      padding: 0 8px;
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 -1px 0 rgba(4, 4, 5, 0.2);
    }
    .panel-user .avatar { width: 32px; height: 32px; border-radius: 50%; }
    .panel-user .pu-info { flex: 1 1 auto; min-width: 0; }
    .panel-user .pu-name {
      font-size: 14px;
      font-weight: 600;
      color: var(--header-primary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      line-height: 1.2;
    }
    .panel-user .pu-tag {
      font-size: 12px;
      color: var(--text-muted);
      font-family: var(--font-mono);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .panel-user .pu-actions {
      display: flex;
      gap: 2px;
    }
    .icon-btn {
      width: 32px;
      height: 32px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--interactive-normal);
      cursor: pointer;
      display: grid;
      place-items: center;
      transition: background-color 120ms ease, color 120ms ease;
    }
    .icon-btn:hover { background: var(--bg-modifier-hover); color: var(--interactive-hover); }
    /* ============= main chat ============= */
    .main {
      background: var(--bg-primary);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .channel-header {
      height: 48px;
      flex: 0 0 48px;
      padding: 0 16px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: var(--elevation-low);
    }
    .channel-header .ch-name {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 700;
      color: var(--header-primary);
      font-size: 16px;
    }
    .channel-header .ch-name .hash {
      color: var(--interactive-muted);
      font-size: 24px;
      line-height: 1;
    }
    .channel-header .divider {
      width: 1px;
      height: 24px;
      background: rgba(78, 80, 88, 0.48);
    }
    .channel-header .topic {
      color: var(--text-muted);
      font-size: 14px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1 1 auto;
      min-width: 0;
    }
    .channel-header .header-actions {
      display: flex;
      gap: 4px;
      flex: 0 0 auto;
    }
    /* ============= messages ============= */
    .messages-pane {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 16px 0 8px;
      display: flex;
      flex-direction: column-reverse;
    }
    .messages-pane::-webkit-scrollbar { width: 14px; }
    .messages-pane::-webkit-scrollbar-thumb { background: var(--bg-tertiary); border-radius: 8px; border: 4px solid var(--bg-primary); }
    .messages-pane::-webkit-scrollbar-track { background: transparent; }
    .empty-state {
      padding: 40px 24px;
      color: var(--text-muted);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }
    .empty-state .big {
      width: 68px;
      height: 68px;
      border-radius: 50%;
      background: var(--bg-accent);
      display: grid;
      place-items: center;
      color: var(--text-muted);
      font-size: 32px;
      margin-bottom: 8px;
    }
    .message {
      padding: 2px 48px 2px 72px;
      position: relative;
      transition: background-color 80ms ease;
    }
    .message:hover { background: rgba(4, 4, 5, 0.07); }
    .message.start { margin-top: 16px; padding-top: 4px; padding-bottom: 4px; }
    .message .avatar {
      position: absolute;
      left: 16px;
      top: 4px;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      cursor: pointer;
    }
    .message .header-line {
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 2px;
    }
    .message .author {
      color: var(--header-primary);
      font-weight: 600;
      font-size: 16px;
      cursor: pointer;
    }
    .message .author:hover { text-decoration: underline; }
    .message .author.bot-author { color: #5865f2; }
    .message .bot-tag {
      background: var(--brand);
      color: white;
      font-size: 10px;
      font-weight: 600;
      padding: 1px 4px;
      border-radius: 3px;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      vertical-align: middle;
      transform: translateY(-1px);
    }
    .message .timestamp {
      color: var(--text-muted);
      font-size: 12px;
    }
    .message .edited {
      color: var(--text-muted);
      font-size: 10px;
      margin-left: 4px;
    }
    .message .body {
      color: var(--text-normal);
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 16px;
      line-height: 1.375;
    }
    .message .meta-line {
      color: var(--text-muted);
      font-size: 11px;
      margin-top: 2px;
      font-family: var(--font-mono);
    }
    .message .timestamp-gutter {
      position: absolute;
      left: 16px;
      width: 40px;
      text-align: center;
      color: var(--text-muted);
      font-size: 11px;
      opacity: 0;
      pointer-events: none;
    }
    .message:not(.start):hover .timestamp-gutter { opacity: 1; }
    .message-actions {
      position: absolute;
      right: 16px;
      top: -16px;
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--elevation-medium);
      display: none;
      padding: 2px;
      gap: 0;
    }
    .message:hover .message-actions { display: flex; }
    .system-line {
      padding: 8px 24px;
      color: var(--text-muted);
      font-size: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .system-line .rule { flex: 1 1 auto; height: 1px; background: rgba(78, 80, 88, 0.48); }
    /* ============= composer ============= */
    .composer-wrap {
      flex: 0 0 auto;
      padding: 0 16px 24px;
    }
    .typing-line {
      height: 24px;
      padding: 0 4px;
      font-size: 13px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .typing-dots {
      display: inline-flex;
      gap: 2px;
    }
    .typing-dots span {
      width: 4px;
      height: 4px;
      background: var(--text-muted);
      border-radius: 50%;
      animation: typing-bounce 1.2s infinite ease-in-out;
    }
    .typing-dots span:nth-child(2) { animation-delay: 0.15s; }
    .typing-dots span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes typing-bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
      40% { transform: translateY(-3px); opacity: 1; }
    }
    .composer {
      background: var(--channeltextarea);
      border-radius: 8px;
      padding: 0 16px;
      display: flex;
      align-items: flex-end;
      gap: 12px;
      min-height: 44px;
    }
    .composer .add-btn {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--interactive-normal);
      color: var(--bg-primary);
      border: 0;
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
      align-self: center;
      flex: 0 0 24px;
      display: grid;
      place-items: center;
    }
    .composer .add-btn:hover { background: var(--interactive-hover); }
    .composer .input {
      flex: 1 1 auto;
      background: transparent;
      border: 0;
      outline: 0;
      padding: 11px 0;
      color: var(--text-normal);
      resize: none;
      font-size: 16px;
      line-height: 1.375;
      max-height: 200px;
      min-height: 22px;
    }
    .composer .input::placeholder { color: var(--text-muted); }
    .composer .toolbox {
      display: flex;
      align-items: center;
      gap: 4px;
      align-self: center;
      flex: 0 0 auto;
    }
    .composer .send-btn {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--brand);
      color: white;
      border: 0;
      cursor: pointer;
      display: grid;
      place-items: center;
      transition: background-color 120ms ease, transform 120ms ease;
    }
    .composer .send-btn:hover { background: var(--brand-hover); transform: scale(1.05); }
    /* ============= members panel ============= */
    .members {
      background: var(--bg-secondary);
      display: flex;
      flex-direction: column;
      min-width: 0;
      box-shadow: -1px 0 0 rgba(0, 0, 0, 0.12);
    }
    .members-tabs {
      display: flex;
      gap: 4px;
      padding: 8px;
      border-bottom: 1px solid rgba(0, 0, 0, 0.18);
    }
    .tab-btn {
      flex: 1 1 auto;
      padding: 6px 10px;
      border-radius: 4px;
      border: 0;
      background: transparent;
      color: var(--interactive-normal);
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      transition: background-color 120ms ease, color 120ms ease;
    }
    .tab-btn:hover { background: var(--bg-modifier-hover); color: var(--interactive-hover); }
    .tab-btn[data-active="1"] { background: var(--bg-modifier-selected); color: var(--interactive-active); }
    .members-scroller {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 12px 8px;
    }
    .members-scroller::-webkit-scrollbar { width: 8px; }
    .members-scroller::-webkit-scrollbar-thumb { background: var(--bg-tertiary); border-radius: 4px; }
    .members-scroller::-webkit-scrollbar-track { background: transparent; }
    .group-label {
      padding: 4px 8px;
      color: var(--header-secondary);
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .member {
      padding: 4px 8px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      color: var(--interactive-normal);
      transition: background-color 80ms ease;
    }
    .member:hover { background: var(--bg-modifier-hover); color: var(--interactive-hover); }
    .member .avatar-wrap {
      position: relative;
      flex: 0 0 32px;
    }
    .member .avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
    }
    .member .status-dot {
      position: absolute;
      right: -2px;
      bottom: -2px;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--status-online);
      border: 3px solid var(--bg-secondary);
    }
    .member .status-dot.bot { background: var(--brand); }
    .member .name {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 500;
    }
    .member .role {
      font-size: 11px;
      color: var(--text-muted);
      flex: 0 0 auto;
    }
    /* ============= secondary tab pane (settings/devtools) ============= */
    .panel {
      padding: 16px 12px;
    }
    .panel h3 {
      margin: 16px 12px 8px;
      color: var(--header-secondary);
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0.02em;
    }
    .panel h3:first-child { margin-top: 0; }
    .form-row {
      padding: 6px 12px;
      display: grid;
      gap: 6px;
    }
    .form-row label {
      font-size: 12px;
      color: var(--header-secondary);
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .form-row input[type="text"], .form-row input:not([type]) {
      width: 100%;
      background: var(--bg-tertiary);
      border: 1px solid transparent;
      border-radius: 4px;
      padding: 8px 10px;
      color: var(--text-normal);
      transition: border-color 120ms ease;
    }
    .form-row input:focus { outline: none; border-color: var(--brand); }
    .form-row.row-h { grid-template-columns: 1fr auto; align-items: end; gap: 8px; }
    .checkbox {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      color: var(--text-normal);
      font-size: 13px;
      cursor: pointer;
      user-select: none;
    }
    .checkbox input { width: 16px; height: 16px; accent-color: var(--brand); }
    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 12px 0;
    }
    .btn {
      border: 0;
      border-radius: 3px;
      padding: 8px 14px;
      cursor: pointer;
      background: var(--brand);
      color: white;
      font-weight: 500;
      font-size: 14px;
      transition: background-color 120ms ease;
      min-height: 32px;
      min-width: 60px;
    }
    .btn:hover { background: var(--brand-hover); }
    .btn.secondary {
      background: var(--bg-accent);
      color: var(--text-normal);
    }
    .btn.secondary:hover { background: #4f5159; }
    .btn.danger { background: var(--danger); }
    .btn.danger:hover { background: #c93a3d; }
    .btn.ghost { background: transparent; color: var(--interactive-normal); }
    .btn.ghost:hover { background: var(--bg-modifier-hover); color: var(--interactive-hover); }
    .request-card {
      margin: 6px 12px;
      padding: 10px 12px;
      border-radius: 4px;
      background: var(--bg-tertiary);
      border-left: 3px solid var(--brand);
      font-family: var(--font-mono);
      font-size: 12px;
    }
    .request-card .method {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 3px;
      background: var(--brand-soft);
      color: var(--header-primary);
      font-weight: 700;
      margin-right: 6px;
    }
    .request-card .method.GET { color: #3ba55d; }
    .request-card .method.POST { color: #5865f2; }
    .request-card .method.PATCH { color: #faa61a; }
    .request-card .method.PUT { color: #faa61a; }
    .request-card .method.DELETE { color: #ed4245; }
    .request-card .body {
      margin-top: 6px;
      color: var(--text-muted);
      white-space: pre-wrap;
      word-break: break-all;
      font-size: 11px;
      max-height: 200px;
      overflow: auto;
    }
    .pill-stat {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 12px;
      color: var(--text-muted);
      font-size: 13px;
    }
    .pill-stat strong { color: var(--header-primary); }
    .toast-area {
      position: fixed;
      top: 16px;
      right: 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 100;
      max-width: 360px;
    }
    .toast {
      background: var(--bg-floating);
      color: var(--header-primary);
      padding: 12px 14px;
      border-radius: 8px;
      box-shadow: var(--elevation-medium), var(--elevation-stroke);
      border-left: 4px solid var(--brand);
      animation: slidein 200ms ease-out;
      font-size: 13px;
      word-break: break-word;
    }
    .toast.error { border-left-color: var(--danger); }
    .toast.ok { border-left-color: var(--success); }
    @keyframes slidein {
      from { opacity: 0; transform: translateX(40px); }
      to { opacity: 1; transform: translateX(0); }
    }
    .badge {
      display: inline-block;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 8px;
      background: var(--bg-tertiary);
      color: var(--interactive-normal);
      font-weight: 500;
      margin-left: 6px;
    }
    .hidden-bucket { display: none; }
    /* legacy ids kept for compatibility, hidden but addressable */
    .legacy-mount > * { display: none; }
    /* responsive collapse */
    @media (max-width: 1080px) {
      .app { grid-template-columns: var(--servers-width) var(--sidebar-width) minmax(0, 1fr); }
      .members { display: none; }
    }
    @media (max-width: 768px) {
      .app { grid-template-columns: var(--servers-width) minmax(0, 1fr); }
      .sidebar { display: none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <!-- ============== Server bar ============== -->
    <nav class="servers" aria-label="Servers">
      <div class="server-pill home" data-active="1" title="Direct Messages">
        <button type="button" aria-label="Direct Messages">V</button>
      </div>
      <div class="server-divider"></div>
      <div id="server-list"></div>
      <div class="server-pill" title="Reset state">
        <button type="button" id="server-reset" aria-label="Reset state">R</button>
      </div>
      <div class="server-pill" title="Refresh">
        <button type="button" id="server-refresh" aria-label="Refresh">&#x21bb;</button>
      </div>
    </nav>

    <!-- ============== Sidebar / channel list ============== -->
    <section class="sidebar" aria-label="Channels">
      <header class="sidebar-header">
        <span class="guild-name" id="header-guild-name">Mock Guild</span>
        <span class="chev" aria-hidden="true">&#x25BE;</span>
      </header>
      <div class="channel-scroller">
        <div class="channel-category" data-collapsed="0">
          <span class="arrow">&#x25BE;</span>
          <span>Text Channels</span>
        </div>
        <div id="channel-list"></div>
        <div class="channel-category" data-collapsed="0" style="margin-top:8px;">
          <span class="arrow">&#x25BE;</span>
          <span>Voice Channels</span>
        </div>
        <div class="channel">
          <span class="hash">&#x1F50A;</span>
          <span class="channel-name">General Voice</span>
          <span class="channel-badge">0</span>
        </div>
      </div>
      <div class="panel-user">
        <img class="avatar" id="self-avatar" alt="" src="">
        <div class="pu-info">
          <div class="pu-name" id="self-name">VaidCord Bot</div>
          <div class="pu-tag" id="self-tag">#0000</div>
        </div>
        <div class="pu-actions">
          <button class="icon-btn" title="Mute">&#x1F3A4;</button>
          <button class="icon-btn" title="Deafen">&#x1F3A7;</button>
          <button class="icon-btn" id="open-settings-btn" title="User Settings">&#x2699;</button>
        </div>
      </div>
    </section>

    <!-- ============== Main chat area ============== -->
    <main class="main">
      <header class="channel-header">
        <span class="ch-name">
          <span class="hash">#</span>
          <span id="header-channel-name">general</span>
        </span>
        <span class="divider"></span>
        <span class="topic" id="header-topic">Welcome to your VaidCord mock workspace.</span>
        <div class="header-actions">
          <button class="icon-btn" title="Pinned" aria-label="Pinned">&#x1F4CC;</button>
          <button class="icon-btn" title="Members" aria-label="Members">&#x1F465;</button>
          <button class="icon-btn" id="open-devtools-btn" title="Inspect Requests">&#x1F50D;</button>
        </div>
      </header>
      <div class="messages-pane" id="messages-pane">
        <div id="messages"></div>
      </div>
      <div class="composer-wrap">
        <div class="typing-line" id="typing-line"></div>
        <div class="composer">
          <button class="add-btn" id="composer-add" type="button" title="More options">+</button>
          <textarea
            id="composer-input"
            class="input"
            rows="1"
            placeholder="Message #general"
            aria-label="Message"
          ></textarea>
          <div class="toolbox">
            <button class="icon-btn" id="composer-typing" title="Trigger typing">&#x270D;</button>
            <button class="icon-btn" id="composer-as-bot" title="Send as bot via REST">&#x1F916;</button>
            <button class="send-btn" id="composer-send" type="button" title="Send simulated message">&#x2B9E;</button>
          </div>
        </div>
      </div>
    </main>

    <!-- ============== Right sidebar: members / devtools ============== -->
    <aside class="members" aria-label="Workspace panel">
      <div class="members-tabs">
        <button class="tab-btn" data-tab="members" data-active="1" type="button">Members</button>
        <button class="tab-btn" data-tab="profiles" type="button">Profiles</button>
        <button class="tab-btn" data-tab="requests" type="button">Requests</button>
        <button class="tab-btn" data-tab="dev" type="button">Dev</button>
      </div>
      <div class="members-scroller" data-pane="members">
        <div id="members-list"></div>
      </div>
      <div class="members-scroller hidden-bucket" data-pane="profiles">
        <div class="panel">
          <h3>Bot Identity</h3>
          <div class="form-row">
            <label for="profile-id">Profile ID</label>
            <input id="profile-id" placeholder="Leave blank to auto-create">
          </div>
          <div class="form-row">
            <label for="profile-name">Username</label>
            <input id="profile-name" placeholder="Profile username">
          </div>
          <div class="form-row">
            <label for="profile-global-name">Display Name</label>
            <input id="profile-global-name" placeholder="Optional display name">
          </div>
          <div class="form-row">
            <label for="profile-discriminator">Discriminator</label>
            <input id="profile-discriminator" value="0">
          </div>
          <label class="checkbox"><input id="profile-bot" type="checkbox"> Profile is a bot</label>
          <div class="button-row">
            <button class="btn" id="create-profile-btn" type="button">Create</button>
            <button class="btn secondary" id="save-profile-btn" type="button">Save</button>
            <button class="btn ghost" id="set-current-profile-btn" type="button">Use as Bot</button>
          </div>
          <h3>Active Bot</h3>
          <div class="form-row">
            <label for="current-user-select">Send as</label>
            <input id="current-user-select" list="profile-options" placeholder="id | username">
          </div>
        </div>
      </div>
      <div class="members-scroller hidden-bucket" data-pane="requests">
        <div class="panel">
          <h3>REST Activity</h3>
          <div id="requests"></div>
        </div>
      </div>
      <div class="members-scroller hidden-bucket" data-pane="dev">
        <div class="panel">
          <h3>Connection</h3>
          <div class="pill-stat">REST <strong id="base-url">-</strong></div>
          <div class="pill-stat">Gateway <strong id="gateway-url">-</strong></div>
          <div class="pill-stat">Active bot <strong id="current-user">-</strong></div>

          <h3>Counters</h3>
          <div class="pill-stat">Requests <strong id="request-count">0</strong></div>
          <div class="pill-stat">Messages <strong id="message-count">0</strong></div>
          <div class="pill-stat">Typing <strong id="typing-count">0</strong></div>
          <div class="pill-stat">Channels <strong id="channel-count">0</strong></div>
          <div class="pill-stat">Guilds <strong id="guild-count">0</strong></div>

          <h3>Compose Override</h3>
          <div class="form-row">
            <label for="channel-id">Channel ID</label>
            <input id="channel-id" value="123">
          </div>
          <div class="form-row">
            <label for="channel-name">Channel Name</label>
            <input id="channel-name" value="general">
          </div>
          <div class="form-row">
            <label for="channel-topic">Channel Topic</label>
            <input id="channel-topic" placeholder="Topic for channel edits">
          </div>
          <div class="form-row">
            <label for="guild-id">Guild ID</label>
            <input id="guild-id" value="999">
          </div>
          <div class="form-row">
            <label for="guild-name">Guild Name</label>
            <input id="guild-name" value="Mock Guild">
          </div>
          <div class="form-row">
            <label for="author-id">Author ID</label>
            <input id="author-id" value="2">
          </div>
          <div class="form-row">
            <label for="author-name">Author Name</label>
            <input id="author-name" value="MockUser">
          </div>
          <label class="checkbox"><input id="author-bot" type="checkbox"> Author is bot</label>
          <div class="button-row">
            <button class="btn secondary" id="save-channel-btn" type="button">Save Channel</button>
          </div>

          <h3>Edit/Delete Selected</h3>
          <div class="form-row">
            <label for="message-id">Message ID</label>
            <input id="message-id" placeholder="Click a message to select">
          </div>
          <div class="form-row">
            <label for="message-edit-content">New content</label>
            <input id="message-edit-content" placeholder="Edited content">
          </div>
          <div class="button-row">
            <button class="btn secondary" id="edit-message-btn" type="button">Edit</button>
            <button class="btn danger" id="delete-message-btn" type="button">Delete</button>
          </div>

          <h3>Hidden actions</h3>
          <div class="button-row legacy-mount">
            <!-- legacy buttons kept for tests -->
            <button id="send-btn" type="button">legacy-send</button>
            <button id="send-bot-btn" type="button">legacy-send-bot</button>
            <button id="typing-btn" type="button">legacy-typing</button>
            <button id="refresh-btn" type="button">legacy-refresh</button>
            <button id="reset-btn" type="button">legacy-reset</button>
          </div>
          <div class="button-row">
            <button class="btn ghost" id="reset-state-btn" type="button">Reset Mock State</button>
          </div>
        </div>
      </div>
    </aside>
  </div>

  <div class="toast-area" id="toast-area"></div>
  <datalist id="profile-options"></datalist>
  <!-- legacy ids preserved (hidden) for backward compatibility -->
  <div class="legacy-mount" aria-hidden="true">
    <div id="ui-notice" role="status"></div>
    <div id="users"></div>
    <div id="channels"></div>
    <div id="guilds"></div>
    <div id="typing"></div>
    <input id="content">
  </div>

  <script>
    // ---- DOM handles ----
    const d = (id) => document.getElementById(id);
    const messagesEl = d("messages");
    const messagesPaneEl = d("messages-pane");
    const requestsEl = d("requests");
    const usersEl = d("users");
    const channelsEl = d("channels");
    const guildsEl = d("guilds");
    const typingEl = d("typing");
    const baseUrlEl = d("base-url");
    const gatewayUrlEl = d("gateway-url");
    const currentUserEl = d("current-user");
    const requestCountEl = d("request-count");
    const messageCountEl = d("message-count");
    const typingCountEl = d("typing-count");
    const channelCountEl = d("channel-count");
    const guildCountEl = d("guild-count");
    const profileOptionsEl = d("profile-options");
    const toastArea = d("toast-area");
    const composerInput = d("composer-input");
    const composerTextProxy = d("content");
    const channelListEl = d("channel-list");
    const serverListEl = d("server-list");
    const membersListEl = d("members-list");
    const headerChannelName = d("header-channel-name");
    const headerGuildName = d("header-guild-name");
    const headerTopic = d("header-topic");
    const typingLineEl = d("typing-line");
    const selfNameEl = d("self-name");
    const selfTagEl = d("self-tag");
    const selfAvatarEl = d("self-avatar");

    // ---- helpers ----
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }[c]));
    }
    function showNotice(message, isError = true) {
      // legacy support: keep #ui-notice text in sync
      d("ui-notice").textContent = message || "";
      if (!message) return;
      const t = document.createElement("div");
      t.className = "toast " + (isError ? "error" : "ok");
      t.textContent = message;
      toastArea.appendChild(t);
      setTimeout(() => { t.style.opacity = "0"; t.style.transform = "translateX(40px)"; }, 4000);
      setTimeout(() => t.remove(), 4500);
    }
    async function apiFetch(url, options = {}) {
      const response = await fetch(url, options);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`${options.method || "GET"} ${url} failed with ${response.status}: ${text || response.statusText}`);
      }
      return response;
    }
    function formatProfileValue(user) {
      return `${user.id} | ${user.username}`;
    }
    function parseSelectedProfileId() {
      return (d("current-user-select").value || "").split("|")[0].trim();
    }
    function fillProfileForm(user) {
      d("profile-id").value = user.id || "";
      d("profile-name").value = user.username || "";
      d("profile-global-name").value = user.global_name || "";
      d("profile-discriminator").value = user.discriminator || "0";
      d("profile-bot").checked = Boolean(user.bot);
      d("author-id").value = user.id || "";
      d("author-name").value = user.username || "";
      d("author-bot").checked = Boolean(user.bot);
    }
    function avatarUrl(user) {
      const seed = encodeURIComponent(user.id || user.username || "x");
      // local stable colorful avatar - no external network required
      const palette = ["5865f2", "3ba55d", "faa61a", "ed4245", "eb459e", "00a8fc", "9b6dff"];
      const idx = (Number(user.id) || (user.username || "x").length) % palette.length;
      const color = palette[idx];
      const initial = (user.global_name || user.username || "?").charAt(0).toUpperCase();
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'>` +
        `<rect width='40' height='40' rx='20' fill='%23${color}'/>` +
        `<text x='50%' y='52%' dominant-baseline='middle' text-anchor='middle' ` +
        `fill='white' font-family='gg sans, Helvetica, Arial' font-size='18' font-weight='600'>` +
        `${escapeHtml(initial)}</text></svg>`;
      return `data:image/svg+xml;utf8,${svg.replace(/#/g, "%23")}`;
    }
    function formatTime(ts) {
      if (!ts) return "";
      try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        const today = new Date();
        const sameDay = d.toDateString() === today.toDateString();
        const opts = { hour: "numeric", minute: "2-digit" };
        if (sameDay) return `Today at ${d.toLocaleTimeString([], opts)}`;
        const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
        if (d.toDateString() === yesterday.toDateString()) {
          return `Yesterday at ${d.toLocaleTimeString([], opts)}`;
        }
        return d.toLocaleDateString() + " " + d.toLocaleTimeString([], opts);
      } catch { return ts; }
    }
    function formatTimeShort(ts) {
      if (!ts) return "";
      try {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      } catch { return ""; }
    }

    // ---- selection state ----
    const selection = {
      channelId: "123",
      messageId: "",
    };

    function syncChannelSelection(state) {
      const cid = d("channel-id").value || selection.channelId || "123";
      selection.channelId = cid;
      const channel = state.channels.find((c) => String(c.id) === String(cid));
      const channelName = channel ? channel.name : (d("channel-name").value || "general");
      headerChannelName.textContent = channelName || "channel";
      headerTopic.textContent = (channel && channel.topic) || "Welcome to your VaidCord mock workspace.";
      composerInput.placeholder = `Message #${channelName || "general"}`;
      const guild = state.guilds.find((g) => channel && String(g.id) === String(channel.guild_id))
        || state.guilds[0]
        || { id: d("guild-id").value, name: d("guild-name").value };
      headerGuildName.textContent = guild.name || "Direct Messages";
    }

    // ---- renderers ----
    function renderServers(state) {
      const guilds = state.guilds || [];
      serverListEl.innerHTML = guilds.map((g) => {
        const initial = (g.name || "?").trim().charAt(0).toUpperCase();
        return `<div class="server-pill" data-guild-id="${escapeHtml(g.id)}" title="${escapeHtml(g.name)}">
          <button type="button" aria-label="${escapeHtml(g.name)}">${escapeHtml(initial)}</button>
        </div>`;
      }).join("");
      serverListEl.querySelectorAll(".server-pill").forEach((node) => {
        node.addEventListener("click", () => {
          const gid = node.getAttribute("data-guild-id") || "";
          d("guild-id").value = gid;
          // pick first channel of this guild
          const ch = (state.channels || []).find((c) => String(c.guild_id) === String(gid));
          if (ch) {
            d("channel-id").value = ch.id;
            d("channel-name").value = ch.name || "";
            d("channel-topic").value = ch.topic || "";
          }
          syncChannelSelection(state);
          renderChannels(state);
          renderMessages(state);
          renderMembers(state);
        });
      });
    }

    function renderChannels(state) {
      const gid = d("guild-id").value;
      const channels = (state.channels || []).filter((c) => !gid || String(c.guild_id) === String(gid) || !c.guild_id);
      channelListEl.innerHTML = channels.map((c) => {
        const isActive = String(c.id) === String(selection.channelId);
        return `
          <div class="channel" data-channel-id="${escapeHtml(c.id)}" data-active="${isActive ? 1 : 0}"
               data-channel-name="${escapeHtml(c.name || "")}"
               data-channel-topic="${escapeHtml(c.topic || "")}"
               data-guild-id="${escapeHtml(c.guild_id || "")}">
            <span class="hash">#</span>
            <span class="channel-name">${escapeHtml(c.name || "channel")}</span>
            ${c.guild_id ? "" : '<span class="channel-badge">DM</span>'}
          </div>
        `;
      }).join("") || `<div class="channel" style="opacity:.6;cursor:default;"><span class="hash">#</span><span class="channel-name">no channels</span></div>`;

      // legacy mirror
      channelsEl.innerHTML = channels.map((c) => `<div data-channel-id="${escapeHtml(c.id)}"></div>`).join("");

      channelListEl.querySelectorAll(".channel").forEach((node) => {
        node.addEventListener("click", () => {
          const cid = node.getAttribute("data-channel-id") || "";
          d("channel-id").value = cid;
          d("channel-name").value = node.getAttribute("data-channel-name") || "";
          d("channel-topic").value = node.getAttribute("data-channel-topic") || "";
          const gid = node.getAttribute("data-guild-id");
          if (gid) d("guild-id").value = gid;
          selection.channelId = cid;
          syncChannelSelection(state);
          renderChannels(state);
          renderMessages(state);
        });
      });
    }

    function renderMessages(state) {
      const cid = selection.channelId;
      const all = (state.messages || []).filter((m) => String(m.channel_id) === String(cid));
      if (!all.length) {
        messagesEl.innerHTML = `
          <div class="empty-state">
            <div class="big">#</div>
            <h3 style="margin:0;color:var(--header-primary);">Welcome to #${escapeHtml(headerChannelName.textContent)}!</h3>
            <div>This is the start of the #${escapeHtml(headerChannelName.textContent)} channel.</div>
            <div style="font-size:12px;">Use the composer below to simulate inbound traffic, or POST to /api/v10 to act as the bot.</div>
          </div>
        `;
        return;
      }
      const isContinuation = (prev, cur) => {
        if (!prev) return false;
        if (prev.author.id !== cur.author.id) return false;
        if (!prev.timestamp || !cur.timestamp) return false;
        const dp = new Date(prev.timestamp).getTime();
        const dc = new Date(cur.timestamp).getTime();
        return Math.abs(dc - dp) < 7 * 60 * 1000;
      };
      let html = "";
      let prev = null;
      let lastDay = "";
      for (const m of all) {
        // day separator
        const day = (m.timestamp || "").slice(0, 10);
        if (day && day !== lastDay) {
          html += `<div class="system-line"><span class="rule"></span><span>${escapeHtml(formatTime(m.timestamp).split(" at ")[0])}</span><span class="rule"></span></div>`;
          lastDay = day;
        }
        const cont = isContinuation(prev, m);
        const cls = "message" + (cont ? "" : " start");
        const author = m.author || {};
        if (cont) {
          html += `
            <div class="${cls}" data-message-id="${escapeHtml(m.id)}"
                 data-message-content="${escapeHtml(m.content || "")}"
                 data-channel-id="${escapeHtml(m.channel_id)}">
              <span class="timestamp-gutter">${escapeHtml(formatTimeShort(m.timestamp))}</span>
              <div class="body">${escapeHtml(m.content || "")}${m.edited_timestamp ? `<span class="edited">(edited)</span>` : ""}</div>
            </div>
          `;
        } else {
          html += `
            <div class="${cls}" data-message-id="${escapeHtml(m.id)}"
                 data-message-content="${escapeHtml(m.content || "")}"
                 data-channel-id="${escapeHtml(m.channel_id)}">
              <img class="avatar" src="${avatarUrl(author)}" alt="">
              <div class="header-line">
                <span class="author ${author.bot ? 'bot-author' : ''}">${escapeHtml(author.global_name || author.username || "user")}</span>
                ${author.bot ? '<span class="bot-tag">Bot</span>' : ""}
                <span class="timestamp">${escapeHtml(formatTime(m.timestamp))}</span>
              </div>
              <div class="body">${escapeHtml(m.content || "")}${m.edited_timestamp ? `<span class="edited">(edited)</span>` : ""}</div>
              <div class="meta-line">id=${escapeHtml(m.id)}${m.guild_id ? ` &middot; guild=${escapeHtml(m.guild_id)}` : ""}</div>
            </div>
          `;
        }
        prev = m;
      }
      messagesEl.innerHTML = html;
      messagesEl.querySelectorAll(".message").forEach((node) => {
        node.addEventListener("click", () => {
          d("message-id").value = node.getAttribute("data-message-id") || "";
          d("message-edit-content").value = node.getAttribute("data-message-content") || "";
          d("channel-id").value = node.getAttribute("data-channel-id") || "123";
          selection.messageId = d("message-id").value;
        });
      });
    }

    function renderMembers(state) {
      const users = state.users || [];
      const bots = users.filter((u) => u.bot);
      const humans = users.filter((u) => !u.bot);
      const renderGroup = (label, arr) => {
        if (!arr.length) return "";
        return `<div class="group-label">${escapeHtml(label)} — ${arr.length}</div>` +
          arr.map((u) => `
            <div class="member" data-user-id="${escapeHtml(u.id)}"
                 data-user-name="${escapeHtml(u.username || "")}"
                 data-user-global-name="${escapeHtml(u.global_name || "")}"
                 data-user-discriminator="${escapeHtml(u.discriminator || "0")}"
                 data-user-bot="${u.bot ? "1" : "0"}">
              <div class="avatar-wrap">
                <img class="avatar" src="${avatarUrl(u)}" alt="">
                <span class="status-dot${u.bot ? " bot" : ""}"></span>
              </div>
              <span class="name">${escapeHtml(u.global_name || u.username || "user")}</span>
              ${u.bot ? '<span class="role">Bot</span>' : ""}
            </div>
          `).join("");
      };
      membersListEl.innerHTML = renderGroup("Online", humans) + renderGroup("Bots", bots) ||
        `<div class="group-label" style="opacity:.6;">No members yet</div>`;
      // legacy mirror
      usersEl.innerHTML = users.map((u) => `<div data-user-id="${escapeHtml(u.id)}"></div>`).join("");

      membersListEl.querySelectorAll(".member").forEach((node) => {
        node.addEventListener("click", () => {
          fillProfileForm({
            id: node.getAttribute("data-user-id") || "",
            username: node.getAttribute("data-user-name") || "",
            global_name: node.getAttribute("data-user-global-name") || "",
            discriminator: node.getAttribute("data-user-discriminator") || "0",
            bot: node.getAttribute("data-user-bot") === "1",
          });
          activateTab("profiles");
        });
      });
    }

    function renderRequests(state) {
      const requests = [...(state.requests || [])].reverse();
      requestsEl.innerHTML = requests.map((r) => {
        const method = (r.method || "GET").toUpperCase();
        return `
          <div class="request-card">
            <span class="method ${escapeHtml(method)}">${escapeHtml(method)}</span>
            <span>${escapeHtml(r.path)}</span>
            <div class="body">${escapeHtml(JSON.stringify(r.json || {}, null, 2))}</div>
          </div>
        `;
      }).join("") || `<div class="pill-stat" style="opacity:.6;">No requests yet</div>`;
    }

    function renderTyping(state) {
      const typing = [...(state.typing_events || [])].reverse();
      // legacy mirror
      typingEl.innerHTML = typing.map((t) => `<div data-typing-id="${escapeHtml(t.user_id)}"></div>`).join("");
      const cid = selection.channelId;
      const recent = typing.filter((t) => String(t.channel_id) === String(cid)).slice(0, 3);
      if (!recent.length) {
        typingLineEl.innerHTML = "";
        return;
      }
      const names = recent.map((t) => `<strong style="color:var(--header-primary);">${escapeHtml(t.username)}</strong>`).join(", ");
      typingLineEl.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span>${names} ${recent.length === 1 ? "is" : "are"} typing…`;
    }

    function renderGuildsLegacy(state) {
      guildsEl.innerHTML = (state.guilds || []).map((g) => `<div data-guild-id="${escapeHtml(g.id)}"></div>`).join("");
    }

    async function refresh() {
      const response = await apiFetch("/api/mock/state");
      const state = await response.json();

      baseUrlEl.textContent = state.base_url;
      gatewayUrlEl.textContent = state.gateway_url;
      const cu = state.current_user;
      currentUserEl.textContent = `${cu.username} (${cu.id})`;
      d("current-user-select").value = formatProfileValue(cu);
      profileOptionsEl.innerHTML = (state.users || []).map((u) =>
        `<option value="${escapeHtml(formatProfileValue(u))}"></option>`
      ).join("");

      requestCountEl.textContent = (state.requests || []).length;
      messageCountEl.textContent = (state.messages || []).length;
      typingCountEl.textContent = (state.typing_events || []).length;
      channelCountEl.textContent = (state.channels || []).length;
      guildCountEl.textContent = (state.guilds || []).length;

      selfNameEl.textContent = cu.global_name || cu.username || "VaidCord Bot";
      selfTagEl.textContent = `#${cu.discriminator || "0"}`;
      selfAvatarEl.src = avatarUrl(cu);

      if (!selection.channelId) selection.channelId = d("channel-id").value || "123";
      syncChannelSelection(state);
      renderServers(state);
      renderChannels(state);
      renderMessages(state);
      renderMembers(state);
      renderRequests(state);
      renderTyping(state);
      renderGuildsLegacy(state);
    }

    // ---- actions ----
    function readContent() {
      // Composer is the source of truth; legacy #content kept in sync for tests.
      const v = composerInput.value;
      composerTextProxy.value = v;
      return v;
    }
    async function simulateMessage() {
      await apiFetch("/api/mock/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          channel_id: d("channel-id").value || "123",
          channel_name: d("channel-name").value || "general",
          guild_id: d("guild-id").value || "999",
          guild_name: d("guild-name").value || "Mock Guild",
          author_id: d("author-id").value || "2",
          author_username: d("author-name").value || "MockUser",
          author_bot: d("author-bot").checked,
          content: readContent()
        })
      });
      composerInput.value = "";
      autosizeComposer();
      await refresh();
    }
    async function sendBotMessage() {
      const channelId = d("channel-id").value || "123";
      await apiFetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ content: readContent() })
      });
      composerInput.value = "";
      autosizeComposer();
      await refresh();
    }
    async function triggerTyping() {
      const channelId = d("channel-id").value || "123";
      await apiFetch(`/api/v10/channels/${encodeURIComponent(channelId)}/typing`, { method: "POST" });
      await refresh();
    }
    async function saveChannel() {
      const channelId = d("channel-id").value || "123";
      await apiFetch(`/api/v10/channels/${encodeURIComponent(channelId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: d("channel-name").value,
          topic: d("channel-topic").value
        })
      });
      await refresh();
    }
    async function editMessage() {
      const channelId = d("channel-id").value || "123";
      const messageId = d("message-id").value;
      if (!messageId) return;
      await apiFetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ content: d("message-edit-content").value })
      });
      await refresh();
    }
    async function deleteMessage() {
      const channelId = d("channel-id").value || "123";
      const messageId = d("message-id").value;
      if (!messageId) return;
      await apiFetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`, {
        method: "DELETE"
      });
      d("message-id").value = "";
      d("message-edit-content").value = "";
      await refresh();
    }
    async function resetState() {
      await apiFetch("/api/mock/reset", {method: "POST"});
      d("message-id").value = "";
      d("message-edit-content").value = "";
      composerInput.value = "";
      await refresh();
    }
    async function createProfile() {
      const response = await apiFetch("/api/mock/profiles", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          id: d("profile-id").value || undefined,
          username: d("profile-name").value || "Profile",
          global_name: d("profile-global-name").value || null,
          discriminator: d("profile-discriminator").value || "0",
          bot: d("profile-bot").checked
        })
      });
      const profile = await response.json();
      fillProfileForm(profile);
      await refresh();
    }
    async function saveProfile() {
      const profileId = d("profile-id").value;
      if (!profileId) return;
      const response = await apiFetch(`/api/mock/profiles/${encodeURIComponent(profileId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          username: d("profile-name").value || "Profile",
          global_name: d("profile-global-name").value || null,
          discriminator: d("profile-discriminator").value || "0",
          bot: d("profile-bot").checked
        })
      });
      const profile = await response.json();
      fillProfileForm(profile);
      await refresh();
    }
    async function setCurrentProfile() {
      const profileId = d("profile-id").value || parseSelectedProfileId();
      if (!profileId) return;
      await apiFetch("/api/mock/current-user", {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user_id: profileId})
      });
      await refresh();
    }

    // ---- composer UX ----
    function autosizeComposer() {
      composerInput.style.height = "auto";
      composerInput.style.height = Math.min(composerInput.scrollHeight, 200) + "px";
    }
    composerInput.addEventListener("input", autosizeComposer);
    composerInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const wantBot = e.ctrlKey || e.metaKey;
        guard(wantBot ? sendBotMessage : simulateMessage)();
      }
    });

    // ---- tab switching ----
    function activateTab(name) {
      document.querySelectorAll(".tab-btn").forEach((b) => {
        b.dataset.active = b.dataset.tab === name ? "1" : "0";
      });
      document.querySelectorAll(".members-scroller").forEach((p) => {
        if (p.dataset.pane === name) {
          p.classList.remove("hidden-bucket");
        } else {
          p.classList.add("hidden-bucket");
        }
      });
    }
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.addEventListener("click", () => activateTab(b.dataset.tab));
    });

    // ---- event wiring ----
    function guard(fn) {
      return async () => {
        try { await fn(); }
        catch (err) { showNotice(err.message || String(err)); console.error(err); }
      };
    }
    function bind(id, fn) {
      const el = d(id);
      if (el) el.addEventListener("click", guard(fn));
    }
    // primary composer triggers
    bind("composer-send", simulateMessage);
    bind("composer-as-bot", sendBotMessage);
    bind("composer-typing", triggerTyping);
    // header / server bar
    bind("server-refresh", refresh);
    bind("server-reset", resetState);
    // legacy buttons preserved
    bind("send-btn", simulateMessage);
    bind("send-bot-btn", sendBotMessage);
    bind("typing-btn", triggerTyping);
    bind("refresh-btn", refresh);
    bind("reset-btn", resetState);
    // dev panel
    bind("save-channel-btn", saveChannel);
    bind("edit-message-btn", editMessage);
    bind("delete-message-btn", deleteMessage);
    bind("reset-state-btn", resetState);
    bind("create-profile-btn", createProfile);
    bind("save-profile-btn", saveProfile);
    bind("set-current-profile-btn", setCurrentProfile);
    bind("open-devtools-btn", () => activateTab("requests"));
    bind("open-settings-btn", () => activateTab("profiles"));

    d("current-user-select").addEventListener("change", guard(setCurrentProfile));

    // initial render + polling
    refresh().catch((e) => showNotice(e.message || String(e)));
    setInterval(() => refresh().catch((e) => showNotice(e.message || String(e))), 1800);
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
    )
    for element_id in required_ids:
        if f'id="{element_id}"' not in MOCK_UI_HTML:
            raise ValueError(f"Mock UI is missing required element id={element_id!r}")
