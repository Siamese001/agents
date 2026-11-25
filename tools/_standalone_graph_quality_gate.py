"""Auto-synced standalone Graph Explorer behavioral, contrast & firewall gate fallback for CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Sequence

CORE_GOVERNANCE_GRAPH_GATE_SHA256 = "55f21b247eb0c0d94baf3e0706c0eceb746d0bfced4d9efe34186d86c6209afc"

INV_FIREWALL = "INV-GRAPH-FIREWALL-ZERO-CROSS-REPO-SPILL"
INV_CONTRAST = "INV-GRAPH-WCAG-THEME-PARITY"
INV_BEHAVIOR = "INV-GRAPH-HOP-FORCE-MONOTONICITY"

PROFILE_ALIASES: dict[str, str] = {
    "8080": "port_8080", "port_8080": "port_8080", "decision_intelligence": "port_8080", "die": "port_8080",
    "8081": "port_8081", "port_8081": "port_8081", "agents": "port_8081",
    "8082": "port_8082", "port_8082": "port_8082", "long_goodbye": "port_8082",
}

FIREWALL_BLOCKLISTS: dict[str, tuple[str, ...]] = {
    "port_8080": (
        "127.0.0.1:8081", "localhost:8081", ":8081/", "127.0.0.1:8082", "localhost:8082", ":8082/",
        "augmented_skills_graph", "apps_rg", "resume_graph_engine", "outreach_engine", "Agents Repo - Career",
        "long_goodbye.sqlite", "apps_lg", "v23_nodes", "v23_edges", "v23_scenes", "v23_paragraphs",
        "Long-Goodbye", "Long Goodbye",
    ),
    "port_8081": (
        "127.0.0.1:8080", "localhost:8080", ":8080/", "127.0.0.1:8082", "localhost:8082", ":8082/",
        "long_goodbye.sqlite", "apps_lg", "v23_nodes", "v23_edges", "v23_scenes", "v23_paragraphs",
        "v23_edge_assertions", "Long-Goodbye", "Long Goodbye", "NextEra", "Partner Airgap",
        "build_azure_partner_portal_package", "unified_portfolio_explorer_template",
    ),
    "port_8082": (
        "127.0.0.1:8080", "localhost:8080", ":8080/", "127.0.0.1:8081", "localhost:8081", ":8081/",
        "augmented_skills_graph", "apps_rg", "resume_graph_engine", "outreach_engine", "Agents Repo - Career",
        "NextEra", "Partner Airgap", "Slalom", "employment_exp_slalom", "SVP_ENGINEERING_AI_PLATFORM",
    ),
}

REQUIRED_THEME_VARS: tuple[str, ...] = ("--bg-main", "--bg-card", "--text-main", "--text-muted", "--primary", "--primary-fg")
CONTRAST_PAIRS: tuple[tuple[str, str, float], ...] = (
    ("--text-main", "--bg-main", 4.5), ("--text-main", "--bg-card", 4.5),
    ("--text-muted", "--bg-card", 4.5), ("--primary-fg", "--primary", 3.0),
)
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB_RE = re.compile(r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
_VAR_DECL_RE = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);")
_SCRIPT_RE = re.compile(r"<script[^>]*>([\s\S]*?)</script>", re.IGNORECASE)

_NODE_VM_HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const markupOnly = html.replace(/<script[\s\S]*?<\/script>/gi, "");
const scriptCode = fs.readFileSync(process.argv[3], "utf8");
if (process.argv[4]) new vm.Script(fs.readFileSync(process.argv[4], "utf8"));
const makeClassList = (init = []) => {
  const s = new Set(init);
  return {
    add: (...c) => c.forEach((x) => x && s.add(x)),
    remove: (...c) => c.forEach((x) => s.delete(x)),
    toggle: (c, f) => { const n = f === undefined ? !s.has(c) : Boolean(f); n ? s.add(c) : s.delete(c); return n; },
    contains: (c) => s.has(c)
  };
};
const elementsById = new Map(), typePills = [], confBandPills = [], modeTabs = [], clusterOptions = new Map(), bandSpans = new Map();
function makeEl(id = "", tag = "div", attrs = {}, classes = []) {
  const listeners = new Map(); let _html = "", _kids = [];
  const el = {
    id, tagName: tag.toUpperCase(), value: attrs.value || "", checked: false,
    textContent: attrs.textContent || "", innerText: "", style: {},
    offsetHeight: id === "canvasLegendOverlay" ? 34 : 28,
    classList: makeClassList(classes), attributes: new Map(Object.entries(attrs)),
    setAttribute(k, v) { this.attributes.set(k, String(v)); },
    getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; },
    addEventListener(ev, fn) { if (!listeners.has(ev)) listeners.set(ev, []); listeners.get(ev).push(fn); },
    dispatchEvent(evObj) {
      evObj.currentTarget = this; if (!evObj.target) evObj.target = this;
      if (!evObj.preventDefault) evObj.preventDefault = () => {};
      (listeners.get(evObj.type) || []).forEach((fn) => fn(evObj));
    },
    click(detail = 1) { this.dispatchEvent({ type: "click", detail }); },
    dblclick() { this.dispatchEvent({ type: "dblclick", detail: 2 }); },
    contains(o) { return o === this || _kids.includes(o); },
    getBoundingClientRect() { return { left: 0, top: 0, width: 1280, height: 780 }; },
    get innerHTML() { return _html; },
    set innerHTML(h) {
      _html = String(h || ""); _kids = [];
      for (const m of _html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/gi)) {
        const aMap = {};
        for (const am of m[1].matchAll(/([a-zA-Z0-9_-]+)="([^"]*)"/g)) aMap[am[1]] = am[2];
        const child = makeEl(aMap.id || "", "button", aMap, (aMap.class || "").split(/\s+/).filter(Boolean));
        child.textContent = m[2].replace(/<[^>]+>/g, "").trim();
        if (aMap.id) elementsById.set(aMap.id, child);
        _kids.push(child);
      }
    },
    querySelectorAll(sel) {
      if (sel === "[data-pick-node]") return _kids.filter((c) => c.getAttribute("data-pick-node"));
      if (sel === ".jump-btn") return _kids.filter((c) => c.classList.contains("jump-btn"));
      return [];
    }
  };
  if (id) elementsById.set(id, el);
  return el;
}
for (const m of markupOnly.matchAll(/\bid="([a-zA-Z0-9_-]+)"/g)) if (!elementsById.has(m[1])) makeEl(m[1]);
const selM = markupOnly.match(/<select[^>]*id="clusterSelect"[^>]*>([\s\S]*?)<\/select>/i);
if (selM) for (const om of selM[1].matchAll(/<option[^>]*value="([^"]*)"[^>]*>([\s\S]*?)<\/option>/gi)) clusterOptions.set(om[1], om[2].replace(/<[^>]+>/g, "").trim());
for (const tm of markupOnly.matchAll(/data-type="([^"]+)"/g)) if (!typePills.some((p) => p.getAttribute("data-type") === tm[1])) typePills.push(makeEl("", "button", { "data-type": tm[1] }, ["type-pill"]));
for (const bm of markupOnly.matchAll(/data-conf-band="([^"]+)"/g)) if (!confBandPills.some((p) => p.getAttribute("data-conf-band") === bm[1])) { confBandPills.push(makeEl("", "button", { "data-conf-band": bm[1] }, ["conf-band-pill"])); bandSpans.set(bm[1], makeEl("", "span")); }
for (const mm of markupOnly.matchAll(/data-mode="([^"]+)"/g)) if (!modeTabs.some((p) => p.getAttribute("data-mode") === mm[1])) modeTabs.push(makeEl("", "button", { "data-mode": mm[1] }, ["mode-tab"]));

const ctx2d = {
  font: "", fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1, textAlign: "left", textBaseline: "middle",
  save() {}, restore() {}, clearRect() {}, translate() {}, scale() {}, setTransform() {}, beginPath() {}, closePath() {},
  moveTo() {}, lineTo() {}, quadraticCurveTo() {}, arc() {}, fill() {}, stroke() {}, strokeRect() {}, fillText() {}, setLineDash() {},
  measureText: (t) => ({ width: String(t || "").length * 6.8 })
};
const canvasEl = elementsById.get("graphCanvas") || makeEl("graphCanvas", "canvas");
canvasEl.parentElement = elementsById.get("canvasWrap") || makeEl("canvasWrap", "div");
canvasEl.getContext = () => ctx2d;
const layoutSel = elementsById.get("layoutSelect") || makeEl("layoutSelect", "select");
const clusterSel = elementsById.get("clusterSelect") || makeEl("clusterSelect", "select");
const hopBtn = elementsById.get("btnIsolateSubgraph") || makeEl("btnIsolateSubgraph", "button");
if (!layoutSel.value) layoutSel.value = "hierarchy";
if (!clusterSel.value) clusterSel.value = "all";
if (!hopBtn.textContent) hopBtn.textContent = "Depth: 1-Hop";

let queuedRaf = [];
const sandbox = {
  console, Math, Set, Map, Array, Object, String, Number, Boolean, RegExp, JSON, Infinity, NaN, parseInt, parseFloat, isNaN,
  setTimeout: (fn) => { fn(); return 1; }, clearTimeout: () => {},
  requestAnimationFrame: (fn) => { queuedRaf.push(fn); return queuedRaf.length; },
  window: { devicePixelRatio: 1, location: { hash: "#graph" }, addEventListener() {}, history: { replaceState() {} } },
  history: { replaceState() {} },
  document: {
    documentElement: { classList: makeClassList(["light"]), setAttribute() {} },
    getElementById: (id) => elementsById.get(id) || makeEl(id),
    querySelector(sel) {
      const mB = sel.match(/\[data-band-count="([^"]+)"\]/); if (mB) return bandSpans.get(mB[1]) || makeEl("", "span");
      const mO = sel.match(/#clusterSelect option\[value="([^"]+)"\]/); if (mO && clusterOptions.has(mO[1])) return { textContent: clusterOptions.get(mO[1]) };
      return null;
    },
    querySelectorAll: (sel) => sel === ".type-pill" ? typePills : (sel === ".conf-band-pill" ? confBandPills : (sel === ".mode-tab" ? modeTabs : [])),
    addEventListener() {}
  }
};
sandbox.globalThis = sandbox;
const drainRaf = (cap = 8) => { let k = 0; while (queuedRaf.length && k++ < cap) queuedRaf.shift()(); queuedRaf = []; };
const tail = `;globalThis.__GATE__ = { getVisibleNodes, getVisibleEdges, focusNode, handleSearchInput: typeof handleSearchInput !== "undefined" ? handleSearchInput : null, getState: () => ({ state: typeof state !== "undefined" ? state : {} }) };`;
vm.runInNewContext(scriptCode + tail, sandbox);
drainRaf(8);
const G = sandbox.__GATE__;
const minPairDist = (vis) => {
  let m = Infinity;
  for (let i = 0; i < vis.length; i++) for (let j = i + 1; j < vis.length; j++) m = Math.min(m, Math.hypot(vis[i].x - vis[j].x, vis[i].y - vis[j].y));
  return vis.length <= 1 ? 999 : m;
};
const checkConnected = (vis) => {
  if (vis.length <= 1) return true;
  const visSet = new Set(vis.map((n) => n.id)), adj = new Map(vis.map((n) => [n.id, []]));
  G.getVisibleEdges(visSet).forEach((e) => {
    const u = e.source ? e.source.id : e.from, v = e.target ? e.target.id : e.to;
    if (adj.has(u) && adj.has(v)) { adj.get(u).push(v); adj.get(v).push(u); }
  });
  const seen = new Set([vis[0].id]), q = [vis[0].id];
  while (q.length) for (const nb of adj.get(q.shift()) || []) if (!seen.has(nb)) { seen.add(nb); q.push(nb); }
  return seen.size === vis.length;
};
layoutSel.value = "force"; layoutSel.dispatchEvent({ type: "change", target: layoutSel }); drainRaf(4);
const f1 = G.getVisibleNodes(), md1 = minPairDist(f1), c1 = checkConnected(f1);
hopBtn.click(); drainRaf(4);
const f2 = G.getVisibleNodes(), md2 = minPairDist(f2), c2 = checkConnected(f2);
hopBtn.click(); drainRaf(4);
const f3 = G.getVisibleNodes(), md3 = minPairDist(f3), c3 = checkConnected(f3);
hopBtn.click(); drainRaf(4);
const fOff = G.getVisibleNodes(), mdOff = minPairDist(fOff);

let searchCleared = true, searchHopGrowth = true;
if (G.handleSearchInput && elementsById.has("graphSearchDropdown") && f2.length > 1) {
  if (elementsById.has("resetBtn")) elementsById.get("resetBtn").click();
  layoutSel.value = "force"; layoutSel.dispatchEvent({ type: "change", target: layoutSel });
  const cand = f2.find((n) => String(n.label || "").trim().length >= 5) || f2[0];
  const qStr = String(cand.label).trim().slice(0, 12);
  elementsById.get("searchInput").value = qStr; G.handleSearchInput(qStr);
  const picks = elementsById.get("graphSearchDropdown").querySelectorAll("[data-pick-node]");
  if (picks.length > 0) {
    picks[0].click(); searchCleared = (G.getState().state.search === "");
    const sp1 = G.getVisibleNodes().length; hopBtn.click(); const sp2 = G.getVisibleNodes().length;
    searchHopGrowth = sp1 < sp2;
  }
}
console.log(JSON.stringify({ counts: [f1.length, f2.length, f3.length, fOff.length], minDists: [md1, md2, md3, mdOff], connected: [c1, c2, c3], searchCleared, searchHopGrowth }));
"""

