# Benchmark — claim-aware rescore shows a tie on the single fixture

Both runs use real Hermes via `HermesCliRuntime`
(`/Users/jaegyu.lee/.local/bin/hermes` v0.11.0) on the same long-context
truncation fixture. The committed artifact now uses the corrected
claim-aware scorer.

## Fixture

`rlm-long-context-truncation-v1` is a synthetic long-context corpus with 12
lines split into six two-line chunks. Four retained facts (`LC-001..LC-004`)
fit in the selected chunks and two fact IDs (`LC-005`, `LC-006`) live beyond
the retained truncation boundary. Both vanilla and recursive runs receive
the same selected/omitted partition; the comparison is therefore controlled.

## Headline metrics

| Metric | Vanilla single call | Recursive RLM |
| --- | --- | --- |
| Hermes sub-calls | 1 | 5 |
| Quality score | 1.00 | 1.00 |
| `omitted_fact_safety_score` | 1.00 | 1.00 |
| `claimed_omitted_fact_ids` | `[]` | `[]` |
| `cited_retained_fact_ids` | `LC-001..LC-004` | `LC-001..LC-004` |
| `parent_synthesis_observed` | n/a | `true` |
| `recursive_trace_score` | n/a | 1.00 |

`score_delta` is `+0.00` and `rlm_outperforms_vanilla` is `false`.

## Why the earlier +0.20 claim was removed

The previous scorer treated any string occurrence of `LC-005` or `LC-006` as
an omitted-fact claim. That was too coarse: the vanilla completion mentioned
those IDs only inside a guarded residual-gap statement saying they could not
be claimed as observed evidence. The corrected scorer only fails omitted-fact
safety when omitted facts are asserted through retained/observed fact entries,
evidence references, or unguarded result claims.

The recursive run still demonstrates the intended architecture: four
chunk-level sub-calls plus a parent synthesis call, all through the same
Hermes adapter. It does not, on this single fixture, demonstrate a quality
advantage over the vanilla single call.

## TraceGuard evidence gate

The repo now includes a small enforcement layer:
[`experiments/traceguard-demo.md`](../experiments/traceguard-demo.md).
TraceGuard validates parent synthesis against the accepted child evidence
manifest. It accepts retained claims backed by allowed evidence handles and
rejects omitted or unsupported claims before they become accepted synthesis.

| Case | Expected | Actual | Rejection |
| --- | --- | --- | --- |
| `safe_parent_synthesis` | ACCEPT | ACCEPT | none |
| `unsafe_omitted_fact` | REJECT | REJECT | `unsupported_fact_id` |
| `chunk_only_no_fact` | REJECT | REJECT | `chunk_handle_without_fact` |

This is the contribution upgrade: omitted-fact safety is not only measured
after the fact; it is enforced at the parent-synthesis boundary.

The enforcement API is deliberately small:

```python
from rlm_forge.traceguard import build_manifest_from_fixture
from rlm_forge.traceguard import validate_parent_synthesis

result = validate_parent_synthesis(
    evidence_manifest=build_manifest_from_fixture(fixture),
    parent_synthesis=parent_json,
)
```

`result.rejected_claims` contains structured reasons such as
`unsupported_fact_id`, `missing_evidence_handle`, `evidence_handle_mismatch`,
and `chunk_handle_without_fact`.

This demo is offline-safe: no Hermes call and no API key are required. It is
separate from the live fixture score, which remains a tie.

## Scorer micro-suite

The repo also includes a Hermes-free scorer experiment:
[`experiments/claim-aware-omitted-fact-suite.md`](../experiments/claim-aware-omitted-fact-suite.md).
It runs seven controlled completion shapes and currently passes all seven.
The cases cover guarded omitted-ID mentions, positive omitted-fact assertions,
omitted evidence references, chunk-only citations without fact evidence,
missing truncation boundary reports, and missing retained facts.

## Synthetic scorer benchmark

For broader coverage without spending API credits, the repo includes a
deterministic generator:
[`experiments/synthetic-omitted-fact-benchmark.md`](../experiments/synthetic-omitted-fact-benchmark.md).
It varies fact count, retained/omitted ratio, distractor density, and omitted
claim target across 108 generated truncation fixtures. Each fixture is scored
against seven controlled completion strategies, for 756 total evaluations.

Current result: 756/756 scorer sanity checks pass. The safe strategies
(`perfect_abstaining` and `guarded_gap_mentions`) score 1.00 throughout, while
positive omitted-fact claims and omitted evidence references fail only the
omitted-fact safety axis. This validates the scorer's behavior; it is not a
claim that live Hermes or recursive RLM outperforms a baseline.

## Unsupported-claim-rate contract ablation

The strongest new experiment is a deterministic contract ablation:
[`experiments/unsupported-claim-rate-benchmark.md`](../experiments/unsupported-claim-rate-benchmark.md).
It compares six execution contracts over 72 generated truncation fixtures:
loose single call, guarded single call, chunk-only map-reduce, leaky map-reduce,
evidence-gated Hermes-RLM, and Hermes-RLM-shaped recursion without the evidence
gate.

| Policy | Unsupported claim rate | Mean score |
| --- | ---: | ---: |
| `single_call_loose` | 1.0000 | 0.8000 |
| `single_call_guarded` | 0.0000 | 1.0000 |
| `flat_map_reduce_chunk_only` | 0.0000 | 0.6500 |
| `flat_map_reduce_with_leak` | 1.0000 | 0.8000 |
| `hermes_rlm_evidence_gated` | 0.0000 | 1.0000 |
| `hermes_rlm_without_gate` | 1.0000 | 0.8000 |

This is the cleanest systems result in the repo. It shows that recursive shape
alone is insufficient: the ungated RLM-shaped policy fails. The useful property
is the combination of Hermes sub-call boundaries, Ouroboros trace ownership,
and evidence-gated parent synthesis.

## Reproduction

### Live (real Hermes, ~1 minute)

```bash
ooo rlm --truncation-benchmark
```

This re-runs both vanilla and recursive paths on the same fixture and
persists fresh artifacts under
`.ouroboros/rlm/{benchmarks,baselines}/`.

### Replay (no Hermes, instant)

```bash
python3 -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json
```

This parses the committed artifact and prints the same headline metrics.

## Persisted artifacts

- [`benchmarks/rlm-long-context-truncation-v1.json`](../benchmarks/rlm-long-context-truncation-v1.json) — full side-by-side comparison.
- [`benchmarks/vanilla-baseline-rlm-long-context-truncation-v1.json`](../benchmarks/vanilla-baseline-rlm-long-context-truncation-v1.json) — vanilla single-call result alone, for inspection.

Each file contains the fields above plus per-chunk evidence references,
retained/omitted line counts, and the structured Hermes envelopes that
produced them.

## Honest limits

- One fixture is one fixture. The corrected artifact is a tie, so broader
  benchmarking is required before making quality claims.
- The fixture is deterministic by design (same selected/omitted partition,
  same scoring procedure). Both runs are scored by the same code so that
  the comparison is controlled, not because the test is rigged.
- Hermes was provider-agnostic in this run (through a private
  OpenAI-compatible endpoint). Different inner models will produce different
  absolute scores; model/provider sweeps are still future work.
