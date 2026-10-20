const state = {
  result: null,
  monitoring: null,
  tools: [],
  documents: [],
  health: null,
};

const examples = [
  {
    label: "Weather + currency",
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

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function badge(label, extra = "") {
  const normalized = String(label || "Unsupported").toLowerCase();
  const css = ["verified", "supported", "contradicted", "unsupported", "open", "closed", "half-open", "neutral"].includes(normalized)
    ? normalized
    : "neutral";
  return `<span class="badge ${css} ${extra}">${esc(label)}</span>`;
}

function breakerBadge(value) {
  const normalized = String(value || "closed").toLowerCase();
  return `<span class="badge ${normalized}">${esc(value)}</span>`;
}

function scoreBadge(value) {
  return `<span class="mono">${Number(value || 0).toFixed(2)}</span>`;
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString() : esc(value);
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return esc(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
  element.textContent = message;
  element.className = `toast ${kind}`.trim();
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => element.classList.add("hidden"), 3800);
}

function switchTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
  if (name === "trace") {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function renderExamples() {
  const container = $("#examples");
  container.innerHTML = examples
    .map(
      (item) =>
        `<button type="button" class="example" data-task="${esc(item.text)}">${esc(item.label)}</button>`
    )
    .join("");
  container.addEventListener("click", async (event) => {
    const button = event.target.closest(".example");
    if (!button) return;
    $("#task-input").value = button.dataset.task;
    await submitTask(button.dataset.task);
  });
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    state.health = health;
    const chip = $("#mode-chip");
    chip.textContent = health.mode === "offline" ? "Offline demo mode" : "Live mode";
    chip.className = `chip chip-mode ${health.mode}`;
    $("#tool-count").textContent = `${health.tools} tools`;
    $("#llm-chip").textContent = health.llm_enabled ? "LLM planner enabled" : "Deterministic fallback";
  } catch (error) {
    toast(`Health check failed: ${error.message}`, "bad");
  }
}

async function submitTask(taskText) {
  const task = String(taskText || $("#task-input").value || "").trim();
  if (task.length < 3) {
    toast("Enter a task first.", "bad");
    return;
  }
  $("#task-input").value = task;
  const button = $("#run-button");
  button.disabled = true;
  $("#task-status").classList.remove("hidden");
  try {
    const result = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    state.result = result;
    renderResult(result);
    await loadMonitoring();
    switchTab("workbench");
    const message =
      result.status === "completed"
        ? "Chain completed."
        : result.status === "partial"
          ? "Chain partially completed."
          : "Chain failed. See the trace for the reason.";
    toast(message, result.status === "completed" ? "ok" : result.status === "partial" ? "" : "bad");
  } catch (error) {
    toast(`Task failed: ${error.message}`, "bad");
  } finally {
    button.disabled = false;
    $("#task-status").classList.add("hidden");
  }
}

function renderResult(result) {
  $("#answer-panel").classList.remove("hidden");
  $("#answer-status").textContent =
    result.status === "completed"
      ? "Completed"
      : result.status === "partial"
        ? "Partially completed"
        : "Failed";
  const meta = [];
  meta.push(badge(result.status === "completed" ? "Verified path" : result.status, "neutral"));
  meta.push(`<span class="chip">${esc(result.mode)}</span>`);
  meta.push(`<span class="chip">${formatNumber(result.metrics?.total_ms || result.duration_ms)} ms</span>`);
  meta.push(`<span class="chip">${result.trace?.length || 0} trace events</span>`);
  $("#answer-meta").innerHTML = meta.join("");
  $("#answer-text").textContent = result.answer || "No answer returned.";
  const warnings = result.warnings || [];
  const warningBox = $("#answer-warnings");
  if (warnings.length) {
    warningBox.classList.remove("hidden");
    warningBox.innerHTML = `<strong>Evidence notes</strong><ul>${warnings
      .map((warning) => `<li>${esc(warning)}</li>`)
      .join("")}</ul>`;
  } else {
    warningBox.classList.add("hidden");
  }
  renderCandidates(result);
  renderChain(result);
  renderTrace(result.trace || []);
}

function renderCandidates(result) {
  const panel = $("#candidates-panel");
  const groups = result.candidate_lists || [];
  if (!groups.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const plan = result.plan;
  const selectedBySubgoal = {};
  (plan?.steps || []).forEach((step) => {
    selectedBySubgoal[step.subgoal_id] = step.tool_id;
  });
  const container = $("#candidate-groups");
  container.innerHTML = groups
    .map((group) => {
      const candidates = group.candidates || [];
      const selectedTool = selectedBySubgoal[group.subgoal_id];
      const cards = candidates
        .map((candidate) => {
          const tool = candidate.tool || {};
          const claims = tool.claims || [];
          const selected = selectedTool === tool.id;
          const reasons = (candidate.reasons || [])
            .map((reason) => `<li>${esc(reason)}</li>`)
            .join("");
          const claimRows = claims
            .map(
              (claim) => `
                <div class="claim-row">
                  ${badge(claim.label || "Unsupported")}
                  <div>
                    <div>${esc(claim.text)}</div>
                    <div class="muted">${esc(claim.evidence || "")}</div>
                  </div>
                </div>`
            )
            .join("");
          const width = Math.max(0, Math.min(100, Number(candidate.score || 0) * 100));
          return `
            <article class="candidate ${selected ? "selected" : ""} ${candidate.eligible ? "" : "ineligible"}">
              <div class="rank">${candidate.rank || "-"}</div>
              <div>
                <div class="candidate-title">
                  <strong>${esc(tool.name || tool.id)}</strong>
                  ${badge(candidate.claim_label)}
                  ${selected ? '<span class="badge neutral">selected</span>' : ""}
                  ${candidate.demoted ? '<span class="badge contradicted">demoted</span>' : ""}
                  ${candidate.breaker_state === "open" ? '<span class="badge open">breaker open</span>' : ""}
                </div>
                <div class="provider">${esc(tool.provider_id)} / ${esc(tool.capability)}</div>
                <div class="candidate-desc">${esc(tool.description)}</div>
                <div class="score-line">
                  <span>score ${Number(candidate.score || 0).toFixed(3)}</span>
                  <span class="score-bar"><span style="width:${width}%"></span></span>
                  <span>relevance ${Number(candidate.relevance || 0).toFixed(2)}</span>
                  <span>price ${Number(tool.price || 0).toFixed(2)}</span>
                </div>
              </div>
              <div class="candidate-side">
                <span class="trust-number">trust ${Number(candidate.trust || 0).toFixed(3)}</span>
                ${breakerBadge(candidate.breaker_state)}
              </div>
              <ul class="reasons">${reasons}</ul>
              <details class="claim-detail">
                <summary>${claims.length} claim(s) and evidence</summary>
                ${claimRows || '<p class="muted">No claims recorded.</p>'}
              </details>
            </article>`;
        })
        .join("");
      return `
        <div class="candidate-group">
          <div class="group-head">
            <h3>${esc(group.capability)}</h3>
            <code>${esc(group.subgoal_id)} / ${candidates.length} candidates</code>
          </div>
          ${cards || '<div class="empty-state">No candidate survived the filters.</div>'}
        </div>`;
    })
    .join("");
}

function renderChain(result) {
  const panel = $("#chain-panel");
  const plan = result.plan;
  if (!plan || !plan.steps || !plan.steps.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const container = $("#chain-steps");
  container.innerHTML = plan.steps
    .map((step, index) => {
      const linkChecks = (step.link_checks || [])
        .map(
          (check) => `
            <div class="link-check ${check.valid ? "pass" : "fail"}">
              <strong>${check.valid ? "PASS" : "REJECT"}</strong>
              <div>
                <code>${esc(check.source_concept)}${check.source_unit ? ` (${esc(check.source_unit)})` : ""} &rarr; ${esc(check.target_concept)}${check.target_unit ? ` (${esc(check.target_unit)})` : ""}</code>
                <div>${esc(check.reason)}</div>
              </div>
            </div>`
        )
        .join("");
      const bindings = Object.entries(step.input_bindings || {})
        .map(([key, value]) => `<code>${esc(key)} = ${esc(value)}</code>`)
        .join("&nbsp;&nbsp;");
      const output = step.output
        ? `<details class="step-output"><summary>Provider output</summary><pre>${esc(JSON.stringify(step.output, null, 2))}</pre></details>`
        : "";
      return `
        <div class="chain-step ${esc(step.status)}" data-step="${index + 1}">
          <div class="step-head">
            <strong>${esc(step.tool_name || step.tool_id || "No tool")}</strong>
            ${badge(step.status, "neutral")}
            ${step.substituted_from ? `<span class="badge contradicted">substituted for ${esc(step.substituted_from)}</span>` : ""}
            <span class="provider">${esc(step.capability)}</span>
          </div>
          <div class="step-desc">${esc(step.tool_id)}</div>
          ${bindings ? `<div class="step-meta">${bindings}</div>` : ""}
          ${linkChecks ? `<div class="link-checks">${linkChecks}</div>` : ""}
          <div class="step-meta">
            <span class="chip">source ${esc(step.source || "not called")}</span>
            <span class="chip">${formatNumber(step.latency_ms)} ms</span>
            ${step.cached ? '<span class="chip">cache hit</span>' : ""}
            ${step.error ? `<span class="badge contradicted">${esc(step.error)}</span>` : ""}
          </div>
          ${output}
        </div>`;
    })
    .join("");
}

function renderTrace(events) {
  const empty = $("#trace-empty");
  const list = $("#trace-list");
  if (!events.length) {
    empty.classList.remove("hidden");
    list.innerHTML = "";
    return;
  }
  empty.classList.add("hidden");
  list.innerHTML = events
    .map((event) => {
      const hasData = event.data && Object.keys(event.data).length > 0;
      return `
        <div class="trace-item" data-type="${esc(event.event_type)}">
          <div class="trace-head">
            <span class="actor">#${event.seq} ${esc(event.actor)}</span>
            <strong>${esc(event.event_type)}</strong>
            <time>${formatTime(event.timestamp)}</time>
          </div>
          <p>${esc(event.summary)}</p>
          ${
            hasData
              ? `<details><summary>inputs and outputs</summary><pre>${esc(JSON.stringify(event.data, null, 2))}</pre></details>`
              : ""
          }
        </div>`;
    })
    .join("");
}

async function loadMonitoring() {
  try {
    const data = await api("/api/monitoring");
    state.monitoring = data;
    const providers = data.providers || [];
    const breakers = data.breakers || [];
    const open = breakers.filter((item) => item.state === "open").length;
    const demoted = providers.filter((item) => item.demoted).length;
    const alerts = data.drift_alerts || [];
    $("#monitor-summary").innerHTML = [
      ["Registered tools", providers.length],
      ["Open breakers", open],
      ["Demoted providers", demoted],
      ["Drift alerts", alerts.length],
    ]
      .map(
        ([label, value]) =>
          `<div class="metric-card"><span class="metric-label">${esc(label)}</span><span class="metric-value">${value}</span></div>`
      )
      .join("");

    $("#trust-table tbody").innerHTML = providers
      .map((provider) => {
        const breaker = breakers.find((item) => item.key.endsWith(`->${provider.provider_id}`));
        const status = provider.demoted
          ? badge("demoted", "contradicted")
          : breakerBadge(breaker ? breaker.state : "closed");
        return `<tr>
          <td><strong>${esc(provider.tool_name)}</strong><br><code>${esc(provider.provider_id)}</code></td>
          <td><span class="mono">${Number(provider.trust || 0.5).toFixed(3)}</span></td>
          <td>${formatNumber(provider.calls)}</td>
          <td>${status}${provider.fail_next ? ` <span class="badge contradicted">fail x${provider.fail_next}</span>` : ""}</td>
        </tr>`;
      })
      .join("");

    $("#breaker-table tbody").innerHTML = breakers.length
      ? breakers
          .map(
            (breaker) => `<tr>
              <td><code>${esc(breaker.key)}</code></td>
              <td>${breakerBadge(breaker.state)}</td>
              <td>${formatNumber(breaker.consecutive_failures)}</td>
              <td class="muted">${esc(breaker.last_error || "none")}</td>
            </tr>`
          )
          .join("")
      : '<tr><td colspan="4" class="muted">No links have been exercised yet.</td></tr>';

    const drift = $("#drift-list");
    drift.innerHTML = alerts.length
      ? alerts
          .map(
            (alert) => `<div class="drift-item">
              <strong>${esc(alert.tool_id)}</strong> / ${esc(alert.severity)}
              <div>${esc((alert.reasons || []).join("; "))}</div>
            </div>`
          )
          .join("")
      : '<p class="muted">No drift alerts.</p>';
  } catch (error) {
    toast(`Monitoring unavailable: ${error.message}`, "bad");
  }
}

async function loadTools() {
  try {
    const data = await api("/api/tools");
    state.tools = data.tools || [];
    const select = $("#correction-tool");
    select.innerHTML = state.tools
      .map((tool) => `<option value="${esc(tool.id)}">${esc(tool.name)}</option>`)
      .join("");
    $("#tools-table tbody").innerHTML = state.tools
      .map((tool) => {
        const claims = tool.claims || [];
        const label = claims.find((claim) => claim.label === "Contradicted")?.label ||
          claims.find((claim) => claim.label === "Verified")?.label ||
          claims.find((claim) => claim.label === "Supported")?.label ||
          claims[0]?.label ||
          "Unsupported";
        const validation = (tool.validation || []).length
          ? `<span class="badge contradicted">${tool.validation.length} violation(s)</span>`
          : '<span class="badge supported">valid</span>';
        return `<tr>
          <td><strong>${esc(tool.name)}</strong><br><code>${esc(tool.provider_id)}</code></td>
          <td><code>${esc(tool.capability)}</code><br>${validation}</td>
          <td>${badge(label)}</td>
          <td><span class="mono">${Number(tool.trust || 0.5).toFixed(3)}</span></td>
        </tr>`;
      })
      .join("");
    if (state.tools.length) {
      updateCorrectionDefaults();
    }
  } catch (error) {
    toast(`Tool catalogue unavailable: ${error.message}`, "bad");
  }
}

function updateCorrectionDefaults() {
  const toolId = $("#correction-tool").value;
  const tool = state.tools.find((item) => item.id === toolId);
  if (!tool) return;
  const firstInput = (tool.inputs || [])[0];
  if (!firstInput) return;
  $("#correction-field").value = firstInput.name || firstInput.concept;
  $("#correction-original").value = firstInput.concept;
  if (!$("#correction-concept").value) {
    $("#correction-concept").value = firstInput.concept;
  }
  if (!$("#correction-unit").value) {
    $("#correction-unit").value = firstInput.unit || "";
  }
}

async function loadDocuments() {
  try {
    const data = await api("/api/documents");
    state.documents = data.documents || [];
    const list = $("#document-list");
    list.innerHTML = state.documents.length
      ? state.documents
          .map(
            (document) => `<div class="document-item">
              <span>${esc(document.name)}</span>
              <span>${formatNumber(document.text_chars)} chars</span>
            </div>`
          )
          .join("")
      : '<p class="muted">No documents. A seeded project brief is used by default.</p>';
  } catch (error) {
    toast(`Documents unavailable: ${error.message}`, "bad");
  }
}

async function submitCorrection(event) {
  event.preventDefault();
  const payload = {
    tool_id: $("#correction-tool").value,
    field_name: $("#correction-field").value.trim(),
    original_concept: $("#correction-original").value.trim(),
    corrected_concept: $("#correction-concept").value.trim(),
    corrected_unit: $("#correction-unit").value.trim() || null,
    note: $("#correction-note").value.trim(),
  };
  const output = $("#correction-result");
  try {
    const result = await api("/api/corrections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    output.classList.remove("hidden", "ok", "bad");
    output.classList.add(result.accepted ? "ok" : "bad");
    output.textContent = result.accepted
      ? `Staged correction ${result.correction_id}. ${result.message}`
      : `Rejected: ${(result.violations || []).join("; ")}`;
    toast(result.accepted ? "Correction staged." : "Correction rejected.", result.accepted ? "ok" : "bad");
  } catch (error) {
    output.classList.remove("hidden");
    output.classList.add("bad");
    output.textContent = error.message;
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const file = $("#document-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const output = $("#upload-result");
  try {
    const result = await api("/api/documents", { method: "POST", body: form });
    output.classList.remove("hidden", "ok", "bad");
    output.classList.add("ok");
    output.textContent = `Uploaded ${result.document.name} (${result.document.document_id}) with ${formatNumber(result.document.text_chars)} characters.`;
    toast("Document uploaded.", "ok");
    await loadDocuments();
  } catch (error) {
    output.classList.remove("hidden");
    output.classList.add("bad");
    output.textContent = error.message;
  }
}

async function askDocument(event) {
  event.preventDefault();
  const question = $("#document-question").value.trim();
  if (!question) return;
  const task = question.toLowerCase().startsWith("according")
    ? question
    : `According to the uploaded document, ${question}`;
  switchTab("workbench");
  await submitTask(task);
}

function handleDemoClick(event) {
  const button = event.target.closest("[data-demo]");
  if (!button) return;
  const action = button.dataset.demo;
  const tool = button.dataset.tool;
  runDemoAction(action, tool);
}

async function runDemoAction(action, tool) {
  try {
    if (action === "reset") {
      if (!window.confirm("Reset trust, breakers, drift alerts and provider overrides?")) return;
      await api("/api/demo/reset", { method: "POST" });
      toast("Demo state reset.", "ok");
    } else if (action === "fail") {
      await api(`/api/demo/fail-next/${encodeURIComponent(tool)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ times: 1 }),
      });
      $("#task-input").value = examples[0].text;
      toast("Weather failure scheduled. Running the weather + currency demo.", "");
      await submitTask(examples[0].text);
    } else if (action === "drift") {
      await api(`/api/demo/drift/${encodeURIComponent(tool)}`, { method: "POST" });
      toast("Drift injected. The Auditor lowered trust and tripped the link.", "bad");
    } else if (action === "trip") {
      await api(`/api/demo/trip/${encodeURIComponent(tool)}`, { method: "POST" });
      toast("Circuit breaker tripped.", "bad");
    }
    await loadMonitoring();
  } catch (error) {
    toast(`Demo action failed: ${error.message}`, "bad");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  renderExamples();
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => switchTab(tab.dataset.tab)));
  $("#task-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitTask($("#task-input").value);
  });
  $("#correction-tool").addEventListener("change", updateCorrectionDefaults);
  $("#correction-form").addEventListener("submit", submitCorrection);
  $("#upload-form").addEventListener("submit", uploadDocument);
  $("#document-question-form").addEventListener("submit", askDocument);
  $("#panel-monitoring").addEventListener("click", handleDemoClick);
  await Promise.all([loadHealth(), loadMonitoring(), loadTools(), loadDocuments()]);
});
