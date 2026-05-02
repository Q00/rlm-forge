# RLM-FORGE

A runtime layer for executing **Recursive Language Model** sub-calls through
**Hermes Agent** (Nous Research), with Ouroboros owning recursion, trace replay,
and evidence validation.

> **Implementation artifact for runtime-lifted RLM over Hermes Agent.**
> Inspired by Zhang/Kraska/Khattab — *Recursive Language Models* (arXiv 2512.24601).

---

## Current benchmark status

This is not a new model architecture. It is a runtime-hosted realization of
RLM: Hermes executes bounded inner calls, Ouroboros manages recursive state,
and TraceGuard enforces parent synthesis against accepted child evidence.

On the same long-context truncation fixture (real Hermes via `HermesCliRuntime`
v0.11.0, four chunks selected and two omitted), the claim-aware scorer now
rates the vanilla single call and recursive RLM as a **tie**:

| | vanilla single call | recursive RLM |
| --- | --- | --- |
| Hermes sub-calls | 1 | 5 |
| Quality score | 1.00 | 1.00 |
| Score delta | | +0.00 |
| `omitted_fact_safety_score` | 1.00 | 1.00 |
| `claimed_omitted_fact_ids` | `[]` | `[]` |
| `cited_retained_fact_ids` | `LC-001..LC-004` | `LC-001..LC-004` |

Earlier artifacts reported a `+0.20` RLM advantage because the scorer treated
guarded residual-gap text such as “LC-005 and LC-006 cannot be claimed” as a
positive omitted-fact claim. The corrected scorer distinguishes unavailable
gap mentions from observed evidence claims. The remaining contribution is the
Hermes/RLM integration path and replayable trace, not a demonstrated quality
win on this single fixture.

Persisted side-by-side artifact: [`benchmarks/rlm-long-context-truncation-v1.json`](benchmarks/rlm-long-context-truncation-v1.json).

TraceGuard enforcement demo:
[`experiments/traceguard-demo.md`](experiments/traceguard-demo.md)
shows the new evidence gate in action. Safe parent synthesis is accepted,
an omitted fact is rejected with `unsupported_fact_id`, and chunk-only
evidence is rejected with `chunk_handle_without_fact`. This turns the main
claim from “we measured unsupported claims” into “we can enforce the evidence
contract at parent synthesis time.”

TraceGuard's public entry point is:

```python
validate_parent_synthesis(
    evidence_manifest=build_manifest_from_fixture(fixture),
    parent_synthesis=parent_json,
)
```

Representative no-API output:

```text
safe_parent_synthesis: ACCEPT (unsupported_claim_rate=0.0000)
unsafe_omitted_fact: REJECT (unsupported_claim_rate=0.2000)
chunk_only_no_fact: REJECT (unsupported_claim_rate=1.0000)
```

Judge verification checklist:

| Claim | Artifact |
| --- | --- |
| TraceGuard enforces parent synthesis evidence handles | [`experiments/traceguard-demo.md`](experiments/traceguard-demo.md) |
| Evidence-gated recursion is the mechanism, not recursion alone | [`experiments/unsupported-claim-rate-benchmark.md`](experiments/unsupported-claim-rate-benchmark.md) |
| Claim-aware scorer avoids the earlier false win | [`experiments/claim-aware-omitted-fact-suite.md`](experiments/claim-aware-omitted-fact-suite.md) |
| Broad deterministic scorer coverage | [`experiments/synthetic-omitted-fact-benchmark.md`](experiments/synthetic-omitted-fact-benchmark.md) |
| Live Hermes fixture shows score parity | [`benchmarks/rlm-long-context-truncation-v1.json`](benchmarks/rlm-long-context-truncation-v1.json) |

These offline artifacts do not require a Hermes API key. TraceGuard improves
unsupported-claim enforcement; it does not change the live fixture quality
score, which remains a tie.

Additional scorer experiment:
[`experiments/claim-aware-omitted-fact-suite.md`](experiments/claim-aware-omitted-fact-suite.md)
runs seven controlled completion shapes without Hermes. It verifies that the
corrected scorer accepts guarded gap mentions but rejects positive omitted-fact
claims and omitted evidence references.

Broader scorer stress test:
[`experiments/synthetic-omitted-fact-benchmark.md`](experiments/synthetic-omitted-fact-benchmark.md)
generates 108 truncation fixtures and scores seven deterministic completion
strategies, for 756 total scorer checks. It is not a live-model benchmark; it
supports the narrower claim that the evaluation harness separates guarded gap
mentions, unsupported omitted-fact claims, chunk-only citations, and missing
boundary reports across many fixture shapes.

Contract ablation:
[`experiments/unsupported-claim-rate-benchmark.md`](experiments/unsupported-claim-rate-benchmark.md)
compares six execution contracts over 72 generated fixtures. The
evidence-gated Hermes-RLM contract has a 0.0000 unsupported-claim rate, while
the same recursive shape without evidence gating has a 1.0000 unsupported-claim
rate. This supports the precise systems claim: recursion is useful because it
creates evidence handles that Ouroboros can validate, not because recursion
alone makes hallucination impossible.

---

