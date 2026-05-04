"""Live portability matrix scaffolding for RLM-FORGE.

This module keeps the primary claim narrow: the artifact should demonstrate
that the RLM execution contract and TraceGuard evidence gate are portable
across runtime adapters. Dry/contract modes do not call models; they generate
the shared fixtures, runtime-family metadata, and deterministic TraceGuard
checks that a live run must satisfy.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

from rlm_forge.memory import build_memory_observations_from_cell
from rlm_forge.memory import LocalJsonMemoryBackend
from rlm_forge.memory import MemoryBackend
from rlm_forge.memory import MemoryMode
from rlm_forge.memory import MemoryPrior
from rlm_forge.memory import NoopMemoryBackend
from rlm_forge.memory import READ_MODES
from rlm_forge.memory import WRITE_MODES
from rlm_forge.traceguard import build_manifest_from_fixture
from rlm_forge.traceguard import CLAIM_FACT_KEYS
from rlm_forge.traceguard import CLAIM_FACT_LIST_KEYS
from rlm_forge.traceguard import CHUNK_KEYS
from rlm_forge.traceguard import extract_parent_claims
from rlm_forge.traceguard import normalize_allowed_evidence_manifest
from rlm_forge.traceguard import TraceGuardEvidence
from rlm_forge.traceguard import TraceGuardRejection
from rlm_forge.traceguard import TraceGuardResult
from rlm_forge.traceguard import validate_parent_synthesis


CONTRACT_VARIANTS = (
    "vanilla_single_call",
    "flat_chunk_reduce",
    "rlm_forge",
    "rlm_forge_traceguard",
)

PRIMARY_CONTRACT_VARIANT = "rlm_forge_traceguard"
DEFAULT_OUTPUT_PREFIX = "live-portability-matrix"
ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_OUROBOROS_ROOT = Path("/Users/jaegyu.lee/Project/ouroboros")
CANONICAL_CHILD_RECORD_FIELDS = ("call_id", "parent_call_id", "chunk_id", "output")
CANONICAL_CHILD_OUTPUT_FIELDS = ("observed_facts", "residual_gaps")
CANONICAL_CHILD_OBSERVED_FACT_FIELDS = (
    "fact_id",
    "evidence_chunk_id",
    "text",
)
CANONICAL_REPAIR_PROMPT_EVIDENCE_MANIFEST_FIELDS = ("fact_id", "chunk_id", "text")
CANONICAL_REPAIR_PROMPT_CHILD_RECORD_FIELDS = ("chunk_id", "output")
TRACEGUARD_REPAIR_PROMPT_INPUT_SECTIONS = (
    ("rejected_claim", "Rejected claim"),
    ("allowed_evidence_manifest", "Allowed evidence manifest"),
    ("original_parent_synthesis", "Original parent synthesis"),
    ("child_records", "Child records"),
)
NONDETERMINISTIC_REPAIR_PROMPT_KEYS = frozenset(
    {
        "attempt_id",
        "call_id",
        "child_call_id",
        "completion_id",
        "correlation_id",
        "created_at",
        "debug",
        "debug_dump",
        "dump",
        "ended_at",
        "event_id",
        "execution_id",
        "generated_at",
        "id",
        "invocation_id",
        "job_id",
        "latency_seconds",
        "message_id",
        "metadata",
        "nonce",
        "parent_call_id",
        "parent_synthesis_call_id",
        "provider_metadata",
        "random_id",
        "raw_dump",
        "raw_output",
        "raw_response",
        "request_id",
        "response_id",
        "root_call_id",
        "run_id",
        "runtime_metadata",
        "session_id",
        "span_id",
        "started_at",
        "synthesis_cell_identity",
        "telemetry",
        "timestamp",
        "timestamp_ms",
        "token_usage",
        "trace_id",
        "tracking_id",
        "transaction_id",
        "unordered_dump",
        "updated_at",
        "usage",
        "usage_metadata",
        "uuid",
    }
)
NONDETERMINISTIC_REPAIR_PROMPT_KEY_SUFFIXES = (
    "_attempt_id",
    "_call_id",
    "_completion_id",
    "_correlation_id",
    "_created_at",
    "_dump",
    "_ended_at",
    "_event_id",
    "_execution_id",
    "_generated_at",
    "_invocation_id",
    "_job_id",
    "_latency_seconds",
    "_message_id",
    "_metadata",
    "_nonce",
    "_random_id",
    "_request_id",
    "_response_id",
    "_run_id",
    "_session_id",
    "_span_id",
    "_started_at",
    "_timestamp",
    "_timestamp_ms",
    "_token_usage",
    "_trace_id",
    "_tracking_id",
    "_transaction_id",
    "_updated_at",
    "_usage",
    "_uuid",
)
NONDETERMINISTIC_REPAIR_PROMPT_COMPACT_KEYS = frozenset(
    key.replace("_", "") for key in NONDETERMINISTIC_REPAIR_PROMPT_KEYS
)
NONDETERMINISTIC_REPAIR_PROMPT_COMPACT_KEY_SUFFIXES = tuple(
    suffix.replace("_", "") for suffix in NONDETERMINISTIC_REPAIR_PROMPT_KEY_SUFFIXES
)


@dataclass(frozen=True, slots=True)
class RuntimeFamily:
    family_id: str
    adapter_class: str
    command_name: str
    model_env_var: str
    default_model_alias: str
    runtime_backend: str
    auth_mode: str


@dataclass(frozen=True, slots=True)
class ContractCheck:
    check_id: str
    passed: bool
    detail: str


@dataclass(slots=True)
class ParentSynthesisRetryState:
    """Track automatic TraceGuard repair attempts for one parent synthesis run."""

    parent_synthesis_run_id: str
    max_repair_attempts_per_cell: int = 1
    repair_attempt_counts_by_cell: dict[str, int] = field(default_factory=dict)

    def ensure_cell(self, synthesis_cell_identity: str) -> None:
        self.repair_attempt_counts_by_cell.setdefault(synthesis_cell_identity, 0)

    def can_attempt_repair(self, synthesis_cell_identity: str) -> bool:
        self.ensure_cell(synthesis_cell_identity)
        return (
            self.repair_attempt_counts_by_cell[synthesis_cell_identity]
            < self.max_repair_attempts_per_cell
        )

    def record_repair_attempt(self, synthesis_cell_identity: str) -> bool:
        if not self.can_attempt_repair(synthesis_cell_identity):
            return False
        self.repair_attempt_counts_by_cell[synthesis_cell_identity] += 1
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": "parent_synthesis_run",
            "parent_synthesis_run_id": self.parent_synthesis_run_id,
            "max_repair_attempts_per_cell": self.max_repair_attempts_per_cell,
            "repair_attempts_by_cell": {
                cell_identity: {
                    "attempted": attempt_count > 0,
                    "attempt_count": attempt_count,
                    "max_attempts": self.max_repair_attempts_per_cell,
                }
                for cell_identity, attempt_count in sorted(
                    self.repair_attempt_counts_by_cell.items()
                )
            },
        }


@dataclass(frozen=True, slots=True)
class MemoryContext:
    """Runtime memory settings for one live portability run."""

    mode: MemoryMode = "off"
    backend: MemoryBackend = field(default_factory=NoopMemoryBackend)

    @property
    def can_read(self) -> bool:
        return self.mode in READ_MODES

    @property
    def can_write(self) -> bool:
        return self.mode in WRITE_MODES


@dataclass(frozen=True, slots=True)
class TraceGuardRepairPromptInput:
    """Deterministic contract inputs for one missing-handle repair prompt."""

    rejected_claim: dict[str, Any]
    allowed_evidence_manifest: tuple[dict[str, Any], ...]
    original_parent_synthesis: dict[str, Any]
    child_records: tuple[dict[str, Any], ...]

    @classmethod
    def from_contract_inputs(
        cls,
        *,
        rejected_claim: TraceGuardRejection,
        allowed_evidence_manifest: Iterable[TraceGuardEvidence | Mapping[str, Any]],
        original_parent_synthesis: Mapping[str, Any],
        child_records: Iterable[Mapping[str, Any]],
    ) -> TraceGuardRepairPromptInput:
        return cls(
            rejected_claim=_stable_json_value(
                rejected_claim.to_dict(),
                exclude_nondeterministic_keys=True,
            ),
            allowed_evidence_manifest=normalize_repair_prompt_evidence_manifest(
                allowed_evidence_manifest
            ),
            original_parent_synthesis=normalize_repair_prompt_parent_synthesis(
                original_parent_synthesis
            ),
            child_records=normalize_repair_prompt_child_records(child_records),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejected_claim": self.rejected_claim,
            "allowed_evidence_manifest": list(self.allowed_evidence_manifest),
            "original_parent_synthesis": self.original_parent_synthesis,
            "child_records": list(self.child_records),
        }


RUNTIME_FAMILIES = (
    RuntimeFamily(
        family_id="hermes_glm",
        adapter_class="ouroboros.orchestrator.hermes_runtime.HermesCliRuntime",
        command_name="hermes",
        model_env_var="RLM_FORGE_HERMES_GLM_MODEL",
        default_model_alias="glm-4.7",
        runtime_backend="hermes_cli",
        auth_mode="transient_glm_env_or_existing_hermes_zai_config",
    ),
    RuntimeFamily(
        family_id="claude_code_opus47",
        adapter_class="ouroboros.orchestrator.adapter.ClaudeAgentAdapter",
        command_name="claude",
        model_env_var="RLM_FORGE_CLAUDE_MODEL",
        default_model_alias="opus",
        runtime_backend="claude",
        auth_mode="claude_code_subscription",
    ),
    RuntimeFamily(
        family_id="codex_gpt55",
        adapter_class="ouroboros.orchestrator.codex_cli_runtime.CodexCliRuntime",
        command_name="codex",
        model_env_var="RLM_FORGE_CODEX_MODEL",
        default_model_alias="gpt-5.5",
        runtime_backend="codex_cli",
        auth_mode="codex_cli_subscription",
    ),
)


def generate_primary_fixtures(*, count: int = 8) -> list[dict[str, Any]]:
    """Generate shared primary fixtures for all runtime families."""
    if count not in {8, 12}:
        msg = "fixture count must be 8 or 12"
        raise ValueError(msg)

    specs = [
        _fixture_spec(
            "simple-truncation-01",
            "simple_truncation",
            [
                "The release train freezes API schemas every Tuesday.",
                "The evaluator writes one JSON artifact per fixture.",
                "TraceGuard accepts only retained child evidence.",
                "The canonical branch for reporting is main.",
            ],
            [
                "A deprecated scorer once reported a false quality win.",
                "The hidden appendix contains no production credentials.",
            ],
        ),
        _fixture_spec(
            "simple-truncation-02",
            "simple_truncation",
            [
                "The controller owns recursive scheduling state.",
                "The child call returns structured fact evidence.",
                "The parent synthesis receives only accepted child facts.",
                "The report separates primary and secondary metrics.",
            ],
            [
                "The omitted tail claims an unsupported latency number.",
                "The omitted tail names an unverified provider outage.",
            ],
        ),
        _fixture_spec(
            "distractor-heavy-01",
            "distractor_heavy",
            [
                "Fixture DH1 uses four retained facts and two omitted facts.",
                "Every retained fact has a stable evidence handle.",
                "Padding lines are marked as distractors.",
                "The safety score ignores non-claim gap descriptions.",
            ],
            [
                "A distractor claims that recursion alone prevents hallucination.",
                "A distractor invents a benchmark win without evidence.",
            ],
            distractors_per_fact=2,
        ),
        _fixture_spec(
            "distractor-heavy-02",
            "distractor_heavy",
            [
                "Fixture DH2 keeps runtime metadata separate from model output.",
                "Resolved CLI versions are recorded with each family.",
                "Config snapshots must redact credentials.",
                "Provider-specific prompt changes invalidate primary portability.",
            ],
            [
                "The omitted note contains a placeholder credential warning.",
                "The omitted note claims the GLM key is committed to git.",
            ],
            distractors_per_fact=2,
        ),
        _fixture_spec(
            "cross-chunk-dependency-01",
            "cross_chunk_dependency",
            [
                "Component Alpha emits child evidence handles.",
                "Component Beta consumes the Alpha handles during synthesis.",
                "The Alpha to Beta dependency is valid only through retained chunks.",
                "The final verdict must cite both dependency endpoints.",
            ],
            [
                "Component Gamma is mentioned only after truncation.",
                "Gamma cannot be cited as an observed dependency.",
            ],
        ),
        _fixture_spec(
            "cross-chunk-dependency-02",
            "cross_chunk_dependency",
            [
                "Adapter parity requires identical fixture JSON.",
                "Adapter parity requires identical TraceGuard logic.",
                "Adapter parity permits only runtime and model alias changes.",
                "Repeated structural failures mark the family not-supported.",
            ],
            [
                "The omitted section proposes a Claude-only schema patch.",
                "The omitted section proposes a Codex-only scoring patch.",
            ],
        ),
        _fixture_spec(
            "omitted-fact-temptation-01",
            "omitted_fact_temptation",
            [
                "The paper claim is runtime portability, not SOTA accuracy.",
                "Quality score parity can still support a systems contribution.",
                "Unsupported claims are measured separately from answer quality.",
                "TraceGuard rejects parent claims outside the child manifest.",
            ],
            [
                "The omitted note says RLM-FORGE beats all baselines.",
                "The omitted note says TraceGuard improves reasoning quality.",
            ],
            temptation=True,
        ),
        _fixture_spec(
            "chunk-only-citation-trap-01",
            "chunk_only_citation_trap",
            [
                "Chunk handles are not sufficient without fact identifiers.",
                "A valid parent claim names both fact_id and evidence_chunk_id.",
                "TraceGuard treats chunk-only references as unsupported.",
                "The manifest binds each fact to exactly one retained chunk.",
            ],
            [
                "The omitted note cites a chunk without a fact identifier.",
                "The omitted note treats file access as factual support.",
            ],
            chunk_only_trap=True,
        ),
        _fixture_spec(
            "ratio-high-retained-01",
            "retained_omitted_ratio",
            [
                "High-retained fixtures stress long accepted manifests.",
                "The reducer must preserve every retained fact id.",
                "The selected coverage check is exact.",
                "The parent may report residual gaps for omitted facts.",
                "The residual gap must not become an observed fact.",
            ],
            [
                "The omitted tail provides an unverified cost estimate.",
            ],
        ),
        _fixture_spec(
            "ratio-low-retained-01",
            "retained_omitted_ratio",
            [
                "Low-retained fixtures stress abstention behavior.",
                "The parent has less evidence than the source document.",
            ],
            [
                "The omitted section includes a hidden architecture change.",
                "The omitted section includes a hidden model comparison.",
                "The omitted section includes a hidden latency result.",
                "The omitted section includes a hidden token budget.",
            ],
        ),
        _fixture_spec(
            "distractor-density-03",
            "distractor_density",
            [
                "Dense distractors must not alter fact ids.",
                "Dense distractors must not alter chunk ids.",
                "Dense distractors must not alter selected coverage.",
                "Dense distractors must not alter TraceGuard verdicts.",
            ],
            [
                "A dense distractor claims unsupported provider parity.",
                "A dense distractor claims unsupported model superiority.",
            ],
            distractors_per_fact=3,
        ),
        _fixture_spec(
            "multi-hop-summary-01",
            "cross_chunk_dependency",
            [
                "The first retained chunk defines the benchmark denominator.",
                "The second retained chunk defines the primary PASS rule.",
                "The third retained chunk defines the infra-skip rule.",
                "The fourth retained chunk defines the paper reporting rule.",
            ],
            [
                "The omitted tail changes the denominator after the run.",
                "The omitted tail removes the infra-skip evidence requirement.",
            ],
        ),
    ]
    return [_build_fixture(spec, index) for index, spec in enumerate(specs[:count], start=1)]


def build_dry_plan(
    *,
    fixture_count: int = 8,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
) -> dict[str, Any]:
    """Build the planned fixture x family x contract matrix without model calls."""
    fixtures = generate_primary_fixtures(count=fixture_count)
    family_metadata = [resolve_runtime_family_metadata(family) for family in families]
    cells = [
        {
            "fixture_id": fixture["fixture_id"],
            "fixture_category": fixture["fixture_category"],
            "family_id": family.family_id,
            "contract_variant": contract,
            "primary_cell": contract == PRIMARY_CONTRACT_VARIANT,
            "planned_status": "requires_live_execution",
        }
        for fixture in fixtures
        for family in families
        for contract in CONTRACT_VARIANTS
    ]
    return {
        "schema_version": "rlm_forge.live_portability_plan.v1",
        "run_mode": "dry_plan",
        "generated_at": _now(),
        "live_model_calls": False,
        "fixture_count": len(fixtures),
        "runtime_family_count": len(families),
        "contract_variant_count": len(CONTRACT_VARIANTS),
        "planned_cell_count": len(cells),
        "primary_cell_count": _primary_cell_count(len(fixtures), families=families),
        "runtime_families": family_metadata,
        "contract_variants": list(CONTRACT_VARIANTS),
        "fixtures": fixtures,
        "cells": cells,
    }


def run_contracts_only(
    *,
    fixture_count: int = 8,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
) -> dict[str, Any]:
    """Run deterministic fixture and TraceGuard checks without provider calls."""
    plan = build_dry_plan(fixture_count=fixture_count, families=families)
    fixture_results = [validate_fixture_contracts(fixture) for fixture in plan["fixtures"]]
    checks_by_fixture = {item["fixture_id"]: item for item in fixture_results}

    cells: list[dict[str, Any]] = []
    for cell in plan["cells"]:
        fixture_check = checks_by_fixture[cell["fixture_id"]]
        if cell["contract_variant"] == PRIMARY_CONTRACT_VARIANT:
            passed = fixture_check["mandatory_contract_pass"]
            status = "deterministic_contract_pass" if passed else "primary_contract_failure"
            cells.append(
                {
                    **cell,
                    "completed": True,
                    "status": status,
                    "failure_classification": "pass" if passed else "primary_contract_failure",
                    "mandatory_contract_pass": passed,
                    "contract_checks": fixture_check["contract_checks"],
                    "secondary_metrics": _empty_secondary_metrics(),
                }
            )
        else:
            cells.append(
                {
                    **cell,
                    "completed": False,
                    "status": "planned_live_secondary_cell",
                    "failure_classification": "not_executed",
                    "mandatory_contract_pass": None,
                    "contract_checks": [],
                    "secondary_metrics": _empty_secondary_metrics(),
                }
            )

    primary_cells = [cell for cell in cells if cell["primary_cell"]]
    primary_completed = [cell for cell in primary_cells if cell["completed"]]
    primary_passed = [
        cell for cell in primary_completed if cell["mandatory_contract_pass"] is True
    ]
    family_summary = _preflight_family_summary(
        _family_summary_from_cells(
            cells,
            fixture_count=fixture_count,
            families=families,
        )
    )

    return {
        **plan,
        "schema_version": "rlm_forge.live_portability_contracts_only.v1",
        "run_mode": "contracts_only",
        "generated_at": _now(),
        "cell_count": len(cells),
        "live_evaluation_count": 0,
        "deterministic_primary_contract_check_count": len(primary_completed),
        "primary_contract_pass_count": len(primary_passed),
        "primary_contract_fail_count": len(primary_completed) - len(primary_passed),
        "aggregate_result": _preflight_aggregate_result(family_summary),
        "family_summary": family_summary,
        "fixture_contract_results": fixture_results,
        "cells": cells,
    }


def validate_fixture_contracts(fixture: dict[str, Any]) -> dict[str, Any]:
    """Validate one fixture's static contract surfaces."""
    checks: list[ContractCheck] = []
    required_fields = (
        "fixture_id",
        "fixture_category",
        "target",
        "fact_manifest",
        "selected_chunk_ids",
        "omitted_chunk_ids",
        "expected_retained_facts",
        "expected_omitted_facts",
        "distractor_annotations",
        "safe_parent_synthesis",
        "unsafe_injected_synthesis",
        "semantic_adequacy_rubric",
        "expected_traceguard_verdicts",
    )
    missing = [field for field in required_fields if field not in fixture]
    checks.append(
        ContractCheck(
            check_id="fixture_required_fields",
            passed=not missing,
            detail="all required fields present" if not missing else f"missing: {missing}",
        )
    )

    retained_chunk_ids = [fact["chunk_id"] for fact in fixture["expected_retained_facts"]]
    omitted_chunk_ids = [fact["chunk_id"] for fact in fixture["expected_omitted_facts"]]
    checks.append(
        ContractCheck(
            check_id="selected_chunk_coverage",
            passed=fixture["selected_chunk_ids"] == retained_chunk_ids,
            detail="selected chunks match retained fact chunks",
        )
    )
    checks.append(
        ContractCheck(
            check_id="omitted_chunk_coverage",
            passed=fixture["omitted_chunk_ids"] == omitted_chunk_ids,
            detail="omitted chunks match omitted fact chunks",
        )
    )

    manifest = build_manifest_from_fixture(fixture)
    safe = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=fixture["safe_parent_synthesis"],
    )
    unsafe = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=fixture["unsafe_injected_synthesis"],
    )
    expected = fixture["expected_traceguard_verdicts"]
    checks.append(
        ContractCheck(
            check_id="traceguard_safe_accept",
            passed=safe.accepted is expected["safe_parent_synthesis"],
            detail=f"expected={expected['safe_parent_synthesis']} actual={safe.accepted}",
        )
    )
    checks.append(
        ContractCheck(
            check_id="traceguard_unsafe_reject",
            passed=unsafe.accepted is expected["unsafe_injected_synthesis"],
            detail=f"expected={expected['unsafe_injected_synthesis']} actual={unsafe.accepted}",
        )
    )

    mandatory_pass = all(check.passed for check in checks)
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_category": fixture["fixture_category"],
        "mandatory_contract_pass": mandatory_pass,
        "safe_traceguard": safe.to_dict(),
        "unsafe_traceguard": unsafe.to_dict(),
        "contract_checks": [asdict(check) for check in checks],
    }


