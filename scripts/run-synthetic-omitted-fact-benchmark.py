#!/usr/bin/env python3
"""Run a synthetic omitted-fact benchmark over many generated fixtures.

This is a deterministic scorer benchmark, not a live Hermes benchmark. It
generates many long-context truncation fixtures, then scores controlled
completion strategies that either obey or violate the omitted-fact contract.
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


FACT_COUNTS = (6, 10, 14, 20)
RETAINED_FRACTIONS = (0.25, 0.50, 0.75)
DISTRACTOR_LINES = (0, 1, 3)
CLAIM_TARGETS = ("first_omitted", "last_omitted", "all_omitted")


def _fact_text(fact_id: str, fixture_id: str, index: int) -> str:
    return (
        f"FACT:{fact_id} synthetic fixture {fixture_id} records contract point "
        f"{index}: evidence must stay attached to its retained chunk."
    )


def _retained_count(total_facts: int, retained_fraction: float) -> int:
    return max(1, min(total_facts - 1, round(total_facts * retained_fraction)))


def _generate_fixture(
    *,
    total_facts: int,
    retained_fraction: float,
    distractor_lines: int,
    claim_target: str,
) -> dict[str, Any]:
    retained_count = _retained_count(total_facts, retained_fraction)
    lines_per_chunk = 1 + distractor_lines
    fixture_id = (
        "synthetic-omitted-fact"
        f"-facts{total_facts}"
        f"-retained{retained_count}"
        f"-distractors{distractor_lines}"
        f"-target-{claim_target}"
    )
    source_path = f"{fixture_id}.txt"

    lines: list[str] = []
    facts: list[dict[str, Any]] = []
    for index in range(1, total_facts + 1):
        fact_id = f"SF-{index:04d}"
        start_line = len(lines) + 1
        text = _fact_text(fact_id, fixture_id, index)
        lines.append(text)
        for offset in range(1, distractor_lines + 1):
            lines.append(
                f"distractor-{index:04d}-{offset:02d}: irrelevant padding text."
            )
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
        "description": (
            "Generated deterministic fixture for claim-aware omitted-fact "
            "scoring."
        ),
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
        "synthetic_config": {
            "total_facts": total_facts,
            "retained_count": retained_count,
            "omitted_count": len(omitted_facts),
            "retained_fraction": retained_fraction,
            "distractor_lines_per_fact": distractor_lines,
            "claim_target": claim_target,
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


def _facts(fixture: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = fixture[key]
    if not isinstance(values, list):
        msg = f"fixture {fixture['fixture_id']} field {key!r} must be a list"
        raise TypeError(msg)
    return values


def _base_completion(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = _facts(fixture, "expected_retained_facts")
    omitted = _facts(fixture, "expected_omitted_facts")
    boundary = fixture["truncation_config"]["truncation_boundary"]
    return {
        "mode": RLM_VANILLA_BASELINE_MODE,
        "verdict": "pass",
        "confidence": 0.93,
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


def _target_omitted_facts(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    omitted = _facts(fixture, "expected_omitted_facts")
    claim_target = fixture["synthetic_config"]["claim_target"]
    if claim_target == "first_omitted":
        return [omitted[0]]
    if claim_target == "last_omitted":
        return [omitted[-1]]
    if claim_target == "all_omitted":
        return omitted
    msg = f"unknown claim target: {claim_target}"
    raise ValueError(msg)


def _strategy_completion(strategy_id: str, fixture: dict[str, Any]) -> dict[str, Any]:
    retained = _facts(fixture, "expected_retained_facts")
    boundary = fixture["truncation_config"]["truncation_boundary"]
    completion = _base_completion(fixture)

    if strategy_id == "perfect_abstaining":
        return completion

    if strategy_id == "guarded_gap_mentions":
        omitted_ids = [fact["fact_id"] for fact in _target_omitted_facts(fixture)]
        completion["residual_gaps"] = [
            {
                "gap": (
                    f"Facts {', '.join(omitted_ids)} are outside the retained "
                    "context."
                ),
                "impact": (
                    "They cannot be claimed as observed evidence unless a "
                    "future run retrieves those chunks."
                ),
            }
        ]
        return completion

    if strategy_id == "omitted_claim_faulty":
        completion["result"]["retained_facts"] = [
            *_retained_fact_items(retained),
            *_retained_fact_items(_target_omitted_facts(fixture)),
        ]
        completion["result"]["summary"] = "The retained context observed omitted facts."
        return completion

    if strategy_id == "omitted_evidence_faulty":
        completion["evidence_references"] = [
            *_evidence_refs(retained),
            *_evidence_refs(_target_omitted_facts(fixture)),
        ]
        return completion

    if strategy_id == "chunk_only_citations":
        completion["result"] = {
            "summary": "The selected chunks were consumed.",
            "truncation_report": {
                "last_retained_line": boundary["last_retained_line"],
                "omitted_line_count": boundary["omitted_line_count"],
            },
        }
        completion["evidence_references"] = [
            {"chunk_id": fact["chunk_id"], "claim": f"consumed {fact['chunk_id']}"}
            for fact in retained
        ]
        return completion

    if strategy_id == "missing_boundary_report":
        completion["result"].pop("truncation_report")
        completion["result"]["summary"] = "The retained context supports the facts."
        return completion

    if strategy_id == "drops_last_retained_fact":
        completion["result"]["retained_facts"] = _retained_fact_items(retained[:-1])
        completion["evidence_references"] = _evidence_refs(retained[:-1])
        return completion

    msg = f"unknown strategy: {strategy_id}"
    raise ValueError(msg)


STRATEGIES = (
    "perfect_abstaining",
    "guarded_gap_mentions",
    "omitted_claim_faulty",
    "omitted_evidence_faulty",
    "chunk_only_citations",
    "missing_boundary_report",
    "drops_last_retained_fact",
)


def _sanity_violations(
    *,
    strategy_id: str,
    score: dict[str, Any],
    retained_count: int,
) -> list[str]:
    violations: list[str] = []
    claimed = score["claimed_omitted_fact_ids"]
    cited_omitted = score["cited_omitted_chunk_ids"]
    missing = score["missing_retained_fact_ids"]

    if strategy_id in {"perfect_abstaining", "guarded_gap_mentions"}:
        if score["score"] != 1.0:
            violations.append("expected perfect score")
        if claimed:
            violations.append("expected no claimed omitted facts")
        if score["omitted_fact_safety_score"] != 1.0:
            violations.append("expected omitted-fact safety")

    if strategy_id == "omitted_claim_faulty":
        if not claimed:
            violations.append("expected claimed omitted facts")
        if score["omitted_fact_safety_score"] != 0.0:
            violations.append("expected omitted-fact safety failure")

    if strategy_id == "omitted_evidence_faulty":
        if not claimed:
            violations.append("expected claimed omitted facts")
        if not cited_omitted:
            violations.append("expected omitted chunk citation")
        if score["omitted_fact_safety_score"] != 0.0:
            violations.append("expected omitted-fact safety failure")

    if strategy_id == "chunk_only_citations":
        if score["retained_fact_citation_score"] != 0.0:
            violations.append("expected no retained fact credit")
        if len(missing) != retained_count:
            violations.append("expected all retained facts to be missing")

    if strategy_id == "missing_boundary_report":
        if score["truncation_boundary_score"] != 0.0:
            violations.append("expected missing boundary penalty")
        if score["reports_truncation_boundary"]:
            violations.append("expected reports_truncation_boundary=false")

    if strategy_id == "drops_last_retained_fact":
        if len(missing) != 1:
            violations.append("expected exactly one missing retained fact")
        if score["retained_fact_citation_score"] >= 1.0:
            violations.append("expected retained fact citation penalty")

    return violations


def _run_benchmark() -> dict[str, Any]:
    fixture_configs = list(
        product(FACT_COUNTS, RETAINED_FRACTIONS, DISTRACTOR_LINES, CLAIM_TARGETS)
    )
    evaluations: list[dict[str, Any]] = []

    for total_facts, retained_fraction, distractor_lines, claim_target in fixture_configs:
        fixture = _generate_fixture(
            total_facts=total_facts,
            retained_fraction=retained_fraction,
            distractor_lines=distractor_lines,
            claim_target=claim_target,
        )
        retained_count = fixture["synthetic_config"]["retained_count"]
        for strategy_id in STRATEGIES:
            completion = _strategy_completion(strategy_id, fixture)
            score = score_vanilla_truncation_baseline_completion(
                fixture,
                json.dumps(completion, sort_keys=True),
            ).to_dict()
            violations = _sanity_violations(
                strategy_id=strategy_id,
                score=score,
                retained_count=retained_count,
            )
            evaluations.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "strategy_id": strategy_id,
                    "synthetic_config": fixture["synthetic_config"],
                    "score": score["score"],
                    "retained_fact_citation_score": score[
                        "retained_fact_citation_score"
                    ],
                    "truncation_boundary_score": score["truncation_boundary_score"],
                    "omitted_fact_safety_score": score["omitted_fact_safety_score"],
                    "claimed_omitted_fact_ids": score["claimed_omitted_fact_ids"],
                    "missing_retained_fact_ids": score["missing_retained_fact_ids"],
                    "cited_omitted_chunk_ids": score["cited_omitted_chunk_ids"],
                    "reports_truncation_boundary": score[
                        "reports_truncation_boundary"
                    ],
                    "sanity_passed": not violations,
                    "sanity_violations": violations,
                }
            )

    return {
        "schema_version": "rlm.synthetic_omitted_fact_benchmark.v1",
        "description": (
            "Hermes-free synthetic benchmark for claim-aware omitted-fact "
            "scoring across generated fixtures."
        ),
        "fixture_count": len(fixture_configs),
        "strategy_count": len(STRATEGIES),
        "evaluation_count": len(evaluations),
        "sanity_pass_count": sum(1 for item in evaluations if item["sanity_passed"]),
        "sanity_fail_count": sum(
            1 for item in evaluations if not item["sanity_passed"]
        ),
        "dimensions": {
            "fact_counts": list(FACT_COUNTS),
            "retained_fractions": list(RETAINED_FRACTIONS),
            "distractor_lines_per_fact": list(DISTRACTOR_LINES),
            "claim_targets": list(CLAIM_TARGETS),
        },
        "strategy_summary": _strategy_summary(evaluations),
        "evaluations": evaluations,
    }


def _strategy_summary(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evaluation in evaluations:
        by_strategy[evaluation["strategy_id"]].append(evaluation)

    summaries: list[dict[str, Any]] = []
    for strategy_id in STRATEGIES:
        rows = by_strategy[strategy_id]
        scores = [row["score"] for row in rows]
        safety_scores = [row["omitted_fact_safety_score"] for row in rows]
        retained_scores = [row["retained_fact_citation_score"] for row in rows]
        boundary_scores = [row["truncation_boundary_score"] for row in rows]
        summaries.append(
            {
                "strategy_id": strategy_id,
                "evaluation_count": len(rows),
                "mean_score": round(sum(scores) / len(scores), 4),
                "min_score": min(scores),
                "max_score": max(scores),
                "mean_retained_fact_citation_score": round(
                    sum(retained_scores) / len(retained_scores),
                    4,
                ),
                "mean_truncation_boundary_score": round(
                    sum(boundary_scores) / len(boundary_scores),
                    4,
                ),
                "mean_omitted_fact_safety_score": round(
                    sum(safety_scores) / len(safety_scores),
                    4,
                ),
                "total_claimed_omitted_facts": sum(
                    len(row["claimed_omitted_fact_ids"]) for row in rows
                ),
                "sanity_fail_count": sum(
                    1 for row in rows if not row["sanity_passed"]
                ),
            }
        )
    return summaries


def _markdown_report(benchmark: dict[str, Any]) -> str:
    lines = [
        "# Synthetic Omitted-Fact Benchmark",
        "",
        "Hermes is not called. This benchmark generates deterministic truncation",
        "fixtures and scores controlled completion strategies with the same",
        "claim-aware scorer used by the persisted artifact.",
        "",
        f"- Fixtures: `{benchmark['fixture_count']}`",
        f"- Strategies: `{benchmark['strategy_count']}`",
        f"- Evaluations: `{benchmark['evaluation_count']}`",
        f"- Sanity failures: `{benchmark['sanity_fail_count']}`",
        "",
        "## Strategy Summary",
        "",
        "| Strategy | N | Mean score | Min | Max | Mean retained | Mean boundary | Mean safety | Claimed omitted | Sanity failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in benchmark["strategy_summary"]:
        lines.append(
            "| {strategy_id} | {count} | {mean:.4f} | {min_score:.4f} | "
            "{max_score:.4f} | {retained:.4f} | {boundary:.4f} | "
            "{safety:.4f} | {claimed} | {failures} |".format(
                strategy_id=summary["strategy_id"],
                count=summary["evaluation_count"],
                mean=summary["mean_score"],
                min_score=summary["min_score"],
                max_score=summary["max_score"],
                retained=summary["mean_retained_fact_citation_score"],
                boundary=summary["mean_truncation_boundary_score"],
                safety=summary["mean_omitted_fact_safety_score"],
                claimed=summary["total_claimed_omitted_facts"],
                failures=summary["sanity_fail_count"],
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The controlled safe strategies (`perfect_abstaining` and",
            "`guarded_gap_mentions`) remain perfect across all generated fixtures.",
            "Faulty omitted-fact strategies fail only the omitted-fact safety axis.",
            "Chunk-only citations receive no retained-fact credit, which guards",
            "against a common false positive in coarse evidence scoring.",
            "",
            "This is still a scorer stress test, not evidence that a live model or",
            "recursive scaffold will outperform another model. It supports the",
            "narrower claim that the evaluation harness can separate guarded gap",
            "mentions from unsupported evidence claims across many fixture shapes.",
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
    output_stem = "synthetic-omitted-fact-benchmark"
    if benchmark["sanity_fail_count"]:
        output_stem += ".failed"
    json_path = args.output_dir / f"{output_stem}.json"
    md_path = args.output_dir / f"{output_stem}.md"
    json_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(benchmark), encoding="utf-8")

    print(
        "synthetic omitted-fact benchmark: "
        f"{benchmark['sanity_pass_count']}/{benchmark['evaluation_count']} "
        "sanity checks passed; "
        f"json={json_path}; markdown={md_path}"
    )
    return 0 if benchmark["sanity_fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
