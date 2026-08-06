/* n8n Workflow Inspection — browser front end.
 *
 * The linting is not reimplemented here. This loads the actual Python package
 * into Pyodide and calls `n8n_linter.api.analyze`, so the browser and the CLI
 * cannot drift: same rules, same severities, same plain-language copy, one
 * source of truth. CI builds the wheel from this repo on every push.
 *
 * Pyodide is fetched lazily, only once someone picks a file, so the page itself
 * stays light for anyone who is only reading it.
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
  docFile: el("doc-file"),
  verdict: el("verdict"),
  record: el("record"),
  scheduleWrap: el("schedule-wrap"),
  findings: el("findings"),
  techOutput: el("tech-output"),
  viewPlain: el("view-plain"),
  viewTech: el("view-tech"),
  copyBtn: el("copy-report"),
  downloadBtn: el("download-report"),
  againBtn: el("check-another"),
  infoToggle: el("info-toggle"),
  infoToggleWrap: el("info-toggle-wrap"),
  ruleList: el("rule-list"),
  versionTag: el("version-tag"),
};

let pyodide = null;
let analyzeFn = null;
let lastResult = null;
let showInfo = false;

/* ---------------------------------------------------------------- engine */

/** Mark a named progress step active, and everything before it done. */
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

  // CI writes this manifest beside the wheel so the filename can carry the
  // version without the page needing to know it in advance.
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
  const label = { error: "Must fix", warning: "Worth fixing", info: "Note" };
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
}

async function check(text, filename) {
  show("loading");
  step("engine");
  try {
    const run = await bootPython();
    step("scan");
    // Yield a frame so the step paints before Python blocks the thread.
    await new Promise((r) => setTimeout(r, 0));

    lastResult = JSON.parse(run(text, filename));
    showInfo = false;
    setView("plain");
    render(lastResult);
    show("results");
    ui.results.scrollIntoView({ block: "start", behavior: "smooth" });
  } catch (err) {
    show("results");
    ui.docFile.textContent = filename;
    ui.verdict.className = "verdict v-void";
    ui.verdict.innerHTML = `
      <p class="verdict-mark"><span class="verdict-glyph">!</span>Not completed</p>
      <p class="verdict-statement">The checker could not start</p>
      <p class="verdict-detail">${escapeHtml(err.message || String(err))}</p>
      <p class="verdict-detail">The command-line version works offline:
        <code>pip install git+https://github.com/Redsf/n8n-workflow-linter</code></p>`;
    ui.record.innerHTML = "";
    ui.findings.innerHTML = "";
    ui.scheduleWrap.hidden = true;
    ui.infoToggleWrap.hidden = true;
  }
}

/* --------------------------------------------------------------- render */

const VERDICT = {
  leak: (r) => ({
    cls: "v-fail",
    glyph: "✗",
    mark: "Not safe to share",
    statement: "Do not send this file yet",
    detail: `${r.summary.errors} credential${r.summary.errors === 1 ? "" : "s"} ${
      r.summary.errors === 1 ? "is" : "are"
    } written inside this file in plain text. Anyone who receives it can read and
      use ${r.summary.errors === 1 ? "it" : "them"}. Treat ${
      r.summary.errors === 1 ? "it" : "them"
    } as already exposed: regenerate at the source, fix the items below, export
      again, then check it again.`,
  }),
  safe: (r) => ({
    cls: "v-warn",
    glyph: "✓",
    mark: "Safe to share",
    statement: "No credentials are exposed",
    detail: `Nothing in this file will leak a password or an API key. ${
      r.summary.warnings + r.summary.info === 1
        ? "One finding below is"
        : `${r.summary.warnings + r.summary.info} findings below are`
    } worth attention: they make the workflow fragile, or more expensive than it
      needs to be. None of them stop it working today.`,
  }),
  clean: () => ({
    cls: "v-pass",
    glyph: "✓",
    mark: "Passed",
    statement: "Nothing to fix",
    detail: `No credentials exposed, no missing safety nets, no loose ends. Safe
      to share, and set up to tell you when something goes wrong.`,
  }),
  unreadable: (r) => ({
    cls: "v-void",
    glyph: "!",
    mark: "Not checked",
    statement: "This file could not be read",
    detail: `${escapeHtml(r.error || "")}. Open the workflow in n8n, use the
      three-dots menu at the top right, then Download, and make sure the whole
      file is saved.`,
  }),
};

