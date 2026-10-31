const platformState = {
  me: null,
  favorites: new Set(),
  favoriteRows: [],
  notifications: [],
  sharingTaskId: "",
  shareUrl: "",
  authMode: "login",
  tourStep: 0,
  confirmAction: null,
  uploadTimer: null,
};

const platformQuery = (selector, root = document) => root.querySelector(selector);

function platformEsc(value) {
  return typeof esc === "function" ? esc(value) : String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function platformInitial(value) {
  const text = String(value || "D").trim();
  return (text.charAt(0) || "D").toUpperCase();
}

function platformAnnounce(message) {
  const live = document.getElementById("a11y-live");
  if (live) live.textContent = message;
}

async function platformLoadMe() {
  try {
    const payload = await api("/api/auth/me");
    platformState.me = payload;
    platformRenderIdentity();
    await Promise.allSettled([platformLoadFavorites(), platformLoadNotifications()]);
  } catch (error) {
    platformState.me = null;
  }
}

function platformRenderIdentity() {
  const payload = platformState.me;
  const user = payload?.user || { display_name: "Demo user", email: "" };
  const workspace = payload?.workspace || { name: "Demo workspace", role: "admin" };
  const authenticated = Boolean(payload?.authenticated);
  const initials = platformInitial(user.display_name);
  const workspaceInitials = String(workspace.name || "AB").slice(0, 2).toUpperCase();
  const name = document.getElementById("sidebar-user-name");
  const role = document.getElementById("sidebar-user-role");
  const avatar = document.getElementById("sidebar-user-avatar");
  const toolbarUser = document.getElementById("toolbar-user");
  const accountButton = document.getElementById("account-button");
  const workspaceName = document.getElementById("workspace-name");
  const workspaceAvatar = document.getElementById("workspace-avatar");
  if (name) name.textContent = user.display_name || "Demo user";
  if (role) role.textContent = authenticated ? user.email || "Signed in" : "Demo mode";
  if (avatar) avatar.textContent = initials;
  if (toolbarUser) {
    toolbarUser.textContent = initials;
    toolbarUser.setAttribute("aria-label", authenticated ? `Account for ${user.display_name}` : "Sign in");
  }
  if (accountButton) accountButton.textContent = authenticated ? "Account" : "Sign in";
  if (workspaceName) workspaceName.textContent = workspace.name || "Demo workspace";
  if (workspaceAvatar) workspaceAvatar.textContent = workspaceInitials;
  const accountBadge = document.getElementById("settings-account-badge");
  if (accountBadge) accountBadge.textContent = authenticated ? "Signed in" : "Demo mode";
  const settingsAccount = document.getElementById("settings-account");
  if (settingsAccount) {
    settingsAccount.innerHTML = authenticated
      ? `<div class="api-note">${icon("user")}<div><strong>${platformEsc(user.display_name)}</strong><p>${platformEsc(user.email)}</p></div></div>
         <div class="settings-data-actions"><a class="btn secondary" href="/settings">Manage account</a><button class="btn danger" type="button" data-platform-logout>Sign out</button></div>`
      : `<p class="small muted">You are using a shared demo workspace. Create an account to keep saved tasks, favorites and settings.</p>
         <div class="settings-data-actions"><button class="btn primary" type="button" data-open-auth="register">Create an account</button><button class="btn secondary" type="button" data-open-auth="login">Sign in</button></div>`;
  }
  platformRenderWorkspaceMenu();
  platformRenderAuthModal();
  if (payload?.settings) platformApplySavedSettings(payload.settings);
}

function platformApplySavedSettings(settings) {
  if (!settings) return;
  if (!localStorage.getItem("agent-bazaar-theme") && ["light", "dark"].includes(settings.theme)) {
    applyTheme(settings.theme);
  }
  if (settings.high_contrast) platformSetContrast(true, false);
  const themeSelect = document.getElementById("settings-theme");
  if (themeSelect) themeSelect.value = settings.theme || "dark";
  const contrast = document.getElementById("settings-contrast");
  if (contrast) contrast.checked = Boolean(settings.high_contrast) || document.documentElement.dataset.contrast === "on";
  const notifications = document.getElementById("settings-notifications");
  if (notifications) notifications.checked = settings.notifications !== false;
}

function platformSetContrast(enabled, persist = true) {
  if (enabled) document.documentElement.dataset.contrast = "on";
  else delete document.documentElement.dataset.contrast;
  if (persist) {
    try {
      if (enabled) localStorage.setItem("agent-bazaar-contrast", "on");
      else localStorage.removeItem("agent-bazaar-contrast");
    } catch (error) {}
  }
  const toggle = document.getElementById("contrast-toggle");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(Boolean(enabled)));
    toggle.classList.toggle("active", Boolean(enabled));
  }
}

function platformResolveTheme(theme) {
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  return theme === "light" ? "light" : "dark";
}

function platformBindTheme() {
  const toggle = document.getElementById("contrast-toggle");
  toggle?.addEventListener("click", () => {
    platformSetContrast(document.documentElement.dataset.contrast !== "on");
    platformAnnounce(document.documentElement.dataset.contrast === "on" ? "High contrast on" : "High contrast off");
  });
  if (document.documentElement.dataset.contrast === "on") platformSetContrast(true, false);
  try {
    if (localStorage.getItem("agent-bazaar-theme-preference") === "system") {
      applyTheme(platformResolveTheme("system"));
    }
  } catch (error) {}
  const media = window.matchMedia("(prefers-color-scheme: light)");
  media.addEventListener?.("change", () => {
    let preference = "dark";
    try {
      preference = localStorage.getItem("agent-bazaar-theme-preference") || "dark";
    } catch (error) {}
    if (preference === "system") applyTheme(platformResolveTheme("system"));
  });
}

async function platformLoadFavorites() {
  try {
    const payload = await api("/api/favorites");
    platformState.favoriteRows = payload.favorites || [];
    platformState.favorites = new Set(platformState.favoriteRows.map((row) => row.tool_id));
    if (typeof state !== "undefined") {
      state.savedTools = platformState.favorites;
      if (state.page === "marketplace") renderMarketplace();
    }
    if (document.body.dataset.page === "settings") platformRenderSavedWork();
    platformRefreshOpenToolFavorite();
  } catch (error) {}
}