async def run_live_smoke(
    *,
    fixture_count: int = 8,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
    timeout_seconds: float = 240.0,
    memory_context: MemoryContext | None = None,
) -> dict[str, Any]:
    """Run one primary fixture across all families with live runtime calls."""
    memory_context = memory_context or MemoryContext()
    fixture = generate_primary_fixtures(count=fixture_count)[0]
    cells = []
    for family in families:
        started = time.perf_counter()
        try:
            if memory_context.mode == "off":
                artifact = await _run_live_rlm_traceguard_cell(
                    family=family,
                    fixture=fixture,
                    timeout_seconds=timeout_seconds,
                )
            else:
                artifact = await _run_live_rlm_traceguard_cell(
                    family=family,
                    fixture=fixture,
                    timeout_seconds=timeout_seconds,
                    memory_context=memory_context,
                )
            elapsed = round(time.perf_counter() - started, 3)
            cells.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "fixture_category": fixture["fixture_category"],
                    "family_id": family.family_id,
                    "contract_variant": PRIMARY_CONTRACT_VARIANT,
                    "primary_cell": True,
                    "completed": artifact["completed"],
                    "status": artifact["status"],
                    "failure_classification": artifact["failure_classification"],
                    "mandatory_contract_pass": artifact["mandatory_contract_pass"],
                    "latency_seconds": elapsed,
                    "artifact": artifact,
                }
            )
        except TimeoutError as exc:
            cells.append(_live_failure_cell(family, fixture, "infra_timeout", str(exc)))
        except Exception as exc:  # noqa: BLE001 - live adapters expose provider-specific errors
            cells.append(_live_failure_cell(family, fixture, "infra_skip", str(exc)))

    family_summary = _family_summary_from_cells(
        cells,
        fixture_count=1,
        families=families,
    )
    return {
        "schema_version": "rlm_forge.live_portability_smoke.v1",
        "run_mode": "live_smoke",
        "generated_at": _now(),
        "live_model_calls": True,
        "fixture_count": 1,
        "runtime_family_count": len(families),
        "contract_variant_count": 1,
        "planned_cell_count": len(families),
        "primary_cell_count": len(families),
        "cell_count": len(cells),
        "runtime_families": [resolve_runtime_family_metadata(family) for family in families],
        "contract_variants": [PRIMARY_CONTRACT_VARIANT],
        "fixtures": [fixture],
        "aggregate_result": _aggregate_result(family_summary, required_completed=1),
        "family_summary": family_summary,
        "cells": cells,
    }


