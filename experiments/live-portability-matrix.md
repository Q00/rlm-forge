# RLM-FORGE Live Portability Contracts-Only Check

- Run mode: `contracts_only`
- Live model calls: `False`
- Fixtures: `8`
- Runtime families: `3`
- Contract variants: `4`
- Planned cells: `96`
- Primary cells: `24`

## Runtime Families

| Family | Adapter | Model alias | CLI version | Auth mode |
| --- | --- | --- | --- | --- |
| hermes_glm | `HermesCliRuntime` | `glm-4.7` | `Hermes Agent v0.11.0 (2026.4.23)` | `transient_glm_env_or_existing_hermes_zai_config` |
| claude_code_opus47 | `ClaudeAgentAdapter` | `opus` | `2.1.119 (Claude Code)` | `claude_code_subscription` |
| codex_gpt55 | `CodexCliRuntime` | `gpt-5.5` | `codex-cli 0.128.0` | `codex_cli_subscription` |

## Family Summary

| Family | Checked primary | Passed primary | Failed primary | Infra skipped | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| hermes_glm | 8 | 8 | 0 | 0 | `preflight_pass` |
| claude_code_opus47 | 8 | 8 | 0 | 0 | `preflight_pass` |
| codex_gpt55 | 8 | 8 | 0 | 0 | `preflight_pass` |

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

Contracts-only mode validates fixture completeness and TraceGuard safe/unsafe verdicts for 24/24 primary cells without calling providers. It is a precondition for the live matrix, not the live portability result itself.