def resolve_profile_name(profile: str) -> str:
    key = str(profile or "").strip().lower().replace("-", "_")
    if key not in PROFILE_ALIASES:
        raise ValueError(f"Unknown graph firewall profile '{profile}'. Expected one of: {sorted(PROFILE_ALIASES)}")
    return PROFILE_ALIASES[key]

def _parse_color_rgb(raw: str) -> tuple[int, int, int] | None:
    val = raw.strip().split("!")[0].strip()
    m_hex = _HEX_RE.match(val)
    if m_hex:
        hx = "".join(ch * 2 for ch in m_hex.group(1)) if len(m_hex.group(1)) == 3 else m_hex.group(1)
        return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
    m_rgb = _RGB_RE.match(val)
    return (int(m_rgb.group(1)), int(m_rgb.group(2)), int(m_rgb.group(3))) if m_rgb else None

def compute_wcag_contrast(rgb_a: tuple[int, int, int], rgb_b: tuple[int, int, int]) -> float:
    def _lum(rgb: tuple[int, int, int]) -> float:
        ch = [(max(0.0, min(1.0, c / 255.0))) for c in rgb]
        lin = [s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4 for s in ch]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    l1, l2 = _lum(rgb_a), _lum(rgb_b)
    return round((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05), 2)

def verify_cross_repo_firewall(html_text: str, profile: str, *, extra_payload_texts: Sequence[str] = ()) -> list[str]:
    prof = resolve_profile_name(profile)
    violations: list[str] = []
    corpora = [("html_bundle", html_text), *((f"payload_{i}", t) for i, t in enumerate(extra_payload_texts))]
    for token in FIREWALL_BLOCKLISTS[prof]:
        for src_name, blob in corpora:
            if token in blob:
                violations.append(f"{INV_FIREWALL} [{prof}]: forbidden cross-repo token '{token}' found in {src_name}")
                break
    return violations

