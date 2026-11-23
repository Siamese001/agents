"""Pure-White (#ffffff) HTML/CSS/JS Template for Blind QRELS Calibration Studio (DIE Parity).

Matches DIE Repo's 2026 Pure-White Click-to-Grade Studio standard:
- Locked `color-scheme: light only` and `background: #ffffff !important`
- Collapsible 3-step Quick Start Guide + per-box inline rater instructions
- Clickable header pill nav (`✓` graded, `⚑` quarantined, active pill, overlap %, seed)
- Separated Core Candidate Statement + Source Evidence Excerpts + collapsed
  Reference-Only Scope/Boilerplate Drawer (`do not grade`)
- Step 1 Quick Yes/No Consistency Checks (mechanically locking Grade 2/3 when failed)
- Step 2 Behavior-Anchored 3-2-1-0 Click-to-Grade Buttons with hover/click criteria
- Step 3 Rejection Taxonomy Pills + Rationale Input (mechanically required on Grade 0)
- Step 4 Safe Quarantine Escape Hatch (Abstain: Insufficient Evidence / Flag: Defective Query)
"""

from __future__ import annotations

QRELS_STUDIO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light only" />
  <title>Blind QRELS Relevance Calibration Studio</title>
  <style>
    :root {
      color-scheme: light only;
      --bg: #ffffff; --panel: #ffffff; --panel-subtle: #ffffff;
      --border: #cbd5e1; --border-strong: #94a3b8;
      --text: #0f172a; --muted: #475569;
      --accent: #0f172a; --accent-bg: #ffffff;
      --pass: #047857; --pass-bg: #ffffff;
      --fail: #b91c1c; --fail-bg: #ffffff;
      --warn: #b45309; --warn-bg: #ffffff;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; background: #ffffff !important; background-color: #ffffff !important; color: var(--text);
      color-scheme: light only;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.5;
    }
    header {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      padding: 12px 22px; background: #ffffff; border-bottom: 1px solid var(--border);
    }
    .title-wrap h1 { margin: 0; font-size: 16px; font-weight: 700; color: var(--text); }
    .title-wrap p { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
    .pill-nav { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; max-width: 62%; justify-content: flex-end; }
    .item-pill {
      padding: 5px 10px; border-radius: 999px; border: 1px solid var(--border);
      background: #ffffff; color: var(--muted); font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .item-pill.active { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); border-width: 2px; }
    .item-pill.done { border-color: var(--pass); color: var(--pass); background: var(--pass-bg); }
    .item-pill.quarantined { border-color: var(--warn); color: var(--warn); background: var(--warn-bg); }
    main {
      display: grid; grid-template-columns: 1.25fr 1fr; gap: 18px;
      padding: 16px 22px 24px; max-width: 1520px; margin: 0 auto; background: #ffffff;
    }
    @media (max-width: 1024px) { main { grid-template-columns: 1fr; } }
    .card {
      background: #ffffff; border: 1px solid var(--border); border-radius: 10px;
      padding: 15px 17px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    details.guide-banner {
      grid-column: 1 / -1; background: #ffffff; border: 1px solid var(--border-strong);
      border-left: 4px solid var(--text); border-radius: 10px; padding: 10px 14px; font-size: 12.5px;
    }
    details.guide-banner summary { cursor: pointer; font-weight: 700; color: var(--text); font-size: 13px; }
    .guide-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8px; }
    @media (max-width: 900px) { .guide-steps { grid-template-columns: 1fr; } }
    .guide-step { background: #ffffff; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; color: var(--text); }
    .summary-banner {
      grid-column: 1 / -1; background: var(--pass-bg); border: 1px solid var(--pass);
      color: var(--pass); border-radius: 10px; padding: 14px 18px; display: none; font-size: 13px;
    }
    .meta-bar {
      display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--muted);
      padding-bottom: 10px; margin-bottom: 10px; border-bottom: 1px solid var(--border);
    }
    .badge {
      background: #ffffff; border: 1px solid var(--border); padding: 2px 8px;
      border-radius: 6px; font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: var(--text);
    }
    .prompt-banner {
      background: #ffffff; border: 1px solid var(--border); border-left: 4px solid var(--text);
      border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;
    }
    .section-kicker {
      font-size: 11px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
      color: var(--accent); margin-bottom: 4px;
    }
    .box-guide { font-size: 12px; color: var(--muted); margin: 3px 0 8px; line-height: 1.4; }
    .prompt-text { font-size: 14.5px; font-weight: 600; color: var(--text); }
    .candidate-box {
      background: #ffffff; border: 1px solid var(--border-strong); border-radius: 8px; padding: 14px;
      white-space: pre-wrap; font-size: 13.5px; max-height: 38vh; overflow-y: auto; color: var(--text);
    }
    .evidence-panel {
      margin-top: 12px; background: #ffffff; border: 1px solid var(--border);
      border-radius: 8px; padding: 10px 12px;
    }
    .evidence-item {
      background: #ffffff; border: 1px solid var(--border); border-radius: 6px;
      padding: 8px 10px; margin-top: 6px; font-size: 12px; color: var(--text);
    }
    .evidence-src { font-weight: 700; color: var(--accent); font-size: 11px; }
    details.boilerplate-drawer {
      margin-top: 10px; background: #ffffff; border: 1px dashed var(--border-strong);
      border-radius: 8px; padding: 8px 12px; font-size: 12px; color: var(--muted);
    }
    details.boilerplate-drawer summary { cursor: pointer; font-weight: 600; color: var(--muted); }
    details.boilerplate-drawer pre { white-space: pre-wrap; margin: 8px 0 0; font-size: 11.5px; color: var(--muted); }
    .decision-box { border: 1px solid var(--border); border-radius: 9px; padding: 11px 12px; margin-bottom: 10px; background: #ffffff; }
    .box-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .atomic-grid { display: grid; grid-template-columns: 1fr; gap: 6px; }
    .atomic-chip {
      display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px;
      border: 1px solid var(--border); border-radius: 7px; background: #ffffff;
      font-size: 11.5px; color: var(--text);
    }
    .atomic-toggle { display: flex; gap: 4px; flex-shrink: 0; }
    .chip-btn {
      padding: 3px 8px; border-radius: 5px; border: 1px solid var(--border); background: #ffffff;
      font-size: 11px; font-weight: 700; cursor: pointer; color: var(--muted);
    }
    .chip-btn.yes { background: var(--pass); color: #ffffff; border-color: var(--pass); }
    .chip-btn.no { background: var(--fail); color: #ffffff; border-color: var(--fail); }
    .grade-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 6px; }
    .grade-btn {
      padding: 10px 6px; border-radius: 8px; border: 1px solid var(--border-strong);
      background: #ffffff; color: var(--text); font-size: 12.5px; font-weight: 700; cursor: pointer;
      display: flex; flex-direction: column; align-items: center; gap: 2px;
    }
    .grade-btn span.sub { font-size: 10.5px; font-weight: 500; color: var(--muted); }
    .grade-btn.selected { background: var(--accent); color: #ffffff; border-color: var(--accent); }
    .grade-btn.selected span.sub { color: #e2e8f0; }
    .grade-btn:disabled { opacity: 0.38; cursor: not-allowed; }
    .anchor-hint {
      margin-top: 8px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px;
      font-size: 12px; color: var(--text); background: #ffffff; min-height: 42px;
    }
    .tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
    .tag-pill {
      padding: 4px 9px; border-radius: 999px; border: 1px solid var(--border); background: #ffffff;
      color: var(--muted); font-size: 11px; font-weight: 600; cursor: pointer;
    }
    .tag-pill.active { background: var(--fail-bg); color: var(--fail); border-color: var(--fail); border-width: 2px; }
    .notes-input {
      width: 100%; padding: 8px 10px; border-radius: 7px; border: 1px solid var(--border-strong);
      background: #ffffff; color: var(--text); font-size: 12.5px;
    }
    .save-btn {
      width: 100%; margin-top: 10px; padding: 10px; border-radius: 8px; border: 1px solid var(--pass);
      background: #ffffff; color: var(--pass); font-size: 13px; font-weight: 700; cursor: pointer;
    }
    .save-btn:hover:not(:disabled) { background: var(--pass); color: #ffffff; }
    .save-btn:disabled { opacity: 0.42; cursor: not-allowed; }
    .escape-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .escape-btn {
      padding: 6px 10px; border-radius: 7px; border: 1px solid var(--warn); background: #ffffff;
      color: var(--warn); font-size: 11.5px; font-weight: 600; cursor: pointer;
    }
    .rule-hint { font-size: 11.5px; color: var(--muted); margin-top: 6px; }
    .toast { margin-top: 10px; font-size: 12px; padding: 9px 12px; border-radius: 8px; display: none; }
    .toast.ok { display: block; background: #ffffff; color: var(--pass); border: 1px solid var(--pass); }
    .toast.err { display: block; background: #ffffff; color: var(--fail); border: 1px solid var(--fail); }
  </style>
</head>
<body>
  <header>
    <div class="title-wrap">
      <h1>Blind QRELS Relevance Calibration Studio</h1>
      <p id="subhead">Loading blinded 4-channel QRELS pool...</p>
    </div>
    <div class="pill-nav" id="pillNav"></div>
  </header>
  <main>
    <details open class="guide-banner" id="quickGuide">
      <summary>Quick Start Guide: How to Grade Each Passage (~30 seconds) - click to collapse</summary>
      <div class="guide-steps">
        <div class="guide-step"><strong>1. Read Core Statement Only:</strong> Read the <strong>Query</strong> and <strong>Core Candidate Statement</strong> on the left. Ignore dimmed boilerplate footers in the Reference-Only drawer.</div>
        <div class="guide-step"><strong>2. Score 3-2-1-0 Rigorously:</strong> Optionally check the 5 consistency toggles, then click <strong>3</strong> (Authoritative), <strong>2</strong> (Supporting), <strong>1</strong> (Marginal Stub), or <strong>0</strong> (Irrelevant/Confounder).</div>
        <div class="guide-step"><strong>3. Explain Grade 0 or Skip Safely:</strong> For <strong>Grade 0</strong>, select at least 1 rejection tag or type an 8+ char note. If evidence is missing or the query is broken, use <strong>Abstain</strong> or <strong>Flag</strong> instead of guessing.</div>
      </div>
    </details>
    <div class="summary-banner" id="summaryBanner"></div>
    <section class="card">
      <div class="meta-bar" id="metaBar"></div>
      <div class="prompt-banner">
        <div class="section-kicker">Query &amp; Target Surface (Grade Relevance Against This Need)</div>
        <div class="box-guide" style="margin:2px 0 6px;">Evaluate whether the Core Candidate Statement below directly answers this exact retrieval query.</div>
        <div class="prompt-text" id="promptBox"></div>
      </div>
      <div class="section-kicker" style="margin-top:4px;">Core Candidate Statement (Grade Only This Text)</div>
      <div class="candidate-box" id="candidateBox"></div>
      <div class="evidence-panel" id="evidencePanel">
        <div class="section-kicker" style="margin:0;">Source Fact &amp; Provenance Excerpts</div>
        <div class="box-guide" style="margin:2px 0 4px;">Cross-check metrics, dates (MM/DD/YYYY), and employer boundaries against linked graph evidence.</div>
        <div id="evidenceList"></div>
      </div>
      <details class="boilerplate-drawer" id="boilerplateDrawer" style="display:none;">
        <summary>Reference Only: Repeated Scope &amp; Boilerplate Footer (do not grade)</summary>
        <pre id="boilerplateBox"></pre>
      </details>
    </section>
    <section class="card">
      <div class="decision-box">
        <div class="section-kicker">Step 1: Quick Consistency Checks (Optional Helper)</div>
        <div class="box-guide">Tap <strong>Yes</strong> or <strong>No</strong> to catch stubs, wrong employers, or policy conflicts. Marking a cap check <strong>No</strong> mechanically locks Grades 2 and 3.</div>
        <div class="atomic-grid" id="atomicGrid"></div>
      </div>
      <div class="decision-box">
        <div class="box-head">
          <div class="section-kicker" style="margin:0;">Step 2: Behavior-Anchored Relevance Grade (Required)</div>
          <span class="badge" id="selectedGradeBadge">Not selected</span>
        </div>
        <div class="box-guide">Hover or click any grade (<strong>3</strong> Authoritative, <strong>2</strong> Supporting, <strong>1</strong> Marginal Stub, <strong>0</strong> Irrelevant/Confounder) to read exact criteria.</div>
        <div class="grade-row" id="gradeRow"></div>
        <div class="anchor-hint" id="anchorHint">Hover or click 3, 2, 1, or 0 to inspect behavior-anchored criteria.</div>
      </div>
      <div class="decision-box">
        <div class="section-kicker">Step 3: Rejection Tags &amp; Rationale (Required for Grade 0)</div>
        <div class="box-guide"><strong>Grades 1-3:</strong> notes optional, click Save Grade &amp; Next. <strong>Grade 0:</strong> pick at least 1 rejection tag or write an 8+ character reason to unlock Save.</div>
        <div class="tag-row" id="tagRow"></div>
        <input class="notes-input" id="notesInput" type="text" placeholder="Optional for Grades 1-3; required for Grade 0 if no tag is selected (min 8 chars)..." oninput="updateSaveLocks()" />
        <button class="save-btn" id="btnSave" onclick="submitGrade()" disabled>Save Grade &amp; Next</button>
        <div class="rule-hint" id="ruleHint"></div>
      </div>
      <div class="decision-box" style="margin-bottom:0;">
        <div class="section-kicker">Step 4: Can't Grade This Item? (Quarantine Safely)</div>
        <div class="box-guide">Never guess. Quarantined items are sealed separately and excluded from scored QRELS denominators.</div>
        <div class="escape-row">
          <button class="escape-btn" onclick="submitQuarantine('ABSTAIN_INSUFFICIENT_EVIDENCE')">Abstain: Insufficient Evidence</button>
          <button class="escape-btn" onclick="submitQuarantine('DEFECTIVE_QUERY')">Flag: Defective Query</button>
        </div>
      </div>
      <div class="toast" id="toastBox"></div>
    </section>
  </main>
  <script>
    let STATE = { items: [], rubric: {}, atomic_checks: [], rejection_tags: [], savedByPair: {}, quarantinedByPair: {}, idx: 0 };
    let DRAFT = { grade: null, atomic: {}, tags: new Set() };

    async function loadState() {
      const res = await fetch("/api/state");
      STATE = await res.json();
      const firstOpen = STATE.items.findIndex(it => !STATE.savedByPair[it.pair_id] && !STATE.quarantinedByPair[it.pair_id]);
      STATE.idx = firstOpen >= 0 ? firstOpen : 0;
      loadDraft(); renderNav(); renderItem();
    }
    function loadDraft() {
      const it = STATE.items[STATE.idx];
      const ex = it ? STATE.savedByPair[it.pair_id] : null;
      if (ex) {
        DRAFT = { grade: ex.relevance_grade, atomic: { ...(ex.atomic_checks || {}) }, tags: new Set(ex.rejection_tags || []) };
        document.getElementById("notesInput").value = ex.critique_rationale || ex.notes || "";
      } else {
        DRAFT = { grade: null, atomic: {}, tags: new Set() };
        document.getElementById("notesInput").value = "";
      }
    }
    function renderNav() {
      const nav = document.getElementById("pillNav"); nav.innerHTML = "";
      const done = STATE.items.filter(it => STATE.savedByPair[it.pair_id]).length;
      const quar = STATE.items.filter(it => STATE.quarantinedByPair[it.pair_id]).length;
      document.getElementById("subhead").textContent =
        `Surface: ${STATE.surface || "multi"} | Graded: ${done}/${STATE.items.length} | Quarantined: ${quar} | Seed: ${STATE.presentation_seed ?? "fixed"} | Blind Mode: Ranks & Channels Hidden`;
      STATE.items.forEach((it, i) => {
        const b = document.createElement("button");
        const isD = Boolean(STATE.savedByPair[it.pair_id]);
        const isQ = Boolean(STATE.quarantinedByPair[it.pair_id]);
        b.className = "item-pill" + (i === STATE.idx ? " active" : "") + (isD ? " done" : (isQ ? " quarantined" : ""));
        b.textContent = (isD ? "✓ " : (isQ ? "⚑ " : "")) + `${i + 1}`;
        b.title = `${it.surface} | ${it.target_section}`;
        b.onclick = () => { STATE.idx = i; loadDraft(); hideToast(); renderNav(); renderItem(); };
        nav.appendChild(b);
      });
      const ban = document.getElementById("summaryBanner");
      if (done + quar === STATE.items.length && STATE.items.length > 0) {
        ban.style.display = "block";
        ban.innerHTML = `<strong>Completed ${done} QRELS grade(s) and ${quar} quarantined item(s).</strong> Sealed store: <code>${STATE.store_path}</code>`;
      } else { ban.style.display = "none"; }
    }
    function isCappedAt1() {
      return (STATE.atomic_checks || []).some(c => c.caps_grade_at_1_when_false && DRAFT.atomic[c.id] === false);
    }
    function renderItem() {
      const it = STATE.items[STATE.idx]; if (!it) return;
      document.getElementById("metaBar").innerHTML =
        `<span>Item <strong>${STATE.idx + 1} of ${STATE.items.length}</strong></span>` +
        `<span class="badge">${it.surface || "candidate_graph"}</span>` +
        `<span class="badge">section: ${it.target_section || "general"}</span>` +
        `<span class="badge">sha256: ${(it.artifact_sha256 || "").slice(0, 14)}...</span>`;
      document.getElementById("promptBox").textContent = it.query_text || "(No query)";
      document.getElementById("candidateBox").textContent = it.core_statement || "(Empty core statement)";
      const evList = document.getElementById("evidenceList"); evList.innerHTML = "";
      const excerpts = it.source_evidence_excerpts || [];
      if (excerpts.length === 0) {
        evList.innerHTML = `<div class="evidence-item">Grade directly from the Core Candidate Statement above. Use <strong>Abstain: Insufficient Evidence</strong> if facts cannot be verified.</div>`;
      } else {
        excerpts.forEach(ev => {
          const d = document.createElement("div"); d.className = "evidence-item";
          d.innerHTML = `<div class="evidence-src">${ev.source || "Graph Source"}${ev.date ? " (" + ev.date + ")" : ""}</div><div></div>`;
          d.lastChild.textContent = ev.excerpt || "";
          evList.appendChild(d);
        });
      }
      const dr = document.getElementById("boilerplateDrawer");
      if (it.boilerplate_footer) {
        dr.style.display = "block"; dr.open = false;
        document.getElementById("boilerplateBox").textContent = it.boilerplate_footer;
      } else { dr.style.display = "none"; }

      const ag = document.getElementById("atomicGrid"); ag.innerHTML = "";
      (STATE.atomic_checks || []).forEach(c => {
        const val = DRAFT.atomic[c.id];
        const row = document.createElement("div"); row.className = "atomic-chip";
        row.innerHTML = `<span>${c.label}</span><div class="atomic-toggle">` +
          `<button class="chip-btn ${val === true ? "yes" : ""}" onclick="setAtomic('${c.id}', true)">Yes</button>` +
          `<button class="chip-btn ${val === false ? "no" : ""}" onclick="setAtomic('${c.id}', false)">No</button></div>`;
        ag.appendChild(row);
      });

      const capped = isCappedAt1();
      if (capped && DRAFT.grade !== null && DRAFT.grade >= 2) { DRAFT.grade = null; }
      const gr = document.getElementById("gradeRow"); gr.innerHTML = "";
      const gradesSpec = (STATE.rubric && STATE.rubric.grades) || {};
      [3, 2, 1, 0].forEach(g => {
        const info = gradesSpec[String(g)] || { short_label: String(g), meaning: "" };
        const btn = document.createElement("button");
        btn.className = "grade-btn" + (DRAFT.grade === g ? " selected" : "");
        btn.disabled = capped && g >= 2;
        btn.innerHTML = `<span>Grade ${g}</span><span class="sub">${info.short_label}</span>`;
        btn.onmouseenter = () => previewGrade(g);
        btn.onmouseleave = () => restoreGradeHint();
        btn.onclick = () => { DRAFT.grade = g; renderItem(); };
        gr.appendChild(btn);
      });
      restoreGradeHint();

      const tr = document.getElementById("tagRow"); tr.innerHTML = "";
      (STATE.rejection_tags || []).forEach(t => {
        const p = document.createElement("button");
        p.className = "tag-pill" + (DRAFT.tags.has(t.id) ? " active" : "");
        p.textContent = t.label;
        p.onclick = () => { DRAFT.tags.has(t.id) ? DRAFT.tags.delete(t.id) : DRAFT.tags.add(t.id); renderItem(); };
        tr.appendChild(p);
      });
      updateSaveLocks();
    }
    function previewGrade(g) {
      const info = ((STATE.rubric && STATE.rubric.grades) || {})[String(g)];
      if (info) document.getElementById("anchorHint").textContent = `Grade ${g} (${info.short_label}): ${info.meaning}`;
    }
    function restoreGradeHint() {
      const b = document.getElementById("selectedGradeBadge");
      if (DRAFT.grade === null) {
        b.textContent = "Not selected";
        document.getElementById("anchorHint").textContent = "Hover or click 3, 2, 1, or 0 to inspect behavior-anchored criteria.";
      } else {
        b.textContent = `Selected: Grade ${DRAFT.grade}`;
        previewGrade(DRAFT.grade);
      }
    }
    function setAtomic(id, val) { DRAFT.atomic[id] = val; renderItem(); }
    function updateSaveLocks() {
      const btn = document.getElementById("btnSave");
      const hint = document.getElementById("ruleHint");
      const noteLen = (document.getElementById("notesInput").value || "").trim().length;
      if (DRAFT.grade === null) {
        btn.disabled = true;
        hint.textContent = isCappedAt1()
          ? "Grades 2 and 3 locked by failed Step 1 consistency check. Select Grade 1 or Grade 0."
          : "Select a relevance grade (3, 2, 1, or 0) to enable Save.";
        return;
      }
      if (DRAFT.grade === 0 && DRAFT.tags.size === 0 && noteLen < 8) {
        btn.disabled = true;
        hint.textContent = "Grade 0 requires at least 1 rejection tag or an 8+ character rationale.";
        return;
      }
      btn.disabled = false;
      hint.textContent = `Ready to save Grade ${DRAFT.grade} and advance to the next ungraded item.`;
    }
    function showToast(msg, ok) { const t = document.getElementById("toastBox"); t.className = "toast " + (ok ? "ok" : "err"); t.textContent = msg; }
    function hideToast() { const t = document.getElementById("toastBox"); t.className = "toast"; t.textContent = ""; }
    function advanceNext() {
      const nxt = STATE.items.findIndex((it, i) => i > STATE.idx && !STATE.savedByPair[it.pair_id] && !STATE.quarantinedByPair[it.pair_id]);
      if (nxt >= 0) { STATE.idx = nxt; loadDraft(); }
      renderNav(); renderItem();
    }
    async function submitGrade() {
      const it = STATE.items[STATE.idx]; if (!it || DRAFT.grade === null) return;
      const notes = (document.getElementById("notesInput").value || "").trim();
      const res = await fetch("/api/grade", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pair_id: it.pair_id, query_id: it.query_id, record_id: it.record_id,
          surface: it.surface, topic_family: it.topic_family, partition: it.partition,
          artifact_sha256: it.artifact_sha256, relevance_grade: DRAFT.grade,
          atomic_checks: DRAFT.atomic, rejection_tags: Array.from(DRAFT.tags),
          critique_rationale: notes, notes: notes
        })
      });
      const data = await res.json();
      if (!res.ok) { showToast(data.error || "Failed to save grade.", false); return; }
      STATE.savedByPair[it.pair_id] = data.record;
      delete STATE.quarantinedByPair[it.pair_id];
      showToast(`Saved Grade ${DRAFT.grade} (${data.record.event_id.slice(0, 14)}...).`, true);
      advanceNext();
    }
    async function submitQuarantine(reason) {
      const it = STATE.items[STATE.idx]; if (!it) return;
      const notes = (document.getElementById("notesInput").value || "").trim();
      const res = await fetch("/api/quarantine", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pair_id: it.pair_id, query_id: it.query_id, record_id: it.record_id,
          surface: it.surface, topic_family: it.topic_family, partition: it.partition,
          artifact_sha256: it.artifact_sha256, reason: reason, notes: notes
        })
      });
      const data = await res.json();
      if (!res.ok) { showToast(data.error || "Failed to quarantine item.", false); return; }
      STATE.quarantinedByPair[it.pair_id] = data.quarantined;
      showToast(`Quarantined (${reason}). Excluded from scored QRELS denominators.`, true);
      advanceNext();
    }
    loadState();
  </script>
</body>
</html>
"""

__all__ = ["QRELS_STUDIO_HTML"]
