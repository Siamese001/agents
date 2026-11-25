"""Auto-synced standalone model-neutral naming & layer-import linter fallback for CI and public clones."""
from __future__ import annotations

CORE_GOVERNANCE_LINTERS_SHA256 = "8b1a3c5bd91d00f2766f5aeb3fbf80da0f7a6a0a9db91074e244141d9f7e8c0d"

import ast
from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Any, NamedTuple, Sequence

PROHIBITED_PATH_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bgpt[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bastra\b"),
    re.compile(r"(?i)\bluna\b"),
    re.compile(r"(?i)\bterra\b"),
    re.compile(r"(?i)\bsol(?:_medium|_high|-medium|-high)?\b"),
    re.compile(r"(?i)\bclaude[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bgemini[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\bllama[0-9_\-a-z]*\b"),
    re.compile(r"(?i)\b(?:sonnet|haiku|opus)\b"),
    re.compile(r"\b(?:o1|o3)(?:-[a-z0-9]+)?\b"),
    re.compile(r"(?i)\b(?:openai_o1|openai_o3)\b"),
)
AST_MODEL_LITERAL_RE = re.compile(
    r"(?:gpt-[0-9a-z_.-]+|claude-[0-9a-z_.-]+|gemini-[0-9a-z_.-]+|\bo[134]-[0-9a-z_.-]+|"
    r"text-embedding-[0-9a-z_.-]+|BAAI/[0-9a-z_.-]+|qwen[0-9a-z_.-]*|llama[0-9a-z_.-]*|mistral[0-9a-z_.-]*)",
    re.IGNORECASE,
)
MODEL_GUARDIAN_RE = re.compile(
    r"#\s*(?:guardian|ssot):\s*(?:allow-(?:model-literal|model-id|model)\s*--\s*.+|exempt\s*\(\s*HARDCODED_MODEL_LITERAL\s*\))",
    re.IGNORECASE,
)
LAYER_GUARDIAN_RE = re.compile(r"#\s*guardian:\s*allow-layer-violation\s*--\s*(.+)", re.IGNORECASE)
DEFAULT_EXEMPT_PATH_REGEXES: tuple[str, ...] = (
    r"^\.git/", r"^\.venv/", r"(?:^|/)__pycache__/", r"(?:^|/)\.pytest_cache/",
    r"^\.agents/", r"^archive/", r"^scratch/",
)
DEFAULT_FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "tests", "fixtures", "archive", "archives", "docs", "pytest", "unittest.mock",
)

class NamingViolation(NamedTuple):
    file_path: str
    matched_token: str
    detail: str

class LayerViolation(NamedTuple):
    file_path: str
    line_number: int
    imported_module: str
    rule: str
    detail: str

def _compile_patterns(raw_patterns: Sequence[str | re.Pattern[str]]) -> list[re.Pattern[str]]:
    return [p if isinstance(p, re.Pattern) else re.compile(p) for p in raw_patterns]

def _find_subpath_model_tokens(subpath: str) -> list[tuple[str, str]]:
    norm = subpath.replace("\\", "/")
    stem_and_ext = Path(norm).name
    tokens = [t for t in re.split(r"[/\\._\-]+", norm) if t]
    hits: list[tuple[str, str]] = []
    for pat in PROHIBITED_PATH_MODEL_PATTERNS:
        m = pat.search(stem_and_ext)
        if m:
            hits.append((m.group(0), f"Filename '{stem_and_ext}' contains prohibited model identifier '{m.group(0)}'."))
            continue
        for tok in tokens:
            tm = pat.fullmatch(tok)
            if tm:
                hits.append((tm.group(0), f"Path component '{tok}' contains prohibited model identifier '{tm.group(0)}'."))
                break
    return hits

def is_model_path_exempt(
    rel_path: str,
    *,
    exempt_patterns: Sequence[str | re.Pattern[str]] = DEFAULT_EXEMPT_PATH_REGEXES,
    exempt_package_prefixes: Sequence[str] = (),
) -> bool:
    norm = rel_path.replace("\\", "/")
    if any(p.search(norm) for p in _compile_patterns(exempt_patterns)):
        return True
    for prefix_pat in exempt_package_prefixes:
        if re.search(f"{prefix_pat}(?:\\.py)?$", norm):
            return True
        m = re.match(f"{prefix_pat}/(.+)$", norm)
        if m and not _find_subpath_model_tokens(m.group(1)):
            return True
    return False

