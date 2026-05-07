# Layered Memory Ablation Benchmark

Deterministic 2x2 ablation separating Hermes-style prompt memory from RLM-FORGE guarded operational memory.

- Fixture Count: `12`
- Provider Profile Count: `4`
- Policy Count: `4`
- Evaluation Count: `192`

## Policy Summary

| Policy | N | Initial accept | Final accept | Accepted memory-answer | Mean repairs | Mean calls | Final unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hermes_memory_off__rlm_memory_off | 48 | 0.2500 | 0.5000 | 0.0000 | 0.2500 | 1.2500 | 0.5000 |
| hermes_memory_on__rlm_memory_off | 48 | 0.5000 | 1.0000 | 0.0000 | 0.5000 | 1.5000 | 0.0000 |
| hermes_memory_off__rlm_memory_on | 48 | 0.5000 | 0.5000 | 0.0000 | 0.0000 | 1.0000 | 0.5000 |
| hermes_memory_on__rlm_memory_on | 48 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |

## Interpretation

This 2x2 ablation separates two memory roles. Hermes-style prompt
memory models a formatting/schema-discipline prior that prevents
chunk-only parent synthesis. RLM-FORGE guarded memory models an
evidence-handle prior that prevents missing fact handles.

The combined policy reaches full initial and final acceptance with no
repair calls, while each single memory layer fixes only its assigned
failure class. This is a deterministic role-separation result, not a
live provider quality result.
