# TraceGuard Evidence Gate Demo

Hermes is not called. This demo validates parent synthesis outputs
against an accepted child evidence manifest.

- Cases: `3`
- Passed: `3`
- Failed: `0`

| Case | Expected | Actual | Unsupported claim rate | Rejection reasons |
| --- | --- | --- | ---: | --- |
| safe_parent_synthesis | ACCEPT | ACCEPT | 0.0000 | `[]` |
| unsafe_omitted_fact | REJECT | REJECT | 0.2000 | `['unsupported_fact_id']` |
| chunk_only_no_fact | REJECT | REJECT | 1.0000 | `['chunk_handle_without_fact', 'chunk_handle_without_fact']` |

Interpretation: TraceGuard accepts parent synthesis only when every
structured fact claim is backed by an accepted child evidence handle.
It rejects omitted facts and rejects chunk handles that do not identify
supported fact IDs.
