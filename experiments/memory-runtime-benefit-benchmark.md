# Memory Runtime Benefit Benchmark

Hermes is not called. This deterministic benchmark isolates a narrow
runtime-control performance question: can guarded operational memory
priors reduce repair work for known schema failure modes while preserving
the fresh-evidence boundary?

- Fixtures: `20`
- Provider profiles: `4`
- Policies: `3`
- Evaluations: `240`

## Policy Summary

| Policy | N | Initial accept | Final accept | Mean repairs | Mean parent+repair calls | Final unsupported rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no_memory | 80 | 0.2500 | 0.5000 | 0.2500 | 1.2500 | 0.2778 |
| guarded_operational_memory_prior | 80 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| unsafe_answer_memory_prior | 80 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.1111 |

## Provider Profile Detail

| Provider profile | Policy | Initial accept | Final accept | Mean repairs | Mean calls |
| --- | --- | ---: | ---: | ---: | ---: |
| schema_stable | no_memory | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| schema_stable | guarded_operational_memory_prior | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| schema_stable | unsafe_answer_memory_prior | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| missing_handle_prone | no_memory | 0.0000 | 1.0000 | 1.0000 | 2.0000 |
| missing_handle_prone | guarded_operational_memory_prior | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| missing_handle_prone | unsafe_answer_memory_prior | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| chunk_only_prone | no_memory | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| chunk_only_prone | guarded_operational_memory_prior | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| chunk_only_prone | unsafe_answer_memory_prior | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| answer_memory_contaminated | no_memory | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| answer_memory_contaminated | guarded_operational_memory_prior | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| answer_memory_contaminated | unsafe_answer_memory_prior | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

## Interpretation

The guarded operational memory prior represents a schema/retry prior,
not answer evidence. In this controlled benchmark it makes the parent
synthesis use fact-level evidence handles from the start. That raises
initial TraceGuard acceptance and removes the repair call required by
the missing-handle-prone no-memory policy.

The unsafe answer-memory policy is intentionally different. It models
a contaminated memory that tries to add an answer fact. TraceGuard
rejects it as unsupported, demonstrating why memory must remain a
prior over how to ask for evidence rather than evidence itself.

This benchmark supports a runtime performance claim only: guarded
operational memory can reduce validation/repair work for known schema
failure modes. It does not show model-quality, latency, token, or cost
improvement in live providers.
