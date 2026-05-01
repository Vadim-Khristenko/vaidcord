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
      --bg: #0b1020;
      --bg-soft: #131a2e;
      --panel: #111827;
      --panel-2: #0f172a;
      --line: #26314f;
      --text: #edf2ff;
      --muted: #9fb0d2;
      --accent: #4f7cff;
      --accent-soft: rgba(79, 124, 255, 0.14);
      --green: #1fa971;
      --green-soft: rgba(31, 169, 113, 0.16);
      --red: #d95c5c;
      --yellow: #f0b429;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top right, rgba(79, 124, 255, 0.18), transparent 28%),
        linear-gradient(180deg, #0b1020 0%, #090d19 100%);
      color: var(--text);
      font: 14px/1.45 "Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif;
    }
    .shell {
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      padding: 20px;
      border-right: 1px solid var(--line);
      background: rgba(9, 14, 28, 0.94);
      backdrop-filter: blur(12px);
    }
    main {
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      min-width: 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 15px;
    }
    .mark {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, #4f7cff, #6e58ff);
      color: white;
      font-weight: 800;
    }
    .status-card, .quick-card {
      margin-top: 18px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(17, 24, 39, 0.86);
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 4px 10px;
      background: var(--green-soft);
      color: #8ef0c1;
      font-size: 12px;
      font-weight: 700;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--green);
    }
    .meta, .quick-stats {
      margin-top: 12px;
      display: grid;
      gap: 8px;
      color: var(--muted);
      word-break: break-word;
      font-size: 13px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(15, 23, 42, 0.82);
      backdrop-filter: blur(10px);
    }
    h1 {
      margin: 0;
      font-size: 20px;
    }
    .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
    }
    button {
      border: 1px solid transparent;
      border-radius: 10px;
      font: inherit;
      cursor: pointer;
      color: white;
      background: var(--accent);
      padding: 10px 14px;
      font-weight: 700;
    }
    button.secondary {
      background: transparent;
      border-color: var(--line);
      color: var(--text);
    }
    .composer {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(13, 18, 33, 0.78);
    }
    .field {
      display: grid;
      gap: 6px;
      min-width: 0;
    }
    .field.wide {
      grid-column: span 2;
    }
    .field.full {
      grid-column: 1 / -1;
    }
    .field label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 11px 12px;
      min-width: 0;
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }
    .actions {
      display: flex;
      gap: 10px;
      align-items: end;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.9fr) minmax(320px, 1fr);
      min-height: 0;
    }
    .column {
      min-width: 0;
      border-right: 1px solid var(--line);
      overflow: auto;
    }
    .column:last-child { border-right: 0; }
    .section {
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
    }
    .section h2 {
      margin: 0 0 12px;
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
    }
    .stack {
      display: grid;
      gap: 10px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(17, 24, 39, 0.82);
      padding: 12px;
    }
    .card strong {
      color: white;
    }
    .small {
      color: var(--muted);
      font-size: 12px;
    }
    .body {
      margin-top: 6px;
      color: #dfe8ff;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 700;
      margin-left: 8px;
      background: var(--accent-soft);
      color: #b7c7ff;
    }
    .warn {
      color: var(--yellow);
    }
    @media (max-width: 1180px) {
      .shell { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .composer { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .workspace { grid-template-columns: 1fr; }
      .column { border-right: 0; border-bottom: 1px solid var(--line); }
    }
    @media (max-width: 700px) {
      header { display: grid; }
      .composer { grid-template-columns: 1fr; }
      .field.wide, .field.full { grid-column: auto; }
      .actions { align-items: stretch; }
      .actions button { flex: 1; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><div class="mark">V</div><div>VaidCord Mock Server</div></div>
      <div class="status-card">
        <span class="pill"><span class="dot"></span> Local Gateway Ready</span>
        <div class="meta">
          <div>REST base: <span id="base-url">-</span></div>
          <div>Gateway: <span id="gateway-url">-</span></div>
          <div>Active bot: <span id="current-user">-</span></div>
        </div>
      </div>
      <div class="quick-card">
        <div class="small">Quick Stats</div>
        <div class="quick-stats">
          <div>Requests: <span id="request-count">0</span></div>
          <div>Messages: <span id="message-count">0</span></div>
          <div>Typing: <span id="typing-count">0</span></div>
          <div>Channels: <span id="channel-count">0</span></div>
          <div>Guilds: <span id="guild-count">0</span></div>
        </div>
      </div>
      <div class="quick-card">
        <div class="small">Bot Profile</div>
        <div class="field" style="margin-top: 10px;">
          <label for="current-user-select">Send as</label>
          <input id="current-user-select" list="profile-options" aria-label="Active bot profile">
        </div>
      </div>
    </aside>
    <main>
      <header>
        <div>
          <h1>Mock Discord Workspace</h1>
          <div class="sub">Simulate inbound traffic, inspect REST calls, and keep bot testing close to real Discord flows.</div>
        </div>
        <div class="toolbar">
          <button class="secondary" id="refresh-btn" type="button">Refresh</button>
          <button class="secondary" id="reset-btn" type="button">Reset State</button>
        </div>
      </header>
      <section class="composer">
        <div class="field">
          <label for="channel-id">Channel ID</label>
          <input id="channel-id" value="123" aria-label="Channel ID">
        </div>
        <div class="field">
          <label for="channel-name">Channel Name</label>
          <input id="channel-name" value="general" aria-label="Channel Name">
        </div>
        <div class="field">
          <label for="guild-id">Guild ID</label>
          <input id="guild-id" value="999" aria-label="Guild ID">
        </div>
        <div class="field">
          <label for="guild-name">Guild Name</label>
          <input id="guild-name" value="Mock Guild" aria-label="Guild Name">
        </div>
        <div class="field">
          <label for="author-id">Author ID</label>
          <input id="author-id" value="2" aria-label="Author ID">
        </div>
        <div class="field">
          <label for="author-name">Author Name</label>
          <input id="author-name" value="MockUser" aria-label="Author Name">
        </div>
        <div class="field">
          <label for="author-bot">Author Is Bot</label>
          <input id="author-bot" type="checkbox" aria-label="Author Is Bot">
        </div>
        <div class="field full">
          <label for="content">Simulated inbound message</label>
          <input id="content" placeholder="Type the message content the bot should receive" aria-label="Message content">
        </div>
        <div class="field full actions">
          <button id="send-btn" type="button">Simulate Message</button>
          <button id="send-bot-btn" class="secondary" type="button">Send Bot Message</button>
          <button id="typing-btn" class="secondary" type="button">Trigger Typing</button>
        </div>
        <div class="field">
          <label for="channel-topic">Channel Topic</label>
          <input id="channel-topic" placeholder="Optional topic for channel edits" aria-label="Channel Topic">
        </div>
        <div class="field full actions">
          <button id="save-channel-btn" class="secondary" type="button">Save Channel</button>
        </div>
        <div class="field">
          <label for="message-id">Message ID</label>
          <input id="message-id" placeholder="Select a message card or enter an id" aria-label="Message ID">
        </div>
        <div class="field wide">
          <label for="message-edit-content">Edited Message Content</label>
          <input id="message-edit-content" placeholder="Edit the selected message" aria-label="Edited Message Content">
        </div>
        <div class="field full actions">
          <button id="edit-message-btn" class="secondary" type="button">Edit Message</button>
          <button id="delete-message-btn" class="secondary" type="button">Delete Message</button>
        </div>
        <div class="field">
          <label for="profile-id">Profile ID</label>
          <input id="profile-id" placeholder="Leave blank to auto-create" aria-label="Profile ID">
        </div>
        <div class="field">
          <label for="profile-name">Profile Name</label>
          <input id="profile-name" placeholder="Profile username" aria-label="Profile Name">
        </div>
        <div class="field">
          <label for="profile-global-name">Display Name</label>
          <input id="profile-global-name" placeholder="Optional display name" aria-label="Display Name">
        </div>
        <div class="field">
          <label for="profile-discriminator">Discriminator</label>
          <input id="profile-discriminator" value="0" aria-label="Discriminator">
        </div>
        <div class="field">
          <label for="profile-bot">Profile Is Bot</label>
          <input id="profile-bot" type="checkbox" aria-label="Profile Is Bot">
        </div>
        <div class="field full actions">
          <button id="create-profile-btn" class="secondary" type="button">Create Profile</button>
          <button id="save-profile-btn" class="secondary" type="button">Save Profile</button>
          <button id="set-current-profile-btn" class="secondary" type="button">Use As Bot</button>
        </div>
      </section>
      <section class="workspace">
        <div class="column">
          <div class="section">
            <h2>Messages</h2>
            <div class="stack" id="messages"></div>
          </div>
          <div class="section">
            <h2>Typing Events</h2>
            <div class="stack" id="typing"></div>
          </div>
        </div>
        <div class="column">
          <div class="section">
            <h2>Users</h2>
            <div class="stack" id="users"></div>
          </div>
          <div class="section">
            <h2>Channels</h2>
            <div class="stack" id="channels"></div>
          </div>
          <div class="section">
            <h2>Guilds</h2>
            <div class="stack" id="guilds"></div>
          </div>
        </div>
        <div class="column">
          <div class="section">
            <h2>REST Requests</h2>
            <div class="stack" id="requests"></div>
          </div>
        </div>
      </section>
    </main>
  </div>
  <datalist id="profile-options"></datalist>
  <script>
    const messages = document.getElementById("messages");
    const requests = document.getElementById("requests");
    const users = document.getElementById("users");
    const channels = document.getElementById("channels");
    const guilds = document.getElementById("guilds");
    const typing = document.getElementById("typing");
    const baseUrl = document.getElementById("base-url");
    const gatewayUrl = document.getElementById("gateway-url");
    const currentUser = document.getElementById("current-user");
    const requestCount = document.getElementById("request-count");
    const messageCount = document.getElementById("message-count");
    const typingCount = document.getElementById("typing-count");
    const channelCount = document.getElementById("channel-count");
    const guildCount = document.getElementById("guild-count");
    const currentUserSelect = document.getElementById("current-user-select");
    const profileOptions = document.getElementById("profile-options");

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"
      }[char]));
    }

    function formatProfileValue(user) {
      return `${user.id} | ${user.username}`;
    }

    function parseSelectedProfileId() {
      const raw = currentUserSelect.value || "";
      return raw.split("|")[0].trim();
    }

    function fillProfileForm(user) {
      document.getElementById("profile-id").value = user.id || "";
      document.getElementById("profile-name").value = user.username || "";
      document.getElementById("profile-global-name").value = user.global_name || "";
      document.getElementById("profile-discriminator").value = user.discriminator || "0";
      document.getElementById("profile-bot").checked = Boolean(user.bot);
      document.getElementById("author-id").value = user.id || "";
      document.getElementById("author-name").value = user.username || "";
      document.getElementById("author-bot").checked = Boolean(user.bot);
    }

    function renderCards(target, items, emptyText, formatter) {
      target.innerHTML = items.map(formatter).join("") || `<div class="small">${emptyText}</div>`;
    }

    async function refresh() {
      const response = await fetch("/api/mock/state");
      const state = await response.json();

      baseUrl.textContent = state.base_url;
      gatewayUrl.textContent = state.gateway_url;
      currentUser.textContent = `${state.current_user.username} (${state.current_user.id})`;
      currentUserSelect.value = formatProfileValue(state.current_user);
      profileOptions.innerHTML = state.users.map((user) =>
        `<option value="${escapeHtml(formatProfileValue(user))}"></option>`
      ).join("");

      requestCount.textContent = state.requests.length;
      messageCount.textContent = state.messages.length;
      typingCount.textContent = state.typing_events.length;
      channelCount.textContent = state.channels.length;
      guildCount.textContent = state.guilds.length;

      renderCards(messages, [...state.messages].reverse(), "No messages yet.", (message) => `
        <article
          class="card"
          data-message-id="${escapeHtml(message.id)}"
          data-message-content="${escapeHtml(message.content || "")}"
          data-channel-id="${escapeHtml(message.channel_id)}"
        >
          <strong>${escapeHtml(message.author.username)}</strong>
          <span class="badge">${escapeHtml(message.channel_id)}</span>
          ${message.guild_id ? `<span class="badge">${escapeHtml(message.guild_id)}</span>` : ""}
          <div class="small">${escapeHtml(message.id)}</div>
          <div class="small">${escapeHtml(message.timestamp || "")}${message.edited_timestamp ? ` · edited ${escapeHtml(message.edited_timestamp)}` : ""}</div>
          <div class="body">${escapeHtml(message.content || "(empty message)")}</div>
        </article>
      `);

      renderCards(typing, [...state.typing_events].reverse(), "No typing events yet.", (entry) => `
        <article class="card">
          <strong>${escapeHtml(entry.username)}</strong>
          <span class="badge">${escapeHtml(entry.channel_id)}</span>
          <div class="small">user_id=${escapeHtml(entry.user_id)}</div>
          <div class="small">${escapeHtml(entry.timestamp || "")}</div>
        </article>
      `);

      renderCards(users, state.users, "No users in state.", (user) => `
        <article
          class="card"
          data-user-id="${escapeHtml(user.id)}"
          data-user-name="${escapeHtml(user.username || "")}"
          data-user-global-name="${escapeHtml(user.global_name || "")}"
          data-user-discriminator="${escapeHtml(user.discriminator || "0")}"
          data-user-bot="${user.bot ? "1" : "0"}"
        >
          <strong>${escapeHtml(user.username)}</strong>
          ${user.bot ? '<span class="badge">bot</span>' : ""}
          <div class="small">${escapeHtml(user.id)}${user.global_name ? ` · ${escapeHtml(user.global_name)}` : ""}</div>
        </article>
      `);

      renderCards(channels, state.channels, "No channels in state.", (channel) => `
        <article
          class="card"
          data-channel-id="${escapeHtml(channel.id)}"
          data-channel-name="${escapeHtml(channel.name || "")}"
          data-channel-topic="${escapeHtml(channel.topic || "")}"
          data-guild-id="${escapeHtml(channel.guild_id || "")}"
        >
          <strong>${escapeHtml(channel.name || "unnamed channel")}</strong>
          <span class="badge">type=${escapeHtml(channel.type)}</span>
          <div class="small">id=${escapeHtml(channel.id)}${channel.guild_id ? ` · guild=${escapeHtml(channel.guild_id)}` : ' · DM'}</div>
          ${channel.topic ? `<div class="body">${escapeHtml(channel.topic)}</div>` : ""}
        </article>
      `);

      renderCards(guilds, state.guilds, "No guilds in state.", (guild) => `
        <article class="card">
          <strong>${escapeHtml(guild.name)}</strong>
          <div class="small">id=${escapeHtml(guild.id)} · members=${escapeHtml(guild.member_count ?? 0)}</div>
        </article>
      `);

      renderCards(requests, [...state.requests].reverse(), "No API calls yet.", (request) => `
        <article class="card">
          <strong>${escapeHtml(request.method)}</strong>
          <span class="badge">${escapeHtml(request.path)}</span>
          <div class="body">${escapeHtml(JSON.stringify(request.json || {}, null, 2))}</div>
        </article>
      `);

      messages.querySelectorAll("[data-message-id]").forEach((node) => {
        node.addEventListener("click", () => {
          document.getElementById("message-id").value = node.getAttribute("data-message-id") || "";
          document.getElementById("message-edit-content").value = node.getAttribute("data-message-content") || "";
          document.getElementById("channel-id").value = node.getAttribute("data-channel-id") || "123";
        });
      });

      channels.querySelectorAll("[data-channel-id]").forEach((node) => {
        node.addEventListener("click", () => {
          document.getElementById("channel-id").value = node.getAttribute("data-channel-id") || "123";
          document.getElementById("channel-name").value = node.getAttribute("data-channel-name") || "";
          document.getElementById("channel-topic").value = node.getAttribute("data-channel-topic") || "";
          const guildId = node.getAttribute("data-guild-id");
          if (guildId) {
            document.getElementById("guild-id").value = guildId;
          }
        });
      });

      users.querySelectorAll("[data-user-id]").forEach((node) => {
        node.addEventListener("click", () => {
          fillProfileForm({
            id: node.getAttribute("data-user-id") || "",
            username: node.getAttribute("data-user-name") || "",
            global_name: node.getAttribute("data-user-global-name") || "",
            discriminator: node.getAttribute("data-user-discriminator") || "0",
            bot: node.getAttribute("data-user-bot") === "1",
          });
        });
      });
    }

    async function simulateMessage() {
      await fetch("/api/mock/messages", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          channel_id: document.getElementById("channel-id").value || "123",
          channel_name: document.getElementById("channel-name").value || "general",
          guild_id: document.getElementById("guild-id").value || "999",
          guild_name: document.getElementById("guild-name").value || "Mock Guild",
          author_id: document.getElementById("author-id").value || "2",
          author_username: document.getElementById("author-name").value || "MockUser",
          author_bot: document.getElementById("author-bot").checked,
          content: document.getElementById("content").value
        })
      });
      document.getElementById("content").value = "";
      await refresh();
    }

    async function sendBotMessage() {
      const channelId = document.getElementById("channel-id").value || "123";
      await fetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          content: document.getElementById("content").value
        })
      });
      document.getElementById("content").value = "";
      await refresh();
    }

    async function triggerTyping() {
      const channelId = document.getElementById("channel-id").value || "123";
      await fetch(`/api/v10/channels/${encodeURIComponent(channelId)}/typing`, {
        method: "POST"
      });
      await refresh();
    }

    async function saveChannel() {
      const channelId = document.getElementById("channel-id").value || "123";
      await fetch(`/api/v10/channels/${encodeURIComponent(channelId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          name: document.getElementById("channel-name").value,
          topic: document.getElementById("channel-topic").value
        })
      });
      await refresh();
    }

    async function editMessage() {
      const channelId = document.getElementById("channel-id").value || "123";
      const messageId = document.getElementById("message-id").value;
      if (!messageId) return;
      await fetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          content: document.getElementById("message-edit-content").value
        })
      });
      await refresh();
    }

    async function deleteMessage() {
      const channelId = document.getElementById("channel-id").value || "123";
      const messageId = document.getElementById("message-id").value;
      if (!messageId) return;
      await fetch(`/api/v10/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`, {
        method: "DELETE"
      });
      document.getElementById("message-id").value = "";
      document.getElementById("message-edit-content").value = "";
      await refresh();
    }

    async function resetState() {
      await fetch("/api/mock/reset", {method: "POST"});
      document.getElementById("message-id").value = "";
      document.getElementById("message-edit-content").value = "";
      await refresh();
    }

    async function createProfile() {
      const response = await fetch("/api/mock/profiles", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          id: document.getElementById("profile-id").value || undefined,
          username: document.getElementById("profile-name").value || "Profile",
          global_name: document.getElementById("profile-global-name").value || null,
          discriminator: document.getElementById("profile-discriminator").value || "0",
          bot: document.getElementById("profile-bot").checked
        })
      });
      const profile = await response.json();
      fillProfileForm(profile);
      await refresh();
    }

    async function saveProfile() {
      const profileId = document.getElementById("profile-id").value;
      if (!profileId) return;
      const response = await fetch(`/api/mock/profiles/${encodeURIComponent(profileId)}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          username: document.getElementById("profile-name").value || "Profile",
          global_name: document.getElementById("profile-global-name").value || null,
          discriminator: document.getElementById("profile-discriminator").value || "0",
          bot: document.getElementById("profile-bot").checked
        })
      });
      const profile = await response.json();
      fillProfileForm(profile);
      await refresh();
    }

    async function setCurrentProfile() {
      const profileId = document.getElementById("profile-id").value || parseSelectedProfileId();
      if (!profileId) return;
      await fetch("/api/mock/current-user", {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user_id: profileId})
      });
      await refresh();
    }

    document.getElementById("send-btn").addEventListener("click", simulateMessage);
    document.getElementById("send-bot-btn").addEventListener("click", sendBotMessage);
    document.getElementById("typing-btn").addEventListener("click", triggerTyping);
    document.getElementById("save-channel-btn").addEventListener("click", saveChannel);
    document.getElementById("edit-message-btn").addEventListener("click", editMessage);
    document.getElementById("delete-message-btn").addEventListener("click", deleteMessage);
    document.getElementById("create-profile-btn").addEventListener("click", createProfile);
    document.getElementById("save-profile-btn").addEventListener("click", saveProfile);
    document.getElementById("set-current-profile-btn").addEventListener("click", setCurrentProfile);
    currentUserSelect.addEventListener("change", setCurrentProfile);
    document.getElementById("refresh-btn").addEventListener("click", refresh);
    document.getElementById("reset-btn").addEventListener("click", resetState);

    refresh();
    setInterval(refresh, 1800);
  </script>
</body>
</html>
"""
