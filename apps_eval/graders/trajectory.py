"""Trajectory efficiency, loop/oscillation detection, and strict tool-schema validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping, Sequence

ActionType = Literal[
    "tool_call",
    "subagent_delegation",
    "state_read",
    "state_write",
    "lane_exec",
    "gate_check",
    "final_response",
]
StepStatus = Literal["SUCCESS", "ERROR", "TIMEOUT", "BLOCKED"]


@dataclass(frozen=True)
class TrajectoryStep:
    step_index: int
    action_type: ActionType
    target: str
    arguments: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = "SUCCESS"
    latency_ms: float = 0.0
    error_code: str | None = None

    def signature(self) -> tuple[str, str, str]:
        arg_keys = ",".join(f"{k}={self.arguments[k]!r}" for k in sorted(self.arguments))
        return (self.action_type, self.target, arg_keys)


@dataclass(frozen=True)
class TrajectoryTrace:
    trace_id: str
    steps: list[TrajectoryStep]
    optimal_step_count: int | None
    terminal_task_success: bool


@dataclass(frozen=True)
class StepEvaluationVerdict:
    step_index: int
    target: str
    schema_valid: bool
    schema_errors: list[str]
    redundant_duplicate: bool
    loop_detected: bool
    oscillation_detected: bool
    penalty: float


@dataclass(frozen=True)
class TrajectoryScorecard:
    trace_id: str
    total_steps: int
    optimal_step_count: int | None
    efficiency_ratio: float
    schema_compliance_rate: float
    non_redundancy_rate: float
    recovery_rate: float
    loop_count: int
    oscillation_count: int
    unresolved_error_count: int
    terminal_task_success: bool
    composite_score: float
    hard_gates: dict[str, bool]
    passed: bool
    step_verdicts: list[StepEvaluationVerdict]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolSchemaValidator:
    """Strict JSON-subset argument validator rejecting bool-as-int and unknown properties."""

    def __init__(self, registry: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.registry: dict[str, dict[str, Any]] = {
            k: dict(v) for k, v in (registry or {}).items()
        }

    def validate(self, tool_name: str, arguments: Mapping[str, Any]) -> tuple[bool, list[str]]:
        if not self.registry:
            return True, []
        if tool_name not in self.registry:
            return False, [f"unregistered_tool:{tool_name}"]

        schema = self.registry[tool_name]
        errors: list[str] = []
        properties = dict(schema.get("properties") or {})
        required = list(schema.get("required") or [])
        additional_allowed = bool(schema.get("additionalProperties", False))

        for req_key in required:
            if req_key not in arguments:
                errors.append(f"missing_required:{req_key}")

        for key, value in arguments.items():
            if key not in properties:
                if not additional_allowed:
                    errors.append(f"unexpected_property:{key}")
                continue
            prop = properties[key]
            expected_type = prop.get("type")
            if expected_type == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    errors.append(f"type_mismatch:{key}:expected_integer")
            elif expected_type == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(f"type_mismatch:{key}:expected_number")
            elif expected_type == "boolean":
                if not isinstance(value, bool):
                    errors.append(f"type_mismatch:{key}:expected_boolean")
            elif expected_type == "string":
                if not isinstance(value, str):
                    errors.append(f"type_mismatch:{key}:expected_string")
                else:
                    min_len = prop.get("minLength")
                    max_len = prop.get("maxLength")
                    if min_len is not None and len(value) < int(min_len):
                        errors.append(f"min_length_violation:{key}")
                    if max_len is not None and len(value) > int(max_len):
                        errors.append(f"max_length_violation:{key}")
            elif expected_type == "array":
                if not isinstance(value, list):
                    errors.append(f"type_mismatch:{key}:expected_array")
            elif expected_type == "object":
                if not isinstance(value, Mapping):
                    errors.append(f"type_mismatch:{key}:expected_object")

            enum_vals = prop.get("enum")
            if enum_vals is not None and value not in enum_vals:
                errors.append(f"enum_violation:{key}:{value!r}")

        return (len(errors) == 0), errors


class TrajectoryEvaluator:
    """Evaluates multi-step agent trajectories with loop, oscillation, and schema gates."""

    def __init__(self, tool_validator: ToolSchemaValidator | None = None) -> None:
        self.tool_validator = tool_validator or ToolSchemaValidator()

    def evaluate(self, trace: TrajectoryTrace) -> TrajectoryScorecard:
        steps = list(trace.steps)
        total_steps = len(steps)
        if total_steps == 0:
            gates = {
                "non_empty_trace": False,
                "loop_count_zero": True,
                "optimal_steps_available": trace.optimal_step_count is not None and trace.optimal_step_count > 0,
                "efficiency_floor": False,
                "schema_compliance_floor": False,
                "zero_unresolved_errors": False,
                "terminal_task_success": bool(trace.terminal_task_success),
                "composite_floor": False,
            }
            return TrajectoryScorecard(
                trace_id=trace.trace_id,
                total_steps=0,
                optimal_step_count=trace.optimal_step_count,
                efficiency_ratio=0.0,
                schema_compliance_rate=0.0,
                non_redundancy_rate=0.0,
                recovery_rate=0.0,
                loop_count=0,
                oscillation_count=0,
                unresolved_error_count=1,
                terminal_task_success=bool(trace.terminal_task_success),
                composite_score=0.0,
                hard_gates=gates,
                passed=False,
                step_verdicts=[],
            )

        sigs = [s.signature() for s in steps]
        step_verdicts: list[StepEvaluationVerdict] = []
        valid_schema_count = 0
        redundant_count = 0
        loop_count = 0
        oscillation_count = 0
        error_count = 0
        recovered_error_count = 0
        unresolved_error_count = 0

        for idx, step in enumerate(steps):
            schema_ok, schema_errs = (
                self.tool_validator.validate(step.target, step.arguments)
                if step.action_type == "tool_call"
                else (True, [])
            )
            if schema_ok:
                valid_schema_count += 1

            redundant = idx >= 1 and sigs[idx] == sigs[idx - 1]
            three_loop = idx >= 2 and sigs[idx] == sigs[idx - 1] == sigs[idx - 2]
            oscillation = (
                idx >= 3
                and sigs[idx] == sigs[idx - 2]
                and sigs[idx - 1] == sigs[idx - 3]
                and sigs[idx] != sigs[idx - 1]
            )

            penalty = 0.0
            if redundant:
                redundant_count += 1
                penalty += 0.30
            if three_loop:
                loop_count += 1
                penalty += 0.50
            if oscillation:
                oscillation_count += 1
                penalty += 0.50

            if step.status in {"ERROR", "TIMEOUT", "BLOCKED"}:
                error_count += 1
                later_recovered = any(
                    nxt.status == "SUCCESS" for nxt in steps[idx + 1 :]
                )
                if later_recovered and trace.terminal_task_success:
                    recovered_error_count += 1
                else:
                    unresolved_error_count += 1

            step_verdicts.append(
                StepEvaluationVerdict(
                    step_index=step.step_index,
                    target=step.target,
                    schema_valid=schema_ok,
                    schema_errors=schema_errs,
                    redundant_duplicate=redundant,
                    loop_detected=three_loop,
                    oscillation_detected=oscillation,
                    penalty=round(penalty, 2),
                )
            )

        optimal_avail = trace.optimal_step_count is not None and trace.optimal_step_count > 0
        efficiency_ratio = (
            min(1.0, float(trace.optimal_step_count) / float(total_steps))
            if optimal_avail
            else 0.0
        )
        schema_compliance_rate = float(valid_schema_count) / float(total_steps)
        non_redundancy_rate = max(0.0, 1.0 - (float(redundant_count) / float(total_steps)))
        recovery_rate = (
            1.0 if error_count == 0 else float(recovered_error_count) / float(error_count)
        )

        total_loops = loop_count + oscillation_count
        raw_composite = (
            (
                0.35 * efficiency_ratio
                + 0.25 * schema_compliance_rate
                + 0.20 * non_redundancy_rate
                + 0.20 * recovery_rate
            )
            * 100.0
            - 25.0 * float(total_loops)
        )
        composite = max(0.0, min(100.0, raw_composite))
        if not trace.terminal_task_success:
            composite = min(composite, 40.0)
        composite = round(composite, 2)

        hard_gates = {
            "non_empty_trace": True,
            "loop_count_zero": total_loops == 0,
            "optimal_steps_available": optimal_avail,
            "efficiency_floor": efficiency_ratio >= 0.50,
            "schema_compliance_floor": schema_compliance_rate >= 0.85,
            "zero_unresolved_errors": unresolved_error_count == 0,
            "terminal_task_success": bool(trace.terminal_task_success),
            "composite_floor": composite >= 70.0,
        }
        return TrajectoryScorecard(
            trace_id=trace.trace_id,
            total_steps=total_steps,
            optimal_step_count=trace.optimal_step_count,
            efficiency_ratio=round(efficiency_ratio, 4),
            schema_compliance_rate=round(schema_compliance_rate, 4),
            non_redundancy_rate=round(non_redundancy_rate, 4),
            recovery_rate=round(recovery_rate, 4),
            loop_count=loop_count,
            oscillation_count=oscillation_count,
            unresolved_error_count=unresolved_error_count,
            terminal_task_success=bool(trace.terminal_task_success),
            composite_score=composite,
            hard_gates=hard_gates,
            passed=all(hard_gates.values()),
            step_verdicts=step_verdicts,
        )


def steps_from_trace_dicts(raw_steps: Sequence[Mapping[str, Any]]) -> list[TrajectoryStep]:
    """Convert RunTrace trajectory_steps dictionaries into typed TrajectoryStep instances."""
    out: list[TrajectoryStep] = []
    for idx, item in enumerate(raw_steps):
        action = str(item.get("action_type") or "tool_call")
        status = str(item.get("status") or "SUCCESS").upper()
        out.append(
            TrajectoryStep(
                step_index=int(item.get("step_index", idx)),
                action_type=action,  # type: ignore[arg-type]
                target=str(item.get("target") or "unknown"),
                arguments=dict(item.get("arguments") or {}),
                status=status,  # type: ignore[arg-type]
                latency_ms=float(item.get("latency_ms", 0.0)),
                error_code=item.get("error_code"),
            )
        )
    return out
