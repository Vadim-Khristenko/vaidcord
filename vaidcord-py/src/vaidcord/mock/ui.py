"""Static UI for the local Discord mock server."""


MOCK_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VaidCord Mock Server</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050505;
      --panel: #101114;
      --panel-soft: #17191f;
      --line: #252834;
      --text: #f4f6fb;
      --muted: #9ba3b4;
      --accent: #5865f2;
      --green: #23a55a;
      --danger: #ed4245;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .shell {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      border-right: 1px solid var(--line);
      background: #090a0d;
      padding: 20px;
    }
    main {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      min-width: 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      letter-spacing: 0;
    }
    .mark {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: var(--accent);
      color: white;
      font-weight: 800;
    }
    .status {
      margin-top: 24px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 4px 10px;
      background: rgba(35, 165, 90, .16);
      color: #8df0b7;
      font-size: 12px;
      font-weight: 700;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--green);
    }
    .meta {
      margin-top: 14px;
      color: var(--muted);
      display: grid;
      gap: 8px;
      word-break: break-word;
    }
    header {
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .sub {
      color: var(--muted);
      margin-top: 3px;
      font-size: 13px;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      min-height: 0;
    }
    .messages, .requests {
      padding: 20px 24px;
      overflow: auto;
    }
    .requests {
      border-left: 1px solid var(--line);
      background: #08090b;
    }
    .message, .request {
      background: var(--panel-soft);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 10px;
    }
    .message strong, .request strong { color: white; }
    .body { margin-top: 6px; color: #dfe3ee; white-space: pre-wrap; }
    .small { color: var(--muted); font-size: 12px; }
    form {
      display: grid;
      grid-template-columns: minmax(120px, 180px) minmax(0, 1fr) auto;
      gap: 10px;
      padding: 16px 24px;
      border-top: 1px solid var(--line);
      background: var(--panel);
    }
    input, button {
      height: 40px;
      border-radius: 8px;
      border: 1px solid var(--line);
      font: inherit;
    }
    input {
      background: #06070a;
      color: var(--text);
      padding: 0 12px;
      min-width: 0;
    }
    button {
      background: var(--accent);
      color: white;
      border-color: transparent;
      padding: 0 18px;
      font-weight: 700;
      cursor: pointer;
    }
    @media (max-width: 860px) {
      .shell, .workspace { grid-template-columns: 1fr; }
      aside, .requests { border-right: 0; border-left: 0; border-bottom: 1px solid var(--line); }
      form { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><div class="mark">V</div><div>VaidCord Mock Server</div></div>
      <div class="status">
        <span class="pill"><span class="dot"></span> Online</span>
        <div class="meta">
          <div>REST base: <span id="base-url">-</span></div>
          <div>Gateway: <span id="gateway-url">-</span></div>
          <div>Requests: <span id="request-count">0</span></div>
        </div>
      </div>
    </aside>
    <main>
      <header>
        <div>
          <h1>Mock Discord Workspace</h1>
          <div class="sub">Send test messages and inspect bot API calls locally.</div>
        </div>
      </header>
      <section class="workspace">
        <div class="messages" id="messages"></div>
        <div class="requests" id="requests"></div>
      </section>
      <form id="send-form">
        <input id="channel-id" value="123" aria-label="Channel ID">
        <input id="content" placeholder="Message content" aria-label="Message content">
        <button type="submit">Send</button>
      </form>
    </main>
  </div>
  <script>
    const messages = document.getElementById("messages");
    const requests = document.getElementById("requests");
    const baseUrl = document.getElementById("base-url");
    const gatewayUrl = document.getElementById("gateway-url");
    const requestCount = document.getElementById("request-count");

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"
      }[char]));
    }

    async function refresh() {
      const response = await fetch("/api/mock/state");
      const state = await response.json();
      baseUrl.textContent = state.base_url;
      gatewayUrl.textContent = state.gateway_url;
      requestCount.textContent = state.requests.length;
      messages.innerHTML = state.messages.map((message) => `
        <article class="message">
          <strong>${escapeHtml(message.author.username)}</strong>
          <span class="small">#${escapeHtml(message.channel_id)} - ${escapeHtml(message.id)}</span>
          <div class="body">${escapeHtml(message.content)}</div>
        </article>
      `).join("") || '<div class="small">No messages yet.</div>';
      requests.innerHTML = state.requests.slice().reverse().map((request) => `
        <article class="request">
          <strong>${escapeHtml(request.method)}</strong>
          <span class="small">${escapeHtml(request.path)}</span>
          <div class="body">${escapeHtml(JSON.stringify(request.json || {}, null, 2))}</div>
        </article>
      `).join("") || '<div class="small">No API calls yet.</div>';
    }

    document.getElementById("send-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const channelId = document.getElementById("channel-id").value || "123";
      const content = document.getElementById("content").value;
      await fetch("/api/mock/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({channel_id: channelId, content})
      });
      document.getElementById("content").value = "";
      await refresh();
    });

    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""
