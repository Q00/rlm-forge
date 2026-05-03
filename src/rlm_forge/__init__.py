"""Runtime for executing RLM sub-calls through Hermes Agent.

Re-exports the recursive surface from ``ouroboros.rlm`` so that this
submission package has a clean, focused namespace for hackathon judges.
The actual recursion engine lives in the upstream Ouroboros project under
the ``ouroboros.rlm`` and ``ouroboros.execution.decomposition`` modules,
both of which use the same ``HermesCliRuntime`` adapter.
"""

from ouroboros.rlm import (  # noqa: F401  re-exported for the hackathon namespace
    MAX_RLM_AC_TREE_DEPTH,
    MAX_RLM_AMBIGUITY_THRESHOLD,
    RLM_MVP_SRC_DOGFOOD_BENCHMARK_ID,
    RLMRunConfig,
    RLMRunResult,
    RLMSharedTruncationBenchmarkConfig,
    RLMSharedTruncationBenchmarkResult,
    RLMTraceStore,
    RLMVanillaTruncationBaselineConfig,
    run_rlm_benchmark,
    run_rlm_loop,
    run_shared_truncation_benchmark,
    run_vanilla_truncation_baseline,
)
from ouroboros.orchestrator.hermes_runtime import HermesCliRuntime  # noqa: F401
from rlm_forge.traceguard import (  # noqa: F401
    TraceGuardClaim,
    TraceGuardEvidence,
    TraceGuardRejection,
    TraceGuardResult,
    build_manifest_from_fixture,
    extract_parent_claims,
    normalize_allowed_evidence_manifest,
    validate_parent_synthesis,
)

__all__ = [
    "HermesCliRuntime",
    "MAX_RLM_AC_TREE_DEPTH",
    "MAX_RLM_AMBIGUITY_THRESHOLD",
    "RLM_MVP_SRC_DOGFOOD_BENCHMARK_ID",
    "RLMRunConfig",
    "RLMRunResult",
    "RLMSharedTruncationBenchmarkConfig",
    "RLMSharedTruncationBenchmarkResult",
    "RLMTraceStore",
    "RLMVanillaTruncationBaselineConfig",
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
    "normalize_allowed_evidence_manifest",
    "validate_parent_synthesis",
]

__version__ = "0.1.0"
