"""Operational memory priors for RLM-FORGE runs.

Memory in RLM-FORGE is deliberately not evidence. It stores narrow operational
signals that may influence schemas, retry policy, or routing. It must never
store fixture answers, fact identifiers, chunk identifiers, quoted evidence, or
parent/child factual outputs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Literal


MemoryMode = Literal["off", "read", "write", "read-write"]

READ_MODES: frozenset[MemoryMode] = frozenset({"read", "read-write"})
WRITE_MODES: frozenset[MemoryMode] = frozenset({"write", "read-write"})

ALLOWED_PRIOR_KINDS = frozenset(
    {
        "provider_schema_stability",
        "missing_evidence_handle_seen",
        "repair_strategy_succeeded",
        "repair_strategy_failed",
        "latency_bucket",
        "schema_hint_needed",
    }
)
ALLOWED_TASKS = frozenset(
    {
        "extract_child_evidence",
        "synthesize_parent_answer_from_child_evidence",
        "repair_missing_evidence_handle",
        "parent_synthesis_retry",
    }
)
ALLOWED_RECOMMENDATIONS = frozenset(
    {
        "require_fact_id_and_evidence_chunk_id",
        "preserve_child_fact_identity",
        "prefer_strict_json_schema",
        "retry_once_after_missing_handle_repair",
        "route_synthesis_to_schema_stable_provider",
        "avoid_chunk_only_citations",
        "record_latency_without_quality_claim",
    }
)
ALLOWED_RECORD_FIELDS = frozenset(
    {
        "kind",
        "task",
        "recommendation",
        "family_id",
        "fixture_category",
        "outcome",
        "confidence",
        "created_at",
    }
)

_FORBIDDEN_PATTERNS = (
    re.compile(r"\bFACT\s*:", re.IGNORECASE),
    re.compile(r"\b(?:LP|LC)-\d{2,}-\d{2,}\b"),
    re.compile(r"\b(?:LP|LC)-\d{3,}\b"),
    re.compile(r"\blive_portability/[^ \n\t]+"),
    re.compile(r"\b(?:chunk|evidence)_chunk_id\b.*:", re.IGNORECASE),
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:traceguard|evidence|validation)", re.IGNORECASE),
    re.compile(r"bypass\s+(?:traceguard|evidence|validation)", re.IGNORECASE),
    re.compile(r"treat\s+memory\s+as\s+evidence", re.IGNORECASE),
    re.compile(r"claim\s+(?:LP|LC)-", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class MemoryPrior:
    """A sanitized operational prior allowed into prompts."""

    kind: str
    task: str
    recommendation: str
    family_id: str | None = None
    fixture_category: str | None = None
    confidence: float = 1.0

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "task": self.task,
            "recommendation": self.recommendation,
            "family_id": self.family_id,
            "fixture_category": self.fixture_category,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class MemoryObservation:
    """A write candidate for operational memory."""

    kind: str
    task: str
    recommendation: str
    family_id: str
    fixture_category: str
    outcome: str
    confidence: float = 1.0
    created_at: str | None = None

    def to_record(self) -> dict[str, Any]:
        created_at = self.created_at or datetime.now(UTC).isoformat()
        return {**asdict(self), "created_at": created_at}


@dataclass(frozen=True, slots=True)
class MemoryCandidateRejection:
    """A redacted memory rejection for audit artifacts."""

    reason: str
    source: str
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "source": self.source, "field": self.field}


@dataclass(frozen=True, slots=True)
class MemoryRecallResult:
    priors: tuple[MemoryPrior, ...]
    rejected_candidates: tuple[MemoryCandidateRejection, ...]

    def to_trace(self) -> dict[str, Any]:
        return {
            "recalled_priors": [prior.to_prompt_dict() for prior in self.priors],
            "rejected_memory_candidates": [
                rejection.to_dict() for rejection in self.rejected_candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    stored_observations: tuple[dict[str, Any], ...]
    rejected_candidates: tuple[MemoryCandidateRejection, ...]

    def to_trace(self) -> dict[str, Any]:
        return {
            "stored_observations": list(self.stored_observations),
            "rejected_memory_candidates": [
                rejection.to_dict() for rejection in self.rejected_candidates
            ],
            "contamination_guard": {
                "passed": not self.rejected_candidates,
                "rejected_count": len(self.rejected_candidates),
            },
        }


class MemoryBackend:
    """Backend interface for operational memory."""

    def recall(
        self,
        *,
        family_id: str,
        fixture_category: str,
        tasks: Iterable[str],
    ) -> MemoryRecallResult:
        raise NotImplementedError

    def store(self, observations: Iterable[MemoryObservation]) -> MemoryWriteResult:
        raise NotImplementedError


class NoopMemoryBackend(MemoryBackend):
    def recall(
        self,
        *,
        family_id: str,
        fixture_category: str,
        tasks: Iterable[str],
    ) -> MemoryRecallResult:
        return MemoryRecallResult(priors=(), rejected_candidates=())

    def store(self, observations: Iterable[MemoryObservation]) -> MemoryWriteResult:
        return MemoryWriteResult(stored_observations=(), rejected_candidates=())


class LocalJsonMemoryBackend(MemoryBackend):
    """Append-only local JSONL operational memory."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def recall(
        self,
        *,
        family_id: str,
        fixture_category: str,
        tasks: Iterable[str],
    ) -> MemoryRecallResult:
        allowed_tasks = set(tasks)
        priors: list[MemoryPrior] = []
        rejected: list[MemoryCandidateRejection] = []
        if not self.path.exists():
            return MemoryRecallResult(priors=(), rejected_candidates=())

        for line_number, line in enumerate(self.path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            source = f"{self.path.name}:{line_number}"
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                rejected.append(MemoryCandidateRejection("invalid_json", source))
                continue
            prior, rejection = prior_from_record(
                record,
                source=source,
                family_id=family_id,
                fixture_category=fixture_category,
                allowed_tasks=allowed_tasks,
            )
            if rejection is not None:
                rejected.append(rejection)
                continue
            if prior is not None:
                priors.append(prior)

        return MemoryRecallResult(
            priors=tuple(sorted(priors, key=_prior_sort_key)),
            rejected_candidates=tuple(rejected),
        )

    def store(self, observations: Iterable[MemoryObservation]) -> MemoryWriteResult:
        stored: list[dict[str, Any]] = []
        rejected: list[MemoryCandidateRejection] = []
        for index, observation in enumerate(observations):
            record = observation.to_record()
            rejection = validate_memory_record(record, source=f"write:{index}")
            if rejection is not None:
                rejected.append(rejection)
                continue
            stored.append(record)

        if stored:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                for record in stored:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")

        return MemoryWriteResult(
            stored_observations=tuple(stored),
            rejected_candidates=tuple(rejected),
        )


def prior_from_record(
    record: Any,
    *,
    source: str,
    family_id: str,
    fixture_category: str,
    allowed_tasks: set[str],
) -> tuple[MemoryPrior | None, MemoryCandidateRejection | None]:
    if not isinstance(record, dict):
        return None, MemoryCandidateRejection("record_not_object", source)

    rejection = validate_memory_record(record, source=source)
    if rejection is not None:
        return None, rejection

    task = record["task"]
    if task not in allowed_tasks:
        return None, None
    record_family = record.get("family_id")
    record_category = record.get("fixture_category")
    if record_family not in {None, family_id}:
        return None, None
    if record_category not in {None, fixture_category}:
        return None, None

    return (
        MemoryPrior(
            kind=record["kind"],
            task=task,
            recommendation=record["recommendation"],
            family_id=record_family,
            fixture_category=record_category,
            confidence=_confidence(record.get("confidence")),
        ),
        None,
    )


def validate_memory_record(
    record: dict[str, Any],
    *,
    source: str,
) -> MemoryCandidateRejection | None:
    extra_fields = set(record) - ALLOWED_RECORD_FIELDS
    if extra_fields:
        return MemoryCandidateRejection(
            "field_not_allowed",
            source,
            sorted(extra_fields)[0],
        )
    for field in ("kind", "task", "recommendation"):
        if not isinstance(record.get(field), str):
            return MemoryCandidateRejection("missing_required_field", source, field)
    if record["kind"] not in ALLOWED_PRIOR_KINDS:
        return MemoryCandidateRejection("kind_not_allowed", source, "kind")
    if record["task"] not in ALLOWED_TASKS:
        return MemoryCandidateRejection("task_not_allowed", source, "task")
    if record["recommendation"] not in ALLOWED_RECOMMENDATIONS:
        return MemoryCandidateRejection(
            "recommendation_not_allowed",
            source,
            "recommendation",
        )

    for field in (
        "kind",
        "task",
        "recommendation",
        "family_id",
        "fixture_category",
        "outcome",
    ):
        value = record.get(field)
        if isinstance(value, str):
            text_rejection = _reject_forbidden_text(value, source=source, field=field)
            if text_rejection is not None:
                return text_rejection
    return None


def build_memory_observations_from_cell(
    *,
    family_id: str,
    fixture_category: str,
    traceguard_accepted: bool,
    traceguard_repair: dict[str, Any],
    latency_seconds: float | None = None,
) -> tuple[MemoryObservation, ...]:
    observations: list[MemoryObservation] = []
    if traceguard_repair.get("initial_accept") is False:
        observations.append(
            MemoryObservation(
                kind="missing_evidence_handle_seen",
                task="synthesize_parent_answer_from_child_evidence",
                recommendation="require_fact_id_and_evidence_chunk_id",
                family_id=family_id,
                fixture_category=fixture_category,
                outcome=str(traceguard_repair.get("failure_reason") or "rejected"),
            )
        )
    if traceguard_repair.get("repair_accept") is True:
        observations.append(
            MemoryObservation(
                kind="repair_strategy_succeeded",
                task="parent_synthesis_retry",
                recommendation="retry_once_after_missing_handle_repair",
                family_id=family_id,
                fixture_category=fixture_category,
                outcome="repair_accept",
            )
        )
    elif traceguard_repair.get("repair_accept") is False:
        observations.append(
            MemoryObservation(
                kind="repair_strategy_failed",
                task="repair_missing_evidence_handle",
                recommendation="prefer_strict_json_schema",
                family_id=family_id,
                fixture_category=fixture_category,
                outcome=str(
                    traceguard_repair.get("repair_failure_reason")
                    or traceguard_repair.get("failure_reason")
                    or "repair_rejected"
                ),
            )
        )
    if traceguard_accepted:
        observations.append(
            MemoryObservation(
                kind="provider_schema_stability",
                task="synthesize_parent_answer_from_child_evidence",
                recommendation="preserve_child_fact_identity",
                family_id=family_id,
                fixture_category=fixture_category,
                outcome="traceguard_accept",
            )
        )
    if latency_seconds is not None:
        observations.append(
            MemoryObservation(
                kind="latency_bucket",
                task="synthesize_parent_answer_from_child_evidence",
                recommendation="record_latency_without_quality_claim",
                family_id=family_id,
                fixture_category=fixture_category,
                outcome=_latency_bucket(latency_seconds),
            )
        )
    return tuple(observations)


def _reject_forbidden_text(
    text: str,
    *,
    source: str,
    field: str,
) -> MemoryCandidateRejection | None:
    for pattern in (*_FORBIDDEN_PATTERNS, *_INJECTION_PATTERNS):
        if pattern.search(text):
            return MemoryCandidateRejection("forbidden_or_injection_text", source, field)
    return None


def _confidence(value: Any) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    return 1.0


def _prior_sort_key(prior: MemoryPrior) -> tuple[str, str, str, str, str]:
    return (
        prior.task,
        prior.kind,
        prior.family_id or "",
        prior.fixture_category or "",
        prior.recommendation,
    )


def _latency_bucket(latency_seconds: float) -> str:
    if latency_seconds < 60:
        return "latency_lt_60s"
    if latency_seconds < 180:
        return "latency_60s_to_180s"
    return "latency_gte_180s"
