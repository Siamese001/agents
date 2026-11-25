"""Auto-synced standalone security, purity & commit linter fallback for CI and public clones."""
from __future__ import annotations

CORE_GOVERNANCE_LINTERS_SHA256 = "8b1a3c5bd91d00f2766f5aeb3fbf80da0f7a6a0a9db91074e244141d9f7e8c0d"

import ast
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, NamedTuple, Sequence

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Private Key", re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9_\-]{20,}\b")),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[a-zA-Z0-9_-]{20,}\b")),
    ("GitHub Personal Access Token", re.compile(r"\bghp_[a-zA-Z0-9]{36}\b")),
    ("GitHub Fine-Grained Token", re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{50,}\b")),
    ("Notion API Token", re.compile(r"\b(?:ntn_[0-9A-Za-z]{40,}|secret_[0-9A-Za-z]{43})\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{24,}\b")),
    ("Hardcoded Bearer Token", re.compile(r"""(?i)authorization['"]?\s*[:=]\s*['"]bearer\s+([a-zA-Z0-9_\-\.]{24,})['"]""")),
    ("Generic High-Entropy Secret", re.compile(r"""(?i)(?:api_key|apikey|secret_key|auth_token|access_token)\s*=\s*['"]([a-zA-Z0-9_\-]{24,})['"]""")),
)
DEFAULT_SENSITIVE_ENV_VARS: frozenset[str] = frozenset({
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GITHUB_TOKEN", "GH_TOKEN", "HF_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
})
DEFAULT_ALLOWED_SSOT_FILES: frozenset[str] = frozenset({
    "storage/credentials.py", "storage/connection.py", "config/credentials.py",
    "config/secret_providers.py", "config/paths.py", "dual_pipeline/credentials.py",
})
DEFAULT_FORBIDDEN_ENV_FILES: tuple[str, ...] = (".env", ".env.local", "env_di", "env_agents")
DUMMY_MARKERS: tuple[str, ...] = (
    "example", "dummy", "placeholder", "mock", "fake", "xxx", "<your_", "your-api-key",
    "redacted", "sk-test-", "sk_test_", "sk-ant-test", "-test-", "_test_",
    "test_key", "test-key", "test_token", "test-token", "testsecret", "testapikey",
)
FAST_TRIGGERS: tuple[str, ...] = (
    "private key", "akia", "aiza", "sk-", "ghp_", "github_pat_", "ntn_",
    "secret_", "xox", "bearer ", "api_key", "apikey", "secret_key", "auth_token", "access_token",
)
FORBIDDEN_FIXTURE_PATHS: tuple[str, ...] = (
    "fixtures/", "/fixtures/", "golden/", "/golden/", "expected_outputs/",
    "/expected_outputs/", "benchmark_references/", "tests/fixtures", "data/eval/golden",
)
FORBIDDEN_FIXTURE_MODULES: frozenset[str] = frozenset({"fixtures", "tests", "golden", "expected_outputs"})
PREDETERMINED_KEYS: frozenset[str] = frozenset({
    "executive_summary", "final_summary", "synthesis", "extracted_insights",
    "pinned_eval", "pinned_evals", "golden_answer", "expected_output",
    "result_payload", "summary_payload", "f2_text", "f3_data",
})
PURITY_GUARDIAN_RE = re.compile(r"#\s*guardian:\s*allow-(?:purity|fixture|golden|layer-violation)\s*--\s*(.+)", re.IGNORECASE)
CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\((?P<scope>[a-zA-Z0-9_\-\./]+)\))?(?P<breaking>!)?: (?P<description>.+)$"
)
MERGE_COMMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Merge branch '[^']+'(\s+into\s+[^\s]+)?(\s+\([^\)]+\))?.*$", re.IGNORECASE),
    re.compile(r"^Merge remote-tracking branch '[^']+'.*$", re.IGNORECASE),
    re.compile(r"^Merge pull request #\d+.*$", re.IGNORECASE),
    re.compile(r"^merge:\s+.+$", re.IGNORECASE),
)
DIRTY_DUMP_RE = re.compile(
    r"(?i)(?:^(?:dirty|wip|temp|tmp|stash)(?:\s+(?:dump|commit|save|files|wip))?$|\b(?:temp dump|save files|save changes|checkpoint dump|dirty files)\b)"
)
COMMIT_MODEL_RE = re.compile(
    r"(?i)(?<!\.)\b(gpt-?[0-9a-z]*|astra|sol[-_](?:max|medium|high)|luna|terra|claude[-_0-9a-z]*|gemini[-_][0-9a-z]+|llama[-_0-9a-z]*)\b"
)

