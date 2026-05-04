from __future__ import annotations

from dataclasses import fields
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import rlm_forge.live_portability as live_portability
from rlm_forge.live_portability import CONTRACT_VARIANTS
from rlm_forge.live_portability import RUNTIME_FAMILIES
from rlm_forge.live_portability import build_dry_plan
from rlm_forge.live_portability import generate_primary_fixtures
from rlm_forge.live_portability import run_contracts_only
from rlm_forge.live_portability import run_live_primary
from rlm_forge.live_portability import validate_fixture_contracts
from rlm_forge.traceguard import build_manifest_from_fixture
from rlm_forge.traceguard import extract_parent_claims
from rlm_forge.traceguard import normalize_allowed_evidence_manifest
from rlm_forge.traceguard import validate_parent_synthesis


def test_primary_fixtures_have_required_mix_and_traceguard_verdicts() -> None:
    fixtures = generate_primary_fixtures(count=8)

    assert len(fixtures) == 8
    categories = [fixture["fixture_category"] for fixture in fixtures]
    assert categories.count("simple_truncation") >= 2
    assert categories.count("distractor_heavy") >= 2
    assert categories.count("cross_chunk_dependency") >= 2
    assert categories.count("omitted_fact_temptation") >= 1
    assert categories.count("chunk_only_citation_trap") >= 1

    for fixture in fixtures:
        result = validate_fixture_contracts(fixture)
        assert result["mandatory_contract_pass"], fixture["fixture_id"]
        assert result["safe_traceguard"]["accepted"] is True
        assert result["unsafe_traceguard"]["accepted"] is False


def test_fresh_child_evidence_manifest_accepts_current_child_fact_prefix_normalization() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    retained = fixture["expected_retained_facts"][0]
    text_without_fact_prefix = retained["text"].removeprefix(
        f"FACT:{retained['fact_id']} "
    )

    manifest = live_portability.build_fresh_child_evidence_manifest(
        fixture_manifest=build_manifest_from_fixture(fixture),
        child_records=[
            {
                "call_id": "current-child-1",
                "output": {
                    "observed_facts": [
                        {
                            "fact_id": retained["fact_id"],
                            "evidence_chunk_id": retained["chunk_id"],
                            "text": text_without_fact_prefix,
                        }
                    ],
                    "residual_gaps": [],
                },
            }
        ],
    )

    assert [item.to_dict() for item in manifest] == [
        {
            "fact_id": retained["fact_id"],
            "chunk_id": retained["chunk_id"],
            "text": retained["text"],
            "child_call_id": "current-child-1",
        }
    ]


def test_fresh_child_evidence_manifest_rejects_wrong_current_child_text() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    retained = fixture["expected_retained_facts"][0]

    manifest = live_portability.build_fresh_child_evidence_manifest(
        fixture_manifest=build_manifest_from_fixture(fixture),
        child_records=[
            {
                "call_id": "current-child-1",
                "output": {
                    "observed_facts": [
                        {
                            "fact_id": retained["fact_id"],
                            "evidence_chunk_id": retained["chunk_id"],
                            "text": "A different claim with the same handle.",
                        }
                    ],
                    "residual_gaps": [],
                },
            }
        ],
    )

    assert manifest == ()


def test_chunk_only_citation_trap_fixture_has_null_handle_repair_demo() -> None:
    fixture = next(
        item
        for item in generate_primary_fixtures(count=8)
        if item["fixture_id"] == "chunk-only-citation-trap-01"
    )
    missing_fact = fixture["expected_retained_facts"][1]
    parent = fixture["repairable_missing_handle_parent_synthesis"]

    validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=parent,
    )
    repaired = json.loads(json.dumps(parent))
    repaired["result"]["retained_facts"][1]["evidence_chunk_id"] = missing_fact[
        "chunk_id"
    ]

    assert fixture["fixture_category"] == "chunk_only_citation_trap"
    assert parent["result"]["retained_facts"][1] == {
        "fact_id": "LP-08-002",
        "text": missing_fact["text"],
        "evidence_chunk_id": None,
    }
    assert fixture["safe_parent_synthesis"]["result"]["retained_facts"][1][
        "evidence_chunk_id"
    ] == missing_fact["chunk_id"]
    assert validation.accepted is False
    assert [rejection.reason for rejection in validation.rejected_claims] == [
        "missing_evidence_handle"
    ]
    assert validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=repaired,
    ).accepted is True


def test_dry_plan_has_8_by_3_by_4_matrix() -> None:
    plan = build_dry_plan(fixture_count=8)

    assert plan["fixture_count"] == 8
    assert plan["runtime_family_count"] == len(RUNTIME_FAMILIES) == 3
    assert plan["contract_variant_count"] == len(CONTRACT_VARIANTS) == 4
    assert plan["planned_cell_count"] == 8 * 3 * 4
    assert plan["primary_cell_count"] == 8 * 3


def test_contracts_only_primary_cells_all_pass_without_live_calls() -> None:
    result = run_contracts_only(fixture_count=8)

    assert result["live_model_calls"] is False
    assert result["live_evaluation_count"] == 0
    assert result["deterministic_primary_contract_check_count"] == 8 * 3
    assert result["primary_contract_pass_count"] == 8 * 3
    assert result["aggregate_result"]["status"] == "preflight_pass"
    assert (
        result["aggregate_result"]["primary_claim_status"]
        == "not_evaluated_without_live_provider_calls"
    )


def test_family_summary_distinguishes_contract_failure_from_incomplete() -> None:
    family = RUNTIME_FAMILIES[0]
    cells = [
        {
            "family_id": family.family_id,
            "primary_cell": True,
            "completed": True,
            "mandatory_contract_pass": True,
            "failure_classification": "pass",
        },
        {
            "family_id": family.family_id,
            "primary_cell": True,
            "completed": True,
            "mandatory_contract_pass": False,
            "failure_classification": "primary_contract_failure",
        },
    ]

    summary = live_portability._family_summary_from_cells(  # noqa: SLF001
        cells,
        fixture_count=2,
        families=(family,),
    )

    assert summary[0]["status"] == "contract_failure"


def test_parent_synthesis_retry_state_is_scoped_and_keyed_by_cell_identity() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    family = RUNTIME_FAMILIES[0]
    cell_identity = live_portability.synthesis_cell_identity(
        family=family,
        fixture=fixture,
    )
    state = live_portability.ParentSynthesisRetryState(
        parent_synthesis_run_id="run-a",
    )
    next_parent_run_state = live_portability.ParentSynthesisRetryState(
        parent_synthesis_run_id="run-b",
    )

    state.ensure_cell(cell_identity)

    assert state.to_dict() == {
        "scope": "parent_synthesis_run",
        "parent_synthesis_run_id": "run-a",
        "max_repair_attempts_per_cell": 1,
        "repair_attempts_by_cell": {
            cell_identity: {
                "attempted": False,
                "attempt_count": 0,
                "max_attempts": 1,
            }
        },
    }
    assert state.record_repair_attempt(cell_identity) is True
    assert state.record_repair_attempt(cell_identity) is False
    assert next_parent_run_state.record_repair_attempt(cell_identity) is True
    assert state.to_dict()["repair_attempts_by_cell"][cell_identity] == {
        "attempted": True,
        "attempt_count": 1,
        "max_attempts": 1,
    }


def test_traceguard_repair_scheduler_requires_unrecorded_cell_attempt() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    cell_identity = live_portability.synthesis_cell_identity(
        family=RUNTIME_FAMILIES[0],
        fixture=fixture,
    )
    retry_state = live_portability.ParentSynthesisRetryState(
        parent_synthesis_run_id="run-a",
    )
    repair = {"repair_eligible": True, "repair_attempted": False}

    assert (
        live_portability._schedule_traceguard_repair_attempt(  # noqa: SLF001
            traceguard_repair=repair,
            retry_state=retry_state,
            synthesis_cell_identity=cell_identity,
        )
        is True
    )
    assert (
        live_portability._schedule_traceguard_repair_attempt(  # noqa: SLF001
            traceguard_repair=repair,
            retry_state=retry_state,
            synthesis_cell_identity=cell_identity,
        )
        is False
    )

    blocked_state = live_portability.ParentSynthesisRetryState(
        parent_synthesis_run_id="run-b",
    )
    assert (
        live_portability._schedule_traceguard_repair_attempt(  # noqa: SLF001
            traceguard_repair={"repair_eligible": True, "repair_attempted": True},
            retry_state=blocked_state,
            synthesis_cell_identity=cell_identity,
        )
        is False
    )
    assert retry_state.to_dict()["repair_attempts_by_cell"][cell_identity] == {
        "attempted": True,
        "attempt_count": 1,
        "max_attempts": 1,
    }
    assert blocked_state.to_dict()["repair_attempts_by_cell"] == {}


@pytest.mark.asyncio
async def test_live_primary_shape_without_provider_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    family = RUNTIME_FAMILIES[0]

    async def fake_live_cell(*, family, fixture, timeout_seconds):  # type: ignore[no-untyped-def]
        return {
            "completed": True,
            "status": "live_contract_pass",
            "failure_classification": "pass",
            "mandatory_contract_pass": True,
            "trace_structure": {
                "root_call_id": f"{fixture['fixture_id']}::{family.family_id}::root",
                "parent_synthesis_call_id": f"{fixture['fixture_id']}::{family.family_id}::parent",
                "child_call_count": len(fixture["selected_chunk_ids"]),
                "child_records": [],
                "selected_chunk_coverage_pass": True,
            },
            "parent_synthesis": fixture["safe_parent_synthesis"],
            "traceguard_validation": {"accepted": True},
            "secondary_metrics": {},
        }

    monkeypatch.setattr(
        live_portability,
        "_run_live_rlm_traceguard_cell",
        fake_live_cell,
    )

    result = await run_live_primary(
        fixture_count=8,
        families=(family,),
        timeout_seconds=1,
    )

    assert result["run_mode"] == "live_primary"
    assert result["run_status"] == "completed"
    assert result["planned_cell_count"] == 8
    assert result["cell_count"] == 8
    assert result["aggregate_result"]["status"] == "pass"
    assert result["family_summary"][0]["passed_primary_cells"] == 8


