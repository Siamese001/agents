"""Unmocked integration tests for the Agents Knowledge Graph Explorer dataset, HTML export, and HTTP portal."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

from scripts.serve_agents_graph_portal import create_agents_graph_portal_server
from tools import _standalone_graph_quality_gate
from tools.export_interactive_knowledge_graph import export_interactive_knowledge_graph
from tools.verify_graph_explorer_gate import (
    main as verify_gate_main,
    run_agents_graph_quality_gate,
    verify_agents_explorer_artifacts,
)
from tools.interactive_graph_export_core.dataset_builder import (
    IDENTITY_ROOT_ID,
    UI_TYPE_META,
    build_agents_explorer_dataset,
    compute_multihop_subgraph,
    filter_bundle_lens,
    render_explorer_html,
    render_portal_shell_html,
    resolve_default_graph_db_path,
    search_bundle_nodes,
)


def test_build_agents_explorer_dataset_from_live_sqlite() -> None:
    db_path = resolve_default_graph_db_path()
    assert db_path.is_file(), f"Expected live skills graph DB at {db_path}"

    data = build_agents_explorer_dataset(db_path)
    assert data["repo_name"] == "agents"
    assert data["total_nodes"] >= 800
    assert data["total_edges"] >= 4000
    assert data["total_evidence_links"] > 0
    assert len(data["nodes"]) == data["total_nodes"]
    assert len(data["edges"]) == data["total_edges"]

    node_ids = {n["id"] for n in data["nodes"]}
    assert IDENTITY_ROOT_ID in node_ids
    for edge in data["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids
        assert edge["from"] != edge["to"]

    assert len(data["skills"]) >= 200
    assert len(data["engagements"]) >= 40
    assert len(data["evidence"]) >= 150
    assert len(data["role_projections"]) >= 15
    assert len(data["employments"]) == 6


def test_filter_lens_and_search_helpers() -> None:
    data = build_agents_explorer_dataset()
    backbone = filter_bundle_lens(data, "backbone")
    assert 15 <= backbone["node_count"] <= 35
    assert backbone["edge_count"] > 0

    track_slice = filter_bundle_lens(data, "track_genai_agentic")
    assert track_slice["node_count"] > 10
    assert track_slice["edge_count"] > 0

    hits = search_bundle_nodes(data, "agentic")
    assert hits["count"] > 0
    assert all("id" in r and "label" in r for r in hits["results"])


def test_export_standalone_html(tmp_path: Path) -> None:
    receipt = export_interactive_knowledge_graph(output_dir=tmp_path)
    out_file = Path(receipt["output_html"])
    assert out_file.is_file()
    html_text = out_file.read_text(encoding="utf-8")
    assert "Agents Repo - Career &amp; Skills Graph" in html_text
    assert 'id="graphCanvas"' in html_text
    assert 'id="archMatrixSvg"' in html_text
    assert IDENTITY_ROOT_ID in html_text
    assert "__SNAPSHOT_DATE__" not in html_text

    rendered_arch = render_explorer_html(build_agents_explorer_dataset(), default_mode="opmodel")
    assert '"opmodel"' in rendered_arch


def test_live_http_portal_endpoints() -> None:
    server = create_agents_graph_portal_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=10) as resp:
            assert resp.status == 200
            health = json.loads(resp.read().decode("utf-8"))
            assert health["status"] == "ok"
            assert health["total_nodes"] >= 800

        with urllib.request.urlopen(f"{base}/graph", timeout=10) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert "/api/v1/bootstrap" in body
            assert 'id="graphCanvas"' in body

        with urllib.request.urlopen(f"{base}/api/v1/bootstrap", timeout=10) as resp:
            assert resp.status == 200
            boot = json.loads(resp.read().decode("utf-8"))
            assert boot["total_nodes"] >= 800
            assert len(boot["skills"]) >= 200

        with urllib.request.urlopen(f"{base}/api/v1/lens/backbone", timeout=10) as resp:
            assert resp.status == 200
            lens = json.loads(resp.read().decode("utf-8"))
            assert 15 <= lens["node_count"] <= 35

        with urllib.request.urlopen(f"{base}/api/v1/node/{IDENTITY_ROOT_ID}", timeout=10) as resp:
            assert resp.status == 200
            node_resp = json.loads(resp.read().decode("utf-8"))
            assert node_resp["node"]["id"] == IDENTITY_ROOT_ID
            assert len(node_resp["edges"]) > 0

        with urllib.request.urlopen(f"{base}/api/v1/node/pillar_agentic_ai_platforms?hops=2", timeout=10) as resp:
            assert resp.status == 200
            hop2_resp = json.loads(resp.read().decode("utf-8"))
            assert hop2_resp["hops"] == 2
            assert hop2_resp["node_count"] > 45
            assert hop2_resp["edge_count"] >= hop2_resp["node_count"] - 1

        with urllib.request.urlopen(f"{base}/api/v1/search?q=slalom", timeout=10) as resp:
            assert resp.status == 200
            srch = json.loads(resp.read().decode("utf-8"))
            assert srch["count"] > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_multihop_subgraph_zero_disconnected_islands() -> None:
    """Verify 2-hop and 3-hop neighborhoods are 100% connected and block super-hub hairball bounce."""
    data = build_agents_explorer_dataset()
    for target_id in ("pillar_agentic_ai_platforms", "skill_governed_agentic_systems_architecture"):
        for hops in (2, 3):
            sub = compute_multihop_subgraph(data, target_id, hops=hops)
            node_ids = {n["id"] for n in sub["nodes"]}
            assert target_id in node_ids
            assert len(node_ids) > 15

            # Build induced adjacency from returned visible edges and prove 100% reachability
            adj: dict[str, set[str]] = {nid: set() for nid in node_ids}
            for e in sub["edges"]:
                u, v = e["from"], e["to"]
                assert u in node_ids and v in node_ids
                adj[u].add(v)
                adj[v].add(u)

            visited = {target_id}
            queue = [target_id]
            while queue:
                cur = queue.pop(0)
                for nb in adj[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)

            disconnected = node_ids - visited
            assert not disconnected, f"{target_id} at {hops}-hop had disconnected nodes: {disconnected}"

    # Specifically verify Agentic AI Platforms 2-hop expands into its own domains & skills without bouncing into Actuarial/Derivatives skills
    ag_sub = compute_multihop_subgraph(data, "pillar_agentic_ai_platforms", hops=2)
    ag_ids = {n["id"] for n in ag_sub["nodes"]}
    assert "domain_agentic_systems_architecture" in ag_ids
    assert "skill_governed_agentic_systems_architecture" in ag_ids
    assert "skill_derivatives_derivatives_pricing" not in ag_ids


def test_backbone_connectivity_role_projections_and_multihop_api_parity() -> None:
    """Verify connected Career Backbone, read-only role_family projections, and uniform /api/v1/node?hops=1..3 parity."""
    data = build_agents_explorer_dataset()
    node_by_id = {n["id"]: n for n in data["nodes"]}
    assert node_by_id[IDENTITY_ROOT_ID]["rawType"] == "identity"

    # 1. Career Backbone forms a single connected component (0 isolated backbone hubs)
    backbone = filter_bundle_lens(data, "backbone")
    bb_ids = {n["id"] for n in backbone["nodes"]}
    bb_adj: dict[str, set[str]] = {nid: set() for nid in bb_ids}
    for edge in backbone["edges"]:
        bb_adj[edge["from"]].add(edge["to"])
        bb_adj[edge["to"]].add(edge["from"])
    visited = {IDENTITY_ROOT_ID}
    queue = [IDENTITY_ROOT_ID]
    while queue:
        cur = queue.pop(0)
        for nb in bb_adj[cur]:
            if nb not in visited:
                visited.add(nb)
                queue.append(nb)
    assert visited == bb_ids, f"Isolated Career Backbone hubs detected: {bb_ids - visited}"

    # 2. All 30 non-root role_family nodes project > 1 distinct weighted pillar/skill edges
    role_family_nodes = [n for n in data["nodes"] if n["rawType"] == "role_family"]
    assert len(role_family_nodes) == 30
    for rf_node in role_family_nodes:
        incident = [e for e in data["edges"] if e["from"] == rf_node["id"] or e["to"] == rf_node["id"]]
        assert len(incident) > 1, f"{rf_node['id']} had <= 1 incident edges"

    # 3. Strict multi-hop growth across root, pillar, employment, skill, policy_rule, and role_family
    for target_id in (
        IDENTITY_ROOT_ID,
        "pillar_agentic_ai_platforms",
        "employment_exp_slalom_001",
        "skill_governed_agentic_systems_architecture",
        "policy_rule_skill_projection_not_proof",
        "SVP_ENGINEERING_AI_PLATFORM",
    ):
        sub1 = compute_multihop_subgraph(data, target_id, hops=1)
        sub2 = compute_multihop_subgraph(data, target_id, hops=2)
        sub3 = compute_multihop_subgraph(data, target_id, hops=3)
        assert sub1["node_count"] < sub2["node_count"] < sub3["node_count"], (
            f"Expected strict multi-hop growth for {target_id}: "
            f"1-hop={sub1['node_count']}, 2-hop={sub2['node_count']}, 3-hop={sub3['node_count']}"
        )

    # 4. Bridge-first enabled_types traversal retains intermediate bridges so 2-hop never starves or disconnects
    types_without_domain = set(UI_TYPE_META.keys()) - {"domain"}
    bf1 = compute_multihop_subgraph(data, "pillar_agentic_ai_platforms", hops=1, enabled_types=types_without_domain)
    bf2 = compute_multihop_subgraph(data, "pillar_agentic_ai_platforms", hops=2, enabled_types=types_without_domain)
    assert bf2["node_count"] > bf1["node_count"]

    # 5. Live HTTP /api/v1/node/<id>?hops=1..3 schema & strict growth parity
    server = create_agents_graph_portal_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    expected_keys = {"node", "center_id", "hops", "node_count", "edge_count", "nodes", "edges"}
    try:
        counts: list[int] = []
        for h in (1, 2, 3):
            with urllib.request.urlopen(f"{base}/api/v1/node/{IDENTITY_ROOT_ID}?hops={h}", timeout=10) as resp:
                assert resp.status == 200
                payload = json.loads(resp.read().decode("utf-8"))
                assert set(payload.keys()) == expected_keys
                assert payload["hops"] == h
                assert payload["node_count"] == len(payload["nodes"])
                assert payload["edge_count"] == len(payload["edges"])
                counts.append(payload["node_count"])
        assert counts[0] < counts[1] < counts[2]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_explorer_client_force_layout_and_multihop_transitions_in_node_vm(tmp_path: Path) -> None:
    """Execute rendered Explorer JS in Node VM to verify Force 1/2/3-hop, search pick, scopes, and collision physics."""
    node_bin = shutil.which("node")
    assert node_bin is not None, "node runtime is required for client-side explorer behavioral verification"

    data = build_agents_explorer_dataset()
    rendered_html = render_explorer_html(data, default_mode="graph")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", rendered_html, re.S)
    assert len(scripts) == 1

    # Also verify portal shell HTML renders valid async bootstrap syntax
    portal_html = render_portal_shell_html(data, default_mode="graph")
    portal_scripts = re.findall(r"<script[^>]*>(.*?)</script>", portal_html, re.S)
    assert len(portal_scripts) == 1

    bundle_js = tmp_path / "explorer_bundle.js"
    portal_js = tmp_path / "portal_bundle.js"
    harness_js = tmp_path / "verify_explorer_vm.js"
    bundle_js.write_text(scripts[0], encoding="utf-8")
    portal_js.write_text(portal_scripts[0], encoding="utf-8")

    harness_js.write_text(
        r"""
