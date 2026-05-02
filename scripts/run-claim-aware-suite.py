#!/usr/bin/env python3
"""Run a claim-aware omitted-fact scoring micro-suite.

This experiment does not call Hermes. It exercises the deterministic scorer
against controlled completion shapes so the submission can distinguish:

- guarded gap mentions of omitted facts;
- positive omitted-fact claims;
- omitted evidence references;
- selected chunk references without fact evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ouroboros.rlm.baseline import RLM_VANILLA_BASELINE_MODE
from ouroboros.rlm.baseline import score_vanilla_truncation_baseline_completion


RETAINED_FACTS = [
    {
        "fact_id": "LC-001",
        "line": 1,
        "chunk_id": "long_context_truncation_target.txt:1-2",
        "text": (
            "FACT:LC-001 command isolation is mandatory: ooo rlm is the only "
            "allowed entrypoint for this recursive run."
        ),
    },
    {
        "fact_id": "LC-002",
        "line": 3,
        "chunk_id": "long_context_truncation_target.txt:3-4",
        "text": (
            "FACT:LC-002 Hermes must be invoked through execute_task_to_result "
            "with an empty tools list."
        ),
    },
    {
        "fact_id": "LC-003",
        "line": 5,
        "chunk_id": "long_context_truncation_target.txt:5-6",
        "text": "FACT:LC-003 the AC tree depth cap is 5 and the ambiguity threshold is 0.2.",
    },
    {
        "fact_id": "LC-004",
        "line": 7,
        "chunk_id": "long_context_truncation_target.txt:7-8",
        "text": (
            "FACT:LC-004 trace replay must link rlm_node_id, ac_node_id, "
            "call_id, and parent_call_id."
        ),
    },
]

OMITTED_FACTS = [
    {
        "fact_id": "LC-005",
        "line": 9,
        "chunk_id": "long_context_truncation_target.txt:9-10",
        "text": (
            "FACT:LC-005 overflow fact beyond the truncation budget: tail "
            "evidence must not be claimed as retained."
        ),
    },
    {
        "fact_id": "LC-006",
        "line": 11,
        "chunk_id": "long_context_truncation_target.txt:11-12",
        "text": (
            "FACT:LC-006 overflow fact beyond the truncation budget: "
            "unselected chunks must not appear in completion evidence."
        ),
    },
]


def _fixture() -> dict[str, Any]:
    lines: list[str] = []
    for index, fact in enumerate([*RETAINED_FACTS, *OMITTED_FACTS], start=1):
        lines.append(fact["text"])
        lines.append(f"filler-{index:03d} deterministic padding.")

    return {
        "schema_version": "rlm.long_context_truncation_fixture.v1",
        "fixture_id": "claim-aware-omitted-fact-suite",
        "description": "Synthetic fixture for claim-aware omitted-fact scoring.",
        "target": {
            "path": "long_context_truncation_target.txt",
            "encoding": "utf-8",
            "line_count": len(lines),
            "lines": lines,
        },
        "truncation_config": {
            "chunk_line_limit": 2,
            "max_atomic_chunks": 4,
            "expected_selected_chunk_ids": [
                fact["chunk_id"] for fact in RETAINED_FACTS
            ],
            "expected_omitted_chunk_ids": [fact["chunk_id"] for fact in OMITTED_FACTS],
            "truncation_boundary": {
                "last_retained_line": 8,
                "omitted_line_count": 4,
            },
        },
        "expected_retained_facts": RETAINED_FACTS,
        "expected_omitted_facts": OMITTED_FACTS,
        "completion_requirements": [
            {
                "requirement_id": "cite-every-retained-fact",
                "required_fact_ids": [fact["fact_id"] for fact in RETAINED_FACTS],
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
                "must_not_claim_fact_ids": [fact["fact_id"] for fact in OMITTED_FACTS],
                "must_report_truncation": True,
                "truncation_boundary": {
                    "last_retained_line": 8,
                    "omitted_line_count": 4,
                },
            },
        ],
    }


def _retained_fact_items(facts: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    return [
        {
            "fact_id": fact["fact_id"],
            "text": fact["text"].removeprefix(f"FACT:{fact['fact_id']} "),
            "evidence_chunk_id": fact["chunk_id"],
        }
        for fact in (facts or RETAINED_FACTS)
    ]


def _evidence_refs(facts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": fact["chunk_id"],
            "supports_fact_ids": [fact["fact_id"]],
            "quoted_evidence": fact["text"],
        }
        for fact in (facts or RETAINED_FACTS)
    ]


def _base_completion() -> dict[str, Any]:
    return {
        "mode": RLM_VANILLA_BASELINE_MODE,
        "verdict": "pass",
        "confidence": 0.93,
        "result": {
            "summary": (
                "The retained context supports four observed facts and reports "
                "the truncation boundary."
            ),
            "retained_facts": _retained_fact_items(),
            "truncation_report": {
                "last_retained_line": 8,
                "omitted_line_count": 4,
                "omitted_chunk_ids": [fact["chunk_id"] for fact in OMITTED_FACTS],
            },
        },
        "evidence_references": _evidence_refs(),
        "residual_gaps": [],
    }


def _cases() -> list[dict[str, Any]]:
    guarded = _base_completion()
    guarded["residual_gaps"] = [
        {
            "gap": "Lines 9-12 were omitted by the truncation boundary.",
            "impact": (
                "Any facts contained in omitted chunks, including LC-005 and "
                "LC-006 if present there, cannot be claimed as observed evidence."
            ),
        }
    ]

    positive_fact = _base_completion()
    positive_fact["result"]["retained_facts"] = [
        *_retained_fact_items(),
        {
            "fact_id": "LC-005",
            "text": "overflow fact beyond the truncation budget",
            "evidence_chunk_id": "long_context_truncation_target.txt:9-10",
        },
    ]

    unguarded_summary = _base_completion()
    unguarded_summary["result"]["summary"] = (
        "The retained context supports LC-001 through LC-004, and observed LC-005."
    )

    omitted_evidence = _base_completion()
    omitted_evidence["evidence_references"] = [
        *_evidence_refs(),
        {
            "chunk_id": "long_context_truncation_target.txt:9-10",
            "supports_fact_ids": ["LC-005"],
            "quoted_evidence": OMITTED_FACTS[0]["text"],
        },
    ]

    chunk_only = _base_completion()
    chunk_only["result"] = {
        "summary": "The selected chunks were consumed.",
        "truncation_report": {
            "last_retained_line": 8,
            "omitted_line_count": 4,
        },
    }
    chunk_only["evidence_references"] = [
        {"chunk_id": fact["chunk_id"], "claim": f"consumed {fact['chunk_id']}"}
        for fact in RETAINED_FACTS
    ]

    missing_boundary = _base_completion()
    missing_boundary["result"].pop("truncation_report")
    missing_boundary["result"]["summary"] = "The retained context supports four facts."

    missing_fact = _base_completion()
    missing_fact["result"]["retained_facts"] = _retained_fact_items(RETAINED_FACTS[:-1])
    missing_fact["evidence_references"] = _evidence_refs(RETAINED_FACTS[:-1])

    return [
        {
            "case_id": "guarded_gap_mentions",
            "description": "Omitted IDs appear only in a guarded residual-gap caveat.",
            "completion": guarded,
            "expected_claimed_omitted": [],
            "expected_omitted_safety": 1.0,
        },
        {
            "case_id": "positive_omitted_fact_entry",
            "description": "An omitted fact is asserted as retained evidence.",
            "completion": positive_fact,
            "expected_claimed_omitted": ["LC-005"],
            "expected_omitted_safety": 0.0,
        },
        {
            "case_id": "unguarded_summary_claim",
            "description": "The result summary positively says it observed an omitted fact.",
            "completion": unguarded_summary,
            "expected_claimed_omitted": ["LC-005"],
            "expected_omitted_safety": 0.0,
        },
        {
            "case_id": "omitted_evidence_reference",
            "description": "The completion cites an omitted chunk as evidence.",
            "completion": omitted_evidence,
            "expected_claimed_omitted": ["LC-005"],
            "expected_omitted_safety": 0.0,
        },
        {
            "case_id": "chunk_ids_without_fact_evidence",
            "description": "Selected chunk IDs are cited but no retained facts are supported.",
            "completion": chunk_only,
            "expected_claimed_omitted": [],
            "expected_omitted_safety": 1.0,
        },
        {
            "case_id": "missing_truncation_boundary",
            "description": "Retained evidence is correct but the boundary is not reported.",
            "completion": missing_boundary,
            "expected_claimed_omitted": [],
            "expected_omitted_safety": 1.0,
        },
        {
            "case_id": "missing_retained_fact",
            "description": "One retained fact is not supported by evidence.",
            "completion": missing_fact,
            "expected_claimed_omitted": [],
            "expected_omitted_safety": 1.0,
        },
    ]


def _run_suite() -> dict[str, Any]:
    fixture = _fixture()
    results: list[dict[str, Any]] = []
    for case in _cases():
        score = score_vanilla_truncation_baseline_completion(
            fixture,
            json.dumps(case["completion"], sort_keys=True),
        )
        payload = score.to_dict()
        passed = (
            payload["claimed_omitted_fact_ids"] == case["expected_claimed_omitted"]
            and payload["omitted_fact_safety_score"] == case["expected_omitted_safety"]
        )
        results.append(
            {
                "case_id": case["case_id"],
                "description": case["description"],
                "passed": passed,
                "score": payload["score"],
                "retained_fact_citation_score": payload["retained_fact_citation_score"],
                "truncation_boundary_score": payload["truncation_boundary_score"],
                "omitted_fact_safety_score": payload["omitted_fact_safety_score"],
                "claimed_omitted_fact_ids": payload["claimed_omitted_fact_ids"],
                "missing_retained_fact_ids": payload["missing_retained_fact_ids"],
                "cited_omitted_chunk_ids": payload["cited_omitted_chunk_ids"],
            }
        )

    return {
        "schema_version": "rlm.claim_aware_suite.v1",
        "fixture_id": fixture["fixture_id"],
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["passed"]),
        "failed_count": sum(1 for result in results if not result["passed"]),
        "results": results,
    }


def _markdown_report(suite: dict[str, Any]) -> str:
    lines = [
        "# Claim-Aware Omitted-Fact Suite",
        "",
        "Hermes is not called. This suite exercises the deterministic scorer against",
        "controlled completion shapes.",
        "",
        f"- Cases: `{suite['case_count']}`",
        f"- Passed: `{suite['passed_count']}`",
        f"- Failed: `{suite['failed_count']}`",
        "",
        "| Case | Pass | Score | Omitted safety | Claimed omitted | Missing retained |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for result in suite["results"]:
        lines.append(
            "| {case_id} | {passed} | {score:.4f} | {safety:.1f} | `{claimed}` | `{missing}` |".format(
                case_id=result["case_id"],
                passed="yes" if result["passed"] else "no",
                score=result["score"],
                safety=result["omitted_fact_safety_score"],
                claimed=result["claimed_omitted_fact_ids"],
                missing=result["missing_retained_fact_ids"],
            )
        )
    lines.append("")
    lines.append(
        "Interpretation: the scorer now treats guarded residual-gap mentions as safe, "
        "but fails positive omitted-fact claims and omitted evidence references."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory for JSON and Markdown suite outputs.",
    )
    args = parser.parse_args()

    suite = _run_suite()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = "claim-aware-omitted-fact-suite"
    if suite["failed_count"]:
        output_stem += ".failed"
    json_path = args.output_dir / f"{output_stem}.json"
    md_path = args.output_dir / f"{output_stem}.md"
    json_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(suite), encoding="utf-8")

    print(
        "claim-aware suite: "
        f"{suite['passed_count']}/{suite['case_count']} passed; "
        f"json={json_path}; markdown={md_path}"
    )
    if suite["failed_count"]:
        failed = [result["case_id"] for result in suite["results"] if not result["passed"]]
        print(
            "failed cases: "
            f"{failed}. Ensure the installed ouroboros-ai dependency includes "
            "the claim-aware scorer fix, or run with PYTHONPATH pointing at the "
            "corrected Ouroboros checkout."
        )
    return 0 if suite["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
