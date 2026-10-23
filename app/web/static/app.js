const state = {
  page: window.__PAGE__ || document.body.dataset.page || "dashboard",
  health: null,
  tools: [],
  ontology: null,
  monitoring: null,
  result: null,
  documents: [],
  recent: [],
  monitorActivity: [],
  monitorDetails: [],
  monitorSelected: null,
  monitorPaused: false,
  marketQuery: "",
  marketCapability: "all",
  marketSort: "trust",
  selectedTraceSeq: null,
  lastFocused: null,
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

function clamp(value, minimum = 0, maximum = 100) {
  return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function claimClass(label) {
  const normalized = String(label || "Unsupported").toLowerCase();
  return ["verified", "supported", "contradicted", "unsupported"].includes(normalized)
    ? normalized
    : "neutral";
}

function claimIcon(label) {
  const normalized = claimClass(label);
  if (normalized === "contradicted") return "x-circle";
  if (normalized === "unsupported") return "alert";
  return "shield";
}

function claimBadge(label) {
  const normalized = claimClass(label);
  return `<span class="badge ${normalized}">${icon(claimIcon(label))}${esc(label || "Unsupported")}</span>`;
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
  return ["Contradicted", "Verified", "Supported", "Unsupported"].find((label) => labels.includes(label)) || "Unsupported";
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
  $$(".modal.is-open").forEach((entry) => {
    if (entry !== modal) entry.classList.remove("is-open");
  });
  modal.classList.add("is-open");
  document.body.style.overflow = "hidden";
  if (id === "history-modal") loadHistory();
  if (id === "documents-modal") loadDocuments();
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
  $$(".modal.is-open").forEach((modal) => modal.classList.remove("is-open"));
  document.body.style.overflow = "";
}

function loadHealth() {
  return api("/api/health")
    .then((health) => {
      state.health = health;
      const date = new Date().toLocaleDateString([], { day: "2-digit", month: "short" });
      const chip = $("#demo-date");
      if (chip) {
        chip.textContent = `${health.mode === "offline" ? "Demo" : "Live"} · ${date}`;
        chip.title = `${health.tools} tools · ${health.llm_enabled ? "LLM planner" : "deterministic planner"}`;
      }
      return health;
    })
    .catch((error) => {
      toast(`Health check failed: ${error.message}`, "bad");
      return null;
    });
}

function loadToolsData() {
  return api("/api/tools")
    .then((data) => {
      state.tools = data.tools || [];
      return state.tools;
    })
    .catch((error) => {
      toast(`Tool catalogue unavailable: ${error.message}`, "bad");
      return state.tools;
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
      return data;
    })
    .catch((error) => {
      toast(`Monitoring unavailable: ${error.message}`, "bad");
      return state.monitoring;
    });
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
  $("#mobile-menu")?.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
  $("#sidebar-scrim")?.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
  $("#workspace-switcher")?.addEventListener("click", () => toast("This sandbox uses a single demo workspace."));
  $("#notification-button")?.addEventListener("click", () => {
    if (state.page === "monitor") {
      $("#alert-feed")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      window.location.href = "/monitor";
    }
  });
}

function bindTheme() {
  $$("[data-set-theme]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.setTheme));
  });
  $("#toolbar-theme")?.addEventListener("click", toggleTheme);
  applyTheme(currentTheme());
}

function bindWindowControls() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-window-action]");
    if (!button) return;
    const card = button.closest(".window-card");
    if (!card) return;
    const action = button.dataset.windowAction;
    if (action === "minimize") card.classList.toggle("is-collapsed");
    if (action === "maximize") card.classList.toggle("is-maximized");
    if (action === "close") card.classList.add("is-closed");
  });
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
    if (event.key === "Escape") closeAllModals();
  });
}

