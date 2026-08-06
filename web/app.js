/* n8n Workflow Linter — browser front end.
 *
 * The linting itself is not reimplemented here. This loads the actual Python
 * package into Pyodide and calls `n8n_linter.api.analyze`, so the browser and the
 * CLI cannot drift: same rules, same severities, same plain-language copy, one
 * source of truth. The wheel is built from this repo in CI on every push.
 *
 * Pyodide is fetched lazily — only once someone actually chooses a file — so the
 * page itself stays light for anyone who is just reading it.
 */

const PYODIDE_VERSION = "0.26.4";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

const el = (id) => document.getElementById(id);

const ui = {
  input: el("input-panel"),
  loading: el("loading-panel"),
  loadingText: el("loading-text"),
  results: el("results-panel"),
  dropzone: el("dropzone"),
  fileInput: el("file-input"),
  trySample: el("try-sample"),
  pasteToggle: el("paste-toggle"),
  pastePanel: el("paste-panel"),
  pasteArea: el("paste-area"),
  pasteRun: el("paste-run"),
  verdict: el("verdict"),
  counts: el("counts"),
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

async function bootPython(report) {
  if (analyzeFn) return analyzeFn;

  report("Downloading the Python engine…");
  const { loadPyodide } = await import(`${PYODIDE_CDN}pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  report("Installing the linter…");
  await pyodide.loadPackage("micropip");

  // CI writes this manifest next to the wheel so the filename can carry the
  // version without the page needing to know it in advance.
  const manifest = await fetch(new URL("./dist/wheel.json", import.meta.url))
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);

  if (!manifest?.file) {
    throw new Error(
      "The linter package is missing from this deployment. " +
      "Run scripts/build-web.sh and redeploy."
    );
  }

  const wheelUrl = new URL(`./dist/${manifest.file}`, import.meta.url).href;
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(wheelUrl);

  report("Starting up…");
  analyzeFn = pyodide.runPython(`
from n8n_linter.api import analyze_json, rule_catalogue
import json

def _run(text, filename):
    return analyze_json(text, filename)

_run
  `);

  const version = pyodide.runPython("import n8n_linter; n8n_linter.__version__");
  ui.versionTag.textContent = `v${version}`;
  renderRuleList();

  return analyzeFn;
}

function renderRuleList() {
  const rules = JSON.parse(
    pyodide.runPython("import json; json.dumps(rule_catalogue())")
  );
  ui.ruleList.innerHTML = rules
    .map(
      (r) => `<div class="rule-row">
        <span class="dot ${r.severity}" title="${r.severity}"></span>
        <span>${escapeHtml(r.title)}</span>
      </div>`
    )
    .join("");
}

/* ------------------------------------------------------------------ flow */

function show(panel) {
  ui.input.hidden = panel !== "input";
  ui.loading.hidden = panel !== "loading";
  ui.results.hidden = panel !== "results";
}

async function check(text, filename) {
  show("loading");
  try {
    const run = await bootPython((msg) => {
      ui.loadingText.textContent = msg;
    });
    ui.loadingText.textContent = "Checking your workflow…";
    // Yield a frame so the message paints before Python blocks the thread.
    await new Promise((r) => setTimeout(r, 0));

    lastResult = JSON.parse(run(text, filename));
    showInfo = false;
    render(lastResult);
    show("results");
    ui.results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    show("results");
    ui.verdict.className = "verdict unreadable";
    ui.verdict.innerHTML = `
      <h2>The checker could not start</h2>
      <p>${escapeHtml(err.message || String(err))}</p>
      <p>If this keeps happening, the CLI works offline:
      <code>pip install git+https://github.com/Redsf/n8n-workflow-linter</code></p>`;
    ui.counts.innerHTML = "";
    ui.findings.innerHTML = "";
    ui.infoToggleWrap.hidden = true;
  }
}

/* --------------------------------------------------------------- render */

const VERDICT_COPY = {
  leak: (r) => [
    "Do not share this file yet",
    `${r.summary.errors} credential${r.summary.errors === 1 ? " is" : "s are"} written
     inside this file in plain text. Anyone you send it to can read ${r.summary.errors === 1 ? "it" : "them"}
     and use ${r.summary.errors === 1 ? "it" : "them"}. Treat ${r.summary.errors === 1 ? "it" : "them"} as
     already exposed: regenerate at the source, fix the items below, export again, and re-check.`,
  ],
  safe: (r) => [
    "Safe to share",
    `No passwords or API keys are inside this file. There ${
      r.summary.warnings + r.summary.info === 1 ? "is 1 thing" : `are ${r.summary.warnings + r.summary.info} things`
    } below that will make this workflow fragile or confusing later, but none of them
     stop it working today.`,
  ],
  clean: () => [
    "All clear",
    `No secrets, no missing safety nets, no loose ends. Safe to share, and set up to
     tell you when something goes wrong.`,
  ],
  unreadable: (r) => [
    "This is not a workflow file n8n can read",
    `${escapeHtml(r.error || "")} — open the workflow in n8n and use the three-dots
     menu, top right, then Download. Make sure the whole file is saved.`,
  ],
};

function render(r) {
  const [heading, body] = VERDICT_COPY[r.verdict](r);
  ui.verdict.className = `verdict ${r.verdict}`;
  ui.verdict.innerHTML = `
    <span class="file-name">${escapeHtml(r.filename)}${
      r.workflow_name && r.workflow_name !== r.filename
        ? ` — “${escapeHtml(r.workflow_name)}”`
        : ""
    }</span>
    <h2>${heading}</h2>
    <p>${body}</p>`;

  ui.counts.innerHTML = r.ok
    ? [
        ["error", r.summary.errors, "must fix"],
        ["warning", r.summary.warnings, "worth fixing"],
        ["info", r.summary.info, "minor"],
      ]
        .map(
          ([sev, n, label]) =>
            `<span class="count"><span class="dot ${sev}"></span><b>${n}</b> ${label}</span>`
        )
        .join("") + `<span class="count"><b>${r.summary.nodes}</b> steps checked</span>`
    : "";

  renderFindings(r);
  ui.techOutput.textContent = technicalReport(r);
}

function renderFindings(r) {
  const order = ["error", "warning", "info"];
  const headings = {
    error: "Must fix before sharing",
    warning: "Worth fixing — these cause problems later",
    info: "Minor — tidy up when convenient",
  };

  // Count findings, not rule groups — the summary bar above counts findings, and
  // "6 minor" next to "show 2 minor notes" reads like a bug.
  const hiddenInfo = r.groups
    .filter((g) => g.severity === "info")
    .reduce((n, g) => n + g.count, 0);
  let html = "";

  for (const sev of order) {
    const groups = r.groups.filter((g) => g.severity === sev);
    if (!groups.length) continue;
    if (sev === "info" && !showInfo) continue;
    html += `<h3 class="group-heading">${headings[sev]}</h3>`;
    html += groups.map(findingCard).join("");
  }

  ui.findings.innerHTML = html;

  if (hiddenInfo && !showInfo) {
    ui.infoToggleWrap.hidden = false;
    ui.infoToggle.textContent = `Show ${hiddenInfo} minor note${hiddenInfo === 1 ? "" : "s"}`;
  } else if (hiddenInfo && showInfo) {
    ui.infoToggleWrap.hidden = false;
    ui.infoToggle.textContent = "Hide minor notes";
  } else {
    ui.infoToggleWrap.hidden = true;
  }
}

function findingCard(g) {
  const steps = g.nodes.length
    ? `<p class="finding-steps">${g.nodes.length === 1 ? "Step" : "Steps"} affected: ${g.nodes
        .map((n) => `<code>${escapeHtml(n)}</code>`)
        .join(" ")}</p>`
    : `<p class="finding-steps">${escapeHtml(g.message)}</p>`;

  const details = g.details
    .map((d) => `<pre class="detail-block">${escapeHtml(d)}</pre>`)
    .join("");

  return `
  <article class="finding ${g.severity}">
    <div class="finding-head">
      <span class="badge ${g.severity}">${g.severity}</span>
      <div>
        <h4 class="finding-title">${escapeHtml(g.title)}</h4>
        ${steps}
      </div>
    </div>
    <div class="finding-body">
      ${details}
      ${g.meaning ? `<div><p class="sub">What this means</p><p>${escapeHtml(g.meaning)}</p></div>` : ""}
      ${g.fix ? `<div><p class="sub">How to fix it</p>${fixHtml(g.fix)}</div>` : ""}
      <p class="rule-id">rule: ${g.rule}</p>
    </div>
  </article>`;
}

/** Numbered fixes become a real list; prose stays a paragraph. */
function fixHtml(fix) {
  const lines = fix.split("\n").map((l) => l.trim()).filter(Boolean);
  const numbered = lines.filter((l) => /^\d+\./.test(l));
  if (numbered.length >= 2) {
    return `<ol class="fix-steps">${lines
      .map((l) => `<li>${escapeHtml(l.replace(/^\d+\.\s*/, ""))}</li>`)
      .join("")}</ol>`;
  }
  return lines.map((l) => `<p>${escapeHtml(l)}</p>`).join("");
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
  const [heading, body] = VERDICT_COPY[r.verdict](r);
  const out = [
    `n8n Workflow Linter — ${r.filename}`,
    "=".repeat(60),
    "",
    heading.toUpperCase(),
    stripTags(body).replace(/\s+/g, " ").trim(),
    "",
  ];
  for (const sev of ["error", "warning", "info"]) {
    const groups = r.groups.filter((g) => g.severity === sev);
    if (!groups.length) continue;
    out.push("-".repeat(60), sev.toUpperCase(), "-".repeat(60), "");
    for (const g of groups) {
      out.push(`* ${g.title}   [${g.rule}]`);
      if (g.nodes.length) out.push(`  Steps: ${g.nodes.join(", ")}`);
      for (const d of g.details) out.push("", d.split("\n").map((l) => "  " + l).join("\n"));
      if (g.meaning) out.push("", "  What this means:", `  ${g.meaning}`);
      if (g.fix) out.push("", "  How to fix it:", g.fix.split("\n").map((l) => "  " + l).join("\n"));
      out.push("");
    }
  }
  out.push(
    "-".repeat(60),
    "Checked with n8n-workflow-linter — github.com/Redsf/n8n-workflow-linter",
    "The workflow file was not uploaded anywhere; this ran in the browser."
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
    alert("That file is over 12 MB, which is far larger than any n8n export. Check it is the right file.");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => check(String(reader.result), file.name);
  reader.onerror = () => alert("Could not read that file.");
  reader.readAsText(file);
}

/* ---------------------------------------------------------------- wiring */

ui.dropzone.addEventListener("click", () => ui.fileInput.click());
ui.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ui.fileInput.click(); }
});
ui.fileInput.addEventListener("change", (e) => readFile(e.target.files[0]));