async function platformSaveFavorite(toolId, note = "", tags = "") {
  try {
    await api("/api/favorites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_id: toolId, note, tags }),
    });
    platformState.favorites.add(toolId);
    platformState.favoriteRows = platformState.favoriteRows.filter((row) => row.tool_id !== toolId);
    platformState.favoriteRows.unshift({ tool_id: toolId, note, tags });
    if (typeof state !== "undefined") {
      state.savedTools = platformState.favorites;
      if (state.page === "marketplace") renderMarketplace();
    }
    if (document.body.dataset.page === "settings") platformRenderSavedWork();
    platformRefreshOpenToolFavorite();
    return true;
  } catch (error) {
    toast(`Could not save tool: ${error.message}`, "bad");
    return false;
  }
}

async function platformToggleFavorite(toolId, note = "", tags = "") {
  const saved = platformState.favorites.has(toolId);
  if (!saved) {
    if (await platformSaveFavorite(toolId, note, tags)) {
      toast("Saved. Find it under Find tools → Saved.", "ok");
    }
    return;
  }
  try {
    await api(`/api/favorites/${encodeURIComponent(toolId)}`, { method: "DELETE" });
    platformState.favorites.delete(toolId);
    platformState.favoriteRows = platformState.favoriteRows.filter((row) => row.tool_id !== toolId);
    if (typeof state !== "undefined") {
      state.savedTools = platformState.favorites;
      if (state.page === "marketplace") renderMarketplace();
    }
    if (document.body.dataset.page === "settings") platformRenderSavedWork();
    platformRefreshOpenToolFavorite();
    toast("Removed from saved tools.", "ok");
  } catch (error) {
    toast(`Could not update saved tools: ${error.message}`, "bad");
  }
}

function platformRefreshOpenToolFavorite() {
  const modal = document.getElementById("tool-modal");
  if (!modal?.classList.contains("is-open")) return;
  const route = document.getElementById("tool-modal-route")?.textContent || "";
  const toolId = route.replace(/^service \/ /, "").trim();
  if (toolId) platformEnhanceToolModal(toolId);
}

function platformEnhanceToolModal(toolId) {
  const body = document.getElementById("tool-modal-body");
  if (!body) return;
  body.querySelector("[data-favorite-panel]")?.remove();
  const row = platformState.favoriteRows.find((entry) => entry.tool_id === toolId);
  const saved = platformState.favorites.has(toolId);
  const tool = typeof toolById === "function" ? toolById(toolId) : null;
  if (tool && !body.querySelector("[data-tool-preview]")) {
    const preview = document.createElement("div");
    preview.className = "tool-preview";
    preview.dataset.toolPreview = "true";
    preview.innerHTML = `<div class="tool-preview-bar"><span>Example result</span><span class="badge verified">${icon("check")}Checked</span></div>
      <div class="tool-preview-body"><span class="tool-icon">${icon(capabilityIcon(tool.capability))}</span><div><strong>${platformEsc(tool.name)}</strong><p>${platformEsc(tool.description || "A short, plain description of this tool.")}</p><small>Inputs: ${platformEsc((tool.inputs || []).map((input) => input.concept).join(", ") || "none")}</small></div></div>`;
    body.insertBefore(preview, body.querySelector(".detail-grid") || body.firstChild);
  }
  const panel = document.createElement("div");
  panel.className = "favorite-panel";
  panel.dataset.favoritePanel = "true";
  panel.innerHTML = `<div class="inline-head"><h3 style="margin:0">${icon("star")}${saved ? "Saved tool" : "Save this tool"}</h3><button class="btn small ${saved ? "danger" : "secondary"}" type="button" data-toggle-tool-save>${saved ? "Remove" : "Save tool"}</button></div>
    <form class="form-stack" data-favorite-note-form>
      <label>Note<input name="note" maxlength="500" value="${platformEsc(row?.note || "")}" placeholder="Why is this tool useful?"></label>
      <label>Tags<input name="tags" maxlength="200" value="${platformEsc(row?.tags || "")}" placeholder="weather, free, keyless"></label>
      <button class="btn small secondary" type="submit">${saved ? "Update note and tags" : "Save with note"}</button>
    </form>`;
  const footer = body.querySelector(".tool-modal-footer");
  if (footer) body.insertBefore(panel, footer);
  else body.appendChild(panel);
  panel.querySelector("[data-toggle-tool-save]")?.addEventListener("click", () => platformToggleFavorite(toolId));
  panel.querySelector("[data-favorite-note-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (await platformSaveFavorite(toolId, String(data.get("note") || ""), String(data.get("tags") || ""))) {
      toast("Tool saved with your note.", "ok");
    }
  });
}

function platformBindMarketplace() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-favorite-tool]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    platformToggleFavorite(button.dataset.favoriteTool);
  }, true);
  document.addEventListener("keydown", (event) => {
    const button = event.target.closest("[data-favorite-tool]");
    if (!button || !["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    platformToggleFavorite(button.dataset.favoriteTool);
  }, true);
  document.addEventListener("platform:tool-opened", (event) => {
    platformEnhanceToolModal(event.detail.toolId);
  });
  document.addEventListener("platform:market-rendered", () => {
    document.querySelectorAll("[data-favorite-tool]").forEach((button) => {
      const saved = platformState.favorites.has(button.dataset.favoriteTool);
      button.classList.toggle("is-saved", saved);
      button.setAttribute("aria-pressed", String(saved));
      button.setAttribute("aria-label", saved ? "Remove from saved tools" : "Save tool");
    });
  });
}

async function platformLoadNotifications() {
  try {
    const payload = await api("/api/notifications?limit=30");
    platformState.notifications = payload.notifications || [];
    const button = document.getElementById("notification-button");
    const dot = button?.querySelector(".notification-dot");
    if (dot) dot.classList.toggle("hidden", !payload.unread);
    if (button) button.setAttribute("aria-label", payload.unread ? `Open notifications, ${payload.unread} unread` : "Open notifications");
    platformRenderNotifications();
  } catch (error) {}
}

function platformRenderNotifications() {
  const list = document.getElementById("notification-list");
  if (!list) return;
  list.innerHTML = platformState.notifications.length
    ? platformState.notifications
        .map(
          (item) => `<div class="notification-item ${item.read_at ? "" : "is-unread"}">
            ${item.read_at ? "" : '<span class="notification-dot" aria-hidden="true"></span>'}
            <div><strong>${platformEsc(item.title)}</strong><p class="small">${platformEsc(item.body)}</p><small>${formatDateTime(item.created_at)}</small></div>
          </div>`
        )
        .join("")
    : `<div class="empty-panel compact"><strong>No notifications yet</strong><p>Run a task or a scheduled job to see updates here.</p></div>`;
}

async function platformOpenNotifications() {
  await platformLoadNotifications();
  openModal("notifications-modal");
  document.getElementById("mark-notifications-read")?.focus();
}

async function platformMarkNotificationsRead() {
  try {
    await api("/api/notifications/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [] }),
    });
    await platformLoadNotifications();
    toast("Notifications marked as read.", "ok");
  } catch (error) {
    toast(`Could not update notifications: ${error.message}`, "bad");
  }
}

