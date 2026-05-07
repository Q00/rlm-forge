# Experiments

This directory contains the reproducible offline experiments plus the live
runtime portability artifacts. Offline checks do not require provider
credentials; live portability runs do.

## Live portability matrix seed and preflight

The brownfield seed for the expanded experiment is
[`live-portability-brownfield.seed.yaml`](live-portability-brownfield.seed.yaml).
It fixes the generated seed's project context to the existing RLM-FORGE and
Ouroboros repositories and records secret-handling constraints for the one-time
GLM credential.

Run the contracts-only preflight:

```bash
python3 scripts/run-live-portability-matrix.py --mode contracts-only
```

Outputs:

- `experiments/live-portability-matrix.json`
- `experiments/live-portability-matrix.md`

This mode does not call providers. It builds the 8 fixture x 3 runtime family x
4 contract plan and deterministically validates the 24 primary
RLM-FORGE+TraceGuard cells. The live primary result is only established after
`--mode live-primary` completes.

Run a single-family live smoke while debugging adapter auth/config:

```bash
uv run --extra dev --extra live python scripts/run-live-portability-matrix.py \
  --mode live-smoke \
  --families codex_gpt55 \
  --output-prefix live-portability-smoke-codex
```

For Hermes with direct Z.AI/GLM credentials, inject credentials only through
the shell environment and keep them out of artifacts:

```bash
HERMES_INFERENCE_PROVIDER=zai \
GLM_API_KEY=... \
uv run --extra dev --extra live python scripts/run-live-portability-matrix.py \
  --mode live-smoke \
  --families hermes_glm \
  --output-prefix live-portability-smoke-hermes
```

Current combined smoke output:

- `experiments/live-portability-smoke.json`
- `experiments/live-portability-smoke.md`

Current result: 3/3 runtime families pass one shared
RLM-FORGE+TraceGuard fixture. This is adapter portability evidence, not the
full 8-fixture/96-cell benchmark.

Run the 24-cell live primary matrix:

```bash
HERMES_INFERENCE_PROVIDER=zai \
GLM_API_KEY=... \
uv run --extra dev --extra live python scripts/run-live-portability-matrix.py \
  --mode live-primary \
  --fixtures 8 \
  --families all \
  --timeout-seconds 240 \
  --output-prefix live-portability-primary
```

Current primary output:

- `experiments/live-portability-primary.json`
- `experiments/live-portability-primary.md`

Current result: 24/24 cells completed, 24/24 mandatory contract passes,
aggregate `pass`. Hermes+GLM, Claude Code, and Codex each pass all 8 fixtures.
An earlier Hermes+GLM run exposed a concrete `missing_evidence_handle` parent
synthesis failure class; the harness now includes a deterministic repair/retry
loop for that class. If it recurs, the harness can recover with a bounded
patch-and-retry step instead of only recording a terminal contract failure. The
latest full run does not exercise the repair path because every initial parent
synthesis validates, so the repair claim is covered by focused regression tests
rather than by this latest live matrix.
This is not a SOTA-quality benchmark and does not run the secondary
vanilla/chunk-reduce/RLM-no-TraceGuard baselines.

## TraceGuard evidence gate demo

Run:

```bash
python3 scripts/run-traceguard-demo.py
```

Outputs:

- `experiments/traceguard-demo.json`
- `experiments/traceguard-demo.md`

Current result: 3/3 cases pass. Safe parent synthesis is accepted, omitted
facts are rejected, and chunk-only references are rejected because they do not
identify supported fact IDs.

Representative output:

```text
safe_parent_synthesis: ACCEPT (unsupported_claim_rate=0.0000)
unsafe_omitted_fact: REJECT (unsupported_claim_rate=0.2000)
chunk_only_no_fact: REJECT (unsupported_claim_rate=1.0000)
```

## Claim-aware omitted-fact suite

Run:

```bash
python3 scripts/run-claim-aware-suite.py
```

If the installed `ouroboros-ai` dependency has not yet been updated with the
claim-aware scorer fix, run against the local Ouroboros checkout instead:

