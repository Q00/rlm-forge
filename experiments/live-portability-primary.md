# RLM-FORGE Live Portability Primary Run

- Run mode: `live_primary`
- Run status: `completed`
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
| hermes_glm | 8 | 8 | 0 | 0 | `pass` |
| claude_code_opus47 | 8 | 8 | 0 | 0 | `pass` |
| codex_gpt55 | 8 | 8 | 0 | 0 | `pass` |

## Live Cells

| Fixture | Family | Status | Latency seconds | Child calls | TraceGuard accepted |
| --- | --- | --- | ---: | ---: | --- |
| simple-truncation-01 | hermes_glm | `live_contract_pass` | 142.912 | 4 | `True` |
| simple-truncation-01 | claude_code_opus47 | `live_contract_pass` | 67.31 | 4 | `True` |
| simple-truncation-01 | codex_gpt55 | `live_contract_pass` | 68.589 | 4 | `True` |
| simple-truncation-02 | hermes_glm | `live_contract_pass` | 158.606 | 4 | `True` |
| simple-truncation-02 | claude_code_opus47 | `live_contract_pass` | 68.59 | 4 | `True` |
| simple-truncation-02 | codex_gpt55 | `live_contract_pass` | 63.27 | 4 | `True` |
| distractor-heavy-01 | hermes_glm | `live_contract_pass` | 118.719 | 4 | `True` |
| distractor-heavy-01 | claude_code_opus47 | `live_contract_pass` | 69.348 | 4 | `True` |
| distractor-heavy-01 | codex_gpt55 | `live_contract_pass` | 46.362 | 4 | `True` |
| distractor-heavy-02 | hermes_glm | `live_contract_pass` | 168.6 | 4 | `True` |
| distractor-heavy-02 | claude_code_opus47 | `live_contract_pass` | 65.809 | 4 | `True` |
| distractor-heavy-02 | codex_gpt55 | `live_contract_pass` | 44.45 | 4 | `True` |
| cross-chunk-dependency-01 | hermes_glm | `live_contract_pass` | 117.956 | 4 | `True` |
| cross-chunk-dependency-01 | claude_code_opus47 | `live_contract_pass` | 72.449 | 4 | `True` |
| cross-chunk-dependency-01 | codex_gpt55 | `live_contract_pass` | 50.511 | 4 | `True` |
| cross-chunk-dependency-02 | hermes_glm | `live_contract_pass` | 145.81 | 4 | `True` |
| cross-chunk-dependency-02 | claude_code_opus47 | `live_contract_pass` | 69.4 | 4 | `True` |
| cross-chunk-dependency-02 | codex_gpt55 | `live_contract_pass` | 47.537 | 4 | `True` |
| omitted-fact-temptation-01 | hermes_glm | `live_contract_pass` | 186.679 | 4 | `True` |
| omitted-fact-temptation-01 | claude_code_opus47 | `live_contract_pass` | 70.109 | 4 | `True` |
| omitted-fact-temptation-01 | codex_gpt55 | `live_contract_pass` | 52.313 | 4 | `True` |
| chunk-only-citation-trap-01 | hermes_glm | `live_contract_pass` | 205.471 | 4 | `True` |
| chunk-only-citation-trap-01 | claude_code_opus47 | `live_contract_pass` | 69.158 | 4 | `True` |
| chunk-only-citation-trap-01 | codex_gpt55 | `live_contract_pass` | 47.469 | 4 | `True` |

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

Live primary mode executes the RLM-FORGE+TraceGuard contract for 24/24 planned primary cells. Aggregate status: `pass`. A pass supports the runtime portability claim; it does not evaluate secondary baselines or SOTA model quality.
