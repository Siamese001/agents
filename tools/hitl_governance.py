#!/usr/bin/env python3
"""HITL Governance and Ambiguity Gating Engine (20% margin, 65% floor, 300/250-char caps, zero-jargon)."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any, Sequence

DEFAULT_AMBIGUITY_THRESHOLD: float = 0.20
DEFAULT_MIN_CONFIDENCE_FLOOR: float = 0.65
MAX_QUESTION_LENGTH: int = 300
MAX_OPTION_LENGTH: int = 250
DEFAULT_STORE_PATH = Path("artifacts/governance/hitl_decisions.sqlite")


def _resolve_default_store_path() -> Path:
    """Resolve persistent HITL store in primary git repository root so history survives worktree cleanup."""
    env_override = os.environ.get("HITL_STORE_PATH")
    if env_override:
        return Path(env_override).resolve()
    repo_dir = Path(__file__).resolve().parents[1]
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=False, shell=False, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            common_raw = Path(proc.stdout.strip())
            common_dir = (common_raw if common_raw.is_absolute() else (repo_dir / common_raw)).resolve()
            if common_dir.name == ".git":
                return (common_dir.parent / DEFAULT_STORE_PATH).resolve()
    except (OSError, subprocess.SubprocessError):  # guardian: allow-silent-swallow -- fallback to local repo path if git is unavailable
        pass
    return (repo_dir / DEFAULT_STORE_PATH).resolve()


AUTHENTIC_USER_ARTIFACT_APPROVAL_MARKERS = (
    "automatically approved the artifact through their review policy",
    "user has automatically approved the artifact",
    "the user has approved the artifact",
)
SYNTHETIC_APPROVAL_MARKERS = (
    "autonomous policy supervisor",
    "stop_hook_auto_proceed",
    "user pre-approved this wave in preferences",
    "pre-approved by supervisor",
    "unauthorized autonomous approval",
    "rogue supervisor auto-proceed",
)


def parse_confidence_score(val: Any) -> float:
    """Robustly parse confidence score into a 0.0 - 1.0 float."""
    if isinstance(val, (int, float)):
        num = float(val)
        return num / 100.0 if num > 1.0 else max(0.0, min(1.0, num))
    if isinstance(val, dict):
        for k in ("calibrated_confidence", "confidence_score", "confidence", "confidence_level"):
            if k in val:
                return parse_confidence_score(val[k])
    if isinstance(val, str):
        cleaned = val.strip()
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", cleaned)
        if pct_match:
            return float(pct_match.group(1)) / 100.0
        upper = cleaned.upper()
        if "HIGH" in upper:
            return 0.88
        if "MEDIUM" in upper:
            return 0.62
        if "LOW" in upper:
            return 0.35
        num_match = re.search(r"\b(0(?:\.\d+)?|1(?:\.0+)?)\b", cleaned)
        if num_match:
            return float(num_match.group(1))
    return 0.50


def calculate_calibrated_confidence(
    option: Any,
    category: str | None = None,
    evidence_refs: Sequence[str] | None = None,
    has_verification_receipt: bool = False,
    risk_level: str = "LOW",
    is_irreversible: bool = False,
    blast_radius_layers: int = 1,
    store: HITLDecisionStore | None = None,
) -> float:
    """Calculate multi-factor calibrated confidence: clamp(C_base + E_evidence - R_risk + L_learning, 0.05, 0.99)."""
    base = parse_confidence_score(option)
    opt_label = ""
    if isinstance(option, dict):
        opt_label = option.get("label", option.get("title", option.get("name", "")))
        if not evidence_refs and "evidence_refs" in option:
            evidence_refs = option["evidence_refs"]
        if not has_verification_receipt and "has_verification_receipt" in option:
            has_verification_receipt = bool(option["has_verification_receipt"])
        if risk_level == "LOW" and "risk_level" in option:
            risk_level = str(option["risk_level"])
        if not is_irreversible and "is_irreversible" in option:
            is_irreversible = bool(option["is_irreversible"])
        if blast_radius_layers == 1 and "blast_radius_layers" in option:
            blast_radius_layers = int(option["blast_radius_layers"])
        if not category and "category" in option:
            category = str(option["category"])
    elif isinstance(option, str):
        opt_label = option

    evidence_boost = (min(len(evidence_refs) * 0.03, 0.09) if evidence_refs else 0.0) + (0.05 if has_verification_receipt else 0.0)
    risk_map = {"MEDIUM": 0.04, "HIGH": 0.08, "CRITICAL": 0.15}
    risk_penalty = risk_map.get(str(risk_level).upper(), 0.0) + (0.08 if is_irreversible else 0.0)
    if blast_radius_layers > 1:
        risk_penalty += min((blast_radius_layers - 1) * 0.03, 0.09)
    learning_factor = store.query_learning_adjustment(category, opt_label) if (store and category) else 0.0
    return round(max(0.05, min(0.99, base + evidence_boost - risk_penalty + learning_factor)), 4)


class HITLDecisionStore:
    """Thread-safe persistent SQLite store for HITL decisions and system learning."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path).resolve() if db_path is not None else _resolve_default_store_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS hitl_decisions ("
                "decision_id TEXT PRIMARY KEY, task_id TEXT, category TEXT, context_summary TEXT, "
                "context_hash TEXT, options_json TEXT, selected_option TEXT, operator_action TEXT, "
                "margin REAL, calibrated_confidence REAL, outcome TEXT DEFAULT 'PENDING', "
                "created_at TEXT, updated_at TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS learning_aggregates ("
                "category TEXT PRIMARY KEY, total_decisions INTEGER DEFAULT 0, "
                "autonomous_proceeds INTEGER DEFAULT 0, human_approvals INTEGER DEFAULT 0, "
                "human_overrides INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0, "
                "failure_count INTEGER DEFAULT 0, mean_margin REAL DEFAULT 0.0, "
                "learning_factor REAL DEFAULT 0.0, updated_at TEXT)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitl_category ON hitl_decisions(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hitl_outcome ON hitl_decisions(outcome)")

    def record_decision(
        self, decision_id: str, task_id: str, category: str, options: Sequence[Any],
        selected_option: str, operator_action: str, margin: float, calibrated_confidence: float,
        context_summary: str = "", outcome: str = "PENDING",
    ) -> dict[str, Any]:
        """Record a decision into persistent store and update learning aggregates."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ctx_hash = hashlib.sha256(f"{category}:{context_summary}:{selected_option}".encode("utf-8")).hexdigest()[:16]
        opts_serialized = json.dumps([opt if isinstance(opt, (dict, list, str, int, float)) else str(opt) for opt in options])
        conn = self._get_connection()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO hitl_decisions ("
                "decision_id, task_id, category, context_summary, context_hash, options_json, "
                "selected_option, operator_action, margin, calibrated_confidence, outcome, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (decision_id, task_id, category, context_summary, ctx_hash, opts_serialized,
                 selected_option, operator_action, margin, calibrated_confidence, outcome, now, now),
            )
            self._update_learning_aggregates(category, operator_action, outcome, margin, now)
        return {"decision_id": decision_id, "category": category, "operator_action": operator_action, "margin": margin, "status": "STORED"}

    def record_outcome(self, decision_id: str, outcome: str) -> bool:
        """Update the verified execution outcome ('SUCCESS', 'FAILED', 'ROLLED_BACK')."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = self._get_connection()
        with conn:
            cursor = conn.execute(
                "UPDATE hitl_decisions SET outcome = ?, updated_at = ? WHERE decision_id = ?",
                (outcome, now, decision_id),
            )
            if cursor.rowcount > 0:
                row = conn.execute(
                    "SELECT category, operator_action, margin FROM hitl_decisions WHERE decision_id = ?",
                    (decision_id,),
                ).fetchone()
                if row:
                    self._update_learning_aggregates(row["category"], row["operator_action"], outcome, row["margin"], now)
                return True
        return False

    def record_execution_outcome(self, decision_id: str, outcome: str, **_kwargs: Any) -> bool:
        """Record verified execution outcome (alias supporting sidecar automation callers)."""
        return self.record_outcome(decision_id=decision_id, outcome=outcome)

    def _update_learning_aggregates(
        self, category: str, operator_action: str, outcome: str, margin: float, timestamp: str,
    ) -> None:
        """Recalculate Bayesian learning aggregate factor for the category."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN operator_action = 'PROCEED_AUTONOMOUSLY' THEN 1 ELSE 0 END) as auto_cnt, "
            "SUM(CASE WHEN operator_action = 'APPROVED' THEN 1 ELSE 0 END) as app_cnt, "
            "SUM(CASE WHEN operator_action = 'OVERRIDDEN' THEN 1 ELSE 0 END) as ovr_cnt, "
            "SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as succ_cnt, "
            "SUM(CASE WHEN outcome IN ('FAILED', 'ROLLED_BACK') THEN 1 ELSE 0 END) as fail_cnt, "
            "AVG(margin) as avg_margin FROM hitl_decisions WHERE category = ?",
            (category,),
        ).fetchone()
        total, auto_cnt, app_cnt = row["total"] or 0, row["auto_cnt"] or 0, row["app_cnt"] or 0
        ovr_cnt, succ_cnt, fail_cnt = row["ovr_cnt"] or 0, row["succ_cnt"] or 0, row["fail_cnt"] or 0
        avg_margin = float(row["avg_margin"] or 0.0)
        positives = succ_cnt + (app_cnt * 0.5)
        negatives = fail_cnt + (ovr_cnt * 1.5)
        learning_factor = max(-0.25, min(0.15, round(((positives - negatives) / (total + 3.0)) * 0.15, 4)))
        conn.execute(
            "INSERT OR REPLACE INTO learning_aggregates ("
            "category, total_decisions, autonomous_proceeds, human_approvals, human_overrides, "
            "success_count, failure_count, mean_margin, learning_factor, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (category, total, auto_cnt, app_cnt, ovr_cnt, succ_cnt, fail_cnt, avg_margin, learning_factor, timestamp),
        )

    def query_learning_adjustment(self, category: str, option_label: str = "") -> float:
        """Query Bayesian learning adjustment factor for category/option."""
        conn = self._get_connection()
        row = conn.execute("SELECT learning_factor FROM learning_aggregates WHERE category = ?", (category,)).fetchone()
        if not row:
            return 0.0
        base_factor = float(row["learning_factor"])
        if option_label:
            opt_row = conn.execute(
                "SELECT SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) as succ, "
                "SUM(CASE WHEN outcome IN ('FAILED', 'ROLLED_BACK') THEN 1 ELSE 0 END) as fail "
                "FROM hitl_decisions WHERE category = ? AND selected_option = ?",
                (category, option_label),
            ).fetchone()
            if opt_row and (opt_row["succ"] or opt_row["fail"]):
                succ, fail = opt_row["succ"] or 0, opt_row["fail"] or 0
                opt_bonus = round(((succ - (fail * 2)) / (succ + fail + 2.0)) * 0.10, 4)
                return max(-0.25, min(0.20, base_factor + opt_bonus))
        return base_factor

    def get_calibration_metrics(self) -> dict[str, Any]:
        """Return system learning calibration metrics across all categories."""
        conn = self._get_connection()
        total_decisions = conn.execute("SELECT COUNT(*) FROM hitl_decisions").fetchone()[0]
        categories_data = [dict(r) for r in conn.execute("SELECT * FROM learning_aggregates ORDER BY total_decisions DESC").fetchall()]
        outcomes = {r["outcome"]: r["cnt"] for r in conn.execute("SELECT outcome, COUNT(*) as cnt FROM hitl_decisions GROUP BY outcome").fetchall()}
        return {
            "total_decisions": total_decisions, "outcomes": outcomes, "categories": categories_data,
            "ambiguity_threshold": DEFAULT_AMBIGUITY_THRESHOLD, "min_confidence_floor": DEFAULT_MIN_CONFIDENCE_FLOOR,
            "store_path": str(self.db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def evaluate_hitl_surfacing_gate(
    options: Sequence[Any],
    margin_threshold: float = DEFAULT_AMBIGUITY_THRESHOLD,
    min_confidence_floor: float = DEFAULT_MIN_CONFIDENCE_FLOOR,
    store: HITLDecisionStore | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Evaluate candidate HITL options against the calibrated 20% ambiguity margin and 65% floor rules."""
    if not options:
        return {
            "should_surface": False, "margin": 0.0, "margin_threshold": margin_threshold,
            "min_confidence_floor": min_confidence_floor, "below_confidence_floor": False,
            "top_option": None, "top_score": 0.0, "second_score": 0.0,
            "action": "EMPTY_OPTIONS", "reason": "No options provided to evaluate.",
        }
    scored = sorted(((calculate_calibrated_confidence(opt, category=category, store=store), opt) for opt in options), key=lambda x: x[0], reverse=True)
    top_score, top_opt = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = round(top_score - second_score, 4)
    within_margin = margin <= margin_threshold
    below_confidence_floor = top_score < min_confidence_floor
    should_surface = within_margin or below_confidence_floor
    action = "SURFACE_HITL_ATOMIC" if should_surface else "PROCEED_AUTONOMOUSLY"
    if within_margin:
        reason = f"Margin Delta = {margin:.2%} is within the calibrated {margin_threshold:.0%} threshold (\u0394 \u2264 {margin_threshold:.0%}): genuine ambiguity requires operator input."
    elif below_confidence_floor:
        reason = f"Top confidence {top_score:.2%} is below the {min_confidence_floor:.0%} autonomous confidence floor (INV-HITL-MIN-CONFIDENCE-FLOOR): operator input required."
    else:
        reason = f"Margin Delta = {margin:.2%} strictly exceeds the calibrated {margin_threshold:.0%} threshold (\u0394 > {margin_threshold:.0%}): proceed autonomously with top option."
    return {
        "should_surface": should_surface, "margin": margin, "margin_threshold": margin_threshold,
        "min_confidence_floor": min_confidence_floor, "below_confidence_floor": below_confidence_floor,
        "top_option": top_opt, "top_score": top_score, "second_score": second_score,
        "action": action, "reason": reason,
    }