@pytest.mark.asyncio
async def test_live_cell_artifact_includes_traceguard_repair_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
    )

    repair = artifact["traceguard_repair"]

    assert "failure_reason" in repair
    assert repair["failure_reason"] is None
    assert repair["initial_accept"] is True
    assert repair["repair_eligible"] is False
    assert repair["repair_attempted"] is False
    assert repair["initial_rejection_reasons"] == []
    assert repair["initial_rejection_exclusive_missing_evidence_handle"] is False
    assert (
        repair["initial_rejection_exclusive_repairable_missing_evidence_handle"]
        is False
    )
    assert repair["before_validation"] == artifact["traceguard_validation"]


@pytest.mark.asyncio
async def test_live_cell_repairs_exclusive_missing_handle_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
    )
    cell_identity = live_portability.synthesis_cell_identity(
        family=RUNTIME_FAMILIES[0],
        fixture=fixture,
    )
    retry_state = artifact["traceguard_repair"]["retry_orchestration_state"]
    retried_parent_synthesis = artifact["retried_parent_synthesis"]
    retried_missing_fact = retried_parent_synthesis["result"]["retained_facts"][0]
    retried_evidence_handle = retried_missing_fact["evidence_chunk_id"]
    retried_validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=retried_parent_synthesis,
    )

    assert artifact["mandatory_contract_pass"] is True
    assert artifact["trace_structure"]["synthesis_cell_identity"] == cell_identity
    assert artifact["traceguard_validation"]["accepted"] is True
    assert artifact["parent_synthesis"] == parent
    assert isinstance(retried_evidence_handle, str)
    assert retried_evidence_handle
    assert retried_evidence_handle == first["chunk_id"]
    assert retried_evidence_handle in retried_validation.allowed_chunk_ids
    assert retried_validation.accepted is True
    assert (
        retried_validation.to_dict()
        == artifact["traceguard_repair"]["parent_synthesis_retry_validation"]
    )
    assert artifact["repaired_parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] == first["chunk_id"]
    assert artifact["parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] is None
    assert {
        rejection["reason"]
        for rejection in artifact["traceguard_repair"]["before_validation"]["rejected_claims"]
    } == {"missing_evidence_handle"}
    assert artifact["traceguard_repair"]["initial_rejection_reasons"] == [
        "missing_evidence_handle"
    ]
    assert (
        artifact["traceguard_repair"][
            "initial_rejection_exclusive_missing_evidence_handle"
        ]
        is True
    )
    assert (
        artifact["traceguard_repair"][
            "initial_rejection_exclusive_repairable_missing_evidence_handle"
        ]
        is True
    )
    assert artifact["traceguard_repair"]["initial_accept"] is False
    assert artifact["traceguard_repair"]["repair_eligible"] is True
    assert artifact["traceguard_repair"]["repair_attempted"] is True
    assert artifact["traceguard_repair"]["failure_reason"] is None
    assert (
        artifact["traceguard_repair"]["repair_strategy"]
        == "patch_missing_evidence_handle_fields"
    )
    assert artifact["traceguard_repair"]["repair_accept"] is True
    assert artifact["traceguard_repair"]["after_validation"]["accepted"] is True
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []
    assert artifact["traceguard_repair"]["parent_synthesis_retry_attempted"] is True
    assert artifact["traceguard_repair"]["parent_synthesis_retry_accept"] is True
    assert artifact["traceguard_repair"]["parent_synthesis_retry_validation"][
        "accepted"
    ] is True
    assert artifact["traceguard_repair"][
        "parent_synthesis_retry_patch_fidelity_errors"
    ] == []
    assert retry_state["scope"] == "parent_synthesis_run"
    assert (
        retry_state["parent_synthesis_run_id"]
        == artifact["trace_structure"]["parent_synthesis_call_id"]
    )
    assert retry_state["synthesis_cell_identity"] == cell_identity
    assert retry_state["repair_attempts_by_cell"] == {
        cell_identity: {
            "attempted": True,
            "attempt_count": 1,
            "max_attempts": 1,
        }
    }
    assert retried_parent_synthesis == artifact["repaired_parent_synthesis"]
    assert artifact["initial_traceguard_validation"] == artifact["traceguard_repair"][
        "before_validation"
    ]
    assert artifact["initial_traceguard_validation"]["accepted"] is False
    assert artifact["effective_parent_synthesis"] == artifact["retried_parent_synthesis"]
    assert artifact["effective_traceguard_validation"] == artifact["traceguard_validation"]
    assert artifact["traceguard_validation"] == artifact["traceguard_repair"][
        "parent_synthesis_retry_validation"
    ]
    assert artifact["traceguard_repair"]["initial_failure_reason"] == (
        "missing_evidence_handle"
    )


@pytest.mark.asyncio
async def test_live_cell_records_repair_attempt_before_repair_runtime_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    events: list[str] = []
    original_record = live_portability.ParentSynthesisRetryState.record_repair_attempt

    def tracking_record_repair_attempt(
        self: live_portability.ParentSynthesisRetryState,
        synthesis_cell_identity: str,
    ) -> bool:
        events.append("record_repair_attempt")
        return original_record(self, synthesis_cell_identity)

    monkeypatch.setattr(
        live_portability.ParentSynthesisRetryState,
        "record_repair_attempt",
        tracking_record_repair_attempt,
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        events=events,
    )

    assert artifact["mandatory_contract_pass"] is True
    assert events.index("record_repair_attempt") < events.index(
        "repair_missing_evidence_handle"
    )
    assert events.count("record_repair_attempt") == 1
    assert events.count("repair_missing_evidence_handle") == 1
    assert events.count("synthesize_parent_answer_from_child_evidence") == 2


@pytest.mark.asyncio
async def test_repair_runtime_error_preserves_original_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_error=RuntimeError("repair provider returned non-json"),
    )
    repair = artifact["traceguard_repair"]

    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["parent_synthesis"] == parent
    assert artifact["effective_parent_synthesis"] == parent
    assert artifact["traceguard_validation"] == artifact["initial_traceguard_validation"]
    assert artifact["traceguard_validation"] == repair["before_validation"]
    assert repair["initial_failure_reason"] == "missing_evidence_handle"
    assert repair["failure_reason"] == "repair_runtime_error"
    assert repair["repair_failure_reason"] == "repair_runtime_error"
    assert repair["repair_attempted"] is True
    assert repair["repair_accept"] is False
    assert "RuntimeError: repair provider returned non-json" in repair[
        "repair_runtime_error"
    ]
    assert repair["after_validation"] is None
    assert repair["parent_synthesis_retry_attempted"] is False
    assert "repaired_parent_synthesis" not in artifact
    assert "retried_parent_synthesis" not in artifact


@pytest.mark.asyncio
async def test_parent_retry_runtime_error_preserves_repair_artifact_without_infra_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_error=RuntimeError("retry provider timed out"),
    )
    repair = artifact["traceguard_repair"]

    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["repaired_parent_synthesis"] == artifact["effective_parent_synthesis"]
    assert artifact["effective_traceguard_validation"] == repair["after_validation"]
    assert artifact["traceguard_validation"] == repair["after_validation"]
    assert repair["initial_failure_reason"] == "missing_evidence_handle"
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_attempted"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert repair["parent_synthesis_retry_failure_reason"] == (
        "parent_synthesis_retry_runtime_error"
    )
    assert "RuntimeError: retry provider timed out" in repair[
        "parent_synthesis_retry_runtime_error"
    ]
    assert repair["parent_synthesis_retry_validation"] is None
    assert "retried_parent_synthesis" not in artifact


@pytest.mark.asyncio
async def test_live_cell_validates_initial_parent_before_repairability_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    events: list[str] = []
    validations: list[dict[str, Any]] = []
    original_validate = live_portability.validate_parent_synthesis
    original_initial_repair_block = live_portability._initial_traceguard_repair_block
    original_schedule_repair = live_portability._schedule_traceguard_repair_attempt

    def tracking_validate_parent_synthesis(
        *,
        evidence_manifest: Any,
        parent_synthesis: dict[str, Any],
    ) -> Any:
        result = original_validate(
            evidence_manifest=evidence_manifest,
            parent_synthesis=parent_synthesis,
        )
        validations.append(
            {
                "parent_synthesis": json.loads(json.dumps(parent_synthesis)),
                "validation": result.to_dict(),
            }
        )
        event = (
            "initial_traceguard_validation"
            if len(validations) == 1
            else "subsequent_traceguard_validation"
        )
        events.append(event)
        return result

    def tracking_initial_traceguard_repair_block(**kwargs: Any) -> dict[str, Any]:
        events.append("repairability_check")
        assert validations
        assert kwargs["validation"].to_dict() == validations[0]["validation"]
        return original_initial_repair_block(**kwargs)

    def tracking_schedule_traceguard_repair_attempt(**kwargs: Any) -> bool:
        events.append("schedule_repair_attempt")
        return original_schedule_repair(**kwargs)

    monkeypatch.setattr(
        live_portability,
        "validate_parent_synthesis",
        tracking_validate_parent_synthesis,
    )
    monkeypatch.setattr(
        live_portability,
        "_initial_traceguard_repair_block",
        tracking_initial_traceguard_repair_block,
    )
    monkeypatch.setattr(
        live_portability,
        "_schedule_traceguard_repair_attempt",
        tracking_schedule_traceguard_repair_attempt,
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        events=events,
    )

    parent_synthesis_indexes = [
        index
        for index, event in enumerate(events)
        if event == "synthesize_parent_answer_from_child_evidence"
    ]
    initial_validation_index = events.index("initial_traceguard_validation")

    assert parent_synthesis_indexes
    assert parent_synthesis_indexes[0] < initial_validation_index
    assert initial_validation_index < events.index("repairability_check")
    assert initial_validation_index < events.index("schedule_repair_attempt")
    assert initial_validation_index < events.index("repair_missing_evidence_handle")
    assert initial_validation_index < parent_synthesis_indexes[1]
    assert validations[0]["parent_synthesis"] == parent
    assert validations[0]["validation"] == artifact["traceguard_repair"][
        "before_validation"
    ]
    assert validations[0]["validation"]["accepted"] is False
    assert artifact["traceguard_repair"]["initial_accept"] is False
    assert artifact["traceguard_repair"]["repair_attempted"] is True


