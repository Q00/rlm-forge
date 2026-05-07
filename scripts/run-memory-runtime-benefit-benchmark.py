#!/usr/bin/env python3
"""Run a deterministic memory-runtime benefit benchmark.

This benchmark does not call Hermes. It isolates a narrow runtime question:
when a provider/family has a known evidence-handle omission failure mode, can a
guarded operational memory prior improve the runtime contract before repair?

The measured benefit is runtime-control performance, not model quality:

- higher initial TraceGuard acceptance;
- fewer repair calls;
- fewer total parent/repair operations;
- unchanged final evidence discipline.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import product
import json
from pathlib import Path
from typing import Any

from rlm_forge.traceguard import TraceGuardEvidence
from rlm_forge.traceguard import validate_parent_synthesis


FIXTURE_CATEGORIES = (
    "simple_truncation",
    "distractor_heavy",
    "cross_chunk_dependency",
    "omitted_fact_temptation",
    "chunk_only_citation_trap",
)
PROVIDER_PROFILES = (
    "schema_stable",
    "missing_handle_prone",
    "chunk_only_prone",
    "answer_memory_contaminated",
)
POLICIES = (
    "no_memory",
    "guarded_operational_memory_prior",
    "unsafe_answer_memory_prior",
)


def _fixture(category: str, variant: int) -> dict[str, Any]:
    fixture_id = f"memory-runtime-{category}-{variant:02d}"
    facts: list[dict[str, str]] = []
    for index in range(1, 5):
        fact_id = f"MR-{variant:02d}-{index:03d}"
        chunk_id = f"{fixture_id}.txt:{index}-{index}"
        facts.append(
            {
                "fact_id": fact_id,
                "chunk_id": chunk_id,
                "text": (
                    f"{category} fixture {variant} retained fact {index} "
                    "must keep fact_id attached to evidence_chunk_id."
                ),
            }
        )
    return {
        "fixture_id": fixture_id,
        "fixture_category": category,
        "expected_retained_facts": facts,
    }


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


def _base_parent_synthesis(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = fixture["expected_retained_facts"]
    return {
        "mode": "rlm_forge_parent_synthesis",
        "verdict": "pass",
        "confidence": 0.95,
        "result": {
            "summary": (
                "Parent synthesis uses child evidence with fact-level handles."
            ),
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
    parent = json.loads(json.dumps(parent))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    return parent


def _chunk_only_reference(parent: dict[str, Any]) -> dict[str, Any]:
    parent = json.loads(json.dumps(parent))
    parent["evidence_references"] = [
        {"chunk_id": item["chunk_id"], "claim": f"read {item['chunk_id']}"}
        for item in parent["evidence_references"]
    ]
    parent["result"].pop("retained_facts", None)
    return parent


def _contaminate_from_answer_memory(parent: dict[str, Any]) -> dict[str, Any]:
    parent = json.loads(json.dumps(parent))
    parent["result"]["retained_facts"].append(
        {
            "fact_id": "MEMORY-ANSWER-001",
            "text": "A durable memory entry said this answer should be retained.",
            "evidence_chunk_id": "memory://unsafe-answer-prior",
        }
    )
    return parent


def _initial_parent_synthesis(
    *,
    fixture: dict[str, Any],
    provider_profile: str,
    policy_id: str,
) -> dict[str, Any]:
    parent = _base_parent_synthesis(fixture)

    if policy_id == "guarded_operational_memory_prior":
        return parent

    if policy_id == "unsafe_answer_memory_prior":
        return _contaminate_from_answer_memory(parent)

    if policy_id != "no_memory":
        msg = f"unknown policy: {policy_id}"
        raise ValueError(msg)

    if provider_profile == "schema_stable":
        return parent
    if provider_profile == "missing_handle_prone":
        return _omit_one_handle(parent)
    if provider_profile == "chunk_only_prone":
        return _chunk_only_reference(parent)
    if provider_profile == "answer_memory_contaminated":
        return _contaminate_from_answer_memory(parent)

    msg = f"unknown provider profile: {provider_profile}"
    raise ValueError(msg)


def _repair_missing_handles(
    *,
    parent_synthesis: dict[str, Any],
    manifest: tuple[TraceGuardEvidence, ...],
) -> dict[str, Any]:
    repaired = json.loads(json.dumps(parent_synthesis))
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


def _run_case(
    *,
    fixture: dict[str, Any],
    provider_profile: str,
    policy_id: str,
) -> dict[str, Any]:
    manifest = _manifest(fixture)
    initial_parent = _initial_parent_synthesis(
        fixture=fixture,
        provider_profile=provider_profile,
        policy_id=policy_id,
    )
    initial = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=initial_parent,
    )
    repair_attempted = False
    final = initial
    repairable = (
        not initial.accepted
        and {rejection.reason for rejection in initial.rejected_claims}
        == {"missing_evidence_handle"}
    )
    if repairable:
        repair_attempted = True
        repaired = _repair_missing_handles(
            parent_synthesis=initial_parent,
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
        "initial_traceguard_accepted": initial.accepted,
        "initial_rejection_reasons": sorted(
            {rejection.reason for rejection in initial.rejected_claims}
        ),
        "repair_attempted": repair_attempted,
        "final_traceguard_accepted": final.accepted,
        "final_unsupported_claim_rate": final.unsupported_claim_rate,
        "parent_synthesis_calls": 1,
        "repair_calls": 1 if repair_attempted else 0,
        "total_parent_repair_calls": 1 + (1 if repair_attempted else 0),
    }


def _run_benchmark() -> dict[str, Any]:
    fixtures = [
        _fixture(category, variant)
        for category, variant in product(FIXTURE_CATEGORIES, range(1, 5))
    ]
    evaluations = [
        _run_case(
            fixture=fixture,
            provider_profile=provider_profile,
            policy_id=policy_id,
        )
        for fixture, provider_profile, policy_id in product(
            fixtures,
            PROVIDER_PROFILES,
            POLICIES,
        )
    ]
    return {
        "schema_version": "rlm.memory_runtime_benefit_benchmark.v1",
        "description": (
            "Deterministic runtime-control benchmark showing that guarded "
            "operational memory priors can reduce repair work for known "
            "schema failure modes without making memory admissible evidence."
        ),
        "fixture_count": len(fixtures),
        "provider_profile_count": len(PROVIDER_PROFILES),
        "policy_count": len(POLICIES),
        "evaluation_count": len(evaluations),
        "dimensions": {
            "fixture_categories": list(FIXTURE_CATEGORIES),
            "provider_profiles": list(PROVIDER_PROFILES),
            "policies": list(POLICIES),
        },
        "policy_summary": _policy_summary(evaluations),
        "provider_policy_summary": _provider_policy_summary(evaluations),
        "evaluations": evaluations,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4)


def _policy_summary(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evaluations:
        by_policy[row["policy_id"]].append(row)
    return [_summary_row(policy_id, by_policy[policy_id]) for policy_id in POLICIES]


def _provider_policy_summary(
    evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in evaluations:
        by_key[(row["provider_profile"], row["policy_id"])].append(row)
    return [
        {
            "provider_profile": provider_profile,
            **_summary_row(policy_id, by_key[(provider_profile, policy_id)]),
        }
        for provider_profile, policy_id in product(PROVIDER_PROFILES, POLICIES)
    ]


def _summary_row(policy_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "evaluation_count": len(rows),
        "initial_traceguard_accept_rate": _mean(
            [1.0 if row["initial_traceguard_accepted"] else 0.0 for row in rows]
        ),
        "final_traceguard_accept_rate": _mean(
            [1.0 if row["final_traceguard_accepted"] else 0.0 for row in rows]
        ),
        "mean_repair_calls": _mean([row["repair_calls"] for row in rows]),
        "mean_total_parent_repair_calls": _mean(
            [row["total_parent_repair_calls"] for row in rows]
        ),
        "mean_final_unsupported_claim_rate": _mean(
            [row["final_unsupported_claim_rate"] for row in rows]
        ),
    }


def _markdown_report(benchmark: dict[str, Any]) -> str:
    lines = [
        "# Memory Runtime Benefit Benchmark",
        "",
        "Hermes is not called. This deterministic benchmark isolates a narrow",
        "runtime-control performance question: can guarded operational memory",
        "priors reduce repair work for known schema failure modes while preserving",
        "the fresh-evidence boundary?",
        "",
        f"- Fixtures: `{benchmark['fixture_count']}`",
        f"- Provider profiles: `{benchmark['provider_profile_count']}`",
        f"- Policies: `{benchmark['policy_count']}`",
        f"- Evaluations: `{benchmark['evaluation_count']}`",
        "",
        "## Policy Summary",
        "",
        "| Policy | N | Initial accept | Final accept | Mean repairs | Mean parent+repair calls | Final unsupported rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in benchmark["policy_summary"]:
        lines.append(
            "| {policy} | {count} | {initial:.4f} | {final:.4f} | "
            "{repairs:.4f} | {calls:.4f} | {unsupported:.4f} |".format(
                policy=row["policy_id"],
                count=row["evaluation_count"],
                initial=row["initial_traceguard_accept_rate"],
                final=row["final_traceguard_accept_rate"],
                repairs=row["mean_repair_calls"],
                calls=row["mean_total_parent_repair_calls"],
                unsupported=row["mean_final_unsupported_claim_rate"],
            )
        )

    lines.extend(
        [
            "",
            "## Provider Profile Detail",
            "",
            "| Provider profile | Policy | Initial accept | Final accept | Mean repairs | Mean calls |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in benchmark["provider_policy_summary"]:
        lines.append(
            "| {provider} | {policy} | {initial:.4f} | {final:.4f} | "
            "{repairs:.4f} | {calls:.4f} |".format(
                provider=row["provider_profile"],
                policy=row["policy_id"],
                initial=row["initial_traceguard_accept_rate"],
                final=row["final_traceguard_accept_rate"],
                repairs=row["mean_repair_calls"],
                calls=row["mean_total_parent_repair_calls"],
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The guarded operational memory prior represents a schema/retry prior,",
            "not answer evidence. In this controlled benchmark it makes the parent",
            "synthesis use fact-level evidence handles from the start. That raises",
            "initial TraceGuard acceptance and removes the repair call required by",
            "the missing-handle-prone no-memory policy.",
            "",
            "The unsafe answer-memory policy is intentionally different. It models",
            "a contaminated memory that tries to add an answer fact. TraceGuard",
            "rejects it as unsupported, demonstrating why memory must remain a",
            "prior over how to ask for evidence rather than evidence itself.",
            "",
            "This benchmark supports a runtime performance claim only: guarded",
            "operational memory can reduce validation/repair work for known schema",
            "failure modes. It does not show model-quality, latency, token, or cost",
            "improvement in live providers.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory for JSON and Markdown benchmark outputs.",
    )
    args = parser.parse_args()

    benchmark = _run_benchmark()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "memory-runtime-benefit-benchmark.json"
    md_path = args.output_dir / "memory-runtime-benefit-benchmark.md"
    json_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(benchmark), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