_TRUNCATION_PATTERN = re.compile(r"(?:\.\.\.|…|\[truncated\]|\[cut\s*off\])", re.IGNORECASE)
_COMPOUND_QUESTION_PATTERN = re.compile(
    r"(?:;\s*(?:and\s+)?(?:also|what|which|how|should|do|would)\b"
    r"|\b(?:additionally|secondly|furthermore),?\s+(?:what|which|how|should|do|would)\b)",
    re.IGNORECASE,
)

ALLOWED_CAMEL_WHITELIST: frozenset[str] = frozenset({
    "iPhone", "iPad", "iCloud", "macOS", "iOS", "watchOS", "tvOS", "eBay", "jQuery", "oAuth", "openAI", "graphQL", "iCIMS",
})

ALLOWED_PASCAL_WHITELIST: frozenset[str] = frozenset({
    "GitHub", "GitLab", "GitKraken", "LinkedIn", "YouTube", "OpenAI", "ChatGPT", "DeepMind", "DeepWiki", "Context7",
    "PlayWright", "PowerShell", "JavaScript", "TypeScript", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "DuckDB", "ChromaDB",
    "FastAPI", "PyTest", "PyTorch", "TensorFlow", "HuggingFace", "LangChain", "LlamaIndex", "AutoGen", "CrewAI", "McKinsey",
    "PriceWaterhouse", "SharePoint", "OneDrive", "PowerPoint", "WordPress", "SalesForce", "ServiceNow", "WorkDay", "HubSpot",
    "DataDog", "CloudFlare", "DigitalOcean", "HashiCorp", "SnowFlake", "DataBricks", "ConFluent", "Palantir", "Anthropic",
    "Google", "Microsoft", "Amazon", "Apple", "Meta", "Netflix", "Option", "Confidence", "Recommended", "Impact", "Action",
    "Evidence", "Risk", "High", "Medium", "Low", "Decision", "Candidate", "Context", "Summary", "Status", "Approve", "Reject",
    "Defer", "Keep", "Update", "Remove", "Enable", "Disable", "Proceed", "Cancel", "Retry", "Skip", "NextEra", "TransUnion",
    "MasterCard", "FedEx", "PayPal", "SpaceX", "BlueOrigin", "LockheedMartin", "Raytheon", "NorthropGrumman", "GeneralElectric",
    "GeneralMotors", "MorganStanley", "GoldmanSachs", "BlackRock", "JPMorgan", "WellsFargo", "BankOfAmerica", "Citigroup",
    "AmericanExpress", "CapitalOne", "CharlesSchwab", "Fidelity", "Vanguard", "StateStreet", "PaloAlto", "CrowdStrike",
    "FortiNet", "CheckPoint", "CyberArk", "Okta", "Zscaler", "SentinelOne", "Splunk", "ElasticSearch", "NewRelic", "Dynatrace",
    "AppDynamics", "PagerDuty", "Atlassian", "BitBucket", "Confluence", "Trello", "Asana", "Monday", "AirTable", "SmartSheet",
    "DocuSign", "DropBox", "Zoom", "WebEx", "Slack", "Teams", "Discord", "Telegram", "WhatsApp", "Signal", "Stripe", "Square",
    "Adyen", "Braintree", "Plaid", "Twilio", "SendGrid", "MailChimp", "Zendesk", "Intercom", "FreshWorks", "Shopify",
    "BigCommerce", "WooCommerce", "Magento", "Squarespace", "Wix", "WebFlow", "Figma", "Canva", "Adobe", "PhotoShop",
    "Illustrator", "InDesign", "Premiere", "AfterEffects", "AutoCAD", "SolidWorks", "MatLab", "LabView", "Simulink", "Tableau",
    "PowerBI", "Looker", "QlikView", "MicroStrategy", "Domo", "Sisense", "Metabase", "Superset", "Grafana", "Prometheus",
    "Kubernetes", "Docker", "Terraform", "Ansible", "Jenkins", "CircleCI", "TravisCI", "ArgoCD", "Istio", "Envoy", "Nginx",
    "Apache", "Kafka", "RabbitMQ", "ActiveMQ", "Redis", "Memcached", "Cassandra", "CouchBase", "DynamoDB", "CosmosDB",
    "BigQuery", "RedShift", "Vertica", "Teradata", "Oracle", "Sybase", "Informix", "DB2", "NetSuite", "QuickBooks", "Xero",
    "FreshBooks", "Sage", "Wave", "Gusto", "Rippling", "Deel", "Remote", "Oyster", "Lattice", "CultureAmp", "BambooHR",
    "GreenHouse", "Lever", "Workable", "SmartRecruiters", "JobVite", "Taleo", "SuccessFactors", "Cornerstone", "Degreed",
    "Coursera", "Udemy", "EdX", "PluralSight", "DataCamp", "LeetCode", "HackerRank", "CodeSignal", "CoderPad", "StackOverflow",
    "StackExchange", "Reddit", "Quora", "SubStack", "Ghost", "Patreon", "KickStarter", "IndieGogo", "GoFundMe", "EventBrite",
    "MeetUp", "TicketMaster", "StubHub", "SeatGeek", "DoorDash", "UberEats", "GrubHub", "InstaCart", "PostMates", "Lyft",
    "AirBnb", "Booking", "Expedia", "TripAdvisor", "SkyScanner", "Kayak", "Zillow", "RedFin", "Realtor", "Trulia", "Compass",
    "Opendoor", "Carvana", "CarMax", "AutoTrader", "KelleyBlueBook", "RobinHood", "CoinBase", "Binance", "Kraken", "Gemini",
    "OpenSea", "MetaMask", "Ledger", "Trezor", "BlockChain", "BitCoin", "Ethereum", "Solana", "Cardano", "Polkadot",
    "Avalanche", "Polygon", "ChainLink", "UniSwap", "Aave", "Compound", "MakerDAO", "TikTok", "SnapChat", "Pinterest",
    "Twitch", "Spotify", "SoundCloud", "Pandora", "AppleMusic", "AmazonMusic", "YouTubeMusic", "DisneyPlus", "Hulu", "Max",
    "Peacock", "ParamountPlus", "PrimeVideo", "PlayStation", "Xbox", "Nintendo", "Steam", "EpicGames", "Roblox", "MineCraft",
    "Fortnite", "Valorant", "LeagueOfLegends", "OverWatch", "WorldOfWarcraft", "CallOfDuty", "GrandTheftAuto", "CyberPunk",
    "EldenRing", "StarField", "BaldursGate", "Diablo", "StarCraft", "HearthStone", "ApexLegends", "RocketLeague", "AmongUs",
    "FallGuys", "GenshinImpact", "HonkaiStarRail", "Bayesian",
})