const vm = require("vm");
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
const portalCode = fs.readFileSync(process.argv[3], "utf8");

// Syntax-compile portal shell script to ensure zero wrapper brace/quote regressions
new vm.Script(portalCode);

function makeClassList(initial = []) {
  const set = new Set(initial);
  return {
    add: (...cls) => cls.forEach((c) => c && set.add(c)),
    remove: (...cls) => cls.forEach((c) => set.delete(c)),
    toggle: (c, force) => {
      if (force === undefined) {
        if (set.has(c)) { set.delete(c); return false; }
        set.add(c); return true;
      }
      if (force) set.add(c); else set.delete(c);
      return Boolean(force);
    },
    contains: (c) => set.has(c)
  };
}

const elementsById = new Map();
const typePills = [];
const confBandPills = [];
const modeTabs = [];
const clusterOptions = new Map([
  ["all", "Full Career Graph (All Nodes)"],
  ["backbone", "Career Architecture Backbone"],
  ["policy_guardrails", "Policy & Claim Guardrails"],
  ["projections_layer", "Role Projections & Resume Sections"],
  ["track_genai_agentic", "Track 3: GenAI & Agentic AI Platforms"],
  ["emp_slalom", "Slalom — Senior Director"],
  ["emp_unify", "Unify Consulting — SVP Engineering"]
]);

