from __future__ import annotations

import json
from types import SimpleNamespace

from rlm_forge.ooo_rlm_traceguard import validate_ooo_rlm_result


def _result(parent_output: dict[str, object]) -> SimpleNamespace:
    child = SimpleNamespace(
        order=0,
        chunk_id="paper.md:1-20",
        call_id="rlm_call_atomic_chunk_001",
        result_payload={
            "reported_result": {
                "summary": "The child extracted evidence from the first chunk."
            }
        },
    )
    parent_state = SimpleNamespace(
        parent_node_id="rlm_node_root",
        ordered_child_results=lambda: (child,),
    )
    parent_subcall = SimpleNamespace(completion=json.dumps(parent_output))
    atomic_execution = SimpleNamespace(
        hermes_subcall=parent_subcall,
        parent_execution_state=parent_state,
    )
    return SimpleNamespace(atomic_execution=atomic_execution)


def test_ooo_rlm_gate_accepts_parent_claims_with_fresh_child_handles() -> None:
    gate = validate_ooo_rlm_result(
        _result(
            {
                "mode": "synthesize_parent",
                "verdict": "completed",
                "result": {
                    "parent_summary": "The parent consumed child evidence.",
                    "key_synthesized_claims": [
                        {
                            "claim": "The target supports a bounded runtime claim.",
                            "supported_by_child_result_ids": [
                                "rlm_node_root:child_result:000"
                            ],
                        }
                    ],
                },
            }
        )
    )

    assert gate.status == "accepted"
    assert gate.validation is not None
    assert gate.validation.accepted is True
    assert gate.validation.unsupported_claim_rate == 0.0


def test_ooo_rlm_gate_rejects_unknown_child_result_handles() -> None:
    gate = validate_ooo_rlm_result(
        _result(
            {
                "mode": "synthesize_parent",
                "verdict": "completed",
                "result": {
                    "key_synthesized_claims": [
                        {
                            "claim": "This claim cites a child that was never run.",
                            "supported_by_child_result_ids": [
                                "rlm_node_root:child_result:999"
                            ],
                        }
                    ],
                },
            }
        )
    )

    assert gate.status == "rejected"
    assert gate.validation is not None
    assert gate.validation.accepted is False
    assert {
        rejection.reason for rejection in gate.validation.rejected_claims
    } == {"unsupported_fact_id"}


def test_ooo_rlm_gate_rejects_direct_memory_answer_fact() -> None:
    gate = validate_ooo_rlm_result(
        _result(
            {
                "mode": "synthesize_parent",
                "verdict": "completed",
                "result": {
                    "key_synthesized_claims": [
                        {
                            "claim": "The target supports a bounded runtime claim.",
                            "supported_by_child_result_ids": [
                                "rlm_node_root:child_result:000"
                            ],
                        }
                    ],
                    "retained_facts": [
                        {
                            "fact_id": "MEMORY-ANSWER-001",
                            "text": "Memory says the paper proves a quality win.",
                            "evidence_chunk_id": "memory://hermes/MEMORY.md",
                        }
                    ],
                },
            }
        )
    )

    assert gate.status == "rejected"
    assert gate.validation is not None
    assert gate.validation.accepted is False
    assert {
        rejection.reason for rejection in gate.validation.rejected_claims
    } == {"unsupported_fact_id"}