@pytest.mark.asyncio
async def test_live_cell_invokes_traceguard_for_initial_and_repaired_parent_before_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    events: list[str] = []
    validations: list[dict[str, Any]] = []
    original_validate = live_portability.validate_parent_synthesis

    def tracking_validate_parent_synthesis(
        *,
        evidence_manifest: Any,
        parent_synthesis: dict[str, Any],
    ) -> Any:
        result = original_validate(
            evidence_manifest=evidence_manifest,
            parent_synthesis=parent_synthesis,
        )
        validations.append(
            {
                "parent_synthesis": json.loads(json.dumps(parent_synthesis)),
                "validation": result.to_dict(),
            }
        )
        events.append(f"traceguard_validation_{len(validations)}")
        return result

    monkeypatch.setattr(
        live_portability,
        "validate_parent_synthesis",
        tracking_validate_parent_synthesis,
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        events=events,
    )

    parent_synthesis_indexes = [
        index
        for index, event in enumerate(events)
        if event == "synthesize_parent_answer_from_child_evidence"
    ]
    initial_validation_index = events.index("traceguard_validation_1")
    repair_index = events.index("repair_missing_evidence_handle")
    repaired_validation_index = events.index("traceguard_validation_2")
    retry_validation_index = events.index("traceguard_validation_3")

    assert len(validations) == 3
    assert parent_synthesis_indexes[0] < initial_validation_index
    assert initial_validation_index < repair_index
    assert repair_index < repaired_validation_index
    assert repaired_validation_index < parent_synthesis_indexes[1]
    assert parent_synthesis_indexes[1] < retry_validation_index
    assert validations[0]["parent_synthesis"] == parent
    assert validations[0]["validation"] == artifact["traceguard_repair"][
        "before_validation"
    ]
    assert validations[0]["validation"]["accepted"] is False
    assert validations[1]["parent_synthesis"] == artifact["repaired_parent_synthesis"]
    assert validations[1]["validation"] == artifact["traceguard_repair"][
        "after_validation"
    ]
    assert validations[1]["validation"]["accepted"] is True
    assert validations[2]["parent_synthesis"] == artifact["retried_parent_synthesis"]
    assert validations[2]["validation"] == artifact["traceguard_repair"][
        "parent_synthesis_retry_validation"
    ]
    assert validations[2]["validation"]["accepted"] is True
    assert artifact["traceguard_validation"] == validations[2]["validation"]
    assert artifact["traceguard_repair"]["repair_accept"] is True
    assert artifact["traceguard_repair"]["parent_synthesis_retry_attempted"] is True
    assert artifact["traceguard_repair"]["parent_synthesis_retry_accept"] is True


@pytest.mark.asyncio
async def test_live_cell_captures_missing_evidence_handle_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    del parent["result"]["retained_facts"][1]["evidence_chunk_id"]

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
    )

    references = artifact["traceguard_repair"][
        "missing_evidence_handle_references"
    ]
    by_fact = {reference["fact_id"]: reference for reference in references}

    assert artifact["traceguard_repair"]["repair_eligible"] is True
    assert set(by_fact) == {first["fact_id"], second["fact_id"]}
    assert by_fact[first["fact_id"]] == {
        "parent_path": "result.retained_facts[0]",
        "surface": "result.retained_facts",
        "fact_id": first["fact_id"],
        "claim_text": first["text"],
        "evidence_chunk_id_state": "null",
        "evidence_handle": first["chunk_id"],
        "evidence_handles": {
            "allowed_manifest": first["chunk_id"],
            "child_records": [first["chunk_id"]],
        },
    }
    assert by_fact[second["fact_id"]] == {
        "parent_path": "result.retained_facts[1]",
        "surface": "result.retained_facts",
        "fact_id": second["fact_id"],
        "claim_text": second["text"],
        "evidence_chunk_id_state": "missing",
        "evidence_handle": second["chunk_id"],
        "evidence_handles": {
            "allowed_manifest": second["chunk_id"],
            "child_records": [second["chunk_id"]],
        },
    }
    assert artifact["parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] is None
    assert (
        "evidence_chunk_id"
        not in artifact["parent_synthesis"]["result"]["retained_facts"][1]
    )
    assert artifact["repaired_parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] == first["chunk_id"]
    assert artifact["repaired_parent_synthesis"]["result"]["retained_facts"][1][
        "evidence_chunk_id"
    ] == second["chunk_id"]


@pytest.mark.asyncio
async def test_live_cell_applies_only_missing_evidence_chunk_id_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["summary"] = "rewritten summary must be ignored"
    repair_synthesis["result"]["retained_facts"][0][
        "text"
    ] = "rewritten missing claim text must be ignored"
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"][1][
        "text"
    ] = "rewritten valid claim text must be ignored"
    repair_synthesis["result"]["retained_facts"][1][
        "evidence_chunk_id"
    ] = "not-allowed/changed-valid-handle.txt:1-1"
    repair_synthesis["evidence_references"][0][
        "chunk_id"
    ] = "not-allowed/changed-valid-reference.txt:1-1"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    repaired = artifact["repaired_parent_synthesis"]

    assert artifact["mandatory_contract_pass"] is True
    assert artifact["traceguard_validation"]["accepted"] is True
    assert repaired != repair_synthesis
    assert repaired["result"]["summary"] == parent["result"]["summary"]
    assert (
        repaired["result"]["retained_facts"][0]["text"]
        == parent["result"]["retained_facts"][0]["text"]
    )
    assert repaired["result"]["retained_facts"][0]["evidence_chunk_id"] == first[
        "chunk_id"
    ]
    assert (
        repaired["result"]["retained_facts"][1]["text"]
        == parent["result"]["retained_facts"][1]["text"]
    )
    assert repaired["result"]["retained_facts"][1]["evidence_chunk_id"] == second[
        "chunk_id"
    ]
    assert (
        repaired["evidence_references"][0]["chunk_id"]
        == parent["evidence_references"][0]["chunk_id"]
    )
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_preserves_each_original_retained_fact_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    for index, fact in enumerate(repair_synthesis["result"]["retained_facts"]):
        fact["text"] = f"rewritten repair fact text {index}"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    original_texts = [
        fact["text"] for fact in parent["result"]["retained_facts"]
    ]
    repaired_texts = [
        fact["text"]
        for fact in artifact["repaired_parent_synthesis"]["result"]["retained_facts"]
    ]
    retried_texts = [
        fact["text"]
        for fact in artifact["retried_parent_synthesis"]["result"]["retained_facts"]
    ]

    assert artifact["mandatory_contract_pass"] is True
    assert repaired_texts == original_texts
    assert retried_texts == original_texts
    assert all("rewritten repair fact text" not in text for text in repaired_texts)
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []
    assert artifact["traceguard_repair"][
        "parent_synthesis_retry_patch_fidelity_errors"
    ] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_preserves_original_answer_text_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    answer_text = "Answer line 1\n  Answer line 2 with spacing\tand tabs.\n"
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["summary"] = answer_text
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["summary"] = "repair rewrote answer text"
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    repaired_answer = artifact["repaired_parent_synthesis"]["result"]["summary"]

    assert artifact["mandatory_contract_pass"] is True
    assert repaired_answer.encode("utf-8") == answer_text.encode("utf-8")
    assert repaired_answer != repair_synthesis["result"]["summary"]
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_preserves_parent_claim_texts_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["summary"] = "SUMMARY keeps Case, punctuation!?\n  indent\t"
    parent["result"]["fact_id"] = first["fact_id"]
    parent["result"]["statement"] = "Result claim Line A\n  Line B, CASE!?\t"
    parent["result"]["evidence_chunk_id"] = None
    parent["result"]["retained_facts"][0][
        "text"
    ] = "Retained CLAIM A: spaces  punctuation!?\n  next\tline."
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    parent["result"]["retained_facts"][1][
        "text"
    ] = "Retained CLAIM B: keep ORDER; keep Case."
    parent["evidence_references"][0][
        "quoted_evidence"
    ] = "Quoted CLAIM A:\n  exact spacing, Case!?"

    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["summary"] = "repair rewrote summary"
    repair_synthesis["result"]["statement"] = "repair rewrote result claim"
    repair_synthesis["result"]["evidence_chunk_id"] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"][0][
        "text"
    ] = "repair rewrote retained claim"
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"][1][
        "text"
    ] = "repair rewrote another retained claim"
    repair_synthesis["evidence_references"] = list(
        reversed(repair_synthesis["evidence_references"])
    )
    repair_synthesis["evidence_references"][0][
        "quoted_evidence"
    ] = "repair reordered and rewrote quoted evidence"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    original_claim_texts = _parent_claim_text_snapshot(parent)
    repaired_claim_texts = _parent_claim_text_snapshot(
        artifact["repaired_parent_synthesis"]
    )
    retried_claim_texts = _parent_claim_text_snapshot(
        artifact["retried_parent_synthesis"]
    )

    assert artifact["mandatory_contract_pass"] is True
    assert original_claim_texts == repaired_claim_texts
    assert original_claim_texts == retried_claim_texts
    assert original_claim_texts[0]["text"] == (
        "Retained CLAIM A: spaces  punctuation!?\n  next\tline.".encode("utf-8")
    )
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []
    assert artifact["traceguard_repair"][
        "parent_synthesis_retry_patch_fidelity_errors"
    ] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_diff_is_evidence_handle_only_with_claim_text_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["summary"] = "Summary bytes stay exact:\n  Case\tTabs."
    parent["result"]["retained_facts"][0][
        "text"
    ] = "First claim bytes stay exact:\n  Case\tTabs."
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    parent["result"]["retained_facts"][1][
        "text"
    ] = "Second claim bytes stay exact: punctuation !?"
    del parent["result"]["retained_facts"][1]["evidence_chunk_id"]

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
    )

    repaired = artifact["repaired_parent_synthesis"]
    retried = artifact["retried_parent_synthesis"]
    expected_diffs = [
        {
            "path": "$.result.retained_facts[0].evidence_chunk_id",
            "before": None,
            "after": first["chunk_id"],
        },
        {
            "path": "$.result.retained_facts[1].evidence_chunk_id",
            "before": _MISSING,
            "after": second["chunk_id"],
        },
    ]
    expected_artifact_diff = [
        {
            "path": "$.result.retained_facts[0].evidence_chunk_id",
            "before_state": "null",
            "after_state": "value",
            "before": None,
            "after": first["chunk_id"],
        },
        {
            "path": "$.result.retained_facts[1].evidence_chunk_id",
            "before_state": "missing",
            "after_state": "value",
            "after": second["chunk_id"],
        },
    ]

    assert artifact["mandatory_contract_pass"] is True
    assert "repaired_parent_synthesis" in artifact
    assert artifact["traceguard_repair"]["parent_synthesis_diff"] == (
        expected_artifact_diff
    )
    assert _parent_claim_text_snapshot(parent) == _parent_claim_text_snapshot(repaired)
    assert _parent_claim_text_snapshot(parent) == _parent_claim_text_snapshot(retried)
    assert _parent_synthesis_diffs(parent, repaired) == expected_diffs
    assert _parent_synthesis_diffs(parent, retried) == expected_diffs
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []
    assert artifact["traceguard_repair"][
        "parent_synthesis_retry_patch_fidelity_errors"
    ] == []


