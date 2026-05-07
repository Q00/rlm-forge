# Paper Key Sections ooo rlm Demo

This is the cleaner full demo for the contribution story. It uses the actual dependency `ouroboros rlm` path, the terminal counterpart to `ooo rlm`, over a mechanically generated target file containing the paper sections needed for the contribution and memory story.

## Command

```bash
uv run --extra dev ouroboros rlm experiments/paper-ooo-rlm-key-sections-target.txt --cwd /Users/jaegyu.lee/Project/ouroboros-rlm-hermes --debug
```

Reported result: `5` Hermes atomic execution sub-calls and RLM tree depth `1`.

## Flow

```text
paper/main.tex key sections
  |
  | mechanical extraction into paper-ooo-rlm-key-sections-target.txt
  v
ooo rlm / ouroboros rlm
  |
  | decomposes target into 4 bounded chunks
  v
4 child Hermes calls
  |
  | child_result:000..003
  v
1 parent Hermes synthesis call
  |
  | consumes all child results
  v
accepted parent synthesis with residual gaps
```

## Child Calls

| Order | Session | Chunk | Verdict | Parse note | Hermes memory injected |
| ---: | --- | --- | --- | --- | --- |
| 0 | `20260507_184010_f5fe9a` | `experiments/paper-ooo-rlm-key-sections-target.txt:1-80` | `success` | `completion JSON malformed; key fields recovered` | `true` |
| 1 | `20260507_184042_55e6b7` | `experiments/paper-ooo-rlm-key-sections-target.txt:81-160` | `completed` | `ok` | `true` |
| 2 | `20260507_184105_820761` | `experiments/paper-ooo-rlm-key-sections-target.txt:161-240` | `completed` | `ok` | `true` |
| 3 | `20260507_184126_0ef558` | `experiments/paper-ooo-rlm-key-sections-target.txt:241-302` | `passed` | `ok` | `true` |

## Parent Summary

The supplied child results collectively support a bounded parent synthesis of the target as a runtime-systems paper about RLM-FORGE. Across the abstract, contribution framing, architecture section, operational-memory experiment, deterministic memory benchmarks, and conclusion excerpt, the target argues that Recursive Language Models can be runtime-lifted into an existing Hermes Agent execution contract rather than requiring a new recursive model architecture. The central mechanism is a two-layer ownership split: Ouroboros owns recursive scheduling, termination, trace persistence, evidence validation, and state mutation, while Hermes executes one bounded inner inference at a time through HermesCliRuntime and is explicitly constrained not to recursively call Ouroboros or invoke ooo commands. TraceGuard acts as the evidence gate for parent synthesis, rejecting unsupported structured claims before committed state mutation. The preserved RLM control surfaces are bounded context partitioning, explicit parent-child call graphs, child evidence handles, replayable intermediate outputs, provider-swappable inner execution, and evidence-gated parent synthesis. The supplied results also support a narrow experimental framing: the live truncation fixture is described as showing score parity after claim-aware rescoring, not a quality win; a 24-cell primary portability matrix across Hermes+GLM, Claude Code, and Codex is reported as passing the mandatory runtime contract; and a second 24-cell matrix with experimental read-write operational memory enabled is reported as passing while still requiring fresh child evidence. The memory claims are deliberately bounded. RLM-FORGE memory is described as an allowlisted operational-prior store, not factual evidence: it may carry schema or retry priors such as preserving fact_id with evidence_chunk_id, but accepted evidence manifests are rebuilt from current child outputs. The target further distinguishes Hermes built-in prompt memory from RLM-FORGE guarded memory as separable behavioral/runtime layers. Deterministic memory benchmarks are presented as runtime-control evidence only: TraceGuard rejects adversarial answer-memory contamination, guarded operational memory reduces missing-handle repair work, layered memory improves initial acceptance in the modeled setting, and adaptive repair memory reduces mean repair calls while preserving final TraceGuard acceptance.

## Accepted Claims

- `KEY-OOO-RLM-CLAIM-001` RLM-FORGE presents RLM as a deployable runtime primitive in an existing agent runtime, not as a new model architecture. Evidence: Chunk 001 cites abstract lines 42-54 and contribution lines 108-117; chunk 004 cites conclusion lines 970-975..
- `KEY-OOO-RLM-CLAIM-002` The architecture separates recursive orchestration from bounded inner inference: Ouroboros owns recursion and trace/control state, Hermes performs bounded local calls, and TraceGuard decides whether parent synthesis can be committed. Evidence: Chunk 002 cites lines 241-242, 280-291, and 311-313..
- `KEY-OOO-RLM-CLAIM-003` RLM-FORGE preserves operational RLM control surfaces at runtime: bounded sub-calls, explicit parent-child call graphs, evidence handles, replayable outputs, provider portability, and evidence-gated synthesis. Evidence: Chunk 001 cites lines 42-54 and 114-117; chunk 002 cites lines 246-270 and 272-275; chunk 004 cites lines 970-975..
- `KEY-OOO-RLM-CLAIM-004` TraceGuard enforces evidence discipline by requiring accepted child evidence handles and rejecting unsupported or memory-contaminated factual claims. Evidence: Chunk 001 cites lines 125-135; chunk 002 cites lines 288-291; chunk 004 cites lines 566-571..
- `KEY-OOO-RLM-CLAIM-005` The reported live evidence is contract-pass and runtime-control evidence, not a broad live model-quality, latency, token, or cost improvement claim. Evidence: Chunk 001 cites lines 69-74 and 146-150; chunk 002 cites lines 272-275; chunk 003 cites lines 518-522 and 537-541; chunk 004 cites lines 555-564 and 580-583..
- `KEY-OOO-RLM-CLAIM-006` Operational memory is bounded to runtime priors and is excluded from admissible factual evidence; accepted evidence is rebuilt from fresh child outputs. Evidence: Chunk 001 cites lines 136-150; chunk 003 cites lines 480-495 and 515-522; chunk 004 cites lines 555-564 and 976-983..
- `KEY-OOO-RLM-CLAIM-007` Hermes built-in memory and RLM-FORGE guarded memory are treated as separable runtime layers with different roles. Evidence: Chunk 001 cites lines 63-68 and 143-150; chunk 003 cites lines 524-535; chunk 004 cites lines 571-575 and 984-985..

## Evidence Boundary

- Parent verdict: `completed`
- All child results consumed: `true`
- All claims have child support: `true`
- Memory is prior, not evidence.
- Caveat: this is the actual `ooo rlm` recursive path. It does not automatically invoke the separate `rlm_forge.traceguard.validate_parent_synthesis` function.

## Residual Gaps

- This parent synthesis is limited to the supplied target excerpts and child results; it does not access or verify the full file outside the provided chunks.
- Several supplied chunks are marked truncated or begin/end mid-section, including contribution text after line 150, lifecycle content after line 317, the full memory-runtime-benefit table context, and the conclusion sentence after line 985.
- The first child result has wrapper-level null verdict/confidence/evidence fields despite containing a JSON completion with verdict success and confidence 0.91; this synthesis consumes it using the embedded completion payload and notes the wrapper inconsistency.
- The reported 24-cell live matrices, scorer correction, deterministic ablations, and memory benchmarks are treated as textual claims in the supplied evidence, not independently validated experimental results.
- The conclusion excerpt cuts off after stating that the two memory layers have separable runtime, so any final concluding claims beyond that point are unavailable.
