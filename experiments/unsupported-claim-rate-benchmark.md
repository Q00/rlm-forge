# Unsupported Claim Rate Contract Ablation

Hermes is not called. This deterministic experiment compares execution
contracts under generated truncation fixtures. It measures whether a
completion policy makes unsupported claims about facts that were outside
the retained context.

- Fixtures: `72`
- Policies: `6`
- Evaluations: `432`

## Policy Summary

| Policy | N | Unsupported claim rate | Mean score | Retained citation | Omitted safety | Mean claimed omitted | Mean omitted chunks cited |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| single_call_loose | 72 | 1.0000 | 0.8000 | 1.0000 | 0.0000 | 3.1667 | 0.0000 |
| single_call_guarded | 72 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| flat_map_reduce_chunk_only | 72 | 0.0000 | 0.6500 | 0.0000 | 1.0000 | 0.0000 | 0.0000 |
| flat_map_reduce_with_leak | 72 | 1.0000 | 0.8000 | 1.0000 | 0.0000 | 3.1667 | 3.1667 |
| hermes_rlm_evidence_gated | 72 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| hermes_rlm_without_gate | 72 | 1.0000 | 0.8000 | 1.0000 | 0.0000 | 3.1667 | 0.0000 |

## Interpretation

The evidence-gated Hermes-RLM contract has the same unsupported-claim
rate as a guarded single call: zero. The difference is structural:
RLM exposes parent/child evidence handles and therefore gives the
outer scaffold a concrete place to validate synthesis.

The ablation also shows what the project should not claim. Recursive
shape alone is insufficient: `hermes_rlm_without_gate` has a 1.0
unsupported-claim rate. Flat map-reduce without fact evidence is safe
but loses retained-fact recall. The useful contribution is therefore
the combination of Hermes sub-call boundaries, Ouroboros trace
ownership, and evidence-gated validation.