def verify_contrast_and_surface_parity(html_text: str) -> list[str]:
    violations: list[str] = []
    styles = "\n".join(re.findall(r"<style[^>]*>([\s\S]*?)</style>", html_text, re.I))
    light_m, dark_m = re.search(r":root[^{]*\{([^}]*)\}", styles, re.S), re.search(r"html\.dark[^{]*\{([^}]*)\}", styles, re.S)
    light_vars = {m.group(1): m.group(2).strip() for m in _VAR_DECL_RE.finditer(light_m.group(1) if light_m else "")}
    dark_vars = {m.group(1): m.group(2).strip() for m in _VAR_DECL_RE.finditer(dark_m.group(1) if dark_m else "")}
    for theme_name, tvars in (("light", light_vars), ("dark", dark_vars)):
        missing = [k for k in REQUIRED_THEME_VARS if k not in tvars]
        if missing:
            violations.append(f"{INV_CONTRAST} [{theme_name}]: missing CSS theme tokens {missing}")
            continue
        for fg_k, bg_k, floor in CONTRAST_PAIRS:
            fg_rgb, bg_rgb = _parse_color_rgb(tvars[fg_k]), _parse_color_rgb(tvars[bg_k])
            if fg_rgb is None or bg_rgb is None:
                violations.append(f"{INV_CONTRAST} [{theme_name}]: unparseable color in {fg_k}/{bg_k}")
            elif compute_wcag_contrast(fg_rgb, bg_rgb) < floor:
                violations.append(
                    f"{INV_CONTRAST} [{theme_name}]: contrast {fg_k} vs {bg_k} is {compute_wcag_contrast(fg_rgb, bg_rgb)}:1 (< {floor}:1)"
                )
    for req_band in ("ALL", "VERIFIED", "HIGH", "ESTABLISHED", "PROVISIONAL", "LOW"):
        if f'data-conf-band="{req_band}"' not in html_text:
            violations.append(f"{INV_CONTRAST}: missing confidence filter band '{req_band}'")
    if 'id="graphCanvas"' not in html_text or ("zoomInBtn" not in html_text and "zoomAroundCenter" not in html_text):
        violations.append(f"{INV_CONTRAST}: missing graphCanvas or viewport zoom controls")
    return violations