class LeakViolation(NamedTuple):
    file_path: str
    line_number: int
    leak_type: str
    detail: str

def load_repo_linter_profile(repo_root: Path) -> dict[str, Any]:
    cand = Path(repo_root) / "config" / "governance" / "linter_profile.json"
    if cand.is_file():
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

def is_shannon_entropy_high(token: str, threshold: float = 3.5) -> bool:
    if not token or len(token) < 16:
        return False
    freq: dict[str, int] = {}
    for ch in token:
        freq[ch] = freq.get(ch, 0) + 1
    ent = -sum((cnt / len(token)) * math.log2(cnt / len(token)) for cnt in freq.values())
    return ent >= threshold

def _is_dummy_secret(val: str) -> bool:
    low = val.lower()
    return any(m in low for m in DUMMY_MARKERS)

class CredentialEnvAstVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, sensitive_vars: set[str]):
        self.rel_path = rel_path
        self.sensitive_vars = sensitive_vars
        self.violations: list[LeakViolation] = []

    def visit_Call(self, node: ast.Call) -> None:
        fn = ""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "environ" and node.func.attr == "get":
                fn = "os.environ.get"
            elif isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "getenv":
                fn = "os.getenv"
        elif isinstance(node.func, ast.Name) and node.func.id == "getenv":
            fn = "getenv"
        if fn and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            var = node.args[0].value
            if var in self.sensitive_vars:
                self.violations.append(
                    LeakViolation(self.rel_path, node.lineno, "DIRECT_ENV_SECRET_READ", f"Direct call {fn}('{var}') prohibited; use CredentialManager.")
                )
        self.generic_visit(node)

def check_file_for_secrets(
    file_path: Path,
    repo_root: Path,
    *,
    explicitly_targeted: bool = False,
    forbidden_env_files: Sequence[str] = DEFAULT_FORBIDDEN_ENV_FILES,
    excluded_dir_parts: Sequence[str] = (".git", ".venv", ".worktrees", "artifacts", "docs/archive", "fixtures"),
    excluded_filenames: Sequence[str] = (".env.example", "uv.lock", "poetry.lock", "package-lock.json"),
) -> list[tuple[int, str, str]]:
    if explicitly_targeted and (file_path.name in forbidden_env_files or (file_path.name.startswith(".env.") and file_path.name != ".env.example")):
        return [(1, "Forbidden Environment Credential File", f"Sensitive credential file '{file_path.name}' must never be staged or committed.")]
    if not file_path.exists() or file_path.is_dir() or file_path.name in excluded_filenames:
        return []
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = file_path.as_posix()
    if any(part in rel.split("/") or rel.startswith(f"{part}/") for part in excluded_dir_parts):
        return []
    if not explicitly_targeted and (file_path.name in forbidden_env_files or file_path.name.startswith(".env.")):
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not any(t in content.lower() for t in FAST_TRIGGERS):
        return []
    out: list[tuple[int, str, str]] = []
    for idx, line in enumerate(content.splitlines(), start=1):
        if "# allow-secret" in line or "# pragma: allow-secret" in line or "guardian: allow-secret" in line:
            continue
        low = line.lower()
        if not any(t in low for t in FAST_TRIGGERS):
            continue
        for sname, pat in SECRET_PATTERNS:
            m = pat.search(line)
            if not m or _is_dummy_secret(m.group(0)):
                continue
            if sname in ("Generic High-Entropy Secret", "Hardcoded Bearer Token"):
                tok = m.group(1) if m.groups() else m.group(0)
                if _is_dummy_secret(tok) or not is_shannon_entropy_high(tok):
                    continue
            raw = m.group(0)
            red = raw[:4] + "..." + raw[-4:] if len(raw) > 8 else "***"
            out.append((idx, sname, f"Potential {sname} detected: {red}"))
    return out