function platformRenderWorkspaceMenu() {
  const list = document.getElementById("workspace-menu-list");
  if (!list) return;
  const workspaces = platformState.me?.workspaces || [];
  list.innerHTML = workspaces
    .map(
      (workspace) => `<button type="button" role="menuitem" data-platform-workspace="${platformEsc(workspace.workspace_id)}" aria-current="${workspace.workspace_id === platformState.me?.workspace?.workspace_id}">
        <span><strong>${platformEsc(workspace.name)}</strong><small>${platformEsc(workspace.role)}</small></span>
      </button>`
    )
    .join("");
}

function platformToggleWorkspaceMenu() {
  const menu = document.getElementById("workspace-menu");
  const switcher = document.getElementById("workspace-switcher");
  if (!menu) return;
  const open = menu.classList.toggle("hidden");
  switcher?.setAttribute("aria-expanded", String(!open));
  if (!open) {
    platformRenderWorkspaceMenu();
    menu.querySelector("button")?.focus();
  }
}

function platformBindWorkspace() {
  document.addEventListener("platform:workspace-menu", () => platformToggleWorkspaceMenu());
  document.getElementById("workspace-menu-list")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-platform-workspace]");
    if (!button) return;
    try {
      await api("/api/platform/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: button.dataset.platformWorkspace }),
      });
      window.location.reload();
    } catch (error) {
      toast(`Could not switch workspace: ${error.message}`, "bad");
    }
  });
  document.getElementById("workspace-create-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("workspace-create-name");
    const name = input?.value?.trim();
    if (!name) return;
    try {
      await api("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      window.location.reload();
    } catch (error) {
      toast(`Could not create workspace: ${error.message}`, "bad");
    }
  });
  document.addEventListener("click", (event) => {
    const menu = document.getElementById("workspace-menu");
    if (!menu || menu.classList.contains("hidden")) return;
    if (menu.contains(event.target) || event.target.closest("#workspace-switcher")) return;
    menu.classList.add("hidden");
    document.getElementById("workspace-switcher")?.setAttribute("aria-expanded", "false");
  });
}

function platformSetAuthMode(mode) {
  platformState.authMode = mode === "register" ? "register" : "login";
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.authMode === platformState.authMode));
  });
  document.getElementById("auth-name-row")?.classList.toggle("hidden", platformState.authMode !== "register");
  document.getElementById("auth-workspace-row")?.classList.toggle("hidden", platformState.authMode !== "register");
  const submit = document.getElementById("auth-submit");
  if (submit) submit.textContent = platformState.authMode === "register" ? "Create account" : "Sign in";
  const password = document.getElementById("auth-password");
  if (password) password.autocomplete = platformState.authMode === "register" ? "new-password" : "current-password";
}

function platformOpenAuth(mode = "login") {
  platformSetAuthMode(mode);
  platformRenderAuthModal();
  openModal("auth-modal");
  const focus = platformState.me?.authenticated
    ? document.getElementById("auth-logout")
    : document.getElementById("auth-email");
  focus?.focus();
}

function platformRenderAuthModal() {
  const signedIn = Boolean(platformState.me?.authenticated);
  document.getElementById("auth-form")?.classList.toggle("hidden", signedIn);
  document.querySelector(".segmented")?.classList.toggle("hidden", signedIn);
  document.getElementById("auth-signed-in")?.classList.toggle("hidden", !signedIn);
  const name = document.getElementById("auth-user-name");
  const email = document.getElementById("auth-user-email");
  if (name) name.textContent = platformState.me?.user?.display_name || "Signed in";
  if (email) email.textContent = platformState.me?.user?.email || "";
}