function render(r) {
  const v = VERDICT[r.verdict](r);

  ui.docFile.textContent = r.workflow_name && r.workflow_name !== r.filename
    ? `${r.filename} · ${r.workflow_name}`
    : r.filename;

  ui.verdict.className = `verdict ${v.cls}`;
  ui.verdict.innerHTML = `
    <p class="verdict-mark"><span class="verdict-glyph">${v.glyph}</span>${v.mark}</p>
    <p class="verdict-statement">${v.statement}</p>
    <p class="verdict-detail">${v.detail}</p>`;

  ui.record.innerHTML = r.ok
    ? [
        ["Findings", tally(r.summary)],
        ["Steps checked", `${r.summary.nodes}`],
        ["Rules applied", "17"],
        ["Checked", new Date().toISOString().slice(0, 10)],
      ]
        .map(([k, val]) => `<dt>${k}</dt><dd>${val}</dd>`)
        .join("")
    : "";

  ui.scheduleWrap.hidden = !r.ok || r.groups.length === 0;
  renderSchedule(r);
  ui.techOutput.textContent = technicalReport(r);
}

function tally(s) {
  const parts = [
    [s.errors, "must fix", "t-fail"],
    [s.warnings, "worth fixing", "t-warn"],
    [s.info, "note" + (s.info === 1 ? "" : "s"), "t-note"],
  ].filter(([n]) => n > 0);
  if (!parts.length) return "none";
  return `<span class="tally">${parts
    .map(([n, label, cls]) => `<span class="${cls}"><b>${n}</b> ${label}</span>`)
    .join("")}</span>`;
}

const SEV = {
  error: { cls: "is-fail", label: "Must fix" },
  warning: { cls: "is-warn", label: "Worth fixing" },
  info: { cls: "is-note", label: "Note" },
};

function renderSchedule(r) {
  const visible = r.groups.filter((g) => showInfo || g.severity !== "info");
  ui.findings.innerHTML = visible.map(itemHtml).join("");

  // Count findings rather than rule groups: the record above counts findings,
  // and "6 notes" beside "show 2 notes" reads as a bug in the tool.
  const hidden = r.groups
    .filter((g) => g.severity === "info")
    .reduce((n, g) => n + g.count, 0);

  if (!hidden) {
    ui.infoToggleWrap.hidden = true;
    return;
  }
  ui.infoToggleWrap.hidden = false;
  ui.infoToggle.textContent = showInfo
    ? "Hide minor notes"
    : `Show ${hidden} minor note${hidden === 1 ? "" : "s"}`;
}

function itemHtml(g, i) {
  const sev = SEV[g.severity];
  const where = g.nodes.length
    ? `<p class="item-where">${g.nodes.length === 1 ? "Step" : "Steps"}: ${g.nodes
        .map((n) => `<code>${escapeHtml(n)}</code>`)
        .join(" ")}</p>`
    : `<p class="item-where">${escapeHtml(g.message)}</p>`;

  const data = g.details
    .map((d) => `<pre class="item-data">${escapeHtml(d)}</pre>`)
    .join("");

  return `
  <li class="item ${sev.cls}">
    <div class="item-mark">
      <span class="item-no">${String(i + 1).padStart(2, "0")}</span>
      <span class="item-sev">${sev.label}</span>
    </div>
    <div>
      <h4 class="item-title">${escapeHtml(g.title)}</h4>
      ${where}
      ${data}
      ${g.meaning ? `<div class="item-note"><p class="field-label">What this means</p><p>${escapeHtml(g.meaning)}</p></div>` : ""}
      ${g.fix ? `<div class="item-note"><p class="field-label">How to fix it</p>${fixHtml(g.fix)}</div>` : ""}
      <p class="item-rule">${g.rule}</p>
    </div>
  </li>`;
}