["dragenter", "dragover"].forEach((evt) =>
  ui.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    ui.dropzone.classList.add("is-over");
  })
);
["dragleave", "drop"].forEach((evt) =>
  ui.dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    ui.dropzone.classList.remove("is-over");
  })
);
ui.dropzone.addEventListener("drop", (e) => readFile(e.dataTransfer.files[0]));

// Stop a stray drop elsewhere on the page from navigating away from the app.
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

ui.trySample.addEventListener("click", async () => {
  show("loading");
  ui.loadingText.textContent = "Loading the sample workflow…";
  try {
    const res = await fetch(new URL("./sample-workflow.json", import.meta.url));
    check(await res.text(), "sample-workflow.json");
  } catch {
    show("input");
    alert("Could not load the sample file.");
  }
});

ui.pasteToggle.addEventListener("click", () => {
  ui.pastePanel.hidden = !ui.pastePanel.hidden;
  if (!ui.pastePanel.hidden) ui.pasteArea.focus();
});
ui.pasteRun.addEventListener("click", () => {
  const text = ui.pasteArea.value.trim();
  if (text) check(text, "pasted-workflow.json");
});

ui.viewPlain.addEventListener("click", () => setView("plain"));
ui.viewTech.addEventListener("click", () => setView("tech"));
function setView(mode) {
  const plain = mode === "plain";
  ui.findings.hidden = !plain;
  ui.techOutput.hidden = plain;
  ui.infoToggleWrap.hidden = !plain || ui.infoToggle.textContent === "";
  ui.viewPlain.classList.toggle("is-on", plain);
  ui.viewTech.classList.toggle("is-on", !plain);
  ui.viewPlain.setAttribute("aria-pressed", String(plain));
  ui.viewTech.setAttribute("aria-pressed", String(!plain));
  if (plain && lastResult) renderFindings(lastResult);
}

ui.infoToggle.addEventListener("click", () => {
  showInfo = !showInfo;
  renderFindings(lastResult);
});

ui.copyBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(currentReport());
    ui.copyBtn.textContent = "Copied";
    setTimeout(() => (ui.copyBtn.textContent = "Copy report"), 1600);
  } catch {
    alert("Your browser blocked clipboard access. Use Download instead.");
  }
});

ui.downloadBtn.addEventListener("click", () => {
  const blob = new Blob([currentReport()], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(lastResult?.filename || "workflow").replace(/\.json$/, "")}-lint-report.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

ui.againBtn.addEventListener("click", () => {
  ui.fileInput.value = "";
  ui.pasteArea.value = "";
  show("input");
  window.scrollTo({ top: 0, behavior: "smooth" });
});