function platformBindAuth() {
  document.addEventListener("click", (event) => {
    const open = event.target.closest("[data-open-auth]");
    if (open) {
      event.preventDefault();
      platformOpenAuth(open.dataset.openAuth);
      return;
    }
    if (event.target.closest("[data-platform-logout]")) {
      event.preventDefault();
      platformLogout();
    }
  });
  document.getElementById("account-button")?.addEventListener("click", () => platformOpenAuth("login"));
  document.getElementById("toolbar-user")?.addEventListener("click", () => platformOpenAuth("login"));
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => platformSetAuthMode(button.dataset.authMode));
  });
  document.getElementById("auth-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("auth-email")?.value?.trim() || "";
    const password = document.getElementById("auth-password")?.value || "";
    const displayName = document.getElementById("auth-name")?.value?.trim() || "";
    const workspaceName = document.getElementById("auth-workspace")?.value?.trim() || "";
    const result = document.getElementById("auth-result");
    const submit = document.getElementById("auth-submit");
    if (submit) submit.disabled = true;
    try {
      const payload =
        platformState.authMode === "register"
          ? { email, password, display_name: displayName, workspace_name: workspaceName }
          : { email, password, display_name: "", workspace_name: "" };
      await api(`/api/auth/${platformState.authMode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast(platformState.authMode === "register" ? "Account created." : "Signed in.", "ok");
      window.location.reload();
    } catch (error) {
      if (result) {
        result.className = "inline-result error";
        result.textContent = error.message;
      }
    } finally {
      if (submit) submit.disabled = false;
    }
  });
  document.getElementById("auth-logout")?.addEventListener("click", platformLogout);
}

async function platformLogout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
    window.location.reload();
  } catch (error) {
    toast(`Could not sign out: ${error.message}`, "bad");
  }
}

async function platformLoadRecent() {
  const container = document.getElementById("recent-tasks");
  if (!container) return;
  try {
    const payload = await api("/api/tasks/recent?limit=5");
    const tasks = payload.tasks || [];
    container.innerHTML = tasks.length
      ? tasks
          .map(
            (task) => `<button class="recent-task" type="button" data-platform-recent="${platformEsc(task.task_id)}">
              <span><strong>${platformEsc(task.task)}</strong><small>${platformEsc(task.status)} · ${formatDateTime(task.created_at)}</small></span>
              ${icon("chevron-right")}
            </button>`
          )
          .join("")
      : `<div class="empty-panel compact"><strong>No tasks yet</strong><p>Ask your first question above. It will appear here.</p></div>`;
  } catch (error) {
    container.innerHTML = `<div class="empty-panel compact"><strong>Recent tasks unavailable</strong><p>${platformEsc(error.message)}</p></div>`;
  }
}

function platformBindRecent() {
  document.getElementById("recent-refresh")?.addEventListener("click", platformLoadRecent);
  document.getElementById("recent-tasks")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-platform-recent]");
    if (!button) return;
    await loadTask(button.dataset.platformRecent);
    window.history.replaceState(null, "", `/dashboard?task=${encodeURIComponent(button.dataset.platformRecent)}`);
    document.getElementById("results-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
    document.getElementById("answer-text")?.focus?.();
  });
  document.getElementById("starter-grid")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-starter]");
    if (!button) return;
    const input = document.getElementById("task-input");
    if (input) {
      input.value = button.dataset.starter;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    }
    runTask(button.dataset.starter);
  });
}

function platformTaskActions() {
  const actions = document.getElementById("task-actions");
  const result = typeof state !== "undefined" ? state.result : null;
  if (!actions || !result) return;
  const tools = [...new Set((result.plan?.steps || []).map((step) => step.tool_id).filter(Boolean))];
  actions.innerHTML = `
    <button class="btn small secondary" type="button" data-task-action="save">${icon("star")}Save task</button>
    <button class="btn small secondary" type="button" data-task-action="workflow">${icon("layers")}Save workflow</button>
    ${tools.length ? `<button class="btn small secondary" type="button" data-task-action="favorite">${icon("star")}Save source tools</button>` : ""}
    <button class="btn small secondary" type="button" data-task-action="share">${icon("external")}Share or export</button>
    <button class="btn small ghost" type="button" data-task-action="copy">${icon("copy")}Copy answer</button>`;
  actions.querySelector("[data-task-action='save']")?.addEventListener("click", platformSaveTask);
  actions.querySelector("[data-task-action='workflow']")?.addEventListener("click", platformSaveWorkflow);
  actions.querySelector("[data-task-action='favorite']")?.addEventListener("click", () => {
    tools.forEach((toolId) => {
      if (!platformState.favorites.has(toolId)) platformToggleFavorite(toolId);
    });
  });
  actions.querySelector("[data-task-action='share']")?.addEventListener("click", () => platformOpenShare(result.task_id));
  actions.querySelector("[data-task-action='copy']")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(result.answer || "");
      toast("Answer copied.", "ok");
    } catch (error) {
      toast("Copy was blocked by the browser.", "bad");
    }
  });
}

function platformRenderCalculation() {
  const body = document.getElementById("calc-body");
  const result = typeof state !== "undefined" ? state.result : null;
  if (!body || !result) return;
  const steps = result.plan?.steps || [];
  const warnings = result.warnings || [];
  body.innerHTML = steps.length
    ? steps
        .map(
          (step, index) => `<div class="calc-step">
            <strong>${index + 1}. ${platformEsc(step.tool_name || step.tool_id)}</strong>
            <div>Did: ${platformEsc(step.capability || "a step")} · Result: ${platformEsc(step.status)}${step.cached ? " · reused a saved result" : ""}</div>
            ${step.error ? `<div class="small muted">Problem: ${platformEsc(step.error)}</div>` : ""}
          </div>`
        )
        .join("") + (warnings.length ? `<div class="calc-step"><strong>Notes</strong><div>${warnings.map((warning) => platformEsc(warning)).join("<br>")}</div></div>` : "")
    : "<p>No tools were needed for this answer.</p>";
}

async function platformSaveTask() {
  const result = typeof state !== "undefined" ? state.result : null;
  if (!result) return;
  try {
    await api("/api/saved-tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: result.task_id, title: result.task.slice(0, 300) }),
    });
    toast("Task saved.", "ok");
  } catch (error) {
    toast(`Could not save task: ${error.message}`, "bad");
  }
}

async function platformSaveWorkflow() {
  const result = typeof state !== "undefined" ? state.result : null;
  if (!result) return;
  try {
    await api("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: result.task.slice(0, 120),
        task: result.task,
        document_id: result.document_id || null,
        plan: { steps: result.plan?.steps || [] },
      }),
    });
    toast("Workflow saved. Replay it from Settings.", "ok");
  } catch (error) {
    toast(`Could not save workflow: ${error.message}`, "bad");
  }
}

async function platformOpenShare(taskId) {
  openModal("share-modal");
  const input = document.getElementById("share-url");
  const status = document.getElementById("share-status");
  const copy = document.getElementById("copy-share");
  platformState.sharingTaskId = taskId;
  platformState.shareUrl = "";
  if (input) input.value = "";
  if (copy) copy.disabled = true;
  if (status) status.textContent = "Creating a read-only link…";
  try {
    const payload = await api(`/api/tasks/${encodeURIComponent(taskId)}/share`, { method: "POST" });
    platformState.shareUrl = payload.url;
    if (input) input.value = payload.url;
    if (copy) copy.disabled = false;
    if (status) status.textContent = "Anyone with this link can read the answer and evidence.";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

function platformBindShare() {
  document.getElementById("copy-share")?.addEventListener("click", async () => {
    if (!platformState.shareUrl) return;
    try {
      await navigator.clipboard.writeText(platformState.shareUrl);
      toast("Share link copied.", "ok");
    } catch (error) {
      const input = document.getElementById("share-url");
      input?.select();
      toast("Select the link and copy it manually.", "bad");
    }
  });
  document.getElementById("share-exports")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-export]");
    if (!button || !platformState.sharingTaskId) return;
    const url = `/api/tasks/${encodeURIComponent(platformState.sharingTaskId)}/export?format=${button.dataset.export}`;
    window.location.href = url;
  });
}

function platformBindResult() {
  document.addEventListener("platform:result", () => {
    platformTaskActions();
    platformRenderCalculation();
    platformLoadRecent();
    platformLoadNotifications();
  });
}

async function platformLoadFavoritesList() {
  const payload = await api("/api/favorites");
  platformState.favoriteRows = payload.favorites || [];
  platformState.favorites = new Set(platformState.favoriteRows.map((row) => row.tool_id));
}

function platformRenderSavedWork() {
  const container = document.getElementById("settings-saved");
  if (!container) return;
  container.innerHTML = `<div class="loading-line">Loading saved work…</div>`;
  Promise.all([platformLoadFavoritesList(), api("/api/saved-tasks"), api("/api/workflows")])
    .then(([, tasksPayload, workflowsPayload]) => {
      const favoriteRows = platformState.favoriteRows
        .map((row) => `<div class="list-row"><span><strong>${platformEsc(row.tool_id)}</strong><small>${platformEsc(row.tags || row.note || "Saved tool")}</small></span><button class="btn danger small" type="button" data-delete-favorite="${platformEsc(row.tool_id)}">Remove</button></div>`)
        .join("");
      const taskRows = (tasksPayload.saved_tasks || [])
        .map((row) => `<div class="list-row"><span><strong>${platformEsc(row.title)}</strong><small>Saved task</small></span><button class="btn secondary small" type="button" data-replay-task="${platformEsc(row.task_id)}">Open</button><button class="btn danger small" type="button" data-delete-saved="${platformEsc(row.task_id)}">Remove</button></div>`)
        .join("");
      const workflowRows = (workflowsPayload.workflows || [])
        .map((row) => `<div class="list-row"><span><strong>${platformEsc(row.name)}</strong><small>${platformEsc(row.task)}</small></span><button class="btn secondary small" type="button" data-run-workflow="${platformEsc(row.task)}">Run</button><button class="btn danger small" type="button" data-delete-workflow="${platformEsc(row.workflow_id)}">Remove</button></div>`)
        .join("");
      container.innerHTML =
        `<h3>Saved tools</h3>${favoriteRows || '<p class="small muted">No saved tools yet.</p>'}` +
        `<h3>Saved tasks</h3>${taskRows || '<p class="small muted">No saved tasks yet.</p>'}` +
        `<h3>Workflows</h3>${workflowRows || '<p class="small muted">No workflows yet.</p>'}`;
    })
    .catch((error) => {
      container.innerHTML = `<p class="small muted">Saved work unavailable: ${platformEsc(error.message)}</p>`;
    });
}

function platformBindSettings() {
  const displayForm = document.getElementById("settings-display-form");
  displayForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const theme = document.getElementById("settings-theme")?.value || "dark";
    const highContrast = Boolean(document.getElementById("settings-contrast")?.checked);
    const notifications = Boolean(document.getElementById("settings-notifications")?.checked);
    try {
      const resolved = platformResolveTheme(theme);
      applyTheme(resolved);
      try {
        localStorage.setItem("agent-bazaar-theme-preference", theme);
        localStorage.setItem("agent-bazaar-theme", resolved);
      } catch (error) {}
      platformSetContrast(highContrast);
      await api("/api/platform/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme, high_contrast: highContrast, notifications }),
      });
      toast("Display settings saved.", "ok");
    } catch (error) {
      toast(`Could not save settings: ${error.message}`, "bad");
    }
  });
  document.getElementById("settings-workspace-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("settings-workspace-name")?.value?.trim();
    if (!name) return;
    try {
      await api("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      window.location.reload();
    } catch (error) {
      toast(`Could not create workspace: ${error.message}`, "bad");
    }
  });
  document.getElementById("settings-key-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const provider = document.getElementById("settings-key-provider")?.value?.trim();
    const key = document.getElementById("settings-key-value")?.value || "";
    if (!provider || !key) return;
    try {
      await api("/api/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, key }),
      });
      document.getElementById("settings-key-value").value = "";
      await platformLoadKeys();
      toast("Credential saved.", "ok");
    } catch (error) {
      toast(`Could not save credential: ${error.message}`, "bad");
    }
  });
  document.getElementById("settings-import")?.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const result = await api("/api/workspace/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast(`Imported ${JSON.stringify(result.imported || {})}.`, "ok");
      window.location.reload();
    } catch (error) {
      toast(`Could not import workspace: ${error.message}`, "bad");
    }
  });
  document.getElementById("settings-saved")?.addEventListener("click", async (event) => {
    const favorite = event.target.closest("[data-delete-favorite]");
    const saved = event.target.closest("[data-delete-saved]");
    const workflow = event.target.closest("[data-delete-workflow]");
    const replay = event.target.closest("[data-replay-task]");
    const run = event.target.closest("[data-run-workflow]");
    try {
      if (favorite) {
        await api(`/api/favorites/${encodeURIComponent(favorite.dataset.deleteFavorite)}`, { method: "DELETE" });
        platformRenderSavedWork();
      } else if (saved) {
        await api(`/api/saved-tasks/${encodeURIComponent(saved.dataset.deleteSaved)}`, { method: "DELETE" });
        platformRenderSavedWork();
      } else if (workflow) {
        await api(`/api/workflows/${encodeURIComponent(workflow.dataset.deleteWorkflow)}`, { method: "DELETE" });
        platformRenderSavedWork();
      } else if (replay) {
        window.location.href = `/dashboard?task=${encodeURIComponent(replay.dataset.replayTask)}`;
      } else if (run) {
        window.location.href = `/dashboard?run=${encodeURIComponent(run.dataset.runWorkflow)}`;
      }
    } catch (error) {
      toast(`Could not update saved work: ${error.message}`, "bad");
    }
  });
  document.getElementById("settings-workspaces")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-switch-workspace]");
    if (!button) return;
    try {
      await api("/api/platform/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: button.dataset.switchWorkspace }),
      });
      window.location.reload();
    } catch (error) {
      toast(`Could not switch workspace: ${error.message}`, "bad");
    }
  });
}

async function platformLoadKeys() {
  const container = document.getElementById("settings-key-list");
  if (!container) return;
  try {
    const payload = await api("/api/api-keys");
    container.innerHTML = (payload.keys || [])
      .map((key) => `<div class="list-row"><span><strong>${platformEsc(key.provider)}</strong><small>${platformEsc(key.masked)} · updated ${formatDateTime(key.updated_at)}</small></span><button class="btn danger small" type="button" data-delete-key="${platformEsc(key.provider)}">Remove</button></div>`)
      .join("") || '<p class="small muted" style="padding:12px 0">No saved credentials.</p>';
  } catch (error) {
    container.innerHTML = `<p class="small muted">Credentials unavailable: ${platformEsc(error.message)}</p>`;
  }
}

function platformBindKeys() {
  document.getElementById("settings-key-list")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-key]");
    if (!button) return;
    try {
      await api(`/api/api-keys/${encodeURIComponent(button.dataset.deleteKey)}`, { method: "DELETE" });
      await platformLoadKeys();
      toast("Credential removed.", "ok");
    } catch (error) {
      toast(`Could not remove credential: ${error.message}`, "bad");
    }
  });
}

async function platformRenderSettingsPage() {
  const workspaces = document.getElementById("settings-workspaces");
  if (workspaces) {
    const payload = await api("/api/workspaces");
    workspaces.innerHTML = (payload.workspaces || [])
      .map(
        (workspace) => `<div class="list-row"><span><strong>${platformEsc(workspace.name)}</strong><small>${platformEsc(workspace.role)}</small></span>${workspace.workspace_id === payload.active?.workspace_id ? '<span class="badge verified">Current</span>' : `<button class="btn secondary small" type="button" data-switch-workspace="${platformEsc(workspace.workspace_id)}">Switch</button>`}</div>`
      )
      .join("");
  }
  await Promise.allSettled([platformLoadKeys(), platformRenderSavedWork()]);
  platformApplySavedSettings(platformState.me?.settings);
}

function platformMetric(label, value, detail) {
  return `<div class="metric-card"><span>${platformEsc(label)}</span><strong>${platformEsc(value)}</strong><small>${platformEsc(detail)}</small></div>`;
}

async function platformRenderAnalytics() {
  const metrics = document.getElementById("analytics-metrics");
  const chart = document.getElementById("analytics-chart");
  const tools = document.getElementById("analytics-tools");
  const capabilities = document.getElementById("analytics-capabilities");
  try {
    const payload = await api("/api/analytics");
    const totals = payload.totals || {};
    if (metrics) {
      metrics.innerHTML =
        platformMetric("Tasks", totals.tasks ?? 0, "Recorded in this workspace") +
        platformMetric("Success rate", `${Math.round(Number(totals.success_rate || 0) * 100)}%`, `${totals.completed || 0} completed`) +
        platformMetric("Average time", `${Math.round(Number(totals.average_latency_ms || 0))} ms`, "Across recorded tasks") +
        platformMetric("Needs attention", totals.failed ?? 0, "Partial or failed tasks");
    }
    const days = payload.by_day || [];
    if (chart) {
      const max = Math.max(1, ...days.map((day) => Number(day.tasks || 0)));
      chart.innerHTML = days.length
        ? `<div class="chart-bars">${days
            .map(
              (day) => `<div class="chart-bar"><span style="height:${Math.max(6, Math.round((Number(day.tasks || 0) / max) * 120))}px" title="${platformEsc(day.date)}: ${day.tasks} tasks"></span><small>${platformEsc(day.date.slice(5))}</small></div>`
            )
            .join("")}</div>`
        : `<div class="empty-panel compact"><strong>No activity yet</strong><p>Run a task to start the chart.</p></div>`;
    }
    const listMarkup = (rows, labelKey, valueKey) =>
      rows.length
        ? rows.map((row) => `<div class="list-row"><span><strong>${platformEsc(row[labelKey])}</strong></span><span class="badge neutral">${row[valueKey]} task${row[valueKey] === 1 ? "" : "s"}</span></div>`).join("")
        : '<p class="small muted" style="padding:12px 0">No data yet.</p>';
    if (tools) tools.innerHTML = listMarkup(payload.top_tools || [], "tool_id", "tasks");
    if (capabilities) capabilities.innerHTML = listMarkup(payload.top_capabilities || [], "capability", "tasks");
  } catch (error) {
    if (chart) chart.innerHTML = `<div class="empty-panel compact"><strong>Analytics unavailable</strong><p>${platformEsc(error.message)}</p></div>`;
  }
}

async function platformAdminLoad() {
  try {
    const [flags, overrides, webhooks, schedules, cache, audit] = await Promise.all([
      api("/api/admin/flags"),
      api("/api/admin/overrides"),
      api("/api/webhooks"),
      api("/api/schedules"),
      api("/api/cache"),
      api("/api/audit?limit=20"),
    ]);
    const flagsContainer = document.getElementById("admin-flags");
    if (flagsContainer) {
      flagsContainer.innerHTML = (flags.flags || [])
        .map(
          (flag) => `<label class="check-row list-row"><input type="checkbox" data-admin-flag="${platformEsc(flag.name)}" ${flag.enabled ? "checked" : ""}><span><strong>${platformEsc(flag.name)}</strong><small>${platformEsc(flag.description || "")}</small></span></label>`
        )
        .join("");
    }
    const overrideList = document.getElementById("admin-overrides");
    if (overrideList) {
      overrideList.innerHTML = (overrides.overrides || [])
        .map((row) => `<div class="list-row"><span><strong>${platformEsc(row.tool_id)}</strong><small>${platformEsc(row.field_name)} = ${platformEsc(row.value)}</small></span></div>`)
        .join("") || '<p class="small muted" style="padding:12px 0">No overrides.</p>';
    }
    const webhookList = document.getElementById("admin-webhooks");
    if (webhookList) {
      webhookList.innerHTML = (webhooks.webhooks || [])
        .map((hook) => `<div class="list-row"><span><strong>${platformEsc(hook.event)}</strong><small>${platformEsc(hook.url)}</small></span><button class="btn danger small" type="button" data-delete-webhook="${platformEsc(hook.webhook_id)}">Remove</button></div>`)
        .join("") || '<p class="small muted" style="padding:12px 0">No webhooks.</p>';
    }
    const scheduleList = document.getElementById("admin-schedules");
    if (scheduleList) {
      scheduleList.innerHTML = (schedules.schedules || [])
        .map((schedule) => `<div class="list-row"><span><strong>${platformEsc(schedule.task)}</strong><small>${platformEsc(schedule.cadence)} · next ${formatDateTime(schedule.next_run_at)}</small></span><button class="btn danger small" type="button" data-delete-schedule="${platformEsc(schedule.schedule_id)}">Remove</button></div>`)
        .join("") || '<p class="small muted" style="padding:12px 0">No schedules.</p>';
    }
    const cacheContainer = document.getElementById("admin-cache");
    if (cacheContainer) {
      cacheContainer.innerHTML = `<p class="small muted">${cache.entries || 0} cached result${Number(cache.entries) === 1 ? "" : "s"}. Automatic expiry is ${cache.ttl_seconds || 0} seconds.</p>`;
    }
    const auditContainer = document.getElementById("admin-audit");
    if (auditContainer) {
      auditContainer.innerHTML = (audit.entries || [])
        .map((entry) => `<div class="list-row"><span><strong>${platformEsc(entry.action)}</strong><small>${platformEsc(entry.detail || "")}</small></span><small>${formatDateTime(entry.created_at)}</small></div>`)
        .join("") || '<p class="small muted" style="padding:12px 0">No audit entries yet.</p>';
    }
    const toolSelect = document.getElementById("admin-override-tool");
    if (toolSelect && !toolSelect.options.length) {
      const toolsPayload = state?.tools?.length ? { tools: state.tools } : await api("/api/tools");
      toolSelect.innerHTML = (toolsPayload.tools || []).map((tool) => `<option value="${platformEsc(tool.id)}">${platformEsc(tool.name)}</option>`).join("");
    }
  } catch (error) {
    toast(`Admin data unavailable: ${error.message}`, "bad");
  }
}

function platformBindAdmin() {
  document.getElementById("admin-refresh")?.addEventListener("click", platformAdminLoad);
  document.getElementById("admin-flags")?.addEventListener("change", async (event) => {
    const checkbox = event.target.closest("[data-admin-flag]");
    if (!checkbox) return;
    try {
      await api(`/api/admin/flags/${encodeURIComponent(checkbox.dataset.adminFlag)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: checkbox.checked }),
      });
      toast("Feature updated.", "ok");
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      toast(`Could not update feature: ${error.message}`, "bad");
    }
  });
  document.getElementById("admin-override-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/admin/overrides", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_id: document.getElementById("admin-override-tool")?.value,
          field_name: document.getElementById("admin-override-field")?.value,
          value: document.getElementById("admin-override-value")?.value,
        }),
      });
      toast("Override saved.", "ok");
      await platformAdminLoad();
    } catch (error) {
      toast(`Could not save override: ${error.message}`, "bad");
    }
  });
  document.getElementById("admin-webhook-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/webhooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: document.getElementById("admin-webhook-url")?.value,
          event: document.getElementById("admin-webhook-event")?.value,
        }),
      });
      toast("Webhook added.", "ok");
      await platformAdminLoad();
    } catch (error) {
      toast(`Could not add webhook: ${error.message}`, "bad");
    }
  });
  document.getElementById("admin-schedule-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task: document.getElementById("admin-schedule-task")?.value,
          cadence: document.getElementById("admin-schedule-cadence")?.value,
        }),
      });
      toast("Schedule added.", "ok");
      await platformAdminLoad();
    } catch (error) {
      toast(`Could not add schedule: ${error.message}`, "bad");
    }
  });
  document.getElementById("admin-run-due")?.addEventListener("click", async () => {
    try {
      const payload = await api("/api/schedules/run-due", { method: "POST" });
      toast(`Ran ${payload.ran?.length || 0} scheduled task${payload.ran?.length === 1 ? "" : "s"}.`, "ok");
      await platformAdminLoad();
    } catch (error) {
      toast(`Could not run schedules: ${error.message}`, "bad");
    }
  });
  document.getElementById("admin-clear-cache")?.addEventListener("click", () => {
    platformConfirm("Clear cached results?", "New tasks will run fresh. This does not delete tasks, files or saved work.", async () => {
      try {
        const payload = await api("/api/cache", { method: "DELETE" });
        toast(`Cleared ${payload.cleared || 0} cached result${payload.cleared === 1 ? "" : "s"}.`, "ok");
        await platformAdminLoad();
      } catch (error) {
        toast(`Could not clear cache: ${error.message}`, "bad");
      }
    });
  });
  document.querySelector(".admin-page")?.addEventListener("click", async (event) => {
    const webhook = event.target.closest("[data-delete-webhook]");
    const schedule = event.target.closest("[data-delete-schedule]");
    try {
      if (webhook) {
        await api(`/api/webhooks/${encodeURIComponent(webhook.dataset.deleteWebhook)}`, { method: "DELETE" });
        await platformAdminLoad();
      } else if (schedule) {
        await api(`/api/schedules/${encodeURIComponent(schedule.dataset.deleteSchedule)}`, { method: "DELETE" });
        await platformAdminLoad();
      }
    } catch (error) {
      toast(`Could not remove item: ${error.message}`, "bad");
    }
  });
}