_QUESTION_JARGON_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bSELECT\s+.+?\s+FROM\s+[a-zA-Z0-9_]+", re.IGNORECASE | re.DOTALL),
        "inline SQL query",
    ),
    (
        re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*_[a-zA-Z0-9_]+\b"),
        "snake_case identifier",
    ),
    (
        re.compile(r"\b[a-z]+[A-Z][a-zA-Z0-9]*\b"),
        "camelCase identifier",
    ),
    (
        re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"),
        "PascalCase identifier",
    ),
    (
        re.compile(
            r"(?:^|[\s`\"'(\[{])(?:[a-zA-Z0-9_\-./]+/)?[a-zA-Z0-9_\-]+\.(?:py|sqlite|jsonl|yaml|yml|toml|sh|sql|md|json)\b"
        ),
        "file path or extension",
    ),
    (
        re.compile(r"(?:^|\s)--[a-zA-Z0-9][a-zA-Z0-9\-]*\b"),
        "CLI flag",
    ),
    (
        re.compile(r"\bCandidate\s+ID\s*:", re.IGNORECASE),
        "Candidate ID slug",
    ),
    (
        re.compile(r"\bO[1-8]\b"),
        "internal step code (O1-O8)",
    ),
    (
        re.compile(
            r"\b(?:HITL|A2A|SSOT|WAL|ACID|JSONL|AST|DDL|DML|PRAGMA|CLI|SDK|BM25|RRF|DAG|MCP|SHA|TTL|UUID|SQL|YAML|TOML|"
            r"blast\s+radius|triad|telemetry|orchestration|deterministic|invariants?|schemas?|payloads?|ratchets?|"
            r"idempotent|sub-?agents?)\b",
            re.IGNORECASE,
        ),
        "technical or systems jargon",
    ),
)


