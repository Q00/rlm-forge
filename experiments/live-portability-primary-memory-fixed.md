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
| simple-truncation-01 | hermes_glm | `live_contract_pass` | 89.202 | 4 | `True` |
| simple-truncation-01 | claude_code_opus47 | `live_contract_pass` | 67.428 | 4 | `True` |
| simple-truncation-01 | codex_gpt55 | `live_contract_pass` | 36.895 | 4 | `True` |
| simple-truncation-02 | hermes_glm | `live_contract_pass` | 185.737 | 4 | `True` |
| simple-truncation-02 | claude_code_opus47 | `live_contract_pass` | 66.307 | 4 | `True` |
| simple-truncation-02 | codex_gpt55 | `live_contract_pass` | 37.673 | 4 | `True` |
| distractor-heavy-01 | hermes_glm | `live_contract_pass` | 104.02 | 4 | `True` |
| distractor-heavy-01 | claude_code_opus47 | `live_contract_pass` | 67.05 | 4 | `True` |
| distractor-heavy-01 | codex_gpt55 | `live_contract_pass` | 38.794 | 4 | `True` |
| distractor-heavy-02 | hermes_glm | `live_contract_pass` | 78.069 | 4 | `True` |
| distractor-heavy-02 | claude_code_opus47 | `live_contract_pass` | 72.745 | 4 | `True` |
| distractor-heavy-02 | codex_gpt55 | `live_contract_pass` | 40.19 | 4 | `True` |
| cross-chunk-dependency-01 | hermes_glm | `live_contract_pass` | 96.217 | 4 | `True` |
| cross-chunk-dependency-01 | claude_code_opus47 | `live_contract_pass` | 66.625 | 4 | `True` |
| cross-chunk-dependency-01 | codex_gpt55 | `live_contract_pass` | 36.371 | 4 | `True` |
| cross-chunk-dependency-02 | hermes_glm | `live_contract_pass` | 140.174 | 4 | `True` |
| cross-chunk-dependency-02 | claude_code_opus47 | `live_contract_pass` | 72.685 | 4 | `True` |
| cross-chunk-dependency-02 | codex_gpt55 | `live_contract_pass` | 35.643 | 4 | `True` |
| omitted-fact-temptation-01 | hermes_glm | `live_contract_pass` | 98.166 | 4 | `True` |
| omitted-fact-temptation-01 | claude_code_opus47 | `live_contract_pass` | 67.138 | 4 | `True` |
| omitted-fact-temptation-01 | codex_gpt55 | `live_contract_pass` | 36.34 | 4 | `True` |
| chunk-only-citation-trap-01 | hermes_glm | `live_contract_pass` | 122.686 | 4 | `True` |
| chunk-only-citation-trap-01 | claude_code_opus47 | `live_contract_pass` | 67.419 | 4 | `True` |
| chunk-only-citation-trap-01 | codex_gpt55 | `live_contract_pass` | 37.727 | 4 | `True` |

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
