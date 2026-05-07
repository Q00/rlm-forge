#!/usr/bin/env python3
"""Exercise the in-process TraceGuard gate for project-local ``ooo rlm``.

This experiment does not rerun Hermes. It validates the exact persisted paper
``ooo rlm`` parent output through the same adapter now installed by the
project-local ``uv run ooo rlm`` / ``uv run ouroboros rlm`` wrappers, then
checks deterministic safe and unsafe parent variants.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from rlm_forge.ooo_rlm_traceguard import validate_ooo_rlm_result
from rlm_forge.ooo_rlm_traceguard import install_ouroboros_rlm_cli_gate


DEFAULT_INPUT = Path("experiments/paper-key-sections-ooo-rlm-demo.json")
DEFAULT_JSON_OUTPUT = Path("experiments/ooo-rlm-inprocess-traceguard-gate.json")
DEFAULT_MD_OUTPUT = Path("experiments/ooo-rlm-inprocess-traceguard-gate.md")


@dataclass(frozen=True, slots=True)
class ChildRecord:
    order: int
    chunk_id: str | None
    call_id: str | None
    result_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParentState:
    parent_node_id: str
    children: tuple[ChildRecord, ...]

    def ordered_child_results(self) -> tuple[ChildRecord, ...]:
        return tuple(sorted(self.children, key=lambda child: child.order))


@dataclass(frozen=True, slots=True)
class ParentSubcall:
    completion: str


@dataclass(frozen=True, slots=True)
class AtomicExecution:
    hermes_subcall: ParentSubcall
    parent_execution_state: ParentState


@dataclass(frozen=True, slots=True)
class RunResult:
    atomic_execution: AtomicExecution


def _child_call_id(order: int) -> str:
    return f"rlm_call_atomic_chunk_{order + 1:03d}"


def _demo_result(demo: dict[str, Any], parent_output: dict[str, Any]) -> RunResult:
    children: list[ChildRecord] = []
    for index, record in enumerate(demo.get("child_records", [])):
        if not isinstance(record, dict):
            continue
        order = record.get("order", index)
        if isinstance(order, bool) or not isinstance(order, int):
            order = index
        completion = record.get("completion")
        result_payload: dict[str, Any] = {}
        if isinstance(completion, dict):
            result_payload = {
                "reported_result": completion.get("result"),
                "completion": json.dumps(completion, sort_keys=True),
            }
        elif isinstance(completion, str):
            result_payload = {"completion": completion}
        children.append(
            ChildRecord(
                order=order,
                chunk_id=record.get("chunk_id") if isinstance(record.get("chunk_id"), str) else None,
                call_id=_child_call_id(order),
                result_payload=result_payload,
            )
        )

    parent_record = demo.get("parent_record", {})
    parent_completion = parent_record.get("completion") if isinstance(parent_record, dict) else {}
    result = parent_output.get("result")
    if not isinstance(result, dict) and isinstance(parent_completion, dict):
        result = parent_completion.get("result")
    parent_node_id = "rlm_node_root"
    if isinstance(result, dict) and isinstance(result.get("parent_node_id"), str):
        parent_node_id = result["parent_node_id"]

    return RunResult(
        atomic_execution=AtomicExecution(
            hermes_subcall=ParentSubcall(completion=json.dumps(parent_output, sort_keys=True)),
            parent_execution_state=ParentState(
                parent_node_id=parent_node_id,
                children=tuple(children),
            ),
        )
    )


def _raw_parent_output(demo: dict[str, Any]) -> dict[str, Any]:
    parent_record = demo.get("parent_record")
    if not isinstance(parent_record, dict):
        raise ValueError("demo artifact has no parent_record object")
    completion = parent_record.get("completion")
    if not isinstance(completion, dict):
        raise ValueError("demo parent_record has no structured completion")
    return completion


def _handle_repaired_parent_output(demo: dict[str, Any]) -> dict[str, Any]:
    raw = json.loads(json.dumps(_raw_parent_output(demo)))
    result = raw.setdefault("result", {})
    result["key_synthesized_claims"] = [
        {
            "claim": claim.get("text"),
            "supported_by_child_result_ids": _repair_demo_child_ids(
                claim.get("supporting_child_result_ids", [])
            ),
        }
        for claim in demo.get("accepted_claims", [])
        if isinstance(claim, dict)
    ]
    result.pop("retained_facts", None)
    raw.pop("evidence_references", None)
    return raw


def _repair_demo_child_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    repaired = []
    for item in value:
        if item == "rlm_node_root:child_result:004":
            repaired.append("rlm_node_root:child_result:003")
        elif isinstance(item, str):
            repaired.append(item)
    return repaired


def _unsafe_memory_parent_output(demo: dict[str, Any]) -> dict[str, Any]:
    unsafe = _handle_repaired_parent_output(demo)
    result = unsafe.setdefault("result", {})
    retained = result.setdefault("retained_facts", [])
    if not isinstance(retained, list):
        retained = []
        result["retained_facts"] = retained
    retained.append(
        {
            "fact_id": "MEMORY-ANSWER-INPROCESS-001",
            "text": "Memory says the paper proves a live quality win.",
            "evidence_chunk_id": "memory://hermes/MEMORY.md",
        }
    )
    return unsafe


def _run(input_path: Path) -> dict[str, Any]:
    demo = json.loads(input_path.read_text(encoding="utf-8"))
    patch_installed = install_ouroboros_rlm_cli_gate()

    cases = []
    for case_id, parent_output in (
        ("raw_persisted_parent", _raw_parent_output(demo)),
        ("handle_repaired_parent", _handle_repaired_parent_output(demo)),
        ("handle_repaired_parent_plus_memory_answer", _unsafe_memory_parent_output(demo)),
    ):
        gate = validate_ooo_rlm_result(_demo_result(demo, parent_output))
        cases.append(
            {
                "case_id": case_id,
                "status": gate.status,
                "accepted": gate.accepted,
                "reason": gate.reason,
                "validation": gate.validation.to_dict() if gate.validation else None,
            }
        )

    return {
        "schema_version": "rlm_forge.ooo_rlm_inprocess_traceguard_gate.v1",
        "source_demo": str(input_path),
        "source_command": demo.get("command"),
        "patch_installed": patch_installed,
        "case_count": len(cases),
        "cases": cases,
        "conclusion": {
            "wrapper_installs_inprocess_gate": True,
            "raw_parent_gate_rejects_bad_child_handle": _case(cases, "raw_persisted_parent")[
                "accepted"
            ]
            is False,
            "handle_repaired_parent_accepts": _case(cases, "handle_repaired_parent")[
                "accepted"
            ]
            is True,
            "memory_answer_rejected": _case(
                cases,
                "handle_repaired_parent_plus_memory_answer",
            )["accepted"]
            is False,
        },
    }


def _case(cases: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    for case in cases:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)


def _reasons(case: dict[str, Any]) -> str:
    validation = case.get("validation")
    if not isinstance(validation, dict):
        return case.get("reason") or "none"
    reasons = sorted(
        {
            item.get("reason", "unknown")
            for item in validation.get("rejected_claims", [])
            if isinstance(item, dict)
        }
    )
    return ", ".join(reasons) or "none"


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# ooo rlm In-Process TraceGuard Gate",
        "",
        "This artifact exercises the same adapter installed by the project-local",
        "`uv run ooo rlm` and `uv run ouroboros rlm` entrypoints. It uses the",
        "persisted paper run so the experiment is deterministic and does not",
        "rerun Hermes.",
        "",
        "## Source",
        "",
        f"- Demo artifact: `{result['source_demo']}`",
        f"- Source command: `{result['source_command']}`",
        f"- Process-local patch installed in experiment: `{str(result['patch_installed']).lower()}`",
        "",
        "## Cases",
        "",
        "| Case | Accepted | Unsupported rate | Rejection reasons |",
        "| --- | ---: | ---: | --- |",
    ]
    for case in result["cases"]:
        validation = case.get("validation") or {}
        rate = validation.get("unsupported_claim_rate", 0.0)
        lines.append(
            "| {case_id} | {accepted} | {rate:.4f} | {reasons} |".format(
                case_id=case["case_id"],
                accepted=str(case["accepted"]).lower(),
                rate=rate,
                reasons=_reasons(case),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The in-process gate is stricter than the earlier normalized post-run",
            "artifact. It rejects the raw persisted parent because that parent cites",
            "`rlm_node_root:child_result:004`, while the actual run produced child",
            "results `000..003`. After repairing that handle to the actual fresh",
            "child manifest, the same evidence boundary accepts. When a memory-answer",
            "fact is injected into the repaired parent, the gate rejects it because",
            "the fact is not present in the current run's child evidence manifest.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    args = parser.parse_args()

    result = _run(args.input)
    args.json_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.md_output.write_text(_markdown(result), encoding="utf-8")
    print(f"Wrote {args.json_output}")
    print(f"Wrote {args.md_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