def scan_question_jargon(text: str) -> list[str]:
    """Scan question or option text for technical jargon, code symbols, file paths, or acronyms."""
    if not text or not isinstance(text, str):
        return []
    violations: list[str] = []
    for pattern, label in _QUESTION_JARGON_PATTERNS:
        for m in pattern.finditer(text):
            sample = m.group(0).strip(" `\"'()[]{}")
            if label == "camelCase identifier" and sample in ALLOWED_CAMEL_WHITELIST:
                continue
            if label == "PascalCase identifier" and sample in ALLOWED_PASCAL_WHITELIST:
                continue
            entry = f"{label} ('{sample}')"
            if entry not in violations:
                violations.append(entry)
    return violations


def validate_hitl_presentation(
    payload: Any,
    *,
    enforce_visibility_and_jargon: bool = False,
) -> list[str]:
    """Validate that a candidate HITL payload adheres to atomic presentation, character visibility, and plain-English controls."""
    errors: list[str] = []

    # 1. Reject bulk / batched decisions
    if isinstance(payload, list) and len(payload) > 1:
        errors.append(
            "HITL_VIOLATION_BULK_DECISION: Presenting multiple decisions simultaneously violates atomic presentation. Present one at a time."
        )
        return errors

    if isinstance(payload, dict) and "questions" in payload:
        if isinstance(payload["questions"], list) and len(payload["questions"]) > 1:
            errors.append(
                "HITL_VIOLATION_BULK_DECISION: Batched questions detected. Present strictly one decision at a time."
            )
            return errors

    item = payload[0] if isinstance(payload, list) and len(payload) == 1 else payload

    if not isinstance(item, dict):
        errors.append("HITL_VIOLATION_INVALID_PAYLOAD: Decision payload must be a dictionary.")
        return errors

    q_text = str(item.get("question") or item.get("prompt") or "").strip()
    if enforce_visibility_and_jargon and q_text:
        if len(q_text) > MAX_QUESTION_LENGTH:
            errors.append(
                f"HITL_VIOLATION_QUESTION_LENGTH: Question length ({len(q_text)} chars) exceeds MAX_QUESTION_LENGTH ({MAX_QUESTION_LENGTH} chars)."
            )
        if _TRUNCATION_PATTERN.search(q_text):
            errors.append(
                "HITL_VIOLATION_TRUNCATION: Question contains ellipsis or truncation marker ('...' or '…'). Write complete, concise sentences."
            )
        if q_text.count("?") > 1 or _COMPOUND_QUESTION_PATTERN.search(q_text):
            errors.append(
                f"HITL_VIOLATION_BUNDLED_QUESTIONS: Question text contains multiple bundled questions. Ask strictly one question at a time."
            )
        q_jargon = scan_question_jargon(q_text)
        if q_jargon:
            errors.append(
                f"HITL_VIOLATION_JARGON_IN_QUESTION: Question text contains technical jargon: {', '.join(q_jargon[:3])}. Use plain English."
            )

    options = item.get("options", [])
    if not isinstance(options, (list, tuple)) or len(options) < 2:
        errors.append(
            "HITL_VIOLATION_INSUFFICIENT_OPTIONS: Decision must provide at least 2 distinct options."
        )
        return errors

    for idx, opt in enumerate(options):
        has_conf = False
        opt_label = ""
        if isinstance(opt, dict):
            has_conf = any(k in opt for k in ("confidence", "confidence_level", "confidence_score", "calibrated_confidence"))
            opt_label = str(opt.get("label") or opt.get("title") or opt.get("text") or "").strip()
        elif isinstance(opt, str):
            has_conf = any(k in opt.lower() for k in ("confidence", "conf:", "high", "medium", "low", "%"))
            opt_label = opt.strip()

        if not has_conf:
            errors.append(
                f"HITL_VIOLATION_MISSING_CONFIDENCE: Option {idx + 1} lacks an explicit calibrated confidence level."
            )

        if enforce_visibility_and_jargon and opt_label:
            if len(opt_label) > MAX_OPTION_LENGTH:
                errors.append(
                    f"HITL_VIOLATION_OPTION_LENGTH: Option {idx + 1} length ({len(opt_label)} chars) exceeds MAX_OPTION_LENGTH ({MAX_OPTION_LENGTH} chars)."
                )
            if _TRUNCATION_PATTERN.search(opt_label):
                errors.append(
                    f"HITL_VIOLATION_TRUNCATION: Option {idx + 1} contains ellipsis or truncation marker ('...' or '…')."
                )
            opt_jargon = scan_question_jargon(opt_label)
            if opt_jargon:
                errors.append(
                    f"HITL_VIOLATION_JARGON_IN_OPTION: Option {idx + 1} contains technical jargon: {', '.join(opt_jargon[:3])}. Use plain English."
                )

    return errors