@pytest.mark.asyncio
async def test_live_cell_repair_does_not_introduce_facts_or_evidence_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"].append(
        {
            "fact_id": "REPAIR-ADDED-FACT",
            "text": "repair-added fact text must be ignored",
            "evidence_chunk_id": first["chunk_id"],
        }
    )
    repair_synthesis["evidence_references"].append(
        {
            "chunk_id": first["chunk_id"],
            "supports_fact_ids": [first["fact_id"]],
            "quoted_evidence": "repair-added evidence content must be ignored",
        }
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    repaired = artifact["repaired_parent_synthesis"]

    assert artifact["mandatory_contract_pass"] is True
    assert artifact["traceguard_repair"]["repair_accept"] is True
    assert repaired["result"]["retained_facts"][0]["evidence_chunk_id"] == first[
        "chunk_id"
    ]
    assert len(repaired["result"]["retained_facts"]) == len(
        parent["result"]["retained_facts"]
    )
    assert len(repaired["evidence_references"]) == len(parent["evidence_references"])
    assert {
        fact["fact_id"] for fact in repaired["result"]["retained_facts"]
    } == {fact["fact_id"] for fact in parent["result"]["retained_facts"]}
    assert all(
        reference.get("quoted_evidence")
        != "repair-added evidence content must be ignored"
        for reference in repaired["evidence_references"]
    )
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_carries_forward_original_retained_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"] = [
        repair_synthesis["result"]["retained_facts"][0],
        repair_synthesis["result"]["retained_facts"][0],
    ]

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    original_fact_ids = [
        fact["fact_id"] for fact in parent["result"]["retained_facts"]
    ]
    repaired_fact_ids = [
        fact["fact_id"]
        for fact in artifact["repaired_parent_synthesis"]["result"]["retained_facts"]
    ]

    assert artifact["mandatory_contract_pass"] is True
    assert repaired_fact_ids == original_fact_ids
    assert len(repaired_fact_ids) == len(original_fact_ids)
    assert len(set(repaired_fact_ids)) == len(set(original_fact_ids))
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []


@pytest.mark.asyncio
async def test_missing_handle_repair_preserves_original_retained_fact_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["retained_facts"][0][
        "fact_id"
    ] = "REPAIR-REWROTE-MISSING-FACT-ID"
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    repair_synthesis["result"]["retained_facts"][1][
        "fact_id"
    ] = "REPAIR-REWROTE-VALID-FACT-ID"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    original_fact_ids = [
        fact["fact_id"] for fact in parent["result"]["retained_facts"]
    ]
    repaired_fact_ids = [
        fact["fact_id"]
        for fact in artifact["repaired_parent_synthesis"]["result"]["retained_facts"]
    ]
    retried_fact_ids = [
        fact["fact_id"]
        for fact in artifact["retried_parent_synthesis"]["result"]["retained_facts"]
    ]

    assert artifact["mandatory_contract_pass"] is True
    assert repaired_fact_ids == original_fact_ids
    assert retried_fact_ids == original_fact_ids
    assert artifact["traceguard_repair"]["patch_fidelity_errors"] == []
    assert artifact["traceguard_repair"][
        "parent_synthesis_retry_patch_fidelity_errors"
    ] == []


@pytest.mark.asyncio
async def test_live_cell_requires_allowed_set_resolution_for_missing_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    child_only_handle = "child-only/not-in-manifest.txt:1-1"
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        child_evidence_chunk_ids_by_fact={first["fact_id"]: child_only_handle},
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    assert tasks.count("repair_missing_evidence_handle") == 0
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 1
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"]["accepted"] is False
    assert artifact["traceguard_repair"]["repair_eligible"] is False
    assert artifact["traceguard_repair"]["repair_attempted"] is False
    assert artifact["traceguard_repair"]["failure_reason"] == "unsupported_fact_id"
    assert (
        artifact["traceguard_repair"]["missing_evidence_handle_resolution_pass"]
        is False
    )
    assert (
        artifact["traceguard_repair"]["repair_strategy"]
        == "not_attempted_non_repairable_traceguard_rejection"
    )
    assert artifact["traceguard_repair"]["repair_accept"] is None
    assert artifact["traceguard_repair"]["parent_synthesis_retry_attempted"] is False
    assert artifact["traceguard_repair"]["parent_synthesis_retry_accept"] is None
    assert "repaired_parent_synthesis" not in artifact
    assert "retried_parent_synthesis" not in artifact
    assert first["chunk_id"] not in artifact["traceguard_repair"][
        "allowed_evidence_handle_set"
    ]
    assert child_only_handle not in artifact["traceguard_repair"][
        "allowed_evidence_handle_set"
    ]
    assert artifact["traceguard_repair"]["missing_evidence_handle_references"] == []


@pytest.mark.asyncio
async def test_live_cell_surfaces_non_repairable_missing_handle_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = ""
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    rejection_reasons = {
        rejection["reason"]
        for rejection in artifact["traceguard_validation"]["rejected_claims"]
    }
    repair = artifact["traceguard_repair"]

    assert rejection_reasons == {"missing_evidence_handle"}
    assert tasks.count("repair_missing_evidence_handle") == 0
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 1
    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"]["accepted"] is False
    assert artifact["parent_synthesis"] == parent
    assert "repaired_parent_synthesis" not in artifact
    assert "retried_parent_synthesis" not in artifact
    assert repair["initial_accept"] is False
    assert repair["repair_eligible"] is False
    assert repair["repair_attempted"] is False
    assert repair["initial_rejection_reasons"] == ["missing_evidence_handle"]
    assert repair["initial_rejection_exclusive_missing_evidence_handle"] is True
    assert (
        repair["initial_rejection_exclusive_repairable_missing_evidence_handle"]
        is False
    )
    assert repair["failure_reason"] == "missing_evidence_handle_unresolved"
    assert (
        repair["repair_strategy"]
        == "not_attempted_non_repairable_traceguard_rejection"
    )
    assert repair["repair_accept"] is None
    assert repair["parent_synthesis_retry_attempted"] is False
    assert repair["parent_synthesis_retry_accept"] is None
    assert repair["before_validation"] == artifact["traceguard_validation"]
    assert repair["after_validation"] is None
    assert repair["missing_evidence_handle_resolution_pass"] is False
    assert repair["missing_evidence_handle_references"] == []


@pytest.mark.asyncio
async def test_live_cell_rejects_repair_eligibility_for_mixed_traceguard_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    parent["result"]["observed_facts"] = [
        {
            "fact_id": "NOT-IN-MANIFEST",
            "text": "unsupported fact",
            "evidence_chunk_id": "unsupported.txt:1-2",
        }
    ]
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    rejection_reasons = {
        rejection["reason"]
        for rejection in artifact["traceguard_validation"]["rejected_claims"]
    }
    assert len(prompts) == len(fixture["selected_chunk_ids"]) + 1
    assert tasks.count("repair_missing_evidence_handle") == 0
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 1
    assert rejection_reasons == {"missing_evidence_handle", "unsupported_fact_id"}
    assert artifact["traceguard_repair"]["repair_eligible"] is False
    assert artifact["traceguard_repair"]["repair_attempted"] is False
    assert set(artifact["traceguard_repair"]["initial_rejection_reasons"]) == {
        "missing_evidence_handle",
        "unsupported_fact_id",
    }
    assert (
        artifact["traceguard_repair"][
            "initial_rejection_exclusive_missing_evidence_handle"
        ]
        is False
    )
    assert (
        artifact["traceguard_repair"][
            "initial_rejection_exclusive_repairable_missing_evidence_handle"
        ]
        is False
    )
    assert (
        artifact["traceguard_repair"]["failure_reason"]
        == "mixed_traceguard_rejection_reasons"
    )
    assert artifact["traceguard_repair"]["parent_synthesis_retry_attempted"] is False
    assert "retried_parent_synthesis" not in artifact
    assert artifact["failure_classification"] == "primary_contract_failure"


