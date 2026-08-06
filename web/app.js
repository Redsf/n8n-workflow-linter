/* n8n Workflow Check — browser front end.
 *
 * The linting is not reimplemented here. This loads the actual Python package
 * into Pyodide and calls `n8n_linter.api.analyze`, so the browser and the CLI
 * cannot drift: same rules, same severities, same plain-language copy, one
 * source of truth. CI builds the wheel from this repo on every push.
 *
 * Findings render as <details> rows rather than JS-managed panels: native
 * disclosure is keyboard-operable, announced correctly, findable by the
 * browser's own in-page search, and printable when forced open.
 */

const PYODIDE_VERSION = "0.26.4";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const el = (id) => document.getElementById(id);

const ui = {
  intake: el("intake"),
  loading: el("loading-panel"),
  results: el("results-panel"),
  progress: el("progress-list"),
  dropzone: el("dropzone"),
  fileInput: el("file-input"),
  trySample: el("try-sample"),
  pasteToggle: el("paste-toggle"),
  pastePanel: el("paste-panel"),
  pasteArea: el("paste-area"),
  pasteRun: el("paste-run"),
  verdict: el("verdict"),
  meta: el("meta"),
  scheduleWrap: el("schedule-wrap"),
  findings: el("findings"),
  techOutput: el("tech-output"),
  viewPlain: el("view-plain"),
  viewTech: el("view-tech"),
  expandAll: el("expand-all"),
  copyBtn: el("copy-report"),
  downloadBtn: el("download-report"),
  againBtn: el("check-another"),
  infoToggle: el("info-toggle"),
  infoToggleWrap: el("info-toggle-wrap"),
  ruleList: el("rule-list"),
  versionTag: el("version-tag"),
  statusbar: el("statusbar"),
  sbMark: el("sb-mark"),
  sbFile: el("sb-file"),
  sbTally: el("sb-tally"),
  sbAgain: el("sb-again"),
};

let pyodide = null;
let analyzeFn = null;
let lastResult = null;
let showInfo = false;

/* ---------------------------------------------------------------- engine */

function step(name) {
  const order = ["engine", "rules", "scan"];
  const at = order.indexOf(name);
  for (const li of ui.progress.querySelectorAll("li")) {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle("is-done", i < at);
    li.classList.toggle("is-active", i === at);
  }
}