function makeEl(id = "", tag = "div", attrs = {}, classes = []) {
  const listeners = new Map();
  let _innerHTML = "";
  let _children = [];
  const el = {
    id, tagName: tag.toUpperCase(), value: attrs.value || "", checked: false,
    textContent: attrs.textContent || "", innerText: "", style: {},
    offsetHeight: id === "canvasLegendOverlay" ? 34 : 28,
    classList: makeClassList(classes),
    attributes: new Map(Object.entries(attrs)),
    setAttribute(k, v) { this.attributes.set(k, String(v)); },
    getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null; },
    addEventListener(ev, fn) {
      if (!listeners.has(ev)) listeners.set(ev, []);
      listeners.get(ev).push(fn);
    },
    dispatchEvent(evObj) {
      const fns = listeners.get(evObj.type) || [];
      evObj.currentTarget = this;
      if (!evObj.target) evObj.target = this;
      if (!evObj.preventDefault) evObj.preventDefault = () => {};
      fns.forEach((fn) => fn(evObj));
    },
    click(detail = 1) { this.dispatchEvent({ type: "click", detail }); },
    dblclick() { this.dispatchEvent({ type: "dblclick", detail: 2 }); },
    contains(other) { return other === this || _children.includes(other); },
    getBoundingClientRect() { return { left: 0, top: 0, width: 1280, height: 780 }; },
    get innerHTML() { return _innerHTML; },
    set innerHTML(htmlStr) {
      _innerHTML = String(htmlStr || "");
      _children = [];
      const btnRe = /<button\b([^>]*)>([\s\S]*?)<\/button>/gi;
      let m;
      while ((m = btnRe.exec(_innerHTML)) !== null) {
        const aMap = {};
        const aRe = /([a-zA-Z0-9_-]+)="([^"]*)"/g;
        let am;
        while ((am = aRe.exec(m[1])) !== null) aMap[am[1]] = am[2];
        const cls = (aMap.class || "").split(/\s+/).filter(Boolean);
        const child = makeEl(aMap.id || "", "button", aMap, cls);
        child.textContent = m[2].replace(/<[^>]+>/g, "").trim();
        if (aMap.id) elementsById.set(aMap.id, child);
        _children.push(child);
      }
    },
    querySelectorAll(sel) {
      if (sel === "[data-pick-node]") return _children.filter((c) => c.getAttribute("data-pick-node"));
      if (sel === ".jump-btn") return _children.filter((c) => c.classList.contains("jump-btn"));
      return [];
    }
  };
  if (id) elementsById.set(id, el);
  return el;
}

