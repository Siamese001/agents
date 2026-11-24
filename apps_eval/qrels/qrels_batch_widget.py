"""Frontier 2026 Blind QRELS 10-Question Batch Widget Renderer (Sticky Question + 2x2 Passage Grid).

Pure domain HTML generator (zero `sqlite3` imports) implementing:
1. Pinned sticky question dock (`position: sticky; top: 0`) so the active question and punchy
   3-2-1-0 criteria strip stay locked in view while scanning or scrolling across Passages A, B, C, and D.
2. Side-by-side 2x2 passage boxes (`A`/`B` top row, `C`/`D` bottom row) directly underneath the
   pinned question, with a 1-click `2x2` / `1-Col` layout toggle saved in `localStorage`.
3. Clean deduplicated presentation of `[Claim]`, `[Outcomes]`, and `[Evidence]` blocks:
   strips synthetic `"Graph evidence supports "` prefixes, drops internal AST evidence stubs,
   collapses verbatim duplicates, highlights quantitative metrics, and maps surface names to plain English.
4. Content-addressed cache hardening:
   - `compute_batch_fingerprint()` hashes the exact blinded question and slot payload (`8`-hex SHA-256),
     scoping `STORAGE_KEY` (`agents_qrels_b<N>_<fp8>`) and prefixing copied replies with `BATCH<N>#<fp8>`.
   - `build_batch_artifact_filename()` appends both `data_fp8` and rendered HTML `ui_fp4` so every
     data rebuild or UI layout revision receives a guaranteed-unique immutable artifact filename.
   - `audit_rendered_batch_html()` fails closed on any blind-field leak, AST-stub leak, or missing
     sticky-question / fingerprint contract before returning HTML.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from apps_eval.qrels.qrels_rubric_contract import strip_blind_forbidden_fields

DEFAULT_FONT_SIZE_PX = 17
FONT_SIZE_STEPS_PX: tuple[int, ...] = (15, 17, 19, 22)
WIDGET_LAYOUT_VERSION = "sticky_grid2x2_v1"

SURFACE_DISPLAY_LABELS: dict[str, str] = {
    "resume_graph_engine": "Resume Evidence",
    "outreach_engine": "Executive Outreach",
    "apps_research": "Research Retrieval",
    "candidate_graph": "Candidate Graph",
}

FAILURE_TAXONOMY_PILLS: tuple[str, ...] = (
    "Missing Scope",
    "Missing Proof",
    "Generic Stub",
    "Wrong Employer",
    "Keyword Trap",
    "Out-of-Scope Query",
)

FORBIDDEN_BLIND_HTML_TOKENS: tuple[str, ...] = (
    "fused_rank",
    "dense_rank",
    "sparse_rank",
    "colbert_rank",
    "bm25_rank",
    "target_record_id",
    "ground_truth_summary",
    '"answerable"',
    "tier1_paraphrase",
    "tier2_cross_domain",
    "tier3_hard_negative",
    "tier4_near_domain_unanswerable",
)

FORBIDDEN_AST_STUB_TOKENS: tuple[str, ...] = (
    "Domain architecture concept:",
    "Production implementation evidence:",
)

_SECTION_SPLIT_RE = re.compile(
    r"\s*\|\s*(?=\[(?:Claim|Outcomes|Evidence|Capabilities|Unit|Confidence|Domain)\])",
    re.IGNORECASE,
)
_EMPLOYER_PREFIX_RE = re.compile(r"^\[([^\]]{2,40})\]\s*(.*)$")
_SYNTHETIC_LEAD_RE = re.compile(
    r"^(?:(?:InsurTech|EY|IBM|Slalom|Unify)\s+)?graph\s+evidence\s+supports\s+",
    re.IGNORECASE,
)
_INTERNAL_AST_STUB_RE = re.compile(
    r"^(?:Domain architecture concept|Production implementation evidence):",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


def _clean_synthetic_prefix(text: str) -> str:
    cleaned = _SYNTHETIC_LEAD_RE.sub("", str(text or "").strip()).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _norm_tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "").casefold()))


def _is_verbatim_duplicate(text_a: str, text_b: str, threshold: float = 0.82) -> bool:
    ta, tb = _norm_tokens(text_a), _norm_tokens(text_b)
    if min(len(ta), len(tb)) < 5:
        return False
    return (len(ta & tb) / max(len(ta), len(tb))) >= threshold


def parse_structured_core_statement(core_statement: str) -> dict[str, Any]:
    """Parse raw pipe-delimited core text into clean, deduplicated Claim, Outcomes, and Evidence blocks."""
    raw = str(core_statement or "").strip()
    if not raw:
        return {"claim": "", "outcomes": [], "evidence": []}

    claim_parts: list[str] = []
    outcomes: list[str] = []
    evidence: list[dict[str, str]] = []

    segments = _SECTION_SPLIT_RE.split(raw)
    matched_any_tag = False
    for seg in segments:
        piece = seg.strip()
        if not piece:
            continue
        low = piece.lower()
        if low.startswith("[claim]"):
            matched_any_tag = True
            body = _clean_synthetic_prefix(piece[len("[claim]") :].strip(" :-|"))
            if body:
                claim_parts.append(body)
        elif low.startswith("[outcomes]"):
            matched_any_tag = True
            body = piece[len("[outcomes]") :].strip(" :-|")
            for item in body.split(";"):
                clean = _clean_synthetic_prefix(item.strip().rstrip("."))
                if clean:
                    outcomes.append(clean)
        elif low.startswith("[evidence]"):
            matched_any_tag = True
            body = piece[len("[evidence]") :].strip(" :-|")
            for item in body.split(";"):
                clean = item.strip()
                if not clean:
                    continue
                m = _EMPLOYER_PREFIX_RE.match(clean)
                if m:
                    evidence.append({"employer": m.group(1).strip(), "text": m.group(2).strip()})
                else:
                    evidence.append({"employer": "", "text": clean})
        else:
            if not matched_any_tag:
                claim_parts.append(_clean_synthetic_prefix(piece))

    if not matched_any_tag:
        return {"claim": _clean_synthetic_prefix(raw), "outcomes": [], "evidence": []}

    claim_text = " ".join(claim_parts).strip() or _clean_synthetic_prefix(raw)
    deduped_outcomes = [o for o in outcomes if not _is_verbatim_duplicate(o, claim_text)]
    deduped_evidence: list[dict[str, str]] = []
    for ev in evidence:
        ev_text = ev["text"]
        if not ev_text or _INTERNAL_AST_STUB_RE.match(ev_text):
            continue
        if _is_verbatim_duplicate(ev_text, claim_text):
            continue
        if any(_is_verbatim_duplicate(ev_text, prev["text"]) for prev in deduped_evidence):
            continue
        deduped_evidence.append(ev)

    return {
        "claim": claim_text,
        "outcomes": deduped_outcomes,
        "evidence": deduped_evidence,
    }


def build_blind_batch_payload(batch_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw queue entries into strictly blinded structured JSON safe for client rendering.

    Explicitly whitelists only blind-safe presentation fields. Never exposes ranks, scores,
    record_id, target_record_id, ground_truth_summary, tier, or answerable flags.
    """
    payload: list[dict[str, Any]] = []
    for q in batch_items:
        blind_cands: list[dict[str, Any]] = []
        for cand in q.get("candidates") or []:
            sanitized = strip_blind_forbidden_fields(cand)
            structured = parse_structured_core_statement(str(sanitized.get("core_statement") or ""))
            blind_cands.append(
                {
                    "slot": str(sanitized.get("slot") or ""),
                    "claim": structured["claim"],
                    "outcomes": structured["outcomes"],
                    "evidence": structured["evidence"],
                    "boilerplate_footer": str(sanitized.get("boilerplate_footer") or ""),
                }
            )
        raw_surface = str(q.get("surface") or "resume_graph_engine")
        payload.append(
            {
                "qrel_id": str(q.get("qrel_id") or ""),
                "query_text": str(q.get("query_text") or ""),
                "surface_label": SURFACE_DISPLAY_LABELS.get(raw_surface, "Candidate Evidence"),
                "candidates": blind_cands,
            }
        )
    return payload