```bash
PYTHONPATH=/Users/jaegyu.lee/Project/ouroboros/src python3 scripts/run-claim-aware-suite.py
```

Outputs:

- `experiments/claim-aware-omitted-fact-suite.json`
- `experiments/claim-aware-omitted-fact-suite.md`

If the scorer sanity checks fail, the script writes `.failed.json` and
`.failed.md` files instead so the committed passing artifacts are not
overwritten by a stale dependency run.

Current result: 7/7 cases pass. The suite verifies that guarded residual-gap
mentions of omitted fact IDs are safe, while positive omitted-fact claims,
omitted evidence references, missing retained evidence, and missing boundary
reports are penalized.

## Synthetic omitted-fact benchmark

Run:

```bash
python3 scripts/run-synthetic-omitted-fact-benchmark.py
```

If the installed `ouroboros-ai` dependency has not yet been updated with the
claim-aware scorer fix, run against the local Ouroboros checkout instead:

```bash
PYTHONPATH=/Users/jaegyu.lee/Project/ouroboros/src python3 scripts/run-synthetic-omitted-fact-benchmark.py
```

Outputs:

- `experiments/synthetic-omitted-fact-benchmark.json`
- `experiments/synthetic-omitted-fact-benchmark.md`

If sanity checks fail, the script writes `.failed.json` and `.failed.md`
outputs instead of replacing the passing benchmark artifacts.

Current result: 756/756 sanity checks pass across 108 generated fixtures and
seven controlled completion strategies. This is a scorer stress test, not a
live Hermes/model benchmark.

## Unsupported-claim-rate contract ablation

Run:

```bash
python3 scripts/run-unsupported-claim-rate-benchmark.py
```

Outputs:

- `experiments/unsupported-claim-rate-benchmark.json`
- `experiments/unsupported-claim-rate-benchmark.md`

Current result: 432 deterministic evaluations across 72 generated fixtures
and six execution contracts. The evidence-gated Hermes-RLM contract has a
0.0000 unsupported-claim rate; the same RLM-shaped contract without evidence
gating has a 1.0000 unsupported-claim rate. This is the clearest ablation for
the paper claim that traceable evidence validation, not recursion alone, is
the useful systems contribution.

## Memory runtime benefit benchmark

Run:

```bash
python3 scripts/run-memory-runtime-benefit-benchmark.py
```

Outputs:

- `experiments/memory-runtime-benefit-benchmark.json`
- `experiments/memory-runtime-benefit-benchmark.md`

Current result: 240 deterministic evaluations across 20 generated fixtures,
four provider-failure profiles, and three memory policies. The guarded
operational-memory prior raises initial TraceGuard acceptance from 0.2500 to
1.0000 relative to no memory and reduces mean repair calls from 0.2500 to
0.0000. This is a runtime-control benchmark only. It does not call Hermes and
does not prove live model-quality, latency, token, or cost improvement.

## Memory contribution benchmarks

Run:

```bash
python3 scripts/run-memory-contribution-benchmarks.py
```

Outputs:

- `experiments/memory-contamination-robustness-benchmark.json`
- `experiments/memory-contamination-robustness-benchmark.md`
- `experiments/layered-memory-ablation-benchmark.json`
- `experiments/layered-memory-ablation-benchmark.md`
- `experiments/adaptive-repair-memory-benchmark.json`
- `experiments/adaptive-repair-memory-benchmark.md`

Current results:

- Memory contamination robustness: unguarded adversarial memory accepts the
  unsupported memory answer at 1.0000; TraceGuard accepts it at 0.0000.
- Layered memory ablation: Hermes-style prompt memory and RLM-FORGE guarded
  memory fix different deterministic failure classes; both together reach
  1.0000 initial accept with 0.0000 mean repair calls.
- Adaptive repair memory: a missing-handle prior learned after the first repair
  raises initial accept from 0.0000 to 0.8750 and reduces mean repair calls
  from 1.0000 to 0.1250 across repeated related tasks.

These are runtime-control benchmarks. They do not call Hermes and do not prove
live model-quality, latency, token, or cost improvement.