def scan_credential_isolation_file(
    file_path: Path,
    repo_root: Path,
    *,
    allowed_ssot_files: set[str] | None = None,
    sensitive_env_vars: set[str] | None = None,
    team_facing_prefixes: Sequence[str] = (),
    career_patterns: Sequence[re.Pattern[str]] = (),
) -> list[LeakViolation]:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = file_path.as_posix()
    ssot = allowed_ssot_files if allowed_ssot_files is not None else set(DEFAULT_ALLOWED_SSOT_FILES)
    if "tests/" in rel or "test_" in rel or "evals/" in rel or rel in ssot:
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    violations: list[LeakViolation] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        if not line.strip().startswith("#"):
            for sname, pat in SECRET_PATTERNS[1:4]:
                if pat.search(line) and not _is_dummy_secret(line):
                    violations.append(LeakViolation(rel, line_no, "HARDCODED_SECRET_TOKEN", f"Potential hardcoded credential token ({sname}) detected"))
        if team_facing_prefixes and any(rel.startswith(pfx) for pfx in team_facing_prefixes) and "INTERNAL_ADVISORY" not in rel:
            for c_pat in career_patterns:
                if c_pat.search(line):
                    violations.append(LeakViolation(rel, line_no, "CAREER_FIREWALL_LEAK", f"Personal career leverage token in team deliverable: '{c_pat.pattern}'"))
    if file_path.suffix == ".py":
        try:
            visitor = CredentialEnvAstVisitor(rel, sensitive_env_vars or set(DEFAULT_SENSITIVE_ENV_VARS))
            visitor.visit(ast.parse(content, filename=str(file_path)))
            violations.extend(visitor.violations)
        except SyntaxError:
            pass
    return violations

def _is_prompt_template(s: str, target_name: str = "") -> bool:
    if any(k in target_name.lower() for k in ("prompt", "template", "instruction", "system_msg", "rubric")):
        return True
    if not s.lstrip().startswith("{") and re.search(r"\{[A-Za-z_][A-Za-z0-9_.]*\}|\$\{[A-Za-z0-9_]+\}|\$[A-Za-z_][A-Za-z0-9_]*", s):
        return True
    low = s.lower()
    return any(kw in low for kw in ("you are ", "instructions:", "prompt:", "guidelines:", "system:", "assistant:", "never introduce"))

class ProductionPurityAstVisitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]):
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []
        self._doc_lines: set[int] = set()

    def _exempt(self, lineno: int) -> bool:
        return 1 <= lineno <= len(self.lines) and bool(PURITY_GUARDIAN_RE.search(self.lines[lineno - 1]))

    def _mark_doc(self, body: list[ast.stmt]) -> None:
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            self._doc_lines.add(body[0].value.lineno)

    def visit_Module(self, node: ast.Module) -> None:
        self._mark_doc(node.body)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._mark_doc(node.body)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in FORBIDDEN_FIXTURE_MODULES and not self._exempt(node.lineno):
                self.violations.append((node.lineno, alias.name, f"Production code imports forbidden fixture/test module '{alias.name}'."))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.split(".")[0] in FORBIDDEN_FIXTURE_MODULES and not self._exempt(node.lineno):
            self.violations.append((node.lineno, node.module, f"Production code imports from forbidden fixture/test module '{node.module}'."))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if node.lineno not in self._doc_lines and not self._exempt(node.lineno):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for tname in names:
                low = tname.lower()
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    s = node.value.value
                    if any(fp in s for fp in FORBIDDEN_FIXTURE_PATHS):
                        self.violations.append((node.lineno, tname, f"Production variable '{tname}' binds forbidden fixture path '{s}'."))
                    elif low in PREDETERMINED_KEYS and len(s.strip()) > 80 and not _is_prompt_template(s, tname):
                        self.violations.append((node.lineno, tname, f"Variable '{tname}' contains hardcoded predetermined domain text ({len(s)} chars)."))
                elif isinstance(node.value, ast.Dict) and self._is_static_domain_dict(node.value):
                    self.violations.append((node.lineno, tname, f"Variable '{tname}' contains precomputed domain payload substituting for runtime generation."))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not self._exempt(node.lineno):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and any(fp in arg.value for fp in FORBIDDEN_FIXTURE_PATHS):
                    self.violations.append((node.lineno, arg.value, f"Production code loads fixture/golden artifact '{arg.value}'."))
        self.generic_visit(node)

    @staticmethod
    def _is_static_domain_dict(node: ast.Dict) -> bool:
        keys, consts, long_strs = [], 0, 0
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.append(k.value.lower())
                if isinstance(v, ast.Constant):
                    consts += 1
                    if isinstance(v.value, str) and len(v.value) > 60 and not _is_prompt_template(v.value):
                        long_strs += 1
                elif isinstance(v, (ast.List, ast.Dict)) and all(isinstance(e, ast.Constant) for e in getattr(v, "elts", [])):
                    consts += 1
        return consts >= 2 and any(k in keys for k in ("nodes", "edges", "executive_summary", "synthesis", "verdict", "final_summary", "result_payload")) and (long_strs >= 1 or consts >= 3)