def scan_path_for_model_tokens(
    rel_path: str,
    *,
    exempt_patterns: Sequence[str | re.Pattern[str]] = DEFAULT_EXEMPT_PATH_REGEXES,
    exempt_package_prefixes: Sequence[str] = (),
) -> list[NamingViolation]:
    norm = re.sub(r"^(?:.*/)?\.worktrees/[^/]+/", "", rel_path.replace("\\", "/"))
    if is_model_path_exempt(norm, exempt_patterns=exempt_patterns, exempt_package_prefixes=exempt_package_prefixes):
        return []
    return [NamingViolation(rel_path, tok, detail) for tok, detail in _find_subpath_model_tokens(norm)]

def _is_catalog_file(file_path: Path, repo_root: Path, catalog_files: Sequence[str]) -> bool:
    if any(file_path.name == b or file_path.name.endswith(b) for b in catalog_files):
        return True
    stems = {Path(b).stem for b in catalog_files}
    try:
        rel_parts = file_path.resolve().relative_to(repo_root.resolve()).parts[:-1]
    except ValueError:
        rel_parts = file_path.parts[:-1]
    return any(part in stems for part in rel_parts)

def check_file_model_neutrality(
    file_path: Path,
    repo_root: Path,
    *,
    production_dirs: Sequence[str],
    excluded_dirs: Sequence[str] = ("tests", "fixtures", "docs", "artifacts", "scratch", ".git", ".venv"),
    exempt_patterns: Sequence[str | re.Pattern[str]] = DEFAULT_EXEMPT_PATH_REGEXES,
    exempt_package_prefixes: Sequence[str] = (),
    catalog_files: Sequence[str] = ("core_model_catalog.py",),
    tree: ast.AST | None = None,
    lines: list[str] | None = None,
) -> list[tuple[int, str, str]]:
    if not file_path.exists():
        return []
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return []
    if any(exc in rel.split("/") for exc in excluded_dirs):
        return []
    if production_dirs and not any(rel == pd or rel.startswith(f"{pd}/") for pd in production_dirs):
        return []
    violations: list[tuple[int, str, str]] = [
        (1, file_path.name, v.detail)
        for v in scan_path_for_model_tokens(rel, exempt_patterns=exempt_patterns, exempt_package_prefixes=exempt_package_prefixes)
    ]
    if _is_catalog_file(file_path, repo_root, catalog_files):
        return violations
    src_lines = lines if lines is not None else file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed = tree
    if parsed is None:
        try:
            parsed = ast.parse("\n".join(src_lines), filename=str(file_path))
        except SyntaxError:
            return violations
    doc_ids = {
        id(n.body[0].value)
        for n in ast.walk(parsed)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
    }
    for n in ast.walk(parsed):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc_ids:
            m = AST_MODEL_LITERAL_RE.search(n.value.strip())
            if m:
                ln = src_lines[n.lineno - 1] if 1 <= n.lineno <= len(src_lines) else ""
                if not MODEL_GUARDIAN_RE.search(ln):
                    violations.append((n.lineno, m.group(0), f"Hardcoded model literal '{m.group(0)}' found in '{n.value.strip()}'."))
    return violations

def evaluate_model_ratchet(
    violations: Sequence[tuple[str, int, str, str]],
    baseline_path: Path,
) -> tuple[bool, list[str]]:
    if not baseline_path.is_file():
        return False, [f"Baseline file not found: {baseline_path}"]
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    base_counts: dict[str, int] = data.get("file_counts", {})
    base_total = int(data.get("total_violations", 0))
    cur_counts: dict[str, int] = {}
    for rel, *_ in violations:
        cur_counts[rel] = cur_counts.get(rel, 0) + 1
    regs: list[str] = []
    for rel, cnt in cur_counts.items():
        b = base_counts.get(rel, 0)
        if b == 0:
            regs.append(f"New file introduced with model literals: {rel} ({cnt} violations)")
        elif cnt > b:
            regs.append(f"Model literal count increased in {rel}: {cnt} > {b}")
    if len(violations) > base_total:
        regs.append(f"Total model literal violations increased: {len(violations)} > {base_total}")
    return len(regs) == 0, regs