async def _run_live_cell_without_provider_calls(
    *,
    monkeypatch: pytest.MonkeyPatch,
    fixture: dict[str, object],
    parent_synthesis: dict[str, object],
    repair_synthesis: dict[str, object] | None = None,
    retry_parent_synthesis: dict[str, object] | None = None,
    repair_error: BaseException | None = None,
    retry_error: BaseException | None = None,
    child_evidence_chunk_ids_by_fact: dict[str, str] | None = None,
    prompts: list[str] | None = None,
    events: list[str] | None = None,
) -> dict[str, object]:
    family = RUNTIME_FAMILIES[0]

    async def fake_execute_json_task(
        runtime: object,
        *,
        prompt: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if prompts is not None:
            prompts.append(prompt)
        payload = json.loads(prompt)
        if events is not None:
            events.append(payload["task"])
        if payload["task"] == "synthesize_parent_answer_from_child_evidence":
            if "retry" in payload:
                if retry_error is not None:
                    raise retry_error
                if retry_parent_synthesis is not None:
                    return retry_parent_synthesis
                return payload["retry"]["repaired_parent_synthesis"]
            return parent_synthesis
        if payload["task"] == "repair_missing_evidence_handle":
            if repair_error is not None:
                raise repair_error
            if repair_synthesis is not None:
                return repair_synthesis
            return _patched_parent_synthesis_from_repair_prompt(payload)

        chunk = payload["chunk"]
        retained_fact = next(
            fact
            for fact in fixture["expected_retained_facts"]  # type: ignore[index]
            if fact["chunk_id"] == chunk["chunk_id"]
        )
        evidence_chunk_id = retained_fact["chunk_id"]
        if child_evidence_chunk_ids_by_fact is not None:
            evidence_chunk_id = child_evidence_chunk_ids_by_fact.get(
                retained_fact["fact_id"],
                retained_fact["chunk_id"],
            )
        return {
            "observed_facts": [
                {
                    "fact_id": retained_fact["fact_id"],
                    "text": retained_fact["text"],
                    "evidence_chunk_id": evidence_chunk_id,
                }
            ],
            "residual_gaps": [],
        }

    monkeypatch.setattr(live_portability, "_build_runtime", lambda family: object())
    monkeypatch.setattr(
        live_portability,
        "_execute_json_task",
        fake_execute_json_task,
    )

    return await live_portability._run_live_rlm_traceguard_cell(  # noqa: SLF001
        family=family,
        fixture=fixture,
        timeout_seconds=1,
    )


def _patched_parent_synthesis_from_repair_prompt(
    payload: dict[str, object],
) -> dict[str, object]:
    repaired = json.loads(json.dumps(payload["original_parent_synthesis"]))
    allowed_by_fact = {
        item["fact_id"]: item["chunk_id"]
        for item in payload["allowed_evidence_manifest"]  # type: ignore[index]
    }
    for fact in repaired["result"]["retained_facts"]:
        if fact.get("evidence_chunk_id") is None:
            fact["evidence_chunk_id"] = allowed_by_fact[fact["fact_id"]]
    return repaired


def _reverse_mapping_order(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _reverse_mapping_order(value[key])
            for key in reversed(list(value))
        }
    if isinstance(value, list):
        return [_reverse_mapping_order(item) for item in value]
    return value


def _parent_claim_text_snapshot(
    parent_synthesis: dict[str, object],
) -> list[dict[str, object]]:
    return [
        {
            "surface": claim.surface,
            "fact_id": claim.fact_id,
            "text": claim.text.encode("utf-8"),
        }
        for claim in extract_parent_claims(parent_synthesis)
    ]


_MISSING = object()


def _parent_synthesis_diffs(
    original: object,
    repaired: object,
    *,
    path: str = "$",
) -> list[dict[str, object]]:
    if isinstance(original, dict) and isinstance(repaired, dict):
        diffs: list[dict[str, object]] = []
        for key in sorted(original.keys() | repaired.keys()):
            before = original.get(key, _MISSING)
            after = repaired.get(key, _MISSING)
            diffs.extend(
                _parent_synthesis_diffs(before, after, path=f"{path}.{key}")
            )
        return diffs

    if isinstance(original, list) and isinstance(repaired, list):
        diffs = []
        for index in range(max(len(original), len(repaired))):
            before = original[index] if index < len(original) else _MISSING
            after = repaired[index] if index < len(repaired) else _MISSING
            diffs.extend(
                _parent_synthesis_diffs(before, after, path=f"{path}[{index}]")
            )
        return diffs

    if original == repaired:
        return []
    return [{"path": path, "before": original, "after": repaired}]


@pytest.mark.asyncio
async def test_failed_missing_handle_repair_does_not_retry_parent_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=parent,
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    repair = artifact["traceguard_repair"]

    assert len(prompts) == len(fixture["selected_chunk_ids"]) + 2
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 1
    assert tasks.count("repair_missing_evidence_handle") == 1
    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"]["accepted"] is False
    assert artifact["parent_synthesis"] == parent
    assert artifact["repaired_parent_synthesis"] == parent
    assert repair["initial_accept"] is False
    assert repair["repair_eligible"] is True
    assert repair["repair_attempted"] is True
    assert repair["repair_accept"] is False
    assert repair["failure_reason"] == "missing_evidence_handle"
    assert repair["before_validation"]["accepted"] is False
    assert repair["after_validation"]["accepted"] is False
    assert repair["patch_fidelity_errors"] == []
    assert repair["parent_synthesis_retry_attempted"] is False
    assert repair["parent_synthesis_retry_accept"] is None
    assert repair["parent_synthesis_retry_validation"] is None
    assert repair["subsequent_repair_attempted"] is False
    assert repair["subsequent_repair_skip_reason"] == "repair_attempt_already_used"
    assert "retried_parent_synthesis" not in artifact


@pytest.mark.asyncio
async def test_successful_missing_handle_repair_retries_parent_synthesis_once_after_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    retry_payload = json.loads(prompts[-1])
    repair = artifact["traceguard_repair"]

    assert len(prompts) == len(fixture["selected_chunk_ids"]) + 3
    assert tasks[-3:] == [
        "synthesize_parent_answer_from_child_evidence",
        "repair_missing_evidence_handle",
        "synthesize_parent_answer_from_child_evidence",
    ]
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 2
    assert tasks.count("repair_missing_evidence_handle") == 1
    assert retry_payload["retry"]["attempt"] == 1
    assert retry_payload["retry"]["trigger"] == (
        "traceguard_missing_evidence_handle_repair_accept"
    )
    assert retry_payload["retry"]["repair_accept"] is True
    assert retry_payload["retry"]["repaired_parent_synthesis"] == artifact[
        "repaired_parent_synthesis"
    ]
    assert artifact["mandatory_contract_pass"] is True
    assert artifact["traceguard_validation"]["accepted"] is True
    assert artifact["retried_parent_synthesis"] == artifact["repaired_parent_synthesis"]
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_attempted"] is True
    assert repair["parent_synthesis_retry_accept"] is True
    assert repair["parent_synthesis_retry_validation"]["accepted"] is True
    assert repair["parent_synthesis_retry_failure_reason"] is None
    assert repair["subsequent_repair_attempted"] is False
    assert repair["subsequent_repair_skip_reason"] is None


@pytest.mark.asyncio
async def test_parent_synthesis_retry_rejects_dropped_or_duplicated_retained_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    retry_parent_synthesis = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    retry_parent_synthesis["result"]["retained_facts"][1] = json.loads(
        json.dumps(retry_parent_synthesis["result"]["retained_facts"][0])
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent_synthesis,
    )
    repair = artifact["traceguard_repair"]
    retry_errors = repair["parent_synthesis_retry_patch_fidelity_errors"]

    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"]["accepted"] is True
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_attempted"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert (
        repair["parent_synthesis_retry_failure_reason"]
        == "parent_synthesis_retry_patch_fidelity_failed"
    )
    assert any(
        f"dropped retained fact {second['fact_id']}" in error
        for error in retry_errors
    )
    assert any(
        f"duplicated retained fact {first['fact_id']}" in error
        for error in retry_errors
    )


@pytest.mark.asyncio
async def test_parent_synthesis_retry_rejects_retained_fact_identity_swaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    retry_parent_synthesis = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    retry_retained_facts = retry_parent_synthesis["result"]["retained_facts"]
    retry_retained_facts[0], retry_retained_facts[1] = (
        retry_retained_facts[1],
        retry_retained_facts[0],
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent_synthesis,
    )
    repair = artifact["traceguard_repair"]
    retry_errors = repair["parent_synthesis_retry_patch_fidelity_errors"]

    assert artifact["mandatory_contract_pass"] is False
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert (
        repair["parent_synthesis_retry_failure_reason"]
        == "parent_synthesis_retry_patch_fidelity_failed"
    )
    assert any(
        "changed retained fact identity "
        f"from {first['fact_id']} to {second['fact_id']}" in error
        for error in retry_errors
    )
    assert any(
        "changed retained fact identity "
        f"from {second['fact_id']} to {first['fact_id']}" in error
        for error in retry_errors
    )


