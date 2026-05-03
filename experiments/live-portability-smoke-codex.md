# RLM-FORGE Live Portability Smoke Run

- Run mode: `live_smoke`
- Run status: `completed`
- Live model calls: `True`
- Fixtures: `1`
- Runtime families: `1`
- Contract variants: `1`
- Planned cells: `1`
- Primary cells: `1`

## Runtime Families

| Family | Adapter | Model alias | CLI version | Auth mode |
| --- | --- | --- | --- | --- |
| codex_gpt55 | `CodexCliRuntime` | `gpt-5.5` | `codex-cli 0.128.0` | `codex_cli_subscription` |

## Family Summary

| Family | Completed primary | Passed primary | Failed primary | Infra skipped | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| codex_gpt55 | 1 | 1 | 0 | 0 | `pass` |

## Live Cells

| Fixture | Family | Status | Latency seconds | Child calls | TraceGuard accepted |
| --- | --- | --- | ---: | ---: | --- |
| simple-truncation-01 | codex_gpt55 | `live_contract_pass` | 45.516 | 4 | `True` |

## Interpretation

Live smoke mode executes one RLM-FORGE+TraceGuard fixture across the claimed families. Aggregate status: `pass`. This is an adapter/auth smoke test before the full 8-fixture matrix.
