<p align="center">
  <img src="assets/rlm-forge-hero.webp" alt="RLM-FORGE — Frontier Recursion Lab" />
</p>

<p align="center">
  <img alt="RLM-FORGE sigil" src="https://img.shields.io/badge/RLM--FORGE-Hermes%20Inner%20Runtime-7170ff?style=for-the-badge&labelColor=08090a" />
  <img alt="TraceGuard" src="https://img.shields.io/badge/TraceGuard-evidence--gated-10b981?style=for-the-badge&labelColor=08090a" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-0f1011?style=for-the-badge&labelColor=08090a" />
</p>

<h1 align="center">RLM-FORGE</h1>

<p align="center">
  <strong>A tiny recursive-runtime forge for Hermes Agent.</strong>
  <br />
  Ouroboros owns the recursion. Hermes performs bounded inner calls. TraceGuard refuses unsupported synthesis.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a>
  ·
  <a href="#what-this-proves">What this proves</a>
  ·
  <a href="#traceguard">TraceGuard</a>
  ·
  <a href="docs/architecture.md">Architecture</a>
  ·
  <a href="paper/main.pdf">Paper</a>
</p>

---

> **Implementation artifact for runtime-lifted RLM over Hermes Agent.**  
> Inspired by Zhang/Kraska/Khattab — *Recursive Language Models* (arXiv 2512.24601).

```text
╭────────────────────────────────────────────────────────────────────╮
│                            RLM-FORGE                               │
│                                                                    │
│  user request                                                      │
│      │                                                             │
│      ▼                                                             │
│  Ouroboros outer scaffold       recursion · state · trace replay   │
│      │                                                             │
│      ▼                                                             │
│  Hermes Agent inner runtime      bounded JSON sub-calls            │
│      │                                                             │
│      ▼                                                             │
│  TraceGuard                    parent claims must cite evidence    │
╰────────────────────────────────────────────────────────────────────╯
```

RLM-FORGE is not a new model architecture. It is a runtime-hosted realization of a Recursive Language Model style execution loop:

- **Hermes Agent** acts as the inner LM runtime.
- **Ouroboros** owns recursion, scheduling, state mutation, termination, and trace replay.
- **TraceGuard** validates that parent synthesis only claims facts backed by accepted child evidence handles.

The result is a compact, replayable, evidence-gated RLM scaffold built on top of the existing Hermes tool/runtime interface.

---

## What this proves

RLM-FORGE makes one careful claim:

> Recursive execution is useful when it creates structured evidence handles that an outer scaffold can validate. Recursion alone is not trusted.

On the current live Hermes long-context truncation fixture, recursive RLM and vanilla single-call Hermes are an honest **tie**:

| Metric | Vanilla single call | Recursive RLM |
| --- | ---: | ---: |
| Hermes sub-calls | 1 | 5 |
| Quality score | 1.00 | 1.00 |
| Score delta | — | +0.00 |
| `omitted_fact_safety_score` | 1.00 | 1.00 |
| `claimed_omitted_fact_ids` | `[]` | `[]` |
| `cited_retained_fact_ids` | `LC-001..LC-004` | `LC-001..LC-004` |

Earlier artifacts reported a `+0.20` RLM advantage because the scorer treated guarded residual-gap text such as “LC-005 and LC-006 cannot be claimed” as a positive omitted-fact claim. The claim-aware scorer fixes that. The contribution here is **not** a quality win on one fixture; it is the Hermes-backed recursive runtime path plus deterministic evidence enforcement.

Persisted artifact: [`benchmarks/rlm-long-context-truncation-v1.json`](benchmarks/rlm-long-context-truncation-v1.json)

---

## Why Hermes

Hermes is unusually well-suited to this kind of runtime experiment:

| Hermes property | Why it matters for RLM-FORGE |
| --- | --- |
| Provider-agnostic runtime | The inner LM can be swapped with `hermes model` without changing the recursion scaffold. |
| Tool/RPC-shaped execution | Hermes' structured “one bounded task in, one result out” style maps naturally to RLM sub-call envelopes. |
| Quiet structured I/O | Ouroboros can call Hermes like a function and validate the resulting JSON. |
| Isolated subagent potential | Future RLM trees can expand horizontally through Hermes subagents instead of a single serial path. |

RLM-FORGE treats Hermes as the only recursive inference boundary. Hermes proposes local decomposition, atomic execution, summary, or synthesis for one bounded node. Ouroboros alone decides recursion, mutation, retry, and termination.

---

## TraceGuard

TraceGuard is the small deterministic layer that turns a trace into an enforceable contract.