def validate_approval_origin(text: str) -> tuple[bool, str]:
    """Validate whether an approval message originates from an authentic human operator or approved review policy."""
    lower = text.lower()
    for marker in AUTHENTIC_USER_ARTIFACT_APPROVAL_MARKERS:
        if marker in lower:
            return True, "AUTHENTIC_USER_ARTIFACT_APPROVAL"

    for marker in SYNTHETIC_APPROVAL_MARKERS:
        if marker in lower:
            return False, f"SYNTHETIC_APPROVAL_DETECTED: Matched synthetic marker '{marker}'."

    return True, "AUTHENTIC_HUMAN_APPROVAL"


PLAN_ONLY_TRIGGERS = (
    "plan only",
    "no implement",
    "plan only stop",
    "do not implement",
    "stop before executing",
)

MODEL_TOKEN_PATTERN = re.compile(
    r"\b(?:gpt-[0-9]+(?:\.[0-9]+)?(?:-[a-z0-9]+)?|claude-[a-z0-9-]+|gemini-[0-9]+(?:\.[0-9]+)?(?:-[a-z0-9]+)?)\b",
    re.IGNORECASE,
)

PROVIDER_PROFILE_REL_PATHS = (
    "resume_graph_engine/config/models/registry.yaml",
    "config/provider_profiles.yaml",
    "outreach_engine/config/provider_profiles.yaml",
    "resume_graph_engine/src/apps_rg/config/provider_profiles.yaml",
)


