"""Pure-White (#ffffff) HTML/CSS/JS Template for Blind External-Rubric Calibration Studio (DIE Parity)."""
from __future__ import annotations

STUDIO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light only" />
  <title>Blind Human Calibration Studio</title>
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
    .pill-nav { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .item-pill {
      padding: 5px 10px; border-radius: 999px; border: 1px solid var(--border);
      background: #ffffff; color: var(--muted); font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .item-pill.active { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }
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
    .meta-bar {
      display: flex; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--muted);
      padding-bottom: 10px; margin-bottom: 10px; border-bottom: 1px solid var(--border);
    }
    .badge {
      background: var(--panel-subtle); border: 1px solid var(--border); padding: 2px 8px;
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
    .prompt-text { font-size: 14.5px; font-weight: 600; color: var(--text); }
    .candidate-box {
      background: #ffffff; border: 1px solid var(--border); border-radius: 8px; padding: 14px;
      white-space: pre-wrap; font-size: 13.5px; max-height: 40vh; overflow-y: auto; color: var(--text);
    }
    .evidence-panel {
      margin-top: 12px; background: var(--panel-subtle); border: 1px solid var(--border);
      border-radius: 8px; padding: 10px 12px;
    }
    .evidence-item {
      background: #ffffff; border: 1px solid var(--border); border-radius: 6px;
      padding: 8px 10px; margin-top: 6px; font-size: 12px; color: var(--text);
    }
    .evidence-src { font-weight: 700; color: var(--accent); font-size: 11px; }
    details.lineage-drawer {
      margin-top: 10px; background: var(--panel-subtle); border: 1px solid var(--border);
      border-radius: 8px; padding: 8px 12px; font-size: 12px; color: var(--muted);
    }
    details.lineage-drawer summary { cursor: pointer; font-weight: 600; color: var(--text); }
    details.lineage-drawer pre { white-space: pre-wrap; margin: 8px 0 0; font-size: 11.5px; color: var(--text); }
    .atomic-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px; }
    .atomic-chip {
      display: flex; justify-content: space-between; align-items: center; gap: 6px; padding: 6px 8px;
      border: 1px solid var(--border); border-radius: 7px; background: var(--panel-subtle);
      font-size: 11.5px; color: var(--text);
    }
    .atomic-toggle { display: flex; gap: 4px; }
    .chip-btn {
      padding: 3px 7px; border-radius: 5px; border: 1px solid var(--border); background: #ffffff;
      font-size: 11px; font-weight: 700; cursor: pointer; color: var(--muted);
    }
    .chip-btn.yes { background: var(--pass); color: #ffffff; border-color: var(--pass); }
    .chip-btn.no { background: var(--fail); color: #ffffff; border-color: var(--fail); }
    .pillar-block {
      margin-bottom: 8px; padding: 9px 11px; border-radius: 8px;
      background: var(--panel-subtle); border: 1px solid var(--border);
    }
    .pillar-head { display: flex; justify-content: space-between; margin-bottom: 5px; }
    .pillar-title { font-size: 12.5px; font-weight: 700; color: var(--text); }
    .pillar-weight { font-size: 11px; color: var(--muted); }
    .score-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
    .score-btn {
      padding: 6px 0; border-radius: 6px; border: 1px solid var(--border-strong);
      background: #ffffff; color: var(--text); font-size: 13px; font-weight: 700; cursor: pointer;
    }
    .score-btn.selected { background: var(--accent); color: #ffffff; border-color: var(--accent); }
    .anchor-hint { margin-top: 4px; font-size: 11.5px; color: var(--muted); }
    .tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
    .tag-pill {
      padding: 4px 8px; border-radius: 999px; border: 1px solid var(--border); background: #ffffff;
      color: var(--muted); font-size: 11px; font-weight: 600; cursor: pointer;
    }
    .tag-pill.active { background: var(--fail-bg); color: var(--fail); border-color: var(--fail); }
    .notes-input {
      width: 100%; padding: 8px 10px; border-radius: 7px; border: 1px solid var(--border-strong);
      background: #ffffff; color: var(--text); font-size: 12.5px;
    }
    .verdict-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0 8px; }
    .verdict-btn {
      padding: 10px; border-radius: 8px; border: 1px solid var(--border); background: #ffffff;
      font-size: 13px; font-weight: 700; cursor: pointer;
    }
    .verdict-btn:disabled { opacity: 0.42; cursor: not-allowed; }
    .verdict-btn.pass { border-color: var(--pass); color: var(--pass); background: var(--pass-bg); }
    .verdict-btn.pass:hover:not(:disabled) { background: var(--pass); color: #ffffff; }
    .verdict-btn.fail { border-color: var(--fail); color: var(--fail); background: var(--fail-bg); }
    .verdict-btn.fail:hover:not(:disabled) { background: var(--fail); color: #ffffff; }
    .escape-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
    .escape-btn {
      padding: 6px 10px; border-radius: 7px; border: 1px solid var(--warn); background: var(--warn-bg);
      color: var(--warn); font-size: 11.5px; font-weight: 600; cursor: pointer;
    }
    .rule-hint { font-size: 11.5px; color: var(--muted); margin-top: 4px; }
    .toast { margin-top: 10px; font-size: 12px; padding: 9px 12px; border-radius: 8px; display: none; }
    .toast.ok { display: block; background: var(--pass-bg); color: var(--pass); border: 1px solid var(--pass); }
    .toast.err { display: block; background: var(--fail-bg); color: var(--fail); border: 1px solid var(--fail); }
    .summary-banner {
      grid-column: 1 / -1; background: var(--pass-bg); border: 1px solid var(--pass);
      color: var(--pass); border-radius: 10px; padding: 14px 18px; display: none; font-size: 13px;
    }
    details.guide-banner {
      grid-column: 1 / -1; background: #ffffff; border: 1px solid var(--border-strong);
      border-left: 4px solid var(--text); border-radius: 10px; padding: 10px 14px; font-size: 12.5px;
    }
    details.guide-banner summary { cursor: pointer; font-weight: 700; color: var(--text); font-size: 13px; }
    .guide-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8px; }
    @media (max-width: 900px) { .guide-steps { grid-template-columns: 1fr; } }
    .guide-step { background: #ffffff; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; color: var(--text); }
    .decision-box { border: 1px solid var(--border); border-radius: 9px; padding: 11px 12px; margin-bottom: 10px; background: #ffffff; }
    .box-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .box-guide { font-size: 12px; color: var(--muted); margin: 3px 0 8px; line-height: 1.4; }
  </style>
</head>
<body>
  <header>
    <div class="title-wrap">
      <h1>Blind External-Rubric Human Calibration Studio</h1>
      <p id="subhead">Loading blind holdout pool...</p>
    </div>
    <div class="pill-nav" id="pillNav"></div>
  </header>
  <main>
    <details open class="guide-banner" id="quickGuide">
      <summary>Quick Start Guide: How to Grade Each Item (~45 seconds) - click to collapse</summary>
      <div class="guide-steps">
        <div class="guide-step"><strong>1. Read Left (Evidence First):</strong> Read the <strong>Prompt</strong> and <strong>Core Answer</strong>, then spot-check facts against the <strong>Source Evidence Excerpts</strong> right below.</div>
        <div class="guide-step"><strong>2. Score Right (4 Pillars):</strong> Optionally tap <strong>Pass/Fail</strong> on the 6 quick checks, then score all <strong>4 pillars</strong> (<code>1</code> = Broken, <code>3</code> = Acceptable, <code>5</code> = Great).</div>
        <div class="guide-step"><strong>3. Save or Skip Safely:</strong> Click <strong>Save as PASS</strong> (needs <code>F &gt;= 4</code>, all <code>&gt;= 3</code>) or pick a defect tag and click <strong>Save as FAIL</strong>. Unsure? Click <strong>Abstain</strong> or <strong>Flag</strong> instead of guessing.</div>
      </div>
    </details>
    <div class="summary-banner" id="summaryBanner"></div>
    <section class="card">
      <div class="meta-bar" id="metaBar"></div>
      <div class="prompt-banner">
        <div class="section-kicker">Prompt Being Answered (React to This Question)</div>
        <div class="box-guide" style="margin:2px 0 6px;">Check whether the Core Answer below accurately and completely answers this exact question.</div>
        <div class="prompt-text" id="promptBox"></div>
      </div>
      <div class="section-kicker" style="margin-top:4px;">Core Candidate Answer</div>
      <div class="candidate-box" id="candidateBox"></div>
      <div class="evidence-panel" id="evidencePanel">
        <div class="section-kicker" style="margin:0;">Source Evidence Excerpts (Verify Factual Faithfulness Against Ground Truth)</div>
        <div class="box-guide" style="margin:2px 0 4px;">Compare claims, dates, and owners in the Core Answer against these real Knowledge Graph excerpts.</div>
        <div id="evidenceList"></div>
      </div>
      <details class="lineage-drawer" id="lineageDrawer" style="display:none;">
        <summary>Reference Only: Graph Lineage Telemetry (grade the core answer above)</summary>
        <pre id="lineageBox"></pre>
      </details>
    </section>
    <section class="card">
      <div class="decision-box">
        <div class="section-kicker">Step 1: Quick Yes/No Checks (Optional Helper)</div>
        <div class="box-guide">Tap <strong>Pass</strong> or <strong>Fail</strong> to catch defects fast. Marking either top factual check <strong>Fail</strong> locks Save as PASS so unsupported claims cannot slip through.</div>
        <div class="atomic-grid" id="atomicGrid" style="margin-bottom:0;"></div>
      </div>
      <div class="decision-box">
        <div class="box-head">
          <div class="section-kicker" style="margin:0;">Step 2: 4-Pillar Score (Required)</div>
          <span class="badge" id="pillarProgress">0/4 scored</span>
        </div>
        <div class="box-guide">Click one number per row: <strong>1</strong> Severe defect, <strong>2</strong> Major gap, <strong>3</strong> Acceptable, <strong>4</strong> Strong, <strong>5</strong> Exemplary. Hover any number to preview its definition. Passing needs <strong>[F] &gt;= 4</strong> and all rows <strong>&gt;= 3</strong>.</div>
        <div id="pillarsContainer"></div>
      </div>
      <div class="decision-box">
        <div class="section-kicker">Step 3: Final Decision (PASS or FAIL)</div>
        <div class="box-guide"><strong>For PASS:</strong> no tags needed, click Save as PASS &amp; Next. <strong>For FAIL:</strong> click at least 1 defect tag below (or type an 8+ character reason) to unlock Save as FAIL &amp; Next.</div>
        <div class="tag-row" id="tagRow"></div>
        <input class="notes-input" id="notesInput" type="text" placeholder="Optional for PASS; required for FAIL if no defect tag is selected (min 8 chars)..." oninput="updateVerdictLocks()" />
        <div class="verdict-row">
          <button class="verdict-btn pass" id="btnPass" onclick="submitGrade('PASS')" disabled>Save as PASS &amp; Next</button>
          <button class="verdict-btn fail" id="btnFail" onclick="submitGrade('FAIL')" disabled>Save as FAIL &amp; Next</button>
        </div>
        <div class="rule-hint" id="ruleHint"></div>
      </div>
      <div class="decision-box" style="margin-bottom:0;">
        <div class="section-kicker">Step 4: Can't Grade This Item? (Skip Safely)</div>
        <div class="box-guide">Never guess. Use <strong>Abstain</strong> if the excerpts do not cover the claims, or <strong>Flag</strong> if the prompt itself is broken. Quarantined items will not skew calibration stats.</div>
        <div class="escape-row" style="margin-top:0; padding-top:0; border-top:none;">
          <button class="escape-btn" onclick="submitQuarantine('ABSTAIN_INSUFFICIENT_EVIDENCE')">Abstain: Insufficient Evidence</button>
          <button class="escape-btn" onclick="submitQuarantine('DEFECTIVE_PROMPT')">Flag: Defective Prompt</button>
        </div>
      </div>
      <div class="toast" id="toastBox"></div>
    </section>
  </main>
  <script>
    let STATE = { items: [], rubric: {}, atomic_checks: [], failure_tags: [], savedByCase: {}, quarantinedByCase: {}, idx: 0 };
    let DRAFT = { grades: {}, atomic: {}, tags: new Set() };
    const PILLARS = [["factual_faithfulness","F"],["completeness_and_relevance","C"],["cold_reader_clarity","R"],["actionability_and_proportion","A"]];

    async function loadState() {
      const res = await fetch("/api/state"); STATE = await res.json();
      const firstOpen = STATE.items.findIndex(it => !STATE.savedByCase[it.case_id] && !STATE.quarantinedByCase[it.case_id]);
      STATE.idx = firstOpen >= 0 ? firstOpen : 0; loadDraft(); renderNav(); renderItem();
    }
    function loadDraft() {
      const it = STATE.items[STATE.idx], ex = it ? STATE.savedByCase[it.case_id] : null;
      if (ex) {
        DRAFT = { grades: { ...ex.dimension_grades }, atomic: { ...(ex.atomic_checks || {}) }, tags: new Set(ex.failure_tags || []) };
        document.getElementById("notesInput").value = ex.critique_rationale || ex.notes || "";
      } else { DRAFT = { grades: {}, atomic: {}, tags: new Set() }; document.getElementById("notesInput").value = ""; }
    }
    function renderNav() {
      const nav = document.getElementById("pillNav"); nav.innerHTML = "";
      const done = STATE.items.filter(it => STATE.savedByCase[it.case_id]).length;
      const quar = STATE.items.filter(it => STATE.quarantinedByCase[it.case_id]).length;
      const ds = STATE.deduplication_stats || {};
      const maxOv = Math.round(Math.max(ds.max_observed_prompt_jaccard || 0, ds.max_observed_body_jaccard || 0) * 100);
      document.getElementById("subhead").textContent =
        `Partition: ${STATE.partition} | Graded: ${done}/${STATE.items.length} | Quarantined: ${quar} | Max overlap: ${maxOv}% | Seed: ${STATE.presentation_seed ?? "fixed"}`;
      STATE.items.forEach((it, i) => {
        const b = document.createElement("button");
        const isD = Boolean(STATE.savedByCase[it.case_id]), isQ = Boolean(STATE.quarantinedByCase[it.case_id]);
        b.className = "item-pill" + (i === STATE.idx ? " active" : "") + (isD ? " done" : (isQ ? " quarantined" : ""));
        b.textContent = (isD ? "✓ " : (isQ ? "⚑ " : "")) + `${i + 1}. ${it.topic_family}`;
        b.onclick = () => { STATE.idx = i; loadDraft(); hideToast(); renderNav(); renderItem(); };
        nav.appendChild(b);
      });
      const ban = document.getElementById("summaryBanner");
      if (done + quar === STATE.items.length && STATE.items.length > 0) {
        ban.style.display = "block";
        ban.innerHTML = `<strong>Completed ${done} gold label(s) and ${quar} quarantined item(s).</strong> Sealed store: <code>${STATE.store_path}</code>`;
      } else { ban.style.display = "none"; }
    }
    function renderItem() {
      const it = STATE.items[STATE.idx]; if (!it) return;
      document.getElementById("metaBar").innerHTML =
        `<span>Item <strong>${STATE.idx + 1} of ${STATE.items.length}</strong></span>` +
        `<span class="badge">${it.case_id}</span><span class="badge">${it.topic_family}</span>` +
        `<span class="badge">sha256: ${it.artifact_sha256.slice(0, 14)}...</span>`;
      document.getElementById("promptBox").textContent = it.prompt_text || "(No prompt)";
      document.getElementById("candidateBox").textContent = it.core_answer_text || it.blinded_text;
      const evList = document.getElementById("evidenceList"); evList.innerHTML = "";
      const excerpts = it.source_evidence_excerpts || [];
      if (excerpts.length === 0) {
        evList.innerHTML = `<div class="evidence-item">No source excerpts attached. Use <strong>Abstain: Insufficient Evidence</strong> if factual claims cannot be verified.</div>`;
      } else {
        excerpts.forEach(ev => {
          const d = document.createElement("div"); d.className = "evidence-item";
          d.innerHTML = `<div class="evidence-src">${ev.source}${ev.date ? " (" + ev.date + ")" : ""}</div><div></div>`;
          d.lastChild.textContent = ev.excerpt; evList.appendChild(d);
        });
      }
      const dr = document.getElementById("lineageDrawer");
      if (it.lineage_footer_text) { dr.style.display = "block"; dr.open = false; document.getElementById("lineageBox").textContent = it.lineage_footer_text; }
      else { dr.style.display = "none"; }
      const ag = document.getElementById("atomicGrid"); ag.innerHTML = "";
      (STATE.atomic_checks || []).forEach(c => {
        const val = DRAFT.atomic[c.id], row = document.createElement("div"); row.className = "atomic-chip";
        row.innerHTML = `<span>${c.label}</span><div class="atomic-toggle">` +
          `<button class="chip-btn ${val === true ? "yes" : ""}" onclick="setAtomic('${c.id}', true)">Pass</button>` +
          `<button class="chip-btn ${val === false ? "no" : ""}" onclick="setAtomic('${c.id}', false)">Fail</button></div>`;
        ag.appendChild(row);
      });
      const pc = document.getElementById("pillarsContainer"); pc.innerHTML = "";
      const dims = STATE.rubric.dimensions || {};
      PILLARS.forEach(([k, code]) => {
        const sp = dims[k] || { title: k, weight: 0.25, anchors: {} }, ch = DRAFT.grades[k] || null;
        const blk = document.createElement("div"); blk.className = "pillar-block";
        const btns = [1,2,3,4,5].map(s =>
          `<button class="score-btn ${ch === s ? "selected" : ""}" onmouseenter="previewAnchor('${k}',${s})" onmouseleave="restoreAnchor('${k}')" onclick="setScore('${k}', ${s})">${s}</button>`
        ).join("");
        const hint = ch ? `${ch}/5: ${sp.anchors[String(ch)] || ""}` : "Hover or click 1 (Severe Defect) to 5 (Exemplary) to read exact criteria";
        blk.innerHTML = `<div class="pillar-head"><span class="pillar-title">[${code}] ${sp.title}</span><span class="pillar-weight">${Math.round((sp.weight||0.25)*100)}%</span></div><div class="score-row">${btns}</div><div class="anchor-hint" id="hint_${k}">${hint}</div>`;
        pc.appendChild(blk);
      });
      const tr = document.getElementById("tagRow"); tr.innerHTML = "";
      (STATE.failure_tags || []).forEach(t => {
        const p = document.createElement("button");
        p.className = "tag-pill" + (DRAFT.tags.has(t.id) ? " active" : "");
        p.textContent = t.label;
        p.onclick = () => { DRAFT.tags.has(t.id) ? DRAFT.tags.delete(t.id) : DRAFT.tags.add(t.id); renderItem(); };
        tr.appendChild(p);
      });
      updateVerdictLocks();
    }
    function previewAnchor(k, s) { const sp = (STATE.rubric.dimensions || {})[k], el = document.getElementById("hint_" + k); if (sp && el) el.textContent = `${s}/5: ${sp.anchors[String(s)] || ""}`; }
    function restoreAnchor(k) { const sp = (STATE.rubric.dimensions || {})[k], el = document.getElementById("hint_" + k), ch = DRAFT.grades[k]; if (sp && el) el.textContent = ch ? `${ch}/5: ${sp.anchors[String(ch)] || ""}` : "Hover or click 1 (Severe Defect) to 5 (Exemplary) to read exact criteria"; }
    function setAtomic(id, val) { DRAFT.atomic[id] = val; renderItem(); }
    function setScore(k, s) { DRAFT.grades[k] = s; renderItem(); }
    function updateVerdictLocks() {
      const scoredCount = PILLARS.filter(([k]) => Number.isInteger(DRAFT.grades[k])).length;
      const prog = document.getElementById("pillarProgress"); if (prog) prog.textContent = `${scoredCount}/4 scored`;
      const complete = scoredCount === 4;
      const fOk = (DRAFT.grades.factual_faithfulness || 0) >= 4 && PILLARS.every(([k]) => (DRAFT.grades[k] || 0) >= 3);
      const critFail = DRAFT.atomic.unsupported_claim_absent === false || DRAFT.atomic.source_contradiction_absent === false;
      const noteLen = (document.getElementById("notesInput").value || "").trim().length;
      document.getElementById("btnPass").disabled = !(complete && fOk && !critFail);
      document.getElementById("btnFail").disabled = !(complete && (DRAFT.tags.size > 0 || noteLen >= 8));
      const hint = document.getElementById("ruleHint");
      if (!complete) hint.textContent = "Score all 4 pillars (F, C, R, A) to enable verdicts.";
      else if (critFail || !fOk) hint.textContent = "PASS locked by external_judge_rubric_v1 pass_rule (F >= 4, all pillars >= 3, passing faithfulness checks). Select a failure tag or critique (>= 8 chars) to Save as FAIL.";
      else hint.textContent = "Ready to save PASS, or select a failure tag / critique (>= 8 chars) to save FAIL.";
    }
    function showToast(msg, ok) { const t = document.getElementById("toastBox"); t.className = "toast " + (ok ? "ok" : "err"); t.textContent = msg; }
    function hideToast() { const t = document.getElementById("toastBox"); t.className = "toast"; t.textContent = ""; }
    function advanceNext() {
      const nxt = STATE.items.findIndex((it, i) => i > STATE.idx && !STATE.savedByCase[it.case_id] && !STATE.quarantinedByCase[it.case_id]);
      if (nxt >= 0) { STATE.idx = nxt; loadDraft(); }
      renderNav(); renderItem();
    }
    async function submitGrade(verdict) {
      const it = STATE.items[STATE.idx], note = (document.getElementById("notesInput").value || "").trim();
      const res = await fetch("/api/grade", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: it.case_id, judge_surface: it.judge_surface, topic_family: it.topic_family,
          partition: it.partition, artifact_sha256: it.artifact_sha256, blinded_text: it.blinded_text,
          evidence_context_sha256: it.evidence_context_sha256 || "", dimension_grades: DRAFT.grades,
          atomic_checks: DRAFT.atomic, failure_tags: Array.from(DRAFT.tags),
          critique_rationale: note, notes: note, human_verdict: verdict
        })
      });
      const data = await res.json();
      if (!res.ok || data.status !== "PASS") { showToast(data.error || "Save failed", false); return; }
      STATE.savedByCase[it.case_id] = data.record; delete STATE.quarantinedByCase[it.case_id];
      advanceNext(); showToast(`Saved ${it.case_id} (${verdict}).`, true);
    }
    async function submitQuarantine(reason) {
      const it = STATE.items[STATE.idx], note = (document.getElementById("notesInput").value || "").trim();
      const res = await fetch("/api/quarantine", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: it.case_id, judge_surface: it.judge_surface, topic_family: it.topic_family,
          partition: it.partition, artifact_sha256: it.artifact_sha256, reason: reason, notes: note
        })
      });
      const data = await res.json();
      if (!res.ok || data.status !== "PASS") { showToast(data.error || "Quarantine failed", false); return; }
      STATE.quarantinedByCase[it.case_id] = data.quarantined; delete STATE.savedByCase[it.case_id];
      advanceNext(); showToast(`Quarantined ${it.case_id} (${reason}).`, true);
    }
    loadState();
  </script>
</body>
</html>
"""

__all__ = ["STUDIO_HTML"]
