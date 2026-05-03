# RLM-FORGE Live Portability Smoke Run

- Run mode: `live_smoke`
- Live model calls: `True`
- Fixtures: `1`
- Runtime families: `3`
- Contract variants: `1`
- Planned cells: `3`
- Primary cells: `3`

## Runtime Families

| Family | Adapter | Model alias | CLI version | Auth mode |
| --- | --- | --- | --- | --- |
| hermes_glm | `HermesCliRuntime` | `glm-4.7` | `Hermes Agent v0.11.0 (2026.4.23)` | `transient_glm_env_or_existing_hermes_zai_config` |
| claude_code_opus47 | `ClaudeAgentAdapter` | `opus` | `2.1.119 (Claude Code)` | `claude_code_subscription` |
| codex_gpt55 | `CodexCliRuntime` | `gpt-5.5` | `codex-cli 0.128.0` | `codex_cli_subscription` |

## Family Summary

| Family | Completed primary | Passed primary | Failed primary | Infra skipped | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| hermes_glm | 1 | 1 | 0 | 0 | `pass` |
| claude_code_opus47 | 1 | 1 | 0 | 0 | `pass` |
| codex_gpt55 | 1 | 1 | 0 | 0 | `pass` |

## Interpretation

Live smoke mode executes one RLM-FORGE+TraceGuard fixture across the claimed families. Aggregate status: `pass`. This is an adapter/auth smoke test before the full 8-fixture matrix.