function platformConfirm(title, copy, action) {
  const titleElement = document.getElementById("confirm-title");
  const copyElement = document.getElementById("confirm-copy");
  if (titleElement) titleElement.textContent = title;
  if (copyElement) copyElement.textContent = copy;
  platformState.confirmAction = action;
  openModal("confirm-modal");
}

function platformBindConfirm() {
  document.getElementById("confirm-action")?.addEventListener("click", async () => {
    const action = platformState.confirmAction;
    platformState.confirmAction = null;
    closeModal(document.getElementById("confirm-modal"));
    if (action) await action();
  });
}

function platformBindDocumentDelete() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("#document-delete");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    platformConfirm(
      "Remove this file?",
      "The file and its extracted text will be removed from this workspace. You can upload it again later.",
      async () => {
        if (typeof deleteDocument === "function") await deleteDocument();
      }
    );
  }, true);
}

function platformBindDocuments() {
  platformBindDocumentDelete();
  const zone = document.getElementById("document-dropzone");
  const input = document.getElementById("document-file");
  const form = document.getElementById("upload-form");
  if (!zone || !input || !form) return;
  ["dragenter", "dragover"].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
    })
  );
  zone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    form.requestSubmit();
  });
  input.addEventListener("change", () => {
    const label = zone.querySelector("strong");
    if (label && input.files?.[0]) label.textContent = input.files[0].name;
  });
  form.addEventListener("submit", () => {
    const bar = document.getElementById("upload-progress");
    const fill = bar?.querySelector("span");
    if (!bar || !fill) return;
    bar.classList.remove("hidden", "is-done");
    bar.setAttribute("aria-valuenow", "15");
    fill.style.width = "15%";
    window.clearInterval(platformState.uploadTimer);
    let progress = 15;
    platformState.uploadTimer = window.setInterval(() => {
      progress = Math.min(85, progress + 9);
      fill.style.width = `${progress}%`;
      bar.setAttribute("aria-valuenow", String(progress));
    }, 220);
  });
  const result = document.getElementById("upload-result");
  if (result) {
    new MutationObserver(() => {
      if (result.classList.contains("hidden")) return;
      window.clearInterval(platformState.uploadTimer);
      const bar = document.getElementById("upload-progress");
      const fill = bar?.querySelector("span");
      if (fill) fill.style.width = "100%";
      if (bar) bar.setAttribute("aria-valuenow", "100");
      window.setTimeout(() => {
        const label = document.getElementById("document-dropzone")?.querySelector("strong");
        if (label) label.textContent = "Drop a file here or choose one";
        if (input) input.value = "";
      }, 900);
    }).observe(result, { attributes: true, attributeFilter: ["class"] });
  }
}

