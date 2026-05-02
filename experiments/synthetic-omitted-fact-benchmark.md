# Synthetic Omitted-Fact Benchmark

Hermes is not called. This benchmark generates deterministic truncation
fixtures and scores controlled completion strategies with the same
claim-aware scorer used by the persisted artifact.

- Fixtures: `108`
- Strategies: `7`
- Evaluations: `756`
- Sanity failures: `0`

## Strategy Summary

| Strategy | N | Mean score | Min | Max | Mean retained | Mean boundary | Mean safety | Claimed omitted | Sanity failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| perfect_abstaining | 108 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| guarded_gap_mentions | 108 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| omitted_claim_faulty | 108 | 0.8000 | 0.8000 | 0.8000 | 1.0000 | 1.0000 | 0.0000 | 297 | 0 |
| omitted_evidence_faulty | 108 | 0.8000 | 0.8000 | 0.8000 | 1.0000 | 1.0000 | 0.0000 | 297 | 0 |
| chunk_only_citations | 108 | 0.6500 | 0.6500 | 0.6500 | 0.0000 | 1.0000 | 1.0000 | 0 | 0 |
| missing_boundary_report | 108 | 0.9000 | 0.9000 | 0.9000 | 1.0000 | 0.0000 | 1.0000 | 0 | 0 |
| drops_last_retained_fact | 108 | 0.9193 | 0.8250 | 0.9767 | 0.7693 | 1.0000 | 1.0000 | 0 | 0 |

## Interpretation

The controlled safe strategies (`perfect_abstaining` and
`guarded_gap_mentions`) remain perfect across all generated fixtures.
Faulty omitted-fact strategies fail only the omitted-fact safety axis.
Chunk-only citations receive no retained-fact credit, which guards
against a common false positive in coarse evidence scoring.

This is still a scorer stress test, not evidence that a live model or
recursive scaffold will outperform another model. It supports the
narrower claim that the evaluation harness can separate guarded gap
mentions from unsupported evidence claims across many fixture shapes.
