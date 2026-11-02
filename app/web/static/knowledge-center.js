// Knowledge Center (Discovery) UI Extension
// This extends the main app.js with Knowledge Center functionality

(function() {
  "use strict";

  // Only run if the knowledge-center container exists
  if (!document.getElementById("knowledge-center")) return;

  const state = window.__STATE__ || {};
  
  // Section definitions
  const KNOWLEDGE_CENTER_SECTIONS = {
    specs: { label: "API Specifications", icon: "code-bracket", description: "Discovered and staged API specifications" },
    graph: { label: "Knowledge Graph", icon: "sitemap", description: "Concepts, capabilities, and relationships" },
    evidence: { label: "Evidence & Verification", icon: "shield-check", description: "Claims, probes, and verification results" },
    ingestion: { label: "Research & Ingestion", icon: "upload-cloud", description: "Upload specs or trigger discovery" }
  };

  // Escape HTML
  function esc(str) {
    if (!str) return "";
    return String(str).replace(/[&<>"']/g, function(c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Format time
  function formatTime(timestamp) {
    if (!timestamp) return "—";
    const date = new Date(timestamp);
    return date.toLocaleString();
  }

  // API helper
  async function api(path, options) {
    const opts = Object.assign({
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin"
    }, options || {});
    const response = await fetch(path, opts);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Request failed (${response.status})`);
    }
    return response.json();
  }

  // Toast notification
  function toast(message, kind) {
    const element = document.getElementById("toast");
    if (!element) return;
    element.textContent = message;
    element.className = "toast " + (kind || "");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function() { element.classList.add("hidden"); }, 4200);
  }

  // Load discovery data
  async function loadDiscoveryData() {
    try {
      const [staged, verified, sources] = await Promise.all([
        api("/api/discovery/staged").catch(function() { return { providers: [] }; }),
        api("/api/discovery/verified").catch(function() { return { providers: [] }; }),
        api("/api/discovery/sources").catch(function() { return { sources: [] }; })
      ]);
      window.__KC_STAGED__ = staged.providers || [];
      window.__KC_VERIFIED__ = verified.providers || [];
      window.__KC_SOURCES__ = sources.sources || [];
      renderAll();
    } catch (error) {
      toast("Failed to load discovery data: " + error.message, "bad");
    }
  }

  // Trigger discovery
  async function triggerDiscovery(sourceType, limit) {
    try {
      const result = await api("/api/discovery/run?source=" + encodeURIComponent(sourceType || "apis-guru") + "&limit=" + (limit || 20), { method: "POST" });
      toast("Discovered " + result.discovered + " new API specifications", "good");
      await loadDiscoveryData();
    } catch (error) {
      toast("Discovery failed: " + error.message, "bad");
    }
  }

  // Stage providers
  async function stageProviders(toolIds) {
    try {
      const result = await api("/api/discovery/stage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_ids: toolIds })
      });
      toast("Staged " + result.staged + " providers", "good");
      await loadDiscoveryData();
    } catch (error) {
      toast("Staging failed: " + error.message, "bad");
    }
  }

  // Verify providers
  async function verifyProviders(toolIds, force) {
    try {
      const result = await api("/api/discovery/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool_ids: toolIds, force: !!force })
      });
      toast("Verified " + result.verified + " providers", "good");
      await loadDiscoveryData();
    } catch (error) {
      toast("Verification failed: " + error.message, "bad");
    }
  }

  // Upload spec
  async function uploadSpec(file) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await api("/api/discovery/upload", { method: "POST", body: formData });
      toast((result.parsed ? "Uploaded and parsed " : "Uploaded ") + result.uploaded, "good");
      await loadDiscoveryData();
    } catch (error) {
      toast("Upload failed: " + error.message, "bad");
    }
  }

  // Render helpers
  function icon(name) {
    // Simple icon placeholder - use SVG inline or text
    const icons = {
      "code-bracket": "⟨/⟩",
      "sitemap": "☰",
      "shield-check": "✓",
      "upload-cloud": "↑",
      "globe": "🌐",
      "folder": "📁",
      "link": "🔗",
      "box": "▣",
      "x-circle": "✕"
    };
    return icons[name] || "?";
  }

  // Render discovery sources
  function renderDiscoverySources() {
    const container = document.getElementById("discovery-sources");
    if (!container) return;
    
    const sources = window.__KC_SOURCES__ || [];
    if (!sources.length) {
      container.innerHTML = '<p class="muted small">No discovery sources configured.</p>';
      return;
    }
    
    container.innerHTML = sources.map(function(source) {
      const isFetchable = source.type === "apis-guru" || source.type === "openapi-url";
      return (
        '<div class="source-card" data-source-type="' + esc(source.type) + '">' +
          '<div class="source-header">' +
            '<span class="source-icon">' + icon(source.type === "apis-guru" ? "globe" : source.type === "local" ? "folder" : "link") + '</span>' +
            '<div class="source-meta"><strong>' + esc(source.name) + '</strong><span class="source-type">' + esc(source.type) + '</span></div>' +
          '</div>' +
          '<p class="source-description">' + esc(source.description || "") + '</p>' +
          (source.specs_available !== undefined ? '<small class="source-count">' + source.specs_available + ' specs available</small>' : "") +
          '<div class="source-actions">' +
            (isFetchable ? '<button class="btn small" data-kc-action="discover">Discover APIs</button>' : "") +
            (source.type === "openapi-url" ? '<button class="btn small secondary" data-kc-action="ingest-url">Ingest from URL</button>' : "") +
            (source.type === "local" ? '<button class="btn small secondary" data-kc-action="upload">Upload Spec</button>' : "") +
          '</div>' +
        '</div>'
      );
    }).join("");
    
    // Attach events
    container.querySelectorAll("[data-kc-action='discover']").forEach(function(btn) {
      btn.addEventListener("click", function() {
        const card = btn.closest(".source-card");
        triggerDiscovery(card && card.dataset.sourceType || "apis-guru");
      });
    });
    container.querySelectorAll("[data-kc-action='ingest-url']").forEach(function(btn) {
      btn.addEventListener("click", showIngestUrlModal);
    });
    container.querySelectorAll("[data-kc-action='upload']").forEach(function(btn) {
      btn.addEventListener("click", showUploadModal);
    });
  }

  // Render staged providers
  function renderStagedProviders() {
    const container = document.getElementById("staged-providers");
    if (!container) return;
    
    const providers = window.__KC_STAGED__ || [];
    if (!providers.length) {
      container.innerHTML = '<div class="empty-state"><span class="empty-icon">' + icon("box") + '</span><p>No API specifications discovered yet.</p><p class="small muted">Use the sources below to discover new APIs.</p></div>';
      return;
    }
    
    container.innerHTML = providers.map(function(p) {
      const isDuplicate = p.duplicate_of !== undefined;
      return (
        '<div class="provider-card' + (isDuplicate ? " duplicate" : "") + '" data-tool-id="' + esc(p.tool_id) + '">' +
          '<div class="provider-header">' +
            '<span class="provider-state ' + p.state + '">' + p.state + '</span>' +
            '<div class="provider-meta"><strong>' + esc(p.name) + '</strong><span class="provider-id">' + esc(p.provider_id) + '</span></div>' +
            