const PLATFORM_TOUR = [
  { title: "Ask in your own words", copy: "No menus or tool names needed. Describe the outcome and press Get answer." },
  { title: "See why the answer is trustworthy", copy: "Open How this was calculated to see each tool, input and check used for the answer." },
  { title: "Keep what matters", copy: "Save a task or workflow, then replay it later. Everything stays in your workspace." },
];

function platformShowTour(step = 0) {
  platformState.tourStep = step;
  const tour = document.getElementById("tour");
  if (!tour) return;
  tour.classList.remove("hidden");
  document.getElementById("tour-step").textContent = `Step ${step + 1} of ${PLATFORM_TOUR.length}`;
  document.getElementById("tour-title").textContent = PLATFORM_TOUR[step].title;
  document.getElementById("tour-copy").textContent = PLATFORM_TOUR[step].copy;
  document.getElementById("tour-next").textContent = step === PLATFORM_TOUR.length - 1 ? "Start asking" : "Next";
  document.getElementById("tour-next")?.focus();
}

function platformCloseTour() {
  document.getElementById("tour")?.classList.add("hidden");
  try {
    localStorage.setItem("agent-bazaar-tour-done", "1");
  } catch (error) {}
}

function platformBindTour() {
  if (document.body.dataset.page !== "dashboard") return;
  let seen = false;
  try {
    seen = localStorage.getItem("agent-bazaar-tour-done") === "1";
  } catch (error) {}
  if (!seen) window.setTimeout(() => platformShowTour(0), 900);
  document.getElementById("tour-next")?.addEventListener("click", () => {
    if (platformState.tourStep >= PLATFORM_TOUR.length - 1) {
      platformCloseTour();
      document.getElementById("task-input")?.focus();
      return;
    }
    platformShowTour(platformState.tourStep + 1);
  });
  document.getElementById("tour-skip")?.addEventListener("click", platformCloseTour);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.getElementById("tour")?.classList.contains("hidden")) platformCloseTour();
  });
}