def check_ast_production_purity(
    file_path: Path,
    repo_root: Path,
    *,
    production_dirs: Sequence[str],
    excluded_dirs: Sequence[str] = ("tests", "fixtures", "apps_eval", "docs", "artifacts", "scratch", ".git", ".venv"),
) -> list[tuple[int, str, str]]:
    if not file_path.exists():
        return []
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return []
    if any(exc in rel.split("/") or rel.startswith(f"{exc}/") for exc in excluded_dirs):
        return []
    if "/tests/" in rel or rel.endswith("_test.py") or Path(rel).name.startswith("test_"):
        return []
    if production_dirs and not any(rel == pd or rel.startswith(f"{pd}/") for pd in production_dirs):
        return []
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        tree = ast.parse("\n".join(lines), filename=str(file_path))
    except SyntaxError:
        return []
    visitor = ProductionPurityAstVisitor(lines)
    visitor.visit(tree)
    return visitor.violations

def lint_staged_worktrees(repo_root: Path, files: Sequence[str] | None = None) -> list[str]:
    found: list[str] = []
    candidates = list(files or [])
    try:
        res = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repo_root, capture_output=True, text=True, check=False, timeout=5)
        candidates.extend(res.stdout.splitlines())
    except Exception:
        pass
    for raw in candidates:
        norm = raw.strip().replace("\\", "/").removeprefix("./")
        if norm == ".worktrees" or norm.startswith(".worktrees/"):
            msg = f"[WORKTREE STAGING VIOLATION] Staging worktree path '{norm}' in repository is strictly prohibited."
            if msg not in found:
                found.append(msg)
    return found

def validate_commit_message(msg: str, *, check_model_neutral: bool = True) -> tuple[bool, str]:
    clean = [ln for ln in msg.splitlines() if not ln.strip().startswith("#")]
    if not clean or not clean[0].strip():
        return False, "Commit message summary line cannot be empty."
    first = clean[0].strip()
    for pat in MERGE_COMMIT_PATTERNS:
        if pat.match(first):
            tail = re.sub(r"^Merge (?:branch|remote-tracking branch) '[^']+'", "", first)
            if check_model_neutral and (mm := COMMIT_MODEL_RE.search(tail)):
                return False, f"Prohibited model identifier '{mm.group(0)}' in merge commit message."
            return True, f"Valid merge commit format: '{first}'"
    if dm := DIRTY_DUMP_RE.search(first):
        return False, f"Prohibited dirty-dump keyword '{dm.group(0)}' in commit message."
    if check_model_neutral and (mm := COMMIT_MODEL_RE.search(first)):
        return False, f"Prohibited model identifier '{mm.group(0)}' in commit message."
    m = CONVENTIONAL_COMMIT_RE.match(first)
    if not m:
        return False, f"Invalid commit message header: '{first}'. Expected '<type>(<scope>): <subject>'."
    desc = m.group("description").strip()
    if len(desc) < 3:
        return False, f"Description '{desc}' is too short (minimum 3 characters required)."
    return True, f"Valid Conventional Commit: '{first}'"