const canvasParent = makeEl("canvasWrap", "div");
const ctx2d = {
  font: "", fillStyle: "", strokeStyle: "", lineWidth: 1, globalAlpha: 1, textAlign: "left", textBaseline: "middle",
  save() {}, restore() {}, clearRect() {}, translate() {}, scale() {}, setTransform() {},
  beginPath() {}, closePath() {}, moveTo() {}, lineTo() {}, quadraticCurveTo() {}, arc() {},
  fill() {}, stroke() {}, strokeRect() {}, fillText() {}, setLineDash() {},
  measureText(txt) { return { width: String(txt || "").length * 6.8 }; }
};
const canvasEl = makeEl("graphCanvas", "canvas");
canvasEl.parentElement = canvasParent;
canvasEl.getContext = () => ctx2d;

[
  "inspectorContent", "hoverBanner", "hoverText", "hoverSub", "visibleStats",
  "canvasLegendOverlay", "btnAllTypes", "btnIsolateSubgraph", "layoutSelect",
  "sizeSelect", "colorSelect", "btnToggleFullTopology", "fitToScreenBtn",
  "zoomInBtn", "zoomOutBtn", "resetBtn", "clusterSelect", "activeScopeBadge",
  "btnClearSsotScope", "activeSearchChip", "graphSearchMatchBadge",
  "btnToggleGuide", "btnCloseGuide", "panelGuideWrap", "themeBtn",
  "searchInput", "graphSearchDropdown", "btnClearSearch",
  "btnCloseDrawer", "detailOverlay", "btnDrawerFocusGraph", "drawerKicker", "drawerTitle", "drawerBody",
  "btnArchToGraph", "btnArchToSkills", "btnArchToEngagements",
  "skillsSortSelect", "chkGroupPillar", "btnToggleSkillsDensity", "btnExportSkillsCsv", "btnResetSkills",
  "btnResetEvidence", "btnExportEngCsv", "btnResetEng",
  "viewOpModelWorkspace", "viewPortfolioWorkspace", "viewSignalsWorkspace",
  "viewDeliveryWorkspace", "viewAgendasWorkspace", "viewGraphWorkspace",
  "kpiArchNodes", "kpiArchSkills", "kpiArchEvidence", "kpiArchGov", "archMatrixSvg",
  "archFocusTitle", "archFocusDesc", "archFocusStats", "archFocusList",
  "kpiPortTotal", "kpiPortExt", "kpiPortProof", "kpiPortConf", "skillsRowTelemetry", "skillsTable", "skillsTableBody",
  "kpiEvMetrics", "kpiEvFacts", "kpiEvRepo", "kpiEvPolicy", "evidenceRowTelemetry", "evidenceLineageText", "evidenceTableBody",
  "kpiEngTotal", "kpiEngSkills", "kpiEngFacts", "kpiEngMetrics", "engRowTelemetry", "engagementsTableBody",
  "projCountBadge", "roleProjectionsGrid"
].forEach((id) => { if (!elementsById.has(id)) makeEl(id); });

