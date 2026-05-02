#!/usr/bin/env python3
"""Run the TraceGuard evidence-gate demo without calling Hermes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rlm_forge.traceguard import build_manifest_from_fixture
from rlm_forge.traceguard import validate_parent_synthesis


def _fixture() -> dict[str, Any]:
    retained = [
        {
            "fact_id": "TG-001",
            "chunk_id": "traceguard_demo.txt:1-2",
            "text": "FACT:TG-001 Hermes child call observed retained setup evidence.",
        },
        {
            "fact_id": "TG-002",
            "chunk_id": "traceguard_demo.txt:3-4",
            "text": "FACT:TG-002 Ouroboros accepted the child evidence handle.",
        },
    ]
    omitted = [
        {
            "fact_id": "TG-003",
            "chunk_id": "traceguard_demo.txt:5-6",
            "text": "FACT:TG-003 omitted tail evidence must not reach parent synthesis.",
        }
    ]
    return {
        "fixture_id": "traceguard-demo-v1",
        "expected_retained_facts": retained,
        "expected_omitted_facts": omitted,
    }


def _safe_parent(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = fixture["expected_retained_facts"]
    return {
        "mode": "hermes_rlm_parent_synthesis",
        "verdict": "pass",
        "confidence": 0.96,
        "result": {
            "summary": "Parent synthesis uses only accepted child evidence.",
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
    }


def _unsafe_omitted_parent(fixture: dict[str, Any]) -> dict[str, Any]:
    parent = _safe_parent(fixture)
    omitted = fixture["expected_omitted_facts"][0]
    parent["result"]["observed_facts"] = [
        {
            "fact_id": omitted["fact_id"],
            "text": omitted["text"],
            "evidence_chunk_id": omitted["chunk_id"],
        }
    ]
    return parent


def _chunk_only_parent(fixture: dict[str, Any]) -> dict[str, Any]:
    retained = fixture["expected_retained_facts"]
    return {
        "mode": "hermes_rlm_parent_synthesis",
        "verdict": "partial",
        "confidence": 0.8,
        "result": {"summary": "Parent synthesis cites chunks but no facts."},
        "evidence_references": [
            {"chunk_id": fact["chunk_id"], "claim": f"read {fact['chunk_id']}"}
            for fact in retained
        ],
    }


def _run_demo() -> dict[str, Any]:
    fixture = _fixture()
    manifest = build_manifest_from_fixture(fixture)
    cases = [
        ("safe_parent_synthesis", _safe_parent(fixture), True),
        ("unsafe_omitted_fact", _unsafe_omitted_parent(fixture), False),
        ("chunk_only_no_fact", _chunk_only_parent(fixture), False),
    ]
    results: list[dict[str, Any]] = []
    for case_id, parent, expected_accepted in cases:
        validation = validate_parent_synthesis(
            evidence_manifest=manifest,
            parent_synthesis=parent,
        )
        results.append(
            {
                "case_id": case_id,
                "expected_accepted": expected_accepted,
                "passed": validation.accepted is expected_accepted,
                "validation": validation.to_dict(),
            }
        )

    return {
        "schema_version": "rlm.traceguard_demo.v1",
        "fixture_id": fixture["fixture_id"],
        "evidence_manifest": [item.to_dict() for item in manifest],
        "case_count": len(results),
        "passed_count": sum(1 for item in results if item["passed"]),
        "failed_count": sum(1 for item in results if not item["passed"]),
        "results": results,
    }


def _markdown_report(demo: dict[str, Any]) -> str:
    lines = [
        "# TraceGuard Evidence Gate Demo",
        "",
        "Hermes is not called. This demo validates parent synthesis outputs",
        "against an accepted child evidence manifest.",
        "",
        f"- Cases: `{demo['case_count']}`",
        f"- Passed: `{demo['passed_count']}`",
        f"- Failed: `{demo['failed_count']}`",
        "",
        "| Case | Expected | Actual | Unsupported claim rate | Rejection reasons |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for result in demo["results"]:
        validation = result["validation"]
        reasons = [item["reason"] for item in validation["rejected_claims"]]
        lines.append(
            "| {case} | {expected} | {actual} | {rate:.4f} | `{reasons}` |".format(
                case=result["case_id"],
                expected="ACCEPT" if result["expected_accepted"] else "REJECT",
                actual="ACCEPT" if validation["accepted"] else "REJECT",
                rate=validation["unsupported_claim_rate"],
                reasons=reasons,
            )
        )
    lines.extend(
        [
            "",
            "Interpretation: TraceGuard accepts parent synthesis only when every",
            "structured fact claim is backed by an accepted child evidence handle.",
            "It rejects omitted facts and rejects chunk handles that do not identify",
            "supported fact IDs.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory for JSON and Markdown demo outputs.",
    )
    args = parser.parse_args()

    demo = _run_demo()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "traceguard-demo.json"
    md_path = args.output_dir / "traceguard-demo.md"
    json_path.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(demo), encoding="utf-8")

    print(
        "traceguard demo: "
        f"{demo['passed_count']}/{demo['case_count']} passed; "
        f"json={json_path}; markdown={md_path}"
    )
    for result in demo["results"]:
        validation = result["validation"]
        print(
            f"{result['case_id']}: "
            f"{'ACCEPT' if validation['accepted'] else 'REJECT'} "
            f"(unsupported_claim_rate={validation['unsupported_claim_rate']:.4f})"
        )
    return 0 if demo["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