function platformBindSwipe() {
  let startX = 0;
  let startY = 0;
  let startedAtEdge = false;
  document.addEventListener(
    "touchstart",
    (event) => {
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      startedAtEdge = startX < 32;
    },
    { passive: true }
  );
  document.addEventListener(
    "touchend",
    (event) => {
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = Math.abs(touch.clientY - startY);
      if (deltaY > 60 || Math.abs(deltaX) < 70) return;
      if (startedAtEdge && deltaX > 0 && !document.body.classList.contains("sidebar-open")) {
        document.getElementById("mobile-menu")?.click();
      } else if (deltaX < 0 && document.body.classList.contains("sidebar-open")) {
        document.getElementById("mobile-menu")?.click();
      }
    },
    { passive: true }
  );
}

function platformShowErrorBoundary(error) {
  const main = document.getElementById("console-content");
  if (!main) return;
  main.innerHTML = `<div class="error-boundary" role="alert">
    <div class="empty-panel">
      <svg><use href="#i-alert"></use></svg>
      <strong>Something went wrong</strong>
      <p>We could not finish loading this page. You can refresh or return to the start.</p>
      <div class="task-actions">
        <button class="btn primary" type="button" id="error-boundary-reload">Refresh page</button>
        <a class="btn secondary" href="/dashboard">Go to start</a>
      </div>
      <details class="calc-details"><summary>Technical details</summary><div>${platformEsc(error?.message || error || "Unknown error")}</div></details>
    </div>
  </div>`;
  document.getElementById("error-boundary-reload")?.addEventListener("click", () => window.location.reload());
}