def verify_behavioral_multihop_and_force_vm(
    html_text: str, *, portal_html_text: str = "", min_pair_dist_px: float = 12.0
) -> tuple[list[str], dict[str, Any]]:
    node_bin = shutil.which("node")
    if not node_bin:
        return [f"{INV_BEHAVIOR}: node binary not found in PATH for headless VM check"], {}
    scripts = _SCRIPT_RE.findall(html_text)
    if not scripts:
        return [f"{INV_BEHAVIOR}: no <script> block found in explorer HTML"], {}
    portal_scripts = _SCRIPT_RE.findall(portal_html_text) if portal_html_text else []

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        html_p, js_p, harness_p = td / "bundle.html", td / "bundle.js", td / "harness.js"
        html_p.write_text(html_text, encoding="utf-8")
        js_p.write_text(scripts[-1], encoding="utf-8")
        harness_p.write_text(_NODE_VM_HARNESS, encoding="utf-8")
        argv = [node_bin, str(harness_p), str(html_p), str(js_p)]
        if portal_scripts:
            portal_p = td / "portal.js"
            portal_p.write_text(portal_scripts[-1], encoding="utf-8")
            argv.append(str(portal_p))
        proc = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=30, check=False)
        if proc.returncode != 0:
            return [f"{INV_BEHAVIOR}: Node VM execution failed: {(proc.stderr or proc.stdout).strip()[-400:]}"], {}
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
        metrics = json.loads(lines[-1]) if lines else {}

    violations: list[str] = []
    c1, c2, c3, c_off = metrics.get("counts", [0, 0, 0, 0])
    if not (0 < c1 < c2 < c3 <= c_off):
        violations.append(f"{INV_BEHAVIOR}: expected 1-Hop < 2-Hop < 3-Hop <= Off, got {[c1, c2, c3, c_off]}")
    for label, md in zip(("1-Hop", "2-Hop", "3-Hop", "Off"), metrics.get("minDists", [])):
        if float(md) <= min_pair_dist_px:
            violations.append(f"{INV_BEHAVIOR}: Force overlap in {label} (minDist={md:.2f}px <= {min_pair_dist_px}px)")
    for label, ok in zip(("1-Hop", "2-Hop", "3-Hop"), metrics.get("connected", [])):
        if not ok:
            violations.append(f"{INV_BEHAVIOR}: disconnected islands detected in {label}")
    if not metrics.get("searchCleared", True):
        violations.append(f"{INV_BEHAVIOR}: picking a search result did not clear active search text")
    if not metrics.get("searchHopGrowth", True):
        violations.append(f"{INV_BEHAVIOR}: search-picked node failed 1-Hop < 2-Hop expansion")
    return violations, metrics