elementsById.get("layoutSelect").value = "hierarchy";
elementsById.get("clusterSelect").value = "all";
elementsById.get("btnIsolateSubgraph").textContent = "Depth: 1-Hop";

["backbone","epoch","employment","pillar","domain","skill","engagement","evidence","metric","projection","policy"].forEach((t) => {
  typePills.push(makeEl("", "button", { "data-type": t }, ["type-pill"]));
});
["ALL","VERIFIED","HIGH","ESTABLISHED","PROVISIONAL","LOW"].forEach((b) => {
  confBandPills.push(makeEl("", "button", { "data-conf-band": b }, ["conf-band-pill"]));
});
["opmodel","portfolio","signals","delivery","agendas","graph"].forEach((m) => {
  modeTabs.push(makeEl("", "button", { "data-mode": m }, ["mode-tab"]));
});
const bandSpans = new Map();
["VERIFIED","HIGH","ESTABLISHED","PROVISIONAL","LOW"].forEach((b) => bandSpans.set(b, makeEl("", "span")));

let queuedRaf = [];
const sandbox = {
  console, Math, Set, Map, Array, Object, String, Number, Boolean, RegExp, JSON,
  Infinity, NaN, parseInt, parseFloat, isNaN,
  setTimeout: (fn) => { fn(); return 1; },
  clearTimeout: () => {},
  requestAnimationFrame: (fn) => { const id = queuedRaf.length + 1; queuedRaf.push(fn); return id; },
  window: { devicePixelRatio: 1, location: { hash: "#graph" }, addEventListener() {}, history: { replaceState() {} } },
  history: { replaceState() {} },
  document: {
    documentElement: { classList: makeClassList(["light"]), setAttribute() {} },
    getElementById(id) { return elementsById.get(id) || makeEl(id); },
    querySelector(sel) {
      const mBand = sel.match(/\[data-band-count="([^"]+)"\]/);
      if (mBand) return bandSpans.get(mBand[1]);
      const mOpt = sel.match(/#clusterSelect option\[value="([^"]+)"\]/);
      if (mOpt && clusterOptions.has(mOpt[1])) return { textContent: clusterOptions.get(mOpt[1]) };
      return null;
    },
    querySelectorAll(sel) {
      if (sel === ".type-pill") return typePills;
      if (sel === ".conf-band-pill") return confBandPills;
      if (sel === ".mode-tab") return modeTabs;
      return [];
    },
    addEventListener() {}
  }
};
sandbox.globalThis = sandbox;
const exportTail = `
;globalThis.__TEST__ = {
  getVisibleNodes, getVisibleEdges, focusNode, setScope, handleSearchInput,
  forceSleep: () => { simSleeping = true; rafId = null; },
  getState: () => ({ state, activeLayout, isolateHopDepth, selectedNode, camera, simSleeping, enabledTypes, edges })
};
`;

vm.runInNewContext(code + exportTail, sandbox);
while (queuedRaf.length) { const fn = queuedRaf.shift(); fn(); }
const T = sandbox.__TEST__;

function minPairDist(vis) {
  let minD = Infinity;
  for (let i = 0; i < vis.length; i++) {
    for (let j = i + 1; j < vis.length; j++) {
      const d = Math.hypot(vis[i].x - vis[j].x, vis[i].y - vis[j].y);
      if (d < minD) minD = d;
    }
  }
  return vis.length <= 1 ? 999 : minD;
}

function assertConnected(vis, label) {
  const visSet = new Set(vis.map((n) => n.id));
  const visEdges = T.getVisibleEdges(visSet);
  if (vis.length <= 1) return;
  const adj = new Map(vis.map((n) => [n.id, []]));
  visEdges.forEach((e) => { adj.get(e.source.id).push(e.target.id); adj.get(e.target.id).push(e.source.id); });
  const seen = new Set([vis[0].id]);
  const q = [vis[0].id];
  while (q.length) {
    const c = q.shift();
    for (const nb of adj.get(c) || []) { if (!seen.has(nb)) { seen.add(nb); q.push(nb); } }
  }
  if (seen.size !== vis.length) throw new Error(`Disconnected island in ${label}: ${seen.size}/${vis.length}`);
}

// 1. Fresh /graph boot -> switch Layout: Force -> cycle 1-Hop -> 2-Hop -> 3-Hop -> Off
const bootVis = T.getVisibleNodes();
if (bootVis.length !== 25) throw new Error("Expected 25 backbone nodes on boot");
assertConnected(bootVis, "boot-backbone");

const layoutSel = elementsById.get("layoutSelect");
const hopBtn = elementsById.get("btnIsolateSubgraph");
layoutSel.value = "force";
layoutSel.dispatchEvent({ type: "change", target: layoutSel });

const f1 = T.getVisibleNodes(); const md1 = minPairDist(f1); assertConnected(f1, "force-1hop");
hopBtn.click();
const f2 = T.getVisibleNodes(); const md2 = minPairDist(f2); assertConnected(f2, "force-2hop");
const r1Mean = f2.filter((n) => n._hopRing === 1).reduce((s, n) => s + Math.hypot(n.x, n.y), 0) / f2.filter((n) => n._hopRing === 1).length;
const r2Mean = f2.filter((n) => n._hopRing === 2).reduce((s, n) => s + Math.hypot(n.x, n.y), 0) / f2.filter((n) => n._hopRing === 2).length;
hopBtn.click();
const f3 = T.getVisibleNodes(); const md3 = minPairDist(f3); assertConnected(f3, "force-3hop");
const r3Mean = f3.filter((n) => n._hopRing === 3).reduce((s, n) => s + Math.hypot(n.x, n.y), 0) / f3.filter((n) => n._hopRing === 3).length;
hopBtn.click();
const fOff = T.getVisibleNodes(); const mdOff = minPairDist(fOff); assertConnected(fOff, "force-off");

if (!(f1.length < f2.length && f2.length < f3.length && f3.length <= fOff.length)) throw new Error("Strict Force hop growth failed");
if (md1 <= 12 || md2 <= 12 || md3 <= 12 || mdOff <= 12) throw new Error("Force collision overlap detected");
if (!(r1Mean < r2Mean && r2Mean < r3Mean)) throw new Error("Concentric Force ring ordering failed");

// 2. Single-click in Depth: Off preserves layout coordinates; drag wakes simulation
const beforeMap = new Map(fOff.map((n) => [n.id, { x: n.x, y: n.y }]));
const hitTarget = fOff.find((n) => n.id === "pillar_agentic_ai_platforms");
const st = T.getState();
const sx = hitTarget.x * st.camera.zoom + st.camera.x;
const sy = hitTarget.y * st.camera.zoom + st.camera.y;
canvasEl.dispatchEvent({ type: "pointerdown", clientX: sx, clientY: sy, pointerId: 1 });
canvasEl.dispatchEvent({ type: "pointerup", clientX: sx, clientY: sy, pointerId: 1 });
for (const n of T.getVisibleNodes()) {
  const b = beforeMap.get(n.id);
  if (Math.hypot(n.x - b.x, n.y - b.y) > 0.001) throw new Error("Single-click scrambled Depth: Off layout");
}
T.forceSleep();
queuedRaf = [];
canvasEl.dispatchEvent({ type: "pointerdown", clientX: sx, clientY: sy, pointerId: 2 });
canvasEl.dispatchEvent({ type: "pointermove", clientX: sx + 50, clientY: sy + 40, pointerId: 2 });
if (T.getState().simSleeping || queuedRaf.length === 0) throw new Error("Drag did not wake Force simulation");
canvasEl.dispatchEvent({ type: "pointerup", clientX: sx + 50, clientY: sy + 40, pointerId: 2 });

// 3. Search pick clears #searchInput and enables multi-hop cycling
elementsById.get("resetBtn").click();
layoutSel.value = "force"; layoutSel.dispatchEvent({ type: "change", target: layoutSel });
elementsById.get("searchInput").value = "governed agentic";
T.handleSearchInput("governed agentic");
elementsById.get("graphSearchDropdown").querySelectorAll("[data-pick-node]")[0].click();
if (T.getState().state.search !== "") throw new Error("Search input was not cleared on pick");
const sp1 = T.getVisibleNodes().length;
hopBtn.click(); const sp2 = T.getVisibleNodes().length;
hopBtn.click(); const sp3 = T.getVisibleNodes().length;
if (!(sp1 < sp2 && sp2 < sp3)) throw new Error("Search-picked node hop growth failed");

// 4. Scope selection focuses SCOPE_DEFAULT_HUB & Bridge-first .type-pill
for (const sc of ["emp_slalom", "policy_guardrails", "projections_layer"]) {
  elementsById.get("resetBtn").click();
  layoutSel.value = "force"; layoutSel.dispatchEvent({ type: "change", target: layoutSel });
  T.setScope(sc);
  const s1 = T.getVisibleNodes(); assertConnected(s1, `scope-${sc}-1`);
  hopBtn.click();
  const s2 = T.getVisibleNodes(); assertConnected(s2, `scope-${sc}-2`);
  if (!(s1.length < s2.length) || minPairDist(s2) <= 12) throw new Error(`Scope ${sc} hop/collision check failed`);
}

elementsById.get("resetBtn").click();
layoutSel.value = "force"; layoutSel.dispatchEvent({ type: "change", target: layoutSel });
T.focusNode("pillar_agentic_ai_platforms");
typePills.find((p) => p.getAttribute("data-type") === "domain").click();
const bf1 = T.getVisibleNodes(); assertConnected(bf1, "bf1");
hopBtn.click();
const bf2 = T.getVisibleNodes(); assertConnected(bf2, "bf2");
if (!(bf1.length < bf2.length)) throw new Error("Bridge-first type-pill check failed");
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [node_bin, str(harness_js), str(bundle_js), str(portal_js)],
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"Node VM explorer verification failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_centralized_graph_quality_and_firewall_gate_plugin_and_standalone(tmp_path: Path) -> None:
    """Verify export gate receipt, plugin + standalone parity, and fail-closed cross-repo firewall on port 8081."""
    receipt = export_interactive_knowledge_graph(output_dir=tmp_path)
    assert receipt["quality_gate_passed"] is True
    assert receipt["quality_gate_profile"] == "port_8081"
    c1, c2, c3, c_off = receipt["vm_hop_counts"]
    assert 0 < c1 < c2 < c3 <= c_off

    exported_html = Path(receipt["output_html"])
    plugin_res = verify_agents_explorer_artifacts(exported_html, force_standalone=False)
    standalone_res = verify_agents_explorer_artifacts(exported_html, force_standalone=True)
    assert plugin_res["passed"] is True, plugin_res["violations"]
    assert standalone_res["passed"] is True, standalone_res["violations"]
    assert plugin_res["vm_metrics"]["counts"] == standalone_res["vm_metrics"]["counts"]
    assert "_standalone_graph_quality_gate" in standalone_res["backend_source"]
    assert len(_standalone_graph_quality_gate.CORE_GOVERNANCE_GRAPH_GATE_SHA256) == 64

    assert verify_gate_main(["--html", str(exported_html)]) == 0
    assert verify_gate_main(["--html", str(exported_html), "--standalone"]) == 0

    clean_html = exported_html.read_text(encoding="utf-8")
    for forbidden in ("127.0.0.1:8080", "127.0.0.1:8082", "NextEra", "v23_nodes", "Long-Goodbye", "Partner Airgap"):
        leaked_res = run_agents_graph_quality_gate(
            clean_html,
            extra_payload_texts=(f'{{"contaminated": "{forbidden}"}}',),
            run_vm=False,
            force_standalone=True,
        )
        assert leaked_res["passed"] is False
        assert any("INV-GRAPH-FIREWALL-ZERO-CROSS-REPO-SPILL" in v and forbidden in v for v in leaked_res["violations"])