function platformRouteFocus() {
  if (!document.referrer.startsWith(window.location.origin)) return;
  const main = document.getElementById("console-content");
  if (!main) return;
  main.setAttribute("tabindex", "-1");
  main.focus({ preventScroll: true });
}

function platformRunFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const taskId = params.get("task");
  const task = params.get("run");
  if (taskId) {
    window.setTimeout(() => loadTask(taskId), 250);
  } else if (task) {
    window.setTimeout(() => runTask(task), 350);
  }
}

function platformBindGlobal() {
  platformBindTheme();
  platformBindWorkspace();
  platformBindAuth();
  platformBindRecent();
  platformBindResult();
  platformBindShare();
  platformBindMarketplace();
  platformBindSettings();
  platformBindKeys();
  platformBindAdmin();
  platformBindConfirm();
  platformBindDocuments();
  platformBindTour();
  platformBindSwipe();
  document.addEventListener("platform:notifications", platformOpenNotifications);
  document.getElementById("mark-notifications-read")?.addEventListener("click", platformMarkNotificationsRead);
}

window.addEventListener("error", (event) => {
  platformShowErrorBoundary(event.error || event.message);
});

window.addEventListener("unhandledrejection", (event) => {
  platformShowErrorBoundary(event.reason);
});

async function platformBootstrap() {
  try {
    platformBindGlobal();
    await platformLoadMe();
    platformRouteFocus();
    const page = document.body.dataset.page;
    if (page === "dashboard") {
      await Promise.allSettled([platformLoadRecent(), platformRunFromQuery()]);
      if (typeof state !== "undefined" && state.result) {
        platformTaskActions();
        platformRenderCalculation();
      }
    }
    if (page === "settings") await platformRenderSettingsPage();
    if (page === "analytics") await platformRenderAnalytics();
    if (page === "admin") await platformAdminLoad();
  } catch (error) {
    platformShowErrorBoundary(error);
  }
}

document.addEventListener("DOMContentLoaded", platformBootstrap);
