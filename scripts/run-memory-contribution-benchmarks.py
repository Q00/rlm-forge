#!/usr/bin/env python3
"""Run deterministic memory contribution benchmarks.

These benchmarks do not call Hermes. They isolate three systems questions:

1. Can TraceGuard prevent answer-memory contamination from becoming accepted
   evidence?
2. Do Hermes-style prompt memory and RLM-FORGE guarded memory have separable
   runtime roles?
3. Can adaptive operational memory reduce repeated repair work across related
   tasks?

The measured benefit is runtime-control performance, not live model quality.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import product
import json
from pathlib import Path
from typing import Any

from rlm_forge.traceguard import TraceGuardEvidence
from rlm_forge.traceguard import TraceGuardResult
from rlm_forge.traceguard import validate_parent_synthesis


FIXTURE_CATEGORIES = (
    "policy_summary",
    "incident_report",
    "repo_architecture",
    "experiment_notes",
)


def _copy_json(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _fixture(category: str, variant: int) -> dict[str, Any]:
    fixture_id = f"memory-contribution-{category}-{variant:02d}"
    facts: list[dict[str, str]] = []
    for index in range(1, 4):
        fact_id = f"MC-{variant:02d}-{index:03d}"
        chunk_id = f"{fixture_id}.txt:{index}-{index}"
        facts.append(
            {
                "fact_id": fact_id,
                "chunk_id": chunk_id,
                "text": (
                    f"{category} fixture {variant} supported fact {index} "
                    "requires a fact_id and evidence_chunk_id pair."
                ),
            }
        )
    return {
        "fixture_id": fixture_id,
        "fixture_category": category,
        "expected_retained_facts": facts,
    }


def _fixtures(variants: int = 3) -> list[dict[str, Any]]:
    return [
        _fixture(category, variant)
        for category, variant in product(FIXTURE_CATEGORIES, range(1, variants + 1))
    ]


def _manifest(fixture: dict[str, Any]) -> tuple[TraceGuardEvidence, ...]:
    return tuple(
        TraceGuardEvidence(
            fact_id=fact["fact_id"],
            chunk_id=fact["chunk_id"],
            text=fact["text"],
            child_call_id=f"{fixture['fixture_id']}::child::{index}",
        )
        for index, fact in enumerate(fixture["expected_retained_facts"], start=1)
    )


def _base_parent(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = fixture["expected_retained_facts"]
    return {
        "mode": "rlm_forge_parent_synthesis",
        "verdict": "pass",
        "confidence": 0.94,
        "result": {
            "summary": "Parent synthesis cites fresh child evidence.",
            "retained_facts": [
                {
                    "fact_id": fact["fact_id"],
                    "text": fact["text"],
                    "evidence_chunk_id": fact["chunk_id"],
                }
                for fact in retained
            ],
        },
        "evidence_references": [
            {
                "chunk_id": fact["chunk_id"],
                "supports_fact_ids": [fact["fact_id"]],
                "quoted_evidence": fact["text"],
            }
            for fact in retained
        ],
        "residual_gaps": [],
    }


def _omit_one_handle(parent: dict[str, Any]) -> dict[str, Any]:
    parent = _copy_json(parent)
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    return parent


def _chunk_only(parent: dict[str, Any]) -> dict[str, Any]:
    parent = _copy_json(parent)
    parent["result"].pop("retained_facts", None)
    parent["evidence_references"] = [
        {"chunk_id": item["chunk_id"], "claim": f"chunk {item['chunk_id']} supports it"}
        for item in parent["evidence_references"]
    ]
    return parent


def _contaminate(parent: dict[str, Any], *, source: str) -> dict[str, Any]:
    parent = _copy_json(parent)
    parent["result"]["retained_facts"].append(
        {
            "fact_id": "MEMORY-ANSWER-001",
            "text": f"Persistent {source} memory asserted an unsupported answer.",
            "evidence_chunk_id": f"memory://{source}/answer-prior",
        }
    )
    return parent


def _repair_missing_handles(
    *,
    parent_synthesis: dict[str, Any],
    manifest: tuple[TraceGuardEvidence, ...],
) -> dict[str, Any]:
    repaired = _copy_json(parent_synthesis)
    handles = {item.fact_id: item.chunk_id for item in manifest}
    retained = repaired.get("result", {}).get("retained_facts", [])
    if not isinstance(retained, list):
        return repaired
    for fact in retained:
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("fact_id")
        if isinstance(fact_id, str) and not fact.get("evidence_chunk_id"):
            fact["evidence_chunk_id"] = handles.get(fact_id)
    return repaired


def _validate_or_accept_all(
    *,
    evidence_manifest: tuple[TraceGuardEvidence, ...],
    parent_synthesis: dict[str, Any],
    traceguard_enabled: bool,
) -> TraceGuardResult | None:
    if traceguard_enabled:
        return validate_parent_synthesis(
            evidence_manifest=evidence_manifest,
            parent_synthesis=parent_synthesis,
        )
    return None


def _claim_has_memory_answer(parent_synthesis: dict[str, Any]) -> bool:
    retained = parent_synthesis.get("result", {}).get("retained_facts", [])
    if not isinstance(retained, list):
        return False
    return any(
        isinstance(fact, dict)
        and str(fact.get("fact_id", "")).startswith("MEMORY-ANSWER")
        for fact in retained
    )


def _accepted(
    *,
    validation: TraceGuardResult | None,
    traceguard_enabled: bool,
) -> bool:
    return validation.accepted if traceguard_enabled and validation else True


def _rejection_reasons(validation: TraceGuardResult | None) -> list[str]:
    if validation is None:
        return []
    return sorted({rejection.reason for rejection in validation.rejected_claims})


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4)


def _summarize(
    rows: list[dict[str, Any]],
    *,
    key_field: str,
    key_order: tuple[str, ...],
) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_key[row[key_field]].append(row)
    return [_summary_row(key_field, key, by_key[key]) for key in key_order]


def _summary_row(key_field: str, key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        key_field: key,
        "evaluation_count": len(rows),
        "initial_traceguard_accept_rate": _mean(
            [1.0 if row["initial_traceguard_accepted"] else 0.0 for row in rows]
        ),
        "final_traceguard_accept_rate": _mean(
            [1.0 if row["final_traceguard_accepted"] else 0.0 for row in rows]
        ),
        "accepted_memory_answer_rate": _mean(
            [1.0 if row["accepted_memory_answer"] else 0.0 for row in rows]
        ),
        "mean_repair_calls": _mean([row["repair_calls"] for row in rows]),
        "mean_total_parent_repair_calls": _mean(
            [row["total_parent_repair_calls"] for row in rows]
        ),
        "mean_final_unsupported_claim_rate": _mean(
            [row["final_unsupported_claim_rate"] for row in rows]
        ),
    }


CONTAMINATION_POLICIES = (
    "unguarded_no_memory",
    "unguarded_benign_memory",
    "unguarded_adversarial_memory",
    "traceguard_no_memory",
    "traceguard_benign_memory",
    "traceguard_adversarial_memory",
)


def _run_contamination_case(
    fixture: dict[str, Any],
    policy_id: str,
) -> dict[str, Any]:
    traceguard_enabled = policy_id.startswith("traceguard")
    adversarial = policy_id.endswith("adversarial_memory")
    parent = _base_parent(fixture)
    if adversarial:
        parent = _contaminate(parent, source="adversarial")
    manifest = _manifest(fixture)
    initial = _validate_or_accept_all(
        evidence_manifest=manifest,
        parent_synthesis=parent,
        traceguard_enabled=traceguard_enabled,
    )
    accepted = _accepted(validation=initial, traceguard_enabled=traceguard_enabled)
    has_memory_answer = _claim_has_memory_answer(parent)
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_category": fixture["fixture_category"],
        "policy_id": policy_id,
        "traceguard_enabled": traceguard_enabled,
        "memory_profile": (
            "adversarial_answer" if adversarial else "benign_or_absent"
        ),
        "initial_traceguard_accepted": accepted,
        "initial_rejection_reasons": _rejection_reasons(initial),
        "repair_attempted": False,
        "final_traceguard_accepted": accepted,
        "final_unsupported_claim_rate": (
            initial.unsupported_claim_rate if initial else 0.0
        ),
        "accepted_memory_answer": accepted and has_memory_answer,
        "repair_calls": 0,
        "total_parent_repair_calls": 1,
    }


def _run_contamination_benchmark() -> dict[str, Any]:
    fixtures = _fixtures()
    evaluations = [
        _run_contamination_case(fixture, policy_id)
        for fixture, policy_id in product(fixtures, CONTAMINATION_POLICIES)
    ]
    return {
        "schema_version": "rlm.memory_contamination_robustness_benchmark.v1",
        "description": (
            "Deterministic benchmark showing that TraceGuard prevents "
            "adversarial answer-memory contamination from becoming accepted "
            "parent synthesis state."
        ),
        "fixture_count": len(fixtures),
        "policy_count": len(CONTAMINATION_POLICIES),
        "evaluation_count": len(evaluations),
        "dimensions": {"policies": list(CONTAMINATION_POLICIES)},
        "policy_summary": _summarize(
            evaluations,
            key_field="policy_id",
            key_order=CONTAMINATION_POLICIES,
        ),
        "evaluations": evaluations,
    }


LAYERED_POLICIES = (
    "hermes_memory_off__rlm_memory_off",
    "hermes_memory_on__rlm_memory_off",
    "hermes_memory_off__rlm_memory_on",
    "hermes_memory_on__rlm_memory_on",
)
LAYERED_PROVIDER_PROFILES = (
    "schema_stable",
    "missing_handle_prone",
    "chunk_only_prone",
    "missing_handle_and_chunk_only_prone",
)


def _layered_parent(
    *,
    fixture: dict[str, Any],
    provider_profile: str,
    hermes_memory_on: bool,
    rlm_memory_on: bool,
) -> dict[str, Any]:
    parent = _base_parent(fixture)
    missing_handle = provider_profile in {
        "missing_handle_prone",
        "missing_handle_and_chunk_only_prone",
    }
    chunk_only = provider_profile in {
        "chunk_only_prone",
        "missing_handle_and_chunk_only_prone",
    }
    if missing_handle and not rlm_memory_on:
        parent = _omit_one_handle(parent)
    if chunk_only and not hermes_memory_on:
        parent = _chunk_only(parent)
    return parent


def _run_layered_case(
    *,
    fixture: dict[str, Any],
    provider_profile: str,
    policy_id: str,
) -> dict[str, Any]:
    hermes_memory_on = "hermes_memory_on" in policy_id
    rlm_memory_on = "rlm_memory_on" in policy_id
    manifest = _manifest(fixture)
    parent = _layered_parent(
        fixture=fixture,
        provider_profile=provider_profile,
        hermes_memory_on=hermes_memory_on,
        rlm_memory_on=rlm_memory_on,
    )
    initial = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=parent,
    )
    repair_attempted = False
    final = initial
    if (
        not initial.accepted
        and {rejection.reason for rejection in initial.rejected_claims}
        == {"missing_evidence_handle"}
    ):
        repair_attempted = True
        repaired = _repair_missing_handles(
            parent_synthesis=parent,
            manifest=manifest,
        )
        final = validate_parent_synthesis(
            evidence_manifest=manifest,
            parent_synthesis=repaired,
        )
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_category": fixture["fixture_category"],
        "provider_profile": provider_profile,
        "policy_id": policy_id,
        "hermes_memory_on": hermes_memory_on,
        "rlm_memory_on": rlm_memory_on,
        "initial_traceguard_accepted": initial.accepted,
        "initial_rejection_reasons": _rejection_reasons(initial),
        "repair_attempted": repair_attempted,
        "final_traceguard_accepted": final.accepted,
        "final_unsupported_claim_rate": final.unsupported_claim_rate,
        "accepted_memory_answer": False,
        "repair_calls": 1 if repair_attempted else 0,
        "total_parent_repair_calls": 1 + (1 if repair_attempted else 0),
    }


def _run_layered_benchmark() -> dict[str, Any]:
    fixtures = _fixtures()
    evaluations = [
        _run_layered_case(
            fixture=fixture,
            provider_profile=provider_profile,
            policy_id=policy_id,
        )
        for fixture, provider_profile, policy_id in product(
            fixtures,
            LAYERED_PROVIDER_PROFILES,
            LAYERED_POLICIES,
        )
    ]
    return {
        "schema_version": "rlm.layered_memory_ablation_benchmark.v1",
        "description": (
            "Deterministic 2x2 ablation separating Hermes-style prompt memory "
            "from RLM-FORGE guarded operational memory."
        ),
        "fixture_count": len(fixtures),
        "provider_profile_count": len(LAYERED_PROVIDER_PROFILES),
        "policy_count": len(LAYERED_POLICIES),
        "evaluation_count": len(evaluations),
        "dimensions": {
            "provider_profiles": list(LAYERED_PROVIDER_PROFILES),
            "policies": list(LAYERED_POLICIES),
        },
        "policy_summary": _summarize(
            evaluations,
            key_field="policy_id",
            key_order=LAYERED_POLICIES,
        ),
        "evaluations": evaluations,
    }


ADAPTIVE_POLICIES = (
    "no_adaptive_memory",
    "adaptive_repair_memory",
)


def _run_adaptive_policy(policy_id: str) -> list[dict[str, Any]]:
    memory_has_missing_handle_prior = False
    rows: list[dict[str, Any]] = []
    for task_index, fixture in enumerate(_fixtures(variants=2), start=1):
        manifest = _manifest(fixture)
        parent = _base_parent(fixture)
        if policy_id == "no_adaptive_memory" or not memory_has_missing_handle_prior:
            parent = _omit_one_handle(parent)
        initial = validate_parent_synthesis(
            evidence_manifest=manifest,
            parent_synthesis=parent,
        )
        repair_attempted = False
        final = initial
        if (
            not initial.accepted
            and {rejection.reason for rejection in initial.rejected_claims}
            == {"missing_evidence_handle"}
        ):
            repair_attempted = True
            if policy_id == "adaptive_repair_memory":
                memory_has_missing_handle_prior = True
            repaired = _repair_missing_handles(
                parent_synthesis=parent,
                manifest=manifest,
            )
            final = validate_parent_synthesis(
                evidence_manifest=manifest,
                parent_synthesis=repaired,
            )
        rows.append(
            {
                "task_index": task_index,
                "fixture_id": fixture["fixture_id"],
                "fixture_category": fixture["fixture_category"],
                "policy_id": policy_id,
                "memory_prior_active_before_call": (
                    policy_id == "adaptive_repair_memory"
                    and task_index > 1
                    and memory_has_missing_handle_prior
                ),
                "initial_traceguard_accepted": initial.accepted,
                "initial_rejection_reasons": _rejection_reasons(initial),
                "repair_attempted": repair_attempted,
                "final_traceguard_accepted": final.accepted,
                "final_unsupported_claim_rate": final.unsupported_claim_rate,
                "accepted_memory_answer": False,
                "repair_calls": 1 if repair_attempted else 0,
                "total_parent_repair_calls": 1 + (1 if repair_attempted else 0),
            }
        )
    return rows


def _run_adaptive_benchmark() -> dict[str, Any]:
    evaluations = [
        row
        for policy_id in ADAPTIVE_POLICIES
        for row in _run_adaptive_policy(policy_id)
    ]
    return {
        "schema_version": "rlm.adaptive_repair_memory_benchmark.v1",
        "description": (
            "Deterministic sequence benchmark showing that an operational "
            "memory prior learned from an initial missing-handle repair can "
            "reduce later repair calls."
        ),
        "task_count_per_policy": len(_fixtures(variants=2)),
        "policy_count": len(ADAPTIVE_POLICIES),
        "evaluation_count": len(evaluations),
        "dimensions": {"policies": list(ADAPTIVE_POLICIES)},
        "policy_summary": _summarize(
            evaluations,
            key_field="policy_id",
            key_order=ADAPTIVE_POLICIES,
        ),
        "evaluations": evaluations,
    }


def _markdown_table(summary: list[dict[str, Any]], key_field: str) -> list[str]:
    lines = [
        "| Policy | N | Initial accept | Final accept | Accepted memory-answer | Mean repairs | Mean calls | Final unsupported |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            "| {policy} | {count} | {initial:.4f} | {final:.4f} | "
            "{memory:.4f} | {repairs:.4f} | {calls:.4f} | {unsupported:.4f} |".format(
                policy=row[key_field],
                count=row["evaluation_count"],
                initial=row["initial_traceguard_accept_rate"],
                final=row["final_traceguard_accept_rate"],
                memory=row["accepted_memory_answer_rate"],
                repairs=row["mean_repair_calls"],
                calls=row["mean_total_parent_repair_calls"],
                unsupported=row["mean_final_unsupported_claim_rate"],
            )
        )
    return lines


def _report(
    *,
    title: str,
    benchmark: dict[str, Any],
    interpretation: list[str],
) -> str:
    lines = [
        f"# {title}",
        "",
        benchmark["description"],
        "",
    ]
    for key in (
        "fixture_count",
        "task_count_per_policy",
        "provider_profile_count",
        "policy_count",
        "evaluation_count",
    ):
        if key in benchmark:
            label = key.replace("_", " ").title()
            lines.append(f"- {label}: `{benchmark[key]}`")
    lines.extend(["", "## Policy Summary", ""])
    lines.extend(_markdown_table(benchmark["policy_summary"], "policy_id"))
    lines.extend(["", "## Interpretation", ""])
    lines.extend(interpretation)
    return "\n".join(lines) + "\n"


def _write_artifact(
    *,
    output_dir: Path,
    stem: str,
    title: str,
    benchmark: dict[str, Any],
    interpretation: list[str],
) -> None:
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        _report(title=title, benchmark=benchmark, interpretation=interpretation),
        encoding="utf-8",
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory for JSON and Markdown benchmark outputs.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    _write_artifact(
        output_dir=args.output_dir,
        stem="memory-contamination-robustness-benchmark",
        title="Memory Contamination Robustness Benchmark",
        benchmark=_run_contamination_benchmark(),
        interpretation=[
            "The adversarial-memory condition adds an unsupported answer fact from",
            "persistent memory. Without TraceGuard, that memory answer becomes",
            "accepted parent state. With TraceGuard, the same unsupported fact is",
            "rejected because it is absent from the fresh child evidence manifest.",
            "",
            "This supports the contribution that memory can be present in the",
            "runtime prompt without becoming admissible evidence.",
        ],
    )
    _write_artifact(
        output_dir=args.output_dir,
        stem="layered-memory-ablation-benchmark",
        title="Layered Memory Ablation Benchmark",
        benchmark=_run_layered_benchmark(),
        interpretation=[
            "This 2x2 ablation separates two memory roles. Hermes-style prompt",
            "memory models a formatting/schema-discipline prior that prevents",
            "chunk-only parent synthesis. RLM-FORGE guarded memory models an",
            "evidence-handle prior that prevents missing fact handles.",
            "",
            "The combined policy reaches full initial and final acceptance with no",
            "repair calls, while each single memory layer fixes only its assigned",
            "failure class. This is a deterministic role-separation result, not a",
            "live provider quality result.",
        ],
    )
    _write_artifact(
        output_dir=args.output_dir,
        stem="adaptive-repair-memory-benchmark",
        title="Adaptive Repair Memory Benchmark",
        benchmark=_run_adaptive_benchmark(),
        interpretation=[
            "The adaptive policy starts without a missing-handle prior. After the",
            "first TraceGuard rejection and repair, it records an operational prior",
            "that later parent calls should preserve fact_id/evidence_chunk_id",
            "pairs. Subsequent related tasks avoid the repair path.",
            "",
            "This supports the runtime-learning claim: memory improves repair",
            "efficiency across repeated task families while every final answer",
            "still depends on fresh child evidence.",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
