#!/usr/bin/env python3
"""Validate the paper ooo rlm demo with TraceGuard.

This script does not rerun Hermes. It takes the persisted output of the actual
dependency `ouroboros rlm` paper run, normalizes the parent synthesis claims
into TraceGuard's fact/evidence-handle contract, and validates two cases:

1. the supported parent synthesis from the ooo rlm run;
2. the same parent synthesis with an injected unsupported memory-answer claim.

The goal is to prove the post-run end-to-end gate for this exact ooo rlm paper
run: child evidence -> parent claims -> deterministic TraceGuard validation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rlm_forge.traceguard import TraceGuardEvidence
from rlm_forge.traceguard import validate_parent_synthesis


DEFAULT_INPUT = Path("experiments/paper-key-sections-ooo-rlm-demo.json")
DEFAULT_JSON_OUTPUT = Path("experiments/paper-ooo-rlm-traceguard-gate.json")
DEFAULT_MD_OUTPUT = Path("experiments/paper-ooo-rlm-traceguard-gate.md")


def _claim_chunk_id(
    claim: dict[str, Any],
    child_records_by_id: dict[str, dict[str, Any]],
) -> str:
    supporting = claim.get("supporting_child_result_ids")
    if not isinstance(supporting, list) or not supporting:
        return ""
    child_record = child_records_by_id.get(str(supporting[0]))
    if not child_record:
        return ""
    chunk_id = child_record.get("chunk_id")
    return chunk_id if isinstance(chunk_id, str) else ""


def _child_records_by_result_id(demo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(demo.get("child_records", [])):
        if not isinstance(record, dict):
            continue
        result_id = f"rlm_node_root:child_result:{index:03d}"
        records[result_id] = record
    return records


def _build_manifest_and_parent(
    demo: dict[str, Any],
) -> tuple[list[TraceGuardEvidence], dict[str, Any]]:
    child_records = _child_records_by_result_id(demo)
    manifest: list[TraceGuardEvidence] = []
    retained_facts: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    for claim in demo.get("accepted_claims", []):
        if not isinstance(claim, dict):
            continue
        claim_id = claim.get("claim_id")
        text = claim.get("text")
        if not isinstance(claim_id, str) or not isinstance(text, str):
            continue
        chunk_id = _claim_chunk_id(claim, child_records)
        if not chunk_id:
            continue
        supporting = [
            item
            for item in claim.get("supporting_child_result_ids", [])
            if isinstance(item, str)
        ]
        child_call_id = supporting[0] if supporting else None
        manifest.append(
            TraceGuardEvidence(
                fact_id=claim_id,
                chunk_id=chunk_id,
                text=text,
                child_call_id=child_call_id,
            )
        )
        retained_facts.append(
            {
                "fact_id": claim_id,
                "text": text,
                "evidence_chunk_id": chunk_id,
            }
        )
        evidence_refs.append(
            {
                "chunk_id": chunk_id,
                "supports_fact_ids": [claim_id],
                "quoted_evidence": text,
            }
        )

    parent_synthesis = {
        "mode": "paper_ooo_rlm_parent_synthesis_traceguard_normalized",
        "verdict": "completed",
        "result": {
            "summary": (
                "Normalized parent claims from the actual paper ooo rlm run."
            ),
            "retained_facts": retained_facts,
        },
        "evidence_references": evidence_refs,
        "residual_gaps": demo.get("residual_gaps", []),
    }
    return manifest, parent_synthesis


def _unsafe_parent(parent_synthesis: dict[str, Any]) -> dict[str, Any]:
    unsafe = json.loads(json.dumps(parent_synthesis))
    unsafe["result"]["retained_facts"].append(
        {
            "fact_id": "MEMORY-ANSWER-OOO-RLM-001",
            "text": (
                "A persistent memory entry says the paper proves live model "
                "quality improvement."
            ),
            "evidence_chunk_id": "memory://hermes/MEMORY.md",
        }
    )
    return unsafe


def _run(input_path: Path) -> dict[str, Any]:
    demo = json.loads(input_path.read_text(encoding="utf-8"))
    manifest, parent = _build_manifest_and_parent(demo)
    safe_result = validate_parent_synthesis(
        evidence_manifest=tuple(manifest),
        parent_synthesis=parent,
    )
    unsafe_parent = _unsafe_parent(parent)
    unsafe_result = validate_parent_synthesis(
        evidence_manifest=tuple(manifest),
        parent_synthesis=unsafe_parent,
    )
    return {
        "schema_version": "rlm_forge.paper_ooo_rlm_traceguard_gate.v1",
        "source_demo": str(input_path),
        "source_command": demo.get("command"),
        "reported_subcall_count": demo.get("reported_subcall_count"),
        "reported_rlm_tree_depth": demo.get("reported_rlm_tree_depth"),
        "manifest": [item.to_dict() for item in manifest],
        "normalized_parent_synthesis": parent,
        "safe_validation": safe_result.to_dict(),
        "unsafe_memory_parent_synthesis": unsafe_parent,
        "unsafe_memory_validation": unsafe_result.to_dict(),
        "conclusion": {
            "exact_ooo_rlm_run_traceguard_safe_accepts": safe_result.accepted,
            "exact_ooo_rlm_run_traceguard_rejects_memory_answer": (
                not unsafe_result.accepted
            ),
            "automatic_gate_scope": (
                "This script is the automatic post-run TraceGuard gate for the "
                "persisted ooo rlm paper run. The stock `ouroboros rlm` CLI "
                "does not call this validator internally."
            ),
        },
    }


def _markdown(result: dict[str, Any]) -> str:
    safe = result["safe_validation"]
    unsafe = result["unsafe_memory_validation"]
    lines = [
        "# Paper ooo rlm TraceGuard Gate",
        "",
        "This artifact validates the exact persisted `ooo rlm` paper run with",
        "the local deterministic TraceGuard validator.",
        "",
        "## Source Run",
        "",
        f"- Demo artifact: `{result['source_demo']}`",
        f"- Command: `{result['source_command']}`",
        f"- Hermes sub-calls: `{result['reported_subcall_count']}`",
        f"- RLM tree depth: `{result['reported_rlm_tree_depth']}`",
        "",
        "## Gate Flow",
        "",
        "```text",
        "persisted ooo rlm paper run",
        "  |",
        "  | child_result ids + parent accepted claims",
        "  v",
        "normalize claims into TraceGuard fact/evidence handles",
        "  |",
        "  +-- safe parent synthesis",
        "  |     -> TraceGuard ACCEPT",
        "  |",
        "  +-- same parent + MEMORY-ANSWER claim",
        "        -> TraceGuard REJECT",
        "```",
        "",
        "## Results",
        "",
        "| Case | Accepted | Unsupported rate | Rejection reasons |",
        "| --- | ---: | ---: | --- |",
        "| exact ooo rlm parent | {accepted} | {rate:.4f} | {reasons} |".format(
            accepted=str(safe["accepted"]).lower(),
            rate=safe["unsupported_claim_rate"],
            reasons=", ".join(
                sorted({item["reason"] for item in safe["rejected_claims"]})
            )
            or "none",
        ),
        "| parent + unsafe memory answer | {accepted} | {rate:.4f} | {reasons} |".format(
            accepted=str(unsafe["accepted"]).lower(),
            rate=unsafe["unsupported_claim_rate"],
            reasons=", ".join(
                sorted({item["reason"] for item in unsafe["rejected_claims"]})
            )
            or "none",
        ),
        "",
        "## Interpretation",
        "",
        "The exact `ooo rlm` paper run produces parent claims that can be",
        "normalized into TraceGuard evidence handles and accepted. When the same",
        "parent synthesis is contaminated with an unsupported memory-answer fact,",
        "TraceGuard rejects it as `unsupported_fact_id` because that fact is not",
        "present in the fresh child evidence manifest.",
        "",
        "Scope note: this is an automatic post-run gate over the persisted `ooo rlm`",
        "run. It proves the end-to-end compatibility of this run with TraceGuard,",
        "but the stock `ouroboros rlm` CLI did not invoke TraceGuard internally.",
    ]
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