def check_forbidden_production_imports(
    file_path: Path,
    repo_root: Path,
    *,
    production_dirs: Sequence[str],
    non_production_dirs: Sequence[str] = ("tests", "fixtures", "docs", "artifacts", "scratch", ".git", ".venv"),
    forbidden_prefixes: Sequence[str] = DEFAULT_FORBIDDEN_IMPORTS,
    tree: ast.AST | None = None,
    lines: list[str] | None = None,
) -> list[tuple[int, str, str]]:
    if not file_path.exists():
        return []
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return []
    if any(rel == np or rel.startswith(f"{np}/") or f"/{np}/" in rel for np in non_production_dirs):
        return []
    if "/tests/" in rel or rel.endswith("_test.py") or Path(rel).name.startswith("test_"):
        return []
    if production_dirs and not any(rel == pd or rel.startswith(f"{pd}/") for pd in production_dirs):
        return []
    src_lines = lines if lines is not None else file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed = tree
    if parsed is None:
        try:
            parsed = ast.parse("\n".join(src_lines), filename=str(file_path))
        except SyntaxError:
            return []
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(parsed):
        targets: list[tuple[str, int]] = []
        if isinstance(node, ast.Import):
            targets.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.append((node.module, node.lineno))
        for mod_name, lineno in targets:
            head = mod_name.split(".")[0]
            if mod_name in forbidden_prefixes or head in forbidden_prefixes or any(mod_name.startswith(f"{p}.") for p in forbidden_prefixes):
                ln = src_lines[lineno - 1] if 1 <= lineno <= len(src_lines) else ""
                if not LAYER_GUARDIAN_RE.search(ln):
                    out.append((lineno, mod_name, f"Production code imports forbidden non-production/testing module '{mod_name}'."))
    return out

def find_import_cycles_tarjan(adj: dict[str, set[str]]) -> list[list[str]]:
    """Detect strongly connected components with size > 1 (or self-loops) via Tarjan's algorithm."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    cycles: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(adj.get(v, ())):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1 or (len(scc) == 1 and v in adj.get(v, ())):
                cycles.append(list(reversed(scc)))

    for node in sorted(adj):
        if node not in indices:
            strongconnect(node)
    return cycles

def check_numeric_layer_dag(
    module_layers: dict[str, int],
    module_imports: dict[str, list[tuple[int, str, bool]]],
) -> list[LayerViolation]:
    """Verify downward-only imports (`source_layer >= target_layer`) across top-level and unguarded imports."""
    violations: list[LayerViolation] = []
    adj: dict[str, set[str]] = defaultdict(set)
    for src_mod, imports in sorted(module_imports.items()):
        src_layer = module_layers.get(src_mod)
        for lineno, dst_mod, is_guarded_lazy in imports:
            if not is_guarded_lazy and dst_mod in module_layers:
                adj[src_mod].add(dst_mod)
            dst_layer = module_layers.get(dst_mod)
            if src_layer is not None and dst_layer is not None and src_layer < dst_layer and not is_guarded_lazy:
                violations.append(
                    LayerViolation(
                        src_mod,
                        lineno,
                        dst_mod,
                        "UPWARD_LAYER_IMPORT",
                        f"Lower layer L{src_layer} ('{src_mod}') must not import higher layer L{dst_layer} ('{dst_mod}').",
                    )
                )
    for cyc in find_import_cycles_tarjan(adj):
        head = cyc[0]
        violations.append(
            LayerViolation(head, 1, " -> ".join([*cyc, head]), "CIRCULAR_IMPORT", f"Circular top-level import cycle: {' -> '.join([*cyc, head])}")
        )
    return violations
