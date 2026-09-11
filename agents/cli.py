"""Unified CLI Entrypoint for Resume Engine and Outreach Engine.

Usage:
    python -m agents resume [run|eval|show] [options]
    python -m agents outreach [run|eval|show] [options]
    python -m agents e2e [--company ... --role ...] [options]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

# Bootstrap paths
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
_OE_SRC = _REPO_ROOT / "outreach_engine" / "src"

for p in (_REPO_ROOT, _RG_SRC, _OE_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# Ensure local dev route signing secrets exist if not supplied in environment
if not os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"):
    os.environ["APPS_RG_ROUTE_HMAC_SECRET"] = "agents-local-dev-session-secret"
if not os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"):
    os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"] = "agents-local-dev-key"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agents",
        description="Sovereign Agentic Platform: Unified CLI entrypoint for Resume Engine and Outreach Engine.",
    )
    parser.add_argument("--version", action="version", version="agents 1.0.0")
    subparsers = parser.add_subparsers(dest="engine", metavar="ENGINE")

    # 1. resume engine
    subparsers.add_parser(
        "resume",
        help="Run, evaluate, or inspect the Resume Graph Engine (apps_rg)",
        add_help=False,
    )

    # 2. outreach engine
    subparsers.add_parser(
        "outreach",
        help="Run, evaluate, or inspect the Executive Outreach Engine (outreach_engine)",
        add_help=False,
    )

    # 3. e2e full lifecycle
    e2e_parser = subparsers.add_parser(
        "e2e",
        help="Run the unified end-to-end lifecycle (Research -> Tailored Resume -> Executive Outreach)",
    )
    e2e_parser.add_argument(
        "--company",
        "--target-company",
        dest="company",
        default="Anthropic",
        help="Target company name (default: Anthropic)",
    )
    e2e_parser.add_argument(
        "--role",
        "--target-role",
        dest="role",
        default="Manager of Applied AI Architecture, Partnerships",
        help="Target role title",
    )
    e2e_parser.add_argument("--jd", default="", help="Optional JD file path or inline text")
    e2e_parser.add_argument("--resume", default="", help="Optional base-resume JSON, Markdown, or text path")
    e2e_parser.add_argument("--brief", help="Optional path to briefing JSON fixture")
    e2e_parser.add_argument("--demo", action="store_true", help="Run with canonical demo fixtures")
    e2e_parser.add_argument("--skip-resume", action="store_true", help="Skip Stage 2 resume tailoring")
    e2e_parser.add_argument("--artifact-dir", help="Directory to persist run outputs")
    e2e_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    return parser


def run_e2e(args: argparse.Namespace) -> int:
    """Execute end-to-end multi-agent career intelligence lifecycle."""
    run_id = f"e2e_{uuid.uuid4().hex[:8]}"
    if args.artifact_dir:
        base_dir = Path(args.artifact_dir).resolve()
    else:
        base_dir = _REPO_ROOT / "artifacts" / "e2e_lifecycle" / run_id
    base_dir.mkdir(parents=True, exist_ok=True)

    company = args.company
    role = args.role
    if args.demo and not args.brief and company == "Anthropic":
        # Anthropic demo target defaults
        company = "Anthropic"
        role = "Manager of Applied AI Architecture, Partnerships"

    if not args.json:
        print("\n" + "=" * 65)
        print("SOVEREIGN AGENTIC PLATFORM: UNIFIED E2E CAREER LIFECYCLE")
        print("=" * 65)
        print(f"Target Company : {company}")
        print(f"Target Role    : {role}")
        print(f"Artifact Dir   : {base_dir}")
        print("=" * 65 + "\n")

    summary_payload: dict[str, Any] = {
        "run_id": run_id,
        "company": company,
        "role": role,
        "artifact_dir": str(base_dir),
        "stages": {},
    }

    # Stage 1 & 2: Resume Tailoring (apps_rg)
    resume_artifact_dir = base_dir / "resume"
    tailored_resume_path = None
    if not args.skip_resume:
        if not args.json:
            print(">>> [Stage 1/3] Tailoring Executive Resume via Resume Graph Engine (apps_rg)...")
        from apps_rg.__main__ import main as resume_main

        resume_args = [
            "run",
            "--target-company", company,
            "--target-role", role,
        ]
        if args.jd:
            resume_args.extend(["--jd", args.jd])
        if args.resume:
            resume_args.extend(["--resume", args.resume])

        rg_code = resume_main(resume_args)
        summary_payload["stages"]["resume_tailoring"] = {
            "exit_code": rg_code,
            "status": "PASSED" if rg_code == 0 else "FAILED",
        }
        if rg_code != 0:
            if not args.json:
                sys.stderr.write("[agents e2e] Warning: Resume generation returned non-zero exit code.\n")
    else:
        if not args.json:
            print(">>> [Stage 1/3] Resume tailoring skipped (--skip-resume).")
        summary_payload["stages"]["resume_tailoring"] = {"status": "SKIPPED"}

    # Stage 3: Executive Outreach Generation (outreach_engine)
    from apps_lic.__main__ import main as outreach_main

    outreach_artifact_dir = base_dir / "outreach"
    outreach_args = [
        "run",
        "--artifact-dir",
        str(outreach_artifact_dir),
    ]
    if args.brief:
        outreach_args.extend(["--brief", args.brief])
    elif args.demo:
        outreach_args.append("--demo")
    else:
        outreach_args.extend(["--company", company, "--role", role])

    if args.json:
        outreach_args.append("--json")

    if not args.json:
        print("\n>>> [Stage 2/3] Generating Grounded Executive Outreach (outreach_engine)...")

    oe_code = outreach_main(outreach_args)
    summary_payload["stages"]["executive_outreach"] = {
        "exit_code": oe_code,
        "status": "PASSED" if oe_code == 0 else "FAILED",
    }
    if oe_code != 0:
        sys.stderr.write("[agents e2e] Outreach generation returned non-zero exit code.\n")
        return oe_code

    # Stage 4: Lifecycle Sealing & Manifest
    summary_path = base_dir / "e2e_lifecycle_summary.json"
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    if not args.json:
        print("\n>>> [Stage 3/3] Lifecycle artifacts validated and sealed.")
        print(f"[agents e2e] Sealed summary manifest at: {summary_path}\n")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        _build_parser().print_help()
        return 0

    if values[0] in {"-h", "--help"}:
        _build_parser().print_help()
        return 0

    if values[0] in {"-v", "--version"}:
        print("agents 1.0.0")
        return 0

    engine = values[0].lower()
    sub_args = values[1:]

    # Handle unified engine dispatch
    if engine in {"resume", "resume_engine", "resume_graph_engine", "apps_rg"}:
        from apps_rg.__main__ import main as resume_main
        return resume_main(sub_args)

    if engine in {"outreach", "outreach_engine", "apps_lic"}:
        from apps_lic.__main__ import main as outreach_main
        return outreach_main(sub_args)

    if engine == "e2e":
        parser = _build_parser()
        args = parser.parse_args(values)
        return run_e2e(args)

    # If first argument is an action or option like --demo, check if directed at outreach
    if engine.startswith("-"):
        parser = _build_parser()
        parser.print_help()
        return 1

    sys.stderr.write(f"Error: Unknown engine '{engine}'. Choices: resume, outreach, e2e\n")
    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