@pytest.mark.asyncio
async def test_parent_synthesis_retry_rejects_retained_fact_text_rewrites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    retry_parent_synthesis = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    retry_parent_synthesis["result"]["retained_facts"][0][
        "text"
    ] = "retry rewrote retained fact text"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent_synthesis,
    )
    repair = artifact["traceguard_repair"]
    retry_errors = repair["parent_synthesis_retry_patch_fidelity_errors"]

    assert artifact["mandatory_contract_pass"] is False
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert (
        repair["parent_synthesis_retry_failure_reason"]
        == "parent_synthesis_retry_patch_fidelity_failed"
    )
    assert any(
        "$.result.retained_facts[0].text changed retained fact text "
        f"for {first['fact_id']}" in error
        for error in retry_errors
    )


@pytest.mark.asyncio
async def test_parent_synthesis_retry_rejects_parent_claim_text_order_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    retry_parent_synthesis = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    retry_parent_synthesis["evidence_references"] = list(
        reversed(retry_parent_synthesis["evidence_references"])
    )

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent_synthesis,
    )
    repair = artifact["traceguard_repair"]
    retry_errors = repair["parent_synthesis_retry_patch_fidelity_errors"]

    assert artifact["mandatory_contract_pass"] is False
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert (
        repair["parent_synthesis_retry_failure_reason"]
        == "parent_synthesis_retry_patch_fidelity_failed"
    )
    assert any(
        "parent claim" in error
        and "order changed" in error
        and "evidence_references" in error
        for error in retry_errors
    )


@pytest.mark.asyncio
async def test_parent_synthesis_retry_rejects_handle_mutation_outside_rejected_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first = fixture["expected_retained_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    parent["result"]["unvalidated_handle_note"] = {
        "fact_id": first["fact_id"],
        "text": "This is not a TraceGuard claim-bearing surface.",
        "evidence_chunk_id": None,
    }
    retry_parent_synthesis = json.loads(json.dumps(parent))
    retry_parent_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = first["chunk_id"]
    retry_parent_synthesis["result"]["unvalidated_handle_note"][
        "evidence_chunk_id"
    ] = first["chunk_id"]

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent_synthesis,
    )
    repair = artifact["traceguard_repair"]
    retry_errors = repair["parent_synthesis_retry_patch_fidelity_errors"]

    assert artifact["mandatory_contract_pass"] is False
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_validation"]["accepted"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert (
        repair["parent_synthesis_retry_failure_reason"]
        == "parent_synthesis_retry_patch_fidelity_failed"
    )
    assert (
        "$.result.unvalidated_handle_note.evidence_chunk_id changed outside "
        "the repairable missing_evidence_handle fields"
    ) in retry_errors


@pytest.mark.asyncio
async def test_rejected_parent_synthesis_retry_is_final_after_existing_repair_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    retry_parent = json.loads(json.dumps(parent))
    prompts: list[str] = []

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        retry_parent_synthesis=retry_parent,
        prompts=prompts,
    )

    tasks = [json.loads(prompt)["task"] for prompt in prompts]
    repair = artifact["traceguard_repair"]
    retry_rejection_reasons = {
        rejection["reason"]
        for rejection in repair["parent_synthesis_retry_validation"]["rejected_claims"]
    }
    retry_state = repair["retry_orchestration_state"]["repair_attempts_by_cell"][
        artifact["trace_structure"]["synthesis_cell_identity"]
    ]

    assert len(prompts) == len(fixture["selected_chunk_ids"]) + 3
    assert tasks.count("repair_missing_evidence_handle") == 1
    assert tasks.count("synthesize_parent_answer_from_child_evidence") == 2
    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"] == repair[
        "parent_synthesis_retry_validation"
    ]
    assert artifact["retried_parent_synthesis"] == retry_parent
    assert repair["repair_attempted"] is True
    assert repair["repair_accept"] is True
    assert repair["parent_synthesis_retry_attempted"] is True
    assert repair["parent_synthesis_retry_accept"] is False
    assert repair["parent_synthesis_retry_failure_reason"] == (
        "missing_evidence_handle"
    )
    assert retry_rejection_reasons == {"missing_evidence_handle"}
    assert repair["subsequent_repair_attempted"] is False
    assert repair["subsequent_repair_skip_reason"] == "repair_attempt_already_used"
    assert retry_state == {
        "attempted": True,
        "attempt_count": 1,
        "max_attempts": 1,
    }


@pytest.mark.asyncio
async def test_missing_handle_repair_skips_and_rejects_handle_outside_allowed_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    repair_synthesis = json.loads(json.dumps(parent))
    repair_synthesis["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] = "not-allowed/not-in-manifest.txt:1-1"

    artifact = await _run_live_cell_without_provider_calls(
        monkeypatch=monkeypatch,
        fixture=fixture,
        parent_synthesis=parent,
        repair_synthesis=repair_synthesis,
    )

    repair = artifact["traceguard_repair"]

    assert artifact["mandatory_contract_pass"] is False
    assert artifact["repaired_parent_synthesis"] == parent
    assert artifact["repaired_parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] is None
    assert repair["repair_eligible"] is True
    assert repair["repair_attempted"] is True
    assert repair["repair_accept"] is False
    assert repair["failure_reason"] == "repair_patch_fidelity_failed"
    assert {
        rejection["reason"] for rejection in repair["after_validation"]["rejected_claims"]
    } == {"missing_evidence_handle"}
    assert repair["parent_synthesis_retry_attempted"] is False
    assert "retried_parent_synthesis" not in artifact
    assert any(
        "$.result.retained_facts[0].evidence_chunk_id proposed a handle outside "
        "the allowed evidence-handle set" in error
        for error in repair["patch_fidelity_errors"]
    )


def test_traceguard_repair_prompt_builder_accepts_only_contract_inputs() -> None:
    fixture = generate_primary_fixtures(count=8)[-1]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][1]["evidence_chunk_id"] = None
    manifest = tuple(reversed(build_manifest_from_fixture(fixture)))
    validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    child_records = [
        {
            "call_id": f"child::{index}",
            "parent_call_id": "root",
            "chunk_id": fact["chunk_id"],
            "output": {
                "observed_facts": [
                    {
                        "fact_id": fact["fact_id"],
                        "text": fact["text"],
                        "evidence_chunk_id": fact["chunk_id"],
                    }
                ],
                "residual_gaps": [],
            },
        }
        for index, fact in enumerate(fixture["expected_retained_facts"], start=1)
    ]
    child_records = list(reversed(child_records))

    model = live_portability.TraceGuardRepairPromptInput.from_contract_inputs(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=manifest,
        original_parent_synthesis=parent,
        child_records=child_records,
    )
    signature = inspect.signature(live_portability.build_traceguard_repair_prompt)
    assert [field.name for field in fields(model)] == [
        "rejected_claim",
        "allowed_evidence_manifest",
        "original_parent_synthesis",
        "child_records",
    ]
    assert set(model.to_dict()) == {
        "rejected_claim",
        "allowed_evidence_manifest",
        "original_parent_synthesis",
        "child_records",
    }
    assert list(signature.parameters) == [
        "rejected_claim",
        "allowed_evidence_manifest",
        "original_parent_synthesis",
        "child_records",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )

    prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=manifest,
        original_parent_synthesis=parent,
        child_records=child_records,
    )
    payload = json.loads(prompt)

    assert prompt == live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=manifest,
        original_parent_synthesis=parent,
        child_records=child_records,
    )
    assert validation.accepted is False
    assert rejected_claim.reason == "missing_evidence_handle"
    assert set(payload) == {
        "allowed_evidence_manifest",
        "child_records",
        "original_parent_synthesis",
        "repair_prompt_sections",
        "rejected_claim",
        "rules",
        "task",
    }
    assert [section["label"] for section in payload["repair_prompt_sections"]] == [
        "Rejected claim",
        "Allowed evidence manifest",
        "Original parent synthesis",
        "Child records",
    ]
    assert [section["input_key"] for section in payload["repair_prompt_sections"]] == [
        "rejected_claim",
        "allowed_evidence_manifest",
        "original_parent_synthesis",
        "child_records",
    ]
    assert payload["rejected_claim"] == rejected_claim.to_dict()
    assert payload["allowed_evidence_manifest"] == list(
        live_portability.normalize_repair_prompt_evidence_manifest(manifest)
    )
    assert payload["allowed_evidence_manifest"] != [
        item.to_dict() for item in manifest
    ]
    assert all(
        "child_call_id" not in item for item in payload["allowed_evidence_manifest"]
    )
    assert payload["original_parent_synthesis"] == (
        live_portability.normalize_repair_prompt_parent_synthesis(parent)
    )
    assert payload["child_records"] == list(
        live_portability.normalize_repair_prompt_child_records(child_records)
    )
    assert payload["child_records"] != child_records
    assert all("call_id" not in record for record in payload["child_records"])
    assert all("parent_call_id" not in record for record in payload["child_records"])
    assert payload["repair_prompt_sections"] == [
        {
            "label": "Rejected claim",
            "input_key": "rejected_claim",
            "content": payload["rejected_claim"],
        },
        {
            "label": "Allowed evidence manifest",
            "input_key": "allowed_evidence_manifest",
            "content": payload["allowed_evidence_manifest"],
        },
        {
            "label": "Original parent synthesis",
            "input_key": "original_parent_synthesis",
            "content": payload["original_parent_synthesis"],
        },
        {
            "label": "Child records",
            "input_key": "child_records",
            "content": payload["child_records"],
        },
    ]