function allSearchEntries(query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [];
  const tools = state.tools
    .filter((tool) =>
      [
        tool.name,
        tool.id,
        tool.provider_id,
        tool.capability,
        tool.description,
        ...(tool.keywords || []),
        ...(tool.tags || []),
        ...(tool.inputs || []).map((input) => input.concept),
        ...(tool.outputs || []).map((output) => output.concept),
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    )
    .slice(0, 6)
    .map((tool) => ({ kind: "tool", id: tool.id, name: tool.name, meta: `${tool.capability} · ${tool.provider_id}` }));
  const capabilities = Object.entries(state.ontology?.capabilities || {})
    .filter(([name, capability]) =>
      `${name} ${capability.description} ${(capability.inputs || []).join(" ")} ${(capability.outputs || []).join(" ")}`
        .toLowerCase()
        .includes(normalized)
    )
    .slice(0, 3)
    .map(([name, capability]) => ({
      kind: "capability",
      id: name,
      name,
      meta: `${(capability.inputs || []).length} inputs · ${(capability.outputs || []).length} outputs`,
    }));
  return [...tools, ...capabilities];
}

function renderGlobalSearch(query) {
  const panel = $("#global-search-results");
  if (!panel) return;
  const results = allSearchEntries(query);
  if (!query.trim()) {
    panel.classList.remove("is-open");
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = results.length
    ? results
        .map(
          (entry) => `<button class="search-result" type="button" data-search-kind="${entry.kind}" data-search-id="${esc(entry.id)}">
            ${icon(entry.kind === "capability" ? "layers" : capabilityIcon(state.tools.find((tool) => tool.id === entry.id)?.capability))}
            <span><strong>${esc(entry.name)}</strong><small>${esc(entry.meta)}</small></span>
          </button>`
        )
        .join("")
    : `<div class="search-result"><span><strong>No matches</strong><small>Try a capability, tool or ontology concept.</small></span></div>`;
  panel.classList.add("is-open");
}

function bindGlobalSearch() {
  const input = $("#global-search");
  const panel = $("#global-search-results");
  if (!input || !panel) return;
  input.addEventListener("input", () => renderGlobalSearch(input.value));
  input.addEventListener("focus", () => {
    if (input.value.trim()) renderGlobalSearch(input.value);
  });
  panel.addEventListener("click", (event) => {
    const result = event.target.closest("[data-search-kind]");
    if (!result) return;
    panel.classList.remove("is-open");
    const id = result.dataset.searchId;
    if (result.dataset.searchKind === "tool") {
      openToolModal(id);
    } else {
      window.location.href = `/marketplace?capability=${encodeURIComponent(id)}`;
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".toolbar-search")) panel.classList.remove("is-open");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
      event.preventDefault();
      input.focus();
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
  if ($("#source-count")) $("#source-count").innerHTML = `${icon("shield")}0 verified sources`;
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
  if (sourceCount) sourceCount.innerHTML = `${icon("shield")}${evidenceCount} evidence-backed source${evidenceCount === 1 ? "" : "s"}`;
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

function initDashboard() {
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
  const closed = Math.max(0, tools.length - open - half);
  const trust = providers.length
    ? providers.reduce((total, provider) => total + Number(provider.trust || 0), 0) / providers.length
    : 0;
  return `
    <div class="catalogue-stat"><strong>${tools.length}</strong><span>Registered<br>services</span></div>
    <div class="catalogue-stat closed"><strong>${closed}</strong><span>Closed<br>circuits</span></div>
    <div class="catalogue-stat ${open ? "open" : "closed"}"><strong>${open}</strong><span>Open<br>circuits</span></div>
    <div class="catalogue-stat"><strong>${formatTrust(trust)}</strong><span>Average live<br>trust</span></div>`;
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
}

function filteredTools() {
  const query = state.marketQuery.trim().toLowerCase();
  return state.tools
    .filter((tool) => {
      if (state.marketCapability !== "all" && tool.capability !== state.marketCapability) return false;
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
      return Number(right.trust || 0) - Number(left.trust || 0);
    });
}

function toolCard(tool) {
  const provider = providerForTool(tool.id);
  const claim = claimLabelForTool(tool.id);
  const breaker = breakerClass(tool.breaker || "closed");
  const trust = Number(tool.trust || 0);
  const calls = Number(provider?.calls || 0);
  const probes = Number(provider?.probes || 0);
  const contradictions = Number(provider?.contradictions || 0);
  const schema = `${(tool.inputs || []).map((input) => input.concept).join(" + ") || "No inputs"} → ${(tool.outputs || []).map((output) => output.concept).join(" + ") || "No outputs"}`;
  return `<article class="window-card tool-card ${esc(breaker)}" data-tool-id="${esc(tool.id)}" tabindex="0" role="button" aria-label="Inspect ${esc(tool.name)}">
    <div class="mini-window-bar"><span>service / ${esc(tool.provider_id)}</span><span><i></i><i></i><i></i></span></div>
    <div class="window-body">
      <div class="tool-card-heading">
        <span class="tool-icon">${icon(capabilityIcon(tool.capability))}</span>
        <span class="tool-title"><strong>${esc(tool.name)}</strong><small>${esc(tool.capability)}</small></span>
        ${icon("arrow-up-right")}
      </div>
      <p class="tool-description">${esc(tool.description)}</p>
      <div class="tool-claim-row">${claimBadge(claim)}<span class="tool-probe">${probes} probes · ${calls} calls</span></div>
      <div>
        <div class="trust-label-row"><span>Live trust score</span><strong>${formatTrust(trust)}</strong></div>
        <div class="trust-track ${breaker === "half-open" ? "half" : breaker}"><span style="width:${clamp(trust * 100)}%"></span></div>
        <div class="trust-counts">${calls} calls · ${contradictions} contradiction${contradictions === 1 ? "" : "s"} · ${tool.price ? `$${formatNumber(tool.price, 2)}` : "free sandbox"}</div>
      </div>
      <div class="breaker-line"><span>Circuit breaker</span>${breakerMarkup(breaker)}</div>
      <div class="tool-code">${esc(schema)}</div>
    </div>
  </article>`;
}

function renderMarketplace() {
  const stats = $("#catalogue-stats");
  if (stats) stats.innerHTML = catalogueStats();
  renderCapabilityControls();
  const grid = $("#tools-grid");
  const tools = filteredTools();
  if (grid) grid.innerHTML = tools.map(toolCard).join("");
  $("#tools-empty")?.classList.toggle("hidden", tools.length > 0);
  const footerCount = $("#market-footer-count");
  if (footerCount) footerCount.textContent = `${tools.length} of ${state.tools.length}`;
  const sync = $("#market-sync-time");
  if (sync) sync.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function initMarketplace() {
  const params = new URLSearchParams(window.location.search);
  state.marketCapability = params.get("capability") || "all";
  const search = $("#market-search");
  if (search) {
    search.value = state.marketQuery;
    search.addEventListener("input", () => {
      state.marketQuery = search.value;
      renderMarketplace();
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
    });
  }
  $("#capability-filter")?.addEventListener("change", (event) => {
    state.marketCapability = event.target.value;
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

function openToolModal(toolId) {
  const tool = toolById(toolId);
  if (!tool) {
    toast("This tool is not in the loaded catalogue.", "bad");
    return;
  }
  const provider = providerForTool(tool.id);
  const firstInput = tool.inputs?.[0];
  const claim = claimLabelForTool(tool.id);
  const breaker = breakerClass(tool.breaker || "closed");
  const objectives = Object.keys(state.ontology?.capabilities || {}).sort();
  const route = $("#tool-modal-route");
  if (route) route.textContent = `service / ${tool.id}`;
  const body = $("#tool-modal-body");
  if (!body) return;
  body.innerHTML = `<div class="tool-modal-top">
      <span class="tool-icon">${icon(capabilityIcon(tool.capability))}</span>
      <div><h2>${esc(tool.name)}</h2><p>${esc(tool.provider_id)} · ${esc(tool.capability)} · ${esc(tool.execution)}</p></div>
    </div>
    <div class="detail-grid">
      <div class="detail-block"><span>Live trust</span><strong>${formatTrust(tool.trust)}</strong><small>${provider?.calls || 0} calls · ${provider?.probes || 0} probes · ${provider?.contradictions || 0} contradictions</small></div>
      <div class="detail-block"><span>Circuit breaker</span><strong>${titleCase(breaker)}</strong><small>${provider?.failure_mode ? `failure mode: ${esc(provider.failure_mode)}` : "link-level isolation"}</small></div>
      <div class="detail-block"><span>Evidence label</span><strong>${claim}</strong><small>${tool.claims?.length || 0} provider claim${tool.claims?.length === 1 ? "" : "s"} on record</small></div>
      <div class="detail-block"><span>Pricing</span><strong>${tool.price ? `$${formatNumber(tool.price, 2)}` : "Free / sandbox"}</strong><small>${esc((tool.tags || []).join(" · ") || "No tags")}</small></div>
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
    <details class="correction-details">
      <summary>Suggest an ontology correction</summary>
      <form class="correction-form" id="tool-correction-form" data-tool-id="${esc(tool.id)}" data-original="${esc(firstInput?.concept || "")}">
        <div class="form-grid">
          <label>Field name<input id="correction-field" required value="${esc(firstInput?.name || "")}" placeholder="forecast"></label>
          <label>Corrected concept<select id="correction-concept" required>${objectives
            .map((concept) => `<option value="${esc(concept)}"${concept === firstInput?.concept ? " selected" : ""}>${esc(concept)}</option>`)
            .join("")}</select></label>
          <label>Unit<input id="correction-unit" value="${esc(firstInput?.unit || "")}" placeholder="C"></label>
          <label>Note<input id="correction-note" placeholder="Why should the mapping change?"></label>
        </div>
        <button class="btn secondary small" type="submit">Stage correction</button>
        <div class="inline-result hidden" id="tool-correction-result"></div>
      </form>
    </details>
    <div class="tool-modal-footer">
      ${tool.docs_url ? `<a class="text-link" href="${esc(tool.docs_url)}" target="_blank" rel="noreferrer">Provider docs ${icon("arrow-up-right")}</a>` : `<span class="muted small">No provider documentation URL</span>`}
      <button class="btn primary" type="button" data-use-tool="${esc(tool.id)}">${icon("play")}Use in a task</button>
    </div>`;
  $("#tool-correction-form")?.addEventListener("submit", submitToolCorrection);
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
  const payload = {
    tool_id: form.dataset.toolId,
    field_name: $("#correction-field")?.value.trim() || "",
    original_concept: form.dataset.original || "",
    corrected_concept: $("#correction-concept")?.value || "",
    corrected_unit: $("#correction-unit")?.value.trim() || null,
    note: $("#correction-note")?.value.trim() || "",
  };
  try {
    const result = await api("/api/corrections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    output.classList.remove("hidden", "bad");
    output.classList.toggle("bad", !result.accepted);
    output.textContent = result.accepted
      ? `Staged ${result.correction_id}. ${result.message}`
      : `Rejected: ${(result.violations || []).join("; ")}`;
    toast(result.accepted ? "Correction staged for the Mapper." : "Correction rejected.", result.accepted ? "ok" : "bad");
  } catch (error) {
    output.classList.remove("hidden");
    output.classList.add("bad");
    output.textContent = error.message;
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
    setQueueRow(
      "shacl",
      accepted ? "done" : "failed",
      (result.violations || []).length ? result.violations.join("; ") : "Mapped shape accepted",
      accepted ? "Passed" : "Rejected"
    );
    if (queueStatus) {
      queueStatus.className = `badge ${accepted ? "verified" : "contradicted"}`;
      queueStatus.innerHTML = `${icon(accepted ? "check" : "x")}${accepted ? (staged ? "Staged" : "Accepted") : "Rejected"}`;
    }
    if (resultBox) {
      resultBox.classList.remove("hidden");
      resultBox.classList.toggle("bad", !accepted);
      resultBox.textContent = accepted
        ? `Listing ${staged ? "staged" : "accepted"} as ${result.tool_id}. The Mapper will review the typed mapping before publication.`
        : `Rejected: ${(result.violations || ["The mapped shape did not pass validation."]).join("; ")}`;
    }
    toast(accepted ? "Listing staged for mapper review." : "Listing rejected by validation.", accepted ? "ok" : "bad");
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

function loadDocuments() {
  return api("/api/documents")
    .then((data) => {
      state.documents = data.documents || [];
      const list = $("#document-list");
      if (list) {
        list.innerHTML = state.documents.length
          ? state.documents
              .map(
                (document) => `<div class="document-item"><span>${esc(document.name)}</span><small>${formatNumber(document.text_chars, 0)} chars · ${esc(document.document_id)}</small></div>`
              )
              .join("")
          : `<div class="document-item"><span class="muted">No uploaded documents. A seeded project brief is used by default.</span></div>`;
      }
      return state.documents;
    })
    .catch((error) => {
      toast(`Documents unavailable: ${error.message}`, "bad");
      return state.documents;
    });
}

async function uploadDocument(event) {
  event.preventDefault();
  const input = $("#document-file");
  const file = input?.files?.[0];
  const output = $("#upload-result");
  if (!file || !output) return;
  const form = new FormData();
  form.append("file", file);
  try {
    const result = await api("/api/documents", { method: "POST", body: form });
    output.classList.remove("hidden", "bad");
    output.textContent = `Uploaded ${result.document.name} (${result.document.document_id}) with ${formatNumber(result.document.text_chars, 0)} characters.`;
    toast("Document uploaded.", "ok");
    if (input) input.value = "";
    await loadDocuments();
  } catch (error) {
    output.classList.remove("hidden");
    output.classList.add("bad");
    output.textContent = error.message;
  }
}

function askDocument(event) {
  event.preventDefault();
  const question = $("#document-question")?.value.trim() || "";
  if (!question) return;
  const task = question.toLowerCase().startsWith("according")
    ? question
    : `According to the uploaded document, ${question}`;
  closeAllModals();
  if (state.page === "dashboard") {
    const input = $("#task-input");
    if (input) {
      input.value = task;
      resizeTaskInput();
    }
    runTask(task);
  } else {
    try {
      localStorage.setItem("agent-bazaar-task", task);
    } catch (error) {
      toast("Could not stage the document question.", "bad");
      return;
    }
    window.location.href = "/dashboard";
  }
}

function bindDocuments() {
  $("#upload-form")?.addEventListener("submit", uploadDocument);
  $("#document-question-form")?.addEventListener("submit", askDocument);
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
  if (!events.length) {
    const providerCount = monitoring.providers?.length || state.tools.length;
    events.push({
      key: "standby-schema",
      kind: "standby",
      time: null,
      severity: "info",
      title: "Schema monitors armed",
      description: `All ${providerCount} provider links are inside their mapped output contracts.`,
      tags: ["Auditor", "0 alerts"],
      toolId: null,
      data: {},
    });
    events.push({
      key: "standby-breaker",
      kind: "standby",
      time: null,
      severity: "low",
      title: "Circuit breakers closed",
      description: "No provider has crossed the failure threshold in this sandbox session.",
      tags: ["Client", "Protected"],
      toolId: null,
      data: {},
    });
  }
  const severityRank = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
  return events.sort((left, right) => {
    const timeDelta = new Date(right.time || 0) - new Date(left.time || 0);
    return timeDelta || (severityRank[right.severity] || 0) - (severityRank[left.severity] || 0);
  });
}

async function loadMonitorActivity() {
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
  }
  state.monitorActivity = monitorEvents();
}

function renderMonitorMetrics() {
  const monitoring = state.monitoring || {};
  const providers = monitoring.providers || [];
  const breakers = monitoring.breakers || [];
  const alerts = monitoring.drift_alerts || [];
  const open = breakers.filter((breaker) => breaker.state === "open").length;
  const trust = providers.length
    ? providers.reduce((total, provider) => total + Number(provider.trust || 0), 0) / providers.length
    : 0;
  const container = $("#monitor-metrics");
  if (!container) return;
  container.innerHTML = `
    <div class="metric-card">${icon("box")}<strong>${providers.length}</strong><label>Registered providers</label><small>${new Set(state.tools.map((tool) => tool.capability)).size} capabilities · sandbox</small></div>
    <div class="metric-card">${icon("shield")}<strong class="${open ? "alert" : "good"}">${open}</strong><label>Open circuits</label><small>${breakers.length} links monitored</small></div>
    <div class="metric-card">${icon("alert")}<strong class="${alerts.length ? "alert" : "good"}">${alerts.length}</strong><label>Drift alerts</label><small>Auditor contract checks</small></div>
    <div class="metric-card">${icon("pulse")}<strong class="good">${formatTrust(trust)}</strong><label>Average live trust</label><small>Beta posterior mean</small></div>`;
}

function selectedMonitorEvent() {
  return state.monitorActivity.find((event) => event.key === state.monitorSelected) || state.monitorActivity[0] || null;
}

function renderMonitorFeed() {
  const feed = $("#alert-feed");
  if (!feed) return;
  feed.innerHTML = state.monitorActivity
    .map(
      (event) => `<article class="feed-item ${event.key === state.monitorSelected ? "active" : ""}" data-monitor-event="${esc(event.key)}">
        <div class="feed-item-top">
          <span class="severity ${esc(event.severity)}">${icon(event.kind === "drift" ? "alert" : event.kind === "failure" ? "alert" : event.kind === "substitution" ? "refresh" : "pulse")}${esc(event.severity)}</span>
          <time>${event.time ? formatTime(event.time) : "now"}</time>
        </div>
        <strong>${esc(event.title)}</strong>
        <p>${esc(event.description)}</p>
        <div class="feed-tags">${event.tags.map((tag) => `<span class="badge neutral">${esc(tag)}</span>`).join("")}</div>
      </article>`
    )
    .join("");
  const count = $("#feed-count");
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
  if (!event || event.kind === "standby") {
    return `<div class="detail-card-head"><h3>Mapping diff</h3><span class="badge verified">${icon("check")}No drift</span></div>
      <div class="mapping-body">
        <div class="mapping-grid">
          <div class="mapping-panel"><span>Expected mapping</span><pre>${esc(expected)}</pre></div>
          <div class="mapping-panel positive"><span>Last validation</span><pre>${esc("schema_valid: true\nreason: all required fields matched\naction: accept")}</pre></div>
        </div>
        <div class="mapping-foot">${icon("shield")}SHACL and unit checks passed for the current catalogue snapshot.</div>
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
    container.innerHTML = `<div class="incident-empty"><span class="answer-icon">${icon("shield")}</span><div><h2>No active incidents</h2><p>Provider contracts are matching the current sandbox snapshot.</p></div><span class="badge verified">${icon("check")}Healthy</span></div>`;
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
          return `<div class="substitution-row"><time>${event.time ? formatTime(event.time) : "now"}</time><span class="log-tag ${tagClass}">${tag}</span><span>${esc(event.title)}</span></div>`;
        })
        .join("")
    : `<div class="substitution-row"><time>now</time><span class="log-tag match">Match</span><span>No failures or substitutions in this session.</span></div>`;
  const substitution = swaps.find((event) => event.kind === "substitution");
  const reason = substitution
    ? `<div class="swap-reason">${icon("check-circle")}<span>Type-compatible substitute accepted. The original provider remains isolated until validation recovers.</span></div>`
    : "";
  container.innerHTML = `<div class="detail-card-head"><h3>Recovery & substitution log</h3><span class="badge neutral">${swaps.length} event${swaps.length === 1 ? "" : "s"}</span></div><div class="substitution-body">${rows}${reason}</div>`;
}

function renderMonitor() {
  renderMonitorMetrics();
  renderMonitorFeed();
  renderMonitorIncident();
  renderMonitorMapping();
  renderMonitorSubstitutions();
  const notifications = $("#notification-button .notification-dot");
  const alerts = state.monitoring?.drift_alerts || [];
  const open = (state.monitoring?.breakers || []).some((breaker) => breaker.state === "open");
  notifications?.classList.toggle("hidden", !alerts.length && !open);
  const snapshot = $("#monitor-snapshot-time");
  if (snapshot) snapshot.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
  $("#simulate-drift")?.addEventListener("click", async () => {
    const button = $("#simulate-drift");
    if (button) button.disabled = true;
    try {
      await api("/api/demo/drift/open-meteo-forecast", { method: "POST" });
      toast("Schema drift injected on open-meteo-forecast.", "bad");
      await loadMonitoringData();
      await loadMonitorActivity();
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

function renderLibrary() {
  const template = $("#library-template");
  if (!template) return;
  $$(".library-frame").forEach((frame) => {
    const clone = template.content.cloneNode(true);
    const label = clone.querySelector("[data-library-label]");
    if (label) label.textContent = frame.dataset.libraryTheme || "theme";
    frame.replaceChildren(clone);
  });
}

async function bootstrap() {
  setActivePage();
  bindTheme();
  bindSidebar();
  bindWindowControls();
  bindModals();
  bindGlobalSearch();
  bindTrace();
  bindDocuments();
  bindOnboarding();
  await Promise.allSettled([loadHealth(), loadToolsData(), loadOntologyData(), loadMonitoringData()]);
  if (state.page === "dashboard") initDashboard();
  if (state.page === "marketplace") initMarketplace();
  if (state.page === "monitor") {
    await loadMonitorActivity();
    initMonitor();
  }
  if (state.page === "library") renderLibrary();
  if (state.page !== "dashboard") bindHistory();
}

document.addEventListener("DOMContentLoaded", bootstrap);
