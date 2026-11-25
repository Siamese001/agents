"""Auto-synced standalone wave-plan validator fallback for CI and public clones."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Sequence

CORE_GOVERNANCE_PLAN_VALIDATOR_SHA256 = "c26e78982b9837972a864167685d14f388c86d246866d816b748fd197c84b8e2"

RE_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
RE_WAVE_HEADER = re.compile(r"^(#{2,3})\s+Wave\s+(\d+)([A-Z]{0,2})(?:[:\s\-]+(.*))?$", re.IGNORECASE)
RE_OBJECTIVE = re.compile(r"(?:^#{3,4}\s+.*(?:objective|scope).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:objective|scope).*?)\*\*)", re.IGNORECASE)
RE_MILESTONES = re.compile(r"(?:^#{3,4}\s+.*(?:milestone|deliverable).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:milestone|deliverable).*?)\*\*)", re.IGNORECASE)
RE_CRITERIA = re.compile(r"(?:^#{3,4}\s+.*(?:acceptance\s+criteria|criteria).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:acceptance\s+criteria|criteria).*?)\*\*)", re.IGNORECASE)
RE_RECEIPT_GATE = re.compile(r"(?:^#{3,4}\s+.*(?:receipt|completion\s+gate|exit\s+gate|verification).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:receipt|completion\s+gate|exit\s+gate|verification).*?)\*\*)", re.IGNORECASE)
RE_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")
RE_DEPENDS_ON = re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Depends\s+On(?:\*\*)?\s*:\s*(.+)$", re.IGNORECASE)
RE_WAVE_DAG_ID = re.compile(r"^(\d+)([A-Z]{0,2})$", re.IGNORECASE)
RE_SHARD_MANIFEST = re.compile(r"```(?:yaml|json)\s+shard-manifest\s*\n([\s\S]*?)```", re.IGNORECASE)
RE_FENCED_CODE = re.compile(r"```[\s\S]*?```")
RE_HITL_TABLE_HDR = re.compile(r"^\s*\|.*?\b(?:Decision|Candidate\s+ID)\b.*?\|.*?\b(?:Options|Confidence|Handling|\u0394|Delta)\b.*?\|", re.IGNORECASE)
GATE_FIELDS: dict[str, re.Pattern[str]] = {
    "Run": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?Run(?:\*\*)?\s*:", re.IGNORECASE),
    "Input": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?Input(?:\*\*)?\s*:", re.IGNORECASE),
    "Expected": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?Expected(?:\*\*)?\s*:", re.IGNORECASE),
    "Verify independently": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?(?:Verify independently|Independent check)(?:\*\*)?\s*:", re.IGNORECASE),
    "Fail if": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?Fail if(?:\*\*)?\s*:", re.IGNORECASE),
    "Record": re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?Record(?:\*\*)?\s*:", re.IGNORECASE),
}
JUDGE_DELIVERABLE_RE = re.compile(
    r"\b(?:llm[\s-]+as[\s-]+a?[\s-]*judge|multi[\s-]*model[\s-]+judge|blind[\s-]+(?:visual|multimodal|audience|subagent)[\s-]+judge)\b",
    re.IGNORECASE,
)
JUDGE_PROOF_TOKENS: tuple[str, ...] = (
    "fail closed", "fail-closed", "judge-receipt", "judge_receipt",
    "missing receipt", "tamper", "exits 1", "exit code 1", "non-zero",
    "hash-bound", "artifact_sha256",
)
DELIVERABLE_KEYWORDS: tuple[str, ...] = ("deliverable", "milestone", "[new]", "[modify]", "[delete]")

class WaveSection:
    def __init__(self, number: int, shard_suffix: str, title: str, start_line: int, header_level: int = 2):
        self.number = number
        self.shard_suffix = (shard_suffix or "").upper()
        self.wave_id = f"{number}{self.shard_suffix}"
        self.title = title
        self.start_line = start_line
        self.header_level = header_level
        self.lines: list[tuple[int, str]] = []
        self.has_objective = False
        self.has_milestones = False
        self.has_criteria = False
        self.has_receipt_gate = False
        self.deliverable_items: list[str] = []
        self.gate_lines: list[str] = []

    def analyze(self) -> None:
        cur_sub: str | None = None
        for _ln, raw in self.lines:
            s = raw.strip()
            if not s:
                continue
            matched = False
            for name, pat, attr in (
                ("objective", RE_OBJECTIVE, "has_objective"),
                ("milestones", RE_MILESTONES, "has_milestones"),
                ("criteria", RE_CRITERIA, "has_criteria"),
                ("receipt", RE_RECEIPT_GATE, "has_receipt_gate"),
            ):
                if pat.search(s):
                    setattr(self, attr, True)
                    cur_sub = name
                    matched = True
                    break
            if matched:
                continue
            if re.match(r"^#{3,4}\s+", s):
                cur_sub = "other"
                continue
            if cur_sub == "receipt":
                self.gate_lines.append(raw)
            m_item = RE_ITEM.match(s)
            if m_item:
                txt = m_item.group(1).strip()
                if cur_sub == "milestones" or (cur_sub is None and any(k in txt.lower() for k in DELIVERABLE_KEYWORDS)):
                    self.deliverable_items.append(txt)

def extract_waves(content: str) -> list[WaveSection]:
    waves: list[WaveSection] = []
    cur: WaveSection | None = None
    in_fence = False
    for idx, raw in enumerate(content.splitlines(), start=1):
        s = raw.strip()
        if s.startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence:
            m = RE_WAVE_HEADER.match(s)
            if m:
                cur = WaveSection(int(m.group(2)), m.group(3) or "", (m.group(4) or "").strip(), idx, len(m.group(1)))
                waves.append(cur)
                continue
            if cur is not None and s.startswith("#") and (len(s) - len(s.lstrip("#"))) <= cur.header_level:
                cur = None
        if cur is not None:
            cur.lines.append((idx, raw))
    return waves

def _extract_depends_on(wave: WaveSection) -> list[str]:
    deps: list[str] = []
    for _ln, raw in wave.lines:
        m = RE_DEPENDS_ON.match(raw.strip())
        if not m:
            continue
        val = m.group(1).strip()
        if val.lower() in ("none", "n/a", "-", "root"):
            continue
        for part in re.split(r"[,;/]+", val):
            cleaned = re.sub(r"^wave\s+", "", part.strip(), flags=re.IGNORECASE).strip()
            dm = RE_WAVE_DAG_ID.match(cleaned)
            if dm:
                deps.append(f"{int(dm.group(1))}{(dm.group(2) or '').upper()}")
            elif cleaned:
                deps.append(cleaned.upper())
    return deps

def _detect_dag_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                return [*path[path.index(nxt):], nxt]
            if state.get(nxt, 0) == 0:
                cyc = dfs(nxt)
                if cyc:
                    return cyc
        path.pop()
        state[node] = 2
        return None

    for k in graph:
        if state.get(k, 0) == 0:
            res = dfs(k)
            if res:
                return res
    return None

def validate_wave_sequence_and_dag(
    waves: Sequence[WaveSection],
    filename: str,
    *,
    allow_sharded: bool = True,
    max_waves: int = 0,
) -> list[str]:
    errors: list[str] = []
    if not waves:
        return errors
    if waves[0].number not in (0, 1):
        errors.append(f"{filename}: First wave must be numbered Wave 0 or Wave 1 (found Wave {waves[0].wave_id} at line {waves[0].start_line}).")
    seen: set[str] = set()
    by_num: dict[int, list[WaveSection]] = {}
    for idx, w in enumerate(waves):
        if not allow_sharded and w.shard_suffix:
            errors.append(f"{filename}: Line {w.start_line}: Sharded Wave {w.wave_id} is disabled in this repository profile.")
        if idx > 0:
            prev = waves[idx - 1].number
            if w.number not in (prev, prev + 1) or (w.number == prev and not (w.shard_suffix or waves[idx - 1].shard_suffix)):
                errors.append(f"{filename}: Non-sequential wave numbering at line {w.start_line} (expected Wave {prev + 1}, found Wave {w.wave_id}).")
        if w.wave_id in seen:
            errors.append(f"{filename}: Duplicate Wave {w.wave_id} at line {w.start_line}.")
        seen.add(w.wave_id)
        by_num.setdefault(w.number, []).append(w)
    if max_waves > 0 and len(by_num) > max_waves:
        errors.append(f"{filename}: Plan declares {len(by_num)} wave numbers, exceeding repository maximum of {max_waves} waves.")
    for num, group in by_num.items():
        if any(not g.shard_suffix for g in group) and any(bool(g.shard_suffix) for g in group):
            errors.append(f"{filename}: Cannot mix unsharded 'Wave {num}' and sharded 'Wave {num}A/B' at the same wave number.")
    dep_graph: dict[str, list[str]] = {}
    for w in waves:
        deps = _extract_depends_on(w)
        dep_graph[w.wave_id] = deps
        for d in deps:
            if d not in seen:
                errors.append(f"{filename}: Line {w.start_line} (Wave {w.wave_id}): Depends On references unknown Wave '{d}'.")
    cyc = _detect_dag_cycle(dep_graph)
    if cyc:
        errors.append(f"{filename}: Dependency cycle detected in Wave Depends On graph: {' -> '.join(cyc)}.")
    return errors

def count_prose_words(content: str) -> int:
    no_fences = RE_FENCED_CODE.sub(" ", content)
    lines: list[str] = []
    in_table = False
    for ln in no_fences.splitlines():
        if not in_table and RE_HITL_TABLE_HDR.match(ln):
            in_table = True
            continue
        if in_table:
            if ln.strip().startswith("|"):
                continue
            in_table = False
        lines.append(ln)
    return len("\n".join(lines).split())

def compute_scaled_word_cap(
    num_waves: int,
    num_items: int,
    *,
    base_max_words: int = 1500,
    max_scaled_words: int = 3500,
    base_words: int = 400,
    words_per_wave: int = 250,
    words_per_item: int = 25,
) -> int:
    if base_max_words <= 0:
        return 0
    return min(max_scaled_words, max(base_max_words, base_words + words_per_wave * num_waves + words_per_item * num_items))

def validate_plan_content(
    content: str,
    filename: str = "implementation_plan.md",
    *,
    strict: bool = True,
    require_objective: bool = True,
    allow_sharded: bool = True,
    max_waves: int = 0,
    base_max_words: int = 0,
    max_scaled_words: int = 3500,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not RE_TITLE.search(content):
        errors.append(f"{filename}: Missing required top-level title ('# <Plan Title>').")
    waves = extract_waves(content)
    if not waves:
        errors.append(f"{filename}: Implementation plan must be wave-based. Found 0 wave sections ('## Wave <N>').")
        return False, errors
    errors.extend(validate_wave_sequence_and_dag(waves, filename, allow_sharded=allow_sharded, max_waves=max_waves))
    for w in waves:
        w.analyze()
        pfx = f"{filename}: Line {w.start_line} (Wave {w.wave_id})"
        if require_objective and not w.has_objective:
            errors.append(f"{pfx}: Missing required 'Objective & Scope' section.")
        if not w.has_milestones:
            errors.append(f"{pfx}: Missing required 'Milestones & Deliverables' section.")
        elif not w.deliverable_items:
            errors.append(f"{pfx}: 'Milestones & Deliverables' must contain at least one itemized deliverable.")
        if not w.has_criteria:
            errors.append(f"{pfx}: Missing required 'Acceptance Criteria' section.")
        if not w.has_receipt_gate:
            errors.append(f"{pfx}: Missing required 'Runtime Receipt & Completion Gate' section.")
        elif strict:
            present = {lbl for lbl, pat in GATE_FIELDS.items() if any(pat.search(gl) for gl in w.gate_lines)}
            missing = [lbl for lbl in GATE_FIELDS if lbl not in present]
            if missing:
                errors.append(f"{filename}: Wave {w.wave_id} completion gate must specify: {', '.join(missing)}.")
            wave_txt = "\n".join(raw for _, raw in w.lines)
            gate_txt = "\n".join(w.gate_lines).lower()
            if JUDGE_DELIVERABLE_RE.search(wave_txt) and not any(tok in gate_txt for tok in JUDGE_PROOF_TOKENS):
                errors.append(f"{filename}: Wave {w.wave_id} declares an LLM-as-a-Judge deliverable without fail-closed receipt verification proof.")
    if strict and base_max_words > 0:
        cap = compute_scaled_word_cap(len(waves), sum(len(w.deliverable_items) for w in waves), base_max_words=base_max_words, max_scaled_words=max_scaled_words)
        wc = count_prose_words(content)
        if wc > cap:
            errors.append(f"{filename}: Prose word count ({wc}) exceeds scaled wave-plan ceiling ({cap} words).")
    for m_shard in RE_SHARD_MANIFEST.finditer(content):
        body = m_shard.group(1).strip()
        if body.startswith(("{", "[")):
            try:
                parsed = json.loads(body)
                shards = parsed if isinstance(parsed, list) else parsed.get("shards", [])
                if not shards:
                    errors.append(f"{filename}: shard-manifest block must declare at least 1 shard.")
            except Exception as exc:
                errors.append(f"{filename}: Invalid JSON shard-manifest block: {exc}")
    return len(errors) == 0, errors

def load_repo_plan_profile(repo_root: Path) -> dict[str, Any]:
    cand = Path(repo_root) / "config" / "governance" / "linter_profile.json"
    if cand.is_file():
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
            prof = data.get("plan_validator") if isinstance(data, dict) else None
            return prof if isinstance(prof, dict) else {}
        except Exception:
            return {}
    return {}

def validate_plan_file(
    path: Path,
    *,
    repo_root: Path | None = None,
    legacy_exemptions: set[str] | None = None,
    strict: bool = True,
) -> tuple[bool, list[str]]:
    if legacy_exemptions and path.name in legacy_exemptions:
        return True, [f"[EXEMPT] Skipped legacy plan: {path.name}"]
    if not path.is_file():
        return False, [f"File not found: {path}"]
    root = Path(repo_root).resolve() if repo_root else path.resolve().parent
    try:
        rel = path.resolve().relative_to(root)
        if len(rel.parts) == 1 and rel.name == "implementation_plan.md":
            br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True, text=True, check=False, timeout=5).stdout.strip()
            if br == "main":
                return False, ["[SINGLE_PLAN_LOCATION_VIOLATION] Root 'implementation_plan.md' is blocked on main."]
    except Exception:
        pass
    prof = load_repo_plan_profile(root)
    exempt = set(legacy_exemptions or ()) | set(prof.get("legacy_exemptions", ()))
    if path.name in exempt:
        return True, [f"[EXEMPT] Skipped legacy plan: {path.name}"]
    content = path.read_text(encoding="utf-8", errors="replace")
    return validate_plan_content(
        content,
        filename=path.name,
        strict=strict,
        require_objective=bool(prof.get("require_objective", True)),
        allow_sharded=bool(prof.get("allow_sharded", True)),
        max_waves=int(prof.get("max_waves", 0)),
        base_max_words=int(prof.get("base_max_words", 0)),
        max_scaled_words=int(prof.get("max_scaled_words", 3500)),
    )

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Centralized wave-based implementation plan validator.")
    parser.add_argument("--file", type=Path, help="Plan file to validate.")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root for profile lookup.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if not args.file:
        parser.error("--file is required")
    ok, errs = validate_plan_file(args.file, repo_root=args.repo_root.resolve(), strict=True)
    if not ok:
        for e in errs:
            print(f"  - {e}")
        return 1
    if not args.quiet:
        print(f"[PASS] {args.file.name}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
