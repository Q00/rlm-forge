"""Smoke tests for the hackathon submission package.

These confirm the package imports cleanly, the persisted artifact replays,
and the public API surface matches expectations. No real Hermes calls are
made by these tests; they are designed to run in any CI without an API key.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "benchmarks" / "rlm-long-context-truncation-v1.json"
SYNTHETIC_BENCHMARK = (
    REPO_ROOT / "experiments" / "synthetic-omitted-fact-benchmark.json"
)
UNSUPPORTED_CLAIM_BENCHMARK = (
    REPO_ROOT / "experiments" / "unsupported-claim-rate-benchmark.json"
)
TRACEGUARD_DEMO = REPO_ROOT / "experiments" / "traceguard-demo.json"


def test_package_imports_cleanly() -> None:
    """The submission namespace re-exports the RLM surface from Ouroboros."""
    import rlm_forge as pkg

    expected = {
        "HermesCliRuntime",
        "MAX_RLM_AC_TREE_DEPTH",
        "MAX_RLM_AMBIGUITY_THRESHOLD",
        "RLM_MVP_SRC_DOGFOOD_BENCHMARK_ID",
        "RLMRunConfig",
        "RLMRunResult",
        "RLMTraceStore",
        "run_rlm_benchmark",
        "run_rlm_loop",
        "run_shared_truncation_benchmark",
        "run_vanilla_truncation_baseline",
        "TraceGuardClaim",
        "TraceGuardEvidence",
        "TraceGuardRejection",
        "TraceGuardResult",
        "build_manifest_from_fixture",
        "extract_parent_claims",
        "validate_parent_synthesis",
    }
    missing = expected - set(pkg.__all__)
    assert not missing, f"missing exports: {missing}"


def test_persisted_artifact_records_claim_aware_rescore() -> None:
    """The committed truncation artifact reflects claim-aware omitted-fact scoring."""
    assert ARTIFACT.exists(), f"missing artifact at {ARTIFACT}"
    data = json.loads(ARTIFACT.read_text())

    comparison = data["quality_comparison"]
    assert comparison["rlm_outperforms_vanilla"] is False
    assert comparison["winner"] == "tie"
    assert comparison["score_delta"] == 0.0
    assert comparison["rlm_quality"]["score"] == 1.0
    assert comparison["vanilla_quality"]["score"] == 1.0

    rlm_completion = comparison["rlm_quality"]["completion_quality"]
    vanilla_completion = comparison["vanilla_quality"]["completion_quality"]

    # Neither output asserts omitted facts under the corrected claim-aware scorer.
    assert rlm_completion["claimed_omitted_fact_ids"] == []
    assert rlm_completion["omitted_fact_safety_score"] == 1.0
    assert vanilla_completion["claimed_omitted_fact_ids"] == []
    assert vanilla_completion["omitted_fact_safety_score"] == 1.0


def test_replay_cli_prints_rescored_delta() -> None:
    """The replay entry point reads the corrected artifact and prints the tie."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rlm_forge.replay",
            str(ARTIFACT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "delta=+0.00" in result.stdout
    assert "rlm_outperforms_vanilla=False" in result.stdout


def test_synthetic_benchmark_artifact_records_scorer_sanity_checks() -> None:
    """The committed synthetic scorer benchmark covers many fixture shapes."""
    assert SYNTHETIC_BENCHMARK.exists(), f"missing artifact at {SYNTHETIC_BENCHMARK}"
    data = json.loads(SYNTHETIC_BENCHMARK.read_text())

    assert data["fixture_count"] == 108
    assert data["strategy_count"] == 7
    assert data["evaluation_count"] == 756
    assert data["sanity_fail_count"] == 0
    assert data["sanity_pass_count"] == 756

    summary = {row["strategy_id"]: row for row in data["strategy_summary"]}
    assert summary["guarded_gap_mentions"]["mean_score"] == 1.0
    assert summary["guarded_gap_mentions"]["total_claimed_omitted_facts"] == 0
    assert summary["chunk_only_citations"]["mean_retained_fact_citation_score"] == 0.0
    assert summary["omitted_claim_faulty"]["mean_omitted_fact_safety_score"] == 0.0


def test_unsupported_claim_rate_ablation_records_contract_effect() -> None:
    """The contract ablation isolates evidence gating as the useful mechanism."""
    assert UNSUPPORTED_CLAIM_BENCHMARK.exists(), (
        f"missing artifact at {UNSUPPORTED_CLAIM_BENCHMARK}"
    )
    data = json.loads(UNSUPPORTED_CLAIM_BENCHMARK.read_text())

    assert data["fixture_count"] == 72
    assert data["policy_count"] == 6
    assert data["evaluation_count"] == 432

    summary = {row["policy_id"]: row for row in data["policy_summary"]}
    assert summary["hermes_rlm_evidence_gated"]["unsupported_claim_rate"] == 0.0
    assert summary["hermes_rlm_evidence_gated"]["mean_score"] == 1.0
    assert summary["hermes_rlm_without_gate"]["unsupported_claim_rate"] == 1.0
    assert summary["single_call_loose"]["unsupported_claim_rate"] == 1.0
    assert summary["flat_map_reduce_chunk_only"]["mean_retained_fact_citation_score"] == 0.0


def test_traceguard_demo_artifact_records_enforcement_results() -> None:
    """The TraceGuard demo proves enforcement, not just post-hoc scoring."""
    assert TRACEGUARD_DEMO.exists(), f"missing artifact at {TRACEGUARD_DEMO}"
    data = json.loads(TRACEGUARD_DEMO.read_text())

    assert data["case_count"] == 3
    assert data["passed_count"] == 3
    assert data["failed_count"] == 0

    results = {row["case_id"]: row["validation"] for row in data["results"]}
    assert results["safe_parent_synthesis"]["accepted"] is True
    assert results["unsafe_omitted_fact"]["accepted"] is False
    assert results["unsafe_omitted_fact"]["rejected_claims"][0]["reason"] == (
        "unsupported_fact_id"
    )
    assert results["chunk_only_no_fact"]["accepted"] is False
    assert results["chunk_only_no_fact"]["rejected_claims"][0]["reason"] == (
        "chunk_handle_without_fact"
    )