def compute_batch_fingerprint(
    batch_items: Sequence[Mapping[str, Any]],
    *,
    batch_index: int,
) -> str:
    """Compute a deterministic 8-hex SHA-256 fingerprint over the exact blinded batch content."""
    blind_questions = build_blind_batch_payload(batch_items)
    canonical = json.dumps(
        {"batch_index": int(batch_index), "questions": blind_questions},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def audit_rendered_batch_html(
    html: str,
    *,
    batch_index: int,
    expected_fingerprint: str,
) -> None:
    """Fail-closed static audit verifying blind safety, sticky layout, and fingerprint binding."""
    text = str(html or "")
    expected_attr = f'data-batch-fingerprint="{expected_fingerprint}"'
    expected_storage = f"agents_qrels_b{int(batch_index)}_{expected_fingerprint}"
    expected_reply = f"BATCH{int(batch_index)}#{expected_fingerprint}"
    if expected_attr not in text:
        raise ValueError(f"QRELS HTML audit failed: missing '{expected_attr}'.")
    if expected_storage not in text:
        raise ValueError(f"QRELS HTML audit failed: missing content-scoped STORAGE_KEY '{expected_storage}'.")
    if expected_reply not in text:
        raise ValueError(f"QRELS HTML audit failed: missing copy-back prefix '{expected_reply}'.")
    if "position: sticky" not in text and "sticky top-0" not in text:
        raise ValueError("QRELS HTML audit failed: missing pinned sticky question dock.")
    for forbidden in FORBIDDEN_BLIND_HTML_TOKENS:
        if forbidden in text:
            raise ValueError(f"QRELS HTML audit failed: blind leakage token detected ({forbidden}).")
    for stub in FORBIDDEN_AST_STUB_TOKENS:
        if stub in text:
            raise ValueError(f"QRELS HTML audit failed: raw internal AST stub leaked ({stub}).")


def build_batch_artifact_filename(
    batch_items: Sequence[Mapping[str, Any]],
    *,
    batch_index: int,
    total_batches: int = 5,
    corpus_digest: str = "",
) -> str:
    """Return an immutable content-addressed filename combining data fingerprint and rendered UI hash."""
    data_fp = compute_batch_fingerprint(batch_items, batch_index=batch_index)
    html = render_blind_batch_widget_html(
        batch_items,
        batch_index=batch_index,
        total_batches=total_batches,
        corpus_digest=corpus_digest,
    )
    ui_fp = hashlib.sha256(html.encode("utf-8")).hexdigest()[:4]
    return f"qrels_batch_{int(batch_index)}_of_{int(total_batches)}_{data_fp}_{ui_fp}.html"


def render_blind_batch_widget_html(
    batch_items: Sequence[Mapping[str, Any]],
    *,
    batch_index: int,
    total_batches: int = 5,
    corpus_digest: str = "",
) -> str:
    """Render self-contained Frontier 2026 HTML with pinned sticky question dock and 2x2 passage boxes."""
    _ = corpus_digest
    blind_questions = build_blind_batch_payload(batch_items)
    q_count = len(blind_questions)
    start_num = ((batch_index - 1) * 10) + 1
    end_num = start_num + q_count - 1
    total_passages = sum(len(q["candidates"]) for q in blind_questions)
    batch_fp = compute_batch_fingerprint(batch_items, batch_index=batch_index)
    storage_key = f"agents_qrels_b{int(batch_index)}_{batch_fp}"
    reply_prefix = f"BATCH{int(batch_index)}#{batch_fp}"
    questions_json = json.dumps(blind_questions, ensure_ascii=False).replace("</", "<\\/")
    tags_json = json.dumps(list(FAILURE_TAXONOMY_PILLS), ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    #qrelsRoot {{ --fs: {DEFAULT_FONT_SIZE_PX}px; font-size: var(--fs); }}
    .q-sticky-dock {{
      position: sticky;
      top: 0;
      z-index: 30;
      background-color: var(--background);
    }}
    .q-title {{ font-size: calc(var(--fs) + 3px); line-height: 1.3; }}
    .q-claim {{ font-size: var(--fs); line-height: 1.5; font-weight: 700; }}
    .q-outcome {{ font-size: calc(var(--fs) - 1px); line-height: 1.45; font-weight: 600; }}
    .q-evidence {{ font-size: calc(var(--fs) - 2px); line-height: 1.45; }}
    .q-metric {{ font-weight: 800; text-decoration: underline; text-decoration-color: var(--primary); text-underline-offset: 2px; }}
    .q-grid-2x2 {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.75rem; align-items: stretch; }}
    @media (min-width: 560px) {{
      .q-grid-2x2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    .q-grid-1col {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.75rem; }}
    .q-scroll-dock {{ max-height: 580px; overflow-y: auto; padding: 2px 4px 6px 2px; }}
  </style>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-0 m-0">
  <div id="qrelsRoot" data-batch-fingerprint="{batch_fp}" data-layout-version="{WIDGET_LAYOUT_VERSION}" class="pb-4 space-y-3">
    <div id="stickyHeader" class="q-sticky-dock pt-2 pb-2.5 space-y-2 border-b-2 border-[var(--primary)] shadow-md">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm font-extrabold text-[var(--foreground)]">Batch {batch_index}/{total_batches}</span>
          <span class="px-1.5 py-0.5 rounded border border-[var(--card-border)] bg-[var(--card)] font-mono text-xs text-[var(--muted-foreground)]">Build #{batch_fp}</span>
          <div id="pillRow" class="flex flex-wrap gap-1"></div>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <div class="inline-flex items-center rounded-lg border border-[var(--card-border)] bg-[var(--card)] overflow-hidden text-xs font-bold" aria-label="Passage box layout">
            <button id="btnLayoutGrid" type="button" title="Show 4 passages in 2x2 boxes" class="px-2 py-1">2x2</button>
            <button id="btnLayoutStack" type="button" title="Show passages in 1 column" class="px-2 py-1 border-l border-[var(--card-border)]">1-Col</button>
          </div>
          <div class="inline-flex items-center rounded-lg border border-[var(--card-border)] bg-[var(--card)] overflow-hidden text-xs font-semibold" aria-label="Font size controls">
            <button id="btnFontDown" type="button" title="Decrease font size" class="px-2 py-1 hover:bg-[var(--secondary)] text-[var(--foreground)]">A-</button>
            <span id="fontReadout" class="px-1.5 py-1 border-x border-[var(--card-border)] font-mono text-xs text-[var(--muted-foreground)] tabular-nums">{DEFAULT_FONT_SIZE_PX}px</span>
            <button id="btnFontUp" type="button" title="Increase font size" class="px-2 py-1 hover:bg-[var(--secondary)] text-[var(--foreground)]">A+</button>
          </div>
          <button id="btnRubricToggle" type="button" class="px-2 py-1 rounded-lg border border-[var(--card-border)] bg-[var(--card)] text-xs font-semibold text-[var(--foreground)] hover:border-[var(--primary)]">Rubric</button>
          <span id="progressBadge" class="px-2.5 py-1 rounded-full border border-[var(--card-border)] bg-[var(--card)] font-mono text-xs font-bold tabular-nums text-[var(--foreground)]">0/{q_count}</span>
          <button id="btnPrev" type="button" class="px-2.5 py-1 rounded-lg border border-[var(--card-border)] bg-[var(--card)] text-xs font-bold text-[var(--foreground)] disabled:opacity-40">Prev</button>
          <button id="btnNext" type="button" class="px-2.5 py-1 rounded-lg border border-[var(--card-border)] bg-[var(--card)] text-xs font-bold text-[var(--foreground)] disabled:opacity-40">Next</button>
          <button id="btnReset" type="button" class="px-2 py-1 rounded-lg border border-[var(--card-border)] text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]">Reset</button>
        </div>
      </div>

      <div class="p-3 rounded-xl bg-[var(--card)] border border-[var(--card-border)] border-l-4 border-l-[var(--primary)]">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-0.5">
          <div id="qMeta" class="text-xs uppercase tracking-wider font-extrabold text-[var(--muted-foreground)]"></div>
          <div id="qSlotCounter" class="text-xs font-mono font-bold text-[var(--primary)]"></div>
        </div>
        <div id="qText" class="q-title font-extrabold text-[var(--foreground)]"></div>
      </div>

      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted-foreground)] px-0.5">
        <span><strong class="text-[var(--success)]">3 Direct Hit</strong> exact proof</span>
        <span><strong class="text-[var(--primary)]">2 Partial</strong> misses a piece</span>
        <span><strong class="text-[var(--warning)]">1 Background</strong> org/theme only</span>
        <span><strong class="text-[var(--error)]">0 Off-Topic</strong> wrong org/trap/OOS</span>
        <span><strong class="text-[var(--foreground)]">? Flag</strong> ungradable</span>
        <span class="ml-auto font-medium">0, 1, or multiple 3s allowed · Keys <kbd class="px-1 rounded border border-[var(--card-border)] font-mono">3</kbd><kbd class="px-1 rounded border border-[var(--card-border)] font-mono">2</kbd><kbd class="px-1 rounded border border-[var(--card-border)] font-mono">1</kbd><kbd class="px-1 rounded border border-[var(--card-border)] font-mono">0</kbd><kbd class="px-1 rounded border border-[var(--card-border)] font-mono">?</kbd></span>
      </div>

      <div id="rubricDrawer" class="hidden grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 text-xs pt-1">
        <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--card-border)] border-t-4 border-t-[var(--success)]">
          <div class="font-extrabold text-[var(--foreground)]"><span class="text-[var(--success)]">3</span> Direct Hit</div>
          <div class="text-[var(--muted-foreground)] mt-0.5 leading-snug">Directly answers the exact question with concrete, attributable proof. Safe to cite as primary evidence.</div>
        </div>
        <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--card-border)] border-t-4 border-t-[var(--primary)]">
          <div class="font-extrabold text-[var(--foreground)]"><span class="text-[var(--primary)]">2</span> Partial Support</div>
          <div class="text-[var(--muted-foreground)] mt-0.5 leading-snug">Right work with useful supporting proof, but misses a required condition, mechanism, or scope piece.</div>
        </div>
        <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--card-border)] border-t-4 border-t-[var(--warning)]">
          <div class="font-extrabold text-[var(--foreground)]"><span class="text-[var(--warning)]">1</span> Background Only</div>
          <div class="text-[var(--muted-foreground)] mt-0.5 leading-snug">Same employer or broad theme context, without answering the specific question asked.</div>
        </div>
        <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--card-border)] border-t-4 border-t-[var(--error)]">
          <div class="font-extrabold text-[var(--foreground)]"><span class="text-[var(--error)]">0</span> Off-Topic / Confounder</div>
          <div class="text-[var(--muted-foreground)] mt-0.5 leading-snug">Wrong employer, wrong system, keyword trap, or ungrounded for an out-of-scope query. Use <strong>?</strong> if ungradable.</div>
        </div>
      </div>
    </div>

    <div id="passagesBox" class="q-grid-2x2 q-scroll-dock"></div>

    <div id="doneCard" class="hidden p-4 rounded-xl bg-[var(--card)] border-2 border-[var(--success)] space-y-2.5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="font-bold text-lg text-[var(--foreground)]">Batch {batch_index} Complete ({total_passages}/{total_passages} passages graded · Q{start_num} to Q{end_num})</div>
        <button id="btnCopy" type="button" class="px-4 py-2 rounded-lg text-sm font-bold bg-[var(--primary)] text-[var(--primary-foreground)]">Copy Batch {batch_index} Grades</button>
      </div>
      <div class="text-sm text-[var(--muted-foreground)]">Paste the copied line into chat to record Batch {batch_index} (Build #{batch_fp}) and advance.</div>
      <textarea id="replyOutput" readonly rows="3" class="w-full p-2.5 rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-[var(--foreground)] font-mono text-sm"></textarea>
      <div id="copyStatus" class="text-sm font-semibold text-[var(--success)] hidden">Copied to clipboard. Paste into chat now.</div>
    </div>
  </div>

  <script>
    const STORAGE_KEY = {json.dumps(storage_key)};
    const REPLY_PREFIX = {json.dumps(reply_prefix)};
    const FONT_KEY = "agents_qrels_font_size_v1";
    const LAYOUT_KEY = "agents_qrels_layout_mode_v1";
    const FONT_STEPS = {json.dumps(list(FONT_SIZE_STEPS_PX))};
    const FAILURE_TAGS = {tags_json};
    const QUESTIONS = {questions_json};
    const SLOTS = ["A", "B", "C", "D"];
    const GRADE_TITLES = {{
      3: "Grade 3 (Direct Hit): answers exact question with concrete proof",
      2: "Grade 2 (Partial Support): right work, misses a key detail",
      1: "Grade 1 (Background Only): same employer/theme, does not answer",
      0: "Grade 0 (Off-Topic / Confounder): wrong employer, keyword trap, or out-of-scope",
      Q: "Quarantine / Flag: ambiguous or ungradable item (excluded from scored denominator)"
    }};
    const METRIC_RE = /(\\$\\d+(?:\\.\\d+)?[MBK]?\\+?|\\b\\d+(?:\\.\\d+)?%\\b|\\b\\d+(?:,\\d{{3}})+\\+?\\b|\\bsub-\\d+ms\\b)/g;

    function loadFontSize() {{
      try {{
        const saved = Number(localStorage.getItem(FONT_KEY));
        if (FONT_STEPS.includes(saved)) return saved;
      }} catch (_) {{}}
      return {DEFAULT_FONT_SIZE_PX};
    }}

    function loadLayoutMode() {{
      try {{
        const saved = localStorage.getItem(LAYOUT_KEY);
        if (saved === "grid" || saved === "stack") return saved;
      }} catch (_) {{}}
      return "grid";
    }}

    let currentFontPx = loadFontSize();
    let currentLayout = loadLayoutMode();

    function applyFontSize(px) {{
      currentFontPx = px;
      document.getElementById("qrelsRoot").style.setProperty("--fs", px + "px");
      document.getElementById("fontReadout").textContent = px + "px";
      try {{ localStorage.setItem(FONT_KEY, String(px)); }} catch (_) {{}}
    }}

    function applyLayoutMode(mode) {{
      currentLayout = mode;
      const box = document.getElementById("passagesBox");
      box.className = (mode === "stack" ? "q-grid-1col" : "q-grid-2x2") + " q-scroll-dock";
      const btnG = document.getElementById("btnLayoutGrid");
      const btnS = document.getElementById("btnLayoutStack");
      btnG.className = "px-2 py-1 " + (mode === "grid" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]");
      btnS.className = "px-2 py-1 border-l border-[var(--card-border)] " + (mode === "stack" ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]");
      try {{ localStorage.setItem(LAYOUT_KEY, mode); }} catch (_) {{}}
    }}

    function loadPersisted() {{
      try {{
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {{
          const obj = JSON.parse(raw);
          if (obj && typeof obj === "object" && obj.grades && typeof obj.curIdx === "number") {{
            return {{
              curIdx: Math.max(0, Math.min(QUESTIONS.length - 1, obj.curIdx)),
              activeSlot: SLOTS.includes(obj.activeSlot) ? obj.activeSlot : "A",
              grades: obj.grades,
              tags: obj.tags && typeof obj.tags === "object" ? obj.tags : {{}}
            }};
          }}
        }}
      }} catch (_) {{}}
      return {{ curIdx: 0, activeSlot: "A", grades: {{}}, tags: {{}} }};
    }}

    let STATE = loadPersisted();

    function savePersisted() {{
      try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(STATE)); }} catch (_) {{}}
    }}

    function isScoredValue(v) {{
      return typeof v === "number" || v === "Q";
    }}

    function isQuestionDone(qrelId) {{
      const g = STATE.grades[qrelId] || {{}};
      return SLOTS.every(s => isScoredValue(g[s]));
    }}

    function countDone() {{
      return QUESTIONS.filter(q => isQuestionDone(q.qrel_id)).length;
    }}

    function getSlotTags(qrelId, slot) {{
      const raw = (STATE.tags[qrelId] || {{}})[slot];
      if (Array.isArray(raw)) return raw;
      if (typeof raw === "string" && raw) return [raw];
      return [];
    }}

    function buildReplyLine() {{
      const body = QUESTIONS.map((q, idx) => {{
        const g = STATE.grades[q.qrel_id] || {{}};
        const base = `Q${{idx + 1}}: A=${{g.A}},B=${{g.B}},C=${{g.C}},D=${{g.D}}`;
        const tagParts = SLOTS
          .filter(s => typeof g[s] === "number" && g[s] < 3 && getSlotTags(q.qrel_id, s).length > 0)
          .map(s => `${{s}}:${{getSlotTags(q.qrel_id, s).join("+")}}`);
        return tagParts.length > 0 ? `${{base}} [${{tagParts.join(";")}}]` : base;
      }}).join(" | ");
      return `${{REPLY_PREFIX}} | ${{body}}`;
    }}

    function appendHighlightedText(container, text) {{
      const parts = String(text || "").split(METRIC_RE);
      parts.forEach((part, idx) => {{
        if (!part) return;
        if (idx % 2 === 1) {{
          const strong = document.createElement("span");
          strong.className = "q-metric";
          strong.textContent = part;
          container.appendChild(strong);
        }} else {{
          container.appendChild(document.createTextNode(part));
        }}
      }});
    }}

    function scrollTopSmooth() {{
      const box = document.getElementById("passagesBox");
      if (box) box.scrollTop = 0;
      try {{ window.scrollTo({{ top: 0, behavior: "smooth" }}); }} catch (_) {{ window.scrollTo(0, 0); }}
    }}

    function jumpToQuestion(idx) {{
      STATE.curIdx = idx;
      const q = QUESTIONS[idx];
      const g = (q && STATE.grades[q.qrel_id]) || {{}};
      STATE.activeSlot = SLOTS.find(s => !isScoredValue(g[s])) || "A";
      savePersisted();
      render();
      scrollTopSmooth();
    }}

    function selectGrade(qrelId, slot, grade) {{
      const wasDone = isQuestionDone(qrelId);
      if (!STATE.grades[qrelId]) STATE.grades[qrelId] = {{}};
      STATE.grades[qrelId][slot] = grade;
      if (!(typeof grade === "number" && grade < 3) && STATE.tags[qrelId]) {{
        delete STATE.tags[qrelId][slot];
      }}
      const nowDone = isQuestionDone(qrelId);
      let advancedQuestion = false;
      if (!wasDone && nowDone && (grade === 3 || grade === "Q")) {{
        const nextOpen = QUESTIONS.findIndex((q, i) => i > STATE.curIdx && !isQuestionDone(q.qrel_id));
        if (nextOpen >= 0) {{
          STATE.curIdx = nextOpen;
          STATE.activeSlot = "A";
          advancedQuestion = true;
        }} else {{
          const anyOpen = QUESTIONS.findIndex(q => !isQuestionDone(q.qrel_id));
          if (anyOpen >= 0) {{
            STATE.curIdx = anyOpen;
            STATE.activeSlot = "A";
            advancedQuestion = true;
          }}
        }}
      }} else {{
        const g = STATE.grades[qrelId];
        const nextSlot = SLOTS.find(s => !isScoredValue(g[s]));
        STATE.activeSlot = nextSlot || slot;
      }}
      savePersisted();
      render();
      if (advancedQuestion) scrollTopSmooth();
    }}

    function toggleTag(qrelId, slot, tagLabel) {{
      if (!STATE.tags[qrelId]) STATE.tags[qrelId] = {{}};
      const curList = getSlotTags(qrelId, slot).slice();
      const idx = curList.indexOf(tagLabel);
      if (idx >= 0) {{
        curList.splice(idx, 1);
      }} else {{
        curList.push(tagLabel);
      }}
      if (curList.length === 0) {{
        delete STATE.tags[qrelId][slot];
      }} else {{
        STATE.tags[qrelId][slot] = curList;
      }}
      savePersisted();
      render();
    }}

    function gradeBtnSelectedStyle(score) {{
      if (score === 3) return "border-[var(--success)] bg-[var(--success)] text-white";
      if (score === 2) return "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]";
      if (score === 1) return "border-[var(--warning)] bg-[var(--warning)] text-white";
      if (score === 0) return "border-[var(--error)] bg-[var(--error)] text-white";
      return "border-[var(--muted-foreground)] bg-[var(--muted-foreground)] text-white";
    }}

    function gradeCardAccentBorder(score) {{
      if (score === 3) return "border-t-[var(--success)]";
      if (score === 2) return "border-t-[var(--primary)]";
      if (score === 1) return "border-t-[var(--warning)]";
      if (score === 0) return "border-t-[var(--error)]";
      if (score === "Q") return "border-t-[var(--muted-foreground)]";
      return "border-t-[var(--card-border)]";
    }}

    function render() {{
      const done = countDone();
      document.getElementById("progressBadge").textContent = `${{done}}/${{QUESTIONS.length}}`;

      const pillRow = document.getElementById("pillRow");
      pillRow.innerHTML = "";
      QUESTIONS.forEach((q, idx) => {{
        const qDone = isQuestionDone(q.qrel_id);
        const active = idx === STATE.curIdx;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "px-2 py-0.5 rounded-full border text-xs font-bold transition-colors " + (
          active
            ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
            : qDone
              ? "border-[var(--success)] text-[var(--success)] bg-[var(--card)]"
              : "border-[var(--card-border)] text-[var(--muted-foreground)] bg-[var(--card)] hover:text-[var(--foreground)]"
        );
        btn.textContent = (qDone ? "✓ " : "") + `Q${{idx + 1}}`;
        btn.onclick = () => jumpToQuestion(idx);
        pillRow.appendChild(btn);
      }});

      const q = QUESTIONS[STATE.curIdx];
      const qGrades = STATE.grades[q.qrel_id] || {{}};
      const gradedSlots = SLOTS.filter(s => isScoredValue(qGrades[s])).length;

      document.getElementById("qMeta").textContent = `Question ${{STATE.curIdx + 1}} of ${{QUESTIONS.length}} · ${{q.surface_label}}`;
      document.getElementById("qSlotCounter").textContent = gradedSlots === 4
        ? "4/4 graded · Click Next (or press →)"
        : `${{gradedSlots}}/4 passages graded`;
      document.getElementById("qText").textContent = q.query_text;
      document.getElementById("btnPrev").disabled = STATE.curIdx === 0;
      const btnNext = document.getElementById("btnNext");
      btnNext.disabled = STATE.curIdx === QUESTIONS.length - 1;
      btnNext.className = "px-2.5 py-1 rounded-lg border text-xs font-bold disabled:opacity-40 " + (
        gradedSlots === 4 && STATE.curIdx < QUESTIONS.length - 1
          ? "border-[var(--success)] bg-[var(--success)] text-white"
          : "border-[var(--card-border)] bg-[var(--card)] text-[var(--foreground)]"
      );

      const box = document.getElementById("passagesBox");
      box.innerHTML = "";

      q.candidates.forEach(c => {{
        const cur = qGrades[c.slot];
        const isGraded = isScoredValue(cur);
        const isFocused = STATE.activeSlot === c.slot;
        const card = document.createElement("div");
        card.className = "p-3.5 rounded-xl border border-t-4 bg-[var(--card)] flex flex-col gap-2.5 shadow-sm transition-colors " +
          gradeCardAccentBorder(cur) + " " +
          (isFocused ? "border-[var(--primary)] ring-1 ring-[var(--primary)]" : "border-[var(--card-border)]");
        card.onclick = () => {{ if (STATE.activeSlot !== c.slot) {{ STATE.activeSlot = c.slot; savePersisted(); render(); }} }};

        const head = document.createElement("div");
        head.className = "flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[var(--card-border)]";

        const labelWrap = document.createElement("div");
        labelWrap.className = "flex items-center gap-1.5";
        const label = document.createElement("span");
        label.className = "px-2 py-0.5 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)] text-sm font-extrabold";
        label.textContent = `Passage ${{c.slot}}`;
        labelWrap.appendChild(label);
        if (isGraded) {{
          const chip = document.createElement("span");
          chip.className = cur === "Q"
            ? "px-2 py-0.5 rounded-full border border-[var(--warning)] text-xs font-bold text-[var(--warning)]"
            : "px-2 py-0.5 rounded-full border border-[var(--success)] text-xs font-bold text-[var(--success)]";
          chip.textContent = cur === "Q" ? "Flagged" : `Grade ${{cur}}`;
          labelWrap.appendChild(chip);
        }}
        head.appendChild(labelWrap);

        const btnGroup = document.createElement("div");
        btnGroup.className = "flex gap-1";
        [3, 2, 1, 0, "Q"].forEach(score => {{
          const b = document.createElement("button");
          b.type = "button";
          b.title = GRADE_TITLES[score];
          const selected = cur === score;
          b.className = "min-w-[36px] h-[34px] px-2.5 rounded-lg border-2 font-extrabold text-sm transition-colors " + (
            selected
              ? gradeBtnSelectedStyle(score)
              : "border-[var(--card-border)] bg-[var(--background)] text-[var(--foreground)] hover:border-[var(--primary)]"
          );
          b.textContent = score === "Q" ? "?" : String(score);
          b.onclick = (e) => {{ e.stopPropagation(); selectGrade(q.qrel_id, c.slot, score); }};
          btnGroup.appendChild(b);
        }});
        head.appendChild(btnGroup);
        card.appendChild(head);

        if (typeof cur === "number" && cur < 3) {{
          const activeTags = getSlotTags(q.qrel_id, c.slot);
          const tagBar = document.createElement("div");
          tagBar.className = "flex flex-wrap items-center gap-1 pt-0.5";
          const tagLbl = document.createElement("span");
          tagLbl.className = "text-xs font-bold text-[var(--muted-foreground)] mr-0.5";
          tagLbl.textContent = "Why < 3:";
          tagBar.appendChild(tagLbl);
          FAILURE_TAGS.forEach(tl => {{
            const tb = document.createElement("button");
            tb.type = "button";
            const activeTag = activeTags.includes(tl);
            const activeCls = cur === 2
              ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
              : cur === 1
                ? "border-[var(--warning)] bg-[var(--warning)] text-white"
                : "border-[var(--error)] bg-[var(--error)] text-white";
            tb.className = "px-2 py-0.5 rounded-full border text-xs font-semibold transition-colors " + (
              activeTag
                ? activeCls
                : "border-[var(--card-border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--primary)]"
            );
            tb.textContent = (activeTag ? "✓ " : "") + tl;
            tb.onclick = (e) => {{ e.stopPropagation(); toggleTag(q.qrel_id, c.slot, tl); }};
            tagBar.appendChild(tb);
          }});
          card.appendChild(tagBar);
        }}

        const claimBlock = document.createElement("div");
        claimBlock.className = "space-y-1";
        const claimTag = document.createElement("span");
        claimTag.className = "inline-block px-1.5 py-0.5 rounded bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs font-extrabold uppercase tracking-wider";
        claimTag.textContent = "Claim";
        claimBlock.appendChild(claimTag);
        const claimBody = document.createElement("div");
        claimBody.className = "q-claim text-[var(--foreground)]";
        appendHighlightedText(claimBody, c.claim || "");
        claimBlock.appendChild(claimBody);
        card.appendChild(claimBlock);

        if (Array.isArray(c.outcomes) && c.outcomes.length > 0) {{
          const outBlock = document.createElement("div");
          outBlock.className = "pt-2 border-t border-[var(--card-border)] space-y-1";
          const outTag = document.createElement("span");
          outTag.className = "inline-block px-1.5 py-0.5 rounded bg-[var(--secondary)] text-[var(--secondary-foreground)] text-xs font-extrabold uppercase tracking-wider";
          outTag.textContent = "Outcomes";
          outBlock.appendChild(outTag);
          const ul = document.createElement("ul");
          ul.className = "list-disc pl-4 space-y-1";
          c.outcomes.forEach(item => {{
            const li = document.createElement("li");
            li.className = "q-outcome text-[var(--foreground)]";
            appendHighlightedText(li, item);
            ul.appendChild(li);
          }});
          outBlock.appendChild(ul);
          card.appendChild(outBlock);
        }}

        if (Array.isArray(c.evidence) && c.evidence.length > 0) {{
          const evBlock = document.createElement("div");
          evBlock.className = "pt-2 border-t border-[var(--card-border)] space-y-1";
          const evTag = document.createElement("div");
          evTag.className = "text-xs font-bold uppercase tracking-wider text-[var(--muted-foreground)]";
          evTag.textContent = "Evidence";
          evBlock.appendChild(evTag);
          const evList = document.createElement("div");
          evList.className = "space-y-1.5";
          c.evidence.forEach(ev => {{
            const row = document.createElement("div");
            row.className = "q-evidence text-[var(--muted-foreground)]";
            if (ev.employer) {{
              const badge = document.createElement("span");
              badge.className = "inline-block mr-1.5 px-1.5 py-0.5 rounded border border-[var(--card-border)] bg-[var(--background)] text-[var(--foreground)] text-xs font-bold";
              badge.textContent = ev.employer;
              row.appendChild(badge);
            }}
            appendHighlightedText(row, ev.text || "");
            evList.appendChild(row);
          }});
          evBlock.appendChild(evList);
          card.appendChild(evBlock);
        }}

        if (c.boilerplate_footer) {{
          const det = document.createElement("details");
          det.className = "mt-auto pt-1.5 border-t border-[var(--card-border)] text-xs text-[var(--muted-foreground)]";
          const sum = document.createElement("summary");
          sum.className = "cursor-pointer select-none font-medium";
          sum.textContent = "Reference only (do not grade)";
          const pre = document.createElement("div");
          pre.className = "mt-1 font-mono text-xs opacity-80 break-words";
          pre.textContent = c.boilerplate_footer;
          det.appendChild(sum);
          det.appendChild(pre);
          card.appendChild(det);
        }}
        box.appendChild(card);
      }});

      const doneCard = document.getElementById("doneCard");
      if (done === QUESTIONS.length) {{
        doneCard.classList.remove("hidden");
        document.getElementById("replyOutput").value = buildReplyLine();
      }} else {{
        doneCard.classList.add("hidden");
      }}
    }}

    document.addEventListener("keydown", (e) => {{
      if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
      const q = QUESTIONS[STATE.curIdx];
      if (!q) return;
      if (["0", "1", "2", "3"].includes(e.key)) {{
        e.preventDefault();
        selectGrade(q.qrel_id, STATE.activeSlot, Number(e.key));
      }} else if (e.key === "?") {{
        e.preventDefault();
        selectGrade(q.qrel_id, STATE.activeSlot, "Q");
      }} else if (e.key === "ArrowLeft" && STATE.curIdx > 0) {{
        e.preventDefault();
        jumpToQuestion(STATE.curIdx - 1);
      }} else if (e.key === "ArrowRight" && STATE.curIdx < QUESTIONS.length - 1) {{
        e.preventDefault();
        jumpToQuestion(STATE.curIdx + 1);
      }}
    }});

    document.getElementById("btnLayoutGrid").onclick = () => applyLayoutMode("grid");
    document.getElementById("btnLayoutStack").onclick = () => applyLayoutMode("stack");
    document.getElementById("btnRubricToggle").onclick = () => {{
      document.getElementById("rubricDrawer").classList.toggle("hidden");
    }};
    document.getElementById("btnFontDown").onclick = () => {{
      const idx = FONT_STEPS.indexOf(currentFontPx);
      if (idx > 0) applyFontSize(FONT_STEPS[idx - 1]);
    }};
    document.getElementById("btnFontUp").onclick = () => {{
      const idx = FONT_STEPS.indexOf(currentFontPx);
      if (idx >= 0 && idx < FONT_STEPS.length - 1) applyFontSize(FONT_STEPS[idx + 1]);
    }};
    document.getElementById("btnPrev").onclick = () => {{
      if (STATE.curIdx > 0) jumpToQuestion(STATE.curIdx - 1);
    }};
    document.getElementById("btnNext").onclick = () => {{
      if (STATE.curIdx < QUESTIONS.length - 1) jumpToQuestion(STATE.curIdx + 1);
    }};
    document.getElementById("btnReset").onclick = () => {{
      STATE = {{ curIdx: 0, activeSlot: "A", grades: {{}}, tags: {{}} }};
      savePersisted();
      render();
      scrollTopSmooth();
    }};
    document.getElementById("btnCopy").onclick = async () => {{
      const txt = buildReplyLine();
      try {{
        await navigator.clipboard.writeText(txt);
        document.getElementById("copyStatus").classList.remove("hidden");
      }} catch (_) {{
        const el = document.getElementById("replyOutput");
        el.select();
        document.execCommand("copy");
        document.getElementById("copyStatus").classList.remove("hidden");
      }}
    }};

    applyFontSize(currentFontPx);
    applyLayoutMode(currentLayout);
    render();
  </script>
</body>
</html>
"""
    audit_rendered_batch_html(html, batch_index=batch_index, expected_fingerprint=batch_fp)
    return html


__all__ = [
    "DEFAULT_FONT_SIZE_PX",
    "FAILURE_TAXONOMY_PILLS",
    "FONT_SIZE_STEPS_PX",
    "FORBIDDEN_AST_STUB_TOKENS",
    "FORBIDDEN_BLIND_HTML_TOKENS",
    "SURFACE_DISPLAY_LABELS",
    "WIDGET_LAYOUT_VERSION",
    "audit_rendered_batch_html",
    "build_batch_artifact_filename",
    "build_blind_batch_payload",
    "compute_batch_fingerprint",
    "parse_structured_core_statement",
    "render_blind_batch_widget_html",
]