def test_traceguard_repair_prompt_sections_include_every_required_input() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    manifest = build_manifest_from_fixture(fixture)
    validation = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    child_records = [
        {
            "call_id": f"child::{index}",
            "parent_call_id": "root",
            "chunk_id": fact["chunk_id"],
            "output": {
                "observed_facts": [
                    {
                        "fact_id": fact["fact_id"],
                        "text": fact["text"],
                        "evidence_chunk_id": fact["chunk_id"],
                    }
                ],
                "residual_gaps": [],
            },
        }
        for index, fact in enumerate(fixture["expected_retained_facts"], start=1)
    ]
    required_sections = {
        "rejected_claim": "Rejected claim",
        "allowed_evidence_manifest": "Allowed evidence manifest",
        "original_parent_synthesis": "Original parent synthesis",
        "child_records": "Child records",
    }

    prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=manifest,
        original_parent_synthesis=parent,
        child_records=child_records,
    )
    payload = json.loads(prompt)
    sections = payload["repair_prompt_sections"]

    assert validation.accepted is False
    assert rejected_claim.reason == "missing_evidence_handle"
    assert len(sections) == len(required_sections)
    assert [section["input_key"] for section in sections] == list(required_sections)
    for input_key, label in required_sections.items():
        section = sections[list(required_sections).index(input_key)]
        assert f'"input_key": "{input_key}"' in prompt
        assert f'"label": "{label}"' in prompt
        assert section == {
            "label": label,
            "input_key": input_key,
            "content": payload[input_key],
        }


def test_traceguard_repair_prompt_identical_inputs_are_byte_identical() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    manifest = build_manifest_from_fixture(fixture)
    validation = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    child_records = [
        {
            "call_id": f"child::{index}",
            "parent_call_id": "root",
            "chunk_id": fact["chunk_id"],
            "output": {
                "observed_facts": [
                    {
                        "fact_id": fact["fact_id"],
                        "text": fact["text"],
                        "evidence_chunk_id": fact["chunk_id"],
                    }
                ],
                "residual_gaps": [],
            },
        }
        for index, fact in enumerate(fixture["expected_retained_facts"], start=1)
    ]

    prompt_bytes = [
        live_portability.build_traceguard_repair_prompt(
            rejected_claim=rejected_claim,
            allowed_evidence_manifest=manifest,
            original_parent_synthesis=parent,
            child_records=child_records,
        ).encode("utf-8")
        for _ in range(3)
    ]

    assert validation.accepted is False
    assert rejected_claim.reason == "missing_evidence_handle"
    assert prompt_bytes[0] == prompt_bytes[1] == prompt_bytes[2]


def test_traceguard_repair_prompt_serialization_is_order_independent() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    first, second = fixture["expected_retained_facts"][:2]
    child_records = [
        {
            "output": {
                "residual_gaps": ["z gap", "a gap"],
                "observed_facts": [
                    {
                        "text": second["text"],
                        "evidence_chunk_id": second["chunk_id"],
                        "fact_id": second["fact_id"],
                    },
                    {
                        "evidence_chunk_id": first["chunk_id"],
                        "fact_id": first["fact_id"],
                        "text": first["text"],
                    },
                ],
            },
            "chunk_id": second["chunk_id"],
            "parent_call_id": "root",
            "call_id": "child::2",
        },
        {
            "call_id": "child::1",
            "parent_call_id": "root",
            "chunk_id": first["chunk_id"],
            "output": {
                "observed_facts": [
                    {
                        "fact_id": first["fact_id"],
                        "text": first["text"],
                        "evidence_chunk_id": first["chunk_id"],
                    },
                    {
                        "fact_id": second["fact_id"],
                        "text": second["text"],
                        "evidence_chunk_id": second["chunk_id"],
                    },
                ],
                "residual_gaps": ["a gap", "z gap"],
            },
        },
    ]
    reordered_child_records = [
        _reverse_mapping_order(record) for record in reversed(child_records)
    ]

    prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=tuple(reversed(build_manifest_from_fixture(fixture))),
        original_parent_synthesis=parent,
        child_records=child_records,
    )
    reordered_prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=build_manifest_from_fixture(fixture),
        original_parent_synthesis=_reverse_mapping_order(parent),
        child_records=reordered_child_records,
    )
    payload = json.loads(prompt)

    assert prompt == reordered_prompt
    assert payload["allowed_evidence_manifest"] == list(
        live_portability.normalize_repair_prompt_evidence_manifest(
            build_manifest_from_fixture(fixture)
        )
    )
    assert payload["child_records"] == list(
        live_portability.normalize_repair_prompt_child_records(child_records)
    )


def test_traceguard_repair_prompt_excludes_nondeterministic_rendered_content() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    first, second = fixture["expected_retained_facts"][:2]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    noisy_parent = json.loads(json.dumps(parent))
    reordered_noisy_parent = _reverse_mapping_order(json.loads(json.dumps(parent)))
    noisy_parent["requestId"] = "018f4d93-20fc-7f88-9a11-3a2aef9e1000"
    noisy_parent["generatedAt"] = "2026-05-03T10:11:12Z"
    reordered_noisy_parent["requestId"] = (
        "018f4d93-20fc-7f88-9a11-3a2aef9e2000"
    )
    reordered_noisy_parent["generatedAt"] = "2026-05-03T11:12:13Z"
    noisy_parent["metadata"] = {
        "generated_at": "2026-05-03T10:11:12Z",
        "request_id": "018f4d93-20fc-7f88-9a11-3a2aef9e1000",
        "unordered_dump": {"b": 2, "a": 1},
    }
    reordered_noisy_parent["metadata"] = {
        "unordered_dump": {"a": 1, "b": 2},
        "request_id": "018f4d93-20fc-7f88-9a11-3a2aef9e2000",
        "generated_at": "2026-05-03T11:12:13Z",
    }
    child_records = [
        {
            "call_id": "runtime-child-018f4d93-20fc-7f88-9a11-3a2aef9e1000",
            "parent_call_id": "runtime-parent-018f4d93-20fc",
            "chunk_id": first["chunk_id"],
            "started_at": "2026-05-03T10:11:12Z",
            "output": {
                "observed_facts": [
                    {
                        "fact_id": first["fact_id"],
                        "text": first["text"],
                        "evidence_chunk_id": first["chunk_id"],
                        "trace_id": "trace-a",
                    }
                ],
                "residual_gaps": [],
                "debug_dump": {"z": 1, "a": 2},
            },
        },
        {
            "call_id": "runtime-child-018f4d93-20fc-7f88-9a11-3a2aef9e2000",
            "parent_call_id": "runtime-parent-018f4d93-20fd",
            "chunk_id": second["chunk_id"],
            "started_at": "2026-05-03T11:12:13Z",
            "output": {
                "observed_facts": [
                    {
                        "fact_id": second["fact_id"],
                        "text": second["text"],
                        "evidence_chunk_id": second["chunk_id"],
                        "trace_id": "trace-b",
                    }
                ],
                "residual_gaps": [],
                "debug_dump": {"a": 2, "z": 1},
            },
        },
    ]
    reordered_child_records = [
        _reverse_mapping_order(
            {
                **child_records[1],
                "call_id": "runtime-child-018f4d93-20fc-different-b",
                "parent_call_id": "runtime-parent-different-b",
                "started_at": "2026-05-03T12:13:14Z",
            }
        ),
        _reverse_mapping_order(
            {
                **child_records[0],
                "call_id": "runtime-child-018f4d93-20fc-different-a",
                "parent_call_id": "runtime-parent-different-a",
                "started_at": "2026-05-03T13:14:15Z",
            }
        ),
    ]
    manifest = (
        {
            "fact_id": first["fact_id"],
            "chunk_id": first["chunk_id"],
            "text": first["text"],
            "child_call_id": "runtime-child-a",
        },
        {
            "fact_id": second["fact_id"],
            "chunk_id": second["chunk_id"],
            "text": second["text"],
            "child_call_id": "runtime-child-b",
        },
    )
    reordered_manifest = tuple(
        _reverse_mapping_order(
            {
                **item,
                "child_call_id": f"runtime-child-different-{index}",
            }
        )
        for index, item in enumerate(reversed(manifest), start=1)
    )

    prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=manifest,
        original_parent_synthesis=noisy_parent,
        child_records=child_records,
    )
    reordered_prompt = live_portability.build_traceguard_repair_prompt(
        rejected_claim=rejected_claim,
        allowed_evidence_manifest=reordered_manifest,
        original_parent_synthesis=reordered_noisy_parent,
        child_records=reordered_child_records,
    )
    payload = json.loads(prompt)

    assert prompt == reordered_prompt
    assert "2026-05-03T10:11:12Z" not in prompt
    assert "018f4d93-20fc-7f88-9a11-3a2aef9e1000" not in prompt
    assert "requestId" not in prompt
    assert "generatedAt" not in prompt
    assert "runtime-child-a" not in prompt
    assert "runtime-parent" not in prompt
    assert "debug_dump" not in prompt
    assert "metadata" not in payload["original_parent_synthesis"]
    assert payload["original_parent_synthesis"]["result"]["retained_facts"][0][
        "fact_id"
    ] == first["fact_id"]
    assert payload["original_parent_synthesis"]["result"]["retained_facts"][0][
        "evidence_chunk_id"
    ] is None
    assert payload["child_records"][0]["chunk_id"] == first["chunk_id"]
    assert payload["allowed_evidence_manifest"][0]["chunk_id"] == first["chunk_id"]


