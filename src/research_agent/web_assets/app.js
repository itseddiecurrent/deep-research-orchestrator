const form = document.querySelector("#research-form");
const queryInput = document.querySelector("#query");
const submitButton = document.querySelector("#submit");
const runSection = document.querySelector("#run");
const results = document.querySelector("#results");
const loading = document.querySelector("#loading");
const errorBox = document.querySelector("#error");
const status = document.querySelector("#status");
const loadingTitle = document.querySelector("#loading-title");
const loadingCopy = document.querySelector("#loading-copy");

const traceNames = {
  session_started: "Session started",
  objective_created: "Objective defined",
  plan_created: "Plan created",
  planner_decision: "Planner decision",
  tool_requested: "Tool requested",
  tool_completed: "Tool completed",
  tool_failed: "Tool failed",
  source_created: "Source captured",
  evidence_created: "Evidence validated",
  evidence_failed: "Evidence rejected",
  evaluation_completed: "Evidence evaluated",
  synthesis_started: "Synthesis started",
  citation_validated: "Citation validated",
  limit_reached: "Runtime limit reached",
  session_completed: "Research completed",
  session_partial: "Partial result",
  session_failed: "Research failed",
};

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.prompt;
    queryInput.focus();
  });
});

queryInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  setRunning(true);
  runSection.classList.remove("hidden");
  results.classList.add("hidden");
  errorBox.classList.add("hidden");
  loading.classList.remove("hidden");
  document.querySelector("#run-title").textContent = query;
  runSection.scrollIntoView({ behavior: "smooth", block: "start" });

  const loadingTimer = cycleLoadingMessages();
  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    renderRun(payload);
  } catch (error) {
    errorBox.textContent = error.message || "Research failed unexpectedly.";
    errorBox.classList.remove("hidden");
    setStatus("failed", "Failed");
  } finally {
    window.clearInterval(loadingTimer);
    loading.classList.add("hidden");
    setRunning(false);
  }
});

function cycleLoadingMessages() {
  const messages = [
    ["Planning the investigation", "The agent is turning your question into a bounded research plan."],
    ["Searching and reading", "Relevant sources are being retrieved through the registered web-search tool."],
    ["Checking the evidence", "Source excerpts and provenance links are being validated before use."],
    ["Building the answer", "The agent may take several passes before producing a cited result."],
  ];
  let index = 0;
  loadingTitle.textContent = messages[0][0];
  loadingCopy.textContent = messages[0][1];
  return window.setInterval(() => {
    index = (index + 1) % messages.length;
    loadingTitle.textContent = messages[index][0];
    loadingCopy.textContent = messages[index][1];
  }, 6500);
}

function setRunning(isRunning) {
  submitButton.disabled = isRunning;
  queryInput.disabled = isRunning;
  submitButton.querySelector("span").textContent = isRunning ? "Researching…" : "Begin research";
  if (isRunning) setStatus("running", "Researching");
}

function setStatus(kind, label) {
  status.className = `status ${kind}`;
  status.querySelector("span").textContent = label;
}

function renderRun(data) {
  const plan = data.plan;
  document.querySelector("#objective").textContent = plan?.objective?.goal || "No plan was produced.";
  const tasks = document.querySelector("#tasks");
  tasks.replaceChildren();
  (plan?.tasks || []).forEach((task) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = task.description;
    const rationale = document.createElement("p");
    rationale.textContent = task.rationale;
    item.append(title, rationale);
    tasks.append(item);
  });

  renderTrace(data.trace || [], data.tool_calls || []);
  renderReport(document.querySelector("#answer"), data.report || "No report was returned.");

  const duration = Math.max(0, new Date(data.updated_at) - new Date(data.created_at));
  const metrics = document.querySelector("#metrics");
  metrics.replaceChildren(
    metric(`${data.tool_calls.length}`, "tools"),
    metric(`${data.sources.length}`, "sources"),
    metric(formatDuration(duration), "elapsed")
  );

  const isFailed = data.status === "failed";
  const isPartial = data.status === "partial";
  setStatus(isFailed ? "failed" : isPartial ? "partial" : "complete", isFailed ? "Failed" : isPartial ? "Partial" : "Complete");
  results.classList.remove("hidden");
}

function metric(value, label) {
  const element = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = value;
  element.append(strong, document.createTextNode(label));
  return element;
}