/** Numbered fixes become an ordered list; prose stays paragraphs.
 *
 * Several rules open with a sentence before the steps ("Two independent
 * questions, worth answering in this order."). Sweeping every line into the list
 * makes that lead-in item 1 and pushes each real step down a number, so the
 * preamble is split off and kept as prose. */
function fixHtml(fix) {
  const lines = fix.split("\n").map((l) => l.trim()).filter(Boolean);
  const first = lines.findIndex((l) => /^\d+\./.test(l));
  const numbered = lines.slice(first === -1 ? lines.length : first);

  if (numbered.filter((l) => /^\d+\./.test(l)).length < 2) {
    return lines.map((l) => `<p>${escapeHtml(l)}</p>`).join("");
  }

  // A step can wrap onto following unnumbered lines; append those to the step
  // they belong to rather than starting a new one.
  const steps = [];
  for (const line of numbered) {
    if (/^\d+\./.test(line)) steps.push(line.replace(/^\d+\.\s*/, ""));
    else if (steps.length) steps[steps.length - 1] += ` ${line}`;
  }

  const preamble = lines
    .slice(0, first === -1 ? 0 : first)
    .map((l) => `<p>${escapeHtml(l)}</p>`)
    .join("");

  return (
    preamble +
    `<ol class="item-fix">${steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>`
  );
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
  if (!r.ok) return `${r.filename}\n\nNot a readable workflow: ${r.error}`;
  const v = VERDICT[r.verdict](r);
  const out = [
    "WORKFLOW INSPECTION REPORT",
    "=".repeat(62),
    `File      ${r.filename}`,
    `Checked   ${new Date().toISOString().slice(0, 10)}`,
    `Result    ${v.mark.toUpperCase()}`,
    `Findings  ${r.summary.errors} must fix, ${r.summary.warnings} worth fixing, ${r.summary.info} note(s)`,
    "",
    v.statement,
    stripTags(v.detail).replace(/\s+/g, " ").trim(),
    "",
    "SCHEDULE OF FINDINGS",
    "=".repeat(62),
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
    "=".repeat(62),
    "Checked with n8n-workflow-linter",
    "github.com/Redsf/n8n-workflow-linter",
    "The workflow file was not uploaded; this ran in the browser."
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
    window.alert(
      "That file is over 12 MB, far larger than any n8n export. Check it is the right file."
    );
    return;
  }
  const reader = new FileReader();
  reader.onload = () => check(String(reader.result), file.name);
  reader.onerror = () => window.alert("That file could not be read.");
  reader.readAsText(file);
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

// A stray drop elsewhere on the page would otherwise navigate away from the app.
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

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
  ui.viewPlain.classList.toggle("is-on", plain);
  ui.viewTech.classList.toggle("is-on", !plain);
  ui.viewPlain.setAttribute("aria-pressed", String(plain));
  ui.viewTech.setAttribute("aria-pressed", String(!plain));
  if (plain && lastResult?.ok) renderSchedule(lastResult);
}

ui.infoToggle.addEventListener("click", () => {
  showInfo = !showInfo;
  renderSchedule(lastResult);
});

ui.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(currentReport());
    ui.copyBtn.textContent = "Copied";
    setTimeout(() => (ui.copyBtn.textContent = "Copy report"), 1600);
  } catch {
    window.alert("The browser blocked clipboard access. Use Download report instead.");
  }
});

ui.downloadBtn.addEventListener("click", () => {
  const blob = new Blob([currentReport()], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(lastResult?.filename || "workflow").replace(/\.json$/, "")}-inspection.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

ui.againBtn.addEventListener("click", () => {
  ui.fileInput.value = "";
  ui.pasteArea.value = "";
  show("intake");
  ui.intake.scrollIntoView({ block: "start", behavior: "smooth" });
});