```python
from rlm_forge import build_manifest_from_fixture, validate_parent_synthesis

result = validate_parent_synthesis(
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

TraceGuard rejects two important failure modes:

| Failure mode | Rejection reason |
| --- | --- |
| Parent claims an omitted fact not present in accepted child evidence | `unsupported_fact_id` |
| Parent cites a chunk handle but no supported fact | `chunk_handle_without_fact` |

Demo artifact: [`experiments/traceguard-demo.md`](experiments/traceguard-demo.md)

---

## Quickstart

RLM-FORGE requires **Python 3.12+**.

### 1. Install Hermes

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
source ~/.bashrc       # or ~/.zshrc
hermes setup           # configure provider + API key
hermes --version       # confirm v0.11+
```

The simplest provider for judges is OpenRouter: set `OPENROUTER_API_KEY` and select any model.

### 2. Install RLM-FORGE

```bash
git clone https://github.com/Q00/rlm-forge.git
cd rlm-forge
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

The package pins a git-ref dependency on the Ouroboros commit that contains the RLM modules and claim-aware scorer until those APIs are released on PyPI.

### 3. Verify without a Hermes API key

```bash
pytest -q
python3 -m rlm_forge.replay benchmarks/rlm-long-context-truncation-v1.json
python3 scripts/run-traceguard-demo.py
```

Expected replay signal:

```text
quality: vanilla=1.00, rlm=1.00, delta=+0.00, rlm_outperforms_vanilla=False
```

### 4. Run the live truncation benchmark

```bash
ooo rlm --truncation-benchmark
```

Expected live shape:

```text
Shared truncation benchmark completed; vanilla Hermes and recursive RLM outputs were recorded.
hermes_subcalls: vanilla=1, rlm=5
chunks: selected=4, omitted=2
quality: vanilla=1.00, rlm=1.00, delta=+0.00, rlm_outperforms_vanilla=False
```

---

## Two integration paths

| Path | Entry point | Where Hermes is called |
| --- | --- | --- |
| Recursive scaffold | `ooo rlm --truncation-benchmark` | `ouroboros.rlm.loop.RLMOuterScaffoldLoop` drives 1 root + 4 chunk sub-calls through `HermesCliRuntime`. |
| AC decomposition pipeline | `decompose_ac(hermes_runtime=...)` | `ouroboros.execution.decomposition.decompose_ac` accepts an `AgentRuntime` and delegates child-AC generation to Hermes. |

The default `ooo run` and `ooo evolve` flows keep their original LLM-only behaviour. Passing `hermes_runtime=None` bypasses every RLM-specific branch.

---

## Evidence map for judges

| Claim | Artifact |
| --- | --- |
| TraceGuard enforces parent synthesis evidence handles | [`experiments/traceguard-demo.md`](experiments/traceguard-demo.md) |
| Evidence-gated recursion is the mechanism, not recursion alone | [`experiments/unsupported-claim-rate-benchmark.md`](experiments/unsupported-claim-rate-benchmark.md) |
| Claim-aware scorer avoids the earlier false win | [`experiments/claim-aware-omitted-fact-suite.md`](experiments/claim-aware-omitted-fact-suite.md) |
| Broad deterministic scorer coverage | [`experiments/synthetic-omitted-fact-benchmark.md`](experiments/synthetic-omitted-fact-benchmark.md) |
| Live Hermes fixture remains an honest tie | [`benchmarks/rlm-long-context-truncation-v1.json`](benchmarks/rlm-long-context-truncation-v1.json) |
| Architecture boundary | [`docs/architecture.md`](docs/architecture.md) |
| Hermes setup notes | [`docs/hermes-setup.md`](docs/hermes-setup.md) |
| Technical note | [`paper/main.pdf`](paper/main.pdf) |

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

## Repository layout

```text
rlm-forge/
├─ src/rlm_forge/
│  ├─ traceguard.py       # evidence-gated parent synthesis validator
│  ├─ replay.py           # offline artifact replay CLI
│  └─ __init__.py         # public API surface
├─ tests/                 # no-API CI tests
├─ experiments/           # deterministic scorer + TraceGuard artifacts
├─ benchmarks/            # persisted Hermes truncation benchmark
├─ docs/                  # architecture, setup, benchmark notes
├─ examples/              # small command wrappers
└─ paper/                 # hackathon technical note
```

---

## What this submission is and is not

| It is | It is not |
| --- | --- |
| A Hermes-backed RLM runtime MVP | A new model architecture |
| A replayable trace and evidence-validation scaffold | A claim that recursion alone prevents hallucination |
| A practical integration recipe for Hermes + Ouroboros | A production RLM service |
| A deterministic TraceGuard enforcement demo | A benchmark suite proving model-quality superiority |

---

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

Current local verification:

```text
9 passed
```

---

## License

MIT. See [`LICENSE`](LICENSE).

## Acknowledgements

- **Hermes Agent** — Nous Research. The inner runtime that made the experiment practical.
- **Ouroboros** — the outer scaffold that owns recursion, state, and traces.
- **Zhang, Kraska, Khattab** — *Recursive Language Models*, the conceptual seed for this work.
