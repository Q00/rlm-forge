"""Replay a persisted truncation-benchmark artifact without calling Hermes.

This lets a judge inspect the committed truncation-benchmark JSON file even
when no Hermes API key is available. It does not run the recursive scaffold;
it parses the artifact produced by the real run and prints the same fields
that ``ooo rlm --truncation-benchmark`` emits at the end of execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _select_chunk_summary(quality: dict[str, Any]) -> str:
    selected = quality.get("selected_chunk_ids", [])
    omitted = quality.get("omitted_chunk_ids", [])
    return f"selected={len(selected)}, omitted={len(omitted)}"


def _print_result(artifact: dict[str, Any]) -> None:
    benchmark_id = artifact.get("benchmark_id", "unknown")
    fixture_id = artifact.get("fixture_id", "unknown")
    print(f"benchmark: {benchmark_id} (fixture {fixture_id})")

    vanilla = artifact.get("quality_comparison", {}).get("vanilla_quality", {})
    rlm = artifact.get("quality_comparison", {}).get("rlm_quality", {})

    vanilla_score = vanilla.get("score")
    rlm_score = rlm.get("score")
    delta = artifact.get("quality_comparison", {}).get("score_delta")
    outperforms = artifact.get("quality_comparison", {}).get("rlm_outperforms_vanilla")

    print(f"chunks: {_select_chunk_summary(rlm)}")
    print(
        "quality: "
        f"vanilla={vanilla_score}, rlm={rlm_score}, "
        f"delta={delta:+.2f}, rlm_outperforms_vanilla={outperforms}"
    )

    vanilla_claimed_omitted = vanilla.get("completion_quality", {}).get(
        "claimed_omitted_fact_ids", []
    )
    rlm_claimed_omitted = rlm.get("completion_quality", {}).get(
        "claimed_omitted_fact_ids", []
    )
    print(
        "claimed_omitted_fact_ids: "
        f"vanilla={vanilla_claimed_omitted}, rlm={rlm_claimed_omitted}"
    )

    vanilla_safety = vanilla.get("completion_quality", {}).get(
        "omitted_fact_safety_score"
    )
    rlm_safety = rlm.get("completion_quality", {}).get("omitted_fact_safety_score")
    print(
        "omitted_fact_safety_score: "
        f"vanilla={vanilla_safety}, rlm={rlm_safety}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifact",
        type=Path,
        help="Path to a persisted truncation benchmark JSON artifact.",
    )
    args = parser.parse_args(argv)

    if not args.artifact.exists():
        print(f"error: artifact not found at {args.artifact}", file=sys.stderr)
        return 2

    with args.artifact.open("r", encoding="utf-8") as fh:
        artifact = json.load(fh)

    _print_result(artifact)
    return 0


if __name__ == "__main__":
    sys.exit(main())
