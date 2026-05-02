# Experiments

This directory contains small reproducible experiments that do not require a
live Hermes API call.

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
