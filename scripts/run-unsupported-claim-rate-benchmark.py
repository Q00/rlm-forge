#!/usr/bin/env python3
"""Run an unsupported-claim-rate contract ablation.

This is a deterministic contract benchmark, not a live model benchmark. It
answers a narrower systems question: under the same generated truncation
fixtures, which execution contracts give the scorer enough structure to catch
or avoid omitted-fact claims?
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import product
import json
from pathlib import Path
from typing import Any

from ouroboros.rlm.baseline import RLM_VANILLA_BASELINE_MODE
from ouroboros.rlm.baseline import score_vanilla_truncation_baseline_completion


FACT_COUNTS = (8, 12, 16, 24)
RETAINED_FRACTIONS = (0.25, 0.50, 0.75)
DISTRACTOR_LINES = (0, 2)
OMITTED_TARGETS = ("first", "last", "all")

POLICIES = (
    "single_call_loose",
    "single_call_guarded",
    "flat_map_reduce_chunk_only",
    "flat_map_reduce_with_leak",
    "hermes_rlm_evidence_gated",
    "hermes_rlm_without_gate",
)

POLICY_SUBCALLS = {
    "single_call_loose": 1,
    "single_call_guarded": 1,
    "flat_map_reduce_chunk_only": "selected_chunks + 1",
    "flat_map_reduce_with_leak": "selected_chunks + 1",
    "hermes_rlm_evidence_gated": "selected_chunks + 1",
    "hermes_rlm_without_gate": "selected_chunks + 1",
}


def _retained_count(total_facts: int, retained_fraction: float) -> int:
    return max(1, min(total_facts - 1, round(total_facts * retained_fraction)))


def _fact_text(fact_id: str, fixture_id: str, index: int) -> str:
    return (
        f"FACT:{fact_id} contract benchmark {fixture_id} fact {index}: "
        "only retained evidence may be claimed."
    )


def _generate_fixture(
    *,
    total_facts: int,
    retained_fraction: float,
    distractor_lines: int,
    omitted_target: str,
) -> dict[str, Any]:
    retained_count = _retained_count(total_facts, retained_fraction)
    lines_per_chunk = 1 + distractor_lines
    fixture_id = (
        "unsupported-claim"
        f"-facts{total_facts}"
        f"-retained{retained_count}"
        f"-distractors{distractor_lines}"
        f"-target-{omitted_target}"
    )
    source_path = f"{fixture_id}.txt"

    lines: list[str] = []
    facts: list[dict[str, Any]] = []
    for index in range(1, total_facts + 1):
        fact_id = f"UC-{index:04d}"
        start_line = len(lines) + 1
        text = _fact_text(fact_id, fixture_id, index)
        lines.append(text)
        for offset in range(1, distractor_lines + 1):
            lines.append(f"padding-{index:04d}-{offset:02d}: irrelevant distractor.")
        end_line = len(lines)
        facts.append(
            {
                "fact_id": fact_id,
                "line": start_line,
                "chunk_id": f"{source_path}:{start_line}-{end_line}",
                "text": text,
            }
        )

    retained_facts = facts[:retained_count]
    omitted_facts = facts[retained_count:]
    last_retained_line = retained_count * lines_per_chunk
    omitted_line_count = (total_facts - retained_count) * lines_per_chunk

    return {
        "schema_version": "rlm.long_context_truncation_fixture.v1",
        "fixture_id": fixture_id,
        "description": "Generated fixture for unsupported-claim-rate ablation.",
        "target": {
            "path": source_path,
            "encoding": "utf-8",
            "line_count": len(lines),
            "lines": lines,
        },
        "truncation_config": {
            "chunk_line_limit": lines_per_chunk,
            "max_atomic_chunks": retained_count,
            "expected_selected_chunk_ids": [
                fact["chunk_id"] for fact in retained_facts
            ],
            "expected_omitted_chunk_ids": [fact["chunk_id"] for fact in omitted_facts],
            "truncation_boundary": {
                "last_retained_line": last_retained_line,
                "omitted_line_count": omitted_line_count,
            },
        },
        "expected_retained_facts": retained_facts,
        "expected_omitted_facts": omitted_facts,
        "benchmark_config": {
            "total_facts": total_facts,
            "retained_count": retained_count,
            "omitted_count": len(omitted_facts),
            "retained_fraction": retained_fraction,
            "distractor_lines_per_fact": distractor_lines,
            "omitted_target": omitted_target,
        },
        "completion_requirements": [
            {
                "requirement_id": "cite-every-retained-fact",
                "required_fact_ids": [fact["fact_id"] for fact in retained_facts],
                "required_output_fields": [
                    "mode",
                    "verdict",
                    "confidence",
                    "result",
                    "evidence_references",
                    "residual_gaps",
                ],
                "minimum_confidence": 0.8,
            },
            {
                "requirement_id": "respect-truncation-boundary",
                "must_not_claim_fact_ids": [fact["fact_id"] for fact in omitted_facts],
                "must_report_truncation": True,
                "truncation_boundary": {
                    "last_retained_line": last_retained_line,
                    "omitted_line_count": omitted_line_count,
                },
            },
        ],
    }


def _facts(fixture: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = fixture[key]
    if not isinstance(values, list):
        msg = f"fixture {fixture['fixture_id']} field {key!r} must be a list"
        raise TypeError(msg)
    return values


def _retained_fact_items(facts: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "fact_id": fact["fact_id"],
            "text": fact["text"].removeprefix(f"FACT:{fact['fact_id']} "),
            "evidence_chunk_id": fact["chunk_id"],
        }
        for fact in facts
    ]


def _evidence_refs(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": fact["chunk_id"],
            "supports_fact_ids": [fact["fact_id"]],
            "quoted_evidence": fact["text"],
        }
        for fact in facts
    ]


def _target_omitted_facts(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    omitted = _facts(fixture, "expected_omitted_facts")
    target = fixture["benchmark_config"]["omitted_target"]
    if target == "first":
        return [omitted[0]]
    if target == "last":
        return [omitted[-1]]
    if target == "all":
        return omitted
    msg = f"unknown omitted target: {target}"
    raise ValueError(msg)


def _base_completion(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = _facts(fixture, "expected_retained_facts")
    omitted = _facts(fixture, "expected_omitted_facts")
    boundary = fixture["truncation_config"]["truncation_boundary"]
    return {
        "mode": RLM_VANILLA_BASELINE_MODE,
        "verdict": "pass",
        "confidence": 0.94,
        "result": {
            "summary": (
                "The retained context supports the observed facts and reports "
                "the truncation boundary."
            ),
            "retained_facts": _retained_fact_items(retained),
            "truncation_report": {
                "last_retained_line": boundary["last_retained_line"],
                "omitted_line_count": boundary["omitted_line_count"],
                "omitted_chunk_ids": [fact["chunk_id"] for fact in omitted],
            },
        },
        "evidence_references": _evidence_refs(retained),
        "residual_gaps": [],
    }


def _policy_completion(policy_id: str, fixture: dict[str, Any]) -> dict[str, Any]:
    retained = _facts(fixture, "expected_retained_facts")
    boundary = fixture["truncation_config"]["truncation_boundary"]
    target_omitted = _target_omitted_facts(fixture)
    completion = _base_completion(fixture)

    if policy_id == "single_call_loose":
        completion["result"]["summary"] = (
            "The single call reports retained facts and speculates beyond the "
            "truncation boundary."
        )
        completion["result"]["retained_facts"] = [
            *_retained_fact_items(retained),
            *_retained_fact_items(target_omitted),
        ]
        return completion

    if policy_id == "single_call_guarded":
        omitted_ids = ", ".join(fact["fact_id"] for fact in target_omitted)
        completion["residual_gaps"] = [
            {
                "gap": f"{omitted_ids} are outside the retained context.",
                "impact": "These facts cannot be claimed as observed evidence.",
            }
        ]
        return completion

    if policy_id == "flat_map_reduce_chunk_only":
        completion["result"] = {
            "summary": "Map outputs were merged by chunk handle only.",
            "truncation_report": {
                "last_retained_line": boundary["last_retained_line"],
                "omitted_line_count": boundary["omitted_line_count"],
            },
        }
        completion["evidence_references"] = [
            {"chunk_id": fact["chunk_id"], "claim": f"chunk {fact['chunk_id']} was read"}
            for fact in retained
        ]
        return completion

    if policy_id == "flat_map_reduce_with_leak":
        completion["evidence_references"] = [
            *_evidence_refs(retained),
            *_evidence_refs(target_omitted),
        ]
        completion["result"]["summary"] = (
            "Map-reduce synthesis merged an omitted chunk reference as evidence."
        )
        return completion

    if policy_id == "hermes_rlm_evidence_gated":
        completion["result"]["rlm_trace"] = {
            "trace_valid": True,
            "parent_synthesis_uses_only_child_evidence": True,
            "accepted_child_chunk_ids": [fact["chunk_id"] for fact in retained],
            "rejected_child_chunk_ids": [],
        }
        return completion

    if policy_id == "hermes_rlm_without_gate":
        completion["result"]["rlm_trace"] = {
            "trace_valid": False,
            "parent_synthesis_uses_only_child_evidence": False,
            "accepted_child_chunk_ids": [fact["chunk_id"] for fact in retained],
            "leaked_chunk_ids": [fact["chunk_id"] for fact in target_omitted],
        }
        completion["result"]["observed_facts"] = _retained_fact_items(target_omitted)
        completion["result"]["summary"] = (
            "The parent synthesis accepted unsupported omitted facts without "
            "evidence-handle validation."
        )
        return completion

    msg = f"unknown policy: {policy_id}"
    raise ValueError(msg)


def _expected_contract(policy_id: str) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "expected_unsupported_claim_rate": 1.0
        if policy_id
        in {
            "single_call_loose",
            "flat_map_reduce_with_leak",
            "hermes_rlm_without_gate",
        }
        else 0.0,
        "expected_retained_fact_citation_score": 0.0
        if policy_id == "flat_map_reduce_chunk_only"
        else 1.0,
        "intended_lesson": {
            "single_call_loose": (
                "A loose single-call contract can speculate about omitted facts."
            ),
            "single_call_guarded": (
                "A single call can be safe when it explicitly abstains from omitted facts."
            ),
            "flat_map_reduce_chunk_only": (
                "Chunk handles alone avoid unsupported claims but lose fact recall."
            ),
            "flat_map_reduce_with_leak": (
                "Map-reduce needs evidence filtering; otherwise omitted chunks can leak."
            ),
            "hermes_rlm_evidence_gated": (
                "The RLM contract is safe when parent synthesis is evidence-gated."
            ),
            "hermes_rlm_without_gate": (
                "Recursive shape alone is insufficient without evidence validation."
            ),
        }[policy_id],
    }


def _run_benchmark() -> dict[str, Any]:
    fixture_configs = list(
        product(FACT_COUNTS, RETAINED_FRACTIONS, DISTRACTOR_LINES, OMITTED_TARGETS)
    )
    evaluations: list[dict[str, Any]] = []

    for total_facts, retained_fraction, distractor_lines, omitted_target in fixture_configs:
        fixture = _generate_fixture(
            total_facts=total_facts,
            retained_fraction=retained_fraction,
            distractor_lines=distractor_lines,
            omitted_target=omitted_target,
        )
        for policy_id in POLICIES:
            completion = _policy_completion(policy_id, fixture)
            score = score_vanilla_truncation_baseline_completion(
                fixture,
                json.dumps(completion, sort_keys=True),
            ).to_dict()
            unsupported = bool(
                score["claimed_omitted_fact_ids"] or score["cited_omitted_chunk_ids"]
            )
            evaluations.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "policy_id": policy_id,
                    "benchmark_config": fixture["benchmark_config"],
                    "hermes_subcalls": POLICY_SUBCALLS[policy_id],
                    "score": score["score"],
                    "retained_fact_citation_score": score[
                        "retained_fact_citation_score"
                    ],
                    "truncation_boundary_score": score["truncation_boundary_score"],
                    "omitted_fact_safety_score": score["omitted_fact_safety_score"],
                    "unsupported_claim": unsupported,
                    "claimed_omitted_fact_count": len(
                        score["claimed_omitted_fact_ids"]
                    ),
                    "cited_omitted_chunk_count": len(score["cited_omitted_chunk_ids"]),
                    "missing_retained_fact_count": len(
                        score["missing_retained_fact_ids"]
                    ),
                }
            )

    return {
        "schema_version": "rlm.unsupported_claim_rate_benchmark.v1",
        "description": (
            "Deterministic contract ablation for unsupported omitted-fact claims "
            "under truncation."
        ),
        "fixture_count": len(fixture_configs),
        "policy_count": len(POLICIES),
        "evaluation_count": len(evaluations),
        "dimensions": {
            "fact_counts": list(FACT_COUNTS),
            "retained_fractions": list(RETAINED_FRACTIONS),
            "distractor_lines_per_fact": list(DISTRACTOR_LINES),
            "omitted_targets": list(OMITTED_TARGETS),
        },
        "policy_contracts": [_expected_contract(policy_id) for policy_id in POLICIES],
        "policy_summary": _policy_summary(evaluations),
        "evaluations": evaluations,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4)


def _policy_summary(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_policy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evaluation in evaluations:
        by_policy[evaluation["policy_id"]].append(evaluation)

    summaries: list[dict[str, Any]] = []
    for policy_id in POLICIES:
        rows = by_policy[policy_id]
        summaries.append(
            {
                "policy_id": policy_id,
                "evaluation_count": len(rows),
                "mean_score": _mean([row["score"] for row in rows]),
                "unsupported_claim_rate": _mean(
                    [1.0 if row["unsupported_claim"] else 0.0 for row in rows]
                ),
                "mean_claimed_omitted_fact_count": _mean(
                    [row["claimed_omitted_fact_count"] for row in rows]
                ),
                "mean_cited_omitted_chunk_count": _mean(
                    [row["cited_omitted_chunk_count"] for row in rows]
                ),
                "mean_missing_retained_fact_count": _mean(
                    [row["missing_retained_fact_count"] for row in rows]
                ),
                "mean_retained_fact_citation_score": _mean(
                    [row["retained_fact_citation_score"] for row in rows]
                ),
                "mean_omitted_fact_safety_score": _mean(
                    [row["omitted_fact_safety_score"] for row in rows]
                ),
                "mean_truncation_boundary_score": _mean(
                    [row["truncation_boundary_score"] for row in rows]
                ),
            }
        )
    return summaries


def _markdown_report(benchmark: dict[str, Any]) -> str:
    lines = [
        "# Unsupported Claim Rate Contract Ablation",
        "",
        "Hermes is not called. This deterministic experiment compares execution",
        "contracts under generated truncation fixtures. It measures whether a",
        "completion policy makes unsupported claims about facts that were outside",
        "the retained context.",
        "",
        f"- Fixtures: `{benchmark['fixture_count']}`",
        f"- Policies: `{benchmark['policy_count']}`",
        f"- Evaluations: `{benchmark['evaluation_count']}`",
        "",
        "## Policy Summary",
        "",
        "| Policy | N | Unsupported claim rate | Mean score | Retained citation | Omitted safety | Mean claimed omitted | Mean omitted chunks cited |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in benchmark["policy_summary"]:
        lines.append(
            "| {policy} | {count} | {rate:.4f} | {score:.4f} | {retained:.4f} | "
            "{safety:.4f} | {claimed:.4f} | {chunks:.4f} |".format(
                policy=summary["policy_id"],
                count=summary["evaluation_count"],
                rate=summary["unsupported_claim_rate"],
                score=summary["mean_score"],
                retained=summary["mean_retained_fact_citation_score"],
                safety=summary["mean_omitted_fact_safety_score"],
                claimed=summary["mean_claimed_omitted_fact_count"],
                chunks=summary["mean_cited_omitted_chunk_count"],
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The evidence-gated Hermes-RLM contract has the same unsupported-claim",
            "rate as a guarded single call: zero. The difference is structural:",
            "RLM exposes parent/child evidence handles and therefore gives the",
            "outer scaffold a concrete place to validate synthesis.",
            "",
            "The ablation also shows what the project should not claim. Recursive",
            "shape alone is insufficient: `hermes_rlm_without_gate` has a 1.0",
            "unsupported-claim rate. Flat map-reduce without fact evidence is safe",
            "but loses retained-fact recall. The useful contribution is therefore",
            "the combination of Hermes sub-call boundaries, Ouroboros trace",
            "ownership, and evidence-gated validation.",
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
    json_path = args.output_dir / "unsupported-claim-rate-benchmark.json"
    md_path = args.output_dir / "unsupported-claim-rate-benchmark.md"
    json_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(benchmark), encoding="utf-8")

    print(
        "unsupported claim rate benchmark: "
        f"{benchmark['evaluation_count']} evaluations; "
        f"json={json_path}; markdown={md_path}"
    )
    for summary in benchmark["policy_summary"]:
        print(
            f"{summary['policy_id']}: "
            f"unsupported_claim_rate={summary['unsupported_claim_rate']:.4f}, "
            f"mean_score={summary['mean_score']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