## Why Hermes

Hermes was the right inner LM precisely because we did not have to fight it:

1. **Provider-agnostic** — swap the inner model with `hermes model` (OpenRouter,
   NIM, custom endpoints). The recursion is independent of the chosen LLM.
2. **Existing RPC tool reuse** — Hermes' "multi-step pipeline → zero-context
   turn" RPC pattern is structurally identical to an RLM sub-call envelope.
   No new REPL, sandbox, or transport was built.
3. **Quiet, structured I/O** — Hermes accepts a JSON envelope and returns one,
   so Ouroboros can call it like a function. The `HermesCliRuntime` adapter is
   ~750 lines and ships with Ouroboros; we did not modify it.
4. **Subagent spawn potential** — Hermes' isolated subagent mechanism opens a
   path to *horizontal* RLM tree expansion in future work.

The RLM scaffold treats Hermes as the only recursive boundary. Hermes proposes
local decomposition, atomic execution, summary, or synthesis for one bounded
node; Ouroboros owns the recursion, termination, and trace replay.

TraceGuard adds the missing enforcement step: parent synthesis is valid only
when every structured claim cites an accepted child evidence handle. Recursive
shape alone is not trusted.

---

## Two empirically-verified integration paths

| Path | Entry point | Where Hermes is called |
| --- | --- | --- |
| **Recursive scaffold** | `ooo rlm --benchmark` | `ouroboros.rlm.loop.RLMOuterScaffoldLoop` drives 1 root + 4 chunk sub-calls through `HermesCliRuntime` |
| **AC decomposition pipeline** | `decompose_ac(hermes_runtime=...)` | `ouroboros.execution.decomposition.decompose_ac` accepts an `AgentRuntime` and delegates child-AC generation to Hermes |

The same `HermesCliRuntime` adapter serves both. The default `ooo run` and
`ooo evolve` flow keep their original LLM-only behaviour; passing
`hermes_runtime=None` (the default) bypasses every RLM-specific branch.

---

## Quickstart (judges, ~5 minutes)

### 1. Install Hermes

Hermes Agent is a separate project from Nous Research:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc       # or ~/.zshrc
hermes setup           # configure your provider and API key
hermes --version       # confirm v0.11+ is installed
```

The simplest provider for judges is OpenRouter — set `OPENROUTER_API_KEY`
and pick any model.

### 2. Install this submission

```bash
git clone https://github.com/<user>/rlm-forge.git
cd rlm-forge
pip install -e .
```

The `pyproject.toml` pins a git-ref dependency on the Ouroboros commit that
contains the RLM modules and the claim-aware scorer until upstream releases
them on PyPI.

### 3. Run the truncation benchmark

```bash
ooo rlm --truncation-benchmark
```

Expected output (real Hermes, ~1 minute):

```
Shared truncation benchmark completed; vanilla Hermes and recursive RLM
outputs were recorded.
hermes_subcalls: vanilla=1, rlm=5
chunks: selected=4, omitted=2
quality: vanilla=1.00, rlm=1.00, delta=+0.00, rlm_outperforms_vanilla=False
```

### 4. Replay the persisted artifact (no Hermes call)

```bash
python3 -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json
```

This prints the committed JSON metrics, so judges without a Hermes API key can
still inspect the recorded run.

---

## Examples

| Script | What it does | Hermes calls |
| --- | --- | --- |
| `examples/01-dry-run.sh` | Validate the RLM path, no side effects | 0 |
| `examples/02-vanilla-baseline.sh` | One vanilla Hermes call on the truncation fixture | 1 |
| `examples/03-truncation-comparison.sh` | Side-by-side vanilla vs recursive RLM | 1 + 5 |

Each script is a one-liner that wraps the Ouroboros CLI.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the layer model,
orchestration boundaries, and 6-step sub-call lifecycle. The full concept
design is `docs/guides/recursive-language-model.md` in the upstream
Ouroboros repository (1,580 lines).

```
User
  |
  v
ooo rlm
  |
  v
Ouroboros outer scaffold
  - validates ambiguity <= 0.2
  - owns ACTree recursion, max depth 5
  - owns RLM tree state, scheduling, termination, trace persistence
  - calls Hermes through HermesCliRuntime
  |
  v
Hermes inner LM layer
  - receives one bounded recursive sub-call at a time
  - proposes decomposition, atomic execution, summary, or synthesis
  - returns structured JSON evidence to Ouroboros
```

---

## What this submission is and is not

This is an **MVP** designed to demonstrate that Hermes can serve as the inner
recursive LM in an RLM-style scaffold with replayable traces and deterministic
evaluation. It is not a production-ready RLM service, does not claim novelty
over the Zhang et al. paper, and no longer claims a quality advantage from the
single truncation fixture. Its contribution is a practical integration recipe
built on top of the Hermes Agent runtime.

---

## License

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

- **Hermes Agent** — Nous Research. The inner LM runtime that made this practical.
- **Ouroboros** — the workflow scaffold that owns the recursion and traces.
- **Zhang, Kraska, Khattab (MIT, 2025)** — *Recursive Language Models*
  (arXiv 2512.24601), the conceptual seed for this work.
