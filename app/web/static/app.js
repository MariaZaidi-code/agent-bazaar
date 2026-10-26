const state = {
  page: window.__PAGE__ || document.body.dataset.page || "dashboard",
  health: null,
  healthError: null,
  tools: [],
  toolsLoading: true,
  toolsError: null,
  ontology: null,
  monitoring: null,
  monitoringError: null,
  result: null,
  documents: [],
  selectedDocument: "",
  documentDetail: null,
  documentAnswer: null,
  recent: [],
  monitorActivity: [],
  monitorDetails: [],
  monitorSelected: null,
  monitorPaused: false,
  monitorActivityError: null,
  monitoringFetchedAt: null,
  marketQuery: "",
  marketCapability: "all",
  marketSort: "trust",
  marketFilters: {
    free: false,
    keyless: false,
    executable: false,
    verifiable: false,
    incidents: false,
  },
  selectedTraceSeq: null,
  lastFocused: null,
  auditor: null,
  auditorError: null,
  auditorTrust: null,
  auditorTrustError: null,
  knowledge: null,
  knowledgeError: null,
  staged: null,
  stagedError: null,
  evaluations: null,
  evaluationsError: null,
  protocolTaskId: null,
  protocolMessages: null,
  protocolError: null,
  trustProvider: "",
  verifyTool: "",
  paletteIndex: 0,
  paletteItems: [],
  paletteRecent: [],
  paletteOpen: false,
  resetArmed: false,
  resetTimer: null,
};

const SAMPLES = [
  {
    label: "Weather + FX",
    text: "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?",
  },
  {
    label: "University SQL",
    text: "How many students are enrolled in the BS Artificial Intelligence program?",
  },
  {
    label: "Public holidays",
    text: "Which public holidays does Pakistan have in 2026?",
  },
  {
    label: "Country + research",
    text: "Compare the population of Japan and find recent research papers on GraphRAG.",
  },
  {
    label: "Document QA",
    text: "According to the uploaded document, what is the main goal of the project?",
  },
];

const CAPABILITY_ICONS = {
  GeocodeLocation: "map",
  GetWeatherForecast: "cloud",
  ConvertCurrency: "coins",
  GetCountryFacts: "map",
  GetPublicHolidays: "clock",
  SearchResearchPapers: "book",
  QueryStructuredData: "database",
  AnswerFromDocument: "file-text",
};

const TRACE_GROUPS = [
  {
    title: "Task intake",
    description: "Request normalization and decomposition",
    types: ["task_started", "task_decomposed"],
  },
  {
    title: "GraphRAG retrieval",
    description: "Candidate discovery and ontology filtering",
    types: ["graphrag_shortlist", "ontology_filtered"],
  },
  {
    title: "Claim verification",
    description: "Evidence labels and candidate ranking",
    types: ["claims_verified", "candidate_ranking", "trust_updated"],
  },
  {
    title: "Type-checked composition",
    description: "Link validation and execution planning",
    types: ["planning_finished", "chain_composed"],
  },
  {
    title: "Execution & recovery",
    description: "Provider calls, failures and substitution",
    types: [
      "step_started",
      "step_succeeded",
      "step_failed",
      "substitution_requested",
      "substitute_selected",
      "substitution_succeeded",
      "breaker_opened",
      "drift_detected",
      "task_completed",
    ],
  },
];

