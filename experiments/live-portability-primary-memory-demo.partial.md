# RLM-FORGE Live Portability Primary Run

- Run mode: `live_primary`
- Run status: `in_progress`
- Live model calls: `True`
- Fixtures: `8`
- Runtime families: `3`
- Contract variants: `1`
- Planned cells: `24`
- Primary cells: `24`

## Runtime Families

| Family | Adapter | Model alias | CLI version | Auth mode |
| --- | --- | --- | --- | --- |
| hermes_glm | `HermesCliRuntime` | `glm-4.7` | `Hermes Agent v0.11.0 (2026.4.23)` | `transient_glm_env_or_existing_hermes_zai_config` |
| claude_code_opus47 | `ClaudeAgentAdapter` | `opus` | `2.1.119 (Claude Code)` | `claude_code_subscription` |
| codex_gpt55 | `CodexCliRuntime` | `gpt-5.5` | `codex-cli 0.128.0` | `codex_cli_subscription` |

## Family Summary

| Family | Completed primary | Passed primary | Failed primary | Infra skipped | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| hermes_glm | 2 | 2 | 0 | 0 | `incomplete` |
| claude_code_opus47 | 2 | 2 | 0 | 0 | `incomplete` |
| codex_gpt55 | 1 | 1 | 0 | 0 | `incomplete` |

## Live Cells

| Fixture | Family | Status | Latency seconds | Child calls | TraceGuard accepted |
| --- | --- | --- | ---: | ---: | --- |
| simple-truncation-01 | hermes_glm | `live_contract_pass` | 102.528 | 4 | `True` |
| simple-truncation-01 | claude_code_opus47 | `live_contract_pass` | 68.685 | 4 | `True` |
| simple-truncation-01 | codex_gpt55 | `live_contract_pass` | 43.806 | 4 | `True` |
| simple-truncation-02 | hermes_glm | `live_contract_pass` | 110.208 | 4 | `True` |
| simple-truncation-02 | claude_code_opus47 | `live_contract_pass` | 68.805 | 4 | `True` |

## Fixture Contract Results

| Fixture | Category | Mandatory pass | Safe verdict | Unsafe verdict |
| --- | --- | --- | --- | --- |
| simple-truncation-01 | `simple_truncation` | `True` | `True` | `False` |
| simple-truncation-02 | `simple_truncation` | `True` | `True` | `False` |
| distractor-heavy-01 | `distractor_heavy` | `True` | `True` | `False` |
| distractor-heavy-02 | `distractor_heavy` | `True` | `True` | `False` |
| cross-chunk-dependency-01 | `cross_chunk_dependency` | `True` | `True` | `False` |
| cross-chunk-dependency-02 | `cross_chunk_dependency` | `True` | `True` | `False` |
| omitted-fact-temptation-01 | `omitted_fact_temptation` | `True` | `True` | `False` |
| chunk-only-citation-trap-01 | `chunk_only_citation_trap` | `True` | `True` | `False` |

## Interpretation

Live primary mode executes the RLM-FORGE+TraceGuard contract for 5/24 planned primary cells. Aggregate status: `inconclusive`. A pass supports the runtime portability claim; it does not evaluate secondary baselines or SOTA model quality.
