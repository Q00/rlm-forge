# Adaptive Repair Memory Benchmark

Deterministic sequence benchmark showing that an operational memory prior learned from an initial missing-handle repair can reduce later repair calls.

- Task Count Per Policy: `8`
- Policy Count: `2`
- Evaluation Count: `16`

## Policy Summary

| Policy | N | Initial accept | Final accept | Accepted memory-answer | Mean repairs | Mean calls | Final unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_adaptive_memory | 8 | 0.0000 | 1.0000 | 0.0000 | 1.0000 | 2.0000 | 0.0000 |
| adaptive_repair_memory | 8 | 0.8750 | 1.0000 | 0.0000 | 0.1250 | 1.1250 | 0.0000 |

## Interpretation

The adaptive policy starts without a missing-handle prior. After the
first TraceGuard rejection and repair, it records an operational prior
that later parent calls should preserve fact_id/evidence_chunk_id
pairs. Subsequent related tasks avoid the repair path.

This supports the runtime-learning claim: memory improves repair
efficiency across repeated task families while every final answer
still depends on fresh child evidence.