function renderTrace(events, toolCalls) {
  const timeline = document.querySelector("#trace");
  timeline.replaceChildren();
  const calls = new Map(toolCalls.map((call) => [call.id, call]));
  const start = events.length ? new Date(events[0].timestamp) : null;

  events.forEach((event) => {
    const item = document.createElement("li");
    item.className = traceTone(event.event_type);
    const dot = document.createElement("i");
    const body = document.createElement("div");
    const head = document.createElement("div");
    head.className = "timeline-head";
    const title = document.createElement("strong");
    title.textContent = traceNames[event.event_type] || humanize(event.event_type);
    const time = document.createElement("time");
    time.textContent = start ? `+${formatDuration(new Date(event.timestamp) - start)}` : "";
    head.append(title, time);
    body.append(head);

    const summary = traceSummary(event, calls.get(event.tool_call_id));
    if (summary) {
      const copy = document.createElement("p");
      copy.textContent = summary;
      body.append(copy);
    }

    const details = traceDetails(event, calls.get(event.tool_call_id));
    if (details) body.append(details);
    item.append(dot, body);
    timeline.append(item);
  });
}

function traceSummary(event, call) {
  if (event.decision_summary) return event.decision_summary;
  if (event.event_type === "tool_requested") {
    return `Calling ${event.data.tool_name} v${event.data.tool_version}.`;
  }
  if (event.event_type === "tool_completed") {
    return `Retrieved ${formatBytes(event.data.size_bytes || 0)} on attempt ${event.data.attempt_number}.`;
  }
  if (event.event_type === "source_created") return event.data.source_url;
  if (event.event_type === "evidence_created") return "A source-backed claim passed lineage and excerpt checks.";
  if (event.event_type === "citation_validated") return "A report citation was linked to validated evidence.";
  if (event.event_type === "synthesis_started") return "Composing claims from validated evidence IDs only.";
  if (event.event_type === "tool_failed") return `The tool failed (${event.data.error_type || "unknown error"}).`;
  if (event.event_type === "limit_reached") return `Stopped at ${humanize(event.data.limit || "runtime limit")}.`;
  return "";
}

function traceDetails(event, call) {
  if (event.event_type === "tool_requested" && call) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Tool arguments";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(call.arguments, null, 2);
    details.append(summary, pre);
    return details;
  }
  if (event.event_type === "source_created" && event.data.source_url) {
    const anchor = document.createElement("a");
    anchor.href = event.data.source_url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = "Open source ↗";
    return anchor;
  }
  return null;
}

function traceTone(type) {
  if (type.includes("failed") || type === "limit_reached") return "danger";
  if (type.includes("completed") || type === "citation_validated" || type === "evidence_created") return "success";
  if (type.includes("tool") || type === "source_created") return "tool";
  return "reasoning";
}

function renderReport(container, markdown) {
  container.replaceChildren();
  const listStack = [];
  markdown.split("\n").forEach((rawLine) => {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      listStack.length = 0;
      return;
    }
    let element;
    if (line.startsWith("## ")) {
      element = document.createElement("h2");
      appendInline(element, line.slice(3));
    } else if (line.startsWith("# ")) {
      element = document.createElement("h1");
      appendInline(element, line.slice(2));
    } else if (/^- /.test(line)) {
      let list = listStack.at(-1);
      if (!list || list.tagName !== "UL") {
        list = document.createElement("ul");
        container.append(list);
        listStack.push(list);
      }
      element = document.createElement("li");
      appendInline(element, line.slice(2));
      list.append(element);
      return;
    } else if (/^\d+\. /.test(line)) {
      let list = listStack.at(-1);
      if (!list || list.tagName !== "OL") {
        list = document.createElement("ol");
        container.append(list);
        listStack.push(list);
      }
      element = document.createElement("li");
      appendInline(element, line.replace(/^\d+\. /, ""));
      list.append(element);
      return;
    } else {
      element = document.createElement("p");
      appendInline(element, line);
    }
    listStack.length = 0;
    container.append(element);
  });
}

function appendInline(parent, text) {
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g;
  let cursor = 0;
  for (const match of text.matchAll(linkPattern)) {
    parent.append(document.createTextNode(text.slice(cursor, match.index)));
    const anchor = document.createElement("a");
    anchor.href = match[2];
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = match[1];
    parent.append(anchor);
    cursor = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(cursor)));
}

function humanize(value) {
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function formatDuration(milliseconds) {
  const seconds = Math.max(0, milliseconds) / 1000;
  return seconds < 60 ? `${seconds.toFixed(seconds < 10 ? 1 : 0)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}