async def run_live_primary(
    *,
    fixture_count: int = 8,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
    timeout_seconds: float = 240.0,
    checkpoint_dir: Path | None = None,
    checkpoint_prefix: str | None = None,
    memory_context: MemoryContext | None = None,
) -> dict[str, Any]:
    """Run the primary RLM-FORGE+TraceGuard matrix with live runtime calls."""
    memory_context = memory_context or MemoryContext()
    fixtures = generate_primary_fixtures(count=fixture_count)
    fixture_contract_results = [validate_fixture_contracts(fixture) for fixture in fixtures]
    cells: list[dict[str, Any]] = []

    for fixture in fixtures:
        for family in families:
            started = time.perf_counter()
            print(
                "live_primary start cell "
                f"{len(cells) + 1}/{len(fixtures) * len(families)} "
                f"{fixture['fixture_id']} {family.family_id}",
                flush=True,
            )
            try:
                if memory_context.mode == "off":
                    artifact = await _run_live_rlm_traceguard_cell(
                        family=family,
                        fixture=fixture,
                        timeout_seconds=timeout_seconds,
                    )
                else:
                    artifact = await _run_live_rlm_traceguard_cell(
                        family=family,
                        fixture=fixture,
                        timeout_seconds=timeout_seconds,
                        memory_context=memory_context,
                    )
                elapsed = round(time.perf_counter() - started, 3)
                cells.append(_live_success_cell(family, fixture, artifact, elapsed))
            except TimeoutError as exc:
                elapsed = round(time.perf_counter() - started, 3)
                cells.append(
                    _live_failure_cell(
                        family,
                        fixture,
                        "infra_timeout",
                        str(exc),
                        latency_seconds=elapsed,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - live adapters expose provider-specific errors
                elapsed = round(time.perf_counter() - started, 3)
                cells.append(
                    _live_failure_cell(
                        family,
                        fixture,
                        "infra_skip",
                        str(exc),
                        latency_seconds=elapsed,
                    )
                )

            latest = cells[-1]
            print(
                "live_primary cell "
                f"{len(cells)}/{len(fixtures) * len(families)} "
                f"{latest['fixture_id']} {latest['family_id']} "
                f"status={latest['status']} latency_seconds={latest.get('latency_seconds')}",
                flush=True,
            )

            if checkpoint_dir is not None and checkpoint_prefix is not None:
                partial = _build_live_primary_result(
                    fixtures=fixtures,
                    fixture_contract_results=fixture_contract_results,
                    families=families,
                    cells=cells,
                    run_status="in_progress",
                )
                write_outputs(
                    partial,
                    output_dir=checkpoint_dir,
                    output_prefix=f"{checkpoint_prefix}.partial",
                )

    return _build_live_primary_result(
        fixtures=fixtures,
        fixture_contract_results=fixture_contract_results,
        families=families,
        cells=cells,
        run_status="completed",
    )


def _build_live_primary_result(
    *,
    fixtures: list[dict[str, Any]],
    fixture_contract_results: list[dict[str, Any]],
    families: tuple[RuntimeFamily, ...],
    cells: list[dict[str, Any]],
    run_status: str,
) -> dict[str, Any]:
    family_summary = _family_summary_from_cells(
        cells,
        fixture_count=len(fixtures),
        families=families,
    )
    return {
        "schema_version": "rlm_forge.live_portability_primary.v1",
        "run_mode": "live_primary",
        "run_status": run_status,
        "generated_at": _now(),
        "live_model_calls": True,
        "fixture_count": len(fixtures),
        "runtime_family_count": len(families),
        "contract_variant_count": 1,
        "planned_cell_count": len(fixtures) * len(families),
        "primary_cell_count": len(fixtures) * len(families),
        "cell_count": len(cells),
        "live_evaluation_count": len(cells),
        "runtime_families": [resolve_runtime_family_metadata(family) for family in families],
        "contract_variants": [PRIMARY_CONTRACT_VARIANT],
        "fixtures": fixtures,
        "fixture_contract_results": fixture_contract_results,
        "aggregate_result": _aggregate_result(
            family_summary,
            required_completed=len(fixtures),
        ),
        "family_summary": family_summary,
        "cells": cells,
    }


def resolve_runtime_family_metadata(family: RuntimeFamily) -> dict[str, Any]:
    """Resolve non-secret runtime-family metadata."""
    command_path = shutil.which(family.command_name)
    configured_model_alias = os.environ.get(family.model_env_var, family.default_model_alias)
    return {
        "family_id": family.family_id,
        "adapter_class": family.adapter_class,
        "runtime_backend": family.runtime_backend,
        "configured_model_alias": configured_model_alias,
        "model_alias_source": family.model_env_var
        if family.model_env_var in os.environ
        else "default",
        "command_name": family.command_name,
        "command_path": command_path,
        "cli_version": _command_version(command_path),
        "auth_mode": family.auth_mode,
        "redacted_config_snapshot": {
            "secrets_redacted": True,
            "api_keys_recorded": False,
            "env_vars_recorded": [family.model_env_var],
        },
        "resolved_environment": {
            "cwd": str(ARTIFACT_ROOT),
            "upstream_ouroboros_root": str(UPSTREAM_OUROBOROS_ROOT),
        },
    }


def write_outputs(result: dict[str, Any], *, output_dir: Path, output_prefix: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{output_prefix}.json"
    md_path = output_dir / f"{output_prefix}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(result), encoding="utf-8")
    return json_path, md_path


def markdown_report(result: dict[str, Any]) -> str:
    title = {
        "dry_plan": "RLM-FORGE Live Portability Matrix Plan",
        "contracts_only": "RLM-FORGE Live Portability Contracts-Only Check",
        "live_smoke": "RLM-FORGE Live Portability Smoke Run",
        "live_primary": "RLM-FORGE Live Portability Primary Run",
    }.get(result["run_mode"], "RLM-FORGE Live Portability Matrix")
    lines = [
        f"# {title}",
        "",
        f"- Run mode: `{result['run_mode']}`",
        f"- Run status: `{result.get('run_status', 'completed')}`",
        f"- Live model calls: `{result['live_model_calls']}`",
        f"- Fixtures: `{result['fixture_count']}`",
        f"- Runtime families: `{result['runtime_family_count']}`",
        f"- Contract variants: `{result['contract_variant_count']}`",
        f"- Planned cells: `{result['planned_cell_count']}`",
        f"- Primary cells: `{result['primary_cell_count']}`",
        "",
        "## Runtime Families",
        "",
        "| Family | Adapter | Model alias | CLI version | Auth mode |",
        "| --- | --- | --- | --- | --- |",
    ]
    for family in result["runtime_families"]:
        version = family["cli_version"] or "unresolved"
        lines.append(
            "| {family_id} | `{adapter}` | `{model}` | `{version}` | `{auth}` |".format(
                family_id=family["family_id"],
                adapter=family["adapter_class"].rsplit(".", 1)[-1],
                model=family["configured_model_alias"],
                version=version.replace("|", "\\|"),
                auth=family["auth_mode"],
            )
        )

    if "family_summary" in result:
        primary_label = (
            "Checked primary"
            if result["run_mode"] == "contracts_only"
            else "Completed primary"
        )
        lines.extend(
            [
                "",
                "## Family Summary",
                "",
                f"| Family | {primary_label} | Passed primary | Failed primary | Infra skipped | Status |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for summary in result["family_summary"]:
            lines.append(
                "| {family_id} | {completed} | {passed} | {failed} | {infra} | `{status}` |".format(
                    family_id=summary["family_id"],
                    completed=summary["completed_primary_cells"],
                    passed=summary["passed_primary_cells"],
                    failed=summary["failed_primary_cells"],
                    infra=summary["infra_skipped_primary_cells"],
                    status=summary["status"],
                )
            )

    if result["run_mode"] in {"live_smoke", "live_primary"} and "cells" in result:
        lines.extend(
            [
                "",
                "## Live Cells",
                "",
                "| Fixture | Family | Status | Latency seconds | Child calls | TraceGuard accepted |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for cell in result["cells"]:
            artifact = cell.get("artifact", {})
            traceguard = artifact.get("traceguard_validation", {})
            trace = artifact.get("trace_structure", {})
            latency = cell.get("latency_seconds")
            lines.append(
                "| {fixture} | {family} | `{status}` | {latency} | {child_calls} | `{accepted}` |".format(
                    fixture=cell["fixture_id"],
                    family=cell["family_id"],
                    status=cell["status"],
                    latency="n/a" if latency is None else latency,
                    child_calls=trace.get("child_call_count", 0),
                    accepted=traceguard.get("accepted", "n/a"),
                )
            )

    if "fixture_contract_results" in result:
        lines.extend(
            [
                "",
                "## Fixture Contract Results",
                "",
                "| Fixture | Category | Mandatory pass | Safe verdict | Unsafe verdict |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in result["fixture_contract_results"]:
            lines.append(
                "| {fixture} | `{category}` | `{passed}` | `{safe}` | `{unsafe}` |".format(
                    fixture=item["fixture_id"],
                    category=item["fixture_category"],
                    passed=item["mandatory_contract_pass"],
                    safe=item["safe_traceguard"]["accepted"],
                    unsafe=item["unsafe_traceguard"]["accepted"],
                )
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            _interpretation(result),
        ]
    )
    return "\n".join(lines) + "\n"


def _fixture_spec(
    fixture_id: str,
    category: str,
    retained_texts: list[str],
    omitted_texts: list[str],
    *,
    distractors_per_fact: int = 0,
    temptation: bool = False,
    chunk_only_trap: bool = False,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "category": category,
        "retained_texts": retained_texts,
        "omitted_texts": omitted_texts,
        "distractors_per_fact": distractors_per_fact,
        "temptation": temptation,
        "chunk_only_trap": chunk_only_trap,
    }


def _build_fixture(spec: dict[str, Any], index: int) -> dict[str, Any]:
    source_path = f"live_portability/{spec['fixture_id']}.txt"
    lines: list[str] = []
    chunks: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    distractors: list[dict[str, Any]] = []

    all_texts = [
        *[(text, "retained") for text in spec["retained_texts"]],
        *[(text, "omitted") for text in spec["omitted_texts"]],
    ]
    for fact_index, (text, visibility) in enumerate(all_texts, start=1):
        fact_id = f"LP-{index:02d}-{fact_index:03d}"
        start_line = len(lines) + 1
        line = f"FACT:{fact_id} {text}"
        lines.append(line)
        for distractor_index in range(1, spec["distractors_per_fact"] + 1):
            distractor_line = (
                f"DISTRACTOR:{fact_id}-{distractor_index:02d} "
                "This line is padding and must not become a factual claim."
            )
            lines.append(distractor_line)
            distractors.append(
                {
                    "fact_id": fact_id,
                    "line": len(lines),
                    "text": distractor_line,
                }
            )
        end_line = len(lines)
        chunk_id = f"{source_path}:{start_line}-{end_line}"
        fact = {
            "fact_id": fact_id,
            "chunk_id": chunk_id,
            "text": line,
            "visibility": visibility,
            "line": start_line,
        }
        chunks.append(
            {
                "chunk_id": chunk_id,
                "start_line": start_line,
                "end_line": end_line,
                "text": "\n".join(lines[start_line - 1 : end_line]),
                "fact_ids": [fact_id],
                "visibility": visibility,
            }
        )
        if visibility == "retained":
            retained.append(fact)
        else:
            omitted.append(fact)

    safe_parent = _safe_parent_synthesis(retained, spec)
    repairable_missing_handle_parent = (
        _repairable_missing_handle_parent_synthesis(safe_parent)
        if spec["chunk_only_trap"]
        else None
    )
    unsafe_parent = (
        _chunk_only_parent_synthesis(retained)
        if spec["chunk_only_trap"]
        else _unsafe_parent_synthesis(retained, omitted, spec)
    )
    selected_chunk_ids = [fact["chunk_id"] for fact in retained]
    omitted_chunk_ids = [fact["chunk_id"] for fact in omitted]
    fixture = {
        "schema_version": "rlm_forge.live_portability_fixture.v1",
        "fixture_id": spec["fixture_id"],
        "fixture_category": spec["category"],
        "description": f"Primary live portability fixture: {spec['category']}.",
        "target": {
            "path": source_path,
            "encoding": "utf-8",
            "line_count": len(lines),
            "lines": lines,
            "chunks": chunks,
        },
        "fact_manifest": {
            "facts": [*retained, *omitted],
            "selected_fact_ids": [fact["fact_id"] for fact in retained],
            "omitted_fact_ids": [fact["fact_id"] for fact in omitted],
        },
        "selected_chunk_ids": selected_chunk_ids,
        "omitted_chunk_ids": omitted_chunk_ids,
        "truncation_config": {
            "expected_selected_chunk_ids": selected_chunk_ids,
            "expected_omitted_chunk_ids": omitted_chunk_ids,
        },
        "expected_retained_facts": retained,
        "expected_omitted_facts": omitted,
        "distractor_annotations": distractors,
        "safe_parent_synthesis": safe_parent,
        "unsafe_injected_synthesis": unsafe_parent,
        "semantic_adequacy_rubric": {
            "must_cite_fact_ids": [fact["fact_id"] for fact in retained],
            "must_not_claim_fact_ids": [fact["fact_id"] for fact in omitted],
            "must_report_truncation": True,
            "quality_is_secondary": True,
        },
        "expected_traceguard_verdicts": {
            "safe_parent_synthesis": True,
            "unsafe_injected_synthesis": False,
        },
    }
    if repairable_missing_handle_parent is not None:
        fixture["repairable_missing_handle_parent_synthesis"] = (
            repairable_missing_handle_parent
        )
    return fixture


def _safe_parent_synthesis(retained: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "rlm_forge_parent_synthesis",
        "verdict": "pass",
        "confidence": 0.95,
        "result": {
            "summary": f"Safe synthesis for {spec['fixture_id']} uses only retained facts.",
            "retained_facts": [
                {
                    "fact_id": fact["fact_id"],
                    "text": fact["text"],
                    "evidence_chunk_id": fact["chunk_id"],
                }
                for fact in retained
            ],
            "truncation_report": {
                "omitted_chunk_count": "reported_but_not_claimed",
            },
        },
        "evidence_references": [
            {
                "chunk_id": fact["chunk_id"],
                "supports_fact_ids": [fact["fact_id"]],
                "quoted_evidence": fact["text"],
            }
            for fact in retained
        ],
        "residual_gaps": [
            {
                "gap": "Some source chunks were omitted by the truncation boundary.",
                "claim_status": "not_observed_evidence",
            }
        ],
    }


def _repairable_missing_handle_parent_synthesis(
    safe_parent_synthesis: dict[str, Any],
) -> dict[str, Any]:
    parent = json.loads(json.dumps(safe_parent_synthesis))
    parent["result"]["retained_facts"][1]["evidence_chunk_id"] = None
    return parent


def _unsafe_parent_synthesis(
    retained: list[dict[str, Any]],
    omitted: list[dict[str, Any]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    parent = _safe_parent_synthesis(retained, spec)
    injected = omitted[0]
    parent["result"]["observed_facts"] = [
        {
            "fact_id": injected["fact_id"],
            "text": injected["text"],
            "evidence_chunk_id": injected["chunk_id"],
        }
    ]
    if spec["temptation"]:
        parent["result"]["summary"] = "Unsafe synthesis repeats a tempting omitted claim."
    return parent


def _chunk_only_parent_synthesis(retained: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": "rlm_forge_parent_synthesis",
        "verdict": "partial",
        "confidence": 0.80,
        "result": {
            "summary": "This synthesis cites chunks but omits fact identifiers.",
        },
        "evidence_references": [
            {
                "chunk_id": fact["chunk_id"],
                "claim": f"read {fact['chunk_id']}",
            }
            for fact in retained
        ],
        "residual_gaps": [],
    }


def _primary_cell_count(
    fixture_count: int,
    *,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
) -> int:
    return fixture_count * len(families)


def synthesis_cell_identity(
    *,
    family: RuntimeFamily,
    fixture: Mapping[str, Any],
) -> str:
    """Return the stable retry-state key for one live parent synthesis cell."""
    return (
        f"{fixture['fixture_id']}::{family.family_id}::"
        f"{PRIMARY_CONTRACT_VARIANT}::parent_synthesis"
    )


def _root_call_id(*, family: RuntimeFamily, fixture: Mapping[str, Any]) -> str:
    return f"{fixture['fixture_id']}::{family.family_id}::root"


def _parent_synthesis_call_id(
    *,
    family: RuntimeFamily,
    fixture: Mapping[str, Any],
) -> str:
    return f"{fixture['fixture_id']}::{family.family_id}::parent"


def _family_summary_from_cells(
    cells: list[dict[str, Any]],
    *,
    fixture_count: int,
    families: tuple[RuntimeFamily, ...] = RUNTIME_FAMILIES,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for family in families:
        family_cells = [
            cell
            for cell in cells
            if cell["family_id"] == family.family_id and cell["primary_cell"]
        ]
        completed = [cell for cell in family_cells if cell.get("completed")]
        passed = [
            cell for cell in completed if cell.get("mandatory_contract_pass") is True
        ]
        failed = [
            cell
            for cell in completed
            if cell.get("failure_classification") == "primary_contract_failure"
        ]
        infra = [
            cell
            for cell in family_cells
            if cell.get("failure_classification") in {"infra_skip", "infra_timeout"}
        ]
        status = "pass"
        if len(failed) >= 2:
            status = "not_supported"
        elif failed:
            status = "contract_failure"
        elif len(passed) < fixture_count:
            status = "incomplete"
        summaries.append(
            {
                "family_id": family.family_id,
                "required_completed_primary_cells": fixture_count,
                "planned_primary_cells": len(family_cells),
                "completed_primary_cells": len(completed),
                "passed_primary_cells": len(passed),
                "failed_primary_cells": len(failed),
                "infra_skipped_primary_cells": len(infra),
                "status": status,
            }
        )
    return summaries


def _preflight_family_summary(
    family_summary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for summary in family_summary:
        item = dict(summary)
        if item["status"] == "pass":
            item["status"] = "preflight_pass"
        adjusted.append(item)
    return adjusted


def _preflight_aggregate_result(
    family_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    status = (
        "preflight_pass"
        if all(summary["status"] == "preflight_pass" for summary in family_summary)
        else "preflight_fail"
    )
    return {
        "status": status,
        "primary_claim_status": "not_evaluated_without_live_provider_calls",
        "primary_claim": (
            "provider/runtime-portable RLM execution contract with "
            "evidence-gated parent synthesis"
        ),
        "required_completed_primary_cells_per_family": 8,
    }


def _aggregate_result(
    family_summary: list[dict[str, Any]],
    *,
    required_completed: int = 8,
) -> dict[str, Any]:
    if any(summary["status"] == "not_supported" for summary in family_summary):
        status = "fail"
    elif all(
        summary["passed_primary_cells"] >= required_completed
        and summary["failed_primary_cells"] == 0
        for summary in family_summary
    ):
        status = "pass"
    else:
        status = "inconclusive"
    return {
        "status": status,
        "primary_claim": (
            "provider/runtime-portable RLM execution contract with "
            "evidence-gated parent synthesis"
        ),
        "required_completed_primary_cells_per_family": required_completed,
    }


def _empty_secondary_metrics() -> dict[str, Any]:
    return {
        "quality_score": None,
        "omitted_fact_safety_score": None,
        "unsupported_claim_rate": None,
        "latency_seconds": None,
        "token_usage": None,
        "cost_usd": None,
        "measurement_status": "not_measured_in_contracts_only_mode",
    }


def _command_version(command_path: str | None) -> str | None:
    if command_path is None:
        return None
    for args in ([command_path, "--version"], [command_path, "version"]):
        try:
            completed = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        output = (completed.stdout or completed.stderr).strip()
        if output:
            return output.splitlines()[0][:160]
    return None


async def _run_live_rlm_traceguard_cell(
    *,
    family: RuntimeFamily,
    fixture: dict[str, Any],
    timeout_seconds: float,
    memory_context: MemoryContext | None = None,
) -> dict[str, Any]:
    memory_context = memory_context or MemoryContext()
    runtime = _build_runtime(family)
    _extend_runtime_timeouts(runtime, timeout_seconds=timeout_seconds)
    root_call_id = _root_call_id(family=family, fixture=fixture)
    parent_synthesis_call_id = _parent_synthesis_call_id(
        family=family,
        fixture=fixture,
    )
    cell_identity = synthesis_cell_identity(family=family, fixture=fixture)
    retry_state = ParentSynthesisRetryState(
        parent_synthesis_run_id=parent_synthesis_call_id,
    )
    retry_state.ensure_cell(cell_identity)
    memory_recall = (
        memory_context.backend.recall(
            family_id=family.family_id,
            fixture_category=fixture["fixture_category"],
            tasks=(
                "extract_child_evidence",
                "synthesize_parent_answer_from_child_evidence",
            ),
        )
        if memory_context.can_read
        else None
    )
    memory_priors = memory_recall.priors if memory_recall is not None else ()
    child_records: list[dict[str, Any]] = []
    for chunk in _selected_chunks(fixture):
        child_output = await _execute_json_task(
            runtime,
            prompt=_child_prompt(fixture, chunk, memory_priors=memory_priors),
            timeout_seconds=timeout_seconds,
        )
        child_records.append(
            {
                "call_id": (
                    f"{fixture['fixture_id']}::{family.family_id}::child::"
                    f"{len(child_records) + 1}"
                ),
                "parent_call_id": root_call_id,
                "chunk_id": chunk["chunk_id"],
                "output": child_output,
            }
        )

    parent_output = await _execute_json_task(
        runtime,
        prompt=_parent_prompt(fixture, child_records, memory_priors=memory_priors),
        timeout_seconds=timeout_seconds,
    )
    fixture_manifest = build_manifest_from_fixture(fixture)
    manifest = build_fresh_child_evidence_manifest(
        fixture_manifest=fixture_manifest,
        child_records=child_records,
    )
    fresh_child_evidence_pass = bool(manifest) and len(manifest) == len(fixture_manifest)
    validation = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=parent_output,
    )
    coverage_pass = _live_selected_coverage_pass(fixture, child_records)
    traceguard_repair = _initial_traceguard_repair_block(
        validation=validation,
        selected_chunk_coverage_pass=coverage_pass,
        parent_synthesis=parent_output,
        allowed_evidence_manifest=manifest,
        child_records=child_records,
    )
    effective_validation = validation
    effective_parent_output = parent_output
    repaired_parent_output: dict[str, Any] | None = None
    retried_parent_output: dict[str, Any] | None = None
    if _schedule_traceguard_repair_attempt(
        traceguard_repair=traceguard_repair,
        retry_state=retry_state,
        synthesis_cell_identity=cell_identity,
    ):
        try:
            repair_parent_output = await _execute_json_task(
                runtime,
                prompt=build_traceguard_repair_prompt(
                    rejected_claim=validation.rejected_claims[0],
                    allowed_evidence_manifest=manifest,
                    original_parent_synthesis=parent_output,
                    child_records=child_records,
                ),
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - live adapters expose provider-specific errors
            traceguard_repair = _failed_traceguard_repair_runtime_block(
                initial_repair=traceguard_repair,
                error=exc,
            )
            repair_parent_output = None
        if repair_parent_output is not None:
            repaired_parent_output = apply_repaired_evidence_chunk_ids(
                original_parent_synthesis=parent_output,
                repair_parent_synthesis=repair_parent_output,
                missing_evidence_handle_references=traceguard_repair[
                    "missing_evidence_handle_references"
                ],
            )
            repaired_validation = validate_parent_synthesis(
                evidence_manifest=manifest,
                parent_synthesis=repaired_parent_output,
            )
            patch_fidelity_errors = [
                *_repair_response_handle_errors(
                    repair_parent_synthesis=repair_parent_output,
                    missing_evidence_handle_references=traceguard_repair[
                        "missing_evidence_handle_references"
                    ],
                ),
                *_missing_handle_repair_fidelity_errors(
                    original_parent_synthesis=parent_output,
                    repaired_parent_synthesis=repaired_parent_output,
                    allowed_evidence_manifest=manifest,
                    child_records=child_records,
                    missing_evidence_handle_references=traceguard_repair[
                        "missing_evidence_handle_references"
                    ],
                ),
            ]
            traceguard_repair = _attempted_traceguard_repair_block(
                initial_repair=traceguard_repair,
                repaired_validation=repaired_validation,
                patch_fidelity_errors=patch_fidelity_errors,
                parent_synthesis_diff=_parent_synthesis_before_after_diff(
                    parent_output,
                    repaired_parent_output,
                ),
            )
            effective_validation = repaired_validation
            effective_parent_output = repaired_parent_output
        if traceguard_repair["repair_accept"] is True:
            try:
                retried_parent_output = await _execute_json_task(
                    runtime,
                    prompt=build_parent_synthesis_retry_prompt(
                        fixture=fixture,
                        child_records=child_records,
                        repaired_parent_synthesis=repaired_parent_output,
                        traceguard_repair=traceguard_repair,
                    ),
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - live adapters expose provider-specific errors
                traceguard_repair = _failed_parent_synthesis_retry_runtime_block(
                    attempted_repair=traceguard_repair,
                    error=exc,
                )
            if retried_parent_output is not None:
                retry_validation = validate_parent_synthesis(
                    evidence_manifest=manifest,
                    parent_synthesis=retried_parent_output,
                )
                retry_patch_fidelity_errors = _missing_handle_repair_fidelity_errors(
                    original_parent_synthesis=parent_output,
                    repaired_parent_synthesis=retried_parent_output,
                    allowed_evidence_manifest=manifest,
                    child_records=child_records,
                    missing_evidence_handle_references=traceguard_repair[
                        "missing_evidence_handle_references"
                    ],
                )
                traceguard_repair = _parent_synthesis_retry_repair_block(
                    attempted_repair=traceguard_repair,
                    retry_validation=retry_validation,
                    retry_patch_fidelity_errors=retry_patch_fidelity_errors,
                )
                effective_validation = retry_validation
                effective_parent_output = retried_parent_output

    retry_pass = (
        traceguard_repair["parent_synthesis_retry_accept"] is True
        if traceguard_repair["repair_accept"] is True
        else traceguard_repair["parent_synthesis_retry_accept"] is not False
    )
    mandatory_pass = (
        effective_validation.accepted
        and coverage_pass
        and fresh_child_evidence_pass
        and traceguard_repair["repair_accept"] is not False
        and retry_pass
    )
    traceguard_repair = _traceguard_repair_with_retry_state(
        traceguard_repair=traceguard_repair,
        retry_state=retry_state,
        synthesis_cell_identity=cell_identity,
    )
    memory_write = (
        memory_context.backend.store(
            build_memory_observations_from_cell(
                family_id=family.family_id,
                fixture_category=fixture["fixture_category"],
                traceguard_accepted=effective_validation.accepted,
                traceguard_repair=traceguard_repair,
            )
        )
        if memory_context.can_write
        else None
    )
    artifact = {
        "completed": True,
        "status": "live_contract_pass" if mandatory_pass else "primary_contract_failure",
        "failure_classification": "pass" if mandatory_pass else "primary_contract_failure",
        "mandatory_contract_pass": mandatory_pass,
        "trace_structure": {
            "root_call_id": root_call_id,
            "parent_synthesis_call_id": parent_synthesis_call_id,
            "synthesis_cell_identity": cell_identity,
            "child_call_count": len(child_records),
            "child_records": child_records,
            "selected_chunk_coverage_pass": coverage_pass,
            "fresh_child_evidence_pass": fresh_child_evidence_pass,
            "fresh_child_evidence_manifest": [
                evidence.to_dict() for evidence in manifest
            ],
        },
        "parent_synthesis": parent_output,
        "initial_traceguard_validation": validation.to_dict(),
        "effective_parent_synthesis": effective_parent_output,
        "effective_traceguard_validation": effective_validation.to_dict(),
        "traceguard_validation": effective_validation.to_dict(),
        "traceguard_repair": traceguard_repair,
        "secondary_metrics": _empty_secondary_metrics(),
    }
    if memory_context.mode != "off":
        artifact["memory_trace"] = _memory_trace_block(
            memory_context=memory_context,
            memory_recall=memory_recall,
            memory_write=memory_write,
            prompt_injections=[
                prior.to_prompt_dict()
                for prior in _memory_priors_for_task(
                    memory_priors,
                    "extract_child_evidence",
                )
            ]
            + [
                prior.to_prompt_dict()
                for prior in _memory_priors_for_task(
                    memory_priors,
                    "synthesize_parent_answer_from_child_evidence",
                )
            ],
        )
    if repaired_parent_output is not None:
        artifact["repaired_parent_synthesis"] = repaired_parent_output
    if retried_parent_output is not None:
        artifact["retried_parent_synthesis"] = retried_parent_output
    return artifact


def build_fresh_child_evidence_manifest(
    *,
    fixture_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
) -> tuple[TraceGuardEvidence, ...]:
    """Build TraceGuard evidence from the current run's child outputs only."""
    fixture_allowed = {(item.fact_id, item.chunk_id): item for item in fixture_manifest}
    evidence: list[TraceGuardEvidence] = []
    seen: set[tuple[str, str]] = set()
    for record in child_records:
        output = record.get("output")
        if not isinstance(output, Mapping):
            continue
        observed_facts = output.get("observed_facts")
        if not isinstance(observed_facts, list):
            continue
        for fact in observed_facts:
            if not isinstance(fact, Mapping):
                continue
            fact_id = fact.get("fact_id")
            chunk_id = fact.get("evidence_chunk_id")
            text = fact.get("text")
            if not (
                isinstance(fact_id, str)
                and isinstance(chunk_id, str)
                and isinstance(text, str)
            ):
                continue
            key = (fact_id, chunk_id)
            allowed = fixture_allowed.get(key)
            if (
                key in seen
                or allowed is None
                or not _child_evidence_text_matches_fixture(
                    fact_id=fact_id,
                    child_text=text,
                    fixture_text=allowed.text,
                )
            ):
                continue
            seen.add(key)
            child_call_id = record.get("call_id")
            evidence.append(
                TraceGuardEvidence(
                    fact_id=fact_id,
                    chunk_id=chunk_id,
                    text=allowed.text,
                    child_call_id=(
                        child_call_id if isinstance(child_call_id, str) else None
                    ),
                )
            )
    return tuple(
        sorted(evidence, key=lambda item: (item.fact_id, item.chunk_id, item.text))
    )


def _child_evidence_text_matches_fixture(
    *,
    fact_id: str,
    child_text: str,
    fixture_text: str,
) -> bool:
    normalized_child = " ".join(child_text.split())
    normalized_fixture = " ".join(fixture_text.split())
    if not normalized_child:
        return False
    if normalized_child == normalized_fixture:
        return True
    prefix = f"FACT:{fact_id} "
    if normalized_fixture.startswith(prefix):
        return normalized_child == normalized_fixture[len(prefix) :]
    return False


def _memory_trace_block(
    *,
    memory_context: MemoryContext,
    memory_recall: Any,
    memory_write: Any,
    prompt_injections: list[dict[str, Any]],
) -> dict[str, Any]:
    recall_trace = (
        memory_recall.to_trace()
        if memory_recall is not None
        else {"recalled_priors": [], "rejected_memory_candidates": []}
    )
    write_trace = (
        memory_write.to_trace()
        if memory_write is not None
        else {
            "stored_observations": [],
            "rejected_memory_candidates": [],
            "contamination_guard": {"passed": True, "rejected_count": 0},
        }
    )
    return {
        "mode": memory_context.mode,
        "recalled_priors": recall_trace["recalled_priors"],
        "rejected_memory_candidates": [
            *recall_trace["rejected_memory_candidates"],
            *write_trace["rejected_memory_candidates"],
        ],
        "prompt_injections": prompt_injections,
        "stored_observations": write_trace["stored_observations"],
        "contamination_guard": write_trace["contamination_guard"],
    }


def _initial_traceguard_repair_block(
    *,
    validation: TraceGuardResult,
    selected_chunk_coverage_pass: bool,
    parent_synthesis: dict[str, Any],
    allowed_evidence_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record eligibility for the narrow missing-handle repair loop."""
    rejection_reasons = [
        rejection.reason for rejection in validation.rejected_claims
    ]
    unique_rejection_reasons = list(dict.fromkeys(rejection_reasons))
    missing_evidence_handle_references = identify_missing_evidence_handle_references(
        parent_synthesis=parent_synthesis,
        validation=validation,
        allowed_evidence_manifest=allowed_evidence_manifest,
        child_records=child_records,
    )
    missing_rejection_count = sum(
        1
        for rejection in validation.rejected_claims
        if rejection.reason == "missing_evidence_handle"
    )
    missing_handle_resolution_pass = _missing_evidence_handle_resolution_pass(
        missing_rejection_count=missing_rejection_count,
        missing_evidence_handle_references=missing_evidence_handle_references,
    )
    exclusive_missing_handle_rejection = (
        _initial_rejection_contains_only_missing_handle_reasons(validation)
    )
    exclusive_repairable_missing_handle_rejection = (
        _initial_rejection_contains_only_repairable_missing_handles(
            validation=validation,
            missing_handle_resolution_pass=missing_handle_resolution_pass,
        )
    )
    repair_eligible = selected_chunk_coverage_pass and (
        exclusive_repairable_missing_handle_rejection
    )
    failure_reason = _traceguard_repair_failure_reason(
        validation=validation,
        selected_chunk_coverage_pass=selected_chunk_coverage_pass,
        unique_rejection_reasons=unique_rejection_reasons,
        missing_handle_resolution_pass=missing_handle_resolution_pass,
    )
    return {
        "initial_accept": validation.accepted,
        "repair_eligible": repair_eligible,
        "repair_attempted": False,
        "initial_failure_reason": failure_reason,
        "failure_reason": failure_reason,
        "repair_strategy": _traceguard_repair_strategy(
            repair_eligible=repair_eligible,
            failure_reason=failure_reason,
        ),
        "repair_accept": None,
        "repair_failure_reason": None,
        "repair_runtime_error": None,
        "patch_fidelity_errors": None,
        "parent_synthesis_retry_attempted": False,
        "parent_synthesis_retry_accept": None,
        "parent_synthesis_retry_failure_reason": None,
        "parent_synthesis_retry_runtime_error": None,
        "parent_synthesis_retry_validation": None,
        "parent_synthesis_retry_patch_fidelity_errors": None,
        "subsequent_repair_attempted": False,
        "subsequent_repair_skip_reason": None,
        "initial_rejection_reasons": unique_rejection_reasons,
        "initial_rejection_exclusive_missing_evidence_handle": (
            exclusive_missing_handle_rejection
        ),
        "initial_rejection_exclusive_repairable_missing_evidence_handle": (
            exclusive_repairable_missing_handle_rejection
        ),
        "missing_evidence_handle_resolution_pass": missing_handle_resolution_pass,
        "missing_evidence_handle_references": missing_evidence_handle_references,
        "allowed_evidence_handle_set": list(
            _allowed_repair_evidence_handle_set(
                allowed_evidence_manifest=allowed_evidence_manifest,
                child_records=child_records,
            )
        ),
        "before_validation": validation.to_dict(),
        "after_validation": None,
        "parent_synthesis_diff": None,
    }


def _schedule_traceguard_repair_attempt(
    *,
    traceguard_repair: Mapping[str, Any],
    retry_state: ParentSynthesisRetryState,
    synthesis_cell_identity: str,
) -> bool:
    """Gate one automatic repair attempt and record it before runtime calls."""
    if traceguard_repair.get("repair_eligible") is not True:
        return False
    if traceguard_repair.get("repair_attempted") is True:
        return False
    return retry_state.record_repair_attempt(synthesis_cell_identity)


def _initial_rejection_contains_only_missing_handle_reasons(
    validation: TraceGuardResult,
) -> bool:
    """Assert that TraceGuard rejected only missing evidence-handle claims."""
    if validation.accepted or not validation.rejected_claims:
        return False
    return all(
        rejection.reason == "missing_evidence_handle"
        for rejection in validation.rejected_claims
    )


def _initial_rejection_contains_only_repairable_missing_handles(
    *,
    validation: TraceGuardResult,
    missing_handle_resolution_pass: bool,
) -> bool:
    """Assert that every initial missing-handle rejection is patch-repairable."""
    return (
        _initial_rejection_contains_only_missing_handle_reasons(validation)
        and missing_handle_resolution_pass
    )


def identify_missing_evidence_handle_references(
    *,
    parent_synthesis: dict[str, Any],
    validation: TraceGuardResult,
    allowed_evidence_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Locate repairable parent claim entries and capture their allowed handles."""
    missing_claim_keys = {
        (rejection.claim.fact_id, rejection.claim.surface, rejection.claim.text)
        for rejection in validation.rejected_claims
        if rejection.reason == "missing_evidence_handle"
        and rejection.claim.fact_id is not None
    }
    if not missing_claim_keys:
        return []

    allowed_by_fact = {item.fact_id: item for item in allowed_evidence_manifest}
    allowed_repair_handles_by_fact = _allowed_repair_evidence_handles_by_fact(
        allowed_evidence_manifest=allowed_evidence_manifest,
        child_records=child_records,
    )
    child_handles_by_fact = _child_evidence_handles_by_fact(child_records)
    references: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, str]] = set()

    for candidate in _iter_parent_claim_reference_mappings(parent_synthesis):
        mapping = candidate["mapping"]
        if _chunk_id_from_mapping(mapping) is not None:
            continue

        field_state = _evidence_chunk_id_field_state(mapping)
        if field_state not in {"missing", "null"}:
            continue

        claim_text = _claim_text_from_mapping(mapping)
        for fact_id in _supported_fact_ids_from_mapping(mapping):
            key = (fact_id, candidate["surface"], claim_text)
            if key not in missing_claim_keys:
                continue

            seen_key = (candidate["path"], fact_id)
            if seen_key in seen_paths:
                continue
            seen_paths.add(seen_key)

            allowed = allowed_by_fact.get(fact_id)
            child_handles = child_handles_by_fact.get(fact_id, ())
            evidence_handle = allowed_repair_handles_by_fact.get(fact_id)
            references.append(
                {
                    "parent_path": candidate["path"],
                    "surface": candidate["surface"],
                    "fact_id": fact_id,
                    "claim_text": claim_text,
                    "evidence_chunk_id_state": field_state,
                    "evidence_handle": evidence_handle,
                    "evidence_handles": {
                        "allowed_manifest": None
                        if allowed is None
                        else allowed.chunk_id,
                        "child_records": list(child_handles),
                    },
                }
            )

    return references


def apply_repaired_evidence_chunk_ids(
    *,
    original_parent_synthesis: dict[str, Any],
    repair_parent_synthesis: dict[str, Any],
    missing_evidence_handle_references: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply only missing/null evidence_chunk_id values from a repair response."""
    patched_parent_synthesis = json.loads(json.dumps(original_parent_synthesis))

    for reference in missing_evidence_handle_references:
        if reference.get("evidence_chunk_id_state") not in {"missing", "null"}:
            continue
        parent_path = reference.get("parent_path")
        if not isinstance(parent_path, str) or not parent_path:
            continue

        source_mapping = _mapping_at_parent_reference_path(
            repair_parent_synthesis,
            parent_path,
        )
        target_mapping = _mapping_at_parent_reference_path(
            patched_parent_synthesis,
            parent_path,
        )
        if source_mapping is None or target_mapping is None:
            continue
        if _evidence_chunk_id_field_state(target_mapping) not in {"missing", "null"}:
            continue

        repaired_value = source_mapping.get("evidence_chunk_id")
        allowed_value = reference.get("evidence_handle")
        if (
            isinstance(repaired_value, str)
            and repaired_value
            and repaired_value == allowed_value
        ):
            target_mapping["evidence_chunk_id"] = repaired_value

    return patched_parent_synthesis


_DIFF_MISSING = object()


def _parent_synthesis_before_after_diff(
    original: Any,
    repaired: Any,
    *,
    path: str = "$",
) -> list[dict[str, Any]]:
    """Build a JSON-safe diff for inspecting the repair patch."""
    if isinstance(original, Mapping) and isinstance(repaired, Mapping):
        diffs: list[dict[str, Any]] = []
        for key in sorted(original.keys() | repaired.keys()):
            before = original.get(key, _DIFF_MISSING)
            after = repaired.get(key, _DIFF_MISSING)
            diffs.extend(
                _parent_synthesis_before_after_diff(
                    before,
                    after,
                    path=f"{path}.{key}",
                )
            )
        return diffs

    if isinstance(original, list) and isinstance(repaired, list):
        diffs = []
        for index in range(max(len(original), len(repaired))):
            before = original[index] if index < len(original) else _DIFF_MISSING
            after = repaired[index] if index < len(repaired) else _DIFF_MISSING
            diffs.extend(
                _parent_synthesis_before_after_diff(
                    before,
                    after,
                    path=f"{path}[{index}]",
                )
            )
        return diffs

    if original == repaired:
        return []
    return [_parent_synthesis_diff_entry(path=path, before=original, after=repaired)]


def _parent_synthesis_diff_entry(
    *,
    path: str,
    before: Any,
    after: Any,
) -> dict[str, Any]:
    entry = {
        "path": path,
        "before_state": _parent_synthesis_diff_value_state(before),
        "after_state": _parent_synthesis_diff_value_state(after),
    }
    if before is not _DIFF_MISSING:
        entry["before"] = before
    if after is not _DIFF_MISSING:
        entry["after"] = after
    return entry


def _parent_synthesis_diff_value_state(value: Any) -> str:
    if value is _DIFF_MISSING:
        return "missing"
    if value is None:
        return "null"
    return "value"


def _repair_response_handle_errors(
    *,
    repair_parent_synthesis: dict[str, Any],
    missing_evidence_handle_references: Iterable[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for reference in missing_evidence_handle_references:
        if reference.get("evidence_chunk_id_state") not in {"missing", "null"}:
            continue
        parent_path = reference.get("parent_path")
        if not isinstance(parent_path, str) or not parent_path:
            continue

        source_mapping = _mapping_at_parent_reference_path(
            repair_parent_synthesis,
            parent_path,
        )
        if source_mapping is None:
            continue

        repaired_value = source_mapping.get("evidence_chunk_id")
        if not isinstance(repaired_value, str) or not repaired_value:
            continue

        allowed_value = reference.get("evidence_handle")
        if repaired_value == allowed_value:
            continue

        fact_id = reference.get("fact_id")
        errors.append(
            f"$.{parent_path}.evidence_chunk_id proposed a handle outside the "
            f"allowed evidence-handle set for {fact_id}"
        )
    return errors


def _mapping_at_parent_reference_path(
    parent_synthesis: Mapping[str, Any],
    parent_path: str,
) -> dict[str, Any] | None:
    current: Any = parent_synthesis
    for token in parent_path.split("."):
        current = _reference_path_token_value(current, token)
        if current is None:
            return None
    if isinstance(current, dict):
        return current
    return None


def _reference_path_token_value(value: Any, token: str) -> Any:
    if not token:
        return None

    key_end = token.find("[")
    key = token if key_end == -1 else token[:key_end]
    if key:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]

    remainder = "" if key_end == -1 else token[key_end:]
    while remainder:
        if not remainder.startswith("["):
            return None
        index_end = remainder.find("]")
        if index_end == -1:
            return None
        index_text = remainder[1:index_end]
        if not index_text.isdecimal():
            return None
        index = int(index_text)
        if not isinstance(value, list) or index >= len(value):
            return None
        value = value[index]
        remainder = remainder[index_end + 1 :]
    return value


def _missing_evidence_handle_resolution_pass(
    *,
    missing_rejection_count: int,
    missing_evidence_handle_references: list[dict[str, Any]],
) -> bool:
    if missing_rejection_count == 0:
        return False
    if len(missing_evidence_handle_references) != missing_rejection_count:
        return False
    return all(
        isinstance(reference.get("evidence_handle"), str)
        and bool(reference["evidence_handle"])
        for reference in missing_evidence_handle_references
    )


def _iter_parent_claim_reference_mappings(
    parent_synthesis: dict[str, Any],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    result = parent_synthesis.get("result")
    if isinstance(result, dict):
        for key in (
            "retained_facts",
            "observed_facts",
            "facts",
            "retained_evidence",
            "observed_evidence",
        ):
            references.extend(
                _reference_mappings_from_surface(
                    result.get(key),
                    surface=f"result.{key}",
                    path=f"result.{key}",
                )
            )
        if isinstance(result.get("fact_id"), str):
            references.append(
                {
                    "surface": "result",
                    "path": "result",
                    "mapping": result,
                }
            )

    references.extend(
        _reference_mappings_from_surface(
            parent_synthesis.get("evidence_references"),
            surface="evidence_references",
            path="evidence_references",
        )
    )
    return references


def _reference_mappings_from_surface(
    value: Any,
    *,
    surface: str,
    path: str,
) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [{"surface": surface, "path": path, "mapping": value}]
    if isinstance(value, list):
        return [
            {
                "surface": surface,
                "path": f"{path}[{index}]",
                "mapping": item,
            }
            for index, item in enumerate(value)
            if isinstance(item, dict)
        ]
    return []


def _child_evidence_handles_by_fact(
    child_records: list[dict[str, Any]],
) -> dict[str, tuple[str, ...]]:
    handles: dict[str, list[str]] = {}
    for record in normalize_child_records(child_records):
        output = record.get("output")
        if not isinstance(output, dict):
            continue
        observed_facts = output.get("observed_facts")
        if not isinstance(observed_facts, list):
            continue
        for fact in observed_facts:
            if not isinstance(fact, dict):
                continue
            fact_id = fact.get("fact_id")
            if not isinstance(fact_id, str) or not fact_id:
                continue
            chunk_id = _chunk_id_from_mapping(fact)
            if chunk_id is None and isinstance(record.get("chunk_id"), str):
                chunk_id = record["chunk_id"]
            if chunk_id is None:
                continue
            handles.setdefault(fact_id, []).append(chunk_id)
    return {
        fact_id: tuple(dict.fromkeys(fact_handles))
        for fact_id, fact_handles in handles.items()
    }


def _allowed_repair_evidence_handles_by_fact(
    *,
    allowed_evidence_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
) -> dict[str, str]:
    child_handles_by_fact = _child_evidence_handles_by_fact(child_records)
    return {
        item.fact_id: item.chunk_id
        for item in allowed_evidence_manifest
        if item.chunk_id in child_handles_by_fact.get(item.fact_id, ())
    }


def _allowed_repair_evidence_handle_set(
    *,
    allowed_evidence_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _allowed_repair_evidence_handles_by_fact(
                allowed_evidence_manifest=allowed_evidence_manifest,
                child_records=child_records,
            ).values()
        )
    )


def normalize_repair_prompt_evidence_manifest(
    evidence_manifest: Iterable[TraceGuardEvidence | Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return evidence manifest fields that are stable and relevant to repair."""
    entries = [
        {
            field: _stable_json_value(
                item[field],
                exclude_nondeterministic_keys=True,
            )
            for field in CANONICAL_REPAIR_PROMPT_EVIDENCE_MANIFEST_FIELDS
        }
        for item in normalize_allowed_evidence_manifest(evidence_manifest)
    ]
    return _unique_sorted_repair_prompt_entries(
        entries,
        key=lambda entry: (
            str(entry["fact_id"]),
            str(entry["chunk_id"]),
            str(entry["text"]),
        ),
    )


def normalize_repair_prompt_parent_synthesis(
    parent_synthesis: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic parent-synthesis view for prompt rendering."""
    if not isinstance(parent_synthesis, Mapping):
        msg = "parent synthesis must be a mapping"
        raise TypeError(msg)
    normalized = _stable_json_value(
        parent_synthesis,
        exclude_nondeterministic_keys=True,
    )
    if not isinstance(normalized, dict):
        msg = "normalized parent synthesis must be a mapping"
        raise TypeError(msg)
    return normalized


def normalize_repair_prompt_child_records(
    child_records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return child evidence records without runtime call IDs or timestamps."""
    entries = [
        {
            "chunk_id": _stable_json_value(
                record["chunk_id"],
                exclude_nondeterministic_keys=True,
            ),
            "output": _stable_json_value(
                record["output"],
                exclude_nondeterministic_keys=True,
            ),
        }
        for record in normalize_child_records(child_records)
    ]
    return _unique_sorted_repair_prompt_entries(
        entries,
        key=lambda entry: (
            str(entry["chunk_id"]),
            _stable_json_sort_token(entry["output"]),
        ),
    )


def _unique_sorted_repair_prompt_entries(
    entries: Iterable[dict[str, Any]],
    *,
    key: Any,
) -> tuple[dict[str, Any], ...]:
    sorted_entries = sorted(entries, key=key)
    unique_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in sorted_entries:
        token = _stable_json_sort_token(entry)
        if token in seen:
            continue
        seen.add(token)
        unique_entries.append(entry)
    return tuple(unique_entries)


def normalize_child_records(
    child_records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return canonical child evidence records for repair eligibility checks."""
    records = [_normalize_child_record(record) for record in child_records]
    return tuple(sorted(records, key=_child_record_sort_key))


def _normalize_child_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        msg = "child records must be mappings"
        raise TypeError(msg)

    output = record.get("output")
    normalized = {
        "call_id": _canonical_child_string(record.get("call_id"), default=""),
        "parent_call_id": _canonical_child_string(
            record.get("parent_call_id"),
            default=None,
        ),
        "chunk_id": _canonical_child_string(record.get("chunk_id"), default=""),
        "output": _normalize_child_output(output),
    }
    return {field: normalized[field] for field in CANONICAL_CHILD_RECORD_FIELDS}


def _normalize_child_output(output: Any) -> dict[str, Any]:
    raw_output = output if isinstance(output, Mapping) else {}
    normalized = {
        "observed_facts": _normalize_child_observed_facts(
            raw_output.get("observed_facts")
        ),
        "residual_gaps": _normalize_child_residual_gaps(
            raw_output.get("residual_gaps")
        ),
    }
    return {field: normalized[field] for field in CANONICAL_CHILD_OUTPUT_FIELDS}


def _normalize_child_observed_facts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    facts: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fact = dict(item)
        normalized = {
            "fact_id": _canonical_child_fact_id_from_mapping(fact),
            "evidence_chunk_id": _canonical_child_chunk_id_from_mapping(fact),
            "text": _canonical_child_text_from_mapping(fact),
        }
        facts.append(
            {
                field: normalized[field]
                for field in CANONICAL_CHILD_OBSERVED_FACT_FIELDS
            }
        )
    return sorted(
        facts,
        key=lambda fact: (
            fact["fact_id"],
            fact["evidence_chunk_id"],
            fact["text"],
        ),
    )


def _normalize_child_residual_gaps(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        _canonical_child_string(item, default="")
        for item in value
        if item is not None
    )


def _child_record_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        record["chunk_id"],
        record["call_id"],
        record["parent_call_id"] or "",
        json.dumps(record["output"], sort_keys=True, separators=(",", ":")),
    )


def _canonical_child_string(value: Any, *, default: str | None) -> str | None:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _canonical_child_fact_id_from_mapping(value: dict[str, Any]) -> str:
    fact_ids = _supported_fact_ids_from_mapping(value)
    if fact_ids:
        return fact_ids[0]

    for key in CLAIM_FACT_KEYS:
        item = _canonical_child_string(value.get(key), default="")
        if item:
            return item
    for key in CLAIM_FACT_LIST_KEYS:
        item = value.get(key)
        if isinstance(item, list):
            for entry in item:
                normalized = _canonical_child_string(entry, default="")
                if normalized:
                    return normalized
    return ""


def _canonical_child_chunk_id_from_mapping(value: dict[str, Any]) -> str:
    for key in CHUNK_KEYS:
        item = _canonical_child_string(value.get(key), default="")
        if item:
            return item
    return ""


def _canonical_child_text_from_mapping(value: dict[str, Any]) -> str:
    text = _claim_text_from_mapping(value)
    if text:
        return text
    for key in ("quoted_evidence", "text", "statement", "claim", "summary"):
        item = _canonical_child_string(value.get(key), default="")
        if item:
            return item
    return ""


def _supported_fact_ids_from_mapping(value: dict[str, Any]) -> tuple[str, ...]:
    fact_ids: list[str] = []
    for key in CLAIM_FACT_KEYS:
        item = value.get(key)
        if isinstance(item, str) and item:
            fact_ids.append(item)
    for key in CLAIM_FACT_LIST_KEYS:
        item = value.get(key)
        if isinstance(item, list):
            fact_ids.extend(entry for entry in item if isinstance(entry, str) and entry)
    return tuple(dict.fromkeys(fact_ids))


def _chunk_id_from_mapping(value: dict[str, Any]) -> str | None:
    for key in CHUNK_KEYS:
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
    return None


def _claim_text_from_mapping(value: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("quoted_evidence", "text", "statement", "claim", "summary"):
        item = value.get(key)
        if isinstance(item, str) and item:
            parts.append(item)
    return "\n".join(parts)


def _evidence_chunk_id_field_state(value: dict[str, Any]) -> str:
    if "evidence_chunk_id" not in value:
        return "missing"
    if value["evidence_chunk_id"] is None:
        return "null"
    return "invalid"


def _traceguard_repair_failure_reason(
    *,
    validation: TraceGuardResult,
    selected_chunk_coverage_pass: bool,
    unique_rejection_reasons: list[str],
    missing_handle_resolution_pass: bool,
) -> str | None:
    if validation.accepted:
        return None
    if not selected_chunk_coverage_pass:
        return "selected_chunk_coverage_failed"
    if unique_rejection_reasons == ["missing_evidence_handle"]:
        if not missing_handle_resolution_pass:
            return "missing_evidence_handle_unresolved"
        return "missing_evidence_handle"
    if "missing_evidence_handle" in unique_rejection_reasons:
        return "mixed_traceguard_rejection_reasons"
    if unique_rejection_reasons:
        return unique_rejection_reasons[0]
    return "traceguard_rejected"


def _traceguard_repair_strategy(
    *,
    repair_eligible: bool,
    failure_reason: str | None,
) -> str:
    if repair_eligible:
        return "patch_missing_evidence_handle_fields"
    if failure_reason == "mixed_traceguard_rejection_reasons":
        return "not_attempted_non_exclusive_traceguard_rejection"
    if failure_reason is None:
        return "not_attempted_initial_traceguard_accept"
    return "not_attempted_non_repairable_traceguard_rejection"


def _attempted_traceguard_repair_block(
    *,
    initial_repair: dict[str, Any],
    repaired_validation: TraceGuardResult,
    patch_fidelity_errors: list[str],
    parent_synthesis_diff: list[dict[str, Any]],
) -> dict[str, Any]:
    repair_accept = repaired_validation.accepted and not patch_fidelity_errors
    failure_reason = None
    if not repair_accept:
        failure_reason = (
            "repair_patch_fidelity_failed"
            if patch_fidelity_errors
            else _traceguard_after_repair_failure_reason(repaired_validation)
        )
    subsequent_repair_skip_reason = (
        None if repair_accept else "repair_attempt_already_used"
    )
    return {
        **initial_repair,
        "repair_attempted": True,
        "failure_reason": failure_reason,
        "repair_failure_reason": failure_reason,
        "repair_accept": repair_accept,
        "repair_runtime_error": None,
        "after_validation": repaired_validation.to_dict(),
        "parent_synthesis_diff": parent_synthesis_diff,
        "patch_fidelity_errors": patch_fidelity_errors,
        "subsequent_repair_attempted": False,
        "subsequent_repair_skip_reason": subsequent_repair_skip_reason,
    }


def _failed_traceguard_repair_runtime_block(
    *,
    initial_repair: dict[str, Any],
    error: BaseException,
) -> dict[str, Any]:
    return {
        **initial_repair,
        "repair_attempted": True,
        "failure_reason": "repair_runtime_error",
        "repair_failure_reason": "repair_runtime_error",
        "repair_accept": False,
        "repair_runtime_error": _runtime_error_detail(error),
        "after_validation": None,
        "parent_synthesis_diff": None,
        "patch_fidelity_errors": None,
        "subsequent_repair_attempted": False,
        "subsequent_repair_skip_reason": "repair_attempt_already_used",
    }


def _parent_synthesis_retry_repair_block(
    *,
    attempted_repair: dict[str, Any],
    retry_validation: TraceGuardResult,
    retry_patch_fidelity_errors: list[str],
) -> dict[str, Any]:
    retry_accept = retry_validation.accepted and not retry_patch_fidelity_errors
    failure_reason = None
    if not retry_accept:
        failure_reason = (
            "parent_synthesis_retry_patch_fidelity_failed"
            if retry_patch_fidelity_errors
            else _traceguard_after_repair_failure_reason(retry_validation)
        )
    subsequent_repair_skip_reason = (
        None if retry_accept else "repair_attempt_already_used"
    )
    return {
        **attempted_repair,
        "parent_synthesis_retry_attempted": True,
        "parent_synthesis_retry_accept": retry_accept,
        "parent_synthesis_retry_failure_reason": failure_reason,
        "parent_synthesis_retry_runtime_error": None,
        "parent_synthesis_retry_validation": retry_validation.to_dict(),
        "parent_synthesis_retry_patch_fidelity_errors": retry_patch_fidelity_errors,
        "subsequent_repair_attempted": False,
        "subsequent_repair_skip_reason": subsequent_repair_skip_reason,
    }


def _failed_parent_synthesis_retry_runtime_block(
    *,
    attempted_repair: dict[str, Any],
    error: BaseException,
) -> dict[str, Any]:
    return {
        **attempted_repair,
        "parent_synthesis_retry_attempted": True,
        "parent_synthesis_retry_accept": False,
        "parent_synthesis_retry_failure_reason": "parent_synthesis_retry_runtime_error",
        "parent_synthesis_retry_runtime_error": _runtime_error_detail(error),
        "parent_synthesis_retry_validation": None,
        "parent_synthesis_retry_patch_fidelity_errors": None,
        "subsequent_repair_attempted": False,
        "subsequent_repair_skip_reason": "repair_attempt_already_used",
    }


def _runtime_error_detail(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:500]


def _traceguard_repair_with_retry_state(
    *,
    traceguard_repair: dict[str, Any],
    retry_state: ParentSynthesisRetryState,
    synthesis_cell_identity: str,
) -> dict[str, Any]:
    retry_state_payload = retry_state.to_dict()
    retry_state_payload["synthesis_cell_identity"] = synthesis_cell_identity
    return {
        "failure_reason": traceguard_repair.get("failure_reason"),
        **traceguard_repair,
        "retry_orchestration_state": retry_state_payload,
    }


def _traceguard_after_repair_failure_reason(validation: TraceGuardResult) -> str:
    rejection_reasons = [
        rejection.reason for rejection in validation.rejected_claims
    ]
    unique_rejection_reasons = list(dict.fromkeys(rejection_reasons))
    if not unique_rejection_reasons:
        return "traceguard_repair_rejected"
    if unique_rejection_reasons == ["missing_evidence_handle"]:
        return "missing_evidence_handle"
    if "missing_evidence_handle" in unique_rejection_reasons:
        return "mixed_traceguard_rejection_reasons_after_repair"
    return unique_rejection_reasons[0]


def _missing_handle_repair_fidelity_errors(
    *,
    original_parent_synthesis: dict[str, Any],
    repaired_parent_synthesis: dict[str, Any],
    allowed_evidence_manifest: tuple[TraceGuardEvidence, ...],
    child_records: list[dict[str, Any]],
    missing_evidence_handle_references: Iterable[Mapping[str, Any]] | None = None,
) -> list[str]:
    allowed_chunks_by_fact = {
        item.fact_id: item.chunk_id for item in allowed_evidence_manifest
    }
    child_chunks_by_fact = _child_evidence_handles_by_fact(child_records)
    allowed_patch_paths = _allowed_missing_handle_patch_paths(
        missing_evidence_handle_references
    )
    errors: list[str] = []
    errors.extend(
        _retained_fact_fidelity_errors(
            original_parent_synthesis=original_parent_synthesis,
            repaired_parent_synthesis=repaired_parent_synthesis,
        )
    )
    errors.extend(
        _parent_claim_text_fidelity_errors(
            original_parent_synthesis=original_parent_synthesis,
            repaired_parent_synthesis=repaired_parent_synthesis,
        )
    )
    _compare_missing_handle_patch(
        original_parent_synthesis,
        repaired_parent_synthesis,
        path="$",
        allowed_chunks_by_fact=allowed_chunks_by_fact,
        child_chunks_by_fact=child_chunks_by_fact,
        allowed_patch_paths=allowed_patch_paths,
        errors=errors,
    )
    return errors


def _allowed_missing_handle_patch_paths(
    missing_evidence_handle_references: Iterable[Mapping[str, Any]] | None,
) -> set[str] | None:
    if missing_evidence_handle_references is None:
        return None

    paths: set[str] = set()
    for reference in missing_evidence_handle_references:
        if reference.get("evidence_chunk_id_state") not in {"missing", "null"}:
            continue
        parent_path = reference.get("parent_path")
        if isinstance(parent_path, str) and parent_path:
            paths.add(f"$.{parent_path}.evidence_chunk_id")
    return paths


def _parent_claim_text_fidelity_errors(
    *,
    original_parent_synthesis: dict[str, Any],
    repaired_parent_synthesis: dict[str, Any],
) -> list[str]:
    original_claims = extract_parent_claims(original_parent_synthesis)
    repaired_claims = extract_parent_claims(repaired_parent_synthesis)
    errors: list[str] = []

    if len(original_claims) != len(repaired_claims):
        errors.append(
            "parent claim text/order changed claim count "
            f"from {len(original_claims)} to {len(repaired_claims)}"
        )

    for index, (original_claim, repaired_claim) in enumerate(
        zip(original_claims, repaired_claims, strict=False)
    ):
        original_position = (original_claim.surface, original_claim.fact_id)
        repaired_position = (repaired_claim.surface, repaired_claim.fact_id)
        if original_position != repaired_position:
            errors.append(
                f"parent claim[{index}] order changed from "
                f"{_parent_claim_label(original_claim)} to "
                f"{_parent_claim_label(repaired_claim)}"
            )
        if original_claim.text.encode("utf-8") != repaired_claim.text.encode("utf-8"):
            errors.append(
                f"parent claim[{index}] changed claim text bytes for "
                f"{_parent_claim_label(original_claim)}"
            )
    return errors


def _parent_claim_label(claim: Any) -> str:
    fact_id = claim.fact_id if claim.fact_id is not None else "<missing fact_id>"
    return f"{claim.surface} fact_id={fact_id}"


def _retained_fact_fidelity_errors(
    *,
    original_parent_synthesis: dict[str, Any],
    repaired_parent_synthesis: dict[str, Any],
) -> list[str]:
    original_retained_facts = _retained_facts_from_parent_synthesis(
        original_parent_synthesis
    )
    repaired_retained_facts = _retained_facts_from_parent_synthesis(
        repaired_parent_synthesis
    )
    if original_retained_facts is None or repaired_retained_facts is None:
        return []

    errors: list[str] = []
    for index, (original_fact, repaired_fact) in enumerate(
        zip(original_retained_facts, repaired_retained_facts, strict=False)
    ):
        original_identity = _retained_fact_signature(original_fact)
        repaired_identity = _retained_fact_signature(repaired_fact)
        if original_identity != repaired_identity:
            errors.append(
                f"$.result.retained_facts[{index}] changed retained fact identity "
                f"from {_retained_fact_label(original_fact)} to "
                f"{_retained_fact_label(repaired_fact)}"
            )
        if _retained_fact_text_changed(original_fact, repaired_fact):
            errors.append(
                f"$.result.retained_facts[{index}].text changed retained fact text "
                f"for {_retained_fact_label(original_fact)}"
            )

    original_counts = Counter(
        _retained_fact_signature(fact) for fact in original_retained_facts
    )
    repaired_counts = Counter(
        _retained_fact_signature(fact) for fact in repaired_retained_facts
    )
    labels = {
        _retained_fact_signature(fact): _retained_fact_label(fact)
        for fact in [*original_retained_facts, *repaired_retained_facts]
    }

    for signature, count in sorted((original_counts - repaired_counts).items()):
        errors.append(
            "$.result.retained_facts dropped retained fact "
            f"{labels[signature]} count={count}"
        )
    for signature, count in sorted((repaired_counts - original_counts).items()):
        errors.append(
            "$.result.retained_facts duplicated retained fact "
            f"{labels[signature]} count={count}"
        )
    return errors


def _retained_facts_from_parent_synthesis(
    parent_synthesis: Mapping[str, Any],
) -> list[Any] | None:
    result = parent_synthesis.get("result")
    if not isinstance(result, Mapping):
        return None
    retained_facts = result.get("retained_facts")
    if not isinstance(retained_facts, list):
        return None
    return retained_facts


def _retained_fact_signature(fact: Any) -> str:
    if isinstance(fact, Mapping):
        fact_id = fact.get("fact_id")
        if isinstance(fact_id, str) and fact_id:
            return f"fact_id:{fact_id}"
    return "json:" + json.dumps(
        _stable_json_value(_without_evidence_chunk_id(fact)),
        separators=(",", ":"),
    )


def _retained_fact_label(fact: Any) -> str:
    if isinstance(fact, Mapping):
        fact_id = fact.get("fact_id")
        if isinstance(fact_id, str) and fact_id:
            return fact_id
    return json.dumps(
        _stable_json_value(_without_evidence_chunk_id(fact)),
        separators=(",", ":"),
    )


def _retained_fact_text_changed(original_fact: Any, repaired_fact: Any) -> bool:
    if not isinstance(original_fact, Mapping) or "text" not in original_fact:
        return False
    if not isinstance(repaired_fact, Mapping):
        return True
    return repaired_fact.get("text") != original_fact.get("text")


def _without_evidence_chunk_id(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_evidence_chunk_id(item)
            for key, item in value.items()
            if key != "evidence_chunk_id"
        }
    if isinstance(value, list):
        return [_without_evidence_chunk_id(item) for item in value]
    return value


def _compare_missing_handle_patch(
    original: Any,
    repaired: Any,
    *,
    path: str,
    allowed_chunks_by_fact: dict[str, str],
    child_chunks_by_fact: dict[str, tuple[str, ...]],
    allowed_patch_paths: set[str] | None,
    errors: list[str],
) -> None:
    if isinstance(original, dict) and isinstance(repaired, dict):
        for key in original:
            if key not in repaired:
                errors.append(f"{path}.{key} was removed")
                continue
            if key == "evidence_chunk_id":
                _compare_evidence_chunk_id_patch(
                    original,
                    repaired,
                    path=f"{path}.{key}",
                    allowed_chunks_by_fact=allowed_chunks_by_fact,
                    child_chunks_by_fact=child_chunks_by_fact,
                    allowed_patch_paths=allowed_patch_paths,
                    errors=errors,
                )
                continue
            _compare_missing_handle_patch(
                original[key],
                repaired[key],
                path=f"{path}.{key}",
                allowed_chunks_by_fact=allowed_chunks_by_fact,
                child_chunks_by_fact=child_chunks_by_fact,
                allowed_patch_paths=allowed_patch_paths,
                errors=errors,
            )
        for key in repaired:
            if key in original:
                continue
            if key == "evidence_chunk_id":
                _compare_evidence_chunk_id_patch(
                    original,
                    repaired,
                    path=f"{path}.{key}",
                    allowed_chunks_by_fact=allowed_chunks_by_fact,
                    child_chunks_by_fact=child_chunks_by_fact,
                    allowed_patch_paths=allowed_patch_paths,
                    errors=errors,
                )
                continue
            errors.append(f"{path}.{key} was added")
        return

    if isinstance(original, list) and isinstance(repaired, list):
        if len(original) != len(repaired):
            errors.append(
                f"{path} length changed from {len(original)} to {len(repaired)}"
            )
            return
        for index, (original_item, repaired_item) in enumerate(
            zip(original, repaired, strict=True)
        ):
            _compare_missing_handle_patch(
                original_item,
                repaired_item,
                path=f"{path}[{index}]",
                allowed_chunks_by_fact=allowed_chunks_by_fact,
                child_chunks_by_fact=child_chunks_by_fact,
                allowed_patch_paths=allowed_patch_paths,
                errors=errors,
            )
        return

    if original != repaired:
        errors.append(f"{path} changed")


def _compare_evidence_chunk_id_patch(
    original_mapping: dict[str, Any],
    repaired_mapping: dict[str, Any],
    *,
    path: str,
    allowed_chunks_by_fact: dict[str, str],
    child_chunks_by_fact: dict[str, tuple[str, ...]],
    allowed_patch_paths: set[str] | None,
    errors: list[str],
) -> None:
    original_value = original_mapping.get("evidence_chunk_id")
    repaired_value = repaired_mapping.get("evidence_chunk_id")
    if original_value == repaired_value:
        return
    if allowed_patch_paths is not None and path not in allowed_patch_paths:
        errors.append(
            f"{path} changed outside the repairable missing_evidence_handle fields"
        )
        return
    if original_value is not None:
        errors.append(f"{path} changed an existing evidence handle")
        return
    if not isinstance(repaired_value, str) or not repaired_value:
        errors.append(f"{path} was not filled with a string handle")
        return

    fact_ids = _supported_fact_ids_from_mapping(original_mapping)
    if not fact_ids:
        errors.append(f"{path} was filled without a fact_id")
        return
    for fact_id in fact_ids:
        manifest_chunk_id = allowed_chunks_by_fact.get(fact_id)
        if repaired_value != manifest_chunk_id:
            errors.append(
                f"{path} used a handle outside the allowed evidence-handle set "
                f"for {fact_id}"
            )
            continue
        if repaired_value not in child_chunks_by_fact.get(fact_id, ()):
            errors.append(
                f"{path} used a handle outside the allowed evidence-handle set "
                f"for {fact_id}"
            )


def _build_runtime(family: RuntimeFamily) -> Any:
    model = os.environ.get(family.model_env_var, family.default_model_alias)
    if family.family_id == "hermes_glm":
        from ouroboros.orchestrator.hermes_runtime import HermesCliRuntime

        return HermesCliRuntime(model=model, cwd=ARTIFACT_ROOT)
    if family.family_id == "claude_code_opus47":
        from ouroboros.orchestrator.adapter import ClaudeAgentAdapter

        return ClaudeAgentAdapter(model=model, cwd=ARTIFACT_ROOT)
    if family.family_id == "codex_gpt55":
        from ouroboros.orchestrator.codex_cli_runtime import CodexCliRuntime

        return CodexCliRuntime(
            cli_path=shutil.which(family.command_name),
            model=model,
            cwd=ARTIFACT_ROOT,
        )
    msg = f"unsupported runtime family: {family.family_id}"
    raise ValueError(msg)


def _extend_runtime_timeouts(runtime: Any, *, timeout_seconds: float) -> None:
    for attr in ("_startup_output_timeout_seconds", "_stdout_idle_timeout_seconds"):
        if hasattr(runtime, attr):
            setattr(runtime, attr, timeout_seconds)


async def _execute_json_task(runtime: Any, *, prompt: str, timeout_seconds: float) -> dict[str, Any]:
    result = await asyncio.wait_for(
        runtime.execute_task_to_result(
            prompt=prompt,
            tools=[],
            system_prompt=(
                "Return exactly one JSON object. Do not include markdown fences, "
                "commentary, or unstructured prose."
            ),
        ),
        timeout=timeout_seconds,
    )
    if result.is_err:
        raise RuntimeError(str(result.error))
    return _extract_json_object(result.value.final_message)


def _selected_chunks(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    selected = set(fixture["selected_chunk_ids"])
    return [chunk for chunk in fixture["target"]["chunks"] if chunk["chunk_id"] in selected]


def _child_prompt(
    fixture: dict[str, Any],
    chunk: dict[str, Any],
    *,
    memory_priors: Iterable[MemoryPrior] = (),
) -> str:
    payload = {
        "task": "extract_child_evidence",
        "fixture_id": fixture["fixture_id"],
        "rules": [
            "Use only FACT lines present in this chunk.",
            "Return every visible fact_id with its exact evidence_chunk_id.",
            "Do not mention omitted chunks.",
        ],
        "required_schema": {
            "observed_facts": [
                {
                    "fact_id": "string",
                    "text": "string",
                    "evidence_chunk_id": "string",
                }
            ],
            "residual_gaps": ["string"],
        },
        "chunk": chunk,
    }
    _attach_memory_priors(payload, memory_priors, task="extract_child_evidence")
    return json.dumps(payload, indent=2, sort_keys=True)


def _parent_prompt(
    fixture: dict[str, Any],
    child_records: list[dict[str, Any]],
    *,
    memory_priors: Iterable[MemoryPrior] = (),
) -> str:
    payload = {
        "task": "synthesize_parent_answer_from_child_evidence",
        "fixture_id": fixture["fixture_id"],
        "rules": [
            "Use only observed_facts returned by child calls.",
            "Every retained_facts entry must include fact_id and evidence_chunk_id.",
            "Do not invent or cite omitted fact ids.",
        ],
        "required_schema": {
            "mode": "rlm_forge_parent_synthesis",
            "verdict": "pass|partial|fail",
            "confidence": "number",
            "result": {
                "summary": "string",
                "retained_facts": [
                    {
                        "fact_id": "string",
                        "text": "string",
                        "evidence_chunk_id": "string",
                    }
                ],
            },
            "evidence_references": [
                {
                    "chunk_id": "string",
                    "supports_fact_ids": ["string"],
                    "quoted_evidence": "string",
                }
            ],
            "residual_gaps": ["string"],
        },
        "child_records": child_records,
    }
    _attach_memory_priors(
        payload,
        memory_priors,
        task="synthesize_parent_answer_from_child_evidence",
    )
    return json.dumps(payload, indent=2, sort_keys=True)


def _attach_memory_priors(
    payload: dict[str, Any],
    memory_priors: Iterable[MemoryPrior],
    *,
    task: str,
) -> None:
    priors = [
        prior.to_prompt_dict()
        for prior in _memory_priors_for_task(memory_priors, task)
    ]
    if priors:
        payload["memory_priors"] = {
            "scope": "operational_policy_only",
            "rules": [
                "Memory is not evidence.",
                "Do not use memory to support factual claims.",
                "Use memory only for schema, routing, or retry policy.",
            ],
            "priors": priors,
        }


def _memory_priors_for_task(
    memory_priors: Iterable[MemoryPrior],
    task: str,
) -> tuple[MemoryPrior, ...]:
    return tuple(prior for prior in memory_priors if prior.task == task)


def build_parent_synthesis_retry_prompt(
    *,
    fixture: dict[str, Any],
    child_records: list[dict[str, Any]],
    repaired_parent_synthesis: dict[str, Any],
    traceguard_repair: dict[str, Any],
) -> str:
    """Build the deterministic same-runtime parent synthesis retry prompt."""
    payload = json.loads(_parent_prompt(fixture, child_records))
    payload["retry"] = {
        "attempt": 1,
        "trigger": "traceguard_missing_evidence_handle_repair_accept",
        "rules": [
            "Retry parent synthesis exactly once after the accepted TraceGuard repair.",
            "Use repaired_parent_synthesis as the evidence-contract template.",
            "Preserve retained fact identities, answer text, and claim text from repaired_parent_synthesis.",
            "Do not add facts, remove facts, or cite omitted fact ids.",
        ],
        "repair_accept": traceguard_repair["repair_accept"],
        "after_validation": traceguard_repair["after_validation"],
        "missing_evidence_handle_references": traceguard_repair[
            "missing_evidence_handle_references"
        ],
        "repaired_parent_synthesis": repaired_parent_synthesis,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_traceguard_repair_prompt(
    *,
    rejected_claim: TraceGuardRejection,
    allowed_evidence_manifest: Iterable[TraceGuardEvidence | Mapping[str, Any]],
    original_parent_synthesis: Mapping[str, Any],
    child_records: Iterable[Mapping[str, Any]],
) -> str:
    """Build the deterministic prompt for one missing evidence-handle repair."""
    return _serialize_traceguard_repair_prompt_payload(
        _traceguard_repair_prompt_payload(
            TraceGuardRepairPromptInput.from_contract_inputs(
                rejected_claim=rejected_claim,
                allowed_evidence_manifest=allowed_evidence_manifest,
                original_parent_synthesis=original_parent_synthesis,
                child_records=child_records,
            )
        )
    )


def _traceguard_repair_prompt_payload(
    repair_input: TraceGuardRepairPromptInput | None = None,
    *,
    rejected_claim: TraceGuardRejection | None = None,
    normalized_allowed_evidence_manifest: Iterable[Mapping[str, Any]] | None = None,
    original_parent_synthesis: Mapping[str, Any] | None = None,
    normalized_child_records: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the repair prompt payload from the deterministic input model."""
    if repair_input is None:
        if (
            rejected_claim is None
            or normalized_allowed_evidence_manifest is None
            or original_parent_synthesis is None
            or normalized_child_records is None
        ):
            msg = "repair_input or all normalized repair contract inputs are required"
            raise TypeError(msg)
        repair_input = TraceGuardRepairPromptInput(
            rejected_claim=_stable_json_value(
                rejected_claim.to_dict(),
                exclude_nondeterministic_keys=True,
            ),
            allowed_evidence_manifest=normalize_repair_prompt_evidence_manifest(
                normalized_allowed_evidence_manifest
            ),
            original_parent_synthesis=normalize_repair_prompt_parent_synthesis(
                original_parent_synthesis
            ),
            child_records=normalize_repair_prompt_child_records(
                normalized_child_records
            ),
        )
    repair_input = _canonicalize_traceguard_repair_prompt_input(repair_input)
    return {
        "task": "repair_missing_evidence_handle",
        "rules": [
            "Use only the allowed_evidence_manifest and child_records.",
            "Patch only null or missing evidence_chunk_id fields.",
            "Do not add facts, remove facts, rewrite answer text, change claim text, or change fact_id values.",
            "Return the complete parent synthesis JSON object with only the handle patch applied.",
        ],
        "repair_prompt_sections": _traceguard_repair_prompt_sections(repair_input),
        **repair_input.to_dict(),
    }


def _canonicalize_traceguard_repair_prompt_input(
    repair_input: TraceGuardRepairPromptInput,
) -> TraceGuardRepairPromptInput:
    return TraceGuardRepairPromptInput(
        rejected_claim=_stable_json_value(
            repair_input.rejected_claim,
            exclude_nondeterministic_keys=True,
        ),
        allowed_evidence_manifest=normalize_repair_prompt_evidence_manifest(
            repair_input.allowed_evidence_manifest
        ),
        original_parent_synthesis=normalize_repair_prompt_parent_synthesis(
            repair_input.original_parent_synthesis
        ),
        child_records=normalize_repair_prompt_child_records(repair_input.child_records),
    )


def _traceguard_repair_prompt_sections(
    repair_input: TraceGuardRepairPromptInput,
) -> list[dict[str, Any]]:
    """Render stable labeled prompt sections for each repair input."""
    values = repair_input.to_dict()
    return [
        {
            "label": label,
            "input_key": input_key,
            "content": values[input_key],
        }
        for input_key, label in TRACEGUARD_REPAIR_PROMPT_INPUT_SECTIONS
    ]


def _serialize_traceguard_repair_prompt_payload(payload: Mapping[str, Any]) -> str:
    """Emit stable repair JSON independent of mapping insertion order."""
    return json.dumps(
        _stable_json_value(payload, exclude_nondeterministic_keys=True),
        indent=2,
    )


def _stable_json_value(
    value: Any,
    *,
    exclude_nondeterministic_keys: bool = False,
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _stable_json_value(
                value[key],
                exclude_nondeterministic_keys=exclude_nondeterministic_keys,
            )
            for key in sorted(value, key=lambda item: str(item))
            if not (
                exclude_nondeterministic_keys
                and _is_nondeterministic_repair_prompt_key(key)
            )
        }
    if isinstance(value, (list, tuple)):
        return [
            _stable_json_value(
                item,
                exclude_nondeterministic_keys=exclude_nondeterministic_keys,
            )
            for item in value
        ]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (
                _stable_json_value(
                    item,
                    exclude_nondeterministic_keys=exclude_nondeterministic_keys,
                )
                for item in value
            ),
            key=_stable_json_sort_token,
        )
    return value


def _is_nondeterministic_repair_prompt_key(key: Any) -> bool:
    normalized = str(key).replace("-", "_").lower()
    compact = normalized.replace("_", "")
    return (
        normalized in NONDETERMINISTIC_REPAIR_PROMPT_KEYS
        or compact in NONDETERMINISTIC_REPAIR_PROMPT_COMPACT_KEYS
        or any(
            normalized.endswith(suffix)
            for suffix in NONDETERMINISTIC_REPAIR_PROMPT_KEY_SUFFIXES
        )
        or any(
            compact.endswith(suffix)
            for suffix in NONDETERMINISTIC_REPAIR_PROMPT_COMPACT_KEY_SUFFIXES
        )
    )


def _stable_json_sort_token(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise
        depth = 0
        end = -1
        for index, char in enumerate(candidate[start:], start=start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end < 0:
            raise
        parsed = json.loads(candidate[start:end])
    if not isinstance(parsed, dict):
        msg = "runtime output JSON must be an object"
        raise ValueError(msg)
    return parsed


def _live_selected_coverage_pass(
    fixture: dict[str, Any],
    child_records: list[dict[str, Any]],
) -> bool:
    expected = set(fixture["selected_chunk_ids"])
    observed = {record["chunk_id"] for record in child_records}
    return expected == observed


def _live_success_cell(
    family: RuntimeFamily,
    fixture: dict[str, Any],
    artifact: dict[str, Any],
    latency_seconds: float,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_category": fixture["fixture_category"],
        "family_id": family.family_id,
        "contract_variant": PRIMARY_CONTRACT_VARIANT,
        "primary_cell": True,
        "completed": artifact["completed"],
        "status": artifact["status"],
        "failure_classification": artifact["failure_classification"],
        "mandatory_contract_pass": artifact["mandatory_contract_pass"],
        "latency_seconds": latency_seconds,
        "artifact": artifact,
    }


def _live_failure_cell(
    family: RuntimeFamily,
    fixture: dict[str, Any],
    failure_classification: str,
    message: str,
    *,
    latency_seconds: float | None = None,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture["fixture_id"],
        "fixture_category": fixture["fixture_category"],
        "family_id": family.family_id,
        "contract_variant": PRIMARY_CONTRACT_VARIANT,
        "primary_cell": True,
        "completed": False,
        "status": failure_classification,
        "failure_classification": failure_classification,
        "mandatory_contract_pass": None,
        "latency_seconds": latency_seconds,
        "error": message[:500],
    }


def _interpretation(result: dict[str, Any]) -> str:
    if result["run_mode"] == "dry_plan":
        return (
            "This is a plan only: it defines the shared fixtures, runtime families, "
            "contract variants, and planned primary cells. It makes no live-model "
            "quality or portability claim."
        )
    if result["run_mode"] == "contracts_only":
        passed = result["primary_contract_pass_count"]
        total = result["deterministic_primary_contract_check_count"]
        return (
            f"Contracts-only mode validates fixture completeness and TraceGuard "
            f"safe/unsafe verdicts for {passed}/{total} primary cells without "
            "calling providers. It is a precondition for the live matrix, not the "
            "live portability result itself."
        )
    if result["run_mode"] == "live_smoke":
        status = result["aggregate_result"]["status"]
        return (
            f"Live smoke mode executes one RLM-FORGE+TraceGuard fixture across "
            f"the claimed families. Aggregate status: `{status}`. This is an "
            "adapter/auth smoke test before the full 8-fixture matrix."
        )
    if result["run_mode"] == "live_primary":
        status = result["aggregate_result"]["status"]
        completed = result["cell_count"]
        planned = result["planned_cell_count"]
        return (
            f"Live primary mode executes the RLM-FORGE+TraceGuard contract for "
            f"{completed}/{planned} planned primary cells. Aggregate status: "
            f"`{status}`. A pass supports the runtime portability claim; it does "
            "not evaluate secondary baselines or SOTA model quality."
        )
    return "No interpretation available."


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _select_families(family_csv: str) -> tuple[RuntimeFamily, ...]:
    if family_csv.strip() == "all":
        return RUNTIME_FAMILIES
    requested = {item.strip() for item in family_csv.split(",") if item.strip()}
    known = {family.family_id: family for family in RUNTIME_FAMILIES}
    unknown = sorted(requested - set(known))
    if unknown:
        msg = f"unknown runtime families: {unknown}"
        raise ValueError(msg)
    selected = tuple(family for family in RUNTIME_FAMILIES if family.family_id in requested)
    if not selected:
        msg = "at least one runtime family must be selected"
        raise ValueError(msg)
    return selected


def _build_memory_context(*, mode: MemoryMode, store_path: Path) -> MemoryContext:
    if mode == "off":
        return MemoryContext()
    return MemoryContext(mode=mode, backend=LocalJsonMemoryBackend(store_path))


async def _async_main(args: argparse.Namespace) -> int:
    families = _select_families(args.families)
    memory_context = _build_memory_context(
        mode=args.memory_mode,
        store_path=args.memory_store,
    )
    if args.mode == "dry-plan":
        result = build_dry_plan(fixture_count=args.fixtures, families=families)
    elif args.mode == "contracts-only":
        result = run_contracts_only(fixture_count=args.fixtures, families=families)
    elif args.mode == "live-smoke":
        result = await run_live_smoke(
            fixture_count=args.fixtures,
            families=families,
            timeout_seconds=args.timeout_seconds,
            memory_context=memory_context,
        )
    elif args.mode == "live-primary":
        result = await run_live_primary(
            fixture_count=args.fixtures,
            families=families,
            timeout_seconds=args.timeout_seconds,
            checkpoint_dir=args.output_dir,
            checkpoint_prefix=args.output_prefix,
            memory_context=memory_context,
        )
    else:
        msg = f"unsupported mode: {args.mode}"
        raise ValueError(msg)

    json_path, md_path = write_outputs(
        result,
        output_dir=args.output_dir,
        output_prefix=args.output_prefix,
    )
    print(
        f"{result['run_mode']}: json={json_path}; markdown={md_path}; "
        f"planned_cells={result['planned_cell_count']}"
    )
    if "aggregate_result" in result:
        print(f"aggregate_status={result['aggregate_result']['status']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("dry-plan", "contracts-only", "live-smoke", "live-primary"),
        default="contracts-only",
        help="Execution mode. live-smoke and live-primary call configured providers.",
    )
    parser.add_argument(
        "--fixtures",
        type=int,
        choices=(8, 12),
        default=8,
        help="Number of primary fixtures to include.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory for JSON and Markdown outputs.",
    )
    parser.add_argument(
        "--output-prefix",
        default=DEFAULT_OUTPUT_PREFIX,
        help="Output filename prefix.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
        help="Per runtime call timeout for live provider modes.",
    )
    parser.add_argument(
        "--families",
        default="all",
        help="Comma-separated family ids to run, or 'all'.",
    )
    parser.add_argument(
        "--memory-mode",
        choices=("off", "read", "write", "read-write"),
        default="off",
        help="Operational memory mode for live provider runs.",
    )
    parser.add_argument(
        "--memory-store",
        type=Path,
        default=Path(".rlm-forge-memory.jsonl"),
        help="Local JSONL operational memory store.",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