def test_traceguard_repair_normalized_serialization_matches_equivalent_orders() -> None:
    fixture = generate_primary_fixtures(count=8)[0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"][0]["evidence_chunk_id"] = None
    validation = validate_parent_synthesis(
        evidence_manifest=build_manifest_from_fixture(fixture),
        parent_synthesis=parent,
    )
    rejected_claim = validation.rejected_claims[0]
    first, second = fixture["expected_retained_facts"][:2]
    manifest = (
        {
            "text": first["text"],
            "child_call_id": "child_0001",
            "chunk_id": first["chunk_id"],
            "ignored": "not part of the repair contract",
            "fact_id": first["fact_id"],
        },
        {
            "fact_id": second["fact_id"],
            "ignored": "not part of the repair contract",
            "chunk_id": second["chunk_id"],
            "child_call_id": "child_0002",
            "text": second["text"],
        },
    )
    reordered_manifest = tuple(
        _reverse_mapping_order(item)
        for item in reversed(manifest)
    )
    child_records = [
        {
            "output": {
                "residual_gaps": ["z gap", "a gap"],
                "observed_facts": [
                    {
                        "text": second["text"],
                        "fact_id": second["fact_id"],
                        "evidence_chunk_id": second["chunk_id"],
                    },
                    {
                        "evidence_chunk_id": first["chunk_id"],
                        "text": first["text"],
                        "fact_id": first["fact_id"],
                    },
                ],
            },
            "ignored": "not part of the repair contract",
            "chunk_id": first["chunk_id"],
            "parent_call_id": "root",
            "call_id": "child::1",
        },
        {
            "call_id": "child::2",
            "parent_call_id": "root",
            "chunk_id": second["chunk_id"],
            "output": {
                "observed_facts": [
                    {
                        "fact_id": second["fact_id"],
                        "text": second["text"],
                        "evidence_chunk_id": second["chunk_id"],
                    }
                ],
                "residual_gaps": [],
            },
        },
    ]
    reordered_child_records = [
        _reverse_mapping_order(
            {
                **child_records[1],
                "output": {
                    "residual_gaps": [],
                    "observed_facts": [
                        {
                            "evidence_chunk_id": second["chunk_id"],
                            "fact_id": second["fact_id"],
                            "text": second["text"],
                        }
                    ],
                },
            }
        ),
        _reverse_mapping_order(
            {
                **child_records[0],
                "output": {
                    "observed_facts": [
                        {
                            "fact_id": first["fact_id"],
                            "text": first["text"],
                            "evidence_chunk_id": first["chunk_id"],
                        },
                        {
                            "evidence_chunk_id": second["chunk_id"],
                            "text": second["text"],
                            "fact_id": second["fact_id"],
                        },
                    ],
                    "residual_gaps": ["a gap", "z gap"],
                },
            }
        ),
    ]

    normalized_manifest = normalize_allowed_evidence_manifest(manifest)
    reordered_normalized_manifest = normalize_allowed_evidence_manifest(
        reordered_manifest
    )
    normalized_child_records = live_portability.normalize_child_records(child_records)
    reordered_normalized_child_records = live_portability.normalize_child_records(
        reordered_child_records
    )
    serialized = live_portability._serialize_traceguard_repair_prompt_payload(  # noqa: SLF001
        live_portability._traceguard_repair_prompt_payload(  # noqa: SLF001
            live_portability.TraceGuardRepairPromptInput(
                rejected_claim=rejected_claim.to_dict(),
                allowed_evidence_manifest=normalized_manifest,
                original_parent_synthesis=parent,
                child_records=normalized_child_records,
            )
        )
    )
    reordered_serialized = live_portability._serialize_traceguard_repair_prompt_payload(  # noqa: SLF001
        live_portability._traceguard_repair_prompt_payload(  # noqa: SLF001
            live_portability.TraceGuardRepairPromptInput(
                rejected_claim=rejected_claim.to_dict(),
                allowed_evidence_manifest=reordered_normalized_manifest,
                original_parent_synthesis=_reverse_mapping_order(parent),
                child_records=reordered_normalized_child_records,
            )
        )
    )

    assert validation.accepted is False
    assert rejected_claim.reason == "missing_evidence_handle"
    assert normalized_manifest == reordered_normalized_manifest
    assert normalized_child_records == reordered_normalized_child_records
    assert serialized == reordered_serialized


def test_traceguard_repair_child_record_normalization_is_canonical() -> None:
    child_records = [
        {
            "call_id": "child::2",
            "parent_call_id": "root",
            "chunk_id": "traceguard.txt:2-2",
            "output": {
                "residual_gaps": ["z gap", "a gap"],
                "observed_facts": [
                    {
                        "text": "second fact",
                        "fact_id": "TG-002",
                        "evidence_chunk_id": "traceguard.txt:2-2",
                        "ignored": "not part of the repair contract",
                    },
                    {
                        "evidence_chunk_id": "traceguard.txt:2-2",
                        "fact_id": "TG-001",
                        "text": "first fact",
                    },
                ],
            },
            "ignored": "not part of the repair contract",
        },
        {
            "call_id": "child::1",
            "parent_call_id": "root",
            "chunk_id": "traceguard.txt:1-1",
            "output": {
                "observed_facts": [
                    {
                        "chunk_id": "traceguard.txt:1-1",
                        "fact_id": "TG-000",
                        "text": "zeroth fact",
                    }
                ],
                "residual_gaps": [],
            },
        },
    ]

    normalized = live_portability.normalize_child_records(child_records)

    assert normalized == (
        {
            "call_id": "child::1",
            "parent_call_id": "root",
            "chunk_id": "traceguard.txt:1-1",
            "output": {
                "observed_facts": [
                    {
                        "fact_id": "TG-000",
                        "evidence_chunk_id": "traceguard.txt:1-1",
                        "text": "zeroth fact",
                    }
                ],
                "residual_gaps": [],
            },
        },
        {
            "call_id": "child::2",
            "parent_call_id": "root",
            "chunk_id": "traceguard.txt:2-2",
            "output": {
                "observed_facts": [
                    {
                        "fact_id": "TG-001",
                        "evidence_chunk_id": "traceguard.txt:2-2",
                        "text": "first fact",
                    },
                    {
                        "fact_id": "TG-002",
                        "evidence_chunk_id": "traceguard.txt:2-2",
                        "text": "second fact",
                    },
                ],
                "residual_gaps": ["a gap", "z gap"],
            },
        },
    )
    assert list(normalized[0]) == [
        "call_id",
        "parent_call_id",
        "chunk_id",
        "output",
    ]
    assert list(normalized[0]["output"]) == ["observed_facts", "residual_gaps"]
    assert list(normalized[0]["output"]["observed_facts"][0]) == [
        "fact_id",
        "evidence_chunk_id",
        "text",
    ]


@pytest.mark.asyncio
async def test_mixed_missing_evidence_handle_does_not_attempt_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = RUNTIME_FAMILIES[0]
    fixture = generate_primary_fixtures(count=8)[0]
    retained = fixture["expected_retained_facts"][0]
    omitted = fixture["expected_omitted_facts"][0]
    parent = json.loads(json.dumps(fixture["safe_parent_synthesis"]))
    parent["result"]["retained_facts"] = [
        {
            "fact_id": retained["fact_id"],
            "text": retained["text"],
            "evidence_chunk_id": None,
        }
    ]
    parent["result"]["observed_facts"] = [
        {
            "fact_id": omitted["fact_id"],
            "text": omitted["text"],
            "evidence_chunk_id": omitted["chunk_id"],
        }
    ]
    parent["evidence_references"] = []
    prompts: list[str] = []

    async def fake_execute_json_task(runtime, *, prompt, timeout_seconds):  # type: ignore[no-untyped-def]
        prompts.append(prompt)
        if len(prompts) <= len(fixture["selected_chunk_ids"]):
            return {"observed_facts": [], "residual_gaps": []}
        return parent

    monkeypatch.setattr(live_portability, "_build_runtime", lambda family: object())
    monkeypatch.setattr(
        live_portability,
        "_execute_json_task",
        fake_execute_json_task,
    )

    artifact = await live_portability._run_live_rlm_traceguard_cell(  # noqa: SLF001
        family=family,
        fixture=fixture,
        timeout_seconds=1,
    )

    reasons = [
        rejection["reason"]
        for rejection in artifact["traceguard_validation"]["rejected_claims"]
    ]
    repair = artifact["traceguard_repair"]

    assert reasons == ["unsupported_fact_id", "unsupported_fact_id"]
    assert len(prompts) == len(fixture["selected_chunk_ids"]) + 1
    assert artifact["status"] == "primary_contract_failure"
    assert artifact["failure_classification"] == "primary_contract_failure"
    assert artifact["mandatory_contract_pass"] is False
    assert artifact["traceguard_validation"]["accepted"] is False
    assert artifact["parent_synthesis"] == parent
    assert "repaired_parent_synthesis" not in artifact
    assert repair["initial_accept"] is False
    assert repair["repair_eligible"] is False
    assert repair["repair_attempted"] is False
    assert repair["failure_reason"] == "unsupported_fact_id"
    assert repair["repair_strategy"] == "not_attempted_non_repairable_traceguard_rejection"
    assert repair["repair_accept"] is None
    assert repair["parent_synthesis_retry_attempted"] is False
    assert repair["parent_synthesis_retry_accept"] is None
    assert "retried_parent_synthesis" not in artifact
    assert repair["before_validation"] == artifact["traceguard_validation"]
    assert repair["after_validation"] is None


def test_brownfield_seed_is_parseable_and_secret_safe() -> None:
    seed_path = Path("experiments/live-portability-brownfield.seed.yaml")
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    serialized = seed_path.read_text(encoding="utf-8")

    assert data["brownfield_context"]["project_type"] == "brownfield"
    assert "/Users/jaegyu.lee/Project/ouroboros-rlm-hermes" in serialized
    assert "/Users/jaegyu.lee/Project/ouroboros" in serialized
    for line in serialized.splitlines():
        normalized = line.strip().lower()
        assert not normalized.startswith(("api_key:", "glm_api_key:", "zai_api_key:"))
        assert not normalized.startswith(("authorization:", "bearer:"))
