"""Evidence-gated parent synthesis validation for Hermes-backed RLM runs.

TraceGuard is intentionally small and deterministic. It validates a parent
synthesis JSON object against the evidence handles accepted from child
sub-calls. The goal is not to judge semantic truth in the open world; it is to
enforce a concrete RLM contract: a parent may only claim facts that a retained
child evidence handle explicitly supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLAIM_FACT_KEYS = ("fact_id", "supports_fact_id")
CLAIM_FACT_LIST_KEYS = ("fact_ids", "supports_fact_ids", "supported_fact_ids")
CHUNK_KEYS = ("chunk_id", "evidence_chunk_id", "source_chunk_id")


@dataclass(frozen=True, slots=True)
class TraceGuardEvidence:
    """A child evidence handle accepted by the outer scaffold."""

    fact_id: str
    chunk_id: str
    text: str
    child_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "child_call_id": self.child_call_id,
        }


@dataclass(frozen=True, slots=True)
class TraceGuardClaim:
    """A parent-synthesis fact claim extracted from structured claim surfaces."""

    fact_id: str | None
    chunk_id: str | None
    surface: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "chunk_id": self.chunk_id,
            "surface": self.surface,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class TraceGuardRejection:
    """A structured reason why a parent claim was rejected."""

    reason: str
    claim: TraceGuardClaim
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "claim": self.claim.to_dict(),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class TraceGuardResult:
    """TraceGuard validation result for one parent synthesis."""

    accepted: bool
    accepted_claims: tuple[TraceGuardClaim, ...]
    rejected_claims: tuple[TraceGuardRejection, ...]
    allowed_fact_ids: tuple[str, ...]
    allowed_chunk_ids: tuple[str, ...]

    @property
    def unsupported_claim_rate(self) -> float:
        total = len(self.accepted_claims) + len(self.rejected_claims)
        if total == 0:
            return 0.0
        return round(len(self.rejected_claims) / total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "unsupported_claim_rate": self.unsupported_claim_rate,
            "accepted_claims": [claim.to_dict() for claim in self.accepted_claims],
            "rejected_claims": [
                rejection.to_dict() for rejection in self.rejected_claims
            ],
            "allowed_fact_ids": list(self.allowed_fact_ids),
            "allowed_chunk_ids": list(self.allowed_chunk_ids),
        }


def build_manifest_from_fixture(fixture: dict[str, Any]) -> tuple[TraceGuardEvidence, ...]:
    """Create accepted child evidence handles from a truncation fixture."""
    evidence: list[TraceGuardEvidence] = []
    for index, fact in enumerate(fixture.get("expected_retained_facts", []), start=1):
        if not isinstance(fact, dict):
            continue
        fact_id = fact.get("fact_id")
        chunk_id = fact.get("chunk_id")
        text = fact.get("text")
        if isinstance(fact_id, str) and isinstance(chunk_id, str) and isinstance(text, str):
            evidence.append(
                TraceGuardEvidence(
                    fact_id=fact_id,
                    chunk_id=chunk_id,
                    text=text,
                    child_call_id=f"child_{index:04d}",
                )
            )
    return tuple(evidence)


def validate_parent_synthesis(
    *,
    evidence_manifest: tuple[TraceGuardEvidence, ...],
    parent_synthesis: dict[str, Any],
) -> TraceGuardResult:
    """Validate parent synthesis claims against accepted child evidence."""
    allowed_by_fact = {item.fact_id: item for item in evidence_manifest}
    allowed_fact_ids = tuple(allowed_by_fact)
    allowed_chunk_ids = tuple(dict.fromkeys(item.chunk_id for item in evidence_manifest))

    accepted: list[TraceGuardClaim] = []
    rejected: list[TraceGuardRejection] = []
    for claim in extract_parent_claims(parent_synthesis):
        if claim.fact_id is None:
            rejected.append(
                TraceGuardRejection(
                    reason="chunk_handle_without_fact",
                    claim=claim,
                    detail=(
                        "The parent cited a chunk handle but did not identify a "
                        "supported fact."
                    ),
                )
            )
            continue

        evidence = allowed_by_fact.get(claim.fact_id)
        if evidence is None:
            rejected.append(
                TraceGuardRejection(
                    reason="unsupported_fact_id",
                    claim=claim,
                    detail=(
                        f"{claim.fact_id} is not present in the accepted child "
                        "evidence manifest."
                    ),
                )
            )
            continue

        if claim.chunk_id is None:
            rejected.append(
                TraceGuardRejection(
                    reason="missing_evidence_handle",
                    claim=claim,
                    detail=f"{claim.fact_id} lacks a chunk/evidence handle.",
                )
            )
            continue

        if claim.chunk_id != evidence.chunk_id:
            rejected.append(
                TraceGuardRejection(
                    reason="evidence_handle_mismatch",
                    claim=claim,
                    detail=(
                        f"{claim.fact_id} must cite {evidence.chunk_id}, "
                        f"not {claim.chunk_id}."
                    ),
                )
            )
            continue

        accepted.append(claim)

    return TraceGuardResult(
        accepted=not rejected,
        accepted_claims=tuple(accepted),
        rejected_claims=tuple(rejected),
        allowed_fact_ids=allowed_fact_ids,
        allowed_chunk_ids=allowed_chunk_ids,
    )


def extract_parent_claims(parent_synthesis: dict[str, Any]) -> tuple[TraceGuardClaim, ...]:
    """Extract structured, claim-bearing entries from a parent synthesis object."""
    claims: list[TraceGuardClaim] = []
    result = parent_synthesis.get("result")
    if isinstance(result, dict):
        for key in (
            "retained_facts",
            "observed_facts",
            "facts",
            "retained_evidence",
            "observed_evidence",
        ):
            value = result.get(key)
            claims.extend(_claims_from_surface(value, f"result.{key}"))
        if isinstance(result.get("fact_id"), str):
            claims.extend(_claims_from_surface(result, "result"))

    claims.extend(
        _claims_from_surface(parent_synthesis.get("evidence_references"), "evidence_references")
    )
    return tuple(claims)


def _claims_from_surface(value: Any, surface: str) -> list[TraceGuardClaim]:
    if isinstance(value, dict):
        return _claims_from_mapping(value, surface)
    if isinstance(value, list):
        claims: list[TraceGuardClaim] = []
        for item in value:
            if isinstance(item, dict):
                claims.extend(_claims_from_mapping(item, surface))
        return claims
    return []


def _claims_from_mapping(value: dict[str, Any], surface: str) -> list[TraceGuardClaim]:
    fact_ids = _supported_fact_ids(value)
    chunk_id = _chunk_id(value)
    text = _claim_text(value)
    if not fact_ids and chunk_id:
        return [
            TraceGuardClaim(
                fact_id=None,
                chunk_id=chunk_id,
                surface=surface,
                text=text,
            )
        ]
    return [
        TraceGuardClaim(
            fact_id=fact_id,
            chunk_id=chunk_id,
            surface=surface,
            text=text,
        )
        for fact_id in fact_ids
    ]


def _supported_fact_ids(value: dict[str, Any]) -> tuple[str, ...]:
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


def _chunk_id(value: dict[str, Any]) -> str | None:
    for key in CHUNK_KEYS:
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
    return None


def _claim_text(value: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("quoted_evidence", "text", "statement", "claim", "summary"):
        item = value.get(key)
        if isinstance(item, str) and item:
            parts.append(item)
    return "\n".join(parts)
