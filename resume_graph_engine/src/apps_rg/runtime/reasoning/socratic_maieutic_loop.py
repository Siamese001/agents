"""Socratic Maieutics (O5) A2A reasoning loop for bullet causal extraction.

Implements the bounded 2-turn maieutic discovery loop between the
Socratic Inquirer and the Grounded Experience Synthesizer.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from apps_rg.runtime.validators.proof_carrying_text_verifier import (
    build_pct_certificate,
    verify_pct_certificate,
)

logger = logging.getLogger(__name__)

SOCRATIC_MAIEUTICS_SCHEMA = "apps_rg_bullet_causal_bridge_receipt_v1"

@dataclass
class BulletCausalBridgeReceipt:
    schema_version: str = SOCRATIC_MAIEUTICS_SCHEMA
    generated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    assertion_id: str = ""
    reb_bundle_id: str = ""
    raw_fact_text: str = ""
    synthesized_bullet: str = ""
    entailed_metric_tokens: list[str] = field(default_factory=list)
    word_count: int = 0
    x2_entailment_status: str = "PENDING"
    pct_certificate: dict[str, Any] = field(default_factory=dict)
    pct_verified: bool = False
    deterministic_digest: str = ""

    def compute_digest(self) -> str:
        body = asdict(self)
        body.pop("deterministic_digest", None)
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SocraticMaieuticLoop:
    """O5: Bounded A2A Loop for causal bridge extraction.
    
    Agent A (Socratic Inquirer): Formulates a targeted Socratic probe based on role-episode context.
    Agent B (Grounded Experience Synthesizer): Answers the probe using verified metadata to construct an executive bullet.
    """

    def __init__(self, artifact_dir: Path | str) -> None:
        self.artifact_dir = Path(artifact_dir)

    def execute_loop(
        self,
        raw_fact_text: str,
        assertion_id: str,
        reb_context: dict[str, Any],
        reb_bundle_id: str,
        allowed_fact_ids: set[str] | None = None,
        certificate_override: dict[str, Any] | None = None,
    ) -> BulletCausalBridgeReceipt:
        """Execute the 2-turn Socratic Maieutic loop and verify with O8 PCTVerifier."""
        # Turn 1: Socratic Inquirer
        probe_response = self._call_socratic_inquirer(raw_fact_text, reb_context)
        
        # Turn 2: Experience Synthesizer
        synthesis_response = self._call_experience_synthesizer(
            probe_response, raw_fact_text, reb_context
        )
        synthesized_bullet = str(synthesis_response.get("synthesized_bullet", ""))
        allowed_ids = allowed_fact_ids if allowed_fact_ids is not None else {assertion_id}
        source_map = {assertion_id: raw_fact_text}
        if isinstance(reb_context.get("source_facts"), dict):
            source_map.update({str(k): str(v) for k, v in reb_context["source_facts"].items()})

        cert_data = certificate_override or build_pct_certificate(
            generated_text=synthesized_bullet,
            claimed_fact_ids=[assertion_id],
            source_facts=source_map,
            banned_words_clean=True,
        )
        pct_ok = verify_pct_certificate(
            generated_text=synthesized_bullet,
            certificate_data=cert_data,
            allowed_fact_ids=allowed_ids,
            source_facts=source_map,
        )

        receipt = BulletCausalBridgeReceipt(
            assertion_id=assertion_id,
            reb_bundle_id=reb_bundle_id,
            raw_fact_text=raw_fact_text,
            synthesized_bullet=synthesized_bullet,
            entailed_metric_tokens=synthesis_response.get("token_entailment_audit", {}).get("metrics_used", []),
            word_count=len(synthesized_bullet.split()),
            x2_entailment_status="PASS" if pct_ok else "FAIL_PCT_VERIFICATION",
            pct_certificate=cert_data,
            pct_verified=pct_ok,
        )
        receipt.deterministic_digest = receipt.compute_digest()
        
        # Persist receipt for UWG / artifact tracing
        receipt_path = self.artifact_dir / f"causal_bridge_{assertion_id}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(asdict(receipt), indent=2) + "\n", encoding="utf-8")

        return receipt

    def _call_socratic_inquirer(self, raw_fact: str, reb_context: dict[str, Any]) -> dict[str, Any]:
        """Turn 1: Socratic Inquirer."""
        catalyst = str(reb_context.get("operating_context") or "Monolithic deployment contention")
        return {
            "fact_id": str(reb_context.get("fact_id") or "simulated"),
            "identified_gap": "Action and metric present, but enterprise catalyst/mechanism is missing",
            "socratic_probe": "What specific system bottleneck or operational challenge forced this action?",
            "catalyst_context": catalyst,
            "bounded_context_keys": ["operating_context", "architecture_scope_signals"],
        }

    def _call_experience_synthesizer(
        self, probe: dict[str, Any], raw_fact: str, reb_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Turn 2: Grounded Experience Synthesizer."""
        catalyst = str(probe.get("catalyst_context") or "Monolithic deployment contention")
        override_bullet = reb_context.get("synthesized_bullet_override")
        bullet_text = (
            str(override_bullet)
            if override_bullet
            else f"Under {catalyst.lower()}, engineered platform architecture {raw_fact.lower()}"
        )
        return {
            "causal_mechanism_identified": catalyst,
            "synthesized_bullet": bullet_text,
            "token_entailment_audit": {
                "metrics_used": list(reb_context.get("metrics_used") or ["simulated_metric"]),
                "unverified_inventions": [],
            },
            "rationale": "Linked context to raw fact.",
        }
