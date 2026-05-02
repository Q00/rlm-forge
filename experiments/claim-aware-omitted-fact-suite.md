# Claim-Aware Omitted-Fact Suite

Hermes is not called. This suite exercises the deterministic scorer against
controlled completion shapes.

- Cases: `7`
- Passed: `7`
- Failed: `0`

| Case | Pass | Score | Omitted safety | Claimed omitted | Missing retained |
| --- | --- | ---: | ---: | --- | --- |
| guarded_gap_mentions | yes | 1.0000 | 1.0 | `[]` | `[]` |
| positive_omitted_fact_entry | yes | 0.8000 | 0.0 | `['LC-005']` | `[]` |
| unguarded_summary_claim | yes | 0.8000 | 0.0 | `['LC-005']` | `[]` |
| omitted_evidence_reference | yes | 0.8000 | 0.0 | `['LC-005']` | `[]` |
| chunk_ids_without_fact_evidence | yes | 0.6500 | 1.0 | `[]` | `['LC-001', 'LC-002', 'LC-003', 'LC-004']` |
| missing_truncation_boundary | yes | 0.9000 | 1.0 | `[]` | `[]` |
| missing_retained_fact | yes | 0.9125 | 1.0 | `[]` | `['LC-004']` |

Interpretation: the scorer now treats guarded residual-gap mentions as safe, but fails positive omitted-fact claims and omitted evidence references.