def load_approved_provider_models(repo_root: Path | str | None = None) -> set[str]:
    """Extract approved model identifiers from canonical provider profile configurations."""
    root = Path(repo_root or ".").resolve()
    approved: set[str] = set()

    for rel_path in PROVIDER_PROFILE_REL_PATHS:
        cfg_file = root / rel_path
        if not cfg_file.is_file():
            continue
        try:
            text = cfg_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
            if isinstance(data, dict):
                def _extract_models(obj: Any) -> None:
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in (
                                "model",
                                "backup_model",
                                "default_model",
                                "gemini_pro",
                                "openai_chatgpt",
                                "snapshot_id",
                            ) and isinstance(v, str):
                                approved.add(v.strip())
                            elif k in ("model_by_section", "anthropic_limit_backup_model_by_section") and isinstance(v, dict):
                                for _, m in v.items():
                                    if isinstance(m, str):
                                        approved.add(m.strip())
                            elif k == "models" and isinstance(v, dict):
                                for model_id, model_def in v.items():
                                    if isinstance(model_id, str):
                                        approved.add(model_id.strip())
                                    if isinstance(model_def, dict) and isinstance(model_def.get("snapshot_id"), str):
                                        approved.add(model_def["snapshot_id"].strip())
                            else:
                                _extract_models(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _extract_models(item)

                _extract_models(data)
                continue
        except (OSError, ValueError, TypeError, KeyError, AttributeError):  # guardian: allow-silent-swallow -- fallback to regex parser on unparseable YAML/JSON
            pass

        for line in text.splitlines():
            m = re.search(
                r"(?:model|backup_model|snapshot_id|gemini_pro|openai_chatgpt|slalom_narrative|unify_narrative|ibm_narrative|insurtech_narrative|competencies|headline|executive_summary)\s*:\s*[\"']?([a-zA-Z0-9.\-_]+)[\"']?",
                line,
            )
            if m:
                val = m.group(1).strip().strip("'\"")
                if any(p in val.lower() for p in ("gpt-", "claude-", "gemini-")):
                    approved.add(val)

    return approved


def find_model_tokens(text: str) -> list[str]:
    """Extract candidate model tokens from text."""
    return [m.group(0) for m in MODEL_TOKEN_PATTERN.finditer(text)]


def validate_model_token_registry(
    text: str,
    repo_root: Path | str | None = None,
    approved_models: set[str] | None = None,
) -> tuple[bool, list[str], set[str]]:
    """Validate that any model tokens in text are declared in the approved provider profiles.

    Returns:
        (is_valid, unapproved_tokens_found, approved_models_set)
    """
    approved = approved_models if approved_models is not None else load_approved_provider_models(repo_root)
    tokens = find_model_tokens(text)
    unapproved: list[str] = []
    for tok in tokens:
        matches = any(tok.lower() == app.lower() for app in approved)
        if not matches:
            unapproved.append(tok)
    return len(unapproved) == 0, unapproved, approved


def evaluate_model_token_ambiguity(
    unapproved_token: str,
    approved_models: set[str] | None = None,
) -> dict[str, Any]:
    """Formulate and score candidate options for an unapproved model token to determine ambiguity margin."""
    import difflib

    approved = list(approved_models) if approved_models else ["gpt-5.6-luna", "claude-sonnet-5", "gemini-3.8-flash"]
    matches = difflib.get_close_matches(unapproved_token, approved, n=1, cutoff=0.4)
    best_candidate = matches[0] if matches else approved[0]

    # Calibrated to represent genuine ambiguity between typo hypothesis vs literal unreleased override
    option_a = {
        "label": f"Resolve as typo for approved canonical pin '{best_candidate}'",
        "confidence_score": 0.56,
        "evidence_refs": ["config/provider_profiles.yaml"],
        "has_verification_receipt": False,
        "risk_level": "MEDIUM",
    }
    option_b = {
        "label": f"Treat '{unapproved_token}' as intentional unreleased external model override",
        "confidence_score": 0.50,
        "evidence_refs": [],
        "has_verification_receipt": False,
        "risk_level": "HIGH",
    }

    eval_result = evaluate_hitl_surfacing_gate([option_a, option_b])
    return {
        "unapproved_token": unapproved_token,
        "suggested_match": best_candidate,
        "options": [option_a, option_b],
        "margin": eval_result["margin"],
        "should_surface": eval_result["should_surface"],
        "action": eval_result["action"],
    }


def validate_plan_only_firewall(
    user_prompt: str,
    artifact_metadata: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Validate that when user requests plan-only, RequestFeedback is false to prevent auto-proceed triggers."""
    lower = user_prompt.lower()
    is_plan_only = any(t in lower for t in PLAN_ONLY_TRIGGERS)
    if not is_plan_only:
        return True, "STANDARD_EXECUTION_ALLOWED"

    if artifact_metadata and artifact_metadata.get("RequestFeedback") is True:
        return False, "PLAN_ONLY_FIREWALL_VIOLATION: User requested plan-only mode; RequestFeedback must be false to prevent auto-execution."

    return True, "PLAN_ONLY_FIREWALL_SATISFIED"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI tool for inspecting HITL decision store, calibration, and system learning."""
    parser = argparse.ArgumentParser(description="HITL Governance & Calibration Engine CLI.")
    parser.add_argument("--status", action="store_true", help="Display persistent store calibration status and metrics.")
    parser.add_argument("--metrics", action="store_true", help="Output JSON calibration metrics.")
    parser.add_argument("--db-path", type=str, default=None, help="Custom SQLite DB path.")

    args = parser.parse_args(argv)
    store = HITLDecisionStore(db_path=args.db_path)

    metrics = store.get_calibration_metrics()
    if args.metrics:
        print(json.dumps(metrics, indent=2))
        return 0

    print("=== HITL Governance Calibration & System Learning Status ===")
    print(f"Store Location:       {metrics['store_path']}")
    print(f"Ambiguity Threshold:  {metrics['ambiguity_threshold']:.0%} (diff > {metrics['ambiguity_threshold']:.0%} proceeds autonomously)")
    print(f"Total Decisions:      {metrics['total_decisions']}")
    print(f"Outcome Distribution: {metrics['outcomes']}")
    print("\nLearning Aggregates by Category:")
    if not metrics["categories"]:
        print("  (No decision aggregates recorded yet)")
    else:
        for cat in metrics["categories"]:
            print(
                f"  - {cat['category']}: Total={cat['total_decisions']}, "
                f"Auto={cat['autonomous_proceeds']}, Approved={cat['human_approvals']}, "
                f"Success={cat['success_count']}, Factor={cat['learning_factor']:+.4f}"
            )

    store.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
