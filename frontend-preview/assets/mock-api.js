(function () {
  "use strict";

  const data = window.MOCK_DATA;
  if (!data) {
    console.error("Agent Bazaar preview: mock-data.js must load before mock-api.js");
    return;
  }

  const originalFetch = window.fetch.bind(window);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  const json = (payload, status = 200) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    });

  const taskMap = new Map(data.tasks.map((task) => [task.task_id, clone(task)]));
  const recent = clone(data.recent.tasks);
  const documents = clone(data.documents.documents);
  let previewTaskCounter = 0;

  function taskForPrompt(prompt) {
    const text = String(prompt || "").toLowerCase();
    if (text.includes("according") || text.includes("document")) {
      return data.tasks.find((task) => task.task.toLowerCase().startsWith("according")) || data.tasks[0];
    }
    if (text.includes("student") || text.includes("enrolled")) return data.tasks[1] || data.tasks[0];
    if (text.includes("holiday")) return data.tasks[2] || data.tasks[0];
    if (text.includes("research") || text.includes("paper") || text.includes("graphrag")) {
      return data.tasks[3] || data.tasks[0];
    }
    return data.tasks[0];
  }

  function taskSummary(result) {
    return {
      task_id: result.task_id,
      task: result.task,
      status: result.status,
      created_at: result.created_at || new Date().toISOString(),
    };
  }

  async function handle(path, options) {
    const method = String(options.method || "GET").toUpperCase();

    if (method === "GET" && path === "/api/health") return json(clone(data.health));
    if (method === "GET" && path === "/api/tools") return json(clone(data.tools));
    if (method === "GET" && path === "/api/ontology") return json(clone(data.ontology));
    if (method === "GET" && path === "/api/monitoring") return json(clone(data.monitoring));

    if (method === "POST" && path === "/api/tasks") {
      let payload = {};
      try {
        payload = JSON.parse(options.body || "{}");
      } catch (error) {
        payload = {};
      }
      await wait(900);
      const result = clone(taskForPrompt(payload.task));
      result.task_id = `task_preview_${Date.now().toString(36)}_${++previewTaskCounter}`;
      result.task = String(payload.task || result.task || "").trim() || result.task;
      taskMap.set(result.task_id, clone(result));
      recent.unshift(taskSummary(result));
      return json(result);
    }

    if (method === "GET" && path === "/api/tasks/recent") {
      return json({ tasks: clone(recent.slice(0, 20)) });
    }

    if (method === "GET" && path.startsWith("/api/tasks/")) {
      const id = decodeURIComponent(path.slice("/api/tasks/".length));
      if (id === "recent") return json({ tasks: clone(recent.slice(0, 20)) });
      const result = taskMap.get(id);
      return result ? json(clone(result)) : json({ detail: "Task not found" }, 404);
    }

    if (method === "POST" && path.startsWith("/api/demo/drift/")) {
      await wait(300);
      const alert = data.monitoring.drift_alerts?.[0] || {
        alert_id: "alert_preview",
        tool_id: path.slice("/api/demo/drift/".length),
        severity: "high",
        reasons: ["Injected drift: response no longer matches the mapped schema."],
        detected_at: new Date().toISOString(),
      };
      return json({ status: "drift_injected", alert: clone(alert) });
    }

    if (method === "GET" && path === "/api/documents") {
      return json({ documents: clone(documents) });
    }

    if (method === "POST" && path === "/api/documents") {
      await wait(500);
      let file = null;
      try {
        file = options.body?.get?.("file") || null;
      } catch (error) {
        file = null;
      }
      const document = {
        document_id: `doc_preview_${Date.now().toString(36)}`,
        name: file?.name || "uploaded-document.txt",
        size_bytes: Number(file?.size || 0),
        text_chars: Number(file?.size || 0),
        created_at: new Date().toISOString(),
      };
      documents.unshift(document);
      return json({ document: clone(document), documents: clone(documents) });
    }

    if (method === "POST" && path === "/api/corrections") {
      await wait(450);
      return json(clone(data.correction));
    }

    if (method === "POST" && path === "/api/listings") {
      await wait(650);
      return json(clone(data.listing));
    }

    return json({ detail: `Preview mock has no handler for ${method} ${path}` }, 404);
  }

  window.fetch = function (input, options = {}) {
    let url;
    try {
      url = new URL(typeof input === "string" ? input : input.url, window.location.href);
    } catch (error) {
      return originalFetch(input, options);
    }
    if (!url.pathname.startsWith("/api/")) return originalFetch(input, options);
    return handle(url.pathname, options).catch((error) => {
      console.error("[preview mock]", error);
      return json({ detail: error.message }, 500);
    });
  };
})();
