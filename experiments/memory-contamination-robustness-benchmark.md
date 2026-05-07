# Memory Contamination Robustness Benchmark

Deterministic benchmark showing that TraceGuard prevents adversarial answer-memory contamination from becoming accepted parent synthesis state.

- Fixture Count: `12`
- Policy Count: `6`
- Evaluation Count: `72`

## Policy Summary

| Policy | N | Initial accept | Final accept | Accepted memory-answer | Mean repairs | Mean calls | Final unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| unguarded_no_memory | 12 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| unguarded_benign_memory | 12 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| unguarded_adversarial_memory | 12 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| traceguard_no_memory | 12 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| traceguard_benign_memory | 12 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| traceguard_adversarial_memory | 12 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.1429 |

## Interpretation

The adversarial-memory condition adds an unsupported answer fact from
persistent memory. Without TraceGuard, that memory answer becomes
accepted parent state. With TraceGuard, the same unsupported fact is
rejected because it is absent from the fresh child evidence manifest.

This supports the contribution that memory can be present in the
runtime prompt without becoming admissible evidence.