const TASK_DRAFTS = {
  GeocodeLocation: "Find the coordinates of Islamabad.",
  GetWeatherForecast: "What is the temperature in Lahore tomorrow?",
  ConvertCurrency: "What is 200 USD in PKR?",
  GetCountryFacts: "Compare the population of Japan and find recent research papers on GraphRAG.",
  GetPublicHolidays: "Which public holidays does Pakistan have in 2026?",
  SearchResearchPapers: "Find recent research papers on GraphRAG.",
  QueryStructuredData: "How many students are enrolled in the BS Artificial Intelligence program?",
  AnswerFromDocument: "According to the uploaded document, what is the main goal of the project?",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function icon(name, className = "") {
  return `<svg${className ? ` class="${className}"` : ""}><use href="#i-${name}"></use></svg>`;
}

function titleCase(value) {
  return String(value || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function tierBadge(tier) {
  const normalized = String(tier || "unknown").toLowerCase();
  const css = { free: "verified", freemium: "supported", paid: "contradicted" }[normalized] || "unsupported";
  return `<span class="badge ${css}">${esc(normalized)}</span>`;
}

function accessBadge(access) {
  const normalized = String(access || "unknown").toLowerCase();
  const css = normalized === "keyless" ? "neutral" : "contradicted";
  return `<span class="badge ${css}">${esc(normalized.replace(/_/g, " "))}</span>`;
}

function hasProfile(tool) {
  const tier = String(tool.pricing_tier || "unknown").toLowerCase();
  const access = String(tool.access_requirement || "unknown").toLowerCase();
  return tier !== "unknown" || access !== "unknown";
}

function executionReason(tool) {
  if (!hasProfile(tool) || tool.is_executable) return "";
  const tier = String(tool.pricing_tier || "unknown").toLowerCase();
  if (tier !== "free") return `not executable: ${tier} tier`;
  return "not executable: requires an api key";
}

function ratingLabel(tool) {
  const value = tool.rating_value;
  if (value === null || value === undefined) {
    return '<span class="muted">no ratings</span>';
  }
  const count = Number(tool.rating_count || 0);
  return `<span class="mono">rating ${Number(value).toFixed(2)}</span> <span class="muted">(${count} rating${count === 1 ? "" : "s"})</span>`;
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return esc(value ?? "-");
  return number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatTrust(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatTime(value) {
  if (!value) return "now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "now";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(value);
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatAge(value) {
  if (!value) return "not observed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(value);
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function truncate(value, length = 120) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function noticeMarkup(kind, title, detail = "") {
  const iconName = kind === "error" ? "x-circle" : kind === "warning" ? "alert" : "check-circle";
  return `<div class="notice ${esc(kind)}">${icon(iconName)}<span><strong>${esc(title)}</strong>${detail ? ` ${esc(detail)}` : ""}</span></div>`;
}

function emptyMarkup(title, detail, iconName = "layers") {
  return `<div class="empty-state inline">${icon(iconName)}<strong>${esc(title)}</strong><p>${esc(detail)}</p></div>`;
}

function scoreTrack(score, className = "") {
  const value = clamp(Number(score) * 100);
  return `<div class="trust-track ${esc(className)}"><span style="width:${value}%"></span></div>`;
}

function clamp(value, minimum = 0, maximum = 100) {
  return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function claimClass(label) {
  const normalized = String(label || "Unverified").toLowerCase();
  if (normalized === "unverified") return "neutral";
  return ["verified", "supported", "contradicted", "unsupported"].includes(normalized)
    ? normalized
    : "neutral";
}

function claimIcon(label) {
  const normalized = claimClass(label);
  if (normalized === "contradicted") return "x-circle";
  if (normalized === "unsupported") return "alert";
  if (normalized === "neutral") return "help";
  return "shield";
}

function claimBadge(label) {
  const normalized = claimClass(label);
  return `<span class="badge ${normalized}">${icon(claimIcon(label))}${esc(label || "Unverified")}</span>`;
}

function breakerClass(value) {
  const normalized = String(value || "closed").toLowerCase();
  return normalized === "half-open" || normalized === "half" ? "half-open" : normalized;
}

function breakerMarkup(value, withDot = true) {
  const normalized = breakerClass(value);
  const label = titleCase(normalized);
  const dotClass = normalized === "half-open" ? "half" : normalized;
  return `<span class="breaker-status ${normalized}">${withDot ? `<i class="dot ${dotClass}"></i>` : ""}<strong>${esc(label)}</strong></span>`;
}

function statusPill(status) {
  const normalized = String(status || "pending").toLowerCase();
  return `<span class="status-pill ${esc(normalized)}">${esc(titleCase(normalized))}</span>`;
}

function selectedClaim(result, step) {
  const list = (result.candidate_lists || []).find((group) => group.subgoal_id === step.subgoal_id);
  const candidate = (list?.candidates || []).find((entry) => entry.tool?.id === step.tool_id);
  return candidate?.claim_label || claimLabelForTool(step.tool_id);
}

function claimLabelForTool(toolId) {
  const tool = state.tools.find((entry) => entry.id === toolId);
  const labels = (tool?.claims || []).map((claim) => claim.label).filter(Boolean);
  return ["Contradicted", "Verified", "Supported", "Unsupported"].find((label) => labels.includes(label)) || "Unverified";
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload);
    } catch (error) {
      detail = await response.text();
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function toast(message, kind = "") {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.className = `toast ${kind}`.trim();
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => element.classList.add("hidden"), 4200);
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function currentTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  const normalized = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = normalized;
  try {
    localStorage.setItem("agent-bazaar-theme", normalized);
  } catch {}
  const meta = $("#theme-color-meta");
  if (meta) meta.setAttribute("content", normalized === "light" ? "#f5f3ee" : "#101113");
  $$("[data-set-theme]").forEach((button) => {
    const active = button.dataset.setTheme === normalized;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  const toggle = $("#toolbar-theme");
  if (toggle) {
    toggle.innerHTML = icon(normalized === "dark" ? "sun" : "moon");
    toggle.setAttribute("title", normalized === "dark" ? "Switch to light theme" : "Switch to dark theme");
  }
}

function toggleTheme() {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  state.lastFocused = document.activeElement;
  closePalette();
  $$(".modal.is-open").forEach((entry) => {
    if (entry !== modal) entry.classList.remove("is-open");
  });
  modal.classList.add("is-open");
  document.body.style.overflow = "hidden";
  if (id === "history-modal") loadHistory();
  if (id === "onboard-modal") resetOnboardState();
  const focusTarget = modal.querySelector("input, textarea, select, button");
  if (focusTarget) window.setTimeout(() => focusTarget.focus(), 40);
}

function closeModal(modal) {
  if (!modal) return;
  modal.classList.remove("is-open");
  if (!$(".modal.is-open")) document.body.style.overflow = "";
  if (state.lastFocused && typeof state.lastFocused.focus === "function") {
    state.lastFocused.focus();
  }
}

function closeAllModals() {
  const open = $(".modal.is-open");
  $$(".modal.is-open").forEach((modal) => modal.classList.remove("is-open"));
  document.body.style.overflow = "";
  if (open && state.lastFocused && typeof state.lastFocused.focus === "function") {
    state.lastFocused.focus();
  }
}

function trapModalFocus(event) {
  if (event.key !== "Tab") return;
  const modal = $(".modal.is-open");
  if (!modal) return;
  const focusable = $$(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    modal
  ).filter((element) => element.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function loadHealth() {
  return api("/api/health")
    .then((health) => {
      state.health = health;
      state.healthError = null;
      const date = new Date().toLocaleDateString([], { day: "2-digit", month: "short" });
      const chip = $("#demo-date");
      if (chip) {
        chip.textContent = `${health.mode === "offline" ? "Demo" : "Live"} · ${date}`;
        chip.title = `${health.tools} tools · ${health.llm_enabled ? "LLM planner" : "deterministic planner"}`;
      }
      return health;
    })
    .catch((error) => {
      state.healthError = error.message;
      state.health = null;
      const chip = $("#demo-date");
      if (chip) {
        chip.textContent = "Environment unknown";
        chip.title = error.message;
      }
      return null;
    });
}

function loadToolsData() {
  state.toolsLoading = true;
  return api("/api/tools")
    .then((data) => {
      state.tools = data.tools || [];
      state.toolsError = null;
      return state.tools;
    })
    .catch((error) => {
      state.toolsError = error.message;
      return state.tools;
    })
    .finally(() => {
      state.toolsLoading = false;
    });
}

function loadOntologyData() {
  return api("/api/ontology")
    .then((data) => {
      state.ontology = data;
      return data;
    })
    .catch((error) => {
      toast(`Ontology unavailable: ${error.message}`, "bad");
      return null;
    });
}

function loadMonitoringData() {
  return api("/api/monitoring")
    .then((data) => {
      state.monitoring = data;
      state.monitoringError = null;
      state.monitoringFetchedAt = new Date().toISOString();
      updateNotificationDot();
      return data;
    })
    .catch((error) => {
      state.monitoringError = error.message;
      updateNotificationDot();
      return state.monitoring;
    });
}

function loadAuditorData() {
  return Promise.allSettled([api("/api/auditor"), api("/api/auditor/trust")]).then(([overview, trust]) => {
    state.auditor = overview.status === "fulfilled" ? overview.value : null;
    state.auditorError = overview.status === "rejected" ? overview.reason.message : null;
    state.auditorTrust = trust.status === "fulfilled" ? trust.value : null;
    state.auditorTrustError = trust.status === "rejected" ? trust.reason.message : null;
    return state.auditor;
  });
}

function loadKnowledgeData() {
  return api("/api/knowledge")
    .then((data) => {
      state.knowledge = data;
      state.knowledgeError = null;
      return data;
    })
    .catch((error) => {
      state.knowledge = null;
      state.knowledgeError = error.message;
      return null;
    });
}

function loadStagedData() {
  return api("/api/staged")
    .then((data) => {
      state.staged = data;
      state.stagedError = null;
      return data;
    })
    .catch((error) => {
      state.staged = null;
      state.stagedError = error.message;
      return null;
    });
}

function loadEvaluationsData() {
  return api("/api/evaluations")
    .then((data) => {
      state.evaluations = data;
      state.evaluationsError = null;
      return data;
    })
    .catch((error) => {
      state.evaluations = null;
      state.evaluationsError = error.message;
      return null;
    });
}

function updateNotificationDot() {
  const dot = $("#notification-button .notification-dot");
  if (!dot) return;
  const alerts = state.monitoring?.drift_alerts || [];
  const open = (state.monitoring?.breakers || []).some((breaker) => breaker.state === "open");
  dot.classList.toggle("hidden", !state.monitoring || (!alerts.length && !open));
}

function providerForTool(toolId) {
  return (state.monitoring?.providers || []).find((provider) => provider.tool_id === toolId) || null;
}

function toolById(toolId) {
  return state.tools.find((tool) => tool.id === toolId) || null;
}

function capabilityIcon(capability) {
  return CAPABILITY_ICONS[capability] || "box";
}

function setActivePage() {
  $$("[data-nav]").forEach((item) => {
    const active = item.dataset.nav === state.page;
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  $$(".page-view").forEach((view) => {
    view.classList.toggle("is-active", view.dataset.view === state.page);
  });
}

function bindSidebar() {
  const menu = $("#mobile-menu");
  const sidebar = $("#sidebar");
  const mobileQuery = window.matchMedia("(max-width: 980px)");
  const setOpen = (open) => {
    const expanded = Boolean(open) && mobileQuery.matches;
    const activeInside = sidebar?.contains(document.activeElement);
    document.body.classList.toggle("sidebar-open", expanded);
    if (menu) {
      menu.setAttribute("aria-expanded", String(expanded));
      menu.setAttribute("aria-label", expanded ? "Close navigation" : "Open navigation");
    }
    if (sidebar) {
      if (mobileQuery.matches) {
        if (!expanded && activeInside) menu?.focus();
        sidebar.setAttribute("aria-hidden", String(!expanded));
        if (expanded) sidebar.removeAttribute("inert");
        else sidebar.setAttribute("inert", "");
      } else {
        sidebar.removeAttribute("aria-hidden");
        sidebar.removeAttribute("inert");
      }
    }
    if (expanded) {
      window.setTimeout(() => sidebar?.querySelector("a, button")?.focus(), 30);
    }
  };
  menu?.addEventListener("click", () => setOpen(!document.body.classList.contains("sidebar-open")));
  $("#sidebar-scrim")?.addEventListener("click", () => setOpen(false));
  $("#workspace-switcher")?.addEventListener("click", () => toast("This sandbox uses a single demo workspace."));
  $("#notification-button")?.addEventListener("click", () => {
    if (state.page === "monitor") {
      $("#alert-feed")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      window.location.href = "/monitor";
    }
  });
  $$("[data-nav]").forEach((item) => item.addEventListener("click", () => setOpen(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("sidebar-open")) {
      setOpen(false);
      menu?.focus();
    }
  });
  mobileQuery.addEventListener("change", () => setOpen(false));
  setOpen(false);
}

function bindTheme() {
  $$("[data-set-theme]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.setTheme));
  });
  $("#toolbar-theme")?.addEventListener("click", toggleTheme);
  applyTheme(currentTheme());
}

function bindModals() {
  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-open-modal]");
    if (opener) {
      event.preventDefault();
      openModal(opener.dataset.openModal);
      return;
    }
    const closer = event.target.closest("[data-close-modal]");
    if (closer) {
      event.preventDefault();
      closeModal(closer.closest(".modal"));
    }
  });
  document.addEventListener("keydown", (event) => {
    trapModalFocus(event);
    if (event.key === "Escape") closeAllModals();
  });
}

const PALETTE_NAV = [
  { title: "Workspace", subtitle: "Ask a question and inspect the answer", icon: "grid", href: "/dashboard" },
  { title: "Marketplace", subtitle: "Browse the service catalogue", icon: "box", href: "/marketplace" },
  { title: "Monitor", subtitle: "Failures, breakers and recovery", icon: "pulse", href: "/monitor" },
  { title: "Documents", subtitle: "Upload, preview and ask a document", icon: "file", href: "/documents" },
  { title: "Trust Center", subtitle: "Evidence, history and staging", icon: "shield", href: "/library" },
  { title: "Documentation", subtitle: "Guides, API reference and shortcuts", icon: "book", href: "/docs" },
];

function paletteAction(title, subtitle, iconName, run) {
  return { group: "Actions", title, subtitle, icon: iconName, run };
}

function buildPaletteItems(query) {
  const normalized = query.trim().toLowerCase();
  const matches = (...values) => !normalized || values.join(" ").toLowerCase().includes(normalized);
  const groups = [];

  const navigation = PALETTE_NAV.filter((entry) => matches(entry.title, entry.subtitle)).map((entry) => ({
    group: "Navigate",
    title: entry.title,
    subtitle: entry.subtitle,
    icon: entry.icon,
    run: () => {
      window.location.href = entry.href;
    },
  }));
  if (navigation.length) groups.push(...navigation);

  const actions = [
    paletteAction("Upload a document", "Open the Documents workspace", "upload", () => {
      window.location.href = "/documents";
    }),
    paletteAction("API reference", "Open the interactive endpoint reference", "terminal", () => {
      window.open("/api/docs", "_blank", "noopener");
    }),
    paletteAction("Onboard a tool", "Submit a listing for Mapper review", "plus", () => openModal("onboard-modal")),
    paletteAction("Execution history", "Reopen a previous run", "history", () => openModal("history-modal")),
    paletteAction("API & environment", "Endpoints and sandbox settings", "key", () => openModal("api-modal")),
    paletteAction("Toggle theme", "Switch between graphite and paper", "sun", () => toggleTheme()),
  ].filter((entry) => matches(entry.title, entry.subtitle));
  if (actions.length) groups.push(...actions);

  if (state.tools.length) {
    const toolMatches = state.tools
      .filter((tool) =>
        matches(
          tool.name,
          tool.id,
          tool.provider_id,
          tool.capability,
          tool.description,
          ...(tool.keywords || []),
          ...(tool.tags || []),
          ...(tool.inputs || []).map((input) => input.concept),
          ...(tool.outputs || []).map((output) => output.concept)
        )
      )
      .slice(0, 8)
      .map((tool) => ({
        group: "Tools",
        title: tool.name,
        subtitle: `${tool.capability} · ${tool.provider_id}`,
        icon: capabilityIcon(tool.capability),
        run: () => openToolModal(tool.id),
      }));
    groups.push(...toolMatches);
  }

  const conceptNames = (state.ontology?.concepts || []).map((concept) => concept.concept);
  const capabilities = Object.keys(state.ontology?.capabilities || capabilityCounts()).sort();
  const concepts = [...new Set(conceptNames)].filter((name) => matches(name)).slice(0, 5);
  const capabilityMatches = capabilities.filter((name) => matches(name)).slice(0, 4);
  if (normalized) {
    groups.push(
      ...concepts.map((name) => ({
        group: "Ontology",
        title: name,
        subtitle: "Search the marketplace for this concept",
        icon: "layers",
        run: () => {
          window.location.href = `/marketplace?q=${encodeURIComponent(name)}`;
        },
      })),
      ...capabilityMatches.map((name) => ({
        group: "Capabilities",
        title: name,
        subtitle: "Filter the marketplace by capability",
        icon: "filter",
        run: () => {
          window.location.href = `/marketplace?capability=${encodeURIComponent(name)}`;
        },
      }))
    );
  }

  if (normalized) {
    const runs = state.recent
      .filter((task) => matches(task.task, task.task_id, task.status))
      .slice(0, 5)
      .map((task) => ({
        group: "Recent runs",
        title: task.task,
        subtitle: `${titleCase(task.status)} · ${formatAge(task.created_at)}`,
        icon: "history",
        run: () => {
          if (state.page === "dashboard") {
            loadTask(task.task_id);
            window.history.replaceState(null, "", `/dashboard?task=${encodeURIComponent(task.task_id)}`);
          } else {
            window.location.href = `/dashboard?task=${encodeURIComponent(task.task_id)}`;
          }
        },
      }));
    groups.push(...runs);
  }

  return groups;
}

function renderPalette(query = "") {
  const container = $("#command-results");
  if (!container) return;
  const items = buildPaletteItems(query);
  state.paletteItems = items;
  state.paletteIndex = Math.min(state.paletteIndex, Math.max(0, items.length - 1));
  if (!items.length) {
    container.innerHTML = `<div class="palette-empty">No matches. Try a tool, capability, concept or page name.</div>`;
    return;
  }
  let index = 0;
  const sections = new Map();
  items.forEach((item) => {
    if (!sections.has(item.group)) sections.set(item.group, []);
    sections.get(item.group).push({ ...item, index: index++ });
  });
  container.innerHTML = [...sections.entries()]
    .map(
      ([group, entries]) => `<div class="palette-section">${esc(group)}</div>${entries
        .map(
          (entry) => `<button class="palette-item ${entry.index === state.paletteIndex ? "is-selected" : ""}" type="button" role="option" id="palette-item-${entry.index}" aria-selected="${entry.index === state.paletteIndex}" data-palette-index="${entry.index}">
            <span class="palette-icon">${icon(entry.icon)}</span>
            <span class="palette-item-copy"><strong>${esc(truncate(entry.title, 90))}</strong><small>${esc(truncate(entry.subtitle, 110))}</small></span>
            ${entry.hint ? `<kbd>${esc(entry.hint)}</kbd>` : ""}
          </button>`
        )
        .join("")}`
    )
    .join("");
  const input = $("#command-input");
  if (input) input.setAttribute("aria-activedescendant", `palette-item-${state.paletteIndex}`);
  selectPaletteItem(state.paletteIndex, false);
}

function selectPaletteItem(index, scroll = true) {
  if (!state.paletteItems.length) return;
  state.paletteIndex = (index + state.paletteItems.length) % state.paletteItems.length;
  $$("[data-palette-index]").forEach((button) => {
    const selected = Number(button.dataset.paletteIndex) === state.paletteIndex;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-selected", String(selected));
    if (selected && scroll) button.scrollIntoView({ block: "nearest" });
  });
  const input = $("#command-input");
  if (input) input.setAttribute("aria-activedescendant", `palette-item-${state.paletteIndex}`);
}

function openPalette() {
  const palette = $("#command-palette");
  if (!palette || state.paletteOpen) return;
  state.paletteOpen = true;
  state.paletteIndex = 0;
  state.lastFocused = document.activeElement;
  palette.classList.add("is-open");
  $$(".modal.is-open").forEach((modal) => modal.classList.remove("is-open"));
  document.body.style.overflow = "hidden";
  const input = $("#command-input");
  if (input) {
    input.value = "";
    input.setAttribute("aria-expanded", "true");
  }
  renderPalette("");
  window.setTimeout(() => input?.focus(), 20);
  if (!state.recent.length) {
    loadPaletteRecent().then(() => {
      if (state.paletteOpen) renderPalette($("#command-input")?.value || "");
    });
  }
}

function closePalette() {
  const palette = $("#command-palette");
  if (!palette || !state.paletteOpen) return;
  state.paletteOpen = false;
  palette.classList.remove("is-open");
  const input = $("#command-input");
  if (input) input.setAttribute("aria-expanded", "false");
  if (!$(".modal.is-open")) document.body.style.overflow = "";
  if (state.lastFocused && typeof state.lastFocused.focus === "function") state.lastFocused.focus();
}

function runPaletteItem(index) {
  const item = state.paletteItems[index];
  if (!item) return;
  closePalette();
  window.setTimeout(() => item.run(), 20);
}

async function loadPaletteRecent() {
  try {
    const data = await api("/api/tasks/recent?limit=6");
    state.recent = data.tasks || [];
  } catch {
    state.recent = state.recent || [];
  }
}

function bindPalette() {
  $("#command-trigger")?.addEventListener("click", openPalette);
  $("[data-close-palette]")?.addEventListener("click", closePalette);
  const input = $("#command-input");
  input?.addEventListener("input", () => {
    state.paletteIndex = 0;
    renderPalette(input.value);
  });
  input?.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      selectPaletteItem(state.paletteIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      selectPaletteItem(state.paletteIndex - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      runPaletteItem(state.paletteIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closePalette();
    }
  });
  $("#command-results")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-palette-index]");
    if (!button) return;
    runPaletteItem(Number(button.dataset.paletteIndex));
  });
  $("#command-results")?.addEventListener("mousemove", (event) => {
    const button = event.target.closest("[data-palette-index]");
    if (!button) return;
    const index = Number(button.dataset.paletteIndex);
    if (index !== state.paletteIndex) selectPaletteItem(index, false);
  });
  document.addEventListener("keydown", (event) => {
    const active = document.activeElement;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(active?.tagName) || active?.isContentEditable;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (state.paletteOpen) closePalette();
      else openPalette();
      return;
    }
    if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      if (state.page === "marketplace" && $("#market-search")) {
        $("#market-search").focus();
      } else if (!state.paletteOpen) {
        openPalette();
      }
    }
  });
}

function renderSamples() {
  const container = $("#sample-chips");
  if (!container) return;
  container.innerHTML = SAMPLES.map(
    (sample) => `<button type="button" data-sample="${esc(sample.text)}">${esc(sample.label)}</button>`
  ).join("");
  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sample]");
    if (!button) return;
    const input = $("#task-input");
    if (!input) return;
    input.value = button.dataset.sample;
    resizeTaskInput();
    runTask(button.dataset.sample);
  });
}

function resizeTaskInput() {
  const input = $("#task-input");
  if (!input) return;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function idleStepper() {
  const container = $("#execution-stepper");
  if (!container) return;
  const stages = [
    ["GraphRAG Shortlisting", "Candidate discovery across the marketplace"],
    ["Ontology Filtering", "Typed input/output compatibility gate"],
    ["Claim Verification", "Evidence labels before ranking"],
    ["Type-Checked Composition", "Link validation before execution"],
    ["Execution", "Provider calls with automatic recovery"],
  ];
  container.innerHTML = stages
    .map(
      ([title, summary]) => `<div class="exec-step queued">
        <div class="step-top"><span class="step-icon">${icon("terminal")}</span><span class="step-ms">standby</span></div>
        <strong>${esc(title)}</strong><small>${esc(summary)}</small><em>Queued</em>
      </div>`
    )
    .join("");
  const meta = $("#run-meta");
  if (meta) meta.innerHTML = `<span class="status-pill">${icon("terminal")}Ready</span><span>awaiting request</span>`;
  const empty = $("#answer-empty");
  const content = $("#answer-content");
  if (empty) empty.classList.remove("hidden");
  if (content) content.classList.add("hidden");
  const source = $("#source-count");
  if (source) {
    source.className = "badge neutral";
    source.innerHTML = `${icon("shield")}No sources yet`;
  }
  if ($("#trace-empty")) $("#trace-empty").classList.remove("hidden");
  if ($("#trace-layout")) $("#trace-layout").classList.add("hidden");
}

function loadingStepper() {
  const container = $("#execution-stepper");
  if (!container) return;
  const stages = [
    ["GraphRAG Shortlisting", "Resolving capabilities and candidates", "running"],
    ["Ontology Filtering", "Waiting for candidates", "queued"],
    ["Claim Verification", "Waiting for filtered tools", "queued"],
    ["Type-Checked Composition", "Waiting for verified tools", "queued"],
    ["Execution", "Provider calls queued", "queued"],
  ];
  container.innerHTML = stages
    .map(
      ([title, summary, status]) => `<div class="exec-step ${status}">
        <div class="step-top"><span class="step-icon">${icon(status === "running" ? "loader" : "terminal")}</span><span class="step-ms">pending</span></div>
        <strong>${esc(title)}</strong><small>${esc(summary)}</small><em>${status === "running" ? "Running" : "Queued"}</em>
      </div>`
    )
    .join("");
  const meta = $("#run-meta");
  if (meta) meta.innerHTML = `<span class="status-pill running">${icon("loader")}Running</span><span>live trace</span>`;
  const empty = $("#answer-empty");
  const content = $("#answer-content");
  if (empty) empty.classList.remove("hidden");
  if (content) content.classList.add("hidden");
  if ($("#trace-empty")) $("#trace-empty").classList.remove("hidden");
  if ($("#trace-layout")) $("#trace-layout").classList.add("hidden");
}

function stageData(result) {
  const steps = result.plan?.steps || [];
  const candidates = (result.candidate_lists || []).flatMap((group) => group.candidates || []);
  const eligible = candidates.filter((candidate) => candidate.eligible);
  const verified = candidates.filter((candidate) => ["Verified", "Supported"].includes(String(candidate.claim_label)));
  const links = steps.flatMap((step) => step.link_checks || []);
  const validLinks = links.filter((check) => check.valid);
  const completedSteps = steps.filter((step) => ["completed", "substituted"].includes(step.status));
  const substituted = steps.filter((step) => step.substituted_from);
  const filtered = (result.trace || []).some((event) => event.event_type === "graphrag_shortlist");
  const executionStatus =
    result.status === "completed" ? "completed" : result.status === "partial" ? "partial" : "failed";
  return [
    {
      title: "GraphRAG Shortlisting",
      summary: candidates.length
        ? `${candidates.length} candidates across ${result.candidate_lists?.length || 0} capabilities`
        : "No candidates retrieved",
      status: filtered || candidates.length ? "completed" : "failed",
      ms: result.metrics?.retrieval_ms,
    },
    {
      title: "Ontology Filtering",
      summary: `${eligible.length} / ${candidates.length} candidates passed typed filtering`,
      status: eligible.length ? "completed" : "failed",
      ms: null,
    },
    {
      title: "Claim Verification",
      summary: `${verified.length} evidence-backed candidates surviving`,
      status: validLinks.length || verified.length ? "completed" : "partial",
      ms: result.metrics?.verification_ms,
    },
    {
      title: "Type-Checked Composition",
      summary: result.plan?.valid
        ? `${validLinks.length} / ${links.length} links validated · plan accepted`
        : `${result.plan?.errors?.length || 0} composition error(s)`,
      status: result.plan?.valid ? "completed" : "failed",
      ms: result.metrics?.composition_ms,
    },
    {
      title: "Execution",
      summary: substituted.length
        ? `${completedSteps.length} / ${steps.length} calls · recovered via ${substituted.map((step) => step.tool_id).join(", ")}`
        : `${completedSteps.length} / ${steps.length} calls completed`,
      status: executionStatus,
      ms: result.metrics?.total_ms || result.duration_ms,
    },
  ];
}

function renderStepper(result) {
  const container = $("#execution-stepper");
  if (!container) return;
  container.innerHTML = stageData(result)
    .map((stage) => {
      const iconName =
        stage.status === "completed" ? "check" : stage.status === "running" ? "loader" : stage.status === "failed" ? "x" : "terminal";
      const statusLabel =
        stage.status === "completed" ? "Complete" : stage.status === "partial" ? "Partial" : stage.status === "running" ? "Running" : "Failed";
      return `<div class="exec-step ${stage.status}">
        <div class="step-top"><span class="step-icon">${icon(iconName)}</span><span class="step-ms">${stage.ms == null ? "" : `${formatNumber(stage.ms, 1)} ms`}</span></div>
        <strong>${esc(stage.title)}</strong><small>${esc(stage.summary)}</small><em>${esc(statusLabel)}</em>
      </div>`;
    })
    .join("");
}

function renderRunMeta(result) {
  const meta = $("#run-meta");
  if (!meta) return;
  meta.innerHTML = [
    statusPill(result.status),
    `<span>${esc(result.mode)}</span>`,
    `<span>${formatNumber(result.metrics?.total_ms || result.duration_ms, 1)} ms</span>`,
    `<span>${result.trace?.length || 0} events</span>`,
  ].join("");
}

function terminalSteps(result) {
  const steps = result.plan?.steps || [];
  const sources = new Set(
    steps.flatMap((step) => (step.link_checks || []).map((check) => check.source_step)).filter(Boolean)
  );
  const terminal = steps.filter((step) => !sources.has(step.id));
  return terminal.length ? terminal : steps;
}

function resultCard(step, result) {
  const capability = step.capability;
  const output = step.output || {};
  const claim = selectedClaim(result, step);
  const providerLabel = `${step.tool_name || step.tool_id || "Provider"}`;
  const commonCode = `${step.tool_id} · ${capability}`;
  let label = capability;
  let value = "Result";
  let suffix = "";
  let detail = "";
  let list = "";
  let iconName = capabilityIcon(capability);

  if (output.forecast) {
    const forecast = output.forecast;
    label = `Weather · ${forecast.location || "Forecast"}`;
    value = formatNumber(forecast.temp_max ?? forecast.temperature, 1);
    suffix = `°${forecast.unit || "C"}`;
    detail = `Low ${formatNumber(forecast.temp_min, 1)}° · ${formatNumber(forecast.precipitation_probability, 0)}% precipitation · ${esc(forecast.date || "")}`;
    iconName = "cloud";
  } else if (output.conversion) {
    const conversion = output.conversion;
    label = `Currency · ${conversion.from || ""} → ${conversion.to || conversion.currency || ""}`;
    value = formatNumber(conversion.amount, 2);
    suffix = conversion.currency || conversion.to || "";
    detail = `Rate ${formatNumber(conversion.rate, 4)} · ${esc(conversion.date || "")}${conversion.source ? ` · ${esc(conversion.source)}` : ""}`;
    iconName = "coins";
  } else if (output.country) {
    const country = output.country;
    label = `Country · ${country.name || "Facts"}`;
    value = formatNumber(country.population, 0);
    suffix = "people";
    detail = `Capital ${esc(country.capital || "-")} · ${esc(country.region || "-")} · ${esc((country.currencies || []).join(", ") || "-")}`;
    iconName = "map";
  } else if (Array.isArray(output.holidays)) {
    label = `Holidays · ${output.holidays[0]?.country_code || "Public calendar"}`;
    value = formatNumber(output.holidays.length, 0);
    suffix = "holidays";
    detail = output.holidays.slice(0, 4).map((holiday) => `${esc(holiday.name)} · ${esc(holiday.date)}`).join(" · ");
    iconName = "clock";
  } else if (Array.isArray(output.papers)) {
    label = "Research papers";
    value = formatNumber(output.papers.length, 0);
    suffix = "results";
    detail = output.papers.length ? "Retrieved from the arXiv research provider." : "No matching papers returned.";
    iconName = "book";
    list = output.papers
      .slice(0, 2)
      .map((paper) => `<li>${icon("file-text")}<span>${esc(paper.title)}${paper.url ? ` · <span class="mono">${esc(paper.url)}</span>` : ""}</span></li>`)
      .join("");
  } else if (output.table) {
    const table = output.table;
    const firstRow = table.rows?.[0] || {};
    const firstColumn = table.columns?.[0] || "result";
    label = `Database · ${table.row_count || 0} row(s)`;
    value = formatNumber(firstRow[firstColumn], 2);
    suffix = titleCase(firstColumn);
    detail = table.columns?.length > 1 ? `Columns: ${esc(table.columns.join(", "))}` : "Read-only SQL result";
    iconName = "database";
    list = table.sql ? `<li>${icon("terminal")}<span class="mono">${esc(table.sql)}</span></li>` : "";
  } else if (output.answer) {
    const answer = output.answer;
    label = "Document evidence";
    value = "Grounded";
    suffix = "answer";
    detail = answer.citations?.[0]?.quote ? `“${esc(answer.citations[0].quote)}”` : "Answer extracted from the uploaded document.";
    iconName = "file-text";
    list = (answer.citations || [])
      .slice(0, 2)
      .map((citation) => `<li>${icon("file-text")}<span>${esc(citation.name || citation.document_id)}</span></li>`)
      .join("");
  } else {
    const [key, raw] = Object.entries(output)[0] || [];
    if (key) {
      label = titleCase(key);
      value = typeof raw === "object" ? "Structured" : formatNumber(raw, 2);
      detail = `Returned by ${providerLabel}.`;
    }
  }

  return `<article class="result-data-card">
    <div class="result-data-head">${icon(iconName)}<span>${esc(label)}</span><span class="provider-pill">${esc(claim)}</span></div>
    <div class="result-value"><strong>${esc(value)}</strong><span>${esc(suffix)}</span></div>
    <p class="result-detail">${detail}</p>
    ${list ? `<ul class="result-list">${list}</ul>` : ""}
    <div class="result-code">${esc(commonCode)} · ${formatNumber(step.latency_ms, 1)} ms${step.cached ? " · cache hit" : ""}${step.substituted_from ? ` · substituted for ${esc(step.substituted_from)}` : ""}</div>
  </article>`;
}

function renderResult(result) {
  state.result = result;
  const empty = $("#answer-empty");
  const content = $("#answer-content");
  if (empty) empty.classList.add("hidden");
  if (content) content.classList.remove("hidden");
  const answerText = $("#answer-text");
  if (answerText) answerText.textContent = result.answer || "No answer returned.";
  const label = $(".answer-label");
  const substituted = (result.plan?.steps || []).some((step) => step.substituted_from);
  if (label) {
    label.textContent =
      result.status === "completed"
        ? substituted
          ? "Recovered response"
          : "Verified response"
        : result.status === "partial"
          ? "Partial response"
          : "Run failed";
  }
  const steps = terminalSteps(result);
  const cards = $("#result-cards");
  if (cards) {
    cards.style.gridTemplateColumns = steps.length === 1 ? "1fr" : "";
    cards.innerHTML = steps.map((step) => resultCard(step, result)).join("");
  }
  const evidenceCount = steps.filter((step) => ["Verified", "Supported"].includes(String(selectedClaim(result, step)))).length;
  const sourceCount = $("#source-count");
  if (sourceCount) {
    sourceCount.className = `badge ${evidenceCount ? "supported" : "neutral"}`;
    sourceCount.innerHTML = evidenceCount
      ? `${icon("shield")}${evidenceCount} evidence-backed source${evidenceCount === 1 ? "" : "s"}`
      : `${icon("alert")}No evidence-backed sources`;
  }
  const foot = $("#result-foot");
  if (foot) {
    const chips = steps.map(
      (step) => `<span class="source-chip">${icon("shield")}${esc(step.tool_name || step.tool_id)} · ${formatNumber(step.latency_ms, 1)} ms</span>`
    );
    if (result.status !== "completed") {
      chips.push(`<span class="source-chip">${icon("alert")}${esc(result.error || "Run requires attention")}</span>`);
    }
    (result.warnings || []).forEach((warning) => {
      chips.push(`<span class="source-chip">${icon("alert")}${esc(warning)}</span>`);
    });
    foot.innerHTML = chips.join("");
  }
  renderRunMeta(result);
  renderStepper(result);
  renderTrace(result.trace || []);
  const footerTask = $("#footer-task-id");
  if (footerTask) footerTask.textContent = ` · ${result.task_id}`;
}

function renderTrace(events) {
  const empty = $("#trace-empty");
  const layout = $("#trace-layout");
  if (!events.length) {
    empty?.classList.remove("hidden");
    layout?.classList.add("hidden");
    return;
  }
  empty?.classList.add("hidden");
  layout?.classList.remove("hidden");
  const grouped = TRACE_GROUPS.map((group) => ({
    ...group,
    events: events.filter((event) => group.types.includes(event.event_type)),
  }));
  const known = new Set(grouped.flatMap((group) => group.types));
  const remaining = events.filter((event) => !known.has(event.event_type));
  if (remaining.length) {
    grouped.push({
      title: "Other decisions",
      description: "Additional recorded agent activity",
      types: [],
      events: remaining,
    });
  }
  const activeGroups = grouped.filter((group) => group.events.length);
  const groupsContainer = $("#trace-groups");
  if (!groupsContainer) return;
  groupsContainer.innerHTML = activeGroups
    .map((group, index) => {
      const open = index === 0;
      return `<div class="trace-group ${open ? "is-open" : ""}" data-group-index="${index}">
        <button class="trace-group-head" type="button">
          ${icon("chevron-right")}
          <span><strong>${esc(group.title)}</strong><small>${esc(group.description)}</small></span>
          <em>${group.events.length}</em>
        </button>
        <div class="trace-events">
          ${group.events
            .map(
              (event) => `<button class="trace-event-button" type="button" data-trace-seq="${event.seq}">
                <code>#${event.seq}</code><span>${esc(event.event_type)}</span>
              </button>`
            )
            .join("")}
        </div>
      </div>`;
    })
    .join("");
  const first = activeGroups[0]?.events[0];
  if (first) selectTraceEvent(first.seq);
}

function selectTraceEvent(seq) {
  const event = (state.result?.trace || []).find((entry) => entry.seq === Number(seq));
  if (!event) return;
  state.selectedTraceSeq = event.seq;
  $$("[data-trace-seq]").forEach((button) => {
    button.classList.toggle("is-selected", Number(button.dataset.traceSeq) === event.seq);
  });
  const detail = $("#trace-detail");
  if (!detail) return;
  const data = Object.keys(event.data || {}).length ? JSON.stringify(event.data, null, 2) : "{}";
  detail.innerHTML = `<div class="trace-detail-head"><h3>${esc(event.event_type)}</h3><span class="badge neutral">${esc(event.actor)}</span></div>
    <p>${esc(event.summary)}</p>
    <pre>${esc(data)}</pre>
    <div class="trace-detail-foot">${icon("check-circle")}Recorded ${formatTime(event.timestamp)} · sequence ${event.seq}</div>`;
}

function bindTrace() {
  $("#trace-groups")?.addEventListener("click", (event) => {
    const eventButton = event.target.closest("[data-trace-seq]");
    if (eventButton) {
      selectTraceEvent(eventButton.dataset.traceSeq);
      return;
    }
    const head = event.target.closest(".trace-group-head");
    if (head) head.closest(".trace-group")?.classList.toggle("is-open");
  });
}

async function runTask(text) {
  const input = $("#task-input");
  const task = String(text || input?.value || "").trim();
  if (task.length < 3) {
    toast("Enter a task first.", "bad");
    return;
  }
  if (input) input.value = task;
  const button = $("#run-button");
  if (button) {
    button.disabled = true;
    button.innerHTML = `${icon("loader")}Running`;
  }
  loadingStepper();
  try {
    const result = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    renderResult(result);
    window.history.replaceState(null, "", `/dashboard?task=${encodeURIComponent(result.task_id)}`);
    loadProtocolMessages(result.task_id);
    const message =
      result.status === "completed"
        ? result.answer?.includes("substitute") || (result.plan?.steps || []).some((step) => step.substituted_from)
          ? "Chain self-healed with a compatible substitute."
          : "Verified chain completed."
        : result.status === "partial"
          ? "Chain partially completed. Inspect the trace."
          : "Chain failed. Inspect the trace for the reason.";
    toast(message, result.status === "completed" ? "ok" : result.status === "partial" ? "" : "bad");
    loadMonitoringData();
  } catch (error) {
    toast(`Task failed: ${error.message}`, "bad");
    idleStepper();
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = `${icon("play")}Run task`;
    }
  }
}

async function loadTask(taskId) {
  try {
    const result = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    renderResult(result);
    loadProtocolMessages(result.task_id);
  } catch (error) {
    toast(`Run unavailable: ${error.message}`, "bad");
  }
}

async function loadHistory() {
  const list = $("#history-list");
  if (!list) return;
  list.innerHTML = `<div class="empty-panel compact"><strong>Loading history</strong><p class="loading-dots"></p></div>`;
  try {
    const data = await api("/api/tasks/recent?limit=20");
    state.recent = data.tasks || [];
    list.innerHTML = state.recent.length
      ? state.recent
          .map(
            (task) => `<button class="history-item" type="button" data-history-task="${esc(task.task_id)}">
              <span><strong>${esc(task.task)}</strong><small>${esc(task.task_id)} · ${formatDateTime(task.created_at)} · ${esc(task.status)}</small></span>
              ${icon("chevron-right")}
            </button>`
          )
          .join("")
      : `<div class="empty-panel compact"><strong>No runs yet</strong><p>Run a task to build an execution history.</p></div>`;
  } catch (error) {
    list.innerHTML = `<div class="empty-panel compact"><strong>History unavailable</strong><p>${esc(error.message)}</p></div>`;
  }
}

function bindHistory() {
  $("#open-history")?.addEventListener("click", () => openModal("history-modal"));
  $("#history-list")?.addEventListener("click", async (event) => {
    const item = event.target.closest("[data-history-task]");
    if (!item) return;
    closeAllModals();
    await loadTask(item.dataset.historyTask);
    window.history.replaceState(null, "", `/dashboard?task=${encodeURIComponent(item.dataset.historyTask)}`);
  });
}

function exportResult() {
  if (!state.result) {
    toast("Run a task before exporting a trace.", "bad");
    return;
  }
  const blob = new Blob([JSON.stringify(state.result, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${state.result.task_id}.json`;
  link.click();
  URL.revokeObjectURL(url);
  toast("Trace exported as JSON.", "ok");
}

function renderWorkspaceStrip() {
  const container = $("#workspace-strip");
  if (!container) return;
  const providers = state.monitoring?.providers || [];
  const observed = providers.filter((provider) => Number(provider.calls || 0) + Number(provider.probes || 0) > 0);
  const trust = observed.length
    ? observed.reduce((total, provider) => total + Number(provider.trust || 0), 0) / observed.length
    : null;
  const open = (state.monitoring?.breakers || []).filter((breaker) => breaker.state === "open").length;
  const mapped = (state.auditor?.mappings || []).length;
  const toolsMetric = state.toolsLoading
    ? `<strong class="skeleton" style="width:54px;height:22px">&nbsp;</strong><small>Loading catalogue</small>`
    : state.toolsError
      ? `<strong>—</strong><small>Catalogue unavailable</small>`
      : `<strong>${state.tools.length}</strong><small>${new Set(state.tools.map((tool) => tool.capability)).size} capabilities</small>`;
  const trustMetric = !state.monitoring
    ? `<strong>—</strong><small>Monitoring unavailable</small>`
    : trust === null
      ? `<strong>—</strong><small>No observations yet</small>`
      : `<strong>${formatTrust(trust)}</strong><small>${observed.length} observed provider${observed.length === 1 ? "" : "s"}</small>`;
  const breakerMetric = !state.monitoring
    ? `<strong>—</strong><small>Monitoring unavailable</small>`
    : `<strong class="${open ? "alert" : ""}">${open}</strong><small>${(state.monitoring.breakers || []).length} links watched</small>`;
  const auditorMetric = state.auditorError
    ? `<strong>—</strong><small>Auditor unavailable</small>`
    : !state.auditor
      ? `<strong class="skeleton" style="width:80px;height:22px">&nbsp;</strong><small>Checking coverage</small>`
      : `<strong>${mapped}</strong><small>${esc(state.auditor.mode)} mode · ${state.auditor.catalog_tools} catalogue tools</small>`;
  container.innerHTML = `
    <div class="strip-metric"><span>Marketplace</span>${toolsMetric}</div>
    <div class="strip-metric"><span>Average trust</span>${trustMetric}</div>
    <div class="strip-metric"><span>Open circuits</span>${breakerMetric}</div>
    <div class="strip-metric"><span>Auditor</span>${auditorMetric}</div>`;
}

function initDashboard() {
  renderWorkspaceStrip();
  renderSamples();
  bindHistory();
  $("#export-json")?.addEventListener("click", exportResult);
  const form = $("#task-form");
  const input = $("#task-input");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    runTask(input?.value);
  });
  input?.addEventListener("input", resizeTaskInput);
  input?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      form?.requestSubmit();
    }
  });
  const draft = (() => {
    try {
      return localStorage.getItem("agent-bazaar-task");
    } catch (error) {
      return null;
    }
  })();
  if (draft && input) {
    input.value = draft;
    resizeTaskInput();
    try {
      localStorage.removeItem("agent-bazaar-task");
    } catch (error) {
      return;
    }
  }
  const taskId = new URLSearchParams(window.location.search).get("task");
  if (taskId) loadTask(taskId);
  else idleStepper();
}

function catalogueStats() {
  const tools = state.tools;
  const breakers = state.monitoring?.breakers || [];
  const providers = state.monitoring?.providers || [];
  const open = breakers.filter((breaker) => breaker.state === "open").length;
  const half = breakers.filter((breaker) => breaker.state === "half-open").length;
  const closed = breakers.length ? Math.max(0, breakers.length - open - half) : null;
  const observed = providers.filter((provider) => Number(provider.calls || 0) + Number(provider.probes || 0) > 0);
  const trust = observed.length
    ? observed.reduce((total, provider) => total + Number(provider.trust || 0), 0) / observed.length
    : null;
  const monitoringMissing = !state.monitoring;
  return `
    <div class="catalogue-stat"><strong>${state.toolsLoading ? "—" : tools.length}</strong><span>Registered<br>services</span></div>
    <div class="catalogue-stat closed"><strong>${closed === null ? "—" : closed}</strong><span>Closed<br>circuits</span></div>
    <div class="catalogue-stat ${open ? "open" : "closed"}"><strong>${monitoringMissing ? "—" : open}</strong><span>Open<br>circuits</span></div>
    <div class="catalogue-stat"><strong>${trust === null ? "—" : formatTrust(trust)}</strong><span>${monitoringMissing ? "Monitoring unavailable" : observed.length ? `Average of ${observed.length} observed` : "No observations yet"}</span></div>`;
}

function capabilityCounts() {
  return state.tools.reduce((counts, tool) => {
    counts[tool.capability] = (counts[tool.capability] || 0) + 1;
    return counts;
  }, {});
}

function renderCapabilityControls() {
  const capabilities = Object.keys(state.ontology?.capabilities || capabilityCounts()).sort();
  const select = $("#capability-filter");
  if (select) {
    select.innerHTML = `<option value="all">All capabilities</option>${capabilities
      .map((capability) => `<option value="${esc(capability)}">${esc(capability)}</option>`)
      .join("")}`;
    select.value = state.marketCapability;
  }
  const counts = capabilityCounts();
  const chips = $("#market-filters");
  if (chips) {
    chips.innerHTML = [
      `<button class="chip ${state.marketCapability === "all" ? "active" : ""}" type="button" data-capability="all">All tools · ${state.tools.length}${state.marketCapability === "all" ? icon("check") : ""}</button>`,
      ...capabilities.map(
        (capability) => `<button class="chip ${state.marketCapability === capability ? "active" : ""}" type="button" data-capability="${esc(capability)}">${esc(capability)} · ${counts[capability] || 0}${state.marketCapability === capability ? icon("check") : ""}</button>`
      ),
    ].join("");
  }
  $$("[data-tool-filter]").forEach((button) => {
    button.classList.toggle("is-active", Boolean(state.marketFilters[button.dataset.toolFilter]));
  });
}

function mappedToolIds() {
  return new Set((state.auditor?.mappings || []).map((mapping) => mapping.app_tool_id));
}

function filteredTools() {
  const query = state.marketQuery.trim().toLowerCase();
  const mapped = mappedToolIds();
  const breakerByProvider = new Map((state.monitoring?.breakers || []).map((breaker) => [breaker.key.split("->").pop(), breaker.state]));
  return state.tools
    .filter((tool) => {
      if (state.marketCapability !== "all" && tool.capability !== state.marketCapability) return false;
      if (state.marketFilters.free && String(tool.pricing_tier || "").toLowerCase() !== "free") return false;
      if (state.marketFilters.keyless && String(tool.access_requirement || "").toLowerCase() !== "keyless") return false;
      if (state.marketFilters.executable && !tool.is_executable) return false;
      if (state.marketFilters.verifiable && !mapped.has(tool.id)) return false;
      if (state.marketFilters.incidents) {
        const stateValue = breakerByProvider.get(tool.provider_id) || tool.breaker || "closed";
        if (!["open", "half-open"].includes(breakerClass(stateValue))) return false;
      }
      if (!query) return true;
      return [
        tool.name,
        tool.id,
        tool.provider_id,
        tool.description,
        tool.capability,
        ...(tool.keywords || []),
        ...(tool.tags || []),
        ...(tool.inputs || []).map((input) => input.concept),
        ...(tool.outputs || []).map((output) => output.concept),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .sort((left, right) => {
      if (state.marketSort === "name") return left.name.localeCompare(right.name);
      if (state.marketSort === "capability") return left.capability.localeCompare(right.capability);
      if (state.marketSort === "tier") {
        const rank = { free: 0, freemium: 1, paid: 2, unknown: 3 };
        const delta =
          (rank[String(left.pricing_tier || "unknown").toLowerCase()] ?? 3) -
          (rank[String(right.pricing_tier || "unknown").toLowerCase()] ?? 3);
        if (delta !== 0) return delta;
      }
      return Number(right.trust || 0) - Number(left.trust || 0);
    });
}

function toolCard(tool) {
  const provider = providerForTool(tool.id);
  const claim = claimLabelForTool(tool.id);
  const breaker = breakerClass(tool.breaker || "closed");
  const trust = Number(tool.trust ?? 0.5);
  const calls = Number(provider?.calls || 0);
  const probes = Number(provider?.probes || 0);
  const contradictions = Number(provider?.contradictions || 0);
  const observed = calls + probes > 0;
  const reason = executionReason(tool);
  const quality = Number(tool.doc_quality || 0);
  const coverage = Number(tool.mapping_coverage || 0);
  const mapping = auditorMapping(tool.id);
  const schema = `${(tool.inputs || []).map((input) => input.concept).join(" + ") || "No inputs"} → ${(tool.outputs || []).map((output) => output.concept).join(" + ") || "No outputs"}`;
  const priceLabel = tool.price ? `$${formatNumber(tool.price, 2)}` : titleCase(tool.pricing_tier || "unknown");
  return `<article class="window-card tool-card ${esc(breaker)}" data-tool-id="${esc(tool.id)}" tabindex="0" role="button" aria-label="Inspect ${esc(tool.name)}">
    <div class="mini-window-bar"><span>service / ${esc(tool.provider_id)}</span><span><i></i><i></i><i></i></span></div>
    <div class="window-body">
      <div class="tool-card-heading">
        <span class="tool-icon">${icon(capabilityIcon(tool.capability))}</span>
        <span class="tool-title"><strong>${esc(tool.name)}</strong><small>${esc(tool.capability)}</small></span>
        ${icon("arrow-up-right")}
      </div>
      <p class="tool-description">${esc(tool.description)}</p>
      <div class="tool-claim-row">${claimBadge(claim)}${mapping ? `<span class="badge neutral" title="Auditor catalogue mapping: ${esc(mapping.catalog_tool_id)}">${icon("shield")}Auditor mapped</span>` : ""}<span class="tool-probe">${probes} probe${probes === 1 ? "" : "s"} · ${calls} call${calls === 1 ? "" : "s"}</span></div>
      <div class="tool-offering-row">
        ${tierBadge(tool.pricing_tier)}
        ${accessBadge(tool.access_requirement)}
        ${reason ? `<span class="badge contradicted">${esc(reason)}</span>` : ""}
      </div>
      <div class="tool-offering-meta">
        ${ratingLabel(tool)}
        <span class="mono">docs ${quality.toFixed(2)} · coverage ${coverage.toFixed(2)}</span>
      </div>
      <div>
        <div class="trust-label-row"><span>${observed ? "Live trust score" : "Default prior"}</span><strong>${formatTrust(trust)}</strong></div>
        <div class="trust-track ${breaker === "half-open" ? "half" : breaker}"><span style="width:${clamp(trust * 100)}%"></span></div>
        <div class="trust-counts">${observed ? `${calls} call${calls === 1 ? "" : "s"} · ${contradictions} contradiction${contradictions === 1 ? "" : "s"}` : "No calls or probes yet"} · ${esc(priceLabel)}</div>
      </div>
      <div class="breaker-line"><span>Circuit breaker</span>${breakerMarkup(breaker)}</div>
      <div class="tool-code">${esc(schema)}</div>
    </div>
  </article>`;
}

function setMarketNotice(kind, title, detail = "", retry = false) {
  const container = $("#market-notice");
  if (!container) return;
  if (!kind) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }
  container.classList.remove("hidden");
  container.innerHTML = `<div class="notice ${esc(kind)}">${icon(kind === "error" ? "x-circle" : "alert")}<span><strong>${esc(title)}</strong>${detail ? ` ${esc(detail)}` : ""}${retry ? ` <button class="text-button" type="button" id="market-retry">Retry</button>` : ""}</span></div>`;
  $("#market-retry")?.addEventListener("click", async () => {
    setMarketNotice(null);
    $("#tools-loading")?.classList.remove("hidden");
    await loadToolsData();
    renderMarketplace();
  });
}

function updateMarketQueryUrl() {
  const params = new URLSearchParams();
  if (state.marketCapability !== "all") params.set("capability", state.marketCapability);
  if (state.marketQuery.trim()) params.set("q", state.marketQuery.trim());
  const next = params.toString() ? `/marketplace?${params}` : "/marketplace";
  window.history.replaceState(null, "", next);
}

function renderMarketplace() {
  const stats = $("#catalogue-stats");
  if (stats) stats.innerHTML = catalogueStats();
  renderCapabilityControls();
  const grid = $("#tools-grid");
  const empty = $("#tools-empty");
  const loading = $("#tools-loading");
  const tools = filteredTools();
  if (loading) loading.classList.toggle("hidden", !state.toolsLoading);
  if (state.toolsError) {
    setMarketNotice("error", "Catalogue unavailable.", state.toolsError, true);
    if (grid) grid.innerHTML = "";
    empty?.classList.add("hidden");
  } else {
    setMarketNotice(null);
    if (grid) grid.innerHTML = state.toolsLoading ? "" : tools.map(toolCard).join("");
    empty?.classList.toggle("hidden", state.toolsLoading || tools.length > 0);
    if (empty) {
      const emptyTitle = $("strong", empty);
      const emptyCopy = $("p", empty);
      if (emptyTitle) emptyTitle.textContent = state.tools.length ? "No tools match" : "Catalogue is empty";
      if (emptyCopy) {
        emptyCopy.textContent = state.tools.length
          ? "Change the search or filter to inspect the rest of the catalogue."
          : "No tools are registered in this sandbox yet.";
      }
    }
  }
  const footerCount = $("#market-footer-count");
  if (footerCount) footerCount.textContent = `${tools.length} of ${state.tools.length}`;
  const sync = $("#market-sync-time");
  if (sync) sync.textContent = state.toolsError ? "unavailable" : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function initMarketplace() {
  const params = new URLSearchParams(window.location.search);
  const capability = params.get("capability");
  state.marketCapability = capability || "all";
  state.marketQuery = params.get("q") || "";
  const search = $("#market-search");
  if (search) {
    search.value = state.marketQuery;
    search.addEventListener("input", () => {
      state.marketQuery = search.value;
      updateMarketQueryUrl();
      renderMarketplace();
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
      if (event.key === "Escape") {
        search.value = "";
        state.marketQuery = "";
        updateMarketQueryUrl();
        renderMarketplace();
      }
    });
  }
  $("#capability-filter")?.addEventListener("change", (event) => {
    state.marketCapability = event.target.value;
    updateMarketQueryUrl();
    renderMarketplace();
  });
  $("#sort-filter")?.addEventListener("change", (event) => {
    state.marketSort = event.target.value;
    renderMarketplace();
  });
  $("#market-filters")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-capability]");
    if (!chip) return;
    state.marketCapability = chip.dataset.capability;
    updateMarketQueryUrl();
    renderMarketplace();
  });
  $("#market-advanced")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-tool-filter]");
    if (!chip) return;
    state.marketFilters[chip.dataset.toolFilter] = !state.marketFilters[chip.dataset.toolFilter];
    renderMarketplace();
  });
  $("#clear-tool-filters")?.addEventListener("click", () => {
    Object.keys(state.marketFilters).forEach((key) => {
      state.marketFilters[key] = false;
    });
    renderMarketplace();
  });
  $("#tools-grid")?.addEventListener("click", (event) => {
    const card = event.target.closest("[data-tool-id]");
    if (card) openToolModal(card.dataset.toolId);
  });
  $("#tools-grid")?.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const card = event.target.closest("[data-tool-id]");
    if (!card) return;
    event.preventDefault();
    openToolModal(card.dataset.toolId);
  });
  $("#onboard-button")?.addEventListener("click", () => openModal("onboard-modal"));
  renderMarketplace();
}

function schemaLines(items, emptyLabel) {
  if (!items?.length) return `<div class="schema-line"><span>${esc(emptyLabel)}</span><span>—</span></div>`;
  return items
    .map(
      (item) => `<div class="schema-line"><span>${esc(item.name || titleCase(item.concept))}</span><span>${esc(item.concept)}${item.unit ? ` · ${esc(item.unit)}` : ""}${item.datatype ? ` · ${esc(item.datatype)}` : ""}${item.required === false ? " · optional" : ""}</span></div>`
    )
    .join("");
}

function ontologyConceptOptions(selected, fallback = []) {
  const names = (state.ontology?.concepts || []).map((concept) => concept.concept);
  const pool = [...new Set([...names, ...fallback].filter(Boolean))].sort();
  return pool
    .map((name) => `<option value="${esc(name)}"${name === selected ? " selected" : ""}>${esc(name)}</option>`)
    .join("");
}

function auditorMapping(toolId) {
  return (state.auditor?.mappings || []).find((mapping) => mapping.app_tool_id === toolId) || null;
}

function auditorResultMarkup(payload, mode = "verify") {
  if (!payload) return "";
  const assessments = payload.assessments || [];
  const labels = assessments.length
    ? assessments
    : (payload.app_labels || []).map((entry) => ({ claim: { text: entry.claim }, label: entry.label, rationale: entry.evidence }));
  const counts = labels.reduce((result, entry) => {
    const label = String(entry.label || "Unsupported");
    result[label] = (result[label] || 0) + 1;
    return result;
  }, {});
  const overall =
    payload.app_overall ||
    ["Contradicted", "Unsupported", "Supported", "Verified"].find((label) => counts[label]) ||
    "Unverified";
  const coverage = payload.coverage || {};
  const source = payload.probe_source || "none";
  const alerts = payload.drift_alerts?.length || payload.alerts?.length || 0;
  const status = payload.probe_valid === false ? "Probe payload invalid" : payload.probe_status_code ? `HTTP ${payload.probe_status_code}` : "No probe status";
  const rows = labels
    .slice(0, 5)
    .map(
      (entry) => `<div class="assessment">
        ${icon(claimIcon(entry.label))}
        <div><strong>${esc(truncate(entry.claim?.text || entry.claim || "Claim", 110))}</strong><small>${esc(entry.label || "Unverified")} · ${esc(truncate(entry.rationale || entry.evidence || "No rationale returned.", 180))}</small></div>
      </div>`
    )
    .join("");
  return `<div class="auditor-summary">
      <div class="auditor-summary-top">
        ${claimBadge(overall)}
        <span class="badge neutral">${esc(mode === "monitor" ? "Monitor pass" : "Verification")}</span>
        <span class="badge neutral">${esc(source)} probe</span>
        ${alerts ? `<span class="badge contradicted">${icon("alert")}${alerts} drift</span>` : ""}
      </div>
      <p class="small muted">${esc(status)} · ${esc(formatNumber(payload.duration_ms || 0, 1))} ms · ${esc(formatNumber(coverage.coverage_percent || 0, 0))}% claim coverage · ${esc(formatNumber(coverage.probeable_coverage_percent || 0, 0))}% probeable coverage</p>
      ${rows || `<p class="small muted">No claim assessments were returned.</p>`}
      ${payload.notes?.length ? `<details><summary>${payload.notes.length} Auditor note${payload.notes.length === 1 ? "" : "s"}</summary><pre>${esc(payload.notes.join("\n"))}</pre></details>` : ""}
    </div>`;
}

async function runToolAuditor(toolId, mode) {
  const output = $("#tool-auditor-result");
  if (!output) return;
  const live = Boolean($("#tool-force-live")?.checked);
  const buttons = $$("[data-auditor-action]");
  buttons.forEach((button) => {
    button.disabled = true;
  });
  output.classList.remove("hidden", "bad", "pending");
  output.classList.add("pending");
  output.innerHTML = `<span class="loading-line">${icon("loader")}Running ${mode} for <code>${esc(toolId)}</code>…</span>`;
  try {
    const path = mode === "monitor" ? `/api/auditor/monitor/${encodeURIComponent(toolId)}` : `/api/auditor/verify/${encodeURIComponent(toolId)}`;
    const payload = await api(`${path}?live=${live ? "true" : "false"}`, { method: "POST" });
    output.classList.remove("pending");
    output.innerHTML = auditorResultMarkup(payload, mode);
    toast(`${mode === "monitor" ? "Monitor pass" : "Verification"} complete for ${toolId}.`, "ok");
    await Promise.allSettled([loadAuditorData(), loadMonitoringData()]);
    if ($("#trust-metrics")) renderTrustCenterData();
    if ($("#monitor-metrics")) renderMonitor();
  } catch (error) {
    output.classList.remove("pending");
    output.classList.add("bad");
    output.textContent = error.message;
    toast(`Auditor ${mode} failed: ${error.message}`, "bad");
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
}

function openToolModal(toolId) {
  const tool = toolById(toolId);
  if (!tool) {
    toast("This tool is not in the loaded catalogue.", "bad");
    return;
  }
  const provider = providerForTool(tool.id);
  const claim = claimLabelForTool(tool.id);
  const breaker = breakerClass(tool.breaker || "closed");
  const reason = executionReason(tool);
  const mapping = auditorMapping(tool.id);
  const fields = [
    ...(tool.inputs || []).map((entry) => ({ ...entry, direction: "input" })),
    ...(tool.outputs || []).map((entry) => ({ ...entry, direction: "output" })),
  ];
  const conceptFallback = fields.map((entry) => entry.concept).filter(Boolean);
  const route = $("#tool-modal-route");
  if (route) route.textContent = `service / ${tool.id}`;
  const body = $("#tool-modal-body");
  if (!body) return;
  body.innerHTML = `<div class="tool-modal-top">
      <span class="tool-icon">${icon(capabilityIcon(tool.capability))}</span>
      <div><h2 id="tool-modal-title">${esc(tool.name)}</h2><p>${esc(tool.provider_id)} · ${esc(tool.capability)} · ${esc(tool.execution)}</p></div>
    </div>
    <div class="detail-grid">
      <div class="detail-block"><span>Live trust</span><strong>${formatTrust(tool.trust)}</strong><small>${provider?.calls || 0} calls · ${provider?.probes || 0} probes · ${provider?.contradictions || 0} contradictions</small></div>
      <div class="detail-block"><span>Circuit breaker</span><strong>${titleCase(breaker)}</strong><small>${provider?.failure_mode ? `failure mode: ${esc(provider.failure_mode)}` : "link-level isolation"}</small></div>
      <div class="detail-block"><span>Evidence label</span><strong>${claim}</strong><small>${tool.claims?.length || 0} provider claim${tool.claims?.length === 1 ? "" : "s"} on record</small></div>
      <div class="detail-block"><span>Pricing &amp; access</span><strong>${esc(titleCase(tool.pricing_tier || "unknown"))} · ${esc(titleCase(tool.access_requirement || "unknown"))}</strong><small>${tool.price ? `$${formatNumber(tool.price, 2)}` : "No listed price"} · ${esc((tool.tags || []).join(" · ") || "No tags")}</small></div>
      <div class="detail-block"><span>Quality</span><strong>${tool.rating_value === null || tool.rating_value === undefined ? "No ratings" : `${Number(tool.rating_value).toFixed(2)} / 5`}</strong><small>${Number(tool.rating_count || 0)} rating${Number(tool.rating_count || 0) === 1 ? "" : "s"} · docs ${Number(tool.doc_quality || 0).toFixed(2)} · mapping ${Number(tool.mapping_coverage || 0).toFixed(2)}</small></div>
      <div class="detail-block"><span>Execution</span><strong>${tool.is_executable ? "Executable" : "Not executable"}</strong><small>${esc(reason || "Free and keyless: the Client may call this tool.")}</small></div>
    </div>
    <div class="claim-list">
      ${(tool.claims || [])
        .map(
          (holder) => `<div class="claim-card">${claimBadge(holder.label)}<div><strong>${esc(holder.text)}</strong><small>${esc(holder.evidence || "No evidence recorded.")}</small></div></div>`
        )
        .join("") || `<div class="claim-card"><div><strong>No provider claims</strong><small>Registration does not confer Verified status.</small></div></div>`}
    </div>
    <div class="schema-block"><h3>Inputs</h3>${schemaLines(tool.inputs, "No inputs")}</div>
    <div class="schema-block"><h3>Outputs</h3>${schemaLines(tool.outputs, "No outputs")}</div>
    <div class="auditor-block">
      <div class="auditor-block-head"><strong>${icon("shield")}Auditor verification</strong>${mapping ? `<span class="badge neutral">Mapped</span>` : `<span class="badge neutral">Not mapped</span>`}</div>
      ${
        mapping
          ? `<p class="small muted" style="margin:0">Catalogue target <code>${esc(mapping.catalog_tool_id)}</code>. Verification always establishes a fresh baseline; fixture probes are labelled as fixtures.</p>
            <div class="auditor-block-actions">
              <button class="btn small secondary" type="button" data-auditor-action="verify" data-auditor-tool="${esc(tool.id)}">${icon("shield")}Verify now</button>
              <button class="btn small secondary" type="button" data-auditor-action="monitor" data-auditor-tool="${esc(tool.id)}">${icon("pulse")}Monitor only</button>
              <label class="auditor-live-option"><input id="tool-force-live" type="checkbox"> Force live network</label>
            </div>
            <div class="inline-result hidden" id="tool-auditor-result" role="status" aria-live="polite"></div>`
          : `<p class="small muted" style="margin:0">The Auditor has no catalogue mapping for this tool, so it cannot produce claim-level evidence here. <a class="text-link" href="/library">Open the Trust Center</a> to inspect mapped tools.</p>`
      }
    </div>
    ${
      fields.length
        ? `<details class="correction-details">
            <summary>Suggest an ontology correction</summary>
            <form class="correction-form" id="tool-correction-form" data-tool-id="${esc(tool.id)}">
              <div class="form-grid">
                <label>Field<select id="correction-field">${fields
                  .map(
                    (entry, index) => `<option value="${esc(entry.name || entry.concept)}" data-concept="${esc(entry.concept || "")}" data-unit="${esc(entry.unit || "")}"${index === 0 ? " selected" : ""}>${esc(entry.direction)} · ${esc(entry.name || entry.concept)} (${esc(entry.concept || "untyped")})</option>`
                  )
                  .join("")}</select></label>
                <label>Corrected ontology concept<select id="correction-concept" required>${ontologyConceptOptions(fields[0]?.concept, conceptFallback)}</select></label>
                <label>Unit<input id="correction-unit" value="${esc(fields[0]?.unit || "")}" placeholder="C"></label>
                <label>Note<input id="correction-note" placeholder="Why should the mapping change?"></label>
              </div>
              <button class="btn secondary small" type="submit">Submit correction</button>
              <div class="inline-result hidden" id="tool-correction-result"></div>
            </form>
          </details>`
        : `<p class="small muted" style="margin-top:12px">This tool has no typed fields to correct.</p>`
    }
    <div class="tool-modal-footer">
      ${tool.docs_url ? `<a class="text-link" href="${esc(tool.docs_url)}" target="_blank" rel="noreferrer">Provider docs ${icon("arrow-up-right")}</a>` : `<span class="muted small">No provider documentation URL</span>`}
      <button class="btn primary" type="button" data-use-tool="${esc(tool.id)}">${icon("play")}Use in a task</button>
    </div>`;
  $("#tool-correction-form")?.addEventListener("submit", submitToolCorrection);
  $("#correction-field")?.addEventListener("change", (event) => {
    const option = event.target.selectedOptions[0];
    const unit = $("#correction-unit");
    if (unit) unit.value = option?.dataset.unit || "";
    const concept = $("#correction-concept");
    if (concept && option?.dataset.concept && [...concept.options].some((entry) => entry.value === option.dataset.concept)) {
      concept.value = option.dataset.concept;
    }
  });
  $$("[data-auditor-action]").forEach((button) => {
    button.addEventListener("click", () => runToolAuditor(button.dataset.auditorTool, button.dataset.auditorAction));
  });
  body.querySelector("[data-use-tool]")?.addEventListener("click", () => {
    const task = TASK_DRAFTS[tool.capability] || `Use ${tool.name} to answer a question.`;
    try {
      localStorage.setItem("agent-bazaar-task", task);
    } catch (error) {
      toast("Could not stage the task in this browser.", "bad");
      return;
    }
    window.location.href = "/dashboard";
  });
  openModal("tool-modal");
}

async function submitToolCorrection(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const output = $("#tool-correction-result");
  if (!output) return;
  const submit = form.querySelector('button[type="submit"]');
  const fieldOption = $("#correction-field")?.selectedOptions[0];
  const payload = {
    tool_id: form.dataset.toolId,
    field_name: $("#correction-field")?.value.trim() || "",
    original_concept: fieldOption?.dataset.concept || "",
    corrected_concept: $("#correction-concept")?.value || "",
    corrected_unit: $("#correction-unit")?.value.trim() || null,
    note: $("#correction-note")?.value.trim() || "",
  };
  if (!payload.original_concept) {
    output.classList.remove("hidden");
    output.classList.add("bad");
    output.textContent = "The selected field has no original concept to correct.";
    return;
  }
  if (submit) submit.disabled = true;
  output.classList.add("hidden");
  try {
    const result = await api("/api/corrections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const staged = Boolean(result.staged);
    const accepted = Boolean(result.accepted);
    const violations = result.violations || [];
    output.classList.remove("hidden", "bad", "pending");
    if (accepted) {
      output.classList.add("pending");
      output.innerHTML = `${icon("check-circle")} <strong>Accepted.</strong> ${esc(result.message || "The correction was promoted into the graph.")} <span class="mono">${esc(result.correction_id)}</span>`;
      toast("Correction accepted and promoted into the graph.", "ok");
    } else if (staged) {
      output.classList.add("pending");
      output.innerHTML = `${icon("clock")} <strong>Staged for review.</strong> ${esc(result.message || violations.join("; ") || "The Mapper will review this correction before promotion.")} <span class="mono">${esc(result.correction_id)}</span>`;
      toast("Correction staged for Mapper review.", "ok");
    } else {
      output.classList.add("bad");
      output.innerHTML = `${icon("x-circle")} <strong>Rejected.</strong> ${esc(violations.join("; ") || result.message || "The correction did not pass validation.")}`;
      toast("Correction rejected.", "bad");
    }
    await loadStagedData();
    if ($("#staging-ledger")) renderStagedLedger();
    if (state.auditor) await loadAuditorData();
  } catch (error) {
    output.classList.remove("hidden", "pending");
    output.classList.add("bad");
    output.textContent = error.message;
  } finally {
    if (submit) submit.disabled = false;
  }
}

function resetOnboardState() {
  const select = $("#onboard-category");
  if (!select) return;
  const capabilities = Object.keys(state.ontology?.capabilities || {}).sort();
  select.innerHTML = capabilities
    .map((capability) => `<option value="${esc(capability)}">${esc(capability)}</option>`)
    .join("");
  if (capabilities.length) select.value = capabilities.includes("AnswerFromDocument") ? "AnswerFromDocument" : capabilities[0];
  updateOnboardOntology();
  $("#onboard-file-row")?.classList.add("hidden");
  $("#onboard-result")?.classList.add("hidden");
  $$("#onboard-queue .queue-row").forEach((row) => {
    row.classList.remove("running", "done", "failed");
    const status = $("em", row);
    if (status) status.textContent = "Queued";
  });
  const queueStatus = $("#onboard-queue-status");
  if (queueStatus) {
    queueStatus.className = "badge neutral";
    queueStatus.textContent = "Ready";
  }
}

function updateOnboardOntology() {
  const capability = $("#onboard-category")?.value;
  const details = state.ontology?.capabilities?.[capability];
  const field = $("#onboard-ontology");
  if (!field) return;
  field.innerHTML = `${icon("layers")}<span>${esc(capability || "Select a category")}${details?.inputs?.length ? ` · ${esc(details.inputs.join(", "))}` : ""}</span>${icon("chevron-down")}`;
}

function bindOnboarding() {
  $("#onboard-category")?.addEventListener("change", updateOnboardOntology);
  const fileInput = $("#onboard-file");
  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    const row = $("#onboard-file-row");
    if (!file || !row) return;
    $("#onboard-file-name").textContent = file.name;
    row.classList.remove("hidden");
  });
  const dropzone = $("#onboard-dropzone");
  if (dropzone) {
    ["dragenter", "dragover"].forEach((name) =>
      dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dropzone.style.borderColor = "var(--accent)";
      })
    );
    ["dragleave", "drop"].forEach((name) =>
      dropzone.addEventListener(name, () => {
        dropzone.style.borderColor = "";
      })
    );
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!fileInput || !event.dataTransfer?.files?.length) return;
      fileInput.files = event.dataTransfer.files;
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  $("#onboard-form")?.addEventListener("submit", submitListing);
}

function setQueueRow(stage, status, summary, label) {
  const row = $(`#onboard-queue .queue-row[data-stage="${stage}"]`);
  if (!row) return;
  row.classList.remove("running", "done", "failed");
  if (status) row.classList.add(status);
  const small = $("small", row);
  const stateLabel = $("em", row);
  if (small && summary) small.textContent = summary;
  if (stateLabel) stateLabel.textContent = label;
}

async function submitListing(event) {
  event.preventDefault();
  const name = $("#onboard-name")?.value.trim() || "";
  const capability = $("#onboard-category")?.value || "";
  const docsUrl = $("#onboard-url")?.value.trim() || "";
  const file = $("#onboard-file")?.files?.[0];
  const resultBox = $("#onboard-result");
  const submit = $("#onboard-submit");
  if (!name || !capability || !file || !docsUrl) {
    toast("Name, category, URL and a specification file are required.", "bad");
    return;
  }
  if (submit) {
    submit.disabled = true;
    submit.innerHTML = `${icon("loader")}Validating`;
  }
  const queueStatus = $("#onboard-queue-status");
  if (queueStatus) {
    queueStatus.className = "badge running";
    queueStatus.textContent = "Running";
  }
  resultBox?.classList.add("hidden");
  try {
    setQueueRow("parser", "running", `Reading ${file.name}…`, "Running");
    await delay(360);
    setQueueRow("parser", "done", `Spec attached · ${file.name}`, "Complete");
    setQueueRow("mapper", "running", "Resolving ontology types…", "Running");
    await delay(420);
    const capabilitySpec = state.ontology?.capabilities?.[capability] || { inputs: [], outputs: [] };
    const inputs = (capabilitySpec.inputs || []).map((concept) => ({
      concept,
      name: titleCase(concept).replaceAll(" ", "").replace(/^./, (letter) => letter.toLowerCase()),
      datatype: "string",
      required: true,
    }));
    const outputs = (capabilitySpec.outputs || []).map((concept) => ({
      concept,
      name: titleCase(concept).replaceAll(" ", "").replace(/^./, (letter) => letter.toLowerCase()),
      datatype: "string",
      required: true,
    }));
    setQueueRow("mapper", "done", `${inputs.length} inputs · ${outputs.length} outputs resolved`, "Complete");
    setQueueRow("shacl", "running", "Validating mapped shape…", "Running");
    const result = await api("/api/listings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: `Sandbox listing for ${capability}, submitted from the Agent Bazaar interface.`,
        capability,
        inputs,
        outputs,
        docs_url: docsUrl,
      }),
    });
    const accepted = Boolean(result.accepted);
    const staged = Boolean(result.staged);
    const promoted = accepted && !staged;
    const violations = result.violations || [];
    setQueueRow(
      "shacl",
      accepted ? "done" : "failed",
      violations.length ? violations.join("; ") : promoted ? "Mapped shape accepted and promoted" : "Mapped shape accepted and staged",
      accepted ? "Passed" : "Rejected"
    );
    if (queueStatus) {
      queueStatus.className = `badge ${accepted ? (promoted ? "verified" : "warning") : "contradicted"}`;
      queueStatus.innerHTML = `${icon(accepted ? (promoted ? "check" : "clock") : "x")}${accepted ? (promoted ? "Promoted" : "Staged") : "Rejected"}`;
    }
    if (resultBox) {
      resultBox.classList.remove("hidden", "bad", "pending");
      if (!accepted) resultBox.classList.add("bad");
      else if (staged) resultBox.classList.add("pending");
      resultBox.textContent = accepted
        ? promoted
          ? `Listing promoted into the knowledge graph as ${result.tool_id}. It is eligible for retrieval immediately.`
          : `Listing accepted and staged as ${result.tool_id}. The Mapper will review the typed mapping before promotion.`
        : `Rejected: ${(violations.length ? violations : ["The mapped shape did not pass validation."]).join("; ")}`;
    }
    toast(
      accepted ? (promoted ? "Listing promoted into the knowledge graph." : "Listing staged for Mapper review.") : "Listing rejected by validation.",
      accepted ? "ok" : "bad"
    );
    if (accepted) {
      await loadToolsData();
      await loadOntologyData();
      renderMarketplace();
      await loadStagedData();
    }
  } catch (error) {
    setQueueRow("shacl", "failed", error.message, "Failed");
    if (queueStatus) {
      queueStatus.className = "badge contradicted";
      queueStatus.textContent = "Failed";
    }
    if (resultBox) {
      resultBox.classList.remove("hidden");
      resultBox.classList.add("bad");
      resultBox.textContent = error.message;
    }
    toast(`Listing failed: ${error.message}`, "bad");
  } finally {
    if (submit) {
      submit.disabled = false;
      submit.innerHTML = `${icon("shield")}Register tool`;
    }
  }
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(value < 10240 ? 1 : 0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function renderDocumentList() {
  const list = $("#document-list");
  const count = $("#documents-count");
  if (count) {
    count.textContent = state.documents.length
      ? `${state.documents.length} file${state.documents.length === 1 ? "" : "s"} in this sandbox`
      : "No files uploaded yet";
  }
  if (!list) return;
  if (!state.documents.length) {
    list.innerHTML = emptyMarkup(
      "No documents yet",
      "Upload a text, Markdown, CSV, PDF or DOCX file to start a grounded question.",
      "file-text"
    );
    return;
  }
  list.innerHTML = state.documents
    .map(
      (item) => `<button class="document-row ${item.document_id === state.selectedDocument ? "is-selected" : ""}" type="button" data-document-id="${esc(item.document_id)}" aria-pressed="${item.document_id === state.selectedDocument}">
        <span class="document-row-icon">${icon("file-text")}</span>
        <span class="document-row-copy"><strong>${esc(item.name)}</strong><small>${formatFileSize(item.size_bytes)} · ${formatNumber(item.text_chars, 0)} characters</small></span>
        ${icon("chevron-right")}
      </button>`
    )
    .join("");
}

function clearDocumentDetail(message, detail = "") {
  const empty = $("#document-empty");
  const panel = $("#document-detail");
  const answer = $("#document-answer");
  if (panel) panel.classList.add("hidden");
  if (answer) {
    answer.classList.add("hidden");
    answer.innerHTML = "";
  }
  if (empty) {
    empty.classList.remove("hidden");
    empty.innerHTML = `<svg><use href="#i-file-text"></use></svg><strong>${esc(message)}</strong><p>${esc(detail)}</p>`;
  }
  const ask = $("#document-ask");
  if (ask) ask.disabled = true;
  const status = $("#document-ask-status");
  if (status) {
    status.className = "badge neutral";
    status.textContent = "No document";
  }
  state.documentDetail = null;
}

async function selectDocument(documentId) {
  if (!documentId) {
    state.selectedDocument = "";
    renderDocumentList();
    clearDocumentDetail("No document selected", "Choose a document from the library to preview it.");
    return;
  }
  state.selectedDocument = documentId;
  renderDocumentList();
  const empty = $("#document-empty");
  const panel = $("#document-detail");
  if (empty) {
    empty.classList.remove("hidden");
    empty.innerHTML = `<div class="loading-line">${icon("loader")}Loading document…</div>`;
  }
  if (panel) panel.classList.add("hidden");
  const ask = $("#document-ask");
  if (ask) ask.disabled = true;
  const status = $("#document-ask-status");
  if (status) {
    status.className = "badge neutral";
    status.textContent = "Loading";
  }
  try {
    const payload = await api(`/api/documents/${encodeURIComponent(documentId)}`);
    if (state.selectedDocument !== documentId) return;
    const document = payload.document;
    state.documentDetail = document;
    if (empty) empty.classList.add("hidden");
    if (panel) panel.classList.remove("hidden");
    const name = $("#document-detail-name");
    if (name) name.textContent = document.name;
    const meta = $("#document-detail-meta");
    if (meta) {
      meta.textContent = `${formatFileSize(document.size_bytes)} · ${formatNumber(document.text_chars, 0)} characters · Added ${formatDateTime(document.created_at)} · ${document.document_id}`;
    }
    const preview = $("#document-preview");
    if (preview) preview.textContent = document.text || "No text could be extracted.";
    if (ask) ask.disabled = false;
    if (status) {
      status.className = "badge neutral";
      status.textContent = "Ready";
    }
    const answer = $("#document-answer");
    if (answer) {
      answer.classList.add("hidden");
      answer.innerHTML = "";
    }
  } catch (error) {
    if (state.selectedDocument !== documentId) return;
    clearDocumentDetail("Document unavailable", error.message);
    const status = $("#document-ask-status");
    if (status) {
      status.className = "badge contradicted";
      status.textContent = "Unavailable";
    }
  }
}

async function loadDocuments(preferredId = "") {
  const list = $("#document-list");
  const count = $("#documents-count");
  if (list) list.innerHTML = `<div class="loading-line">${icon("loader")}Loading documents…</div>`;
  if (count) count.textContent = "Checking library…";
  try {
    const data = await api("/api/documents");
    state.documents = data.documents || [];
    const target = preferredId || state.selectedDocument || state.documents[0]?.document_id || "";
    const exists = state.documents.some((item) => item.document_id === target);
    renderDocumentList();
    if (target && exists) await selectDocument(target);
    else if (state.documents.length) await selectDocument(state.documents[0].document_id);
    else {
      state.selectedDocument = "";
      renderDocumentList();
      clearDocumentDetail(
        "Upload your first document",
        "Add a file on the left to preview its extracted text and ask a grounded question."
      );
    }
    return state.documents;
  } catch (error) {
    state.documents = [];
    state.selectedDocument = "";
    if (count) count.textContent = "Library unavailable";
    if (list) list.innerHTML = noticeMarkup("error", "Documents unavailable.", error.message);
    clearDocumentDetail("Document library unavailable", error.message);
    return state.documents;
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const input = $("#document-file");
  const file = input?.files?.[0];
  const output = $("#upload-result");
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  if (!file || !output) return;
  if (file.size > 10 * 1024 * 1024) {
    output.classList.remove("hidden", "good");
    output.classList.add("bad");
    output.textContent = "This file is larger than the 10 MB limit.";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  output.classList.add("hidden");
  if (submit) {
    submit.disabled = true;
    submit.innerHTML = `${icon("loader")}Uploading`;
  }
  try {
    const result = await api("/api/documents", { method: "POST", body: form });
    output.classList.remove("hidden", "bad");
    output.classList.add("good");
    output.textContent = `Uploaded ${result.document.name} · ${formatNumber(result.document.text_chars, 0)} characters extracted.`;
    if (input) input.value = "";
    await loadDocuments(result.document.document_id);
    toast("Document uploaded and selected.", "ok");
  } catch (error) {
    output.classList.remove("hidden", "good");
    output.classList.add("bad");
    output.textContent = error.message;
    toast(`Upload failed: ${error.message}`, "bad");
  } finally {
    if (submit) {
      submit.disabled = false;
      submit.innerHTML = `${icon("upload")}Upload document`;
    }
  }
}

async function deleteDocument() {
  const documentId = state.selectedDocument;
  const documentName = state.documentDetail?.name || "this document";
  if (!documentId) return;
  if (!window.confirm(`Remove “${documentName}”? The uploaded file and its extracted text will be deleted.`)) {
    return;
  }
  const button = $("#document-delete");
  if (button) button.disabled = true;
  try {
    await api(`/api/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    state.selectedDocument = "";
    state.documentDetail = null;
    await loadDocuments();
    toast("Document removed.", "ok");
  } catch (error) {
    toast(`Could not remove the document: ${error.message}`, "bad");
  } finally {
    if (button) button.disabled = false;
  }
}

function renderDocumentAnswer(result) {
  const container = $("#document-answer");
  if (!container) return;
  const steps = result.plan?.steps || [];
  const step = steps.find((entry) => entry.capability === "AnswerFromDocument");
  const raw = step?.output?.answer;
  const payload = raw && typeof raw === "object" ? raw : {};
  const answer = payload.answer || result.answer || "No answer returned.";
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  const status = String(result.status || "completed");
  const statusClass =
    status === "completed" ? "supported" : status === "partial" ? "warning" : "contradicted";
  const statusIcon =
    status === "completed" ? "check-circle" : status === "partial" ? "alert" : "x-circle";
  const citationMarkup = citations.length
    ? `<div class="document-citations">
        <p class="document-citations-label">Cited passages</p>
        ${citations
          .map(
            (citation) => `<blockquote>
              <p>${esc(citation.quote || "No quote returned.")}</p>
              <footer>${icon("file-text")}<span>${esc(citation.name || citation.document_id)}</span>${citation.score === undefined ? "" : `<small>relevance ${Number(citation.score).toFixed(2)}</small>`}</footer>
            </blockquote>`
          )
          .join("")}
      </div>`
    : `<p class="small muted">This answer had no cited passage. Try rephrasing with terms from the document.</p>`;
  container.classList.remove("hidden");
  container.innerHTML = `<div class="document-answer-head">
      <div>
        <span class="badge ${statusClass}">${icon(statusIcon)}${esc(titleCase(status))}</span>
        <span class="small muted">${formatNumber(result.duration_ms || 0, 0)} ms · ${esc(payload.document_id || state.selectedDocument)}</span>
      </div>
      <a class="text-link" href="/dashboard?task=${encodeURIComponent(result.task_id)}">Open full trace ${icon("arrow-up-right")}</a>
    </div>
    <p class="document-answer-text">${esc(answer)}</p>
    ${citationMarkup}`;
}

async function askDocument(event) {
  event.preventDefault();
  const question = $("#document-question")?.value.trim() || "";
  const documentId = state.selectedDocument;
  const button = $("#document-ask");
  const status = $("#document-ask-status");
  if (!documentId) {
    toast("Select a document before asking a question.", "bad");
    return;
  }
  if (!question) return;
  const task = question.toLowerCase().startsWith("according")
    ? question
    : `According to the uploaded document, ${question}`;
  if (button) {
    button.disabled = true;
    button.innerHTML = `${icon("loader")}Asking`;
  }
  if (status) {
    status.className = "badge neutral";
    status.textContent = "Running";
  }
  try {
    const result = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, document_id: documentId }),
    });
    renderDocumentAnswer(result);
    if (status) {
      const complete = result.status === "completed";
      status.className = `badge ${complete ? "supported" : "contradicted"}`;
      status.textContent = complete ? "Answered" : titleCase(result.status);
    }
    toast(
      result.status === "completed" ? "Document answer ready." : "Document question needs attention.",
      result.status === "completed" ? "ok" : "bad"
    );
  } catch (error) {
    const container = $("#document-answer");
    if (container) {
      container.classList.remove("hidden");
      container.innerHTML = noticeMarkup("error", "Document question failed.", error.message);
    }
    if (status) {
      status.className = "badge contradicted";
      status.textContent = "Failed";
    }
    toast(`Document question failed: ${error.message}`, "bad");
  } finally {
    if (button) {
      button.disabled = !state.selectedDocument;
      button.innerHTML = `${icon("play")}Ask document`;
    }
  }
}

function bindDocuments() {
  $("#upload-form")?.addEventListener("submit", uploadDocument);
  $("#document-question-form")?.addEventListener("submit", askDocument);
  $("#document-list")?.addEventListener("click", (event) => {
    const row = event.target.closest("[data-document-id]");
    if (row) selectDocument(row.dataset.documentId);
  });
  $("#document-delete")?.addEventListener("click", deleteDocument);
}

function initDocumentsPage() {
  return loadDocuments();
}

function monitorEvents() {
  const monitoring = state.monitoring || {};
  const events = [];
  (monitoring.drift_alerts || []).forEach((alert) => {
    events.push({
      key: `drift-${alert.alert_id}`,
      kind: "drift",
      time: alert.detected_at,
      severity: alert.severity || "high",
      title: `Schema drift detected on ${alert.tool_id}`,
      description: (alert.reasons || []).join("; ") || "The Auditor rejected the provider's response shape.",
      tags: ["Auditor", "Drift", alert.severity || "high"],
      toolId: alert.tool_id,
      data: alert,
    });
  });
  (monitoring.breakers || []).forEach((breaker) => {
    (breaker.transitions || []).slice(-2).forEach((transition, index) => {
      if (transition.from === transition.to) return;
      events.push({
        key: `breaker-${breaker.key}-${index}-${transition.to}`,
        kind: "breaker",
        time: null,
        severity: transition.to === "open" ? "high" : transition.to === "half-open" ? "medium" : "info",
        title: `Circuit breaker ${transition.to} · ${breaker.key}`,
        description: transition.reason || breaker.last_error || "Breaker state changed by the Client.",
        tags: ["Circuit breaker", transition.to],
        toolId: breaker.key.split("->").pop(),
        data: breaker,
      });
    });
  });
  state.monitorDetails.forEach((result) => {
    const steps = result.plan?.steps || [];
    (result.trace || [])
      .filter((event) => event.event_type === "step_failed")
      .forEach((failure) => {
        const toolId = failure.data?.tool_id || "provider";
        const step = steps.find((entry) => entry.substituted_from === toolId);
        events.push({
          key: `fail-${result.task_id}-${failure.seq}`,
          kind: "failure",
          time: failure.timestamp || result.created_at,
          severity: "high",
          title: `${toolId} failed a typed call`,
          description: failure.summary || "The provider returned an unusable response.",
          tags: ["Client", "Provider failure", step ? "Recovered" : "Isolated"],
          toolId,
          data: { result, failure, step },
        });
      });
    steps
      .filter((step) => step.substituted_from)
      .forEach((step) => {
        const failure = (result.trace || []).find(
          (event) => event.event_type === "step_failed" && event.data?.tool_id === step.substituted_from
        );
        events.push({
          key: `swap-${result.task_id}-${step.id}`,
          kind: "substitution",
          time: result.created_at,
          severity: "info",
          title: `Recovered ${step.capability} with a substitute`,
          description: `${step.substituted_from} failed; ${step.tool_id} completed the call.`,
          tags: ["Self-healing", "Substitution", `${formatNumber(step.latency_ms, 1)} ms`],
          toolId: step.tool_id,
          data: { result, step, failure },
        });
      });
  });
  const severityRank = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
  return events.sort((left, right) => {
    const timeDelta = new Date(right.time || 0) - new Date(left.time || 0);
    return timeDelta || (severityRank[right.severity] || 0) - (severityRank[left.severity] || 0);
  });
}

async function loadMonitorActivity() {
  state.monitorActivityError = null;
  try {
    const recent = await api("/api/tasks/recent?limit=8");
    state.recent = recent.tasks || [];
    const details = await Promise.all(
      state.recent.slice(0, 6).map((task) =>
        api(`/api/tasks/${encodeURIComponent(task.task_id)}`).catch(() => null)
      )
    );
    state.monitorDetails = details.filter(Boolean);
  } catch (error) {
    state.monitorDetails = [];
    state.monitorActivityError = error.message;
  }
  state.monitorActivity = monitorEvents();
}

function monitorNotice() {
  const container = $("#monitor-notice");
  if (!container) return;
  const detail = state.monitoringError || state.monitorActivityError;
  if (!detail) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }
  container.classList.remove("hidden");
  const stale = state.monitoring ? ` Showing the last snapshot from ${formatTime(state.monitoringFetchedAt)}.` : "";
  container.innerHTML = `<div class="notice error">${icon("x-circle")}<span><strong>${state.monitoringError ? "Monitoring API unavailable." : "Execution history unavailable."}</strong> ${esc(detail)}${esc(stale)} <button class="text-button" type="button" id="monitor-retry">Retry</button></span></div>`;
  $("#monitor-retry")?.addEventListener("click", async () => {
    await Promise.allSettled([loadMonitoringData(), loadMonitorActivity()]);
    renderMonitor();
  });
}

function renderMonitorMetrics() {
  const container = $("#monitor-metrics");
  if (!container) return;
  if (!state.monitoring) {
    container.innerHTML = `
      <div class="metric-card">${icon("box")}<strong>—</strong><label>Registered providers</label><small>Monitoring unavailable</small></div>
      <div class="metric-card">${icon("shield")}<strong>—</strong><label>Open circuits</label><small>Monitoring unavailable</small></div>
      <div class="metric-card">${icon("alert")}<strong>—</strong><label>Drift alerts</label><small>Monitoring unavailable</small></div>
      <div class="metric-card">${icon("pulse")}<strong>—</strong><label>Average live trust</label><small>No observations loaded</small></div>`;
    return;
  }
  const monitoring = state.monitoring;
  const providers = monitoring.providers || [];
  const breakers = monitoring.breakers || [];
  const alerts = monitoring.drift_alerts || [];
  const open = breakers.filter((breaker) => breaker.state === "open").length;
  const observed = providers.filter((provider) => Number(provider.calls || 0) + Number(provider.probes || 0) > 0);
  const trust = observed.length
    ? observed.reduce((total, provider) => total + Number(provider.trust || 0), 0) / observed.length
    : null;
  container.innerHTML = `
    <div class="metric-card">${icon("box")}<strong>${providers.length}</strong><label>Registered providers</label><small>${new Set(state.tools.map((tool) => tool.capability)).size} capabilities · ${esc(monitoring.mode || "sandbox")}</small></div>
    <div class="metric-card">${icon("shield")}<strong class="${open ? "alert" : ""}">${open}</strong><label>Open circuits</label><small>${breakers.length} links monitored</small></div>
    <div class="metric-card">${icon("alert")}<strong class="${alerts.length ? "alert" : ""}">${alerts.length}</strong><label>Drift alerts</label><small>Auditor ${esc(monitoring.auditor?.mode || "unknown")} · ${Number(monitoring.auditor?.mapped_tools || 0)}/${Number(monitoring.auditor?.catalog_tools || 0)} mapped</small></div>
    <div class="metric-card">${icon("pulse")}<strong>${trust === null ? "—" : formatTrust(trust)}</strong><label>Average live trust</label><small>${observed.length ? `${observed.length} observed provider${observed.length === 1 ? "" : "s"} · posterior mean` : "No calls or probes recorded"}</small></div>`;
}

function selectedMonitorEvent() {
  return state.monitorActivity.find((event) => event.key === state.monitorSelected) || state.monitorActivity[0] || null;
}

function renderMonitorFeed() {
  const feed = $("#alert-feed");
  if (!feed) return;
  const count = $("#feed-count");
  if (!state.monitorActivity.length) {
    feed.innerHTML = `<div class="empty-state inline" style="margin:14px">${icon("pulse")}<strong>No incidents recorded</strong><p>${esc(
      state.monitorActivityError
        ? "Execution history could not be loaded."
        : "No drift alerts, breaker transitions or failed calls have been recorded in this session."
    )}</p></div>`;
    if (count) count.textContent = state.monitorActivityError ? "unavailable" : "0 events";
    return;
  }
  feed.innerHTML = state.monitorActivity
    .map(
      (event) => `<button class="feed-item ${event.key === state.monitorSelected ? "active" : ""}" type="button" data-monitor-event="${esc(event.key)}">
        <div class="feed-item-top">
          <span class="severity ${esc(event.severity)}">${icon(event.kind === "drift" ? "alert" : event.kind === "failure" ? "alert" : event.kind === "substitution" ? "refresh" : "pulse")}${esc(event.severity)}</span>
          <time>${event.time ? formatTime(event.time) : "no timestamp"}</time>
        </div>
        <strong>${esc(event.title)}</strong>
        <p>${esc(event.description)}</p>
        <div class="feed-tags">${event.tags.map((tag) => `<span class="badge neutral">${esc(tag)}</span>`).join("")}</div>
      </button>`
    )
    .join("");
  if (count) count.textContent = `${state.monitorActivity.length} event${state.monitorActivity.length === 1 ? "" : "s"}`;
}

function mappingForEvent(event) {
  const tool = toolById(event?.toolId || "open-meteo-forecast");
  const output = tool?.outputs?.[0];
  const concept = output?.concept || "Temperature";
  const unit = output?.unit || "C";
  const expected = output
    ? `${concept}<${unit}>\n${(output.fields || []).slice(0, 4).map((field) => `  ${field}: typed`).join("\n") || "  schema: mapped"}`
    : "Typed provider contract\n  schema: mapped";
  if (!event) {
    return `<div class="detail-card-head"><h3>Mapping diff</h3><span class="badge neutral">No incident</span></div>
      <div class="mapping-body">
        ${emptyMarkup("No mapping diff to show", "Select an incident, or trigger drift from the control room to compare the expected and observed envelopes.", "map")}
      </div>`;
  }
  if (event.kind === "standby") {
    return `<div class="detail-card-head"><h3>Mapping diff</h3><span class="badge neutral">No incident</span></div>
      <div class="mapping-body">
        ${emptyMarkup("No mapping diff to show", "No drift validation is attached to this entry.", "map")}
      </div>`;
  }
  if (event.kind === "substitution") {
    const original = toolById(event.data.step.substituted_from);
    return `<div class="detail-card-head"><h3>Composition contract</h3><span class="badge supported">${icon("check")}Preserved</span></div>
      <div class="mapping-body">
        <div class="mapping-grid">
          <div class="mapping-panel"><span>Original capability</span><pre>${esc(`${event.data.step.capability}\n  inputs: bound\n  output: ${original?.name || event.data.step.substituted_from}`)}</pre></div>
          <div class="mapping-panel positive"><span>Substitute contract</span><pre>${esc(`tool: ${event.data.step.tool_id}\n  output: schema-valid\n  substituted_from: ${event.data.step.substituted_from}`)}</pre></div>
        </div>
        <div class="mapping-foot">${icon("check")}Type-compatible substitute selected; no ontology repair required.</div>
      </div>`;
  }
  if (event.kind === "failure") {
    const recovered = event.data?.step;
    return `<div class="detail-card-head"><h3>Failure isolation</h3><span class="badge ${recovered ? "supported" : "contradicted"}">${icon(recovered ? "refresh" : "alert")}${recovered ? "Recovered" : "Isolated"}</span></div>
      <div class="mapping-body">
        <div class="mapping-grid">
          <div class="mapping-panel negative"><span>Failed link</span><pre>${esc(`tool: ${event.toolId}\nreason: ${event.description}\naction: isolate`)}</pre></div>
          <div class="mapping-panel ${recovered ? "positive" : ""}"><span>Recovery path</span><pre>${esc(recovered ? `substitute: ${recovered.tool_id}\ncapability: ${recovered.capability}\nstatus: completed\nsubstituted_from: ${event.toolId}` : "substitute: none available\nstatus: fail closed\nanswer composition: blocked")}</pre></div>
        </div>
        <div class="mapping-foot">${icon(recovered ? "check" : "alert")}${recovered ? "The failed link was replaced before answer composition." : "The failure was isolated; no unverified output entered the answer."}</div>
      </div>`;
  }
  const reasons = (event.data.reasons || [event.description]).join("\n");
  return `<div class="detail-card-head"><h3>Mapping diff</h3><span class="badge contradicted">${icon("x")}Rejected</span></div>
    <div class="mapping-body">
      <div class="mapping-grid">
        <div class="mapping-panel"><span>Expected mapping</span><pre>${esc(expected)}</pre></div>
        <div class="mapping-panel negative"><span>Observed envelope</span><pre>${esc(`schema_valid: false\nreason: ${reasons}\ntool: ${event.toolId || "provider"}\naction: quarantine`)}</pre></div>
      </div>
      <div class="mapping-foot">${icon("alert")}The Auditor rejected the response before it entered any answer.</div>
    </div>`;
}

function renderMonitorIncident() {
  const event = selectedMonitorEvent();
  const container = $("#incident-card");
  if (!container) return;
  if (!event || event.kind === "standby") {
    container.innerHTML = `<div class="incident-empty"><span class="answer-icon">${icon("shield")}</span><div><h2>No incidents recorded</h2><p>${esc(
      state.monitoringError
        ? "Monitoring data is unavailable, so no health conclusion can be drawn."
        : "No drift alerts or breaker transitions are present in this session."
    )}</p></div><span class="badge neutral">${esc(state.monitoringError ? "Unknown" : "Clear")}</span></div>`;
    return;
  }
  const title =
    event.kind === "drift"
      ? "Provider contract drift"
      : event.kind === "substitution"
        ? "Chain recovered automatically"
        : event.kind === "failure"
          ? "Provider call failed"
          : "Circuit breaker isolated a link";
  const recoveredFailure = event.kind === "failure" && event.data?.step;
  const badge =
    event.kind === "substitution" || recoveredFailure
      ? `<span class="badge supported">${icon("refresh")}Recovered</span>`
      : event.kind === "failure"
        ? `<span class="badge contradicted">${icon("alert")}Isolated</span>`
        : `<span class="badge contradicted">${icon("alert")}${esc(event.severity)}</span>`;
  const meta = [event.tags[0], event.toolId, event.kind === "drift" ? "response quarantined" : event.kind === "failure" ? "link isolated" : "link protected"]
    .filter(Boolean)
    .map((tag) => `<span class="badge neutral">${esc(tag)}</span>`)
    .join("");
  container.innerHTML = `<div class="incident-body">
    <div class="incident-head"><div><h2>${esc(title)}</h2><p>${esc(event.description)}</p></div>${badge}</div>
    <div class="incident-meta">${meta}</div>
  </div>`;
}

function renderMonitorMapping() {
  const container = $("#mapping-card");
  if (container) container.innerHTML = mappingForEvent(selectedMonitorEvent());
}

function renderMonitorSubstitutions() {
  const container = $("#substitution-card");
  if (!container) return;
  const swaps = state.monitorActivity.filter((event) => ["failure", "substitution", "breaker", "drift"].includes(event.kind));
  const rows = swaps.length
    ? swaps
        .slice(0, 6)
        .map((event) => {
          const tag = event.kind === "drift" ? "Open" : event.kind === "failure" ? "Fail" : event.kind === "breaker" ? "Open" : "Swap";
          const tagClass = event.kind === "substitution" ? "swap" : "open";
          return `<div class="substitution-row"><time>${event.time ? formatTime(event.time) : "—"}</time><span class="log-tag ${tagClass}">${tag}</span><span>${esc(event.title)}</span></div>`;
        })
        .join("")
    : `<div class="substitution-row"><time>—</time><span class="log-tag match">Clear</span><span>No failures or substitutions recorded in this session.</span></div>`;
  const substitution = swaps.find((event) => event.kind === "substitution");
  const reason = substitution
    ? `<div class="swap-reason">${icon("check-circle")}<span>Type-compatible substitute accepted. The original provider remains isolated until validation recovers.</span></div>`
    : "";
  container.innerHTML = `<div class="detail-card-head"><h3>Recovery & substitution log</h3><span class="badge neutral">${swaps.length} event${swaps.length === 1 ? "" : "s"}</span></div><div class="substitution-body">${rows}${reason}</div>`;
}

function renderMonitorTrust() {
  const container = $("#monitor-trust-body");
  if (!container) return;
  const providers = [...(state.monitoring?.providers || [])].sort((left, right) => {
    const observed = Number(right.calls || 0) + Number(right.probes || 0) - Number(left.calls || 0) - Number(left.probes || 0);
    return observed || left.tool_name.localeCompare(right.tool_name);
  });
  if (!providers.length) {
    container.className = "panel-body";
    container.innerHTML = emptyMarkup("No provider evidence", state.monitoringError || "No providers are registered in this sandbox.");
    return;
  }
  container.className = "monitor-trust";
  container.innerHTML = providers
    .slice(0, 8)
    .map((provider) => {
      const observations = Number(provider.calls || 0) + Number(provider.probes || 0);
      const score = Number(provider.trust || 0.5);
      return `<div class="monitor-trust-row">
        <span class="monitor-trust-name"><strong>${esc(provider.tool_name)}</strong><small>${esc(provider.provider_id)} · ${observations ? `${observations} observation${observations === 1 ? "" : "s"}` : "prior only"}</small></span>
        ${scoreTrack(score, provider.demoted ? "open" : observations ? "closed" : "")}
        <span>${observations ? formatTrust(score) : "—"}</span>
      </div>`;
    })
    .join("");
}

function populateMonitorControls() {
  const select = $("#control-tool");
  if (!select) return;
  const providers = state.monitoring?.providers || [];
  const previous = select.value;
  select.innerHTML = providers.length
    ? providers
        .map(
          (provider) => `<option value="${esc(provider.tool_id)}">${esc(provider.tool_name)} · ${esc(provider.provider_id)}</option>`
        )
        .join("")
    : `<option value="">No providers available</option>`;
  if (previous && providers.some((provider) => provider.tool_id === previous)) select.value = previous;
  updateControlHint();
}

function updateControlHint() {
  const toolId = $("#control-tool")?.value;
  const mapping = auditorMapping(toolId);
  const hint = $("#control-hint");
  const probe = $("#control-monitor");
  if (probe) probe.disabled = !mapping;
  if (hint) {
    hint.textContent = !toolId
      ? "No provider is available for incident controls."
      : mapping
        ? `Auditor mapping: ${mapping.catalog_tool_id}. Probe establishes a baseline if none exists.`
        : "This provider has no Auditor catalogue mapping; verification is unavailable.";
  }
}

function setControlResult(kind, html) {
  const box = $("#control-result");
  if (!box) return;
  box.classList.remove("hidden", "bad", "pending");
  if (kind) box.classList.add(kind);
  box.innerHTML = html;
}

function renderMonitor() {
  monitorNotice();
  renderMonitorMetrics();
  renderMonitorFeed();
  renderMonitorIncident();
  renderMonitorMapping();
  renderMonitorSubstitutions();
  renderMonitorTrust();
  populateMonitorControls();
  const notifications = $("#notification-button .notification-dot");
  const alerts = state.monitoring?.drift_alerts || [];
  const open = (state.monitoring?.breakers || []).some((breaker) => breaker.state === "open");
  notifications?.classList.toggle("hidden", !state.monitoring || (!alerts.length && !open));
  const snapshot = $("#monitor-snapshot-time");
  if (snapshot) {
    snapshot.textContent = state.monitoring
      ? `${state.monitoringError ? "stale · " : ""}${formatTime(state.monitoringFetchedAt)}`
      : "unavailable";
  }
}

function toggleMonitorPause() {
  state.monitorPaused = !state.monitorPaused;
  const button = $("#pause-feed");
  if (button) {
    button.innerHTML = state.monitorPaused
      ? `${icon("play")}<span>Resume feed</span>`
      : `${icon("pause")}<span>Pause feed</span>`;
  }
  const chip = $("#live-chip");
  chip?.classList.toggle("paused", state.monitorPaused);
  if (chip) chip.innerHTML = `<span></span>${state.monitorPaused ? "Paused" : "Live simulation"}`;
}

async function refreshMonitor() {
  if (state.monitorPaused) return;
  await loadMonitoringData();
  state.monitorActivity = monitorEvents();
  if (!state.monitorActivity.some((event) => event.key === state.monitorSelected)) {
    state.monitorSelected = state.monitorActivity[0]?.key || null;
  }
  renderMonitor();
}

function bindMonitor() {
  $("#pause-feed")?.addEventListener("click", toggleMonitorPause);
  $("#alert-feed")?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-monitor-event]");
    if (!item) return;
    state.monitorSelected = item.dataset.monitorEvent;
    renderMonitor();
  });
  $("#control-tool")?.addEventListener("change", updateControlHint);
  $("#control-fail")?.addEventListener("click", async () => {
    const toolId = $("#control-tool")?.value;
    const times = Math.max(1, Math.min(20, Number($("#control-times")?.value || 1)));
    if (!toolId) {
      setControlResult("bad", "Choose a provider first.");
      return;
    }
    try {
      await api(`/api/demo/fail-next/${encodeURIComponent(toolId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ times }),
      });
      setControlResult("pending", `${icon("clock")}Next ${times} call${times === 1 ? "" : "s"} to <code>${esc(toolId)}</code> will fail. Run a task to exercise recovery.`);
      toast(`Scheduled ${times} failure${times === 1 ? "" : "s"} for ${toolId}.`, "ok");
      await loadMonitoringData();
      renderMonitor();
    } catch (error) {
      setControlResult("bad", esc(error.message));
      toast(`Could not schedule failure: ${error.message}`, "bad");
    }
  });
  $("#control-trip")?.addEventListener("click", async () => {
    const toolId = $("#control-tool")?.value;
    if (!toolId) {
      setControlResult("bad", "Choose a provider first.");
      return;
    }
    try {
      await api(`/api/demo/trip/${encodeURIComponent(toolId)}`, { method: "POST" });
      setControlResult("bad", `${icon("alert")}Breaker opened for <code>${esc(toolId)}</code>. The next composed call will isolate this link.`);
      toast(`Breaker opened for ${toolId}.`, "bad");
      await Promise.allSettled([loadMonitoringData(), loadMonitorActivity()]);
      state.monitorSelected = state.monitorActivity[0]?.key || null;
      renderMonitor();
    } catch (error) {
      setControlResult("bad", esc(error.message));
      toast(`Could not trip breaker: ${error.message}`, "bad");
    }
  });
  $("#control-monitor")?.addEventListener("click", async () => {
    const toolId = $("#control-tool")?.value;
    if (!toolId) {
      setControlResult("bad", "Choose a provider first.");
      return;
    }
    if (!auditorMapping(toolId)) {
      setControlResult("bad", "The Auditor has no catalogue mapping for this provider.");
      return;
    }
    setControlResult("pending", `<span class="loading-line">${icon("loader")}Probing ${esc(toolId)} with the Auditor…</span>`);
    try {
      const payload = await api(`/api/auditor/monitor/${encodeURIComponent(toolId)}?live=false`, { method: "POST" });
      setControlResult("", auditorResultMarkup(payload, "monitor"));
      toast("Auditor monitor pass complete.", "ok");
      await Promise.allSettled([loadMonitoringData(), loadAuditorData()]);
      state.monitorActivity = monitorEvents();
      renderMonitor();
    } catch (error) {
      setControlResult("bad", esc(error.message));
      toast(`Auditor monitor failed: ${error.message}`, "bad");
    }
  });
  const resetButton = $("#reset-demo");
  resetButton?.addEventListener("click", async () => {
    if (!state.resetArmed) {
      state.resetArmed = true;
      resetButton.classList.add("danger");
      resetButton.innerHTML = `${icon("alert")}<span>Click again to confirm</span>`;
      window.clearTimeout(state.resetTimer);
      state.resetTimer = window.setTimeout(() => {
        state.resetArmed = false;
        resetButton.classList.remove("danger");
        resetButton.innerHTML = `${icon("refresh")}<span>Reset demo data…</span>`;
      }, 4000);
      return;
    }
    window.clearTimeout(state.resetTimer);
    state.resetArmed = false;
    resetButton.classList.remove("danger");
    resetButton.innerHTML = `${icon("refresh")}<span>Reset demo data…</span>`;
    resetButton.disabled = true;
    try {
      await api("/api/demo/reset", { method: "POST" });
      state.monitorDetails = [];
      state.monitorSelected = null;
      state.trustProvider = "";
      await Promise.allSettled([
        loadToolsData(),
        loadMonitoringData(),
        loadMonitorActivity(),
        loadAuditorData(),
        loadKnowledgeData(),
        loadStagedData(),
        loadEvaluationsData(),
      ]);
      state.monitorActivity = monitorEvents();
      state.monitorSelected = state.monitorActivity[0]?.key || null;
      renderMonitor();
      renderTrustCenterData();
      renderWorkspaceStrip();
      setControlResult("", `${icon("check-circle")}Demo state reset. Trust, breakers, Auditor baselines, staging and overrides were cleared; task traces and documents were kept.`);
      toast("Demo state reset. Task traces and documents were kept.", "ok");
    } catch (error) {
      setControlResult("bad", esc(error.message));
      toast(`Could not reset the demo: ${error.message}`, "bad");
    } finally {
      resetButton.disabled = false;
      resetButton.innerHTML = `${icon("refresh")}<span>Reset demo data…</span>`;
    }
  });
  $("#simulate-drift")?.addEventListener("click", async () => {
    const button = $("#simulate-drift");
    const toolId = $("#control-tool")?.value;
    if (!toolId) {
      setControlResult("bad", "Choose a provider first.");
      return;
    }
    if (button) button.disabled = true;
    try {
      await api(`/api/demo/drift/${encodeURIComponent(toolId)}`, { method: "POST" });
      setControlResult("bad", `${icon("alert")}Simulated schema drift for <code>${esc(toolId)}</code>. Inspect the feed and mapping diff.`);
      toast(`Simulated drift on ${toolId}.`, "bad");
      await Promise.allSettled([loadMonitoringData(), loadMonitorActivity()]);
      state.monitorSelected = state.monitorActivity.find((event) => event.kind === "drift")?.key || state.monitorSelected;
      renderMonitor();
    } catch (error) {
      toast(`Could not inject drift: ${error.message}`, "bad");
    } finally {
      if (button) button.disabled = false;
    }
  });
  $("#view-all-logs")?.addEventListener("click", () => {
    renderLogsModal();
    openModal("logs-modal");
  });
}

function renderLogsModal() {
  const container = $("#logs-modal-body");
  if (!container) return;
  container.innerHTML = state.monitorActivity
    .map((event) => {
      const tag = event.kind === "drift" ? "Fail" : event.kind === "failure" ? "Fail" : event.kind === "substitution" ? "Swap" : event.kind === "breaker" ? "Open" : "Info";
      const tagClass = event.kind === "drift" || event.kind === "failure" ? "fail" : event.kind === "substitution" ? "swap" : event.kind === "breaker" ? "open" : "info";
      return `<div class="log-detail-row"><time>${event.time ? formatTime(event.time) : "now"}</time><span class="log-tag ${tagClass}">${tag}</span><span>${esc(event.title)} — ${esc(event.description)}</span></div>`;
    })
    .join("");
}

function initMonitor() {
  state.monitorSelected = state.monitorActivity[0]?.key || null;
  bindMonitor();
  renderMonitor();
  window.setInterval(refreshMonitor, 5000);
}

/* --------------------------------------------------------------------------
   Trust Center
   -------------------------------------------------------------------------- */

function trustRecordCounts() {
  return {
    corrections: state.staged?.corrections?.length || 0,
    listings: state.staged?.listings?.length || 0,
    total: (state.staged?.corrections?.length || 0) + (state.staged?.listings?.length || 0),
  };
}

function trustMetricMarkup(label, value, detail) {
  return `<div class="trust-metric"><span>${esc(label)}</span><strong>${value}</strong><small>${detail}</small></div>`;
}

function renderTrustMetrics() {
  const container = $("#trust-metrics");
  if (!container) return;
  const auditor = state.auditor;
  const mappings = auditor?.mappings?.length || 0;
  const catalog = auditor?.catalog_tools || 0;
  const probes = auditor?.probe_definitions || 0;
  const claims = (auditor?.tools || []).reduce((total, tool) => total + (tool.claims?.length || 0), 0);
  const leaderboard = state.auditorTrust?.leaderboard || [];
  const observations = leaderboard.reduce((total, row) => total + Number(row.observations || 0), 0);
  const graph = state.knowledge?.graph;
  const counts = trustRecordCounts();

  const auditorValue = state.auditorError
    ? "—"
    : auditor
      ? `${mappings}/${catalog}`
      : `<span class="skeleton" style="width:48px;height:22px">&nbsp;</span>`;
  const auditorDetail = state.auditorError
    ? "Auditor unavailable"
    : auditor
      ? `${esc(auditor.mode)} mode · ${mappings} mapped`
      : "Checking Auditor";

  const probesValue = state.auditorError
    ? "—"
    : auditor
      ? String(probes)
      : `<span class="skeleton" style="width:36px;height:22px">&nbsp;</span>`;
  const probesDetail = state.auditorError
    ? "No probe definitions"
    : auditor
      ? `${claims} provider claims declared`
      : "Checking probe definitions";

  const trustValue = state.auditorTrustError
    ? "—"
    : state.auditorTrust
      ? String(observations)
      : `<span class="skeleton" style="width:40px;height:22px">&nbsp;</span>`;
  const trustDetail = state.auditorTrustError
    ? "Trust feed unavailable"
    : state.auditorTrust
      ? observations
        ? `${leaderboard.length} tool${leaderboard.length === 1 ? "" : "s"} with evidence`
        : "No probe observations yet"
      : "Checking trust feed";

  const graphValue = state.knowledgeError
    ? "—"
    : graph
      ? formatNumber(graph.mappings, 0)
      : `<span class="skeleton" style="width:48px;height:22px">&nbsp;</span>`;
  const graphDetail = state.knowledgeError
    ? "Knowledge layer unavailable"
    : graph
      ? `${formatNumber(graph.tools, 0)} tools · ${formatNumber(graph.concepts, 0)} concepts`
      : "Checking knowledge layer";

  const stagedValue = state.stagedError
    ? "—"
    : state.staged
      ? String(counts.total)
      : `<span class="skeleton" style="width:32px;height:22px">&nbsp;</span>`;
  const stagedDetail = state.stagedError
    ? "Staging ledger unavailable"
    : state.staged
      ? counts.total
        ? `${counts.corrections} correction${counts.corrections === 1 ? "" : "s"} · ${counts.listings} listing${counts.listings === 1 ? "" : "s"}`
        : "No records awaiting review"
      : "Checking Mapper queue";

  container.innerHTML = [
    trustMetricMarkup("Mapped tools", auditorValue, auditorDetail),
    trustMetricMarkup("Auditor probes", probesValue, probesDetail),
    trustMetricMarkup("Trust observations", trustValue, trustDetail),
    trustMetricMarkup("Graph mappings", graphValue, graphDetail),
    trustMetricMarkup("Staged records", stagedValue, stagedDetail),
  ].join("");

  const mode = $("#trust-mode");
  if (mode) {
    if (state.auditorError) {
      mode.className = "badge contradicted";
      mode.innerHTML = `${icon("alert")}Auditor unavailable`;
    } else if (!state.auditor) {
      mode.className = "badge neutral";
      mode.textContent = "Checking Auditor…";
    } else {
      mode.className = "badge neutral";
      mode.innerHTML = `${icon("shield")}${esc(titleCase(state.auditor.mode))} probes · ${state.auditor.catalog_tools} catalogue tools`;
    }
  }
  const footer = $("#trust-footer-count");
  if (footer) footer.textContent = state.auditor ? String(mappings) : "—";
}

function renderAuditorOverview() {
  const container = $("#auditor-overview");
  const badge = $("#auditor-coverage-badge");
  if (!container) return;
  if (state.auditorError) {
    container.innerHTML = noticeMarkup("error", "Auditor overview unavailable.", state.auditorError);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
    return;
  }
  if (!state.auditor) {
    container.innerHTML = `<div class="loading-line">${icon("loader")}Loading Auditor overview…</div>`;
    if (badge) badge.textContent = "…";
    return;
  }
  const auditor = state.auditor;
  const mappings = auditor.mappings || [];
  const claims = (auditor.tools || []).reduce((total, tool) => total + (tool.claims?.length || 0), 0);
  const probeable = (auditor.tools || []).filter((tool) => tool.probeable).length;
  if (badge) {
    badge.className = "badge supported";
    badge.innerHTML = `${icon("check-circle")}${mappings.length}/${auditor.catalog_tools} mapped`;
  }
  container.innerHTML = `
    <div class="auditor-overview-stat">
      <div><span>Mode</span><strong>${esc(titleCase(auditor.mode))}</strong></div>
      <div><span>Catalogue</span><strong>${auditor.catalog_tools}</strong></div>
      <div><span>Probes</span><strong>${auditor.probe_definitions}</strong></div>
      <div><span>Claims</span><strong>${claims}</strong></div>
    </div>
    <div class="mapping-list">
      ${mappings
        .map(
          (mapping) => `<button class="mapping-list-row" type="button" data-open-tool="${esc(mapping.app_tool_id)}">
            <strong>${esc(mapping.app_tool_id)}</strong>
            <small>→ ${esc(mapping.catalog_tool_id)}</small>
            <span class="badge neutral">${esc(mapping.provider_id || "unmapped")}</span>
          </button>`
        )
        .join("")}
    </div>
    <div class="kg-foot">
      <span>${probeable} probeable catalogue tool${probeable === 1 ? "" : "s"} · ${claims} declared claim${claims === 1 ? "" : "s"}</span>
      <a class="text-link" href="/dashboard">Run a verified task ${icon("arrow-up-right")}</a>
    </div>`;
}

function renderTrustLeaderboard() {
  const container = $("#trust-leaderboard");
  const badge = $("#leaderboard-count");
  if (!container) return;
  if (state.auditorTrustError) {
    container.className = "panel-body";
    container.innerHTML = noticeMarkup("error", "Trust feed unavailable.", state.auditorTrustError);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
    return;
  }
  if (!state.auditorTrust) {
    container.className = "panel-body flush";
    container.innerHTML = `<div class="loading-line" style="padding:0 18px">${icon("loader")}Loading trust observations…</div>`;
    if (badge) badge.textContent = "…";
    return;
  }
  const rows = [...(state.auditorTrust.leaderboard || [])].sort(
    (left, right) => Number(right.observations || 0) - Number(left.observations || 0) || Number(right.score || 0) - Number(left.score || 0)
  );
  const feed = state.auditorTrust.feed || {};
  const totalObservations = rows.reduce((total, row) => total + Number(row.observations || 0), 0);
  if (badge) {
    badge.className = "badge neutral";
    badge.textContent = `${rows.length} tool${rows.length === 1 ? "" : "s"}`;
  }
  if (!rows.length) {
    container.className = "panel-body";
    container.innerHTML = emptyMarkup(
      "No probe observations",
      "Run a verification or monitor pass to populate the Auditor trust ledger. Registry evidence and probe evidence are kept separate."
    );
    return;
  }
  container.className = "panel-body flush";
  container.innerHTML = `<table class="data-table">
      <thead><tr><th>Tool</th><th>Evidence</th><th class="num">Score</th></tr></thead>
      <tbody>
        ${rows
          .map((row) => {
            const mapping = (state.auditor?.mappings || []).find((entry) => entry.catalog_tool_id === row.tool_id);
            const tool = mapping ? toolById(mapping.app_tool_id) : null;
            const label = tool?.name || mapping?.app_tool_id || row.tool_id;
            return `<tr>
              <td><strong>${esc(label)}</strong><br><small class="mono">${esc(row.tool_id)}${mapping ? ` · ${esc(mapping.app_tool_id)}` : ""}</small></td>
              <td>${row.observations || 0} observation${row.observations === 1 ? "" : "s"}<br><small>${esc(row.successes || 0)} success weight · ${esc(row.failures || 0)} failure weight</small></td>
              <td class="num"><div class="score-cell">${scoreTrack(Number(row.score || 0), Number(row.failures || 0) ? "open" : "closed")}<span>${formatTrust(row.score)}</span></div></td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
    <div class="kg-foot">
      <span>${totalObservations} evidence observation${totalObservations === 1 ? "" : "s"} · ${feed.delivery_failures || 0} delivery failure${feed.delivery_failures === 1 ? "" : "s"}</span>
      <span>${rows.filter((row) => row.last_outcome === "probe_pass").length} tool${rows.filter((row) => row.last_outcome === "probe_pass").length === 1 ? "" : "s"} last passed</span>
    </div>`;
}

function renderKnowledge() {
  const container = $("#knowledge-body");
  const badge = $("#knowledge-backend");
  if (!container) return;
  if (state.knowledgeError) {
    container.className = "panel-body";
    container.innerHTML = noticeMarkup("error", "Knowledge layer unavailable.", state.knowledgeError);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
    return;
  }
  if (!state.knowledge) {
    container.className = "panel-body flush";
    container.innerHTML = `<div class="loading-line" style="padding:0 18px">${icon("loader")}Loading graph statistics…</div>`;
    if (badge) badge.textContent = "…";
    return;
  }
  const knowledge = state.knowledge;
  if (!knowledge.available) {
    container.className = "panel-body";
    container.innerHTML = emptyMarkup(
      "Knowledge artifacts unavailable",
      knowledge.reason || "The configured knowledge backend did not expose a graph in this environment.",
      "database"
    );
    if (badge) {
      badge.className = "badge neutral";
      badge.textContent = knowledge.backend || "unavailable";
    }
    return;
  }
  const graph = knowledge.graph || {};
  if (badge) {
    badge.className = "badge supported";
    badge.textContent = knowledge.backend || "graph";
  }
  container.className = "panel-body flush";
  container.innerHTML = `<div class="kg-stats">
      ${[
        ["Tools", graph.tools],
        ["Concepts", graph.concepts],
        ["Mappings", graph.mappings],
        ["Claims", graph.claims],
        ["Published", knowledge.tools?.length || 0],
        ["Ontology", knowledge.concepts || 0],
      ]
        .map(
          ([label, value]) => `<div class="kg-stat"><span>${esc(label)}</span><strong>${formatNumber(value || 0, 0)}</strong></div>`
        )
        .join("")}
    </div>
    <div class="kg-foot">
      <span title="${esc(knowledge.graph_file || "")}">${icon("database")} ${esc(truncate(knowledge.graph_file || "graph store", 46))}</span>
      <span title="${esc(knowledge.ontology_file || "")}">${esc(truncate(knowledge.ontology_file || "ontology", 36))}</span>
    </div>`;
}

function renderStagedLedger() {
  const container = $("#staging-ledger");
  const badge = $("#staging-count");
  if (!container) return;
  if (state.stagedError) {
    container.className = "panel-body";
    container.innerHTML = noticeMarkup("error", "Staging ledger unavailable.", state.stagedError);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
    return;
  }
  if (!state.staged) {
    container.className = "panel-body flush";
    container.innerHTML = `<div class="loading-line" style="padding:0 18px">${icon("loader")}Loading staging records…</div>`;
    if (badge) badge.textContent = "…";
    return;
  }
  const counts = trustRecordCounts();
  if (badge) {
    badge.className = "badge neutral";
    badge.textContent = `${counts.total} record${counts.total === 1 ? "" : "s"}`;
  }
  if (!counts.total) {
    container.className = "panel-body";
    container.innerHTML = emptyMarkup(
      "Staging ledger is clear",
      "Corrections and listings submitted from the UI appear here with their review status. A staged record is awaiting Mapper review, not rejected."
    );
    return;
  }
  const corrections = state.staged.corrections || [];
  const listings = state.staged.listings || [];
  container.className = "panel-body flush";
  container.innerHTML = `<div class="staging-list">
      ${corrections
        .map((record) => {
          const status = String(record.status || "pending_review");
          const statusClass = status === "promoted" ? "supported" : status === "rejected" ? "contradicted" : "warning";
          return `<div class="staging-item">
            <div class="staging-item-top">
              <strong>Correction · ${esc(record.tool_id)}</strong>
              <span class="badge ${statusClass}">${esc(status.replace(/_/g, " "))}</span>
            </div>
            <p>${esc(record.field_name || "field")} · ${esc(record.original_concept || "?")} → ${esc(record.corrected_concept || "?")}${record.corrected_unit ? ` (${esc(record.corrected_unit)})` : ""}</p>
            <p class="mono">${esc(record.correction_id || "")}${record.field_path ? ` · ${esc(record.field_path)}` : ""} · ${formatAge(record.submitted_at)}</p>
          </div>`;
        })
        .join("")}
      ${listings
        .map((record) => {
          const status = String(record.status || "staged");
          const statusClass = status === "promoted" ? "supported" : status === "rejected" ? "contradicted" : "warning";
          return `<div class="staging-item">
            <div class="staging-item-top">
              <strong>Listing · ${esc(record.name || record.tool_id)}</strong>
              <span class="badge ${statusClass}">${esc(status)}</span>
            </div>
            <p>${esc(record.capability || "unmapped capability")} · ${record.promoted ? "promoted into the graph" : "awaiting Mapper promotion"}${(record.violations || []).length ? ` · ${esc((record.violations || []).join("; "))}` : ""}</p>
            <p class="mono">${esc(record.tool_id || "")} · ${formatAge(record.submitted_at)}</p>
          </div>`;
        })
        .join("")}
    </div>`;
}

function metricDisplay(key, value) {
  if (typeof value !== "number" || Number.isNaN(value)) return String(value);
  if (key.endsWith("_ms")) return `${formatNumber(value, 1)} ms`;
  if (/(rate|accuracy|coverage|mrr|ndcg|recovery|delta|precision|recall)/.test(key)) return `${formatNumber(value * 100, 1)}%`;
  return formatNumber(value, 3).replace(/\.?0+$/, "");
}

function renderEvaluations() {
  const container = $("#evaluations-body");
  const badge = $("#evaluation-count");
  if (!container) return;
  if (state.evaluationsError) {
    container.innerHTML = noticeMarkup("error", "Evaluation reports unavailable.", state.evaluationsError);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
    return;
  }
  if (!state.evaluations) {
    container.innerHTML = `<div class="loading-line">${icon("loader")}Loading evaluation reports…</div>`;
    if (badge) badge.textContent = "…";
    return;
  }
  const reports = state.evaluations.reports || [];
  if (badge) {
    badge.className = "badge neutral";
    badge.textContent = `${reports.length} suite${reports.length === 1 ? "" : "s"}`;
  }
  if (!reports.length) {
    container.innerHTML = emptyMarkup(
      "No evaluation reports",
      "Run the offline evaluation suites to publish chain, matching and trust reports here.",
      "flask"
    );
    return;
  }
  container.innerHTML = `<div class="eval-list">
      ${reports
        .map((report) => {
          const summary = report.summary || {};
          const metrics = summary.metrics || {};
          const entries = Object.entries(metrics);
          const primary = entries[0];
          const detail = entries
            .slice(0, 4)
            .map(([key, value]) => `${esc(key.replace(/_/g, " "))} ${metricDisplay(key, value)}`)
            .join(" · ");
          return `<div class="eval-row">
            <span><strong>${esc(report.name || summary.suite || "suite")}</strong><small>${esc(modeLabel(summary.mode))} · ${formatAge(summary.generated_at)} · ${entries.length} metric${entries.length === 1 ? "" : "s"}</small><small>${detail}</small></span>
            <span class="eval-value">${primary ? esc(metricDisplay(primary[0], primary[1])) : "—"}</span>
          </div>`;
        })
        .join("")}
    </div>
    <div class="kg-foot"><span>Offline reports from <code>reports/evaluations</code></span><span>${esc(state.evaluations.mode || "offline")}</span></div>`;
}

function modeLabel(mode) {
  const normalized = String(mode || "offline");
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function populateTrustSelectors() {
  const providerSelect = $("#trust-provider");
  if (providerSelect) {
    const providers = [...(state.monitoring?.providers || [])].sort((left, right) => left.tool_name.localeCompare(right.tool_name));
    const previous = state.trustProvider || providerSelect.value;
    providerSelect.innerHTML = `<option value="">Select a provider</option>${providers
      .map(
        (provider) => `<option value="${esc(provider.provider_id)}">${esc(provider.tool_name)} · ${esc(provider.provider_id)}</option>`
      )
      .join("")}`;
    if (previous && providers.some((provider) => provider.provider_id === previous)) {
      providerSelect.value = previous;
    } else {
      providerSelect.value = "";
      state.trustProvider = "";
    }
  }
  const verifySelect = $("#verify-tool");
  if (verifySelect) {
    const mappings = state.auditor?.mappings || [];
    const previous = state.verifyTool || verifySelect.value;
    verifySelect.innerHTML = `<option value="">Select a mapped tool</option>${mappings
      .map((mapping) => {
        const tool = toolById(mapping.app_tool_id);
        return `<option value="${esc(mapping.app_tool_id)}">${esc(tool?.name || mapping.app_tool_id)} · ${esc(mapping.catalog_tool_id)}</option>`;
      })
      .join("")}`;
    if (previous && mappings.some((mapping) => mapping.app_tool_id === previous)) {
      verifySelect.value = previous;
      state.verifyTool = previous;
    } else {
      const fallback = mappings[0]?.app_tool_id || "";
      verifySelect.value = fallback;
      state.verifyTool = fallback;
    }
  }
  const run = $("#verify-run");
  const monitor = $("#verify-monitor");
  const hasMapping = Boolean(state.verifyTool);
  if (run) run.disabled = !hasMapping;
  if (monitor) monitor.disabled = !hasMapping;
}

function renderTrustDetail(payload) {
  const container = $("#trust-detail");
  const badge = $("#trust-replay-badge");
  if (!container) return;
  if (!payload) {
    container.innerHTML = `<div class="empty-state inline"><strong>No provider selected</strong><p>Choose a provider to inspect its signals and replay consistency.</p></div>`;
    if (badge) {
      badge.className = "badge neutral";
      badge.textContent = "—";
    }
    return;
  }
  const stateRow = payload.state || {};
  const history = payload.history || [];
  const replay = payload.replay || {};
  if (badge) {
    badge.className = `badge ${replay.matches ? "supported" : "contradicted"}`;
    badge.innerHTML = `${icon(replay.matches ? "check" : "alert")}${replay.matches ? "Replay matches" : "Replay differs"}`;
  }
  container.innerHTML = `
    <div class="trust-detail-grid">
      <div><span>Current score</span><strong>${formatTrust(stateRow.score)}</strong></div>
      <div><span>Observed calls</span><strong>${Number(stateRow.calls || 0)}</strong></div>
      <div><span>Probes</span><strong>${Number(stateRow.probes || 0)}</strong></div>
      <div><span>Contradictions</span><strong>${Number(stateRow.contradictions || 0)}</strong></div>
    </div>
    <div class="replay-line ${replay.matches ? "" : "bad"}">
      ${icon(replay.matches ? "check-circle" : "alert")}
      <span>Replayed ${formatTrust(replay.replayed_score)} from ${replay.updates || 0} update${replay.updates === 1 ? "" : "s"} (${formatNumber(replay.replayed_successes || 0, 2)} success / ${formatNumber(replay.replayed_failures || 0, 2)} failure weight). ${replay.matches ? "Ledger and live state agree." : "Ledger replay does not match the live score."}</span>
    </div>
    ${
      history.length
        ? `<div class="trust-history">${history
            .slice(0, 12)
            .map(
              (row) => `<div class="trust-history-row">
                <time>${formatDateTime(row.created_at)}</time>
                <span><strong>${esc(row.signal || "signal")}</strong> · ${row.success ? "success" : "failure"} · weight ${formatNumber(row.weight || 0, 2)} · ${esc(row.source || "")}</span>
                <strong>${formatTrust(row.score)}</strong>
              </div>`
            )
            .join("")}</div>`
        : emptyMarkup("No trust signals yet", "This provider has no recorded execution or probe evidence. Its score is the default prior, not an observation.", "clock")
    }`;
}

async function loadTrustDetail(providerId) {
  const container = $("#trust-detail");
  const badge = $("#trust-replay-badge");
  if (!providerId) {
    state.trustProvider = "";
    renderTrustDetail(null);
    return;
  }
  state.trustProvider = providerId;
  if (container) container.innerHTML = `<div class="loading-line">${icon("loader")}Loading trust history for ${esc(providerId)}…</div>`;
  if (badge) {
    badge.className = "badge neutral";
    badge.textContent = "…";
  }
  try {
    const payload = await api(`/api/trust/${encodeURIComponent(providerId)}`);
    renderTrustDetail(payload);
  } catch (error) {
    if (container) container.innerHTML = noticeMarkup("error", "Trust history unavailable.", error.message);
    if (badge) {
      badge.className = "badge contradicted";
      badge.textContent = "offline";
    }
  }
}

async function runTrustVerification(mode) {
  const toolId = state.verifyTool;
  const output = $("#verify-output");
  if (!output) return;
  if (!toolId) {
    output.className = "auditor-output";
    output.textContent = "Select a mapped tool first.";
    return;
  }
  const buttons = [$("#verify-run"), $("#verify-monitor")];
  buttons.forEach((button) => {
    if (button) button.disabled = true;
  });
  output.className = "auditor-output";
  output.innerHTML = `<span class="loading-line">${icon("loader")}Running ${mode === "monitor" ? "monitor pass" : "verification"} for <code>${esc(toolId)}</code>…</span>`;
  try {
    const path = mode === "monitor" ? `/api/auditor/monitor/${encodeURIComponent(toolId)}` : `/api/auditor/verify/${encodeURIComponent(toolId)}`;
    const payload = await api(`${path}?live=false`, { method: "POST" });
    output.innerHTML = auditorResultMarkup(payload, mode);
    toast(`${mode === "monitor" ? "Monitor pass" : "Verification"} complete for ${toolId}.`, "ok");
    await Promise.allSettled([loadAuditorData(), loadMonitoringData()]);
    renderTrustCenterData();
    const provider = (state.monitoring?.providers || []).find((entry) => entry.tool_id === toolId);
    if (state.trustProvider) await loadTrustDetail(state.trustProvider);
    else if (provider) await loadTrustDetail(provider.provider_id);
    if ($("#monitor-metrics")) {
      state.monitorActivity = monitorEvents();
      renderMonitor();
    }
  } catch (error) {
    output.innerHTML = noticeMarkup("error", "Auditor request failed.", error.message);
    toast(`Auditor request failed: ${error.message}`, "bad");
  } finally {
    buttons.forEach((button) => {
      if (button) button.disabled = !state.verifyTool;
    });
  }
}

function renderTrustCenterData() {
  renderTrustMetrics();
  renderAuditorOverview();
  renderTrustLeaderboard();
  renderKnowledge();
  renderStagedLedger();
  renderEvaluations();
  populateTrustSelectors();
}

async function selectInitialTrustProvider() {
  if (state.trustProvider) return;
  const providers = [...(state.monitoring?.providers || [])].sort((left, right) => {
    const leftObserved = Number(left.calls || 0) + Number(left.probes || 0);
    const rightObserved = Number(right.calls || 0) + Number(right.probes || 0);
    return rightObserved - leftObserved || left.tool_name.localeCompare(right.tool_name);
  });
  const candidate = providers[0];
  if (!candidate) return;
  const select = $("#trust-provider");
  if (select) select.value = candidate.provider_id;
  await loadTrustDetail(candidate.provider_id);
}

async function refreshTrustCenter() {
  const button = $("#trust-refresh");
  if (button) button.disabled = true;
  try {
    await Promise.allSettled([
      loadAuditorData(),
      loadMonitoringData(),
      loadKnowledgeData(),
      loadStagedData(),
      loadEvaluationsData(),
    ]);
    renderTrustCenterData();
    if (state.trustProvider) await loadTrustDetail(state.trustProvider);
    else await selectInitialTrustProvider();
    renderWorkspaceStrip();
  } finally {
    if (button) button.disabled = false;
  }
}

function initTrustCenter() {
  $("#trust-refresh")?.addEventListener("click", refreshTrustCenter);
  $("#verify-tool")?.addEventListener("change", (event) => {
    state.verifyTool = event.target.value;
    populateTrustSelectors();
    const output = $("#verify-output");
    if (output && !state.verifyTool) {
      output.className = "auditor-output";
      output.textContent = "Select a mapped tool to verify its provider claims against live or fixture probes. Verification always establishes a fresh baseline.";
    }
  });
  $("#verify-run")?.addEventListener("click", () => runTrustVerification("verify"));
  $("#verify-monitor")?.addEventListener("click", () => runTrustVerification("monitor"));
  $("#trust-provider")?.addEventListener("change", (event) => {
    loadTrustDetail(event.target.value);
  });
  $("#auditor-overview")?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-open-tool]");
    if (link) openToolModal(link.dataset.openTool);
  });
  renderTrustCenterData();
  populateTrustSelectors();
  selectInitialTrustProvider();
}

/* --------------------------------------------------------------------------
   Task protocol
   -------------------------------------------------------------------------- */

const PROTOCOL_KINDS = {
  TaskRequest: { icon: "play", tone: "neutral", label: "Task" },
  PlanMessage: { icon: "layers", tone: "neutral", label: "Plan" },
  CandidateList: { icon: "filter", tone: "neutral", label: "Candidates" },
  VerifyRequest: { icon: "shield", tone: "warning", label: "Verify" },
  VerifyResult: { icon: "shield", tone: "supported", label: "Verdict" },
  ServiceCall: { icon: "arrow-up-right", tone: "neutral", label: "Call" },
  ServiceResult: { icon: "check", tone: "supported", label: "Result" },
  Feedback: { icon: "history", tone: "neutral", label: "Feedback" },
  TrustUpdate: { icon: "activity", tone: "neutral", label: "Trust" },
  MapResult: { icon: "map", tone: "neutral", label: "Map" },
  DriftAlert: { icon: "alert", tone: "contradicted", label: "Drift" },
};

function verificationStatuses(message) {
  const overall = message.overall;
  if (overall && typeof overall === "object" && !Array.isArray(overall)) {
    return Object.values(overall).map((value) => String(value || "Unverified"));
  }
  if (Array.isArray(overall)) return overall.map((value) => String(value || "Unverified"));
  return overall ? [String(overall)] : [];
}

function verificationLabelCount(message) {
  const labels = message.labels;
  if (Array.isArray(labels)) return labels.length;
  if (labels && typeof labels === "object") {
    return Object.values(labels).reduce(
      (total, records) => total + (Array.isArray(records) ? records.length : 0),
      0
    );
  }
  return 0;
}

function protocolSummary(message) {
  const kind = String(message.kind || "Message");
  if (kind === "TaskRequest") return truncate(message.task || "Task submitted", 160);
  if (kind === "PlanMessage") {
    const steps = message.plan?.steps || message.steps || [];
    return `${steps.length} step${steps.length === 1 ? "" : "s"} planned`;
  }
  if (kind === "CandidateList") return `${(message.candidates || []).length} candidates · ${message.capability || "capability"}`;
  if (kind === "VerifyRequest") return `${(message.candidates || []).length} candidates for ${message.subgoal_id || "subgoal"}`;
  if (kind === "VerifyResult") {
    const statuses = verificationStatuses(message);
    const tallies = statuses.reduce((counts, status) => {
      const key = status.toLowerCase();
      counts[key] = (counts[key] || 0) + 1;
      return counts;
    }, {});
    const outcome = Object.entries(tallies)
      .map(([status, count]) => `${count} ${status}`)
      .join(" · ");
    const labelCount = verificationLabelCount(message);
    const drift = (message.drift_alerts || []).length;
    return `${statuses.length} candidate${statuses.length === 1 ? "" : "s"}${outcome ? ` · ${outcome}` : ""} · ${labelCount} claim label${labelCount === 1 ? "" : "s"} · ${drift} drift alert${drift === 1 ? "" : "s"}`;
  }
  if (kind === "ServiceCall") {
    const params = Object.keys(message.params || {});
    return `${message.tool_id || "tool"} · ${params.length} parameter${params.length === 1 ? "" : "s"} bound`;
  }
  if (kind === "ServiceResult") {
    return `${message.tool_id || "tool"} · ${message.status || "unknown"} · ${formatNumber(message.latency_ms || 0, 1)} ms${message.cached ? " · cache hit" : ""}${message.error ? ` · ${message.error}` : ""}`;
  }
  if (kind === "TrustUpdate") {
    return `${message.provider_id || "provider"} · ${message.signal || "signal"} · ${message.success ? "success" : "failure"} · weight ${formatNumber(message.weight || 0, 2)}`;
  }
  if (kind === "Feedback") {
    return `${message.tool_id || "tool"} · ${message.outcome || "unknown"} · schema ${message.schema_valid ? "valid" : "invalid"}`;
  }
  if (kind === "MapResult") {
    return `${message.tool_id || "tool"} · ${(message.violations || []).length} violation${(message.violations || []).length === 1 ? "" : "s"}`;
  }
  if (kind === "DriftAlert") return `${message.tool_id || "tool"} · ${message.severity || "high"} · ${(message.reasons || []).join("; ") || "drift detected"}`;
  return `${message.sender || "sender"} → ${message.recipient || "recipient"}`;
}

function protocolTone(message) {
  if (message.kind === "ServiceResult") return message.status === "success" ? "supported" : "contradicted";
  if (message.kind === "VerifyResult") {
    const statuses = verificationStatuses(message).map((status) => status.toLowerCase());
    if (!statuses.length) return "neutral";
    const passed = statuses.every((status) => status === "verified" || status === "supported");
    const failed = statuses.every((status) => status === "unsupported" || status === "contradicted");
    return passed ? "supported" : failed ? "contradicted" : "warning";
  }
  if (message.kind === "Feedback") return message.outcome === "success" ? "supported" : "contradicted";
  if (message.kind === "TrustUpdate") return message.success ? "supported" : "contradicted";
  if (message.kind === "DriftAlert") return "contradicted";
  return PROTOCOL_KINDS[message.kind]?.tone || "neutral";
}

function renderProtocolMessages(messages) {
  const body = $("#protocol-body");
  const count = $("#protocol-count");
  if (!body) return;
  if (!messages || !messages.length) {
    if (count) count.textContent = "No messages";
    body.className = "empty-state inline";
    body.innerHTML = `${icon("layers")}<strong>No protocol messages</strong><p>Run a task to inspect every request and response envelope.</p>`;
    return;
  }
  if (count) count.textContent = `${messages.length} message${messages.length === 1 ? "" : "s"}`;
  body.className = "";
  body.innerHTML = `<div class="protocol-list">${messages
    .map((message) => {
      const meta = PROTOCOL_KINDS[message.kind] || { icon: "layers", label: message.kind };
      return `<div class="protocol-message">
        <time>${formatTime(message.timestamp)}</time>
        <span class="message-flow">${esc(message.sender || "?")}<svg><use href="#i-arrow-up-right"></use></svg>${esc(message.recipient || "?")}</span>
        <div class="message-summary"><span class="mono">${esc(meta.label)}</span> ${esc(protocolSummary(message))}
          <details><summary>Envelope</summary><pre>${esc(JSON.stringify(message, null, 2))}</pre></details>
        </div>
        <span class="badge ${protocolTone(message)}">${esc(message.kind || "Message")}</span>
      </div>`;
    })
    .join("")}</div>`;
}

async function loadProtocolMessages(taskId) {
  const body = $("#protocol-body");
  const count = $("#protocol-count");
  if (!body || !taskId) return;
  state.protocolTaskId = taskId;
  body.className = "";
  body.innerHTML = `<div class="loading-line">${icon("loader")}Loading task protocol…</div>`;
  if (count) count.textContent = "Loading…";
  try {
    const data = await api(`/api/tasks/${encodeURIComponent(taskId)}/messages`);
    state.protocolMessages = data.messages || [];
    state.protocolError = null;
    renderProtocolMessages(state.protocolMessages);
  } catch (error) {
    state.protocolMessages = null;
    state.protocolError = error.message;
    if (count) count.textContent = "Unavailable";
    body.className = "";
    body.innerHTML = noticeMarkup("error", "Task protocol unavailable.", error.message);
  }
}

function bindProtocol() {
  $("#protocol-refresh")?.addEventListener("click", () => {
    if (!state.protocolTaskId) {
      toast("Run a task to inspect its protocol messages.", "bad");
      return;
    }
    loadProtocolMessages(state.protocolTaskId);
  });
}

function scrollToPageHash() {
  const id = window.location.hash.replace(/^#/, "");
  if (!id) return;
  const target = document.getElementById(id);
  if (!target) return;
  window.requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
}

async function bootstrap() {
  setActivePage();
  bindTheme();
  bindSidebar();
  bindModals();
  bindPalette();
  bindTrace();
  bindDocuments();
  bindOnboarding();
  bindProtocol();
  await Promise.allSettled([
    loadHealth(),
    loadToolsData(),
    loadOntologyData(),
    loadMonitoringData(),
    loadAuditorData(),
  ]);
  if (state.page === "dashboard") initDashboard();
  if (state.page === "marketplace") initMarketplace();
  if (state.page === "monitor") {
    await loadMonitorActivity();
    initMonitor();
  }
  if (state.page === "library") {
    await Promise.allSettled([loadKnowledgeData(), loadStagedData(), loadEvaluationsData()]);
    initTrustCenter();
  }
  if (state.page === "documents") await initDocumentsPage();
  if (state.page === "docs") scrollToPageHash();
  if (state.page !== "dashboard") bindHistory();
}

document.addEventListener("DOMContentLoaded", bootstrap);