def run_graph_explorer_quality_gate(
    html_text: str, *, profile: str, portal_html_text: str = "", extra_payload_texts: Sequence[str] = (), run_vm: bool = True
) -> dict[str, Any]:
    prof = resolve_profile_name(profile)
    fw_errs = verify_cross_repo_firewall(
        html_text, prof, extra_payload_texts=(*extra_payload_texts, *((portal_html_text,) if portal_html_text else ()))
    )
    ct_errs = verify_contrast_and_surface_parity(html_text)
    vm_errs, vm_metrics = verify_behavioral_multihop_and_force_vm(html_text, portal_html_text=portal_html_text) if run_vm else ([], {})
    all_errs = [*fw_errs, *ct_errs, *vm_errs]
    return {"passed": len(all_errs) == 0, "profile": prof, "violation_count": len(all_errs), "violations": all_errs, "vm_metrics": vm_metrics}

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Centralized Graph Explorer Quality & Cross-Repo Firewall Gate.")
    ap.add_argument("--html", type=Path, help="Rendered Explorer HTML bundle to validate.")
    ap.add_argument("--profile", default="port_8081", help="Firewall profile (port_8080, port_8081, port_8082).")
    ap.add_argument("--portal-html", type=Path, default=None, help="Optional live portal shell HTML.")
    ap.add_argument("--check-self", action="store_true", help="Verify module line budget and profile presets.")
    args = ap.parse_args(argv)
    if args.check_self:
        lc = len(Path(__file__).read_text(encoding="utf-8").splitlines())
        ok = lc <= 360 and set(FIREWALL_BLOCKLISTS) == {"port_8080", "port_8081", "port_8082"}
        print(json.dumps({"passed": ok, "line_count": lc}))
        return 0 if ok else 1
    if not args.html or not args.html.is_file():
        ap.error("--html must point to an existing HTML file")
    portal_txt = args.portal_html.read_text(encoding="utf-8") if args.portal_html and args.portal_html.is_file() else ""
    res = run_graph_explorer_quality_gate(args.html.read_text(encoding="utf-8"), profile=args.profile, portal_html_text=portal_txt)
    print(json.dumps(res, indent=2))
    return 0 if res["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