async function bootPython() {
  if (analyzeFn) return analyzeFn;

  step("engine");
  const { loadPyodide } = await import(`${PYODIDE_CDN}pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  step("rules");
  await pyodide.loadPackage("micropip");

  const manifest = await fetch(new URL("./dist/wheel.json", import.meta.url))
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);

  if (!manifest?.file) {
    throw new Error(
      "The checker package is missing from this deployment. " +
      "Run scripts/build-web.sh and redeploy."
    );
  }

  const micropip = pyodide.pyimport("micropip");
  await micropip.install(new URL(`./dist/${manifest.file}`, import.meta.url).href);

  analyzeFn = pyodide.runPython(`
from n8n_linter.api import analyze_json, rule_catalogue
import json

def _run(text, filename):
    return analyze_json(text, filename)

_run
  `);

  ui.versionTag.textContent = `v${pyodide.runPython("import n8n_linter; n8n_linter.__version__")}`;
  renderRuleList();
  return analyzeFn;
}

function renderRuleList() {
  const rules = JSON.parse(pyodide.runPython("import json; json.dumps(rule_catalogue())"));
  const label = { error: "Must fix", warning: "Fix soon", info: "Note" };
  ui.ruleList.innerHTML = rules
    .map(
      (r) => `<div class="rule-row">
        <span class="rule-sev ${r.severity}">${label[r.severity]}</span>
        <span>${escapeHtml(r.title)}</span>
      </div>`
    )
    .join("");
}

/* ------------------------------------------------------------------ flow */

function show(panel) {
  ui.intake.hidden = panel !== "intake";
  ui.loading.hidden = panel !== "loading";
  ui.results.hidden = panel !== "results";
  syncStatusbar();
}

async function check(text, filename) {
  show("loading");
  step("engine");
  try {
    const run = await bootPython();
    step("scan");
    await new Promise((r) => setTimeout(r, 0));

    lastResult = JSON.parse(run(text, filename));
    showInfo = false;
    render(lastResult);
    show("results");
    setView("plain");
    ui.results.scrollIntoView({ block: "start" });
  } catch (err) {
    show("results");
    ui.verdict.className = "verdict v-void";
    ui.verdict.innerHTML = `
      <p class="verdict-mark">Not checked</p>
      <p class="verdict-line">The checker could not start</p>
      <p class="verdict-say">${escapeHtml(err.message || String(err))}</p>`;
    ui.meta.textContent = filename;
    ui.findings.innerHTML = "";
    ui.scheduleWrap.hidden = true;
    ui.infoToggleWrap.hidden = true;
  }
}

/* --------------------------------------------------------------- render */

const VERDICT = {
  leak: (r) => ({
    cls: "v-fail",
    mark: "Not safe to share",
    line: "Do not send this file",
    say: `${r.summary.errors} credential${r.summary.errors === 1 ? " sits" : "s sit"} in
      this file as readable text. Treat ${r.summary.errors === 1 ? "it" : "them"} as
      already exposed: regenerate at the source, then fix the rows below.`,
  }),
  safe: () => ({
    cls: "v-warn",
    mark: "Safe to share",
    line: "No keys are exposed",
    say: `Nothing here leaks a password or an API key. The rows below will make
      this workflow fragile or expensive, but none of them stop it working.`,
  }),
  clean: () => ({
    cls: "v-pass",
    mark: "Passed",
    line: "Nothing to fix",
    say: "No exposed keys, no missing safety nets, no loose ends.",
  }),
  unreadable: (r) => ({
    cls: "v-void",
    mark: "Not checked",
    line: "This file could not be read",
    say: `${escapeHtml(r.error || "")}. In n8n, use the three-dots menu at the top
      right, then Download.`,
  }),
};

function render(r) {
  const v = VERDICT[r.verdict](r);

  ui.verdict.className = `verdict ${v.cls}`;
  ui.verdict.innerHTML = `
    <p class="verdict-mark">${v.mark}</p>
    <p class="verdict-line">${v.line}</p>
    <p class="verdict-say">${v.say}</p>`;

  const s = r.summary;
  ui.meta.innerHTML = r.ok
    ? [
        escapeHtml(r.filename),
        `${s.nodes} steps`,
        "17 rules",
        s.errors ? `<span class="m-fail"><b>${s.errors}</b> must fix</span>` : "",
        s.warnings ? `<span class="m-warn"><b>${s.warnings}</b> fix soon</span>` : "",
        s.info ? `<span class="m-note"><b>${s.info}</b> note${s.info === 1 ? "" : "s"}</span>` : "",
      ]
        .filter(Boolean)
        .map((x) => `<span>${x}</span>`)
        .join("")
    : escapeHtml(r.filename);

  // Status bar mirrors the verdict once it scrolls out of view.
  ui.sbMark.className = `sb-mark ${v.cls}`;
  ui.sbMark.textContent = v.mark;
  ui.sbFile.textContent = r.filename;
  ui.sbTally.textContent = r.ok
    ? `${s.errors} must fix · ${s.warnings} fix soon · ${s.info} notes`
    : "";

  ui.scheduleWrap.hidden = !r.ok || r.groups.length === 0;
  renderList(r);
  ui.techOutput.textContent = technicalReport(r);
}

const SEV = {
  error: { cls: "is-fail", label: "Must fix" },
  warning: { cls: "is-warn", label: "Fix soon" },
  info: { cls: "is-note", label: "Note" },
};

function renderList(r) {
  const visible = r.groups.filter((g) => showInfo || g.severity !== "info");
  ui.findings.innerHTML = visible.map(rowHtml).join("");
  syncExpandLabel();

  const hidden = r.groups
    .filter((g) => g.severity === "info")
    .reduce((n, g) => n + g.count, 0);

  if (!hidden) {
    ui.infoToggleWrap.hidden = true;
    return;
  }
  ui.infoToggleWrap.hidden = false;
  ui.infoToggle.textContent = showInfo
    ? "Hide notes"
    : `Show ${hidden} note${hidden === 1 ? "" : "s"}`;
}

function rowHtml(g, i) {
  const sev = SEV[g.severity];
  // Errors open by default: the reason someone ran this is to see those.
  const open = g.severity === "error" ? " open" : "";
  const where = g.nodes.length ? g.nodes.join(", ") : "";

  const data = g.details.map((d) => `<pre class="r-data">${escapeHtml(d)}</pre>`).join("");

  return `
  <li>
    <details class="row ${sev.cls}"${open}>
      <summary>
        <span class="r-no">${String(i + 1).padStart(2, "0")}</span>
        <span class="r-sev">${sev.label}</span>
        <span class="r-title">${escapeHtml(g.title)}</span>
        <span class="r-where">${escapeHtml(where)}</span>
        <span class="r-chev" aria-hidden="true"></span>
      </summary>
      <div class="r-body">
        ${data}
        ${g.meaning ? `<div><p class="label">What this means</p><p>${escapeHtml(g.meaning)}</p></div>` : ""}
        ${g.fix ? `<div><p class="label">How to fix it</p>${fixHtml(g.fix)}</div>` : ""}
        <p class="r-id">${g.rule}</p>
      </div>
    </details>
  </li>`;
}

/** Numbered fixes become an ordered list; a lead-in sentence stays prose. */
function fixHtml(fix) {
  const lines = fix.split("\n").map((l) => l.trim()).filter(Boolean);
  const first = lines.findIndex((l) => /^\d+\./.test(l));
  const numbered = lines.slice(first === -1 ? lines.length : first);

  if (numbered.filter((l) => /^\d+\./.test(l)).length < 2) {
    return lines.map((l) => `<p>${escapeHtml(l)}</p>`).join("");
  }

  const steps = [];
  for (const line of numbered) {
    if (/^\d+\./.test(line)) steps.push(line.replace(/^\d+\.\s*/, ""));
    else if (steps.length) steps[steps.length - 1] += ` ${line}`;
  }
  const preamble = lines
    .slice(0, first === -1 ? 0 : first)
    .map((l) => `<p>${escapeHtml(l)}</p>`)
    .join("");

  return preamble + `<ol class="r-fix">${steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>`;
}

/* --------------------------------------------------------------- report */

function technicalReport(r) {
  if (!r.ok) return `${r.filename}\n  error  ${r.error}`;
  const rows = r.findings.map((f) => {
    const loc = f.line ? `:${f.line}` : "";
    const node = f.node ? ` (${f.node})` : "";
    return `  ${loc.padEnd(6)}${f.severity.padEnd(8)}${f.message}${node}  ${f.rule}`;
  });
  const s = r.summary;
  return [
    r.filename,
    ...rows,
    "",
    `Checked 1 workflow file: ${s.errors} error(s), ${s.warnings} warning(s), ${s.info} info.`,
  ].join("\n");
}

function plainReport(r) {
  if (!r.ok) return `${r.filename}\n\nNot readable: ${r.error}`;
  const v = VERDICT[r.verdict](r);
  const s = r.summary;
  const out = [
    "N8N WORKFLOW CHECK",
    "=".repeat(60),
    `File     ${r.filename}`,
    `Checked  ${new Date().toISOString().slice(0, 10)}`,
    `Result   ${v.mark.toUpperCase()}`,
    `Found    ${s.errors} must fix, ${s.warnings} fix soon, ${s.info} note(s)`,
    "",
    v.line,
    stripTags(v.say).replace(/\s+/g, " ").trim(),
    "",
    "FINDINGS",
    "=".repeat(60),
  ];
  r.groups.forEach((g, i) => {
    out.push("", `${String(i + 1).padStart(2, "0")}  [${SEV[g.severity].label}]  ${g.title}`);
    if (g.nodes.length) out.push(`    Steps: ${g.nodes.join(", ")}`);
    for (const d of g.details) out.push("", d.split("\n").map((l) => "    " + l).join("\n"));
    if (g.meaning) out.push("", "    What this means:", `    ${g.meaning}`);
    if (g.fix) out.push("", "    How to fix it:", g.fix.split("\n").map((l) => "    " + l).join("\n"));
    out.push(`    rule: ${g.rule}`);
  });
  out.push(
    "",
    "=".repeat(60),
    "github.com/Redsf/n8n-workflow-linter",
    "Checked in the browser. The file was not uploaded."
  );
  return out.join("\n");
}

const currentReport = () =>
  ui.techOutput.hidden ? plainReport(lastResult) : technicalReport(lastResult);

/* ---------------------------------------------------------------- utils */

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
const stripTags = (s) => String(s).replace(/<[^>]*>/g, "");

function readFile(file) {
  if (!file) return;
  if (file.size > 12 * 1024 * 1024) {
    window.alert("That file is over 12 MB, far larger than any n8n export.");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => check(String(reader.result), file.name);
  reader.onerror = () => window.alert("That file could not be read.");
  reader.readAsText(file);
}

const rows = () => [...ui.findings.querySelectorAll("details.row")];

function syncExpandLabel() {
  const all = rows();
  const allOpen = all.length > 0 && all.every((d) => d.open);
  ui.expandAll.textContent = allOpen ? "Collapse all" : "Expand all";
}

/* --------------------------------------------------------------- wiring */

ui.dropzone.addEventListener("click", () => ui.fileInput.click());
ui.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    ui.fileInput.click();
  }
});
ui.fileInput.addEventListener("change", (e) => readFile(e.target.files[0]));

for (const evt of ["dragenter", "dragover"]) {
  ui.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    ui.dropzone.classList.add("is-over");
  });
}
for (const evt of ["dragleave", "drop"]) {
  ui.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    ui.dropzone.classList.remove("is-over");
  });
}
ui.dropzone.addEventListener("drop", (e) => readFile(e.dataTransfer.files[0]));

window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

ui.findings.addEventListener("toggle", syncExpandLabel, true);

ui.trySample.addEventListener("click", async () => {
  show("loading");
  step("engine");
  try {
    const res = await fetch(new URL("./sample-workflow.json", import.meta.url));
    check(await res.text(), "sample-workflow.json");
  } catch {
    show("intake");
    window.alert("The sample file could not be loaded.");
  }
});

ui.pasteToggle.addEventListener("click", () => {
  const opening = ui.pastePanel.hidden;
  ui.pastePanel.hidden = !opening;
  ui.pasteToggle.setAttribute("aria-expanded", String(opening));
  if (opening) ui.pasteArea.focus();
});
ui.pasteRun.addEventListener("click", () => {
  const text = ui.pasteArea.value.trim();
  if (text) check(text, "pasted-workflow.json");
});

ui.viewPlain.addEventListener("click", () => setView("plain"));
ui.viewTech.addEventListener("click", () => setView("tech"));

function setView(mode) {
  const plain = mode === "plain";
  ui.scheduleWrap.hidden = !plain || !lastResult?.groups.length;
  ui.techOutput.hidden = plain;
  ui.expandAll.hidden = !plain;
  ui.viewPlain.classList.toggle("is-on", plain);
  ui.viewTech.classList.toggle("is-on", !plain);
  ui.viewPlain.setAttribute("aria-pressed", String(plain));
  ui.viewTech.setAttribute("aria-pressed", String(!plain));
  if (plain && lastResult?.ok) renderList(lastResult);
}

ui.expandAll.addEventListener("click", () => {
  const all = rows();
  const open = !(all.length > 0 && all.every((d) => d.open));
  all.forEach((d) => (d.open = open));
  syncExpandLabel();
});

ui.infoToggle.addEventListener("click", () => {
  showInfo = !showInfo;
  renderList(lastResult);
});

ui.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(currentReport());
    ui.copyBtn.textContent = "Copied";
    setTimeout(() => (ui.copyBtn.textContent = "Copy"), 1600);
  } catch {
    window.alert("The browser blocked clipboard access. Use Download instead.");
  }
});

ui.downloadBtn.addEventListener("click", () => {
  const blob = new Blob([currentReport()], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(lastResult?.filename || "workflow").replace(/\.json$/, "")}-check.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

const reset = () => {
  ui.fileInput.value = "";
  ui.pasteArea.value = "";
  show("intake");
  window.scrollTo({ top: 0 });
};
ui.againBtn.addEventListener("click", reset);
ui.sbAgain.addEventListener("click", reset);

// Reveal the status bar once the verdict has scrolled away.
//
// A scroll listener rather than an IntersectionObserver: the verdict starts
// inside a `hidden` panel, and an observer set up against an element with no
// layout box did not reliably re-fire once the panel was shown. This recomputes
// from the element's own rect, so there is no state to get stale.
function syncStatusbar() {
  if (ui.results.hidden) {
    ui.statusbar.hidden = true;
    return;
  }
  ui.statusbar.hidden = ui.verdict.getBoundingClientRect().bottom > 0;
}
window.addEventListener("scroll", syncStatusbar, { passive: true });
window.addEventListener("resize", syncStatusbar, { passive: true });
