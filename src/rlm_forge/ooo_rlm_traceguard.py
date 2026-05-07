"""TraceGuard integration for the dependency ``ouroboros rlm`` CLI.

The upstream RLM command emits a parent Hermes synthesis after child chunk
calls complete. Its stock parent schema cites ``child_result_id`` handles
rather than TraceGuard's ``fact_id`` handles, so this module provides a small
adapter:

child_result_id + child chunk -> TraceGuardEvidence
parent supported_by_child_result_ids -> TraceGuard claim references

Memory or other unsupported answer facts remain outside that fresh child
manifest and are rejected by the existing deterministic TraceGuard validator.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

from rlm_forge.traceguard import TraceGuardEvidence
from rlm_forge.traceguard import TraceGuardResult
from rlm_forge.traceguard import validate_parent_synthesis


SUPPORTED_CHILD_KEYS = (
    "supported_by_child_result_ids",
    "supporting_child_result_ids",
    "child_result_ids",
)


@dataclass(frozen=True, slots=True)
class OOORLMTraceGuardGate:
    """Result of the in-process TraceGuard gate for one ``ooo rlm`` run."""

    status: str
    validation: TraceGuardResult | None
    manifest: tuple[TraceGuardEvidence, ...]
    normalized_parent_synthesis: dict[str, Any]
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.validation.accepted if self.validation is not None else False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "accepted": self.accepted,
            "reason": self.reason,
            "manifest": [item.to_dict() for item in self.manifest],
            "normalized_parent_synthesis": self.normalized_parent_synthesis,
            "validation": self.validation.to_dict() if self.validation is not None else None,
        }


def validate_ooo_rlm_result(result: Any) -> OOORLMTraceGuardGate:
    """Validate a completed dependency ``ouroboros rlm`` result in-process."""
    atomic_execution = getattr(result, "atomic_execution", None)
    if atomic_execution is None:
        return _not_applicable("result has no atomic_execution")

    parent_subcall = getattr(atomic_execution, "hermes_subcall", None)
    parent_state = getattr(atomic_execution, "parent_execution_state", None)
    if parent_subcall is None or parent_state is None:
        return _not_applicable("result has no parent synthesis state")

    parent_output = _json_mapping_or_none(getattr(parent_subcall, "completion", ""))
    if parent_output is None:
        return _rejected("parent synthesis completion is not a JSON object")

    manifest = _manifest_from_parent_state(parent_state)
    if not manifest:
        return _rejected("no accepted child evidence handles were available")

    normalized_parent, claim_count = _normalize_parent_synthesis(
        parent_output,
        child_records_by_id=_child_records_by_id(parent_state),
    )
    if claim_count == 0:
        return _not_applicable("parent synthesis has no claim-bearing surfaces")

    validation = validate_parent_synthesis(
        evidence_manifest=manifest,
        parent_synthesis=normalized_parent,
    )
    return OOORLMTraceGuardGate(
        status="accepted" if validation.accepted else "rejected",
        validation=validation,
        manifest=manifest,
        normalized_parent_synthesis=normalized_parent,
        reason=None if validation.accepted else "traceguard_rejected_parent_synthesis",
    )


def install_ouroboros_rlm_cli_gate() -> bool:
    """Patch the installed Ouroboros RLM CLI helper for this process.

    Returns ``True`` when the patch is installed. The patch is intentionally
    process-local; importing this package does not mutate files in the installed
    dependency.
    """
    from ouroboros.cli.commands import rlm as rlm_command
    from ouroboros.cli.formatters import console
    from ouroboros.cli.formatters.panels import print_error, print_info, print_success

    marker = "_rlm_forge_traceguard_original_run_with_default_trace_store"
    if hasattr(rlm_command, marker):
        return False

    original = rlm_command._run_with_default_trace_store
    setattr(rlm_command, marker, original)

    async def run_with_traceguard(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        gate = validate_ooo_rlm_result(result)
        if gate.status == "not_applicable":
            print_info(f"TraceGuard skipped: {gate.reason}")
            return result
        if gate.accepted:
            validation = gate.validation
            assert validation is not None
            print_success(
                "TraceGuard accepted parent synthesis "
                f"(unsupported_rate={validation.unsupported_claim_rate:.4f}, "
                f"claims={len(validation.accepted_claims)})."
            )
            return result

        validation = gate.validation
        if validation is None:
            print_error(f"TraceGuard rejected parent synthesis: {gate.reason}")
            raise ValueError(gate.reason or "traceguard_rejected_parent_synthesis")

        reasons = sorted({item.reason for item in validation.rejected_claims})
        print_error(
            "TraceGuard rejected parent synthesis "
            f"(unsupported_rate={validation.unsupported_claim_rate:.4f})."
        )
        console.print(f"[dim]rejection_reasons:[/] {', '.join(reasons) or 'unknown'}")
        raise ValueError("traceguard_rejected_parent_synthesis")

    rlm_command._run_with_default_trace_store = run_with_traceguard
    return True


def _not_applicable(reason: str) -> OOORLMTraceGuardGate:
    return OOORLMTraceGuardGate(
        status="not_applicable",
        validation=None,
        manifest=(),
        normalized_parent_synthesis={},
        reason=reason,
    )


def _rejected(reason: str) -> OOORLMTraceGuardGate:
    return OOORLMTraceGuardGate(
        status="rejected",
        validation=None,
        manifest=(),
        normalized_parent_synthesis={},
        reason=reason,
    )


def _json_mapping_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def _child_records_by_id(parent_state: Any) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for result in _ordered_child_results(parent_state):
        child_id = _child_result_id(parent_state, result)
        if child_id:
            records[child_id] = result
    return records


def _manifest_from_parent_state(parent_state: Any) -> tuple[TraceGuardEvidence, ...]:
    evidence: list[TraceGuardEvidence] = []
    for result in _ordered_child_results(parent_state):
        child_id = _child_result_id(parent_state, result)
        chunk_id = _string_or_none(getattr(result, "chunk_id", None))
        if child_id is None or chunk_id is None:
            continue
        evidence.append(
            TraceGuardEvidence(
                fact_id=child_id,
                chunk_id=chunk_id,
                text=_child_record_text(result),
                child_call_id=_string_or_none(getattr(result, "call_id", None)),
            )
        )
    return tuple(evidence)


def _ordered_child_results(parent_state: Any) -> tuple[Any, ...]:
    ordered = getattr(parent_state, "ordered_child_results", None)
    if callable(ordered):
        return tuple(ordered())
    return tuple(getattr(parent_state, "recorded_subcall_results", ()) or ())


def _child_result_id(parent_state: Any, result: Any) -> str | None:
    parent_node_id = _string_or_none(getattr(parent_state, "parent_node_id", None))
    order = getattr(result, "order", None)
    if parent_node_id is None or isinstance(order, bool) or not isinstance(order, int):
        return None
    return f"{parent_node_id}:child_result:{order:03d}"


def _child_record_text(result: Any) -> str:
    payload = getattr(result, "result_payload", None)
    if isinstance(payload, Mapping):
        reported = payload.get("reported_result")
        if isinstance(reported, Mapping):
            summary = reported.get("summary") or reported.get("atomic_summary")
            if isinstance(summary, str) and summary.strip():
                return summary
        if isinstance(reported, str) and reported.strip():
            return reported
        completion = payload.get("completion")
        if isinstance(completion, str) and completion.strip():
            return completion[:2000]
    return f"RLM child result {getattr(result, 'order', 'unknown')}"


def _normalize_parent_synthesis(
    parent_output: Mapping[str, Any],
    *,
    child_records_by_id: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    evidence_references: list[dict[str, Any]] = []
    retained_facts: list[dict[str, Any]] = []
    claim_count = 0

    result = parent_output.get("result")
    if isinstance(result, Mapping):
        for claim in _iter_parent_claims(result):
            claim_count += 1
            evidence_references.extend(
                _claim_evidence_references(claim, child_records_by_id)
            )
        retained_facts.extend(_direct_fact_claims(result))

    for reference in _mapping_list(parent_output.get("evidence_references")):
        normalized = _reference_from_child_result(reference, child_records_by_id)
        if normalized is not None:
            claim_count += 1
            evidence_references.append(normalized)
        elif _has_direct_fact_id(reference):
            claim_count += 1
            evidence_references.append(dict(reference))

    claim_count += len(retained_facts)
    return (
        {
            "mode": "ooo_rlm_parent_synthesis_traceguard_normalized",
            "verdict": parent_output.get("verdict"),
            "result": {
                "summary": _parent_summary(parent_output),
                "retained_facts": retained_facts,
            },
            "evidence_references": evidence_references,
            "residual_gaps": parent_output.get("residual_gaps", []),
        },
        claim_count,
    )


def _iter_parent_claims(result: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for key in ("key_synthesized_claims", "accepted_claims", "claims"):
        yield from _mapping_list(result.get(key))


def _claim_evidence_references(
    claim: Mapping[str, Any],
    child_records_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    text = _claim_text(claim)
    for child_result_id in _supported_child_result_ids(claim):
        child_record = child_records_by_id.get(child_result_id)
        chunk_id = _string_or_none(getattr(child_record, "chunk_id", None))
        if chunk_id is None:
            chunk_id = f"missing://{child_result_id}"
        references.append(
            {
                "chunk_id": chunk_id,
                "supports_fact_ids": [child_result_id],
                "quoted_evidence": text,
            }
        )
    return references


def _reference_from_child_result(
    reference: Mapping[str, Any],
    child_records_by_id: dict[str, Any],
) -> dict[str, Any] | None:
    child_result_id = _string_or_none(reference.get("child_result_id"))
    if child_result_id is None:
        return None
    child_record = child_records_by_id.get(child_result_id)
    chunk_id = _string_or_none(reference.get("chunk_id")) or _string_or_none(
        getattr(child_record, "chunk_id", None)
    )
    if chunk_id is None:
        chunk_id = f"missing://{child_result_id}"
    return {
        "chunk_id": chunk_id,
        "supports_fact_ids": [child_result_id],
        "quoted_evidence": _claim_text(reference),
    }


def _direct_fact_claims(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for key in ("retained_facts", "observed_facts", "facts", "retained_evidence"):
        for item in _mapping_list(result.get(key)):
            if _has_direct_fact_id(item):
                claims.append(dict(item))
    return claims


def _has_direct_fact_id(value: Mapping[str, Any]) -> bool:
    return isinstance(value.get("fact_id"), str) or isinstance(
        value.get("supports_fact_id"), str
    )


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _supported_child_result_ids(value: Mapping[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    child_result_id = _string_or_none(value.get("child_result_id"))
    if child_result_id is not None:
        ids.append(child_result_id)
    for key in SUPPORTED_CHILD_KEYS:
        item = value.get(key)
        if isinstance(item, list | tuple):
            ids.extend(entry for entry in item if isinstance(entry, str) and entry)
    return tuple(dict.fromkeys(ids))


def _claim_text(value: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("claim", "text", "statement", "supports", "evidence", "summary"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            parts.append(item)
    return "\n".join(parts)


def _parent_summary(parent_output: Mapping[str, Any]) -> str:
    result = parent_output.get("result")
    if isinstance(result, Mapping):
        for key in ("parent_summary", "summary"):
            item = result.get(key)
            if isinstance(item, str) and item.strip():
                return item
    return "Normalized dependency ooo rlm parent synthesis."


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
